"""
User-interface building blocks for app.py: the page CSS and small functions that return HTML.

Every function here returns a plain HTML string (no Streamlit calls), so app.py stays readable
and the pieces can be tested on their own. All text that comes from the audited website goes
through esc() before it is placed in HTML.

Rules for HTML given to st.markdown(..., unsafe_allow_html=True):
  * no blank lines and no leading indentation (Markdown would turn them into paragraphs or code)
  * no <h1>-<h6> tags (Streamlit adds anchor links to them) - we use <div class="..."> instead
"""

import html
import re
from collections import Counter
from urllib.parse import urlparse

from explanations import AI_CATS, CATEGORIES, CHECKS, SEO_CATS, STATUS_TEXT
from icons import ICONS, STATUS_ICON, icon

# Extra icons used by the app (same Lucide-style 24x24 stroke format as icons.py).
ICONS.setdefault("image-off", '<path d="M2 2l20 20"/><path d="M10.41 10.41a2 2 0 1 1-2.83-2.83"/>'
                              '<path d="M13.5 13.5 6 21"/><path d="m18 12 3 3"/>'
                              '<path d="M3.59 3.59A2 2 0 0 0 3 5v14a2 2 0 0 0 2 2h14c.55 0 1.05-.22 1.41-.59"/>'
                              '<path d="M21 15V5a2 2 0 0 0-2-2H9"/>')
ICONS.setdefault("type", '<path d="M4 7V4h16v3"/><path d="M9 20h6"/><path d="M12 4v16"/>')
ICONS.setdefault("bar-chart", '<path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>')
ICONS.setdefault("minus", '<path d="M5 12h14"/>')
ICONS.setdefault("printer", '<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>'
                            '<path d="M6 9V3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v6"/><rect x="6" y="14" width="12" height="8" rx="1"/>')
ICONS.setdefault("redirect", '<path d="m15 10 5 5-5 5"/><path d="M4 4v7a4 4 0 0 0 4 4h12"/>')
ICONS.setdefault("flag", '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><path d="M4 22v-7"/>')

TONE = {"pass": "ok", "warn": "warn", "fail": "bad", "info": "info"}
COLOR = {"ok": "#059669", "warn": "#d97706", "bad": "#dc2626", "info": "#2563eb", "muted": "#94a3b8"}

