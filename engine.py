"""
Audit engine
============
Crawls a website the way search engines and AI assistants do, then runs every check.

There is no Streamlit code in this file. The user interface passes a `progress` callback,
and the engine reports what it is doing (stage started, page crawled, log line…) so the
UI can animate the crawl live.

Pipeline (one stage each):
  1. connect  – download the page, follow redirects, read HTTP headers
  2. robots   – robots.txt and llms.txt
  3. sitemap  – sitemap.xml or .xml.gz (page count, freshness)
  4. page     – analyse the main page's HTML in depth
  5. crawl    – visit up to N linked pages on the same site
  6. bots     – check robots.txt rules for 12 bots + knock on the door as each AI bot
  7. links    – check outgoing links for errors
  8. shots    – desktop and mobile screenshots (headless Chrome / Edge, if installed)
  9. score    – run 56 weighted checks and build the result

Speed: robots.txt, llms.txt, sitemaps, the favicon, outgoing links and the screenshots are fetched
in background threads, and every stage has a time budget (see the settings below), so an audit
takes about 10-20 seconds even on slow servers. If a stage crashes, it is logged and skipped with
safe defaults; only a failed connection to the main page stops the audit.

Fields added in version 2.1 (all optional for the UI): crawled pages have `final_url` and
`blocked`; the result has `link_unverified` [(url, reason)], `crawl_skipped_robots` and
`sitemap.listed` (how many sitemaps robots.txt lists).
"""

import warnings

warnings.filterwarnings("ignore")  # hide harmless SSL / urllib3 warnings on macOS

import base64
import datetime
import gzip
import html as htmllib
import io
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from urllib3.exceptions import HTTPError as Urllib3Error

# Everything a network request may raise (requests errors are OSErrors; reading a streamed body
# can also raise urllib3 errors such as ReadTimeoutError or ProtocolError).
NET_ERRORS = (OSError, Urllib3Error, ValueError)

from explanations import AI_CATS, CHECKS, SEO_CATS

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
# Some sites (e.g. w3.org) refuse browser-looking scripts but accept an honest bot name.
BOT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SEO-AI-Auditor/2.0; student project)",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
TIMEOUT = 15          # main page (seconds to wait for an answer)
CONNECT_TIMEOUT = 6   # main page: seconds to wait for the server to accept the connection
PAGE_TIMEOUT = (4, 6)  # (connect, read) seconds for each crawled page / bot probe / link check
FILE_TIMEOUT = (4, 6)  # robots.txt, llms.txt, sitemap, favicon
# Time budgets keep a whole audit at roughly 10-20 seconds, even on slow or hostile servers.
FILES_BUDGET = 8      # robots.txt + llms.txt (fetched in parallel, in the background)
SITEMAP_BUDGET = 5    # sitemap stage (the usual addresses are already downloading)
CRAWL_BUDGET = 8      # seconds the crawl stage may take at most
BOT_BUDGET = 7        # seconds for all live bot tests together
LINK_BUDGET = 10      # outgoing link checks (they run in the background during crawl and bots)
SHOT_TIMEOUT = 15     # one headless-browser screenshot (slow pages are skipped)
SKIP_EXT = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".zip", ".rar", ".mp4",
            ".mp3", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".exe", ".dmg", ".xml",
            ".css", ".js", ".ico", ".avif", ".json", ".rss", ".atom", ".txt", ".gz", ".tar",
            ".7z", ".apk", ".msi", ".csv", ".mov", ".avi", ".wav", ".woff", ".woff2", ".ttf")
# Pages a crawler should not waste its small budget on (login, cart, search, calendars, tags…)
JUNK_PATH_RE = re.compile(
    r"(^|/)(log-?in|log-?out|sign-?in|sign-?up|sign-?out|register|auth|oauth|sso|account|"
    r"my-?account|profile|cart|basket|checkout|wishlist|search|wp-admin|wp-login\.php|wp-json|"
    r"xmlrpc\.php|feed|rss|atom|print|share|cdn-cgi|calendar|events?/\d{4}|tag|tags|author|"
    r"page/\d+|comment-page-\d+|attachment|trackback|amp|subscribe|unsubscribe|password|"
    r"reset|cookies?(-policy|-settings)?|admin)(/|$|\.)"
    # wiki "namespace" pages: /wiki/Special:Random, /wiki/Talk:SEO, /wiki/File:Logo.png …
    r"|/(special|talk|user|user_talk|file|template|help|portal|wikipedia|category|module|"
    r"mediawiki|draft)(_talk)?:", re.I)
JUNK_QUERY_RE = re.compile(r"(^|&)(s|q|query|search|replytocom|share|print|sort|order|filter|"
                           r"lang|redirect|return|returnurl|next|ref|utm_[a-z]+|session|sid|"
                           r"date|month|year|ical|outlook-ical)=", re.I)
# Section names a visitor (and an auditor) would look at first
PRIORITY_PATH_RE = re.compile(
    r"(^|/)(about|about-us|contact|contact-us|blog|news|products?|services?|pricing|faq|docs?|"
    r"documentation|help|support|team|careers|admissions?|courses?|academics|departments?|"
    r"research|programs?|shop|features|solutions)(/|$|\.)", re.I)

# Bots we test. `robots_scored` = counts for the robots.txt score (search + AI answer bots).
# `answer_bot` = AI assistant bots used for the live "knock on the door" test score.
# `ua` = user-agent string used for the live test (None = robots.txt token only, no real crawler).
BOTS = [
    dict(token="Googlebot", label="Google Search", company="Google",
         purpose="Search results and AI Overviews", robots_scored=True, answer_bot=False,
         ua="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"),
    dict(token="Bingbot", label="Bing and Copilot", company="Microsoft",
         purpose="Search results and Copilot answers", robots_scored=True, answer_bot=False,
         ua="Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)"),
    dict(token="OAI-SearchBot", label="ChatGPT search", company="OpenAI",
         purpose="Pages shown in ChatGPT search", robots_scored=True, answer_bot=True,
         ua="Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-SearchBot/1.0; "
            "+https://openai.com/searchbot"),
    dict(token="ChatGPT-User", label="ChatGPT browsing", company="OpenAI",
         purpose="Opens pages when a user asks ChatGPT", robots_scored=True, answer_bot=True,
         ua="Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; "
            "+https://openai.com/bot"),
    dict(token="PerplexityBot", label="Perplexity", company="Perplexity",
         purpose="Pages cited in Perplexity answers", robots_scored=True, answer_bot=True,
         ua="Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; "
            "+https://perplexity.ai/perplexitybot)"),
    dict(token="Claude-SearchBot", label="Claude search", company="Anthropic",
         purpose="Pages shown in Claude search", robots_scored=True, answer_bot=True,
         ua="Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-SearchBot/1.0; "
            "+https://www.anthropic.com)"),
    dict(token="Claude-User", label="Claude browsing", company="Anthropic",
         purpose="Opens pages when a user asks Claude", robots_scored=True, answer_bot=True,
         ua="Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-User/1.0; "
            "+https://www.anthropic.com)"),
    dict(token="GPTBot", label="OpenAI training", company="OpenAI",
         purpose="Collects text to train models", robots_scored=False, answer_bot=False,
         ua="Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.1; "
            "+https://openai.com/gptbot"),
    dict(token="ClaudeBot", label="Anthropic training", company="Anthropic",
         purpose="Collects text to train models", robots_scored=False, answer_bot=False,
         ua="Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; "
            "+claudebot@anthropic.com)"),
    dict(token="Google-Extended", label="Gemini training", company="Google",
         purpose="Permission token for Gemini training", robots_scored=False, answer_bot=False,
         ua=None),
    dict(token="Applebot-Extended", label="Apple AI training", company="Apple",
         purpose="Permission token for Apple Intelligence", robots_scored=False, answer_bot=False,
         ua=None),
    dict(token="CCBot", label="Common Crawl", company="Common Crawl",
         purpose="Open dataset used to train many models", robots_scored=False, answer_bot=False,
         ua="CCBot/2.0 (https://commoncrawl.org/faq/)"),
]

STATUS_POINTS = {"pass": 1.0, "warn": 0.5, "fail": 0.0}
STOP_WORDS = set("""a an and are as at be by for from has have how in is it its of on or our
that the this to was were what when where which who why will with you your we us home page
welcome official site website best top""".split())
GENERIC_ANCHORS = {"click here", "here", "read more", "more", "learn more", "link", "this",
                   "click", "details", "continue", "go"}
QUESTION_RE = re.compile(
    r"^(what|why|how|when|where|who|which|can|does|do|is|are|should|will)\b", re.I)


