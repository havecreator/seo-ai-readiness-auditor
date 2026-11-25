# SEO & AI Readiness Auditor (version 2)

An industrial-training project in **Search Engine Optimization (SEO)**. Type any website address and the
app visits the site the way Google and AI assistants do, crawls a sample of its pages, tests whether AI bots
are actually let in, takes desktop and mobile screenshots and runs 56 weighted checks. It gives an
**SEO score**, an **AI readiness score** and an **overall score** out of 100, a fix list ordered by impact
and a downloadable HTML report.

Built with Python and Streamlit. Runs on Mac and Windows with one double-click. Version 2 adds the
multi-page crawl, the live bot test, screenshots, the Simple / Complex view and a split into seven files.

---

## 1. Objective

To build a practical, free tool that:

1. downloads a website the way a search-engine crawler does, including a small crawl of its linked pages,
2. checks it against well-known on-page, technical, speed, security and site-wide SEO practices,
3. checks whether AI answer engines (ChatGPT search, Perplexity, Claude, Google AI Overviews) can
   **reach, understand and trust** the site, using both robots.txt and a live request as each bot,
4. explains every result twice: in everyday words for a beginner (Simple mode) and with the exact rule,
   weight and raw data for a technical reader (Complex mode).

## 2. Problem statement

Small businesses, colleges and students usually do not know *why* their website does not rank, and
professional SEO suites (Ahrefs, SEMrush, Moz, Screaming Frog) are paid and complex. At the same time more
people get answers directly from AI assistants, and many websites unknowingly **block AI crawlers** in
`robots.txt`, block them at the firewall, or hide their text behind JavaScript, so they are never cited.
There is a need for a free tool that explains both classic SEO problems and the new **AI search (GEO)**
problems in plain language.

## 3. Features

- Enter any address, with or without `https://` (plain `http://` is tried automatically if HTTPS does not work)
- **Live crawl animation**: each stage is shown as it happens; crawled pages appear as nodes of a site map
- **Multi-page crawl**: the main page plus up to 11 linked pages, chosen like a polite crawler would
  (see section 6.2), used for the site-wide checks (duplicate titles, thin pages, crawl errors, speed)
- **Live bot test**: the page is requested as Googlebot, Bingbot, OAI-SearchBot, ChatGPT-User,
  PerplexityBot, Claude-SearchBot, Claude-User, GPTBot, ClaudeBot and CCBot to see who really gets in,
  next to what robots.txt says for 12 bots
- **Desktop and mobile screenshots** taken with headless Chrome or Edge (skipped with a clear message if
  neither browser is installed)
- **Simple / Complex mode**: everyday words and "Good / Could be better / Needs fixing" by default; the
  Complex view adds technical names, weights, points earned, the exact rule, HTTP headers, the redirect
  chain, robots.txt, sitemap, llms.txt, JSON-LD blocks, the full crawl and bot tables and the score maths
- **56 checks in 10 categories**: 41 SEO checks in 7 categories (169 points) and
  15 AI readiness checks in 3 categories (100 points), each with a plain "why it matters" and "how to fix"
- Outgoing link check (one link per external website, up to 15 sites); firewall answers such as 403 / 429
  and timeouts are listed but not counted as broken
- **Downloadable HTML report** (print to PDF) and raw JSON
- Friendly messages for blocked sites (403, CAPTCHA pages), 404 pages, non-HTML addresses, unknown
  domains, timeouts and certificate problems; if one stage fails, the audit continues without it

### 3.1 Categories

| Group | Category (Simple name) | Technical name | Checks | Points |
|---|---|---|---:|---:|
| SEO | Your content | On-page content | 8 | 49 |
| SEO | Technical setup | Technical SEO | 10 | 40 |
| SEO | Speed | Performance | 7 | 22 |
| SEO | Security | Security | 3 | 9 |
| SEO | Sharing and rich results | Social & structured data | 3 | 13 |
| SEO | Links | Link profile | 4 | 13 |
| SEO | Whole-site health | Site-wide crawl | 6 | 23 |
| AI readiness | Can AI reach you? | AI crawler access | 4 | 42 |
| AI readiness | Can AI understand you? | AI content extractability | 7 | 39 |
| AI readiness | Will AI trust you? | Trust and E-E-A-T signals | 4 | 19 |

