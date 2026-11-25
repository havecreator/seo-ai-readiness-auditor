"""
Downloadable HTML report.

    from report import build_report
    html_text = build_report(res)      # res = Auditor(...).run()

Returns one complete, standalone HTML document (inline CSS, inline SVG icons, screenshots
embedded as data URIs). It is designed to be read on screen, attached to a training report,
or printed to PDF on A4 paper. Everything that comes from the audited page is escaped.
"""

import html

from explanations import AI_CATS, CATEGORIES, CHECKS, SEO_CATS, STATUS_TEXT
from icons import STATUS_ICON, icon

try:  # keep the grade words identical to the app
    from engine import grade
except Exception:  # pragma: no cover - engine import should always work inside the app
    def grade(score):
        return ("Excellent" if score >= 90 else "Good" if score >= 75 else
                "Needs work" if score >= 50 else "Poor")


COL = {
    "ok": "#059669", "ok_soft": "#ecfdf5",
    "warn": "#d97706", "warn_soft": "#fffbeb",
    "bad": "#dc2626", "bad_soft": "#fef2f2",
    "accent": "#2563eb", "accent_soft": "#eff6ff",
    "muted": "#64748b", "faint": "#94a3b8", "track": "#e2e8f0",
}
STATUS_COL = {"pass": "ok", "warn": "warn", "fail": "bad", "info": "info"}

GLOSSARY = [
    ("SEO", "Search engine optimisation: making a website easy for search engines to find, "
            "understand and show to people."),
    ("SERP", "Search engine results page: the list of results you see after searching on Google "
             "or Bing."),
    ("Crawl", "When a bot visits a page and follows its links to discover more pages."),
    ("Index", "The search engine's library of pages. Only indexed pages can appear in results."),
    ("robots.txt", "A small text file at the root of a site that tells bots which parts they may "
                   "visit."),
    ("Sitemap", "An XML file that lists the pages of a site so search engines can find them all."),
    ("Canonical", "A tag that names the preferred address of a page when the same content is "
                  "reachable at several addresses."),
    ("Schema", "Structured data (usually JSON-LD) that labels what a page is about, such as an "
               "article, product or business."),
    ("Open Graph", "Tags that control the title, text and image shown when a link is shared on "
                   "social media and chat apps."),
    ("GEO", "Generative engine optimisation: preparing content so AI assistants such as ChatGPT, "
            "Perplexity and Claude can find, understand and cite it."),
    ("llms.txt", "A proposed Markdown file at /llms.txt that gives AI tools a short map of a "
                 "site's most important pages."),
    ("TTFB", "Time to first byte: how long the server takes to start sending the page after it "
             "is requested."),
]

# Checks whose rules are listed in the appendix as the main thresholds (read from
# explanations.CHECKS, so the wording always matches what the engine applies).
KEY_THRESHOLDS = ["title", "meta_desc", "h1", "word_count", "alt_text", "ttfb", "html_size",
                  "render_blocking", "img_dims", "redirects", "internal_links", "broken_links",
                  "ai_robots", "ai_firewall", "no_js", "answer_paras", "text_ratio"]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def e(value):
    """Escape anything for HTML text or attribute use."""
    return html.escape("" if value is None else str(value), quote=True)


def score_key(score):
    return "ok" if score >= 75 else ("warn" if score >= 50 else "bad")


def score_color(score):
    return COL[score_key(score)]


def fmt_secs(value, digits=2):
    try:
        return ("%." + str(digits) + "f s") % float(value)
    except (TypeError, ValueError):
        return "–"


def fmt_ms(value):
    try:
        return "%d ms" % round(float(value) * 1000)
    except (TypeError, ValueError):
        return "–"