class AuditError(Exception):
    """A problem we can explain to the user in plain words (blocked, 404, not HTML…)."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def normalize_url(raw):
    raw = (raw or "").strip().strip("\"'<>").strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        raw = "https:" + raw
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    return raw


def has_scheme(raw):
    return bool(re.match(r"^\s*[\"'<]*\s*(https?:)?//", raw or "", re.I))


def tidy_url(url):
    """Lower-case the scheme and host and drop a default port (https://x.com:443/ -> https://x.com/)."""
    try:
        p = urlparse(url)
    except ValueError:
        return url
    host = (p.hostname or "").lower()
    if not host:
        return url
    port = p.port if p.port and (p.scheme, p.port) not in (("https", 443), ("http", 80)) else None
    netloc = host + (":%d" % port if port else "")
    return p._replace(scheme=p.scheme.lower(), netloc=netloc).geturl()


def bare(host):
    host = (host or "").lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


INDEX_RE = re.compile(r"/(index|default|home)\.(html?|php|aspx?|jsp)$", re.I)


def url_key(url):
    """One key per real page: ignores http/https, www, a trailing slash, index.html and #anchors.

    Used to avoid crawling (and scoring) the same page twice under two addresses."""
    try:
        p = urlparse(url.split("#")[0])
    except ValueError:
        return url
    path = INDEX_RE.sub("/", p.path or "/").rstrip("/") or "/"
    return bare(p.netloc) + path + ("?" + p.query if p.query else "")


def clean_text(s):
    return " ".join((s or "").split())


def meta_content(soup, **attrs):
    tag = soup.find("meta", attrs=attrs)
    if not tag:
        return ""
    val = tag.get("content") or ""
    return (" ".join(val) if isinstance(val, list) else val).strip()


def rel_values(tag):
    rel = tag.get("rel") or []
    if isinstance(rel, str):
        rel = rel.split()
    return [r.lower() for r in rel]


def looks_like_html(text, ctype=""):
    head = text.lstrip()[:200].lower()
    return "html" in (ctype or "").lower() or head.startswith(("<!doctype", "<html", "<?xml", "<head"))


def get_text_file(url, verify=True, headers=None):
    """Fetch a small text resource (robots.txt, llms.txt, sitemap). -> (status, text, content_type)

    Handles gzip-compressed sitemaps (sitemap.xml.gz) and stops reading after 5 MB."""
    headers = headers or HEADERS

    def _get(h):
        r = requests.get(url, headers=h, timeout=FILE_TIMEOUT, allow_redirects=True,
                         verify=verify, stream=True)
        raw = r.raw.read(5_000_000, decode_content=True)
        r.close()
        return r, raw

    try:
        r, raw = _get(headers)
        if r.status_code in (401, 403, 406, 429) and headers is not BOT_HEADERS:
            r, raw = _get(BOT_HEADERS)  # retry with an honest bot name
        if raw[:2] == b"\x1f\x8b":  # a .gz file (requests only un-gzips Content-Encoding)
            try:
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read(20_000_000)
            except (OSError, EOFError):
                pass
        text = raw.decode("utf-8-sig", errors="replace")
        return r.status_code, text, r.headers.get("Content-Type", "")
    except NET_ERRORS:
        return None, "", ""


CHALLENGE_MARKERS = (
    "awswafcookiedomainlist", "gokuprops",                              # AWS WAF (Amazon)
    "/cdn-cgi/challenge-platform", "cf_chl_", "<title>just a moment",   # Cloudflare
    "captcha-delivery.com", "px-captcha",                                # DataDome, PerimeterX
    "bm-verify=", "/_sec/verify", "triggerinterstitialchallenge",       # Akamai Bot Manager
    "/errors/validatecaptcha", "sgcaptcha",                              # Amazon, SiteGround
    "enable javascript and cookies to continue",
)


def is_bot_challenge(status, body, headers=None):
    """True if the server sent an anti-bot / CAPTCHA page instead of the real content."""
    if headers is not None and (headers.get("cf-mitigated") or "").lower() == "challenge":
        return True  # Cloudflare says so explicitly
    if status == 202 and len(body) < 20000:
        return True
    if len(body) > 60000:  # real pages are big; challenge pages are tiny
        return False
    head = body[:60000].decode("utf-8", errors="ignore").lower()
    return any(m in head for m in CHALLENGE_MARKERS)


def make_soup(body, resp):
    """Parse raw bytes so the right character set is used (header charset wins, like browsers)."""
    ctype = resp.headers.get("Content-Type", "")
    header_charset = resp.encoding if "charset" in ctype.lower() else None
    try:
        return BeautifulSoup(body, "lxml", from_encoding=header_charset)
    except LookupError:
        return BeautifulSoup(body, "lxml")


def visible_text_of(soup_bytes_or_soup):
    soup = soup_bytes_or_soup
    for t in soup(["script", "style", "noscript", "svg", "template"]):
        t.decompose()
    body = soup.body or soup
    return body.get_text(" ", strip=True)


def path_of(url):
    p = urlparse(url)
    return (p.path or "/") + ("?" + p.query if p.query else "")


def collect_schema(obj, types, keys, depth=0):
    """Walk JSON-LD recursively, collecting every @type and every key name."""
    if depth > 50:
        return
    if isinstance(obj, dict):
        t = obj.get("@type")
        for x in (t if isinstance(t, list) else [t]):
            if isinstance(x, str) and x.strip():
                types.add(re.split(r"[/:#]", x.strip().rstrip("/"))[-1])
        for k, v in obj.items():
            keys.add(k)
            collect_schema(v, types, keys, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            collect_schema(item, types, keys, depth + 1)


# ---------------------------------------------------------------------------
# robots.txt – evaluated the way Google does (RFC 9309)
# ---------------------------------------------------------------------------
# Python's urllib.robotparser matches user-agents by substring ("Applebot" rules would apply to
# "Applebot-Extended"), uses the first matching rule instead of the most specific one and ignores
# * and $ wildcards, so we use our own small evaluator.
def parse_robots(text):
    """Return a list of groups: (list_of_user_agents, list_of_(allow, path_pattern))."""
    groups, agents, rules, in_rules = [], [], [], False
    for line in text.lstrip("\ufeff").splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key, val = key.strip().lower(), val.strip()
        if key in ("user-agent", "useragent"):
            if in_rules:
                groups.append((agents, rules))
                agents, rules, in_rules = [], [], False
            agents.append(val.split("/")[0].strip().lower())
        elif key in ("allow", "disallow") and agents:
            in_rules = True
            if val:  # an empty "Disallow:" means "allow everything"
                rules.append((key == "allow", val))
    if agents:
        groups.append((agents, rules))
    return groups


def _rule_matches(pattern, path):
    regex = re.escape(pattern).replace(r"\*", ".*")
    if regex.endswith(r"\$"):
        regex = regex[:-2] + "$"
    return re.match(regex, path) is not None


def robots_allows(groups, agent, url):
    """True if `agent` may crawl `url` according to the parsed robots.txt groups."""
    agent = agent.lower()
    rules = [r for ags, rs in groups if agent in ags for r in rs]
    if not any(agent in ags for ags, _ in groups):  # no group of its own -> use "*"
        rules = [r for ags, rs in groups if "*" in ags for r in rs]
    path = path_of(url)
    best = None  # (pattern length, allow) – longest match wins, Allow wins a tie
    for allow, pattern in rules:
        if _rule_matches(pattern, path):
            cand = (len(pattern), allow)
            if best is None or cand > best:
                best = cand
    return True if best is None else best[1]


# ---------------------------------------------------------------------------
# Network workers (run in threads)
# ---------------------------------------------------------------------------
def fetch_page(url):
    """Download the main page. -> (response, html_bytes, seconds, ssl_verified)

    * Some college / government sites have an incomplete HTTPS certificate chain that browsers
      tolerate but Python rejects – we retry without verification and report it as a warning.
    * Some sites block browser-looking scripts (HTTP 403) – we retry once with an honest bot name.
      `resp.request.headers` tells the rest of the audit which identity worked.
    """
    def _get(headers, verify):
        start = time.time()
        r = requests.get(url, headers=headers, timeout=(CONNECT_TIMEOUT, TIMEOUT),
                         allow_redirects=True, stream=True, verify=verify)
        ctype = r.headers.get("Content-Type", "")
        if ctype and "html" not in ctype.lower() and "xml" not in ctype.lower():
            r.close()  # don't download images / PDFs / videos
            return r, b"", time.time() - start
        body = r.raw.read(8_000_000, decode_content=True)  # 8 MB is plenty for any HTML page
        r.close()
        return r, body, time.time() - start

    verified = True
    try:
        resp, body, secs = _get(HEADERS, True)
    except requests.exceptions.SSLError:
        verified = False
        resp, body, secs = _get(HEADERS, False)

    if resp.status_code in (401, 403, 406, 429, 503) or is_bot_challenge(
            resp.status_code, body, resp.headers):
        try:
            r2 = _get(BOT_HEADERS, verified)
            if r2[0].status_code < 400 and not is_bot_challenge(r2[0].status_code, r2[1],
                                                                r2[0].headers):
                resp, body, secs = r2
        except NET_ERRORS:
            pass
    return resp, body, secs, verified


BLOCK_CODES = (401, 403, 429, 999)  # "go away, robot" answers – not the same as a missing page


def crawl_page(url, verify, headers=None):
    """Download one internal page and pull out the basics used by the site-wide checks.

    Extra fields: `final_url` (after redirects) and `blocked` (True when a firewall or
    login wall answered instead of the page – that is not counted as a broken page)."""
    info = dict(url=url, path=path_of(url), status=None, time=None, size_kb=0, title="",
                meta_desc="", h1=0, words=0, canonical="", noindex=False, imgs=0,
                imgs_no_alt=0, error="", final_url=url, blocked=False)
    start = time.time()
    try:
        r = requests.get(url, headers=headers or HEADERS, timeout=PAGE_TIMEOUT,
                         allow_redirects=True, stream=True, verify=verify)
        info["status"] = r.status_code
        info["final_url"] = tidy_url(r.url)
        ctype = r.headers.get("Content-Type", "")
        if ctype and "html" not in ctype.lower():
            r.close()
            info["error"] = "Not an HTML page (%s)" % ctype.split(";")[0]
            info["time"] = time.time() - start
            return info
        body = r.raw.read(3_000_000, decode_content=True)
        r.close()
        info["time"] = time.time() - start
        info["size_kb"] = len(body) / 1024
        if is_bot_challenge(r.status_code, body, r.headers):
            info["blocked"] = True
            info["error"] = "Bot protection page (HTTP %d)" % r.status_code
            return info
        if r.status_code in BLOCK_CODES:
            info["blocked"] = True
            info["error"] = "Access refused (HTTP %d)" % r.status_code
            return info
        soup = make_soup(body, r)
        t = soup.find("title")
        info["title"] = clean_text(t.get_text()) if t else ""
        info["meta_desc"] = clean_text(meta_content(soup, name=re.compile("^description$", re.I)))
        info["h1"] = len(soup.find_all("h1"))
        can = next((l for l in soup.find_all("link") if "canonical" in rel_values(l)), None)
        info["canonical"] = (can.get("href") or "").strip() if can else ""
        robots = (meta_content(soup, name=re.compile("^(robots|googlebot)$", re.I)) + " "
                  + r.headers.get("X-Robots-Tag", "")).lower()
        info["noindex"] = "noindex" in robots
        imgs = soup.find_all("img")
        info["imgs"] = len(imgs)
        info["imgs_no_alt"] = sum(1 for i in imgs if not (i.get("alt") or "").strip())
        info["words"] = len(re.findall(r"\w+", visible_text_of(soup)))
    except requests.exceptions.Timeout:
        info["error"] = "Timed out"
        info["time"] = time.time() - start
    except NET_ERRORS as exc:
        info["error"] = "Timed out" if "timed out" in str(exc).lower() else type(exc).__name__
        info["time"] = time.time() - start
    except Exception as exc:  # noqa: BLE001 – one odd page must never stop the crawl
        info["error"] = "Could not read the page (%s)" % type(exc).__name__
        info["time"] = time.time() - start
    return info


def probe_bot(bot, url, verify):
    """Request the page pretending to be `bot` and see whether the server lets it in."""
    out = dict(status=None, time=None, reachable=False, note="")
    start = time.time()
    try:
        r = requests.get(url, headers={"User-Agent": bot["ua"], "Accept": "text/html,*/*"},
                         timeout=PAGE_TIMEOUT, allow_redirects=True, stream=True, verify=verify)
        chunk = r.raw.read(200_000, decode_content=True)
        r.close()
        out["status"] = r.status_code
        out["time"] = time.time() - start
        challenge = is_bot_challenge(r.status_code, chunk, r.headers)
        out["reachable"] = r.status_code < 400 and not challenge
        if challenge:
            out["note"] = "Firewall challenge page"
        elif r.status_code >= 400:
            out["note"] = "Refused (HTTP %d)" % r.status_code
            if bot["token"] in ("Googlebot", "Bingbot"):
                # Big sites check that "Googlebot" really comes from Google's IP addresses,
                # so a fake one is refused while the real one is let in.
                out["note"] += " – the site may verify the real bot by IP address"
    except requests.exceptions.Timeout:
        out["note"] = "No answer (timed out)"
    except NET_ERRORS as exc:
        out["note"] = ("No answer (timed out)" if "timed out" in str(exc).lower()
                       else "Connection failed (%s)" % type(exc).__name__)
    except Exception as exc:  # noqa: BLE001
        out["note"] = "Test failed (%s)" % type(exc).__name__
    return out


def check_link(url, verify=True):
    """-> (url, status or None, note). note is set when the link could not be judged
    (timeout, old TLS, bot protection) – those are not counted as broken."""
    try:
        r = requests.head(url, headers=HEADERS, timeout=PAGE_TIMEOUT, allow_redirects=True,
                          verify=verify)
        if r.status_code >= 400:  # some servers refuse HEAD – retry with GET
            r = requests.get(url, headers=HEADERS, timeout=PAGE_TIMEOUT, allow_redirects=True,
                             stream=True, verify=verify)
            r.close()
        if r.status_code >= 500 and ((r.headers.get("cf-mitigated") or "").lower() == "challenge"
                                     or r.headers.get("x-amzn-waf-action")):
            return url, None, "Bot protection (HTTP %d)" % r.status_code
        return url, r.status_code, ""
    except requests.exceptions.SSLError as exc:
        if verify:  # a certificate problem is not a "broken link"
            return check_link(url, verify=False)
        return url, None, "Secure connection failed (%s)" % (
            "old TLS on this computer" if "PROTOCOL_VERSION" in str(exc).upper() else "TLS error")
    except requests.exceptions.Timeout:
        return url, None, "No answer within %d seconds" % PAGE_TIMEOUT[1]
    except requests.exceptions.ConnectionError as exc:
        msg = str(exc)
        if any(m in msg for m in ("NameResolution", "Name or service not known", "nodename nor",
                                  "getaddrinfo failed", "Failed to resolve")):
            return url, None, ""  # the domain does not exist any more -> broken
        if "Connection refused" in msg or "Errno 61" in msg or "Errno 111" in msg:
            return url, None, ""  # nothing is listening -> broken
        return url, None, "Connection dropped"
    except NET_ERRORS:
        return url, None, ""
    except Exception as exc:  # noqa: BLE001
        return url, None, "Check failed (%s)" % type(exc).__name__


def link_status(url, verify=True):
    """Backwards-compatible wrapper: -> (url, status or None)."""
    u, s, _ = check_link(url, verify)
    return u, s


def is_broken(status):
    return status is None or status in (404, 410) or status >= 500


# ---------------------------------------------------------------------------
# Screenshots with headless Chrome / Edge (optional – skipped if no browser is installed)
# ---------------------------------------------------------------------------
BROWSER_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_browser():
    for p in BROWSER_PATHS:
        if os.path.exists(p):
            return p
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                 "microsoft-edge", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _run_browser(args, timeout):
    """Run the headless browser and make sure it (and its helper processes) end in time.
    -> True if it finished, False if it had to be stopped."""
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kw["start_new_session"] = True  # own process group, so we can stop all of it
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
    try:
        proc.wait(timeout=timeout)
        return True
    except subprocess.TimeoutExpired:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            else:
                os.killpg(proc.pid, signal.SIGKILL)
        except (OSError, subprocess.SubprocessError):
            proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return False


def take_screenshot(url, mobile=False):
    """-> (base64 JPEG or None, error message or None)

    Runs Chrome / Edge in headless mode with --screenshot. --virtual-time-budget lets the page
    run its scripts for about 5 seconds of page time before the picture is taken."""
    browser = find_browser()
    if not browser:
        return None, ("No Chrome or Edge browser was found on this computer, so the screenshots "
                      "were skipped.")
    # Desktop Chrome will not lay a page out narrower than 500 px (a smaller window is cropped,
    # not re-flowed), so the phone view is 500 x 1080: still a phone layout, never cut off.
    width, height = (500, 1080) if mobile else (1366, 860)
    tmp = tempfile.mkdtemp(prefix="seo-shot-")
    out = os.path.join(tmp, "shot.png")
    args = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
            "--no-default-browser-check", "--disable-extensions", "--mute-audio",
            "--disable-background-networking", "--disable-sync", "--disable-notifications",
            "--ignore-certificate-errors", "--user-data-dir=" + os.path.join(tmp, "profile"),
            # Chrome would otherwise try https:// first and refuse http-only sites
            "--disable-features=HttpsUpgrades,HttpsFirstBalancedModeAutoEnable",
            "--window-size=%d,%d" % (width, height), "--virtual-time-budget=5000",
            "--screenshot=" + out,
            # a normal browser name: some firewalls refuse "HeadlessChrome"
            "--user-agent=" + (MOBILE_UA if mobile else HEADERS["User-Agent"]),
            url]
    try:
        finished = _run_browser(args, SHOT_TIMEOUT)
        if not os.path.exists(out) or os.path.getsize(out) == 0:
            return None, ("The page took too long to draw in the browser." if not finished
                          else "The browser could not capture this page.")
        from PIL import Image  # Pillow (listed in requirements.txt)

        img = Image.open(out).convert("RGB")
        target = 320 if mobile else 1000
        resample = getattr(Image, "Resampling", Image).LANCZOS
        img = img.resize((target, max(1, int(img.height * target / img.width))), resample)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80, optimize=True)
        return base64.b64encode(buf.getvalue()).decode("ascii"), None
    except ImportError:
        return None, "Screenshots need the Pillow package (pip install pillow)."
    except Exception as exc:  # noqa: BLE001 – screenshots must never break the audit
        return None, "Screenshot failed (%s)." % type(exc).__name__
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# The auditor
# ---------------------------------------------------------------------------
STAGES = [
    ("connect", "Connecting to the website"),
    ("robots", "Reading robots.txt and llms.txt"),
    ("sitemap", "Reading the sitemap"),
    ("page", "Analysing the main page"),
    ("crawl", "Crawling linked pages"),
    ("bots", "Testing search and AI bots"),
    ("links", "Checking outgoing links"),
    ("shots", "Capturing desktop and mobile views"),
    ("score", "Scoring and writing the report"),
]