### 3.2 SEO checks (41 checks, 169 points)

Generated from `explanations.CHECKS`, so the weights and rules below are exactly what the code uses.
"info" checks are shown but not scored.

| Category | Check (technical name) | Simple-mode name | Weight | Rule (pass / warn / fail) |
|---|---|---|---:|---|
| On-page content | Title tag | Page title on Google | 10 | <title> length 30–60 chars = pass; any other length = warn; missing = fail. |
| On-page content | Meta description | Short description on Google | 8 | <meta name="description"> length 70–160 = pass; other length = warn; missing = fail. |
| On-page content | H1 heading | Main heading | 7 | count(<h1>) == 1 = pass; more than 1 = warn; none = fail. |
| On-page content | H2 subheadings | Section headings | 4 | at least one <h2> = pass. |
| On-page content | Heading hierarchy | Headings in the right order | 3 | no jump of more than one level between consecutive headings = pass; 1–2 jumps = warn. |
| On-page content | Content length | Amount of text | 7 | visible words ≥ 600 = pass; 300–599 = warn; < 300 = fail. |
| On-page content | Title / content relevance | Title matches the content | 4 | ≥ 50% of title keywords (stop-words removed) appear in H1 + first 150 words = pass; ≥ 25% = warn. |
| On-page content | Image alt attributes | Image descriptions | 6 | alt coverage ≥ 90% = pass; ≥ 50% = warn; else fail. No images = pass. |
| Technical SEO | HTTPS / TLS | Secure connection (padlock) | 6 | final URL is https and the certificate verifies = pass; unverifiable cert = warn; http = fail. |
| Technical SEO | Mobile viewport | Works on mobile phones | 7 | viewport meta with width=device-width = pass; fixed width = warn; missing = fail. |
| Technical SEO | Canonical URL | Preferred address set | 4 | <link rel="canonical"> present and pointing to this page = pass; points elsewhere or missing = warn. |
| Technical SEO | HTML lang attribute | Language declared | 2 | <html lang> present = pass. |
| Technical SEO | Indexability | Allowed to appear on Google | 8 | no 'noindex' in meta robots, meta googlebot or X-Robots-Tag header = pass. |
| Technical SEO | robots.txt | Instructions for search bots | 3 | /robots.txt returns 200 with plain text (not an HTML error page) = pass. |
| Technical SEO | XML sitemap | List of all your pages | 4 | Sitemap: line in robots.txt, /sitemap.xml or /sitemap_index.xml with <urlset>/<sitemapindex> = pass. |
| Technical SEO | Redirect chain | Redirects | 3 | 0–1 redirect hops = pass; 2 = warn; 3 or more = fail. |
| Technical SEO | URL structure | Clean web address | 2 | length < 100, lowercase path, no underscores, ≤ 2 query parameters = pass. |
| Technical SEO | Favicon | Site icon | 1 | <link rel="icon"> or /favicon.ico present = pass. |
| Performance | Time to first byte (TTFB) | Server response speed | 6 | TTFB < 0.8 s = pass; < 1.8 s = warn; else fail (Google's 'good' threshold is 0.8 s). |
| Performance | HTML document size | Page code size | 2 | HTML < 200 KB = pass; < 500 KB = warn; else fail. |
| Performance | Text compression | Compression switched on | 3 | Content-Encoding is gzip, br, zstd or deflate = pass (pages under 1.4 KB also pass). |
| Performance | Render-blocking scripts | Scripts that delay the page | 4 | <head> scripts with src and no async/defer/module: 0–2 = pass; 3–6 = warn; > 6 = fail. |
| Performance | Image dimensions (CLS) | Image sizes declared | 3 | ≥ 80% of <img> have width and height = pass; ≥ 40% = warn. No images = pass. |
| Performance | Lazy loading | Images load only when needed | 2 | pages with more than 5 images use loading="lazy" on at least one = pass. |
| Performance | HTTP caching headers | Browser caching | 2 | Cache-Control, ETag or Last-Modified header present = pass. |
| Security | HSTS header | Always-secure setting | 2 | Strict-Transport-Security header present on an https page = pass. |
| Security | Mixed content | Insecure files on a secure page | 4 | count of img/script/stylesheet/iframe/media loaded over http:// on an https page: 0 = pass; 1–3 = warn; more = fail. |
| Security | Security headers | Protection settings | 3 | 3 of 3 headers = pass; 1–2 = warn; 0 = fail. |
| Social & structured data | Open Graph tags | Preview on WhatsApp and LinkedIn | 5 | 3 of 3 og tags = pass; 1–2 = warn; 0 = fail. |
| Social & structured data | Twitter / X card | Preview on X (Twitter) | 2 | twitter:card meta present = pass. |
| Social & structured data | Structured data (Schema.org) | Rich result labels | 6 | valid JSON-LD or microdata found = pass; found but some blocks invalid = warn; none = fail. |
| Link profile | Internal links | Links to your other pages | 4 | ≥ 5 unique internal links = pass; 1–4 = warn; 0 = fail. |
| Link profile | Anchor text quality | Clear link wording | 3 | generic ('click here', 'read more', 'here', 'more') or empty anchors ≤ 10% = pass; ≤ 25% = warn. |
| Link profile | Broken links | Links that lead nowhere | 6 | crawled internal pages + one sampled link per external site returning 404/410/5xx or an unknown domain: 0 = pass; 1–2 = warn; more = fail. 401/403/429 answers, firewall challenges, timeouts and old-TLS failures are listed but not counted as broken. |
| Link profile | External links | Links to other websites | info | informational, not scored. |
| Site-wide crawl | Crawl errors | Pages that failed to open | 6 | crawled pages returning 404/410/5xx or no response: 0 = pass; 1 = warn; more = fail. Pages that refuse the crawler (401/403/429 or a firewall challenge) are not counted. |
| Site-wide crawl | Duplicate title tags | Pages sharing the same title | 4 | no two crawled pages share a title = pass; ≤ 20% of pages = warn. |
| Site-wide crawl | Duplicate meta descriptions | Pages sharing the same description | 3 | no duplicated non-empty descriptions = pass; ≤ 20% of pages = warn. |
| Site-wide crawl | Missing titles / descriptions | Pages missing a title or description | 4 | all crawled pages have both = pass; ≤ 25% missing = warn. |
| Site-wide crawl | Thin content | Pages with very little text | 3 | pages under 250 words ≤ 20% = pass; ≤ 50% = warn. |
| Site-wide crawl | Average response time | Speed across the site | 3 | average crawled page download < 1.5 s = pass; < 3 s = warn. |

### 3.3 AI readiness checks (15 checks, 100 points)

| Category | Check (technical name) | Simple-mode name | Weight | Rule (pass / warn / fail) |
|---|---|---|---:|---|
| AI crawler access | AI crawler access (robots.txt) | AI assistants allowed in | 16 | RFC 9309 evaluation (longest match wins) for 7 search/answer bots: all allowed = pass; ≥ 50% = warn. |
| AI crawler access | AI crawler reachability (live test) | AI bots actually let in | 10 | GET the page with each AI answer bot's user-agent; 200 with real content = reachable. All reachable = pass; ≥ 50% = warn. (Sites that verify bots by IP address may still allow the real bots.) |
| AI crawler access | llms.txt | Guide file for AI (llms.txt) | 6 | /llms.txt returns 200 with non-HTML text longer than 20 characters = pass (proposal from llmstxt.org; not used by Google Search). |
| AI crawler access | Server-rendered content | Readable without JavaScript | 10 | words in raw HTML ≥ 300 = pass; ≥ 100 = warn; else fail. |
| AI content extractability | FAQ / HowTo schema | Questions and answers labelled | 8 | FAQPage, QAPage or HowTo type present = pass. |
| AI content extractability | Entity schema | Says clearly who you are | 6 | Organization, LocalBusiness, Person, WebSite or similar type present = pass. |
| AI content extractability | Question-style headings | Headings people would ask | 6 | ≥ 2 H2/H3 headings ending in '?' or starting with a question word = pass; 1 = warn. |
| AI content extractability | Answer-sized paragraphs | Short, quotable paragraphs | 6 | ≥ 60% of paragraphs are 15–90 words = pass; ≥ 30% = warn. |
| AI content extractability | Lists and tables | Lists and tables | 5 | list items (<li>, role="list" or <dl>) or a <table> present = pass. |
| AI content extractability | Page summary (meta description) | Clear page summary | 4 | meta description present = pass. |
| AI content extractability | Text-to-HTML ratio | More words than code | 4 | visible text bytes ÷ HTML bytes ≥ 15% = pass; ≥ 8% = warn. |
| Trust and E-E-A-T signals | Author and date signals | Who wrote it, and when | 6 | author (meta or schema) and a date (schema, article:*_time meta or <time>) = pass; one of them = warn. |
| Trust and E-E-A-T signals | Outbound citations | Links to sources | 4 | ≥ 3 unique external links = pass; 1–2 = warn. |
| Trust and E-E-A-T signals | About and contact pages | Shows who runs the site | 5 | links (to this site or its sub-domains) to an about/team page and a contact/support page, found by address or link words = pass; one of them = warn. |
| Trust and E-E-A-T signals | Secure and indexable | Safe and visible to search | 4 | https with a valid certificate and no noindex = pass. |

**Bots tested.** Counted in the robots.txt score (they decide whether a site can be found and *cited*):
Googlebot, Bingbot, OAI-SearchBot, ChatGPT-User, PerplexityBot, Claude-SearchBot, Claude-User. Shown for
information (training bots; blocking them is a business decision): GPTBot, ClaudeBot, Google-Extended,
Applebot-Extended, CCBot. The live test score uses the five AI answer bots (OAI-SearchBot, ChatGPT-User,
PerplexityBot, Claude-SearchBot, Claude-User). Google-Extended and Applebot-Extended are permission
tokens only, with no crawler of their own, so they are not live-tested.

## 4. What is GEO / AI search optimization?

**GEO (Generative Engine Optimization)**, also called AI search optimization or AEO, is the practice of
making content easy for AI assistants to find, understand and quote. ChatGPT search, Perplexity, Claude
and Google AI Overviews read pages with their own crawlers, write an answer and cite a few sources. A page
can only be cited if:

1. **Access**: the AI crawler is allowed in robots.txt, is not blocked by a firewall, and the text is in
   the HTML (most AI crawlers do not run JavaScript). An optional `llms.txt` file gives AI tools a map of
   the site.
2. **Understanding**: the content is organised as clear questions and short, self-contained answers, with
   lists, tables and Schema.org markup.
3. **Trust**: the page shows who wrote it and when, cites sources, links to About and Contact pages, and
   is secure and indexable.

Classic SEO is still the foundation: AI engines build on regular search indexes (Google, Bing).

## 5. Tech stack

| Part | Technology |
|---|---|
| Language | Python 3.9+ (3.9 compatible: no `match`, no `X \| Y` type hints) |
| Web UI | Streamlit |
| Downloading pages | requests |
| HTML parsing | BeautifulSoup 4 + lxml |
| Concurrency | `concurrent.futures.ThreadPoolExecutor` |
| Screenshots | headless Google Chrome / Microsoft Edge (`--screenshot`), Pillow to resize |
| robots.txt rules | own RFC 9309 evaluator (longest match wins, `*` and `$` wildcards) |
| Tables | pandas |
| Report | self-contained HTML (printable to PDF) + JSON |

## 6. Architecture

| File | Role |
|---|---|
| `app.py` | Streamlit entry point: address form, Simple / Complex toggle, runs the audit, result tabs |
| `ui.py` | CSS and HTML building blocks for the results (score cards, check cards, tables) |
| `ui_crawl.py` | the live crawl animation, driven by the engine's progress events |
| `report.py` | builds the downloadable, self-contained HTML report |
| `engine.py` | the auditor: fetching, crawl, robots.txt, bot tests, link check, screenshots, scoring; no Streamlit code |
| `explanations.py` | wording, category, weight and exact rule of every check (one place to review or tune) |
| `icons.py` | inline SVG icons (no emojis, no icon font) |
| `requirements.txt`, `run.command`, `run.bat` | packages and one-click launchers |

The engine knows nothing about the UI. `app.py` creates
`Auditor(url, max_pages=12, check_links=True, screenshots=True, min_seconds=10, progress=callback)` and
calls `run()`. The engine calls `callback` with small events (`stage`, `log`, `node`, `plan`, `bot`,
`tick`, `done`) that `ui_crawl.py` turns into the animation, and returns one result dictionary that
`ui.py` and `report.py` display.

```
 address ──> app.py ──> engine.Auditor.run() ──────────────────────────────> result dict
                 ^            |  progress events (stage, node, bot, log…)         |
                 |            v                                                   v
                 |       ui_crawl.py (live animation)              ui.py (tabs)  report.py (HTML)
                 └── explanations.py (wording, weights, rules) and icons.py (SVG) ┘
```

### 6.1 Pipeline stages

| # | Stage | What happens | Time budget |
|---|---|---|---|
| 1 | connect | download the page, follow redirects, read headers; retry with an honest bot name if refused, without certificate checking if the chain is broken, over http if HTTPS does not answer | 6 s connect, 15 s answer |
| 2 | robots | robots.txt and llms.txt (already downloading in the background since stage 1) | 8 s for files |
| 3 | sitemap | the best sitemap from robots.txt (or `/sitemap.xml`), first child of a sitemap index, `.xml.gz` supported | 5 s |
| 4 | page | parse the main page: title, meta tags, headings, images, links, text, JSON-LD, resources | – |
| 5 | crawl | visit up to 11 chosen pages with 6 threads | 8 s |
| 6 | bots | robots.txt answer for 12 bots, then all 10 live requests at the same time | 7 s |
| 7 | links | outgoing links (started in the background at stage 5) | 10 s |
| 8 | shots | desktop and mobile screenshots (started in the background right after stage 1) | 15 s each |
| 9 | score | run the 56 checks; keep the animation on screen until at least 10 s have passed | – |

Every request has its own limit (4 s to connect, 6 s to answer). Anything not finished inside its budget
is reported as "no answer" and the audit moves on. Each stage runs inside a safe wrapper: if it crashes,
the error is logged, defaults are filled in and the audit continues. Only a failed connection to the main
page stops the audit, with a plain-language message.

### 6.2 How the crawler chooses pages

1. Only links to the same website (`www.` and non-`www.` count as one site).
2. Skip files (PDF, images, archives, feeds), pages that waste a small budget (login, sign-up, cart,
   checkout, search results, tag / author / calendar / paging pages, `?sort=`, `?s=`…), wiki system pages,
   and every page that robots.txt asks crawlers to avoid.
3. Never visit one page twice: http vs https, `www.`, a trailing slash, `index.html` and `#anchors` are
   ignored when comparing addresses; pages that redirect to a page already crawled are counted once.
4. Well-known sections first (About, Contact, Blog, News, Products, Services, Docs, FAQ, Admissions…),
   then short addresses, in the order the links appear (top navigation comes first).
5. At most 3 pages from the same section in the first pass, so the sample covers the whole site; sitemap
   pages top up the list when the page has few links.

### 6.3 Concurrency

| Work | Threads |
|---|---|
| robots.txt, llms.txt, sitemap.xml, sitemap_index.xml, favicon, outgoing links | shared background pool of 10 |
| crawl | 6 |
| live bot test | 10 (all at once) |
| screenshots | 2 browser processes, running from stage 1 until stage 8 |

Most of the time is spent waiting for servers, so running requests side by side turns about 40 requests
into a 5 to 15 second audit. The audit is padded to at least 10 seconds (`min_seconds=10`) so the crawl
animation can be followed on a projector; the padding never changes the results.

## 7. Scoring formula

| Status | Points earned |
|---|---|
| pass ("Good") | full weight |
| warn ("Could be better") | half the weight |
| fail ("Needs fixing") | 0 |
| info ("For your information") | not scored |

```
score   = (points earned / total weight of the scored checks) x 100     (rounded)
overall = (SEO score + AI readiness score) / 2
```

Grades: 90+ Excellent, 75+ Good, 50+ Needs work, below 50 Poor. The same formula gives each category
score. Site-wide checks become "info" (not scored) when fewer than 2 pages could be crawled.

Example: a page that passes every AI check except `llms.txt` (warn, weight 6) and FAQ schema (fail,
weight 8) earns 100 - 3 - 8 = 89 of 100 points, so its AI readiness score is **89**.

## 8. How to run

### Mac
1. Install Python 3 if needed (https://www.python.org/downloads/).
2. Double-click **`run.command`** (the first time macOS may block it: right-click, **Open**, **Open**).
3. The first run creates a `.venv` folder and installs the requirements (1 to 2 minutes). The app opens at
   **http://localhost:8501**. Keep the Terminal window open while you use it.

### Windows
1. Install Python 3 from https://www.python.org/downloads/ and tick **"Add python.exe to PATH"**.
2. Double-click **`run.bat`**. The first run installs everything, then the browser opens at
   http://localhost:8501.

Both launchers reinstall packages automatically when `requirements.txt` changes. For screenshots, Google
Chrome or Microsoft Edge must be installed (any normal installation is found automatically).

### Manual (any OS)
```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## 9. Sample results (real test runs, 25 Nov 2026)

Measured on a Mac with Python 3.9, all options on (12 pages, link check, screenshots). Time is the full
audit including the 10-second minimum.

| Website | SEO | AI | Pages crawled | Seconds | Notes |
|---|---:|---:|---:|---:|---|
| python.org | 81 | 78 | 12 | 10.1 | 11 of 12 pages share one meta description; no FAQ schema; images without sizes |
| moz.com/learn/seo | 86 | 82 | 12 | 11.8 | strong page; skipped heading levels, little text compared with code |
| en.wikipedia.org/wiki/Search_engine_optimization | 78 | 77 | 12 | 10.0 | no meta description on any crawled page; several dead outgoing links; fake Googlebot refused (IP check) |
| bbc.com | 83 | 63 | 12 | 11.2 | robots.txt blocks ChatGPT search, ChatGPT browsing, Perplexity and Claude search; no H1; 627 KB HTML |
| example.com | 61 | 48 | 1 | 10.3 | 25-word placeholder page with no links, so nothing to crawl |
| docs.streamlit.io | 81 | 71 | 12 | 11.6 | has llms.txt; no structured data, no lang attribute |
| w3.org | 83 | 72 | 12 | 10.1 | only answers an honest bot name, so the audit switches to it; no structured data |
| zomato.com | 74 | 36 | 1 | 14.1 | has llms.txt, but robots.txt blocks 5 of 7 answer bots and asks other crawlers to stay out (main page only); firewall drops bot requests |
| home.iitd.ac.in (IIT Delhi) | 70 | 67 | 12 | 17.6 | no compression, 9 render-blocking scripts, one 404 page; slow to draw, so screenshots skipped |
| du.ac.in (Delhi University) | 50 | 66 | 12 | 21.8 | 233 H1 tags, 751 KB HTML; 4 links written without http:// (e.g. www.ipcollege.ac.in/) lead to 404 pages |
| wordpress.org/news (WordPress) | 82 | 72 | 12 | 10.3 | has llms.txt; no meta description, 76-character title |
| techcrunch.com (WordPress) | 87 | 79 | 12 | 12.6 | blocks only training bots (GPTBot, ClaudeBot, Applebot-Extended, CCBot) |
| cloudflare.com (Cloudflare) | 89 | 74 | 12 | 10.3 | has llms.txt; 1.3 MB HTML, 1% readable text |
| httpforever.com (http only) | 80 | 67 | 1 | 10.3 | no HTTPS, so the secure-connection checks fail |

Scores can move by 2 to 3 points between runs because speed checks depend on the network.

Edge cases tested (all give a clear message or a sensible result, never a crash):

| Input | Result |
|---|---|
| `python.org` (no `https://`) | `https://` added, redirected to `https://www.python.org/` |
| `httpforever.com` (site with no HTTPS) | HTTPS fails, `http://` is tried automatically and audited |
| `python.org/static/favicon.ico` (an image) | "That address did not return a web page (it returned image/x-icon)…" |
| `https://www.python.org/sitemap.xml` / a missing page | "Page not found (HTTP 404)…" |
| `thisdomaindoesnotexist-zzqx.com` | connection error, shown by the app as "Could not connect… Check the spelling of the address" |
| `my site.com`, `ht!tp://bad url`, `example..com` | "That does not look like a website address…" (no network request) |
| `reddit.com`, `medium.com`, `npmjs.com` | "The website refused our crawler (HTTP 403)…" |
| `amazon.in` | "The website answered with an anti-bot check (a CAPTCHA or JavaScript challenge)…" |
| `https://expired.badssl.com/` (expired certificate) | audited; HTTPS checks warn "certificate could not be verified" |
| No Chrome / Edge installed (simulated) | audit completes; screenshots show "No Chrome or Edge browser was found…" |
| Each stage forced to crash (simulated) | audit completes; the stage is logged as skipped and its checks fall back safely |

## 10. Limitations

- **No JavaScript rendering for the checks**: pages are read as raw HTML, like most AI crawlers do.
  Single-page apps show few words and low scores. (Screenshots do run JavaScript.)
- **The crawl is a sample**: up to 12 pages inside an 8-second budget, not the whole site.
- **The live bot test cannot fake IP addresses**: big sites verify real Googlebot and Bingbot by IP, so a
  refusal of our imitation does not prove the real bot is refused.
- **robots.txt is evaluated for the audited address**; firewalls may still behave differently per page.
- **Bot protection**: sites such as Reddit, Medium or Amazon refuse automated tools and cannot be audited;
  sites whose robots.txt asks unknown crawlers to stay out (zomato.com) are audited on the main page only.
- **Screenshots** need Chrome or Edge, and very slow pages are skipped after 15 seconds.
- **Old TLS on macOS Python 3.9** (LibreSSL 2.8) cannot open a few sites that only accept TLS 1.3; such
  outgoing links are listed as "could not be checked". Python 3.10+ from python.org fixes this.
- **Rule-based checks**: thresholds are public best-practice guidelines, not Google's ranking algorithm;
  no backlink, keyword-ranking or real-user Core Web Vitals data is used.

## 11. Future scope

- Render JavaScript (Playwright) to compare raw and rendered content
- Core Web Vitals from the Google PageSpeed Insights API
- A larger, scheduled crawl with orphan-page and internal-link-graph analysis
- Keyword analysis and competitor comparison (two sites side by side)
- Use an LLM to suggest rewritten titles, descriptions and FAQ answers
- Track scores over time and export a PDF directly
- Test whether a site is actually cited by AI assistants for chosen questions

---

*Industrial Training Project – Search Engine Optimization.*