def fmt_points(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "0"
    return ("%d" % x) if x == int(x) else ("%.1f" % x)


def status_pill(status, small=False):
    key = STATUS_COL.get(status, "info")
    word = STATUS_TEXT.get(status, ("", ""))[0]
    color = COL["accent"] if key == "info" else COL[key]
    return ('<span class="pill pill-%s%s">%s<span>%s</span></span>'
            % (key, " pill-sm" if small else "", icon(STATUS_ICON.get(status, "circle"),
                                                       12 if small else 14, color), e(word)))


def yes_no_pill(ok, yes="Yes", no="No"):
    if ok:
        return '<span class="pill pill-ok pill-sm">%s<span>%s</span></span>' % (
            icon("check", 12, COL["ok"]), e(yes))
    return '<span class="pill pill-bad pill-sm">%s<span>%s</span></span>' % (
        icon("x", 12, COL["bad"]), e(no))


def ring(score, size=124):
    """Circular score gauge as inline SVG."""
    score = max(0, min(100, int(round(score or 0))))
    stroke = 10
    r = (size - stroke) / 2.0
    c = 2 * 3.14159265 * r
    on = c * score / 100.0
    color = score_color(score)
    return (
        '<svg class="ring" width="{s}" height="{s}" viewBox="0 0 {s} {s}" role="img" '
        'aria-label="{v} out of 100">'
        '<circle cx="{h}" cy="{h}" r="{r:.2f}" fill="none" stroke="{t}" stroke-width="{w}"/>'
        '<circle cx="{h}" cy="{h}" r="{r:.2f}" fill="none" stroke="{col}" stroke-width="{w}" '
        'stroke-linecap="round" stroke-dasharray="{on:.2f} {c:.2f}" '
        'transform="rotate(-90 {h} {h})"/>'
        '<text x="{h}" y="{ty}" text-anchor="middle" class="ring-num" fill="#0f172a">{v}</text>'
        '<text x="{h}" y="{ty2}" text-anchor="middle" class="ring-of" fill="#94a3b8">of 100</text>'
        '</svg>'
    ).format(s=size, h=size / 2.0, r=r, t=COL["track"], w=stroke, col=color,
             on=on if score else 0.001, c=c, v=score, ty=size / 2.0 + 8, ty2=size / 2.0 + 26)


def verdict(seo, ai, overall):
    g = grade(overall)
    start = {
        "Excellent": "The site is in excellent shape",
        "Good": "The site is in good shape",
        "Needs work": "The site has a working base but needs work",
        "Poor": "The site has important gaps",
    }.get(g, "The audit is complete")
    if ai <= seo - 6:
        return start + ", and AI readiness is the weaker area to improve first."
    if seo <= ai - 6:
        return start + ", and the search engine basics are the weaker area to improve first."
    return start + " for both search engines and AI assistants."


def page_issues(p):
    issues = []
    status = p.get("status")
    if p.get("error"):
        issues.append(p["error"])
    elif status is None:
        issues.append("No response")
    elif status >= 400:
        issues.append("HTTP error %s" % status)
    if p.get("error", "").startswith("Not an HTML"):
        return issues
    if status is not None and status < 400:
        if not p.get("title"):
            issues.append("No title")
        if not p.get("meta_desc"):
            issues.append("No description")
        h1 = p.get("h1") or 0
        if h1 == 0:
            issues.append("No H1")
        elif h1 > 1:
            issues.append("%d H1s" % h1)
        if p.get("noindex"):
            issues.append("noindex")
        if (p.get("words") or 0) < 250:
            issues.append("Thin content")
        if p.get("imgs_no_alt"):
            n = p["imgs_no_alt"]
            issues.append("%d image%s without alt" % (n, "" if n == 1 else "s"))
    return issues


def usable_favicon(url):
    url = (url or "").strip()
    low = url.lower()
    if low.startswith(("http://", "https://")) or (low.startswith("data:image/") and len(url) > 20):
        return url
    return ""


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root{
  --bg:#ffffff;--surface:#f8fafc;--surface-2:#f1f5f9;--border:#e2e8f0;--text:#0f172a;
  --muted:#64748b;--faint:#94a3b8;--accent:#2563eb;--accent-ink:#1d4ed8;--accent-soft:#eff6ff;
  --ok:#059669;--ok-soft:#ecfdf5;--warn:#d97706;--warn-soft:#fffbeb;--bad:#dc2626;--bad-soft:#fef2f2;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
*{box-sizing:border-box;-webkit-print-color-adjust:exact;print-color-adjust:exact}
html,body{margin:0;padding:0;background:var(--bg);color:var(--text)}
body{font-family:Inter,-apple-system,"Segoe UI",Roboto,sans-serif;font-size:14px;line-height:1.55;
  -webkit-font-smoothing:antialiased}
.page{max-width:920px;margin:0 auto;padding:40px 32px 56px}
.ic{display:inline-block;vertical-align:middle;flex:none}
h1,h2,h3{margin:0;font-weight:600;letter-spacing:-.01em}
h2{font-size:20px;display:flex;align-items:center;gap:10px;margin:0 0 4px}
h2 .num{display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;
  border-radius:8px;background:var(--accent-soft);color:var(--accent-ink);font-size:13px;font-weight:600}
h3{font-size:15px}
p{margin:0}
.muted{color:var(--muted)}.faint{color:var(--faint)}
.mono{font-family:var(--mono);font-size:.92em}
.small{font-size:12px}
.section{margin-top:40px}
.lead{color:var(--muted);margin:2px 0 16px 36px;font-size:13.5px}
.card{background:#fff;border:1px solid var(--border);border-radius:12px;
  box-shadow:0 1px 2px rgba(15,23,42,.05)}

/* Cover */
.brand{display:flex;align-items:center;gap:10px;color:var(--muted);font-size:13px;font-weight:500}
.brand .mark{display:inline-flex;width:30px;height:30px;border-radius:8px;background:var(--accent-soft);
  align-items:center;justify-content:center}
.cover{padding:28px 28px 24px;margin-top:18px;border-top:4px solid var(--accent)}
.cover h1{font-size:28px;line-height:1.2}
.site{display:flex;align-items:center;gap:12px;margin-top:14px}
.site img{width:36px;height:36px;border-radius:8px;border:1px solid var(--border);object-fit:contain;
  background:#fff;padding:3px}
.site .dom{font-size:18px;font-weight:600}
.site .url{color:var(--muted);font-family:var(--mono);font-size:12.5px;word-break:break-all}
.meta{display:grid;grid-template-columns:repeat(3,1fr);gap:0;margin-top:22px;border:1px solid var(--border);
  border-radius:10px;overflow:hidden}
.meta div{padding:10px 14px;background:var(--surface);border-right:1px solid var(--border);
  border-bottom:1px solid var(--border)}
.meta div:nth-child(3n){border-right:none}
.meta div:nth-last-child(-n+3){border-bottom:none}
.meta .k{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);
  font-weight:500}
.meta .v{font-weight:600;font-size:14px}
.toc{margin-top:18px;display:flex;flex-wrap:wrap;gap:6px 18px;font-size:12.5px;color:var(--muted)}
.toc span b{color:var(--accent-ink);font-weight:600;margin-right:4px}

/* Scores */
.scores{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.score{padding:18px 16px 16px;text-align:center}
.score .label{display:flex;align-items:center;justify-content:center;gap:6px;font-weight:600;font-size:14px}
.score .grade{display:inline-block;margin-top:6px;padding:2px 10px;border-radius:999px;font-size:12px;
  font-weight:600}
.score .sub{color:var(--muted);font-size:12px;margin-top:6px}
.ring{display:block;margin:10px auto 0}
.ring-num{font-size:30px;font-weight:700;font-family:Inter,-apple-system,"Segoe UI",Roboto,sans-serif}
.ring-of{font-size:11px;font-family:Inter,-apple-system,"Segoe UI",Roboto,sans-serif}
.g-ok{background:var(--ok-soft);color:var(--ok)}.g-warn{background:var(--warn-soft);color:var(--warn)}
.g-bad{background:var(--bad-soft);color:var(--bad)}
.verdict{margin-top:14px;padding:14px 18px;display:flex;gap:12px;align-items:flex-start;
  background:var(--surface)}
.verdict p{font-size:15px;font-weight:500}
.counts{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}

/* Pills */
.pill{display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border-radius:999px;font-size:12px;
  font-weight:600;white-space:nowrap}
.pill-sm{padding:2px 8px;font-size:11.5px}
.pill-ok{background:var(--ok-soft);color:var(--ok)}
.pill-warn{background:var(--warn-soft);color:var(--warn)}
.pill-bad{background:var(--bad-soft);color:var(--bad)}
.pill-info{background:var(--accent-soft);color:var(--accent-ink)}
.pill-neutral{background:var(--surface-2);color:var(--muted)}

/* Screenshots */
.shots{display:flex;gap:22px;align-items:flex-start;padding:22px;background:var(--surface)}
.shot-d{flex:1 1 auto;min-width:0}
.shot-m{flex:0 0 170px}
.browser{border:1px solid var(--border);border-radius:10px;overflow:hidden;background:#fff}
.browser .bar{display:flex;align-items:center;gap:6px;padding:7px 10px;background:var(--surface-2);
  border-bottom:1px solid var(--border)}
.browser .dot{width:8px;height:8px;border-radius:50%;background:#cbd5e1}
.browser .addr{flex:1;margin-left:8px;background:#fff;border:1px solid var(--border);border-radius:6px;
  padding:2px 8px;font-size:10.5px;color:var(--muted);font-family:var(--mono);white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.browser img{display:block;width:100%;height:auto}
.phone{border:7px solid #1e293b;border-radius:24px;overflow:hidden;background:#1e293b;position:relative}
.phone .notch{height:12px;background:#1e293b}
.phone img{display:block;width:100%;height:auto;max-height:340px;object-fit:cover;object-position:top;
  border-radius:0 0 14px 14px;background:#fff}
.cap{margin-top:8px;font-size:12px;color:var(--muted);display:flex;align-items:center;gap:6px}

/* Fixes */
.fixes{display:grid;gap:10px}
.fix{padding:14px 16px;display:grid;grid-template-columns:28px 1fr;gap:4px 12px}
.fix .n{width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  font-size:12.5px;font-weight:600;background:var(--surface-2);color:var(--text)}
.fix .head{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.fix .head h3{margin-right:auto}
.fix .found{font-size:13px;color:var(--muted);margin-top:2px;word-break:break-word}
.fix .cols{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:8px}
.fix .cols .t{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);
  font-weight:600;margin-bottom:2px}
.fix .cols p{font-size:13px}
.pts{font-size:11.5px;color:var(--muted);white-space:nowrap}
.allgood{padding:16px 18px;display:flex;gap:10px;align-items:center;background:var(--ok-soft);
  border-color:#a7f3d0}

/* Category bars */
.catgrid{display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:start}
.catbox{padding:16px 18px}
.catbox h3{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.catbox h3 .tot{margin-left:auto;font-size:13px;color:var(--muted);font-weight:500}
.bar-row{display:grid;grid-template-columns:1fr 44px;gap:2px 10px;align-items:center;padding:7px 0;
  border-top:1px solid var(--surface-2)}
.bar-row:first-of-type{border-top:none}
.bar-row .nm{display:flex;align-items:center;gap:7px;font-size:13px;font-weight:500}
.bar-row .tn{font-size:11px;color:var(--faint);font-weight:400}
.bar-row .val{text-align:right;font-weight:600;font-size:13px}
.track{grid-column:1 / span 2;height:7px;border-radius:999px;background:var(--surface-2);overflow:hidden}
.track span{display:block;height:100%;border-radius:999px}
.bar-row .cnt{grid-column:1 / span 2;font-size:11px;color:var(--muted)}

/* Tables */
table{width:100%;border-collapse:separate;border-spacing:0;font-size:12.5px;table-layout:fixed}
thead{display:table-header-group}
th{text-align:left;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.05em;
  color:var(--muted);background:var(--surface);padding:8px 10px;border-bottom:1px solid var(--border)}
td{padding:9px 10px;border-bottom:1px solid var(--surface-2);vertical-align:top;overflow-wrap:anywhere}
tr:last-child td{border-bottom:none}
.tbl{overflow:hidden}
.tbl + .tbl{margin-top:14px}
.tbl-head{display:flex;align-items:center;gap:10px;padding:12px 14px;border-bottom:1px solid var(--border)}
.tbl-head h3{display:flex;align-items:center;gap:8px}
.tbl-head .tn{font-size:12px;color:var(--muted);font-weight:400}
.tbl-head .sc{margin-left:auto;font-weight:600;font-size:13px}
.ck-name{font-weight:600}
.ck-tech{display:block;font-size:11px;color:var(--faint);margin-top:1px;font-weight:400}
.res .v{word-break:break-word}
.res .wf{margin-top:6px;font-size:12px;color:#334155}
.res .wf b{font-weight:600;color:var(--text)}
.rule{font-size:11px;color:var(--muted)}
.rule .w{display:block;font-weight:600;color:var(--text);font-size:11.5px;margin-bottom:2px}
.rule .tx{font-family:var(--mono);font-size:10.5px;line-height:1.45}
.num{text-align:right;white-space:nowrap}
.c{text-align:center}
.note{padding:12px 16px;display:flex;gap:10px;align-items:flex-start;font-size:13px;color:var(--muted);
  background:var(--surface);margin-top:10px}

/* Appendix */
.app-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.box{padding:16px 18px}
.box h3{margin-bottom:8px;display:flex;align-items:center;gap:8px}
.box ul{margin:0;padding-left:18px}
.box li{margin:3px 0;font-size:13px}
.box ul.plain{list-style:none;padding-left:0}
.box ul.plain li{display:flex;align-items:center;gap:10px;margin:6px 0}
.box ul.plain .pill{min-width:64px;justify-content:center}
.formula{font-family:var(--mono);font-size:12.5px;background:var(--surface);border:1px solid var(--border);
  border-radius:8px;padding:8px 12px;margin:8px 0}
.thr td{font-size:12px}
.thr .tx{font-family:var(--mono);font-size:11px;color:#334155}
dl.gl{display:grid;grid-template-columns:1fr 1fr;gap:10px 22px;margin:0}
dl.gl div{break-inside:avoid}
dl.gl dt{font-weight:600;font-size:13px}
dl.gl dd{margin:1px 0 0;font-size:12.5px;color:var(--muted)}
footer{margin-top:44px;padding-top:16px;border-top:1px solid var(--border);display:flex;
  justify-content:space-between;gap:12px;font-size:12px;color:var(--muted);flex-wrap:wrap}

@media (max-width:720px){
  .page{padding:24px 16px 40px}
  .scores,.catgrid,.app-grid,dl.gl,.fix .cols{grid-template-columns:1fr}
  .meta{grid-template-columns:1fr 1fr}
  .shots{flex-direction:column}.shot-m{flex-basis:auto;width:200px}
  .tbl{overflow-x:auto}
}

@page{size:A4;margin:14mm 12mm 14mm}
@media print{
  html,body{font-size:12px}
  .page{max-width:none;padding:0}
  .section{margin-top:26px}
  .section.newpage{break-before:page;margin-top:0}
  .card{box-shadow:none}
  h2,.tbl-head,.lead{break-after:avoid}
  .card.fix,.score,.catbox,.box:not(.gloss),.verdict,.shots,.note,tr,.bar-row,.cover,dl.gl div{break-inside:avoid}
  .tbl{overflow:visible}
  .phone img{max-height:300px}
  a{color:inherit;text-decoration:none}
}
"""


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
def _section(num, title, lead, body, newpage=False):
    return ('<section class="section%s"><h2><span class="num">%d</span>%s</h2>%s%s</section>'
            % (" newpage" if newpage else "", num, e(title),
               '<p class="lead">%s</p>' % lead if lead else "", body))


def _cover(res, toc):
    fav = usable_favicon(res.get("favicon_url"))
    fav_html = ('<img src="%s" alt="Site icon of %s">' % (e(fav), e(res.get("domain"))) if fav
                else '<span class="mark" style="width:36px;height:36px;border-radius:8px;display:'
                     'inline-flex;align-items:center;justify-content:center;background:#f1f5f9">'
                     '%s</span>' % icon("globe", 18, COL["muted"]))
    pages = res.get("pages") or []
    n_pages = len(pages)
    if n_pages > 1:
        crawled = "%d (main + %d linked)" % (n_pages, n_pages - 1)
    else:
        crawled = "%d (main page only)" % n_pages if n_pages else "0"
    ttfb = res.get("ttfb")
    meta = [
        ("Audited on", e(res.get("audited_at") or "–")),
        ("Audit duration", fmt_secs(res.get("duration"), 1)),
        ("Pages crawled", e(crawled)),
        ("HTTP status", e(res.get("status_code") or "–")),
        ("Server response (TTFB)", fmt_secs(ttfb) if ttfb is not None else "–"),
        ("Main page size", (("%.1f KB" if res["size_kb"] < 10 else "%.0f KB") % res["size_kb"])
         if isinstance(res.get("size_kb"), (int, float)) else "–"),
    ]
    meta_html = "".join('<div><span class="k">%s</span><span class="v">%s</span></div>' % (k, v)
                        for k, v in meta)
    toc_html = "".join('<span><b>%d</b>%s</span>' % (i + 1, e(t)) for i, t in enumerate(toc))
    return (
        '<div class="brand"><span class="mark">%s</span>SEO &amp; AI Readiness Auditor</div>'
        '<div class="card cover">'
        '<h1>Website audit report</h1>'
        '<p class="muted" style="margin-top:4px">Search engine optimisation and AI search '
        'readiness</p>'
        '<div class="site">%s<div><div class="dom">%s</div><div class="url">%s</div></div></div>'
        '<div class="meta">%s</div>'
        '<div class="toc">%s</div>'
        '</div>'
        % (icon("search", 16, COL["accent"]), fav_html, e(res.get("domain")),
           e(res.get("final_url") or res.get("url")), meta_html, toc_html)
    )


def _scores(res, checks):
    seo, ai = res.get("seo_score", 0), res.get("ai_score", 0)
    overall = res.get("overall", round((seo + ai) / 2))
    items = [
        ("SEO", "search", seo, "Classic search engines such as Google and Bing"),
        ("AI readiness", "bot", ai, "AI assistants such as ChatGPT, Perplexity and Claude"),
        ("Overall", "gauge", overall, "Average of the two scores"),
    ]
    cards = []
    for label, ic, sc, sub in items:
        cards.append(
            '<div class="card score"><div class="label">%s%s</div>%s'
            '<span class="grade g-%s">%s</span><div class="sub">%s</div></div>'
            % (icon(ic, 16, COL["muted"]), e(label), ring(sc), score_key(sc), e(grade(sc)), e(sub)))
    n = {s: sum(1 for c in checks if c["status"] == s) for s in ("pass", "warn", "fail", "info")}
    counts = (
        '<div class="counts">'
        '<span class="pill pill-ok pill-sm">%s<span>%d good</span></span>'
        '<span class="pill pill-warn pill-sm">%s<span>%d could be better</span></span>'
        '<span class="pill pill-bad pill-sm">%s<span>%d need fixing</span></span>'
        '<span class="pill pill-info pill-sm">%s<span>%d for information</span></span>'
        '</div>'
        % (icon("check-circle", 12, COL["ok"]), n["pass"], icon("alert", 12, COL["warn"]), n["warn"],
           icon("x-circle", 12, COL["bad"]), n["fail"], icon("info", 12, COL["accent"]), n["info"]))
    return (
        '<div class="scores">%s</div>'
        '<div class="card verdict">%s<div><p>%s</p>%s</div></div>'
        % ("".join(cards), icon("bulb", 20, COL["accent"]), e(verdict(seo, ai, overall)), counts))


def _shots(res):
    shots = res.get("shots") or {}
    desk, mob = shots.get("desktop"), shots.get("mobile")
    if not desk and not mob:
        return ""
    parts = []
    if desk:
        parts.append(
            '<div class="shot-d"><div class="browser"><div class="bar"><span class="dot"></span>'
            '<span class="dot"></span><span class="dot"></span><span class="addr">%s</span></div>'
            '<img src="data:image/jpeg;base64,%s" alt="Desktop screenshot of %s"></div>'
            '<div class="cap">%sDesktop view</div></div>'
            % (e(res.get("final_url")), e(desk), e(res.get("domain")), icon("monitor", 14, COL["muted"])))
    if mob:
        parts.append(
            '<div class="shot-m"><div class="phone"><div class="notch"></div>'
            '<img src="data:image/jpeg;base64,%s" alt="Mobile screenshot of %s"></div>'
            '<div class="cap">%sMobile view</div></div>'
            % (e(mob), e(res.get("domain")), icon("phone", 14, COL["muted"])))
    return '<div class="card shots">%s</div>' % "".join(parts)


def _lost(c):
    return (c.get("weight") or 0) - (c.get("earned") or 0)


def top_fixes(checks, n=8):
    issues = [c for c in checks if c["status"] in ("fail", "warn") and (c.get("weight") or 0) > 0]
    issues.sort(key=lambda c: (-_lost(c), c["status"] != "fail", -(c.get("weight") or 0)))
    return issues[:n]


def _fixes(checks):
    fixes = top_fixes(checks)
    if not fixes:
        return ('<div class="card allgood">%s<p>No checks failed or need attention. The page meets '
                'every rule this tool applies.</p></div>' % icon("check-circle", 20, COL["ok"]))
    out = []
    for i, c in enumerate(fixes, 1):
        group = "SEO" if c["cat"] in SEO_CATS else "AI readiness"
        cat_title = CATEGORIES.get(c["cat"], (c["cat"],))[0]
        out.append(
            '<div class="card fix"><span class="n">%d</span><div>'
            '<div class="head"><h3>%s</h3>%s<span class="pts">%s · %s · worth %s points</span></div>'
            '<p class="found">Found: %s</p>'
            '<div class="cols"><div><div class="t">Why it matters</div><p>%s</p></div>'
            '<div><div class="t">How to fix</div><p>%s</p></div></div>'
            '</div></div>'
            % (i, e(c["plain"]), status_pill(c["status"], True), e(group), e(cat_title),
               fmt_points(_lost(c)), e(c.get("value")), e(c.get("why")), e(c.get("fix"))))
    return '<div class="fixes">%s</div>' % "".join(out)


def _cat_counts(checks, cat):
    cs = [c for c in checks if c["cat"] == cat]
    n = {s: sum(1 for c in cs if c["status"] == s) for s in ("pass", "warn", "fail")}
    bits = ["%d good" % n["pass"]]
    if n["warn"]:
        bits.append("%d could be better" % n["warn"])
    if n["fail"]:
        bits.append("%d need fixing" % n["fail"])
    return ", ".join(bits)


def _categories(res, checks):
    cat_scores = res.get("cat_scores") or {}

    def box(title, ic, total, cats):
        rows = []
        for cat in cats:
            if cat not in CATEGORIES:
                continue
            simple, tech, cic = CATEGORIES[cat]
            sc = int(cat_scores.get(cat, 0) or 0)
            rows.append(
                '<div class="bar-row"><div class="nm">%s%s <span class="tn">%s</span></div>'
                '<div class="val" style="color:%s">%d</div>'
                '<div class="track"><span style="width:%d%%;background:%s"></span></div>'
                '<div class="cnt">%s</div></div>'
                % (icon(cic, 14, COL["muted"]), e(simple), e(tech), score_color(sc), sc,
                   max(sc, 1), score_color(sc), e(_cat_counts(checks, cat))))
        return ('<div class="card catbox"><h3>%s%s<span class="tot">%d / 100</span></h3>%s</div>'
                % (icon(ic, 16, COL["accent"]), e(title), total, "".join(rows)))

    return '<div class="catgrid">%s%s</div>' % (
        box("SEO", "search", res.get("seo_score", 0), SEO_CATS),
        box("AI readiness", "bot", res.get("ai_score", 0), AI_CATS))


def _check_tables(res, checks):
    cat_scores = res.get("cat_scores") or {}
    out = []
    for cat in SEO_CATS + AI_CATS:
        cs = [c for c in checks if c["cat"] == cat]
        if not cs:
            continue
        simple, tech, cic = CATEGORIES.get(cat, (cat, cat, "circle"))
        sc = int(cat_scores.get(cat, 0) or 0)
        rows = []
        for c in cs:
            res_html = '<div class="v">%s</div>' % e(c.get("value"))
            if c["status"] in ("warn", "fail"):
                res_html += ('<div class="wf"><b>Why it matters:</b> %s</div>'
                             '<div class="wf"><b>How to fix:</b> %s</div>'
                             % (e(c.get("why")), e(c.get("fix"))))
            elif c["status"] == "info":
                res_html += '<div class="wf">%s</div>' % e(c.get("why"))
            if c["status"] == "info" or not c.get("weight"):
                pts = "Not scored"
            else:
                pts = "%s of %s points" % (fmt_points(c.get("earned")), fmt_points(c.get("weight")))
            rows.append(
                '<tr><td>%s</td><td><span class="ck-name">%s</span><span class="ck-tech">%s</span>'
                '</td><td class="res">%s</td><td class="rule"><span class="w">%s</span>'
                '<span class="tx">%s</span></td></tr>'
                % (status_pill(c["status"], True), e(c.get("plain")), e(c.get("name")), res_html,
                   e(pts), e(c.get("tech"))))
        group = "SEO" if cat in SEO_CATS else "AI readiness"
        out.append(
            '<div class="card tbl"><div class="tbl-head"><h3>%s%s <span class="tn">%s · %s</span>'
            '</h3><span class="sc" style="color:%s">%d / 100</span></div>'
            '<table><colgroup><col style="width:17%%"><col style="width:22%%">'
            '<col style="width:37%%"><col style="width:24%%"></colgroup>'
            '<thead><tr><th>Status</th><th>Check</th><th>Result</th><th>Rule</th></tr></thead>'
            '<tbody>%s</tbody></table></div>'
            % (icon(cic, 16, COL["accent"]), e(simple), e(group), e(tech), score_color(sc), sc,
               "".join(rows)))
    return "".join(out)


def _bots(res):
    bots = res.get("bots") or []
    if not bots:
        return ('<div class="card note">%s<p>No AI crawler information was collected for this '
                'audit.</p></div>' % icon("info", 16, COL["muted"]))
    rows = []
    for b in bots:
        allowed = b.get("robots_allowed")
        robots_cell = yes_no_pill(bool(allowed), "Allowed", "Blocked")
        if b.get("robots_scored"):
            robots_cell += '<span class="ck-tech">Counts towards the score</span>'
        else:
            robots_cell += '<span class="ck-tech">Shown for information</span>'
        if b.get("live_tested"):
            status = b.get("live_status")
            reach = b.get("live_reachable")
            line = ("HTTP %s · %s" % (status, fmt_ms(b.get("live_time")))) if status is not None \
                else ""
            note = b.get("live_note") or ""
            live = yes_no_pill(bool(reach), "Reachable", "Blocked")
            detail = " · ".join(x for x in (line, note) if x)
            if detail:
                live += '<span class="ck-tech">%s</span>' % e(detail)
        else:
            note = b.get("live_note") or ""
            if note == "token only":
                note = "Permission token only, no crawler to test"
            live = ('<span class="pill pill-neutral pill-sm">Not tested</span>'
                    '<span class="ck-tech">%s</span>' % e(note) if note else
                    '<span class="pill pill-neutral pill-sm">Not tested</span>')
        rows.append(
            '<tr><td><span class="ck-name">%s</span><span class="ck-tech mono">%s</span></td>'
            '<td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
            % (e(b.get("label")), e(b.get("token")), e(b.get("company")), e(b.get("purpose")),
               robots_cell, live))
    return (
        '<div class="card tbl"><table><colgroup><col style="width:21%%"><col style="width:13%%">'
        '<col style="width:28%%"><col style="width:18%%"><col style="width:20%%"></colgroup>'
        '<thead><tr><th>Bot</th><th>Company</th><th>Purpose</th><th>robots.txt</th>'
        '<th>Live test</th></tr></thead><tbody>%s</tbody></table></div>'
        '<div class="card note">%s<p>"robots.txt" shows what the site\'s rules say for each bot. '
        '"Live test" shows whether the server actually answered when the page was requested with '
        'that bot\'s name. Sites that check bots by IP address may still let the real bots in.</p>'
        '</div>' % ("".join(rows), icon("info", 16, COL["muted"])))


def _pages(res):
    pages = res.get("pages") or []
    if not pages:
        return ('<div class="card note">%s<p>No pages were crawled in this audit.</p></div>'
                % icon("info", 16, COL["muted"]))
    rows = []
    for i, p in enumerate(pages):
        status = p.get("status")
        st_cls = "ok" if status is not None and status < 300 else (
            "warn" if status is not None and status < 400 else "bad")
        st_html = '<span class="pill pill-%s pill-sm">%s</span>' % (
            st_cls, e(status if status is not None else "–"))
        issues = page_issues(p)
        iss_html = (e(", ".join(issues)) if issues else
                    '<span style="color:%s">None</span>' % COL["ok"])
        path = p.get("path") or p.get("url") or "/"
        tag = '<span class="ck-tech">Main page</span>' if i == 0 else ""
        rows.append(
            '<tr><td><span class="mono">%s</span>%s</td><td>%s</td><td class="num">%s</td>'
            '<td class="num">%s</td><td class="c">%s</td><td class="c">%s</td><td class="c">%s</td>'
            '<td>%s</td></tr>'
            % (e(path), tag, st_html, fmt_secs(p.get("time")), e(p.get("words", 0)),
               icon("check", 14, COL["ok"]) if p.get("title") else icon("x", 14, COL["bad"]),
               icon("check", 14, COL["ok"]) if p.get("meta_desc") else icon("x", 14, COL["bad"]),
               e(p.get("h1", 0)), iss_html))
    note = ""
    if len(pages) == 1:
        note = ('<div class="card note">%s<p>Only the main page was checked. The crawler did not '
                'find other internal pages to visit, so the whole-site checks are shown for '
                'information only.</p></div>' % icon("info", 16, COL["muted"]))
    return (
        '<div class="card tbl"><table><colgroup><col style="width:24%%"><col style="width:9%%">'
        '<col style="width:9%%"><col style="width:9%%"><col style="width:7%%"><col style="width:9%%">'
        '<col style="width:6%%"><col style="width:27%%"></colgroup>'
        '<thead><tr><th>Page</th><th>Status</th><th class="num">Time</th><th class="num">Words</th>'
        '<th class="c">Title</th><th class="c">Descr.</th><th class="c">H1</th><th>Issues</th></tr>'
        '</thead><tbody>%s</tbody></table></div>%s' % ("".join(rows), note))


def _appendix():
    thr_rows = []
    for cid in KEY_THRESHOLDS:
        info = CHECKS.get(cid)
        if not info:
            continue
        thr_rows.append('<tr><td><span class="ck-name">%s</span><span class="ck-tech">%s</span></td>'
                        '<td class="num">%s</td><td class="tx">%s</td></tr>'
                        % (e(info["plain"]), e(info["name"]), e(info["weight"]), e(info["tech"])))
    gl = "".join("<div><dt>%s</dt><dd>%s</dd></div>" % (e(t), e(d)) for t, d in GLOSSARY)
    return (
        '<div class="app-grid">'
        '<div class="card box"><h3>%s How scoring works</h3><ul>'
        '<li>Every check is worth a number of points (its weight).</li>'
        '<li><b>Good</b> (pass) earns the full weight, <b>Could be better</b> (warning) earns half, '
        'and <b>Needs fixing</b> (fail) earns nothing.</li>'
        '<li>Checks marked <b>For your information</b> are not scored.</li></ul>'
        '<div class="formula">score = points earned ÷ points possible × 100</div>'
        '<ul><li>The SEO score uses the SEO checks, the AI readiness score uses the AI checks.</li>'
        '<li>Overall = (SEO score + AI readiness score) ÷ 2.</li></ul></div>'
        '<div class="card box"><h3>%s Grades</h3><ul class="plain">'
        '<li><span class="pill pill-ok pill-sm">90 – 100</span> Excellent</li>'
        '<li><span class="pill pill-ok pill-sm">75 – 89</span> Good</li>'
        '<li><span class="pill pill-warn pill-sm">50 – 74</span> Needs work</li>'
        '<li><span class="pill pill-bad pill-sm">0 – 49</span> Poor</li></ul>'
        '<p class="muted small" style="margin-top:10px">The checks are automatic and look at the '
        'pages as they were at the time of the audit. They follow published guidance from Google '
        'and the AI search providers, but no tool can promise a ranking.</p></div>'
        '</div>'
        '<div class="card tbl" style="margin-top:14px"><div class="tbl-head"><h3>%s Main thresholds'
        '</h3></div><table class="thr"><colgroup><col style="width:30%%"><col style="width:10%%">'
        '<col style="width:60%%"></colgroup><thead><tr><th>Check</th><th class="num">Weight</th>'
        '<th>Rule applied</th></tr></thead><tbody>%s</tbody></table></div>'
        '<div class="card box gloss" style="margin-top:14px"><h3>%s Glossary</h3><dl class="gl">%s</dl>'
        '</div>'
        % (icon("gauge", 16, COL["accent"]), icon("badge", 16, COL["accent"]),
           icon("list", 16, COL["accent"]), "".join(thr_rows), icon("help", 16, COL["accent"]), gl))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def build_report(res):
    """Return a complete standalone HTML document for the audit result `res`."""
    checks = list(res.get("seo") or []) + list(res.get("ai") or [])
    has_shots = bool((res.get("shots") or {}).get("desktop") or (res.get("shots") or {}).get("mobile"))

    plan = [("Score summary", "How the site scores for search engines and AI assistants.",
             lambda: _scores(res, checks), False)]
    if has_shots:
        plan.append(("Screenshots", "How the main page looked to the auditor on a desktop and a "
                     "mobile screen.", lambda: _shots(res), False))
    plan += [
        ("Fix these first", "The issues that cost the most points, in order of impact.",
         lambda: _fixes(checks), False),
        ("Scores by category", "Each bar is the share of available points earned in that area.",
         lambda: _categories(res, checks), False),
        ("All checks", "The full record of every check, its result and the exact rule applied.",
         lambda: _check_tables(res, checks), False),
        ("AI crawler access", "Which search and AI bots the site lets in.",
         lambda: _bots(res), False),
        ("Crawled pages", "The main page and the linked pages visited during the audit.",
         lambda: _pages(res), False),
        ("Appendix", "How the scores are calculated, the main thresholds and the terms used.",
         _appendix, False),
    ]
    toc = [p[0] for p in plan]
    body = [_cover(res, toc)]
    for i, (title, lead, fn, newpage) in enumerate(plan, 1):
        body.append(_section(i, title, e(lead), fn(), newpage=newpage))

    footer = ('<footer><span>Generated by SEO &amp; AI Readiness Auditor – industrial training '
              'project</span><span>%s · %s</span></footer>'
              % (e(res.get("domain")), e(res.get("audited_at"))))

    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>SEO and AI readiness report – %s</title><style>%s</style></head>'
        '<body><main class="page">%s%s</main></body></html>'
        % (e(res.get("domain")), CSS, "".join(body), footer))