class Auditor:
    def __init__(self, url, max_pages=12, check_links=True, screenshots=True, min_seconds=10,
                 progress=None):
        self.scheme_given = has_scheme(url)
        self.url = normalize_url(url)
        self.max_pages = max(1, int(max_pages))
        self.check_links = check_links
        self.screenshots = screenshots
        self.min_seconds = min_seconds
        self.progress = progress
        self.t0 = time.time()
        self.d = {}  # everything we learn goes in here
        self.hdrs = HEADERS  # switched to BOT_HEADERS if the site only lets honest bots in
        self.robots_groups = []
        self.bg = None  # background thread pool (robots, llms, sitemap, favicon, link checks)
        self.pre = {}  # prefetched files: name -> Future
        self.link_futs = []
        self.link_t0 = None

    # ---- progress reporting ------------------------------------------------
    def emit(self, kind, **kw):
        if self.progress:
            try:
                self.progress(dict(kind=kind, t=time.time() - self.t0, **kw))
            except Exception:  # noqa: BLE001 – a UI problem must never stop the audit
                pass

    def log(self, text, level="info"):
        self.emit("log", text=text, level=level)

    def stage(self, key):
        self.emit("stage", key=key)

    def _safe(self, label, fn, fallback=None):
        """Run one stage. If it crashes, log it, fill in safe defaults and carry on, so one
        unexpected page never kills the whole audit."""
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            self.log("%s could not be completed (%s), so it was skipped"
                     % (label, type(exc).__name__), "warn")
            if fallback:
                fallback()

    # ---- main entry point -----------------------------------------------------
    def run(self):
        if not self.url:
            raise AuditError("Please enter a website address, for example https://example.com")
        try:
            host = urlparse(self.url).hostname or ""
        except ValueError:
            host = ""
        labels = host.split(".")
        if host != "localhost" and (len(labels) < 2 or not all(labels) or any(
                c in host for c in " !\"#$%&'()*+,/;<=>?@[\\]^`{|}~")):
            raise AuditError("That does not look like a website address. Type it like "
                             "example.com or https://www.example.com/page")
        self.t0 = time.time()
        shot_pool, shot_futs = None, {}

        self.stage("connect")
        self._connect()  # AuditError / requests errors here stop the audit with a clear message

        self.bg = ThreadPoolExecutor(max_workers=10)
        self._prefetch()
        if self.screenshots:  # screenshots run in the background while we crawl
            shot_pool = ThreadPoolExecutor(max_workers=2)
            self.shot_t0 = time.time()
            shot_futs = {
                "desktop": shot_pool.submit(take_screenshot, self.d["final_url"], False),
                "mobile": shot_pool.submit(take_screenshot, self.d["final_url"], True),
            }
        try:
            self.stage("robots")
            self._safe("Reading robots.txt", self._robots_and_llms, self._robots_fallback)
            self.stage("sitemap")
            self._safe("Reading the sitemap", self._sitemap, self._sitemap_fallback)
            self.stage("page")
            self._page_defaults()
            self._safe("Analysing the page", self._analyse_main_page)
            self.stage("crawl")
            self._safe("Starting the link check", self._start_links)
            self._safe("The crawl", self._crawl,
                       lambda: self.d.setdefault("pages", [self._main_row()]))
            self.stage("bots")
            self._safe("The bot test", self._bots,
                       lambda: self.d.setdefault("bots", self._bot_rows()))
            self.stage("links")
            self._safe("The link check", self._links, self._links_fallback)
            self.stage("shots")
            self._safe("Screenshots", lambda: self._collect_screenshots(shot_futs),
                       lambda: self.d.setdefault("shots", dict(
                           desktop=None, mobile=None, error="Screenshots failed.")))
        finally:
            for pool in (shot_pool, self.bg):
                if pool:
                    pool.shutdown(wait=False)

        self.stage("score")
        result = self._score()
        self._finish_animation(len(result["seo"]) + len(result["ai"]))
        result["duration"] = time.time() - self.t0
        self.emit("done")
        return result

    # ---- 1. connect -------------------------------------------------------------
    def _connect(self):
        self.log("GET %s" % self.url)
        try:
            resp, body, secs, ssl_ok = fetch_page(self.url)
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as exc:
            # Typed without http(s)://? Some small sites still only work over plain http.
            if self.scheme_given or not self.url.lower().startswith("https://"):
                raise
            http_url = "http://" + self.url[8:]
            self.log("HTTPS did not work, trying %s" % http_url, "warn")
            try:
                resp, body, secs, ssl_ok = fetch_page(http_url)
            except NET_ERRORS:
                raise exc
            self.url = http_url
        code = resp.status_code
        chain = [(h.status_code, tidy_url(h.url)) for h in resp.history]
        for c, u in chain:
            self.log("%d redirect from %s" % (c, u), "warn")

        if code >= 400:
            reason = resp.reason or "Error"
            if code in (401, 403, 406, 429, 503) or is_bot_challenge(code, body, resp.headers):
                raise AuditError(
                    "The website refused our crawler (HTTP %d %s). Big sites such as Medium, "
                    "Reddit or NYTimes use bot protection that blocks automated tools. Please try "
                    "another address." % (code, reason))
            if code in (404, 410):
                raise AuditError("Page not found (HTTP %d). Check the address and try again." % code)
            raise AuditError("The website returned an error: HTTP %d %s." % (code, reason))
        if is_bot_challenge(code, body, resp.headers):
            raise AuditError(
                "The website answered with an anti-bot check (a CAPTCHA or JavaScript challenge) "
                "instead of the real page, so an automated tool cannot audit it. Sites such as "
                "Amazon do this. Please try another address.")
        ctype = resp.headers.get("Content-Type", "")
        if not body or not looks_like_html(body[:500].decode("latin-1"), ctype) or \
                "xml" in ctype.lower() and "html" not in ctype.lower() and b"<html" not in body[:3000].lower():
            raise AuditError(
                "That address did not return a web page (it returned %s). Enter the address of a "
                "normal page, not an image, PDF or file." % (ctype.split(";")[0] or "unknown content"))

        final_url = tidy_url(resp.url)
        p = urlparse(final_url)
        host = p.netloc.lower()
        self.resp, self.body = resp, body
        if resp.request is not None and \
                resp.request.headers.get("User-Agent") == BOT_HEADERS["User-Agent"]:
            self.hdrs = BOT_HEADERS  # only an honest bot name got in, so keep using it
            self.log("The site only answered our honest bot name, so the audit uses it", "warn")
        self.d.update(
            url=self.url, final_url=final_url, domain=p.netloc, base="%s://%s" % (p.scheme, p.netloc),
            host=host, bare_host=bare(host),
            status_code=code, reason=resp.reason, redirect_chain=chain + [(code, final_url)],
            load_time=secs, ttfb=resp.elapsed.total_seconds(), size_kb=len(body) / 1024,
            ssl_ok=ssl_ok, headers={k: v for k, v in resp.headers.items()},
        )
        self.log("HTTP %d %s · first byte %.2fs · %.0f KB"
                 % (code, resp.reason or "", self.d["ttfb"], self.d["size_kb"]), "ok")
        if not ssl_ok:
            self.log("HTTPS certificate could not be verified", "warn")
        self.emit("node", path=path_of(final_url), status=code, root=True)

    # ---- background downloads ---------------------------------------------------
    def _fetch(self, url):
        return self.bg.submit(get_text_file, url, self.d["ssl_ok"], self.hdrs)

    def _prefetch(self):
        """Ask for robots.txt, llms.txt, the usual sitemap addresses and the favicon at the same
        time, so the next stages only have to wait for the slowest one, not for all of them."""
        base = self.d["base"]
        for name, path in (("robots", "/robots.txt"), ("llms", "/llms.txt"),
                           ("sitemap", "/sitemap.xml"), ("sitemap_index", "/sitemap_index.xml"),
                           ("favicon", "/favicon.ico")):
            self.pre[name] = self._fetch(base + path)

    def _wait(self, fut, deadline):
        try:
            return fut.result(timeout=max(0.1, deadline - time.time()))
        except Exception:  # noqa: BLE001 – timeout or network error
            return None, "", ""

    # ---- 2. robots.txt + llms.txt ---------------------------------------------
    def _robots_fallback(self):
        self.d.setdefault("robots", dict(found=False, status=None, text="", groups=0, sitemaps=[]))
        self.d.setdefault("llms", dict(found=False, text=""))
        self.robots_groups = []

    def _robots_and_llms(self):
        deadline = time.time() + FILES_BUDGET
        self.log("GET /robots.txt")
        status, text, ctype = self._wait(self.pre["robots"], deadline)
        found = status == 200 and not looks_like_html(text) and "<html" not in text[:2000].lower()
        groups = parse_robots(text) if found else []
        sitemaps = []
        if found:
            for sm in re.findall(r"(?im)^\s*sitemap:\s*(\S+)", text):
                sm = urljoin(self.d["base"] + "/", sm.strip())
                if sm not in sitemaps:
                    sitemaps.append(sm)
        self.d["robots"] = dict(found=found, status=status, text=text[:6000] if found else "",
                                groups=len(groups), sitemaps=sitemaps)
        self.robots_groups = groups
        self.log("robots.txt: %s" % ("found, %d rule groups" % len(groups) if found
                                     else "not found (HTTP %s)" % status if status
                                     else "could not be fetched"),
                 "ok" if found else "warn")

        self.log("GET /llms.txt")
        status, text, ctype = self._wait(self.pre["llms"], deadline)
        has = status == 200 and not looks_like_html(text, ctype) and len(text.strip()) > 20
        self.d["llms"] = dict(found=has, text=text[:3000] if has else "")
        self.log("llms.txt: %s" % ("found" if has else "not found"), "ok" if has else "warn")

    # ---- 3. sitemap ---------------------------------------------------------------
    def _sitemap_fallback(self):
        self.d.setdefault("sitemap", dict(url=None, count=0, children=0, sample=[], lastmod=None,
                                          listed=0))

    def _rank_sitemaps(self, urls):
        """robots.txt may list dozens of sitemaps (BBC lists one per language). Prefer the main
        one on this host: /sitemap.xml, then an index, then the shortest address."""
        def rank(item):
            i, u = item
            p = urlparse(u)
            name = p.path.lower()
            return (bare(p.netloc) != self.d["bare_host"],
                    name not in ("/sitemap.xml", "/sitemap_index.xml", "/sitemap.xml.gz"),
                    "index" not in name, name.count("/"), i)
        return [u for _, u in sorted(enumerate(urls), key=rank)]

    def _sitemap(self):
        deadline = time.time() + SITEMAP_BUDGET
        listed = self.d["robots"]["sitemaps"]
        info = dict(url=None, count=0, children=0, sample=[], lastmod=None, listed=len(listed))
        base = self.d["base"]
        # the usual root addresses first (already downloading), then robots.txt entries
        futs = [(base + "/sitemap.xml", self.pre["sitemap"]),
                (base + "/sitemap_index.xml", self.pre["sitemap_index"])]
        for sm in self._rank_sitemaps(listed)[:3]:
            if sm in (base + "/sitemap.xml", base + "/sitemap_index.xml"):
                continue
            futs.append((sm, self._fetch(sm)))
        for sm, fut in futs:
            self.log("GET %s" % path_of(sm))
            status, text, _ = self._wait(fut, deadline)
            if status != 200 or ("<urlset" not in text and "<sitemapindex" not in text):
                continue
            info["url"] = sm
            if "<sitemapindex" in text:
                children = [htmllib.unescape(c) for c in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text)]
                info["children"] = len(children)
                self.log("Sitemap index with %d child sitemaps" % len(children), "ok")
                if children:
                    s2, t2, _ = self._wait(self._fetch(children[0]), max(deadline, time.time() + 2))
                    text = t2 if s2 == 200 else ""
            locs = [htmllib.unescape(u) for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text)]
            mods = sorted(m[:10] for m in re.findall(r"<lastmod>\s*([^<\s]+)\s*</lastmod>", text))
            info["count"] = len(locs)
            info["sample"] = locs[:200]
            info["lastmod"] = mods[-1] if mods else None
            self.log("Sitemap lists %d pages%s" % (len(locs), (" (child 1 of %d)" % info["children"])
                                                    if info["children"] else ""), "ok")
            break
        if not info["url"]:
            self.log("No sitemap found", "warn")
        self.d["sitemap"] = info

    # ---- 4. main page ---------------------------------------------------------
    def _analyse_main_page(self):
        d, resp, body = self.d, self.resp, self.body
        final_url = d["final_url"]
        soup = make_soup(body, resp)
        text_soup = make_soup(body, resp)
        base_tag = soup.find("base", href=True)
        try:  # <base href> changes what relative links point to
            link_base = urljoin(final_url, base_tag["href"].strip()) if base_tag else final_url
        except ValueError:
            link_base = final_url

        title_tag = (soup.head.find("title") if soup.head else None) or soup.find("title")
        d["title"] = clean_text(title_tag.get_text()) if title_tag else ""
        d["meta_desc"] = clean_text(meta_content(soup, name=re.compile("^description$", re.I)))
        self.log('Title: "%s"' % (d["title"][:70] or "(missing)"))
        d["robots_meta"] = " ".join([
            meta_content(soup, name=re.compile("^(robots|googlebot)$", re.I)),
            resp.headers.get("X-Robots-Tag", "")]).strip().lower()
        d["viewport"] = meta_content(soup, name=re.compile("^viewport$", re.I))
        links = soup.find_all("link")
        can = next((l for l in links if "canonical" in rel_values(l)), None)
        d["canonical"] = (can.get("href") or "").strip() if can else ""
        html_tag = soup.find("html")
        d["lang"] = (html_tag.get("lang") or html_tag.get("xml:lang") or "") if html_tag else ""
        fav = next((l for l in links if any("icon" in r for r in rel_values(l))), None)
        fav_href = (fav.get("href") or "").strip() if fav else ""
        if fav_href.lower().startswith(("data:", "javascript:")):
            fav_href = ""  # href="data:," is a placeholder, not an icon file we can link to
        d["favicon_url"] = urljoin(final_url, fav_href) if fav_href else ""
        if not d["favicon_url"] and "favicon" in self.pre:
            s, txt, t = self._wait(self.pre["favicon"], time.time() + 4)
            if s == 200 and "html" not in t.lower() and txt:
                d["favicon_url"] = d["base"] + "/favicon.ico"
        d["hreflang"] = [l.get("hreflang") for l in links
                         if "alternate" in rel_values(l) and l.get("hreflang")]

        d["og"] = {k: meta_content(soup, property=k) or meta_content(soup, name=k) for k in
                   ("og:title", "og:description", "og:image", "og:site_name", "og:type")}
        if d["og"]["og:image"]:
            d["og"]["og:image"] = urljoin(final_url, d["og"]["og:image"])
        tw_img = (meta_content(soup, name="twitter:image")
                  or meta_content(soup, property="twitter:image"))
        d["twitter_image"] = urljoin(final_url, tw_img) if tw_img else ""
        d["og_image_fallback"] = d["og"]["og:image"] or d["twitter_image"]
        d["twitter_card"] = (meta_content(soup, name="twitter:card")
                             or meta_content(soup, property="twitter:card"))
        d["author_meta"] = meta_content(soup, name=re.compile("^author$", re.I))
        d["article_time"] = (meta_content(soup, property="article:modified_time")
                             or meta_content(soup, property="article:published_time"))
        d["has_time_tag"] = bool(soup.find("time"))

        # Headings
        d["headings"] = [(int(h.name[1]), clean_text(h.get_text(" ", strip=True)))
                         for h in soup.find_all(re.compile("^h[1-6]$"))]
        self.log("%d headings (%d H1)" % (len(d["headings"]),
                                          sum(1 for l, _ in d["headings"] if l == 1)))

        # Images
        images = []
        for img in soup.find_all("img"):
            if str(img.get("width")) in ("0", "1") and str(img.get("height")) in ("0", "1"):
                continue  # 1x1 tracking pixel, not a real image
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
            if not src and (img.get("srcset") or "").strip():
                src = (img["srcset"].split(",")[0].split() or [""])[0]
            # alt="" is correct for purely decorative images that are marked as such
            decorative = img.has_attr("alt") and not (img.get("alt") or "").strip() and (
                (img.get("role") or "").lower() in ("presentation", "none")
                or (img.get("aria-hidden") or "").lower() == "true")
            try:
                src = urljoin(link_base, src) if src and not src.startswith("data:") else ""
            except ValueError:
                src = ""
            images.append(dict(
                src=src,
                alt=clean_text(img.get("alt") or ""),
                has_alt=bool((img.get("alt") or "").strip()) or decorative,
                has_dims=bool(img.get("width") and img.get("height")),
                lazy=(img.get("loading") or "").lower() == "lazy",
            ))
        d["images"] = images
        self.log("%d images, %d without alt text"
                 % (len(images), sum(1 for i in images if not i["has_alt"])))

        # Links and anchor text
        internal, external, anchors, pairs = [], [], [], []
        for a in soup.find_all("a", href=True):
            href = (a.get("href") or "").strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            try:
                absolute = tidy_url(urljoin(link_base, href).split("#")[0])
                lp = urlparse(absolute)
            except ValueError:
                continue
            if lp.scheme not in ("http", "https") or not lp.netloc:
                continue
            text = clean_text(a.get_text(" ", strip=True)) or clean_text(
                a.get("aria-label") or a.get("title") or "")
            if not text:
                img = a.find("img")
                text = clean_text(img.get("alt") or "") if img else ""
            anchors.append(text)
            pairs.append((absolute, text))
            (internal if bare(lp.netloc) == d["bare_host"] else external).append(absolute)
        self.link_order = list(dict.fromkeys(internal))  # order of appearance (navigation first)
        self.anchor_pairs = pairs
        d["internal"] = sorted(set(internal))
        d["external"] = sorted(set(external))
        d["anchors_total"] = len(anchors)
        d["anchors_generic"] = sum(1 for t in anchors if not t or t.lower().strip(" .>»→") in GENERIC_ANCHORS)
        self.log("%d internal links, %d external links" % (len(d["internal"]), len(d["external"])))

        # Text
        visible = visible_text_of(text_soup)
        d["word_count"] = len(re.findall(r"\w+", visible))
        d["first_words"] = " ".join(visible.split()[:150])
        d["text_ratio"] = len(visible.encode("utf-8")) / max(1, len(body))
        paras = [clean_text(p.get_text(" ", strip=True)) for p in soup.find_all("p")]
        d["paragraphs"] = [p for p in paras if len(p.split()) >= 5]
        # <li> items (some sites put them in a <div role="list"> instead of <ul>) or <dl>
        d["has_lists"] = bool(soup.find("li") or soup.find(attrs={"role": "list"})
                              or soup.find("dl"))
        d["has_table"] = bool(soup.find("table"))
        self.log("%d words of visible text" % d["word_count"])

        # Structured data
        types, keys, errors, raw_blocks = set(), set(), 0, []
        for s in soup.find_all("script", type=re.compile(r"ld\+json", re.I)):
            raw = (s.string or s.get_text() or "").strip()
            raw = re.sub(r"^\s*(<!\[CDATA\[|<!--)|(\]\]>|-->)\s*$", "", raw).strip()
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
                collect_schema(parsed, types, keys)
                raw_blocks.append(json.dumps(parsed, indent=2, ensure_ascii=False)[:4000])
            except (ValueError, TypeError, RecursionError):
                errors += 1
                raw_blocks.append(raw[:2000])
        for item in soup.find_all(attrs={"itemtype": True}):
            for it in str(item.get("itemtype") or "").split():
                it = it.rstrip("/").split("/")[-1]
                if it:
                    types.add(it)
        d["schema_types"] = sorted(types)
        d["schema_keys"] = sorted(keys)
        d["schema_errors"] = errors
        d["jsonld"] = raw_blocks[:6]
        self.log("Structured data: %s" % (", ".join(sorted(types)) or "none"),
                 "ok" if types else "warn")

        # Resources and performance hints
        head = soup.head or soup
        blocking = []
        for s in head.find_all("script", src=True):
            if s.has_attr("async") or s.has_attr("defer") or (s.get("type") or "") == "module":
                continue
            blocking.append(urljoin(final_url, s["src"]))
        css = [l for l in links if "stylesheet" in rel_values(l)]
        d["resources"] = dict(
            scripts=len(soup.find_all("script", src=True)),
            inline_scripts=len([s for s in soup.find_all("script") if not s.get("src")]),
            stylesheets=len(css), images=len(images), iframes=len(soup.find_all("iframe")),
            blocking=blocking[:30],
        )
        mixed = []
        if final_url.lower().startswith("https://"):
            for tag, attr in (("img", "src"), ("script", "src"), ("iframe", "src"),
                              ("source", "src"), ("video", "src"), ("audio", "src")):
                for t in soup.find_all(tag):
                    v = (t.get(attr) or "").strip()
                    if v.lower().startswith("http://"):
                        mixed.append(v)
            for l in css:
                v = (l.get("href") or "").strip()
                if v.lower().startswith("http://"):
                    mixed.append(v)
        d["mixed"] = mixed[:50]

    # ---- defaults (used if a stage fails half-way) -------------------------------
    def _page_defaults(self):
        for k, v in dict(title="", meta_desc="", robots_meta="", viewport="", canonical="", lang="",
                         favicon_url="", hreflang=[], og={k: "" for k in (
                             "og:title", "og:description", "og:image", "og:site_name", "og:type")},
                         twitter_card="", twitter_image="", og_image_fallback="", author_meta="", article_time="", has_time_tag=False,
                         headings=[], images=[], internal=[], external=[], anchors_total=0,
                         anchors_generic=0, word_count=0, first_words="", text_ratio=0.0,
                         paragraphs=[], has_lists=False, has_table=False, schema_types=[],
                         schema_keys=[], schema_errors=0, jsonld=[], mixed=[],
                         resources=dict(scripts=0, inline_scripts=0, stylesheets=0, images=0,
                                        iframes=0, blocking=[])).items():
            self.d.setdefault(k, v)
        self.link_order, self.anchor_pairs = [], []

    def _main_row(self):
        d = self.d
        return dict(url=d["final_url"], path=path_of(d["final_url"]), status=d["status_code"],
                    time=d["load_time"], size_kb=d["size_kb"], title=d["title"],
                    meta_desc=d["meta_desc"], h1=sum(1 for l, _ in d["headings"] if l == 1),
                    words=d["word_count"], canonical=d["canonical"],
                    noindex="noindex" in d["robots_meta"], imgs=len(d["images"]),
                    imgs_no_alt=sum(1 for i in d["images"] if not i["has_alt"]), error="",
                    final_url=d["final_url"], blocked=False)

    # ---- 5. crawl ---------------------------------------------------------------
    def _choose_pages(self):
        """Pick which linked pages to visit, the way a polite search-engine crawler would:

        1. only pages on this website (www and non-www count as the same site),
        2. skip files (PDF, images…), pages robots.txt forbids, and pages that are a waste of a
           small crawl budget (login, cart, search results, tag and calendar pages, ?sort= …),
        3. never visit the same page twice (http/https, www, trailing slash, index.html, #part),
        4. prefer main sections: well-known sections (About, Contact, Blog…) first, then short
           addresses, in the order the links appear on the page (top navigation comes first),
        5. at most 3 pages from the same section, so the sample covers the whole site.
        Sitemap pages are used to top up when the page has few links."""
        d = self.d
        seen = {url_key(d["final_url"]), url_key(self.url)}
        pool = list(self.link_order or d["internal"])
        if len(pool) < self.max_pages * 2:
            pool += [u for u in d["sitemap"]["sample"] if bare(urlparse(u).netloc) == d["bare_host"]]
        candidates, skipped_robots = [], 0
        for pos, u in enumerate(pool):
            try:
                p = urlparse(u)
            except ValueError:
                continue
            path = p.path or "/"
            key = url_key(u)
            if key in seen or p.scheme not in ("http", "https"):
                continue
            seen.add(key)
            if path.lower().endswith(SKIP_EXT) or JUNK_PATH_RE.search(path) \
                    or (p.query and JUNK_QUERY_RE.search(p.query)) or len(u) > 300:
                continue
            if self.robots_groups and not robots_allows(self.robots_groups, "seo-ai-auditor", u):
                skipped_robots += 1
                continue  # robots.txt says crawlers should stay out
            depth = len([x for x in path.split("/") if x])
            candidates.append(((0 if PRIORITY_PATH_RE.search(path) else 1, bool(p.query),
                                min(depth, 4), pos), u, (path.strip("/").split("/") or [""])[0]))
        candidates.sort(key=lambda c: c[0])
        d["crawl_skipped_robots"] = skipped_robots
        if skipped_robots:
            self.log("robots.txt asks crawlers like ours to stay away from %d linked page(s), "
                     "so they were not visited" % skipped_robots, "warn")
        want = self.max_pages - 1
        picked, per_section = [], Counter()
        for _, u, section in candidates:  # first pass: at most 3 pages per section
            if len(picked) >= want:
                break
            if per_section[section] < 3:
                picked.append(u)
                per_section[section] += 1
        for _, u, _ in candidates:  # second pass: fill up if the site has few sections
            if len(picked) >= want:
                break
            if u not in picked:
                picked.append(u)
        return picked

    def _crawl(self):
        d = self.d
        pages = [self._main_row()]
        d["pages"] = pages
        targets = self._choose_pages()
        self.emit("plan", paths=[path_of(u) for u in targets])
        self.log("Following %d internal links" % len(targets))
        if targets:
            pool = ThreadPoolExecutor(max_workers=6)
            futs = [pool.submit(crawl_page, u, d["ssl_ok"], self.hdrs) for u in targets]
            try:
                for f in as_completed(futs, timeout=CRAWL_BUDGET):
                    info = f.result()
                    pages.append(info)
                    ok = info["status"] and info["status"] < 400 and not info["error"]
                    self.emit("node", path=info["path"], status=info["status"])
                    self.log("%s %s%s" % (info["status"] or "ERR", info["path"][:60],
                                          (" · %.2fs" % info["time"]) if info["time"] else ""),
                             "ok" if ok else "warn")
            except FuturesTimeout:
                self.log("Crawl time limit reached, remaining pages skipped", "warn")
            finally:
                pool.shutdown(wait=False)
                for f in futs:
                    f.cancel()
        blocked = sum(1 for pg in pages if pg.get("blocked"))
        if blocked:
            self.log("%d page(s) answered with a firewall or login wall instead of content"
                     % blocked, "warn")

    # ---- 6. bots ----------------------------------------------------------------
    def _bot_rows(self):
        d = self.d
        rows = []
        for b in BOTS:
            allowed = robots_allows(self.robots_groups, b["token"], d["final_url"]) \
                if d.get("robots", {}).get("found") else True
            rows.append(dict(token=b["token"], label=b["label"], company=b["company"],
                             purpose=b["purpose"], robots_scored=b["robots_scored"],
                             answer_bot=b["answer_bot"], robots_allowed=allowed,
                             live_tested=bool(b["ua"]), live_status=None, live_time=None,
                             live_reachable=None, live_note="token only" if not b["ua"] else ""))
        return rows

    def _bots(self):
        d = self.d
        rows = self._bot_rows()
        d["bots"] = rows
        for r in rows:
            self.log("robots.txt %s %s" % ("allows" if r["robots_allowed"] else "BLOCKS", r["token"]),
                     "ok" if r["robots_allowed"] else "warn")
        # All live tests at the same time, with one overall time limit
        pool = ThreadPoolExecutor(max_workers=len(BOTS))
        futs = {pool.submit(probe_bot, b, d["final_url"], d["ssl_ok"]): i
                for i, b in enumerate(BOTS) if b["ua"]}
        pending = set(futs.values())
        try:
            for f in as_completed(futs, timeout=BOT_BUDGET):
                i = futs[f]
                r = f.result()
                pending.discard(i)
                rows[i].update(live_status=r["status"], live_time=r["time"],
                               live_reachable=r["reachable"], live_note=r["note"])
                self.emit("bot", token=rows[i]["token"], ok=r["reachable"])
                self.log("Knocked as %s → %s" % (rows[i]["token"],
                                                  r["status"] if r["status"] else r["note"]),
                         "ok" if r["reachable"] else "warn")
        except FuturesTimeout:
            for i in sorted(pending):
                rows[i].update(live_reachable=False,
                               live_note="No answer within %d seconds" % BOT_BUDGET)
                self.emit("bot", token=rows[i]["token"], ok=False)
                self.log("Knocked as %s → no answer" % rows[i]["token"], "warn")
        finally:
            pool.shutdown(wait=False)

    # ---- 7. outgoing links ----------------------------------------------------
    def _start_links(self):
        """Outgoing links point to other websites, so checking them can start in the background
        while we crawl this site (it does not add load to the audited server)."""
        d = self.d
        if not (self.check_links and d["external"]):
            return
        by_host, sample = set(), []  # one link per external website, up to 15 websites
        for u in d["external"]:
            h = bare(urlparse(u).netloc)
            if h not in by_host:
                by_host.add(h)
                sample.append(u)
            if len(sample) >= 15:
                break
        self.link_t0 = time.time()
        self.link_futs = [self.bg.submit(check_link, u, d["ssl_ok"]) for u in sample]

    def _links_fallback(self):
        self.d.setdefault("link_results", [])
        self.d.setdefault("link_unverified", [])

    def _links(self):
        d = self.d
        results, unverified = [], []
        if self.link_futs:
            deadline = max(self.link_t0 + LINK_BUDGET, time.time() + 1)
            try:
                for f in as_completed(self.link_futs, timeout=max(0.1, deadline - time.time())):
                    u, s, note = f.result()
                    if note:
                        unverified.append((u, note))
                        self.log("Could not check %s (%s)" % (u[:60], note))
                    else:
                        results.append((u, s))
                        self.log("%s %s" % (s or "ERR", u[:70]), "warn" if is_broken(s) else "ok")
            except FuturesTimeout:
                self.log("Link check time limit reached, slow links skipped", "warn")
        elif not self.check_links:
            self.log("Outgoing link check switched off")
        else:
            self.log("No outgoing links to check")
        d["link_results"] = results
        d["link_unverified"] = unverified  # could not be judged (timeout, old TLS, firewall)

    # ---- 8. screenshots ---------------------------------------------------------
    def _collect_screenshots(self, futs):
        shots = dict(desktop=None, mobile=None, error=None)
        if not futs:
            shots["error"] = "Screenshots switched off."
            self.log("Screenshots switched off")
        deadline = getattr(self, "shot_t0", time.time()) + SHOT_TIMEOUT + 3
        for kind, f in futs.items():
            try:
                img, err = f.result(timeout=max(0.5, deadline - time.time()))
            except Exception:  # noqa: BLE001
                img, err = None, "Screenshot timed out."
            shots[kind] = img
            if err and not shots["error"]:
                shots["error"] = err
            self.log("%s view: %s" % (kind.capitalize(), "captured" if img else (err or "failed")),
                     "ok" if img else "warn")
        self.d["shots"] = shots

    # ---- 9. scoring -----------------------------------------------------------
    def _finish_animation(self, n_checks):
        """Keep the crawl animation on screen for at least `min_seconds` so it can be followed."""
        steps = ["Weighing %d checks" % n_checks, "Ranking fixes by impact",
                 "Writing plain-language explanations", "Preparing the downloadable report"]
        i = 0
        while time.time() - self.t0 < self.min_seconds:
            if i < len(steps):
                self.log(steps[i])
                i += 1
            self.emit("tick")
            time.sleep(0.35)

    def _score(self):
        d = self.d
        checks = []

        def add(cid, status, value):
            info = CHECKS[cid]
            checks.append(dict(id=cid, status=status, value=value, name=info["name"],
                               plain=info["plain"], cat=info["cat"], weight=info["weight"],
                               why=info["why"], fix=info["fix"], tech=info["tech"]))

        final_url = d["final_url"]
        is_https = final_url.lower().startswith("https://")
        headers = {k.lower(): v for k, v in d["headers"].items()}
        h1s = [t for l, t in d["headings"] if l == 1]
        h2s = [t for l, t in d["headings"] if l == 2]
        noindex = "noindex" in d["robots_meta"]
        images = d["images"]

        # ---------- Content ----------
        tl = len(d["title"])
        add("title", "pass" if 30 <= tl <= 60 else ("warn" if tl else "fail"),
            '"%s" (%d characters)' % (d["title"], tl) if tl else "No title found")
        dl = len(d["meta_desc"])
        add("meta_desc", "pass" if 70 <= dl <= 160 else ("warn" if dl else "fail"),
            "%d characters" % dl if dl else "No description found")
        add("h1", "pass" if len(h1s) == 1 else ("warn" if h1s else "fail"),
            ('%d found: "%s"' % (len(h1s), h1s[0][:70])) if h1s else "No H1 heading found")
        add("h2", "pass" if h2s else "fail", "%d section headings" % len(h2s))
        jumps, prev = 0, None
        for lvl, _ in d["headings"]:
            if prev is not None and lvl - prev > 1:
                jumps += 1
            prev = lvl
        add("heading_order", "pass" if jumps == 0 else ("warn" if jumps <= 2 else "fail"),
            "In order" if jumps == 0 else "%d skipped level(s)" % jumps)
        wc = d["word_count"]
        add("word_count", "pass" if wc >= 600 else ("warn" if wc >= 300 else "fail"),
            "%d words" % wc)
        # \w+ also matches Hindi, Arabic, Chinese… words, not only English letters
        title_words = [w for w in re.findall(r"\w+", d["title"].lower())
                       if w not in STOP_WORDS and (len(w) > 2 or not w.isascii())
                       and not w.isdigit()]
        haystack = (" ".join(h1s) + " " + d["first_words"]).lower()
        if title_words:
            hit = sum(1 for w in set(title_words) if w in haystack) / len(set(title_words))
            add("title_match", "pass" if hit >= 0.5 else ("warn" if hit >= 0.25 else "fail"),
                "%d%% of title words appear in the heading or opening text" % round(hit * 100))
        else:
            add("title_match", "fail" if not d["title"] else "warn", "Title has no topic words")
        if images:
            cov = round(sum(1 for i in images if i["has_alt"]) / len(images) * 100)
            add("alt_text", "pass" if cov >= 90 else ("warn" if cov >= 50 else "fail"),
                "%d%% of %d images described" % (cov, len(images)))
        else:
            add("alt_text", "pass", "No images on this page")

        # ---------- Technical ----------
        add("https", ("pass" if d["ssl_ok"] else "warn") if is_https else "fail",
            ("Secure" if d["ssl_ok"] else "HTTPS, but the certificate could not be verified")
            if is_https else "Not secure (http)")
        vp = d["viewport"]
        add("viewport", ("pass" if "device-width" in vp.lower() else "warn") if vp else "fail",
            vp or "Missing")
        if d["canonical"]:
            try:
                can_abs = tidy_url(urljoin(final_url, d["canonical"]))
            except ValueError:
                can_abs = d["canonical"]
            # same page = same scheme, host (incl. www), path (ignoring a trailing slash) and query
            same = can_abs.split("#")[0].rstrip("/") == final_url.split("#")[0].rstrip("/")
            add("canonical", "pass" if same else "warn",
                "Points to this page" if same else "Points to a different address: %s" % can_abs)
        else:
            add("canonical", "warn", "Not set")
        add("lang", "pass" if d["lang"] else "warn", d["lang"] or "Not declared")
        add("indexable", "fail" if noindex else "pass",
            "Hidden from Google (noindex)" if noindex else "Visible to Google")
        r = d["robots"]
        add("robots", "pass" if r["found"] else "warn",
            "Found (%d rule groups)" % r["groups"] if r["found"]
            else ("Not found (HTTP %s)" % r["status"] if r["status"] else "Could not be fetched"))
        sm = d["sitemap"]
        if sm["url"] and sm["children"]:
            sm_text = "Found: an index of %d sitemaps (the first lists %d pages)" % (
                sm["children"], sm["count"])
        elif sm["url"]:
            sm_text = "Found, lists %d pages" % sm["count"]
        else:
            sm_text = "Not found"
        if sm["url"] and sm["lastmod"]:
            sm_text += ", last updated %s" % sm["lastmod"]
        add("sitemap", "pass" if sm["url"] else "warn", sm_text)
        hops = len(d["redirect_chain"]) - 1
        add("redirects", "pass" if hops <= 1 else ("warn" if hops == 2 else "fail"),
            "No redirects" if hops == 0 else "%d redirect hop(s) before the page" % hops)
        p = urlparse(final_url)
        problems = []
        if len(final_url) >= 100:
            problems.append("long")
        if p.path != p.path.lower():
            problems.append("uppercase letters")
        if "_" in p.path:
            problems.append("underscores")
        if p.query.count("&") + (1 if p.query else 0) > 2:
            problems.append("many parameters")
        add("url", "pass" if not problems else "warn",
            "Clean" if not problems else "Has " + ", ".join(problems))
        add("favicon", "pass" if d["favicon_url"] else "warn",
            "Found" if d["favicon_url"] else "Missing")

        # ---------- Speed ----------
        ttfb = d["ttfb"]
        add("ttfb", "pass" if ttfb < 0.8 else ("warn" if ttfb < 1.8 else "fail"),
            "%.2f seconds" % ttfb)
        kb = d["size_kb"]
        add("html_size", "pass" if kb < 200 else ("warn" if kb < 500 else "fail"), "%.0f KB" % kb)
        enc = headers.get("content-encoding", "").lower()
        if any(e in enc for e in ("gzip", "br", "zstd", "deflate")):
            add("compression", "pass", enc)
        elif kb < 1.4:  # Lighthouse also ignores files this small
            add("compression", "pass", "Not compressed, but the page is tiny (%.1f KB)" % kb)
        else:
            add("compression", "fail", "Not compressed")
        nb = len(d["resources"]["blocking"])
        add("render_blocking", "pass" if nb <= 2 else ("warn" if nb <= 6 else "fail"),
            "%d blocking script(s) in the page head" % nb)
        if images:
            dims = sum(1 for i in images if i["has_dims"]) / len(images)
            add("img_dims", "pass" if dims >= 0.8 else ("warn" if dims >= 0.4 else "fail"),
                "%d%% of images have a set size" % round(dims * 100))
        else:
            add("img_dims", "pass", "No images on this page")
        if len(images) > 5:
            lazy = sum(1 for i in images if i["lazy"])
            add("lazy", "pass" if lazy else "warn", "%d of %d images lazy-load" % (lazy, len(images)))
        else:
            add("lazy", "pass", "Few images, not needed")
        cache = [h for h in ("cache-control", "etag", "last-modified") if h in headers]
        add("caching", "pass" if cache else "warn", ", ".join(cache) if cache else "No caching headers")

        # ---------- Security ----------
        add("hsts", ("pass" if "strict-transport-security" in headers else "warn") if is_https
            else "fail", "On" if "strict-transport-security" in headers else "Off")
        nm = len(d["mixed"])
        add("mixed", "pass" if nm == 0 else ("warn" if nm <= 3 else "fail"),
            "None" if nm == 0 else "%d insecure file(s)" % nm)
        sec = []
        if "x-content-type-options" in headers:
            sec.append("X-Content-Type-Options")
        if "x-frame-options" in headers or "frame-ancestors" in headers.get("content-security-policy", ""):
            sec.append("Frame protection")
        if "referrer-policy" in headers:
            sec.append("Referrer-Policy")
        add("sec_headers", "pass" if len(sec) == 3 else ("warn" if sec else "fail"),
            "%d of 3: %s" % (len(sec), ", ".join(sec)) if sec else "None of the 3")

        # ---------- Social ----------
        ogc = sum(1 for k in ("og:title", "og:description", "og:image") if d["og"][k])
        add("og", "pass" if ogc == 3 else ("warn" if ogc else "fail"), "%d of 3 tags" % ogc)
        add("twitter", "pass" if d["twitter_card"] else "warn", d["twitter_card"] or "Missing")
        st = d["schema_types"]
        add("schema", "pass" if st and not d["schema_errors"] else ("warn" if st else "fail"),
            (", ".join(st) + (" (%d invalid block)" % d["schema_errors"] if d["schema_errors"] else ""))
            if st else "None found")

        # ---------- Links ----------
        ni = len(d["internal"])
        add("internal_links", "pass" if ni >= 5 else ("warn" if ni else "fail"),
            "%d links to other pages on this site" % ni)
        if d["anchors_total"]:
            g = d["anchors_generic"] / d["anchors_total"]
            add("anchor_text", "pass" if g <= 0.10 else ("warn" if g <= 0.25 else "fail"),
                "%d of %d links say things like 'click here' or nothing at all"
                % (d["anchors_generic"], d["anchors_total"]))
        else:
            add("anchor_text", "pass", "No links on this page")
        # A firewall / login wall (401, 403, 429, challenge page) is not a broken page
        crawl_broken = [pg for pg in d["pages"][1:] if is_broken(pg["status"])
                        and not pg.get("blocked") and not pg["error"].startswith("Not an HTML")]
        ext_broken = [(u, s) for u, s in d["link_results"] if is_broken(s)]
        checked = len([pg for pg in d["pages"][1:] if not pg.get("blocked")]) + len(d["link_results"])
        nbk = len(crawl_broken) + len(ext_broken)
        n_unv = len(d.get("link_unverified") or [])
        add("broken_links", "pass" if nbk == 0 else ("warn" if nbk <= 2 else "fail"),
            ("%d broken out of %d checked" % (nbk, checked) if checked else "No links checked")
            + (" (%d more could not be checked: slow, firewalled or old TLS)" % n_unv
               if n_unv else ""))
        add("external_links", "info", "%d links to other websites" % len(d["external"]))

        # ---------- Whole site ----------
        # Pages that redirected to a page we already have count once (no false "duplicates")
        pages, keys = [], set()
        for pg in d["pages"]:
            if not (pg["status"] and pg["status"] < 400 and not pg["error"]):
                continue
            k = url_key(pg.get("final_url") or pg["url"])
            if k not in keys:
                keys.add(k)
                pages.append(pg)
        n = len(pages)
        errors = crawl_broken
        n_blocked = sum(1 for pg in d["pages"][1:] if pg.get("blocked"))
        add("crawl_errors", "pass" if not errors else ("warn" if len(errors) == 1 else "fail"),
            "%d of %d crawled pages failed" % (len(errors), len(d["pages"]))
            + (" (%d more refused our crawler, not counted)" % n_blocked if n_blocked else ""))
        if n >= 2:
            tcount = Counter(pg["title"] for pg in pages if pg["title"])
            dup_t = sum(c for c in tcount.values() if c > 1)
            add("dup_titles", "pass" if dup_t == 0 else ("warn" if dup_t / n <= 0.2 else "fail"),
                "%d of %d pages share a title" % (dup_t, n))
            mcount = Counter(pg["meta_desc"] for pg in pages if pg["meta_desc"])
            dup_m = sum(c for c in mcount.values() if c > 1)
            add("dup_meta", "pass" if dup_m == 0 else ("warn" if dup_m / n <= 0.2 else "fail"),
                "%d of %d pages share a description" % (dup_m, n))
            miss = sum(1 for pg in pages if not pg["title"] or not pg["meta_desc"])
            add("site_missing", "pass" if miss == 0 else ("warn" if miss / n <= 0.25 else "fail"),
                "%d of %d pages are missing one" % (miss, n))
            thin = sum(1 for pg in pages if pg["words"] < 250)
            add("thin_pages", "pass" if thin / n <= 0.2 else ("warn" if thin / n <= 0.5 else "fail"),
                "%d of %d pages have under 250 words" % (thin, n))
            avg = sum(pg["time"] or 0 for pg in pages) / n
            add("site_speed", "pass" if avg < 1.5 else ("warn" if avg < 3 else "fail"),
                "%.2f seconds on average across %d pages" % (avg, n))
        else:
            for cid in ("dup_titles", "dup_meta", "site_missing", "thin_pages", "site_speed"):
                add(cid, "info", "Only %d page could be crawled, so this was not scored" % n)

        # ---------- AI access ----------
        scored = [b for b in d["bots"] if b["robots_scored"]]
        allowed = [b for b in scored if b["robots_allowed"]]
        ratio = len(allowed) / len(scored)
        blocked_names = [b["label"] for b in scored if not b["robots_allowed"]]
        add("ai_robots", "pass" if ratio == 1 else ("warn" if ratio >= 0.5 else "fail"),
            "%d of %d allowed" % (len(allowed), len(scored))
            + (" (blocked: %s)" % ", ".join(blocked_names) if blocked_names else ""))
        answer = [b for b in d["bots"] if b["answer_bot"]]
        reach = [b for b in answer if b["live_reachable"]]
        if answer and any(b["live_reachable"] is not None for b in answer):
            rr = len(reach) / len(answer)
            turned_away = [b["label"] for b in answer if not b["live_reachable"]]
            add("ai_firewall", "pass" if rr == 1 else ("warn" if rr >= 0.5 else "fail"),
                "%d of %d AI bots got the page" % (len(reach), len(answer))
                + (" (turned away: %s)" % ", ".join(turned_away) if turned_away else ""))
        else:
            add("ai_firewall", "info", "The live bot test did not run, so this was not scored")
        add("llms", "pass" if d["llms"]["found"] else "warn",
            "Found" if d["llms"]["found"] else "Not found")
        add("no_js", "pass" if wc >= 300 else ("warn" if wc >= 100 else "fail"),
            "%d words readable without JavaScript" % wc)

        # ---------- AI understanding ----------
        st_set = set(st)
        qa = st_set & {"FAQPage", "QAPage", "HowTo"}
        add("faq_schema", "pass" if qa else "fail", ", ".join(sorted(qa)) or "None found")
        ent = st_set & {"Organization", "LocalBusiness", "Person", "WebSite", "Corporation",
                        "EducationalOrganization", "CollegeOrUniversity", "Store", "Restaurant",
                        "NewsMediaOrganization", "GovernmentOrganization", "School", "NGO",
                        "MedicalOrganization", "Hospital", "OnlineStore", "OnlineBusiness",
                        "ProfilePage", "Brand", "Hotel", "SportsOrganization", "LibrarySystem",
                        "Library", "ResearchOrganization", "Airline", "Dentist", "Physician"}
        add("entity_schema", "pass" if ent else "warn", ", ".join(sorted(ent)) or "None found")
        qh = [t for l, t in d["headings"] if l in (2, 3) and (t.endswith("?") or QUESTION_RE.match(t))]
        add("q_headings", "pass" if len(qh) >= 2 else ("warn" if qh else "fail"),
            "%d question headings" % len(qh))
        paras = d["paragraphs"]
        if paras:
            ar = sum(1 for x in paras if 15 <= len(x.split()) <= 90) / len(paras)
            add("answer_paras", "pass" if ar >= 0.6 else ("warn" if ar >= 0.3 else "fail"),
                "%d%% of %d paragraphs are a good length" % (round(ar * 100), len(paras)))
        else:
            add("answer_paras", "fail", "No paragraphs found")
        add("lists_tables", "pass" if d["has_lists"] or d["has_table"] else "warn",
            "Lists: %s, tables: %s" % ("yes" if d["has_lists"] else "no",
                                       "yes" if d["has_table"] else "no"))
        add("summary", "pass" if d["meta_desc"] else "fail",
            "Present" if d["meta_desc"] else "Missing")
        tr = d["text_ratio"]
        add("text_ratio", "pass" if tr >= 0.15 else ("warn" if tr >= 0.08 else "fail"),
            "%d%% of the page is readable text" % round(tr * 100))

        # ---------- AI trust ----------
        keys = set(d["schema_keys"])
        trust = []
        if d["author_meta"] or "author" in keys:
            trust.append("author")
        if keys & {"datePublished", "dateModified"} or d["article_time"] or d["has_time_tag"]:
            trust.append("date")
        add("author_date", "pass" if len(trust) == 2 else ("warn" if trust else "fail"),
            ("Shows " + " and ".join(trust)) if trust else "No author or date found")
        ne = len(d["external"])
        add("citations", "pass" if ne >= 3 else ("warn" if ne else "fail"),
            "%d links to outside sources" % ne)
        # Look at link addresses on this site and its sub-sites (help.bbc.com) and at link words
        parts = d["bare_host"].split(".")
        root = ".".join(parts[-3:] if len(parts) > 2 and len(parts[-2]) <= 3 else parts[-2:])

        def own_site(u):
            h = bare(urlparse(u).netloc)
            return h == root or h.endswith("." + root)
        own = [(u, t) for u, t in self.anchor_pairs if own_site(u)]
        addrs = [(bare(urlparse(u).netloc) + urlparse(u).path).lower() for u, _ in own] + \
            [(bare(urlparse(u).netloc) + urlparse(u).path).lower() for u in d["internal"]]
        words = [t.lower() for _, t in own if t]
        has_about = any(re.search(r"about|/team\b|who-?we-?are|/company\b|our-?story|impressum|"
                                  r"imprint|leadership|/history\b", x) for x in addrs) \
            or any(re.match(r"(about|who we are|our story|our team)\b", w) for w in words)
        has_contact = any(re.search(r"contact|support|reach-?us|get-?in-?touch|kontakt|feedback|"
                                    r"(^|[./])help([./]|$)", x) for x in addrs) \
            or any(re.match(r"(contact|get in touch|reach us|support\b|help (centre|center))", w)
                   for w in words)
        add("about_contact", "pass" if has_about and has_contact else
            ("warn" if has_about or has_contact else "fail"),
            "About page: %s, contact page: %s" % ("yes" if has_about else "no",
                                                  "yes" if has_contact else "no"))
        if not is_https or noindex:
            add("secure_index", "fail", "HTTPS missing or page hidden with noindex")
        elif not d["ssl_ok"]:
            add("secure_index", "warn", "Visible, but the certificate could not be verified")
        else:
            add("secure_index", "pass", "Secure and visible")

        # ---------- Totals ----------
        for c in checks:
            c["earned"] = c["weight"] * STATUS_POINTS.get(c["status"], 0) \
                if c["status"] in STATUS_POINTS else 0
        seo = [c for c in checks if c["cat"] in SEO_CATS]
        ai = [c for c in checks if c["cat"] in AI_CATS]
        cat_scores = {cat: score_of([c for c in checks if c["cat"] == cat])
                      for cat in SEO_CATS + AI_CATS}
        seo_score, ai_score = score_of(seo), score_of(ai)
        self.log("SEO score %d · AI readiness %d" % (seo_score, ai_score), "ok")

        out = dict(d)
        out.update(seo=seo, ai=ai, seo_score=seo_score, ai_score=ai_score,
                   overall=round((seo_score + ai_score) / 2), cat_scores=cat_scores,
                   audited_at=datetime.datetime.now().strftime("%d %b %Y, %I:%M %p"))
        out.pop("paragraphs", None)
        out.pop("first_words", None)
        return out


def score_of(checks):
    scored = [c for c in checks if c["status"] in STATUS_POINTS]
    total = sum(c["weight"] for c in scored)
    got = sum(c["weight"] * STATUS_POINTS[c["status"]] for c in scored)
    return round(got / total * 100) if total else 0


def grade(score):
    return ("Excellent" if score >= 90 else "Good" if score >= 75 else
            "Needs work" if score >= 50 else "Poor")