# Short, plain descriptions of each category (landing page).
CAT_BLURB = {
    "content": "Page title, Google description, headings, amount of text, image descriptions",
    "tech": "Padlock, phone layout, sitemap, robots.txt, redirects, site icon",
    "speed": "Server response, page size, compression, scripts that hold the page back",
    "security": "Always-secure setting, insecure files, protection headers",
    "social": "Link previews on WhatsApp, LinkedIn and X, rich result labels",
    "links": "Links between your pages, link wording, broken links",
    "site": "Up to 20 linked pages: errors, duplicates, thin pages, speed",
    "ai_access": "Whether ChatGPT, Perplexity and Claude bots are allowed in and actually get in",
    "ai_understand": "Question headings, quotable paragraphs, lists and FAQ labels",
    "ai_trust": "Author and date, sources, About and Contact pages",
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def esc(text):
    """Escape text for HTML."""
    return html.escape("" if text is None else str(text), quote=True)


def md_escape(text):
    """Escape Markdown / LaTeX characters so page text is shown literally by st.markdown."""
    return re.sub(r"([\\`*_{}\[\]<>()#+|~$!])", r"\\\1", str(text))


def trunc(text, n):
    text = text or ""
    return text if len(text) <= n else text[: n - 1].rstrip() + "\u2026"


def tone_of_score(score):
    return "ok" if score >= 75 else ("warn" if score >= 50 else "bad")


def grade_word(score):
    return ("Excellent" if score >= 90 else "Good" if score >= 75 else
            "Needs work" if score >= 50 else "Poor")


def status_word(status, cx=False):
    return STATUS_TEXT.get(status, ("", ""))[1 if cx else 0]


def status_icon(status, size=18):
    tone = TONE.get(status, "info")
    return icon(STATUS_ICON.get(status, "info"), size, COLOR[tone])


def cat_title(cat, cx=False):
    simple, tech, _ = CATEGORIES[cat]
    return tech if cx else simple


def cat_icon(cat):
    return CATEGORIES[cat][2]


def nice_domain(res):
    d = res.get("domain") or ""
    return d[4:] if d.lower().startswith("www.") else d


def favicon_src(res):
    """A usable favicon URL, or '' (some sites use a dummy 'data:,' favicon)."""
    fav = res.get("favicon_url") or ""
    if fav.startswith("data:") and len(fav) < 40:
        return ""
    return fav


def fmt_int(n):
    try:
        return "{:,}".format(int(n))
    except (TypeError, ValueError):
        return str(n)


def all_checks(res):
    return list(res.get("seo", [])) + list(res.get("ai", []))


def lost_points(c):
    return (c.get("weight") or 0) - (c.get("earned") or 0)


def top_issues(res, n=6):
    issues = [c for c in all_checks(res) if c["status"] in ("fail", "warn")]
    issues.sort(key=lambda c: (-lost_points(c), c["status"] != "fail", -c["weight"]))
    return issues[:n]


def top_passes(res, n=6):
    good = [c for c in all_checks(res) if c["status"] == "pass"]
    good.sort(key=lambda c: -c["weight"])
    return good[:n]


def check_counts():
    return Counter(v["cat"] for v in CHECKS.values())


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root{--bg:#ffffff;--surface:#f8fafc;--surface-2:#f1f5f9;--border:#e2e8f0;--text:#0f172a;--muted:#64748b;
--faint:#94a3b8;--accent:#2563eb;--accent-ink:#1d4ed8;--accent-soft:#eff6ff;--ok:#059669;--ok-soft:#ecfdf5;
--warn:#d97706;--warn-soft:#fffbeb;--bad:#dc2626;--bad-soft:#fef2f2;--info:#2563eb;--info-soft:#eff6ff;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;--shadow:0 1px 2px rgba(15,23,42,.05);}
.stApp{background:var(--bg);}
[data-testid="stMainBlockContainer"],.block-container{max-width:1200px;padding-top:2.2rem;padding-bottom:4rem;}
[data-testid="stHeader"]{background:transparent;}
[data-testid="stDecoration"]{display:none;}
.ui,.ui *{box-sizing:border-box;}
.ui{font-family:Inter,-apple-system,"Segoe UI",Roboto,sans-serif;color:var(--text);line-height:1.5;}
.ui .ic{flex:none;vertical-align:middle;}
.mono{font-family:var(--mono);}
/* ---------- Streamlit widgets ---------- */
[data-testid="stForm"]{border:1px solid var(--border);border-radius:14px;background:var(--surface);padding:18px 18px 6px;}
[data-testid="stExpander"] details{border-radius:12px;border-color:var(--border);background:#fff;}
[data-testid="stExpander"] summary p{font-weight:500;}
[data-baseweb="tab-list"]{gap:2px;border-bottom:1px solid var(--border);}
[data-baseweb="tab"]{padding:10px 14px !important;}
[data-baseweb="tab"] p{font-size:15px;font-weight:500;}
[data-baseweb="tab"][aria-selected="true"] p{color:var(--accent-ink);}
[data-baseweb="tab-highlight"]{background:var(--accent) !important;}
[data-baseweb="tab-border"]{display:none;}
[data-testid="stTabs"] [data-baseweb="tab-panel"]{padding-top:18px;}
div[data-testid="stDataFrame"]{border:1px solid var(--border);border-radius:10px;}
/* ---------- App header ---------- */
.apphead{display:flex;align-items:center;gap:14px;}
.apphead .mark{width:44px;height:44px;flex:none;}
.apphead .t{font-size:22px;font-weight:700;letter-spacing:-.01em;line-height:1.2;}
.apphead .s{font-size:14.5px;color:var(--muted);margin-top:2px;}
.examples-label{font-size:13px;color:var(--muted);white-space:nowrap;}
[data-testid="stCheckbox"] label p,[data-testid="stFormSubmitButton"] button p{white-space:nowrap;}
/* ---------- Generic blocks ---------- */
.sec{display:flex;align-items:center;gap:10px;margin:6px 0 12px;}
.sec .sec-ic{width:34px;height:34px;border-radius:9px;background:var(--accent-soft);display:grid;place-items:center;flex:none;}
.sec .sec-t{font-size:18px;font-weight:600;letter-spacing:-.005em;line-height:1.25;}
.sec .sec-s{font-size:13.5px;color:var(--muted);line-height:1.4;}
.sec .sec-right{margin-left:auto;font-size:13px;color:var(--muted);white-space:nowrap;}
.card{background:#fff;border:1px solid var(--border);border-radius:12px;box-shadow:var(--shadow);padding:16px 18px;}
.soft{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 18px;}
.pill{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600;padding:2px 9px;border-radius:999px;white-space:nowrap;line-height:1.6;}
.pill.ok{background:var(--ok-soft);color:var(--ok);} .pill.warn{background:var(--warn-soft);color:#b45309;}
.pill.bad{background:var(--bad-soft);color:var(--bad);} .pill.info{background:var(--info-soft);color:var(--accent-ink);}
.pill.muted{background:var(--surface-2);color:var(--muted);}
.note{font-size:13px;color:var(--muted);}
.empty{padding:22px;text-align:center;color:var(--muted);border:1px dashed var(--border);border-radius:12px;font-size:14px;}
.banner{display:flex;gap:12px;align-items:flex-start;border-radius:12px;padding:14px 16px;border:1px solid;margin:4px 0 14px;}
.banner .b-t{font-weight:600;font-size:15px;}
.banner .b-m{font-size:14px;color:#334155;margin-top:2px;}
.banner.bad{background:var(--bad-soft);border-color:#fecaca;}
.banner.warn{background:var(--warn-soft);border-color:#fde68a;}
.banner.info{background:var(--accent-soft);border-color:#bfdbfe;}
.banner .b-hint{font-size:13px;color:var(--muted);margin-top:6px;}
/* ---------- Landing ---------- */
.land{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:36px;align-items:center;margin:10px 0 30px;}
.land .illu{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:14px;}
.land .illu svg{width:100%;height:auto;display:block;}
.land .lead{font-size:24px;font-weight:700;letter-spacing:-.015em;line-height:1.25;margin-bottom:8px;}
.land .leadp{font-size:15.5px;color:#334155;margin-bottom:18px;}
.steps{display:flex;flex-direction:column;gap:12px;}
.step{display:flex;gap:12px;align-items:flex-start;}
.step .n{width:34px;height:34px;border-radius:10px;border:1px solid var(--border);background:#fff;display:grid;place-items:center;flex:none;box-shadow:var(--shadow);}
.step .st{font-weight:600;font-size:15px;}
.step .sd{font-size:13.5px;color:var(--muted);}
.catgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px;margin-bottom:8px;}
.cattile{display:flex;gap:12px;align-items:flex-start;background:#fff;border:1px solid var(--border);border-radius:12px;padding:14px;box-shadow:var(--shadow);}
.cattile .ci{width:36px;height:36px;border-radius:10px;display:grid;place-items:center;flex:none;background:var(--accent-soft);}
.cattile.ai .ci{background:#f0fdf4;}
.cattile .ct{font-weight:600;font-size:14.5px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;}
.cattile .cd{font-size:13px;color:var(--muted);margin-top:2px;}
.cattile .cn{font-size:12px;font-weight:600;color:var(--faint);margin-top:6px;}
.grouplabel{font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:18px 0 10px;}
@keyframes scan{0%{transform:translateY(0)}100%{transform:translateY(176px)}}
@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}
@keyframes pulse{0%,100%{opacity:.35}50%{opacity:1}}
.illu .scan{animation:scan 3.2s ease-in-out infinite alternate;}
.illu .bot{animation:bob 2.6s ease-in-out infinite;}
.illu .pl{animation:pulse 2.4s ease-in-out infinite;}
.illu .pl2{animation-delay:.8s;} .illu .pl3{animation-delay:1.6s;}
/* ---------- Results header ---------- */
.rhead{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:40px;align-items:center;margin:8px 0 18px;}
.devices{position:relative;padding:0 9% 34px 0;}
.browser{border:1px solid var(--border);border-radius:12px;overflow:hidden;background:#fff;box-shadow:0 1px 2px rgba(15,23,42,.05),0 8px 24px rgba(15,23,42,.06);}
.browser .bar{display:flex;align-items:center;gap:6px;padding:8px 10px;background:var(--surface);border-bottom:1px solid var(--border);}
.browser .bar i{width:9px;height:9px;border-radius:50%;background:#cbd5e1;display:block;flex:none;}
.browser .addr{flex:1;margin-left:8px;display:flex;align-items:center;gap:6px;background:#fff;border:1px solid var(--border);border-radius:999px;padding:2px 10px;font-size:12px;color:var(--muted);overflow:hidden;white-space:nowrap;text-overflow:ellipsis;min-width:0;}
.browser .screen{aspect-ratio:16/10;background:var(--surface-2);overflow:hidden;position:relative;}
.browser .screen img,.phone .pscreen img{width:100%;height:100%;object-fit:cover;object-position:top center;display:block;}
.phone{position:absolute;right:0;bottom:0;width:25%;border:6px solid #0f172a;border-radius:24px;background:#0f172a;overflow:hidden;box-shadow:0 10px 30px rgba(15,23,42,.18);}
.phone .pscreen{aspect-ratio:9/19;background:var(--surface-2);overflow:hidden;border-radius:17px;position:relative;}
.phone .notch{position:absolute;top:4px;left:50%;transform:translateX(-50%);width:34%;height:9px;background:#0f172a;border-radius:6px;z-index:2;}
.ph{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;color:var(--muted);text-align:center;padding:12px;
background-image:radial-gradient(#e2e8f0 1px,transparent 1px);background-size:14px 14px;}
.ph .phd{font-weight:600;color:var(--text);font-size:15px;}
.ph .phs{font-size:12px;}
.ph img{width:36px !important;height:36px !important;object-fit:contain !important;border-radius:8px;background:#fff;}
.shotnote{font-size:12px;color:var(--muted);margin-top:8px;display:flex;align-items:center;gap:6px;}
.siteid{display:flex;align-items:center;gap:12px;margin-bottom:16px;}
.fav{width:40px;height:40px;border-radius:10px;border:1px solid var(--border);background:#fff;display:grid;place-items:center;flex:none;overflow:hidden;position:relative;}
.fav img{width:24px;height:24px;object-fit:contain;position:relative;z-index:1;}
.fav .ic{position:absolute;}
.siteid .dm{font-size:20px;font-weight:700;letter-spacing:-.01em;line-height:1.2;word-break:break-all;}
.siteid .tt{font-size:13.5px;color:var(--muted);line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.rings{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:16px;}
.ring{flex:1;min-width:120px;display:flex;flex-direction:column;align-items:center;text-align:center;padding:12px 8px 10px;border:1px solid var(--border);border-radius:12px;background:#fff;box-shadow:var(--shadow);}
.ring svg{width:112px;height:112px;}
.ring .rv{animation:ringfill 1.4s cubic-bezier(.2,.8,.2,1) both;}
.ring .num{font-size:30px;font-weight:700;fill:var(--text);font-family:Inter,-apple-system,sans-serif;animation:fadein .8s ease .3s both;}
.ring .of{font-size:11px;fill:var(--faint);font-family:Inter,-apple-system,sans-serif;}
.ring .rl{font-weight:600;font-size:14px;margin-top:4px;}
.ring .rg{font-size:12.5px;display:inline-flex;align-items:center;gap:5px;margin-top:2px;}
.ring .rg b{width:7px;height:7px;border-radius:50%;display:inline-block;}
@keyframes ringfill{from{stroke-dashoffset:301.6}}
@keyframes fadein{from{opacity:0}to{opacity:1}}
@keyframes grow{from{width:0}}
@keyframes rise{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.verdict{display:flex;gap:12px;align-items:flex-start;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px;font-size:15px;line-height:1.55;animation:rise .6s ease .4s both;}
.audited{font-size:12.5px;color:var(--muted);margin-top:10px;display:flex;gap:6px;align-items:flex-start;}
.audited .ic{margin-top:2px;}
.audited a{color:var(--muted);text-decoration:underline dotted var(--faint);text-underline-offset:2px;}
.facts{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));border:1px solid var(--border);border-radius:12px;background:#fff;box-shadow:var(--shadow);margin:6px 0 22px;overflow:hidden;}
.fact{padding:12px 14px;border-right:1px solid var(--border);display:flex;gap:10px;align-items:center;}
.fact:last-child{border-right:none;}
.fact .fv{font-size:19px;font-weight:700;line-height:1.1;}
.fact .fl{font-size:12px;color:var(--muted);}
/* ---------- Overview ---------- */
.fixlist{display:flex;flex-direction:column;gap:10px;}
.fix{display:flex;gap:12px;align-items:flex-start;background:#fff;border:1px solid var(--border);border-radius:12px;padding:13px 15px;box-shadow:var(--shadow);animation:rise .4s ease both;}
.fix .fn{width:26px;height:26px;border-radius:8px;display:grid;place-items:center;font-size:13px;font-weight:700;flex:none;}
.fix .fn.bad{background:var(--bad-soft);color:var(--bad);} .fix .fn.warn{background:var(--warn-soft);color:#b45309;}
.fix .ft{font-weight:600;font-size:15px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;}
.fix .fv{font-size:13px;color:var(--muted);margin-top:2px;word-break:break-word;}
.fix .ff{font-size:14px;color:#334155;margin-top:6px;display:flex;gap:7px;align-items:flex-start;}
.fix .ff .ic{margin-top:2px;}
.fix .fp{margin-left:auto;font-size:12px;color:var(--muted);white-space:nowrap;font-family:var(--mono);}
.goodlist{display:flex;flex-direction:column;gap:2px;}
.good{display:flex;gap:10px;align-items:flex-start;padding:8px 2px;border-bottom:1px solid var(--surface-2);font-size:14px;}
.good:last-child{border-bottom:none;}
.good .gv{font-size:12.5px;color:var(--muted);word-break:break-word;}
.cbars{display:flex;flex-direction:column;gap:12px;}
.cbar .top{display:flex;align-items:center;gap:8px;font-size:14px;margin-bottom:5px;}
.cbar .top .sc{margin-left:auto;font-weight:700;font-variant-numeric:tabular-nums;}
.cbar .track{height:8px;background:var(--surface-2);border-radius:999px;overflow:hidden;}
.cbar .fill{height:100%;border-radius:999px;animation:grow 1.1s cubic-bezier(.2,.8,.2,1) both;}
.fill.ok{background:var(--ok);} .fill.warn{background:var(--warn);} .fill.bad{background:var(--bad);}
/* ---------- Check cards ---------- */
.cathead{display:flex;align-items:center;gap:10px;margin:22px 0 10px;padding-bottom:8px;border-bottom:1px solid var(--border);}
.cathead .ci{width:32px;height:32px;border-radius:9px;background:var(--accent-soft);display:grid;place-items:center;flex:none;}
.cathead .ct{font-size:16.5px;font-weight:600;}
.cathead .cs{margin-left:auto;display:flex;gap:8px;align-items:center;font-size:13px;color:var(--muted);}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:12px;}
.chk{display:flex;gap:12px;background:#fff;border:1px solid var(--border);border-radius:12px;padding:14px 16px;box-shadow:var(--shadow);border-left-width:4px;}
.chk.ok{border-left-color:var(--ok);} .chk.warn{border-left-color:var(--warn);} .chk.bad{border-left-color:var(--bad);} .chk.info{border-left-color:var(--accent);}
.chk .cb{flex:1;min-width:0;}
.chk .top{display:flex;gap:8px;align-items:flex-start;justify-content:space-between;}
.chk .nm{font-weight:600;font-size:15px;line-height:1.35;}
.chk .tn{font-family:var(--mono);font-size:12px;color:var(--muted);margin-top:1px;}
.chk .val{font-size:13.5px;margin-top:6px;color:#334155;word-break:break-word;}
.chk .val span{color:var(--muted);}
.chk .why{font-size:13.5px;color:var(--muted);margin-top:6px;}
.chk .fx{display:flex;gap:7px;align-items:flex-start;font-size:13.5px;margin-top:8px;padding:8px 10px;background:var(--surface);border-radius:8px;color:#1e293b;}
.chk .fx .ic{margin-top:2px;}
.chk .tech{margin-top:8px;padding-top:8px;border-top:1px dashed var(--border);font-size:12px;color:var(--muted);}
.chk .tech code{font-family:var(--mono);font-size:11.5px;color:#334155;background:var(--surface-2);padding:1px 5px;border-radius:5px;white-space:normal;}
.chk .pts{font-family:var(--mono);font-size:12px;color:#334155;}
/* ---------- AI bots ---------- */
.geo{display:flex;gap:14px;align-items:flex-start;}
.geo p{margin:0;font-size:15px;line-height:1.6;color:#1e293b;}
.bots{border:1px solid var(--border);border-radius:12px;overflow:hidden;background:#fff;box-shadow:var(--shadow);}
.bothead,.botrow{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr) minmax(0,1fr);gap:12px;align-items:center;padding:11px 16px;}
.bothead{background:var(--surface);font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid var(--border);}
.botrow{border-bottom:1px solid var(--surface-2);}
.botrow:last-child{border-bottom:none;}
.botrow .bn{display:flex;gap:10px;align-items:center;min-width:0;}
.botrow .bn .bi{width:32px;height:32px;border-radius:9px;background:var(--surface-2);display:grid;place-items:center;flex:none;}
.botrow .bt{font-weight:600;font-size:14.5px;}
.botrow .bs{font-size:12.5px;color:var(--muted);}
.yn{display:inline-flex;align-items:center;gap:7px;font-size:13.5px;font-weight:500;}
.yn.yes{color:var(--ok);} .yn.no{color:var(--bad);} .yn.na{color:var(--faint);}
.yn .lbl{display:none;color:var(--muted);font-weight:400;}
/* ---------- Pages crawled ---------- */
.pages{border:1px solid var(--border);border-radius:12px;overflow:hidden;background:#fff;box-shadow:var(--shadow);}
.prow{display:grid;grid-template-columns:72px minmax(0,1.3fr) minmax(0,1.2fr);gap:14px;align-items:center;padding:11px 16px;border-bottom:1px solid var(--surface-2);}
.prow:last-child{border-bottom:none;}
.prow .pp{font-family:var(--mono);font-size:13px;word-break:break-all;}
.prow .pp a{color:var(--text);text-decoration:none;}
.prow .pt{font-size:12.5px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.prow .pb{display:flex;gap:6px;flex-wrap:wrap;}
.code{display:inline-block;min-width:44px;text-align:center;font-family:var(--mono);font-size:12.5px;font-weight:600;padding:2px 8px;border-radius:7px;}
.code.ok{background:var(--ok-soft);color:var(--ok);} .code.bad{background:var(--bad-soft);color:var(--bad);} .code.warn{background:var(--warn-soft);color:#b45309;}
/* ---------- Page details ---------- */
.serp{font-family:Arial,Helvetica,sans-serif;background:#fff;border:1px solid var(--border);border-radius:12px;padding:16px 18px;box-shadow:var(--shadow);}
.serp .sh{display:flex;gap:10px;align-items:center;margin-bottom:6px;}
.serp .sf{width:28px;height:28px;border-radius:50%;background:#f1f3f4;display:grid;place-items:center;overflow:hidden;flex:none;position:relative;}
.serp .sf img{width:18px;height:18px;object-fit:contain;position:relative;z-index:1;}
.serp .sf .ic{position:absolute;}
.serp .sn{font-size:14px;color:#202124;line-height:1.2;}
.serp .su{font-size:12px;color:#4d5156;line-height:1.3;word-break:break-all;}
.serp .stt{font-size:20px;color:#1a0dab;line-height:1.3;margin:2px 0 4px;}
.serp .sd{font-size:14px;color:#4d5156;line-height:1.58;}
.serp .sd.miss{color:#b45309;font-style:italic;}
.share{max-width:520px;border:1px solid var(--border);border-radius:12px;overflow:hidden;background:#fff;box-shadow:var(--shadow);}
.share .si{aspect-ratio:1.91/1;background:var(--surface-2);overflow:hidden;position:relative;}
.share .si img{width:100%;height:100%;object-fit:cover;display:block;position:relative;z-index:1;}
.share .si .ph{z-index:0;}
.share .sb{padding:10px 14px 12px;background:#f8fafc;border-top:1px solid var(--border);}
.share .sdm{font-size:11.5px;text-transform:uppercase;color:var(--muted);letter-spacing:.03em;}
.share .stt{font-weight:600;font-size:15px;line-height:1.3;margin-top:2px;}
.share .sds{font-size:13px;color:var(--muted);line-height:1.4;margin-top:2px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.lenrow{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;}
.shotbig{border:1px solid var(--border);border-radius:12px;overflow:hidden;background:#fff;box-shadow:var(--shadow);}
.shotbig .bar{display:flex;align-items:center;gap:6px;padding:8px 10px;background:var(--surface);border-bottom:1px solid var(--border);font-size:12px;color:var(--muted);}
.shotbig img{width:100%;display:block;}
.shotphone{border:7px solid #0f172a;border-radius:28px;overflow:hidden;background:#0f172a;max-width:260px;margin:0 auto;box-shadow:0 10px 30px rgba(15,23,42,.16);}
.shotphone img{width:100%;display:block;border-radius:20px;}
.gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;}
.gi{border:1px solid var(--border);border-radius:10px;overflow:hidden;background:#fff;display:flex;flex-direction:column;box-shadow:var(--shadow);}
.gi .gimg{aspect-ratio:4/3;background:var(--surface-2);position:relative;overflow:hidden;display:block;}
.gi .gimg img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:1;}
.gi .gimg .gph{position:absolute;inset:0;display:grid;place-items:center;z-index:0;}
.gi .gb{padding:7px 9px 9px;display:flex;flex-direction:column;gap:4px;}
.gi .ga{font-size:12px;color:#334155;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;word-break:break-word;}
.gi .ga.miss{color:var(--faint);font-style:italic;}
.gi .gx{font-size:11px;color:var(--muted);font-family:var(--mono);}
.outline{border:1px solid var(--border);border-radius:12px;background:#fff;padding:8px 0;box-shadow:var(--shadow);max-height:520px;overflow:auto;}
.hl{display:flex;gap:10px;align-items:baseline;padding:4px 16px;font-size:14px;line-height:1.4;}
.hl .lv{font-family:var(--mono);font-size:11px;font-weight:600;padding:1px 6px;border-radius:5px;background:var(--surface-2);color:var(--muted);flex:none;}
.hl.h1 .lv{background:var(--accent-soft);color:var(--accent-ink);}
.hl.h1{font-weight:600;}
.hl .em{color:var(--faint);font-style:italic;}
.kv{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:6px 16px;font-size:13.5px;}
.kv .k{color:var(--muted);}
.kv .v{word-break:break-all;}
.chain{display:flex;flex-direction:column;gap:6px;font-size:13px;}
.chain .cl{display:flex;gap:8px;align-items:center;font-family:var(--mono);word-break:break-all;}
.reportcard{display:flex;gap:16px;align-items:flex-start;}
/* ---------- Responsive ---------- */
@media (max-width: 1000px){
.rhead,.land{grid-template-columns:minmax(0,1fr);gap:24px;}
.facts{grid-template-columns:repeat(3,minmax(0,1fr));}
.fact:nth-child(3){border-right:none;}
.fact:nth-child(-n+3){border-bottom:1px solid var(--border);}
}
@media (max-width: 640px){
[data-testid="stMainBlockContainer"],.block-container{padding-left:16px;padding-right:16px;padding-top:1.4rem;}
.apphead .t{font-size:18px;} .apphead .s{font-size:13px;}
.cards{grid-template-columns:minmax(0,1fr);}
.facts{grid-template-columns:repeat(2,minmax(0,1fr));}
.fact{border-right:none !important;border-bottom:1px solid var(--border);}
.fact:nth-child(odd){border-right:1px solid var(--border) !important;}
.ring{min-width:92px;padding:10px 4px;} .ring svg{width:86px;height:86px;}
.bothead{display:none;}
.botrow{grid-template-columns:minmax(0,1fr);gap:6px;}
.yn .lbl{display:inline;}
.prow{grid-template-columns:60px minmax(0,1fr);}
.prow .pb{grid-column:1 / -1;}
.land .lead{font-size:20px;}
.fix .fp{display:none;}
.cathead{flex-wrap:wrap;}
}
@media (prefers-reduced-motion: reduce){
.ring .rv,.ring .num,.cbar .fill,.fix,.verdict,.illu .scan,.illu .bot,.illu .pl{animation:none !important;}
}
</style>"""


# ---------------------------------------------------------------------------
# Header and landing
# ---------------------------------------------------------------------------
LOGO = ('<svg class="mark" viewBox="0 0 44 44" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
        '<rect width="44" height="44" rx="11" fill="#2563eb"/>'
        '<rect x="11" y="24" width="4" height="8" rx="1.5" fill="#bfdbfe"/>'
        '<rect x="17" y="19" width="4" height="13" rx="1.5" fill="#dbeafe"/>'
        '<rect x="23" y="14" width="4" height="18" rx="1.5" fill="#ffffff"/>'
        '<circle cx="29" cy="25" r="6.5" fill="none" stroke="#ffffff" stroke-width="2.6"/>'
        '<path d="M33.8 29.8 37 33" stroke="#ffffff" stroke-width="2.8" stroke-linecap="round"/>'
        '</svg>')


def app_header():
    return ('<div class="ui apphead">%s<div><div class="t">SEO &amp; AI Readiness Auditor</div>'
            '<div class="s">Checks how easily a website can be found on Google and understood by '
            'AI assistants such as ChatGPT, Perplexity and Claude.</div></div></div>' % LOGO)


def section(title, sub="", icon_name=None, right=""):
    ic = ('<div class="sec-ic">%s</div>' % icon(icon_name, 18, "#2563eb")) if icon_name else ""
    return ('<div class="ui sec">%s<div><div class="sec-t">%s</div>%s</div>%s</div>'
            % (ic, esc(title), ('<div class="sec-s">%s</div>' % esc(sub)) if sub else "",
               ('<div class="sec-right">%s</div>' % right) if right else ""))


def banner(kind, title, message, hint="", icon_name=None):
    icon_name = icon_name or {"bad": "x-circle", "warn": "alert", "info": "info"}[kind]
    return ('<div class="ui banner %s">%s<div><div class="b-t">%s</div><div class="b-m">%s</div>%s</div></div>'
            % (kind, icon(icon_name, 22, COLOR.get(kind, COLOR["info"])), esc(title), esc(message),
               ('<div class="b-hint">%s</div>' % esc(hint)) if hint else ""))


ILLUSTRATION = (
    '<svg viewBox="0 0 520 330" xmlns="http://www.w3.org/2000/svg" role="img" '
    'aria-label="A browser window being scanned by a small robot, with linked pages on the right">'
    # linked pages graph
    '<g stroke="#cbd5e1" stroke-width="1.6" stroke-dasharray="4 4" fill="none">'
    '<path d="M352 96 C380 96 392 70 418 64"/><path d="M430 78 L392 140"/><path d="M438 78 L470 140"/>'
    '<path d="M386 166 L360 224"/><path d="M392 166 L414 224"/><path d="M472 166 L478 224"/></g>'
    '<g font-family="Inter,Arial,sans-serif">'
    '<circle cx="432" cy="62" r="17" fill="#fff" stroke="#2563eb" stroke-width="2"/>'
    '<path d="M426 56h12M426 62h12M426 68h8" stroke="#2563eb" stroke-width="2" stroke-linecap="round"/>'
    '<circle cx="388" cy="152" r="15" fill="#fff" stroke="#e2e8f0" stroke-width="2"/>'
    '<path d="M382 152l4 4 8-8" stroke="#059669" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    '<circle cx="472" cy="152" r="15" fill="#fff" stroke="#e2e8f0" stroke-width="2"/>'
    '<path d="M466 152l4 4 8-8" stroke="#059669" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    '<circle cx="358" cy="238" r="14" fill="#fff" stroke="#e2e8f0" stroke-width="2"/>'
    '<path d="M358 232v7M358 243.5v.5" stroke="#d97706" stroke-width="2.4" stroke-linecap="round"/>'
    '<circle cx="416" cy="238" r="14" fill="#fff" stroke="#e2e8f0" stroke-width="2"/>'
    '<path d="M410 238l4 4 8-8" stroke="#059669" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    '<circle cx="478" cy="238" r="14" fill="#fff" stroke="#e2e8f0" stroke-width="2"/>'
    '<path d="M473 233l10 10M483 233l-10 10" stroke="#dc2626" stroke-width="2.4" stroke-linecap="round"/>'
    '<circle class="pl" cx="432" cy="62" r="23" fill="none" stroke="#93c5fd" stroke-width="1.5"/>'
    '<circle class="pl pl2" cx="388" cy="152" r="21" fill="none" stroke="#a7f3d0" stroke-width="1.5"/>'
    '<circle class="pl pl3" cx="472" cy="152" r="21" fill="none" stroke="#a7f3d0" stroke-width="1.5"/>'
    '</g>'
    # browser window
    '<rect x="16" y="22" width="336" height="254" rx="12" fill="#fff" stroke="#e2e8f0" stroke-width="1.5"/>'
    '<path d="M16 34a12 12 0 0 1 12-12h312a12 12 0 0 1 12 12v18H16z" fill="#f8fafc"/>'
    '<line x1="16" y1="52" x2="352" y2="52" stroke="#e2e8f0" stroke-width="1.5"/>'
    '<circle cx="34" cy="37" r="4" fill="#cbd5e1"/><circle cx="47" cy="37" r="4" fill="#cbd5e1"/>'
    '<circle cx="60" cy="37" r="4" fill="#cbd5e1"/>'
    '<rect x="78" y="29" width="200" height="16" rx="8" fill="#fff" stroke="#e2e8f0"/>'
    '<rect x="88" y="35" width="70" height="4" rx="2" fill="#cbd5e1"/>'
    # page content
    '<rect x="36" y="72" width="140" height="11" rx="5" fill="#0f172a" opacity=".85"/>'
    '<rect x="36" y="92" width="150" height="6" rx="3" fill="#cbd5e1"/>'
    '<rect x="36" y="104" width="128" height="6" rx="3" fill="#cbd5e1"/>'
    '<rect x="36" y="116" width="140" height="6" rx="3" fill="#cbd5e1"/>'
    '<rect x="36" y="134" width="64" height="18" rx="9" fill="#2563eb"/>'
    '<rect x="200" y="70" width="132" height="84" rx="9" fill="#eff6ff"/>'
    '<path d="M210 144l30-34 22 22 14-12 46 24z" fill="#bfdbfe"/><circle cx="300" cy="92" r="9" fill="#dbeafe"/>'
    '<rect x="36" y="172" width="92" height="82" rx="9" fill="#f8fafc" stroke="#e2e8f0"/>'
    '<rect x="138" y="172" width="92" height="82" rx="9" fill="#f8fafc" stroke="#e2e8f0"/>'
    '<rect x="240" y="172" width="92" height="82" rx="9" fill="#f8fafc" stroke="#e2e8f0"/>'
    '<rect x="48" y="186" width="56" height="6" rx="3" fill="#94a3b8"/><rect x="48" y="200" width="68" height="5" rx="2.5" fill="#e2e8f0"/>'
    '<rect x="48" y="211" width="60" height="5" rx="2.5" fill="#e2e8f0"/>'
    '<rect x="150" y="186" width="56" height="6" rx="3" fill="#94a3b8"/><rect x="150" y="200" width="68" height="5" rx="2.5" fill="#e2e8f0"/>'
    '<rect x="150" y="211" width="60" height="5" rx="2.5" fill="#e2e8f0"/>'
    '<rect x="252" y="186" width="56" height="6" rx="3" fill="#94a3b8"/><rect x="252" y="200" width="68" height="5" rx="2.5" fill="#e2e8f0"/>'
    '<rect x="252" y="211" width="60" height="5" rx="2.5" fill="#e2e8f0"/>'
    # scan line
    '<g class="scan"><rect x="24" y="64" width="320" height="2" rx="1" fill="#2563eb" opacity=".55"/>'
    '<rect x="24" y="66" width="320" height="16" fill="#2563eb" opacity=".05"/></g>'
    # robot
    '<g transform="translate(-34 0)"><g class="bot">'
    '<line x1="290" y1="246" x2="290" y2="234" stroke="#0f172a" stroke-width="2.4" stroke-linecap="round"/>'
    '<circle cx="290" cy="231" r="4" fill="#2563eb"/>'
    '<rect x="262" y="246" width="56" height="44" rx="12" fill="#0f172a"/>'
    '<rect x="270" y="256" width="40" height="22" rx="8" fill="#1e293b"/>'
    '<circle cx="282" cy="267" r="4" fill="#93c5fd"/><circle cx="298" cy="267" r="4" fill="#93c5fd"/>'
    '<rect x="256" y="262" width="6" height="12" rx="3" fill="#0f172a"/><rect x="318" y="262" width="6" height="12" rx="3" fill="#0f172a"/>'
    '<circle cx="342" cy="252" r="13" fill="#ffffff" fill-opacity=".7" stroke="#0f172a" stroke-width="3"/>'
    '<path d="M332 262l-9 9" stroke="#0f172a" stroke-width="3.4" stroke-linecap="round"/>'
    '</g></g>'
    '</svg>')


def landing(counts):
    steps = [
        ("globe", "Enter a website address", "Any public page works, for example your college website."),
        ("search", "We visit it like Google and AI bots do",
         "The tool opens the page, reads its hidden files and follows links to more pages."),
        ("list", "56 checks are scored", "Each one is marked Good, Could be better or Needs fixing."),
        ("bulb", "You get a simple to-do list", "Plain explanations, screenshots and a report you can download."),
    ]
    st_html = "".join(
        '<div class="step"><div class="n">%s</div><div><div class="st">%s</div><div class="sd">%s</div></div></div>'
        % (icon(ic, 18, "#2563eb"), esc(t), esc(d)) for ic, t, d in steps)
    head = ('<div class="ui land"><div class="illu">%s</div><div>'
            '<div class="lead">See your website the way search engines and AI assistants see it</div>'
            '<div class="leadp">Google decides who shows up in search results. ChatGPT, Perplexity and '
            'Claude decide which sites they quote. Both depend on the same simple things: can they '
            'get in, can they read the page, and can they trust it.</div>'
            '<div class="steps">%s</div></div></div>' % (ILLUSTRATION, st_html))

    def tiles(cats, ai=False):
        out = []
        for cat in cats:
            simple, _tech, ic = CATEGORIES[cat]
            out.append('<div class="cattile%s"><div class="ci">%s</div><div><div class="ct">%s</div>'
                       '<div class="cd">%s</div><div class="cn">%d checks</div></div></div>'
                       % (" ai" if ai else "", icon(ic, 18, "#059669" if ai else "#2563eb"),
                          esc(simple), esc(CAT_BLURB.get(cat, "")), counts.get(cat, 0)))
        return "".join(out)

    n_seo = sum(counts.get(c, 0) for c in SEO_CATS)
    n_ai = sum(counts.get(c, 0) for c in AI_CATS)
    body = ('<div class="ui">%s<div class="grouplabel">For Google search &middot; %d checks</div>'
            '<div class="catgrid">%s</div><div class="grouplabel">For AI assistants &middot; %d checks</div>'
            '<div class="catgrid">%s</div></div>'
            % (section("What gets checked", "Every check is explained in everyday words.", "list"),
               n_seo, tiles(SEO_CATS), n_ai, tiles(AI_CATS, True)))
    return head, body


# ---------------------------------------------------------------------------
# Results header
# ---------------------------------------------------------------------------
def _fav_img(res, size=24):
    src = favicon_src(res)
    globe = icon("globe", min(size, 20), "#94a3b8")
    if not src:
        return globe
    return '%s<img src="%s" alt="" referrerpolicy="no-referrer" loading="lazy">' % (globe, esc(src))


def _placeholder(res, small=False):
    src = favicon_src(res)
    fav = ('<img src="%s" alt="" referrerpolicy="no-referrer">' % esc(src)) if src else icon("globe", 30, "#94a3b8")
    if small:
        return '<div class="ph">%s</div>' % fav
    return ('<div class="ph">%s<div class="phd">%s</div><div class="phs">No screenshot available</div></div>'
            % (fav, esc(nice_domain(res))))


def device_frames(res):
    shots = res.get("shots") or {}
    desk, mob = shots.get("desktop"), shots.get("mobile")
    og_img = (res.get("og") or {}).get("og:image") or ""
    note = ""
    if desk:
        screen = '<img src="data:image/jpeg;base64,%s" alt="Desktop screenshot">' % desk
    elif og_img:
        screen = ('<div class="ph" style="z-index:0">%s</div><img src="%s" alt="" referrerpolicy="no-referrer" '
                  'style="position:relative;z-index:1;object-position:center">' % (icon("image", 28, "#94a3b8"), esc(og_img)))
        note = "Screenshot not available, showing the site's own preview image instead."
    else:
        screen = _placeholder(res)
        note = shots.get("error") or "Screenshots were not captured."
    if mob:
        pscreen = '<img src="data:image/jpeg;base64,%s" alt="Mobile screenshot">' % mob
    else:
        pscreen = _placeholder(res, small=True)
    addr = esc(trunc(res.get("final_url", ""), 70))
    lock = icon("lock" if str(res.get("final_url", "")).startswith("https") else "alert", 11, "#94a3b8")
    out = ('<div class="devices"><div class="browser"><div class="bar"><i></i><i></i><i></i>'
           '<div class="addr">%s<span>%s</span></div></div><div class="screen">%s</div></div>'
           '<div class="phone"><div class="notch"></div><div class="pscreen">%s</div></div></div>'
           % (lock, addr, screen, pscreen))
    if note:
        out += '<div class="shotnote">%s%s</div>' % (icon("info", 13, "#94a3b8"), esc(note))
    return out


def score_ring(score, label, delay=0.0):
    r = 48
    circ = 2 * 3.14159265 * r  # 301.6
    off = circ * (1 - max(0, min(100, score)) / 100.0)
    tone = tone_of_score(score)
    col = COLOR[tone]
    return ('<div class="ring"><svg viewBox="0 0 112 112" aria-label="%s: %d out of 100">'
            '<circle cx="56" cy="56" r="%d" fill="none" stroke="#eef2f7" stroke-width="9"/>'
            '<circle class="rv" cx="56" cy="56" r="%d" fill="none" stroke="%s" stroke-width="9" '
            'stroke-linecap="round" transform="rotate(-90 56 56)" stroke-dasharray="%.1f" '
            'style="stroke-dashoffset:%.1f;animation-delay:%.2fs"/>'
            '<text class="num" x="56" y="60" text-anchor="middle" style="animation-delay:%.2fs">%d</text>'
            '<text class="of" x="56" y="77" text-anchor="middle">of 100</text></svg>'
            '<div class="rl">%s</div><div class="rg" style="color:%s"><b style="background:%s"></b>%s</div></div>'
            % (esc(label), score, r, r, col, circ, off, delay, delay + 0.3, score, esc(label), col, col,
               grade_word(score)))


def verdict_text(res):
    seo, ai = res.get("seo_score", 0), res.get("ai_score", 0)

    def phrase(s):
        if s >= 90:
            return "in excellent shape"
        if s >= 75:
            return "in good shape"
        if s >= 50:
            return "only partly ready"
        return "poorly prepared"

    same_side = (seo >= 75) == (ai >= 75)
    p_seo, p_ai = phrase(seo), phrase(ai)
    if p_seo == p_ai:
        first = "This site is %s for both Google and AI assistants." % p_seo
    else:
        first = "This site is %s for Google %s %s for AI assistants." % (
            p_seo, "and" if same_side else "but", p_ai)
    issues = top_issues(res, 1)
    if not issues:
        return first + " None of the checks found a problem."
    top = issues[0]
    n_fail = sum(1 for c in all_checks(res) if c["status"] == "fail")
    n_warn = sum(1 for c in all_checks(res) if c["status"] == "warn")
    counts = []
    if n_fail:
        counts.append("%d %s fixing" % (n_fail, "thing needs" if n_fail == 1 else "things need"))
    if n_warn:
        counts.append("%d could be better" % n_warn)
    return "%s %s. The most important one: <b>%s</b>. %s" % (
        esc(first), esc(" and ".join(counts)).capitalize(), esc(top["plain"]), esc(top["fix"]))


def results_header(res, cx=False):
    labels = (("SEO score", "AI readiness (GEO)", "Overall") if cx
              else ("Google search", "AI assistants", "Overall"))
    rings = (score_ring(res.get("seo_score", 0), labels[0], 0.0)
             + score_ring(res.get("ai_score", 0), labels[1], 0.15)
             + score_ring(res.get("overall", 0), labels[2], 0.3))
    title = res.get("title") or "(this page has no title)"
    final = res.get("final_url", "")
    right = ('<div class="siteid"><div class="fav">%s</div><div style="min-width:0"><div class="dm">%s</div>'
             '<div class="tt">%s</div></div></div><div class="rings">%s</div>'
             '<div class="verdict">%s<div>%s</div></div>'
             '<div class="audited">%s<span>Checked <a href="%s" target="_blank" rel="noopener noreferrer">%s</a>'
             ' on %s</span></div>'
             % (_fav_img(res), esc(nice_domain(res)), esc(title), rings, icon("info", 20, "#2563eb"),
                verdict_text(res), icon("clock", 13, "#94a3b8"), esc(final), esc(trunc(final, 60)),
                esc(res.get("audited_at", ""))))
    return '<div class="ui rhead"><div>%s</div><div>%s</div></div>' % (device_frames(res), right)


def facts_row(res):
    checks = all_checks(res)
    issues = sum(1 for c in checks if c["status"] in ("fail", "warn"))
    items = [
        ("sitemap", fmt_int(len(res.get("pages", []))), "pages checked"),
        ("clock", "%.0f s" % (res.get("duration") or 0), "time taken"),
        ("type", fmt_int(res.get("word_count", 0)), "words on the page"),
        ("image", fmt_int(len(res.get("images", []))), "images"),
        ("link", fmt_int(len(res.get("internal", [])) + len(res.get("external", []))), "links"),
        ("alert", fmt_int(issues), "issues found"),
    ]
    out = "".join('<div class="fact">%s<div><div class="fv">%s</div><div class="fl">%s</div></div></div>'
                  % (icon(ic, 20, "#d97706" if ic == "alert" and issues else "#64748b"), esc(v), esc(l))
                  for ic, v, l in items)
    return '<div class="ui facts">%s</div>' % out


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
def fix_list(issues, cx=False):
    if not issues:
        return '<div class="ui empty">%s<div style="margin-top:6px">No problems found in any check.</div></div>' % icon(
            "check-circle", 26, COLOR["ok"])
    out = []
    for i, c in enumerate(issues, 1):
        tone = TONE[c["status"]]
        pts = ('<div class="fp">-%g pts</div>' % lost_points(c)) if cx else ""
        name = esc(c["name"] if cx else c["plain"])
        out.append('<div class="fix" style="animation-delay:%.2fs"><div class="fn %s">%d</div><div style="min-width:0;flex:1">'
                   '<div class="ft">%s<span class="pill %s">%s</span></div><div class="fv">%s</div>'
                   '<div class="ff">%s<span>%s</span></div></div>%s</div>'
                   % (0.05 * i, tone, i, name, tone, esc(status_word(c["status"], cx)),
                      esc(trunc(str(c["value"]), 160)), icon("bulb", 15, "#d97706"), esc(c["fix"]), pts))
    return '<div class="ui fixlist">%s</div>' % "".join(out)


def good_list(passes, cx=False):
    if not passes:
        return '<div class="ui empty">Nothing passed yet.</div>'
    out = "".join('<div class="good">%s<div><div>%s</div><div class="gv">%s</div></div></div>'
                  % (icon("check-circle", 17, COLOR["ok"]), esc(c["name"] if cx else c["plain"]),
                     esc(trunc(str(c["value"]), 110))) for c in passes)
    return '<div class="ui card goodlist" style="padding:6px 16px">%s</div>' % out


def cat_bars(res, cats, cx=False):
    scores = res.get("cat_scores", {})
    out = []
    for i, cat in enumerate(cats):
        sc = scores.get(cat, 0)
        tone = tone_of_score(sc)
        out.append('<div class="cbar"><div class="top">%s<span>%s</span><span class="sc" style="color:%s">%d</span></div>'
                   '<div class="track"><div class="fill %s" style="width:%d%%;animation-delay:%.2fs"></div></div></div>'
                   % (icon(cat_icon(cat), 16, "#64748b"), esc(cat_title(cat, cx)), COLOR[tone], sc, tone,
                      max(sc, 2), 0.06 * i))
    return '<div class="cbars">%s</div>' % "".join(out)


# ---------------------------------------------------------------------------
# Check cards
# ---------------------------------------------------------------------------
def check_card(c, cx=False):
    tone = TONE.get(c["status"], "info")
    tn = ('<div class="tn">%s</div>' % esc(c["name"])) if cx else ""
    fix = ""
    if c["status"] in ("fail", "warn"):
        fix = '<div class="fx">%s<span>%s</span></div>' % (icon("bulb", 15, "#d97706"), esc(c["fix"]))
    tech = ""
    if cx:
        if c["status"] == "info" or not c.get("weight"):
            pts = "not scored"
        else:
            pts = "weight %g &rarr; earned %g" % (c["weight"], c.get("earned", 0))
        tech = ('<div class="tech"><span class="pts">%s</span> &middot; rule: <code>%s</code></div>'
                % (pts, esc(c["tech"])))
    return ('<div class="chk %s">%s<div class="cb"><div class="top"><div><div class="nm">%s</div>%s</div>'
            '<span class="pill %s">%s</span></div><div class="val"><span>%s</span> %s</div>'
            '<div class="why">%s</div>%s%s</div></div>'
            % (tone, status_icon(c["status"], 20), esc(c["plain"]), tn, tone,
               esc(status_word(c["status"], cx)), "Found:" if not cx else "Value:",
               esc(trunc(str(c["value"]), 300)), esc(c["why"]), fix, tech))


def cat_header(cat, score, checks, cx=False):
    probs = sum(1 for c in checks if c["status"] in ("fail", "warn"))
    tone = tone_of_score(score)
    right = ('<span class="pill %s">%s</span><span>%s</span>'
             % ("ok" if not probs else "warn", "All good" if not probs else
                "%d to look at" % probs, ("score %d/100" % score)))
    return ('<div class="ui cathead"><div class="ci">%s</div><div class="ct">%s</div><div class="cs">%s</div></div>'
            % (icon(cat_icon(cat), 17, "#2563eb"), esc(cat_title(cat, cx)), right)).replace(
        "score %d/100" % score, '<b style="color:%s">%d</b>/100' % (COLOR[tone], score))


def cards(checks, cx=False):
    return '<div class="ui cards">%s</div>' % "".join(check_card(c, cx) for c in checks)


# ---------------------------------------------------------------------------
# AI bots
# ---------------------------------------------------------------------------
GEO_TEXT = ("<b>GEO (Generative Engine Optimisation)</b> means preparing a website so AI assistants "
            "can use it. When someone asks ChatGPT, Perplexity, Claude or Google's AI Overviews a "
            "question, the assistant looks up a few web pages and quotes the ones it can reach, "
            "read and trust. This tab checks those three things.")


def _yn(state, yes_text, no_text, na_text, label):
    if state is None:
        return '<span class="yn na">%s<span><span class="lbl">%s: </span>%s</span></span>' % (
            icon("minus", 16, "#94a3b8"), esc(label), esc(na_text))
    if state:
        return '<span class="yn yes">%s<span><span class="lbl">%s: </span>%s</span></span>' % (
            icon("check-circle", 17, COLOR["ok"]), esc(label), esc(yes_text))
    return '<span class="yn no">%s<span><span class="lbl">%s: </span>%s</span></span>' % (
        icon("x-circle", 17, COLOR["bad"]), esc(label), esc(no_text))


def bot_table(bots):
    head = ('<div class="bothead"><div>Assistant or bot</div><div>Allowed by the site\'s rules</div>'
            '<div>Got in when we knocked</div></div>')
    rows = []
    for b in bots:
        live = b.get("live_reachable") if b.get("live_tested") else None
        rows.append('<div class="botrow"><div class="bn"><div class="bi">%s</div><div style="min-width:0">'
                    '<div class="bt">%s</div><div class="bs">%s &middot; %s</div></div></div><div>%s</div><div>%s</div></div>'
                    % (icon("bot", 17, "#64748b"), esc(b["label"]), esc(b["company"]), esc(b["purpose"]),
                       _yn(b.get("robots_allowed"), "Yes", "No, blocked", "Unknown", "Rules"),
                       _yn(live, "Yes", "No, turned away", "Not tested (name only)", "Live test")))
    return '<div class="ui bots">%s%s</div>' % (head, "".join(rows))


# ---------------------------------------------------------------------------
# Pages crawled
# ---------------------------------------------------------------------------
def page_problems(p):
    """-> list of (tone, text) for one crawled page."""
    out = []
    err = p.get("error") or ""
    status = p.get("status")
    if err.startswith("Not an HTML"):
        return [("muted", "Not a web page (file)")]
    if p.get("blocked"):
        return [("muted", "Refused our crawler, so not checked")]
    if err:
        out.append(("bad", "Could not open (%s)" % err))
        return out
    if status and status >= 400:
        out.append(("bad", "Error %s" % status))
        return out
    if not p.get("title"):
        out.append(("bad", "No title"))
    if not p.get("meta_desc"):
        out.append(("warn", "No description"))
    if p.get("h1", 0) == 0:
        out.append(("warn", "No main heading"))
    elif p.get("h1", 0) > 1:
        out.append(("warn", "%d main headings" % p["h1"]))
    if (p.get("words") or 0) < 250:
        out.append(("warn", "Very little text (%d words)" % (p.get("words") or 0)))
    if (p.get("time") or 0) > 1.5:
        out.append(("warn", "Slow (%.1f s)" % p["time"]))
    if p.get("noindex"):
        out.append(("bad", "Hidden from Google"))
    if p.get("imgs_no_alt"):
        out.append(("warn", "%d image%s without description" % (p["imgs_no_alt"], "" if p["imgs_no_alt"] == 1 else "s")))
    return out


def page_list(pages):
    rows = []
    for p in pages:
        status = p.get("status")
        probs = page_problems(p)
        code_tone = "ok" if status and status < 400 and not p.get("error") else (
            "warn" if p.get("blocked") or (p.get("error") or "").startswith("Not an HTML") else "bad")
        chips = "".join('<span class="pill %s">%s</span>' % (t, esc(x)) for t, x in probs) or (
            '<span class="pill ok">%sNo problems</span>' % icon("check", 12, COLOR["ok"]))
        rows.append('<div class="prow"><div><span class="code %s">%s</span></div><div style="min-width:0">'
                    '<div class="pp"><a href="%s" target="_blank" rel="noopener noreferrer">%s</a></div>'
                    '<div class="pt">%s</div></div><div class="pb">%s</div></div>'
                    % (code_tone, esc(status or "ERR"), esc(p.get("url", "")), esc(trunc(p.get("path", "/"), 80)),
                       esc(p.get("title") or "(no title)"), chips))
    return '<div class="ui pages">%s</div>' % "".join(rows)


# ---------------------------------------------------------------------------
# Page details
# ---------------------------------------------------------------------------
def _breadcrumb(url):
    p = urlparse(url)
    parts = [x for x in (p.path or "").split("/") if x][:3]
    return " \u203a ".join(["%s://%s" % (p.scheme, p.netloc)] + parts)


def google_preview(res):
    title = res.get("title") or ""
    desc = res.get("meta_desc") or ""
    name = (res.get("og") or {}).get("og:site_name") or nice_domain(res)
    t = esc(trunc(title, 60)) if title else "(no title, Google will make one up)"
    d = ('<div class="sd">%s</div>' % esc(trunc(desc, 160))) if desc else (
        '<div class="sd miss">No description set, so Google will pick some text from the page.</div>')
    box = ('<div class="serp"><div class="sh"><div class="sf">%s</div><div style="min-width:0"><div class="sn">%s</div>'
           '<div class="su">%s</div></div></div><div class="stt">%s</div>%s</div>'
           % (_fav_img(res, 18), esc(name), esc(_breadcrumb(res.get("final_url", ""))), t, d))
    tl, dl = len(title), len(desc)
    chips = ('<div class="lenrow"><span class="pill %s">Title: %d characters (best 30 to 60)</span>'
             '<span class="pill %s">Description: %d characters (best 70 to 160)</span></div>'
             % ("ok" if 30 <= tl <= 60 else ("warn" if tl else "bad"), tl,
                "ok" if 70 <= dl <= 160 else ("warn" if dl else "bad"), dl))
    return '<div class="ui">%s%s</div>' % (box, chips)


def share_preview(res):
    og = res.get("og") or {}
    img = og.get("og:image") or ""
    title = og.get("og:title") or res.get("title") or ""
    desc = og.get("og:description") or res.get("meta_desc") or ""
    if img:
        pic = ('<div class="ph">%s</div><img src="%s" alt="" referrerpolicy="no-referrer" loading="lazy">'
               % (icon("image", 28, "#94a3b8"), esc(img)))
    else:
        pic = ('<div class="ph">%s<div class="phs">No preview picture set (og:image)</div></div>'
               % icon("image-off", 28, "#94a3b8"))
    missing = [label for key, label in (("og:title", "title"), ("og:description", "description"),
                                        ("og:image", "picture")) if not og.get(key)]
    note = ('<div class="lenrow"><span class="pill ok">%sAll three share tags are set</span></div>'
            % icon("check", 12, COLOR["ok"])) if not missing else (
        '<div class="lenrow"><span class="pill warn">Missing share %s</span></div>' % esc(", ".join(missing)))
    return ('<div class="ui"><div class="share"><div class="si">%s</div><div class="sb"><div class="sdm">%s</div>'
            '<div class="stt">%s</div><div class="sds">%s</div></div></div>%s</div>'
            % (pic, esc(nice_domain(res)), esc(trunc(title, 90) or "(no title)"), esc(trunc(desc, 200)), note))


def shot_desktop(res):
    shots = res.get("shots") or {}
    if not shots.get("desktop"):
        return '<div class="ui empty">%s<div style="margin-top:6px">%s</div></div>' % (
            icon("monitor", 24, "#94a3b8"), esc(shots.get("error") or "No desktop screenshot."))
    return ('<div class="ui shotbig"><div class="bar">%s<span>%s</span></div>'
            '<img src="data:image/jpeg;base64,%s" alt="Desktop screenshot"></div>'
            % (icon("monitor", 14, "#94a3b8"), esc(trunc(res.get("final_url", ""), 90)), shots["desktop"]))


def shot_mobile(res):
    shots = res.get("shots") or {}
    if not shots.get("mobile"):
        return '<div class="ui empty">%s<div style="margin-top:6px">No phone screenshot.</div></div>' % icon(
            "phone", 24, "#94a3b8")
    return ('<div class="ui shotphone"><img src="data:image/jpeg;base64,%s" alt="Phone screenshot"></div>'
            % shots["mobile"])


def unique_images(images):
    """Group identical image addresses. -> list of (image dict, count)."""
    order, counts, first = [], Counter(), {}
    for im in images:
        key = im.get("src") or ("embedded-%d" % len(order))
        if key not in first:
            first[key] = im
            order.append(key)
        counts[key] += 1
    return [(first[k], counts[k]) for k in order]


def gallery(items, cx=False):
    if not items:
        return '<div class="ui empty">No images to show.</div>'
    out = []
    for im, n in items:
        src = im.get("src") or ""
        alt = im.get("alt") or ""
        ph = '<div class="gph">%s</div>' % icon("image", 26, "#cbd5e1")
        img = ('<img src="%s" alt="" referrerpolicy="no-referrer" loading="lazy">' % esc(src)) if src else ""
        wrap = ('<a class="gimg" href="%s" target="_blank" rel="noopener noreferrer">%s%s</a>' % (esc(src), ph, img)
                if src else '<div class="gimg">%s</div>' % ph)
        chip = ('<span class="pill ok">Described</span>' if im.get("has_alt")
                else '<span class="pill warn">No description</span>')
        cap = ('<div class="ga">%s</div>' % esc(trunc(alt, 120))) if alt else (
            '<div class="ga miss">Google and screen readers cannot tell what this shows.</div>')
        extra = []
        if n > 1:
            extra.append("used %d times" % n)
        if cx:
            extra.append("size set" if im.get("has_dims") else "no size")
            if im.get("lazy"):
                extra.append("lazy")
            if not src:
                extra.append("embedded / no src")
        meta = ('<div class="gx">%s</div>' % esc(" \u00b7 ".join(extra))) if extra else ""
        out.append('<div class="gi">%s<div class="gb"><div>%s</div>%s%s</div></div>' % (wrap, chip, cap, meta))
    return '<div class="ui gallery">%s</div>' % "".join(out)


def heading_outline(headings, limit=120):
    if not headings:
        return '<div class="ui empty">This page has no headings.</div>'
    rows, stack = [], []
    for lvl, txt in list(headings)[:limit]:
        lvl = int(lvl)
        while stack and stack[-1] >= lvl:
            stack.pop()
        depth = len(stack)
        stack.append(lvl)
        text = esc(trunc(txt, 140)) if txt else '<span class="em">(empty heading)</span>'
        rows.append('<div class="hl h%d" style="padding-left:%dpx"><span class="lv">H%d</span><span>%s</span></div>'
                    % (lvl, 16 + min(depth, 5) * 20, lvl, text))
    more = ""
    if len(headings) > limit:
        more = '<div class="hl"><span class="em">and %d more</span></div>' % (len(headings) - limit)
    return '<div class="ui outline">%s%s</div>' % ("".join(rows), more)


def heading_summary(headings):
    c = Counter(int(l) for l, _ in headings)
    return " \u00b7 ".join("%d &times; H%d" % (c[i], i) for i in range(1, 7) if c.get(i))


def kv(pairs):
    return '<div class="ui kv">%s</div>' % "".join(
        '<div class="k">%s</div><div class="v">%s</div>' % (esc(k), v) for k, v in pairs)


def redirect_chain(chain):
    rows = []
    for i, (code, url) in enumerate(chain):
        tone = "ok" if int(code) < 300 else "warn"
        rows.append('<div class="cl">%s<span class="code %s">%s</span><span>%s</span></div>'
                    % (icon("redirect" if i else "arrow-right", 14, "#94a3b8"), tone, esc(code), esc(url)))
    return '<div class="ui chain">%s</div>' % "".join(rows)


def report_intro():
    return ('<div class="ui card reportcard"><div class="sec-ic" style="width:44px;height:44px;border-radius:11px;'
            'background:var(--accent-soft);display:grid;place-items:center;flex:none">%s</div><div>'
            '<div style="font-weight:600;font-size:16px">Download the full report</div>'
            '<div class="note" style="font-size:14px;margin-top:2px">A single HTML file with the scores, the '
            'to-do list, every check and the screenshots. It opens in any browser without internet. To make '
            'a PDF, open it and use Print, then Save as PDF.</div></div></div>' % icon("file", 22, "#2563eb"))
