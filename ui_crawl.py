"""
Live "bots crawling the site" animation shown while an audit runs.

    from ui_crawl import CrawlView, CRAWL_CSS
    st.markdown(CRAWL_CSS, unsafe_allow_html=True)     # once per run
    ph = st.empty()
    view = CrawlView(ph, url)
    res = Auditor(url, ..., progress=view.handle).run()
    view.finish()                                       # optional, safe to call twice
    # on an exception: call view.stop() before reusing the placeholder

How it works
------------
* `handle(event)` updates the state and re-renders one HTML card into the placeholder
  (at most ~6 frames per second; `stage`, `plan` and `done` always render). A frame that
  was skipped by the throttle is flushed shortly afterwards by a one-shot timer, so the
  screen never stays behind while the engine waits on the network.
* Streamlit reuses DOM nodes between updates, so every frame alternates its root tag
  (div / section). That forces a fresh mount, and every animation is given a negative
  `animation-delay` computed from the elapsed time, so looping motion continues smoothly
  and one-shot effects (a page "popping" when visited, a new log line fading in) play
  exactly once.
* Plain HTML + CSS only (no JavaScript, no SMIL). All class names start with `cv-`.
"""

import html
import math
import re
import threading
import time
from urllib.parse import urlparse

from icons import icon

try:  # the engine is the source of truth for stage names and bot tokens
    from engine import STAGES as _ENGINE_STAGES, BOTS as _ENGINE_BOTS
    STAGES = list(_ENGINE_STAGES)
    LIVE_BOTS = [b["token"] for b in _ENGINE_BOTS if b.get("ua")]
except Exception:  # noqa: BLE001 - keep the animation usable on its own
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
    LIVE_BOTS = ["Googlebot", "Bingbot", "OAI-SearchBot", "ChatGPT-User", "PerplexityBot",
                 "Claude-SearchBot", "Claude-User", "GPTBot", "ClaudeBot", "CCBot"]

# Share of the progress bar each stage takes (the crawl and bot tests take longest).
STAGE_WEIGHT = {"connect": 1.0, "robots": 1.0, "sitemap": 1.0, "page": 1.0, "crawl": 3.0,
                "bots": 2.0, "links": 1.0, "shots": 0.6, "score": 1.4}

MIN_INTERVAL = 1.0 / 6          # seconds between frames
LOG_LINES = 7
MAX_NODES = 28                  # nodes drawn on the map (the rest are summarised)
CX, CY = 50.0, 46.0             # centre of the map, in % of its width / height
POP_S = 0.9                     # length of the "visited" pop
LOG_IN_S = 1.6                  # length of the new-log-line highlight
CHIP_IN_S = 0.7                 # length of the bot-chip result pop

ROBOTS_RULE_RE = re.compile(r"^robots\.txt (allows|BLOCKS) (\S+)$")

COL = dict(accent="#2563eb", ok="#059669", warn="#d97706", bad="#dc2626",
           muted="#64748b", faint="#94a3b8", text="#0f172a")


# ---------------------------------------------------------------------------------------
# CSS (inject once per run)
# ---------------------------------------------------------------------------------------
_CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
@property --cv-s{syntax:'<integer>';inherits:false;initial-value:0}
@property --cv-d{syntax:'<integer>';inherits:false;initial-value:0}
.cv-root{--bg:#ffffff;--surface:#f8fafc;--surface-2:#f1f5f9;--border:#e2e8f0;--text:#0f172a;
 --muted:#64748b;--faint:#94a3b8;--accent:#2563eb;--accent-ink:#1d4ed8;--accent-soft:#eff6ff;
 --ok:#059669;--ok-soft:#ecfdf5;--warn:#d97706;--warn-soft:#fffbeb;--bad:#dc2626;--bad-soft:#fef2f2;
 --cv-mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
 container-type:inline-size;container-name:cvroot;box-sizing:border-box;width:100%;
 background:var(--bg);border:1px solid var(--border);border-radius:12px;
 box-shadow:0 1px 2px rgba(15,23,42,.05);padding:18px 20px 20px;color:var(--text);
 font-family:Inter,-apple-system,"Segoe UI",Roboto,sans-serif;font-size:14px;line-height:1.4;
 text-align:left;margin:0 0 8px 0}
.cv-root *,.cv-root *::before,.cv-root *::after{box-sizing:border-box}
.cv-root svg.ic{display:block;flex:none}

/* header ------------------------------------------------------------------------- */
.cv-head{display:flex;align-items:center;gap:14px}
.cv-head-ic{width:42px;height:42px;border-radius:10px;background:var(--accent-soft);color:var(--accent);
 display:flex;align-items:center;justify-content:center;flex:none}
.cv-done .cv-head-ic{background:var(--ok-soft)}
.cv-head-txt{flex:1;min-width:0}
.cv-title{font-size:18px;font-weight:650;letter-spacing:-.01em;white-space:nowrap;overflow:hidden;
 text-overflow:ellipsis;color:var(--text)}
.cv-title b{font-weight:700;color:var(--accent-ink)}
.cv-done .cv-title b{color:var(--text)}
.cv-sub{font-size:13.5px;color:var(--muted);margin-top:1px;white-space:nowrap;overflow:hidden;
 text-overflow:ellipsis}
.cv-stats{display:flex;gap:22px;flex:none}
.cv-stat{display:flex;flex-direction:column;align-items:flex-end}
.cv-stat-n{font-size:19px;font-weight:650;font-variant-numeric:tabular-nums;color:var(--text);
 line-height:1.15;white-space:nowrap}
.cv-stat-n small{font-size:13px;color:var(--faint);font-weight:500}
.cv-stat-l{font-size:10.5px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;color:var(--faint)}
.cv-clock{animation:cv-count-s 3600s steps(3600,end) both,cv-count-d 1s steps(10,end) infinite;
 counter-reset:cvs var(--cv-s) cvd var(--cv-d)}
.cv-clock::before{content:counter(cvs) "." counter(cvd)}
@keyframes cv-count-s{from{--cv-s:0}to{--cv-s:3600}}
@keyframes cv-count-d{from{--cv-d:0}to{--cv-d:10}}

/* progress bar --------------------------------------------------------------------- */
.cv-bar{position:relative;height:5px;border-radius:99px;background:var(--surface-2);margin:12px 0 14px;
 overflow:hidden}
.cv-bar-fill{position:absolute;left:0;top:0;bottom:0;border-radius:99px;background:var(--accent);
 width:var(--w1);animation:cv-grow 5s cubic-bezier(.2,.7,.3,1) both}
.cv-done .cv-bar-fill{background:var(--ok);animation:none;width:100%}
.cv-bar-fill::after{content:"";position:absolute;top:0;bottom:0;width:90px;
 background:linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,.55),rgba(255,255,255,0));
 animation:cv-shine 1.8s linear infinite;animation-delay:inherit}
.cv-done .cv-bar-fill::after{display:none}
@keyframes cv-grow{from{width:var(--w0)}to{width:var(--w1)}}
@keyframes cv-shine{from{left:-90px}to{left:100%}}

/* body layout ---------------------------------------------------------------------- */
.cv-body{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:18px;align-items:stretch}
.cv-left{display:flex;flex-direction:column;gap:10px;min-width:0}
.cv-side{display:flex;flex-direction:column;gap:12px;min-width:0}

/* crawl map ------------------------------------------------------------------------ */
.cv-map{position:relative;height:262px;border:1px solid var(--border);border-radius:10px;overflow:hidden;
 background-color:var(--bg);
 background-image:radial-gradient(circle,#e2e8f0 1px,transparent 1.3px);background-size:18px 18px;
 --cx:50%;--cy:46%}
.cv-sweep{position:absolute;left:50%;top:46%;width:760px;height:760px;margin:-380px 0 0 -380px;
 border-radius:50%;pointer-events:none;
 background:conic-gradient(from 0deg,rgba(37,99,235,0) 0deg,rgba(37,99,235,0) 300deg,
   rgba(37,99,235,.10) 358deg,rgba(37,99,235,0) 360deg);
 -webkit-mask-image:radial-gradient(circle,#000 0,#000 25%,transparent 62%);
 mask-image:radial-gradient(circle,#000 0,#000 25%,transparent 62%);
 animation:cv-spin 4.8s linear infinite}
.cv-done .cv-sweep{display:none}
.cv-edges{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
.cv-edges .cv-ring{fill:none;stroke:#e2e8f0;stroke-width:1;stroke-dasharray:2 5}
.cv-edges line{stroke-width:1.5;stroke-linecap:round}
.cv-e-pend{stroke:#e2e8f0;stroke-dasharray:3 5}
.cv-e-wait{stroke:rgba(37,99,235,.45);stroke-dasharray:4 6;animation:cv-ants 1s linear infinite}
.cv-e-ok{stroke:rgba(37,99,235,.42)}
.cv-e-warn{stroke:rgba(217,119,6,.55)}
.cv-e-bad{stroke:rgba(220,38,38,.55)}
.cv-e-skip{stroke:#e2e8f0}
@keyframes cv-ants{from{stroke-dashoffset:10}to{stroke-dashoffset:0}}

.cv-legend{position:absolute;right:10px;bottom:8px;display:flex;gap:12px;font-size:11px;color:var(--muted);
 background:rgba(255,255,255,.85);padding:3px 6px;border-radius:6px;z-index:6}
.cv-legend span{display:inline-flex;align-items:center;gap:5px}
.cv-legend i{display:inline-block;width:9px;height:9px;border-radius:3px;border:1.5px solid}
.cv-lg-ok{background:var(--accent-soft);border-color:var(--accent)!important}
.cv-lg-warn{background:var(--warn-soft);border-color:var(--warn)!important}
.cv-lg-bad{background:var(--bad-soft);border-color:var(--bad)!important}
.cv-lg-pend{background:#fff;border-color:var(--faint)!important;border-style:dashed!important}
.cv-more{position:absolute;right:12px;top:10px;font-size:11px;color:var(--muted);z-index:6}

/* page nodes */
.cv-node{position:absolute;left:var(--x);top:var(--y);width:28px;height:28px;margin:-14px 0 0 -14px;
 border-radius:8px;border:1.5px solid var(--faint);background:#fff;color:var(--faint);
 display:flex;align-items:center;justify-content:center;z-index:3}
.cv-n-pend{border-style:dashed}
.cv-n-wait{border-style:dashed;border-color:var(--accent);color:var(--accent);
 animation:cv-breathe 1.4s ease-in-out infinite}
.cv-n-ok{border-color:var(--accent);background:var(--accent-soft);color:var(--accent)}
.cv-n-warn{border-color:var(--warn);background:var(--warn-soft);color:var(--warn)}
.cv-n-bad{border-color:var(--bad);background:var(--bad-soft);color:var(--bad)}
.cv-n-skip{border-color:var(--border);background:var(--surface-2);color:var(--faint)}
.cv-n-pop{animation:cv-pop .9s cubic-bezier(.2,.9,.3,1.3) both}
.cv-n-pop::after{content:"";position:absolute;inset:-2px;border-radius:10px;border:2px solid currentColor;
 animation:cv-ring .9s ease-out both;animation-delay:inherit}
@keyframes cv-pop{0%{transform:scale(.35)}55%{transform:scale(1.22)}100%{transform:scale(1)}}
@keyframes cv-ring{0%{opacity:.7;transform:scale(1)}100%{opacity:0;transform:scale(2.3)}}
@keyframes cv-breathe{0%,100%{box-shadow:0 0 0 0 rgba(37,99,235,.0)}50%{box-shadow:0 0 0 5px rgba(37,99,235,.12)}}
.cv-lbl{position:absolute;left:var(--x);top:var(--y);transform:translate(-50%,17px);max-width:110px;
 font-family:var(--cv-mono);font-size:11px;color:var(--faint);white-space:nowrap;overflow:hidden;
 text-overflow:ellipsis;z-index:4;background:rgba(255,255,255,.88);padding:0 3px;border-radius:4px;
 line-height:15px}
.cv-l-ok{color:var(--text)}
.cv-l-warn{color:var(--warn)}
.cv-l-bad{color:var(--bad)}
.cv-l-wait{color:var(--accent-ink)}

/* centre: the website itself */
.cv-hub{position:absolute;left:var(--cx);top:var(--cy);width:58px;height:58px;margin:-29px 0 0 -29px;
 border-radius:50%;background:#fff;border:2px solid var(--accent);color:var(--accent);z-index:5;
 display:flex;align-items:center;justify-content:center;box-shadow:0 1px 3px rgba(15,23,42,.08)}
.cv-hub::before{content:"";position:absolute;inset:-2px;border-radius:50%;border:2px solid var(--accent);
 animation:cv-ring 2.4s ease-out infinite;animation-delay:inherit}
.cv-done .cv-hub::before,.cv-hub-wait::before{display:none}
.cv-hub-wait{border-style:dashed;color:var(--faint);border-color:var(--faint);
 animation:cv-breathe 1.4s ease-in-out infinite}
.cv-hub-warn{border-color:var(--warn);color:var(--warn)}
.cv-hub-bad{border-color:var(--bad);color:var(--bad)}
.cv-hub-lbl{position:absolute;left:var(--cx);top:var(--cy);transform:translate(-50%,34px);z-index:5;
 display:flex;flex-direction:column;align-items:center;gap:5px;pointer-events:none}
.cv-hub-name{font-size:13.5px;font-weight:650;color:var(--text);background:rgba(255,255,255,.92);
 padding:0 6px;border-radius:5px;white-space:nowrap;max-width:240px;overflow:hidden;text-overflow:ellipsis}
.cv-pills{display:flex;gap:5px}
.cv-pill{display:inline-flex;align-items:center;gap:4px;font-family:var(--cv-mono);font-size:10.5px;
 padding:2px 7px 2px 5px;border-radius:99px;border:1px solid var(--border);background:#fff;
 color:var(--faint);white-space:nowrap;line-height:14px}
.cv-p-pend{border-style:dashed}
.cv-p-act{border-color:var(--accent);color:var(--accent-ink);background:var(--accent-soft);
 animation:cv-breathe 1.4s ease-in-out infinite}
.cv-p-ok{border-color:rgba(5,150,105,.35);background:var(--ok-soft);color:var(--ok)}
.cv-p-warn{border-color:rgba(217,119,6,.35);background:var(--warn-soft);color:var(--warn)}
.cv-p-done{background:var(--surface-2);color:var(--muted)}

/* packets travelling along the links */
.cv-pkt{position:absolute;width:7px;height:7px;margin:-3.5px 0 0 -3.5px;border-radius:50%;
 background:var(--accent);box-shadow:0 0 0 3px rgba(37,99,235,.14);z-index:2;opacity:0;
 left:var(--cx);top:var(--cy)}
.cv-pk-out{animation:cv-out 1.3s ease-in infinite}
.cv-pk-in{animation:cv-in 2.4s ease-in-out infinite}
.cv-pk-warn{background:var(--warn);box-shadow:0 0 0 3px rgba(217,119,6,.14)}
.cv-pk-bad{background:var(--bad);box-shadow:0 0 0 3px rgba(220,38,38,.14)}
@keyframes cv-out{0%{left:var(--cx);top:var(--cy);opacity:0}12%{opacity:1}88%{opacity:1}
 100%{left:var(--x);top:var(--y);opacity:0}}
@keyframes cv-in{0%{left:var(--x);top:var(--y);opacity:0}10%{opacity:1}70%{left:var(--cx);top:var(--cy);opacity:1}
 78%{opacity:0}100%{left:var(--cx);top:var(--cy);opacity:0}}

/* crawler bots on the map */
.cv-bot{position:absolute;left:var(--x1);top:var(--y1);width:30px;height:30px;margin:-15px 0 0 -15px;
 border-radius:50%;background:#fff;border:1.5px solid var(--accent);color:var(--accent);z-index:7;
 display:flex;align-items:center;justify-content:center;box-shadow:0 2px 6px rgba(37,99,235,.18)}
.cv-bot-hop{animation:cv-hop var(--dur) ease-in-out infinite}
@keyframes cv-hop{
 0%,10%{left:var(--x0);top:var(--y0)} 25%,35%{left:var(--x1);top:var(--y1)}
 50%,60%{left:var(--x2);top:var(--y2)} 75%,85%{left:var(--x3);top:var(--y3)}
 100%{left:var(--x0);top:var(--y0)}}
.cv-orbit{position:absolute;top:0;bottom:0;width:0;left:calc(var(--cx) - var(--rx));z-index:7;
 pointer-events:none;animation:cv-ox var(--half) ease-in-out infinite alternate}
.cv-orbit .cv-bot{left:0;top:calc(var(--cy) - var(--ry));animation:cv-oy var(--half) ease-in-out infinite alternate}
@keyframes cv-ox{from{left:calc(var(--cx) - var(--rx))}to{left:calc(var(--cx) + var(--rx))}}
@keyframes cv-oy{from{top:calc(var(--cy) - var(--ry))}to{top:calc(var(--cy) + var(--ry))}}
.cv-empty{position:absolute;left:0;right:0;bottom:12px;text-align:center;font-size:12px;color:var(--muted);z-index:6}
.cv-done .cv-bot,.cv-done .cv-orbit,.cv-done .cv-orbit .cv-bot{animation:none}

/* bot test chips ------------------------------------------------------------------- */
.cv-bots{border:1px solid var(--border);border-radius:10px;padding:8px 12px 10px;background:var(--bg)}
.cv-bots-h{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:4px 10px;margin-bottom:7px}
.cv-bots-t{font-size:12px;font-weight:650;color:var(--text);display:flex;align-items:center;gap:6px;white-space:nowrap}
.cv-bots-k{display:flex;gap:12px;font-size:11px;color:var(--muted)}
.cv-bots-k span{display:inline-flex;align-items:center;gap:4px;white-space:nowrap}
.cv-chips{display:flex;flex-wrap:wrap;gap:6px}
.cv-chip{display:inline-flex;align-items:center;gap:5px;font-family:var(--cv-mono);font-size:11.5px;
 padding:3px 9px 3px 6px;border-radius:99px;border:1px solid var(--border);background:#fff;
 color:var(--faint);line-height:16px;white-space:nowrap}
.cv-c-pend{border-style:dashed}
.cv-c-test{border-color:var(--accent);color:var(--accent-ink);background:var(--accent-soft)}
.cv-c-test > svg.ic{animation:cv-spin .9s linear infinite;animation-delay:inherit}
.cv-c-ok{border-color:rgba(5,150,105,.4);background:var(--ok-soft);color:var(--text)}
.cv-c-bad{border-color:rgba(220,38,38,.4);background:var(--bad-soft);color:var(--text)}
.cv-c-in{animation:cv-chip .7s cubic-bezier(.2,.9,.3,1.3) both}
.cv-c-lock{display:inline-flex;margin-left:1px}
@keyframes cv-chip{0%{transform:scale(.8);box-shadow:0 0 0 0 rgba(5,150,105,.35)}
 50%{transform:scale(1.08)}100%{transform:scale(1);box-shadow:0 0 0 6px rgba(5,150,105,0)}}

/* stage checklist ------------------------------------------------------------------ */
.cv-steps{display:flex;flex-direction:column;gap:1px}
.cv-step{display:flex;align-items:center;gap:9px;font-size:13.5px;padding:1px 8px;border-radius:7px;
 color:var(--faint);min-height:23px}
.cv-step-ic{animation-delay:inherit;width:20px;height:20px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex:none}
.cv-st-done{color:var(--text)}
.cv-st-done .cv-step-ic{background:var(--ok-soft);color:var(--ok)}
.cv-st-now{color:var(--accent-ink);background:var(--accent-soft);font-weight:600}
.cv-st-now .cv-step-ic svg{animation:cv-spin .9s linear infinite;animation-delay:inherit}
.cv-step-t{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cv-step-d{font-family:var(--cv-mono);font-size:11px;color:var(--faint);font-weight:400}
@keyframes cv-spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}

/* live log ------------------------------------------------------------------------- */
.cv-log{flex:1;background:var(--surface);border:1px solid var(--border);border-radius:10px;
 padding:8px 10px 8px;min-height:0;display:flex;flex-direction:column}
.cv-log-h{display:flex;align-items:center;gap:6px;font-size:11px;font-weight:600;letter-spacing:.07em;
 text-transform:uppercase;color:var(--faint);margin-bottom:4px}
.cv-log-h .cv-live{margin-left:auto;display:inline-flex;align-items:center;gap:5px;letter-spacing:.05em}
.cv-live i{width:7px;height:7px;border-radius:50%;background:var(--ok);display:inline-block;
 animation:cv-blink 1.6s ease-in-out infinite}
.cv-done .cv-live i{animation:none;background:var(--faint)}
@keyframes cv-blink{0%,100%{opacity:1}50%{opacity:.25}}
.cv-ln{display:flex;align-items:center;gap:7px;font-family:var(--cv-mono);font-size:11.5px;line-height:18.5px;
 border-radius:5px;padding:0 4px;margin:0 -4px;color:var(--muted)}
.cv-ln-t{color:var(--faint);flex:none;font-variant-numeric:tabular-nums;width:38px;text-align:right}
.cv-ln-x{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cv-ln-ok{color:color-mix(in srgb,var(--ok) 82%,#000)}
.cv-ln-warn{color:color-mix(in srgb,var(--warn) 78%,#000)}
.cv-ln-new{animation:cv-login 1.6s ease-out both}
@keyframes cv-login{0%{opacity:0;transform:translateY(6px);background:var(--accent-soft)}
 18%{opacity:1;transform:translateY(0);background:var(--accent-soft)}100%{background:rgba(239,246,255,0)}}
.cv-ln-empty{color:var(--faint);font-family:var(--cv-mono);font-size:11.5px}

/* narrower containers -------------------------------------------------------------- */
@container cvroot (max-width:900px){
 .cv-body{grid-template-columns:minmax(0,1fr) 290px}
 .cv-stats{gap:14px}
 .cv-legend{display:none}
 .cv-bots-k{gap:9px;font-size:10.5px}
 .cv-chip{font-size:10.5px;padding:2px 7px 2px 5px;gap:4px}
 .cv-chips{gap:5px}
 .cv-map{height:250px}
}
@container cvroot (max-width:660px){
 .cv-body{grid-template-columns:1fr}
 .cv-head{flex-wrap:wrap}
 .cv-stats{width:100%;justify-content:flex-start}
 .cv-stat{align-items:flex-start}
 .cv-map{height:280px}
 .cv-lbl{max-width:74px;font-size:10px}
 .cv-pills{display:none}
}
@media (prefers-reduced-motion: reduce){
 .cv-sweep,.cv-pkt{display:none}
 .cv-bot,.cv-orbit,.cv-orbit .cv-bot,.cv-n-wait,.cv-n-pop,.cv-n-pop::after,.cv-hub::before,.cv-hub-wait,
 .cv-p-act,.cv-c-in,.cv-ln-new,.cv-e-wait,.cv-bar-fill::after,.cv-live i{animation:none!important}
 .cv-bar-fill{animation:none;width:var(--w0)}
 .cv-st-now .cv-step-ic svg,.cv-c-test > svg.ic{animation-duration:2.4s}
}
"""


def _minify(css):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s*\n\s*", " ", css)
    return re.sub(r"\s{2,}", " ", css).strip()


CRAWL_CSS = "<style>" + _minify(_CSS) + "</style>"


# ---------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------
def _esc(s):
    """HTML-escape, and neutralise characters Streamlit markdown might still interpret."""
    return (html.escape(str(s), quote=True)
            .replace("$", "&#36;").replace(":", "&#58;").replace("*", "&#42;")
            .replace("_", "&#95;").replace("`", "&#96;").replace("~", "&#126;"))


def _domain(url):
    try:
        u = url if "//" in (url or "") else "https://" + (url or "")
        host = urlparse(u).netloc or (url or "")
        host = host.split("@")[-1].split(":")[0]
        return host or "website"
    except Exception:  # noqa: BLE001
        return url or "website"


def _short_path(p, n=16):
    p = p or "/"
    if len(p) <= n:
        return p
    return p[: n - 1] + "…"


def _phase(elapsed, period, offset=0.0):
    """Negative animation delay that keeps a looping animation continuous across frames."""
    if period <= 0:
        return "0s"
    return "-%.3fs" % ((elapsed + offset) % period)


def _age_delay(age):
    return "-%.3fs" % max(0.0, age)


def _fmt(v):
    return "%.2f" % v


def _status_class(code):
    """Map an HTTP status to a node state."""
    if code is None:
        return "bad"
    try:
        c = int(code)
    except (TypeError, ValueError):
        return "bad"
    if c >= 500 or c <= 0:
        return "bad"
    if c >= 400:
        return "warn"
    return "ok"


def _ring_positions(n):
    """Positions (x%, y%) for n page nodes: one ring, or two for bigger crawls."""
    if n <= 0:
        return []
    rings = [(n, 41.0, 38.0, 0.0)] if n <= 14 else None
    if rings is None:
        outer = int(math.ceil(n * 0.6))
        rings = [(outer, 42.0, 39.0, 0.0), (n - outer, 25.0, 23.5, 0.5)]
    pos = []
    for count, rx, ry, shift in rings:
        for i in range(count):
            a = -math.pi / 2 + 2 * math.pi * (i + shift) / count
            pos.append((CX + rx * math.cos(a), CY + ry * math.sin(a)))
    return pos


# ---------------------------------------------------------------------------------------
# the view
# ---------------------------------------------------------------------------------------
class CrawlView:
    """Live crawl animation. Pass `view.handle` as the Auditor's `progress` callback."""

    def __init__(self, placeholder, url):
        self.ph = placeholder
        self.url = url or ""
        self.domain = _domain(self.url)
        if self.domain.startswith("www."):
            self.short_domain = self.domain[4:]
        else:
            self.short_domain = self.domain
        self.t0 = time.time()
        self._lock = threading.RLock()
        self._closed = False
        self._dirty = False
        self._timer = None
        self._last_render = 0.0
        self._frame = 0
        self._ctx = None
        try:
            from streamlit.runtime.scriptrunner import get_script_run_ctx
            self._ctx = get_script_run_ctx(suppress_warning=True)
        except Exception:  # noqa: BLE001
            self._ctx = None

        self.stage_keys = [k for k, _ in STAGES]
        self.stage_labels = dict(STAGES)
        self.stage = None
        self.stage_start = {}        # key -> engine time the stage began
        self.stage_end = {}          # key -> engine time the stage ended
        self.done = False
        self.done_t = None
        self.last_t = 0.0            # latest engine time seen

        self.logs = []               # [(engine t, text, level, wall time)]
        self.plan = None             # list of planned paths (None = not planned yet)
        self.visits = {}             # path -> (status, wall time)
        self.root_status = None
        self.root_seen = False
        self.res = {"robots": None, "llms": None, "sitemap": None}
        self.bots = [{"token": t, "ok": None, "at": None, "blocked": False} for t in LIVE_BOTS]
        self.robots_block = set()
        self._prog = (0.0, 0.0)      # (lo, hi) of the progress bar, 0..100
        self._prog_at = time.time()
        try:
            self._render(time.time())
        except Exception:  # noqa: BLE001
            pass

    # -- public API ----------------------------------------------------------------------
    def handle(self, event):
        """Progress callback for engine.Auditor. Never raises (except Streamlit's own
        stop/rerun signals, which must reach the script)."""
        try:
            with self._lock:
                if self._closed or not isinstance(event, dict):
                    return
                kind = event.get("kind")
                self._apply(kind, event)
                now = time.time()
                if kind in ("stage", "plan", "done") or now - self._last_render >= MIN_INTERVAL:
                    self._render(now)
                else:
                    self._dirty = True
                    self._schedule_flush(now)
                if kind == "done":
                    self._close()
        except Exception:  # noqa: BLE001 - a UI problem must never stop the audit
            pass

    def finish(self):
        """Show the final 'done' frame (no-op if it is already shown). Safe to call twice."""
        try:
            with self._lock:
                if self._closed:
                    return
                if not self.done:
                    self._apply("done", {"kind": "done", "t": time.time() - self.t0})
                self._render(time.time())
                self._close()
        except Exception:  # noqa: BLE001
            pass

    def stop(self):
        """Stop drawing (use when the audit failed, before reusing the placeholder)."""
        try:
            with self._lock:
                self._close()
        except Exception:  # noqa: BLE001
            pass

    close = stop

    # -- state updates -------------------------------------------------------------------
    def _apply(self, kind, ev):
        t = ev.get("t")
        try:
            t = float(t)
        except (TypeError, ValueError):
            t = time.time() - self.t0
        self.last_t = max(self.last_t, t)
        wall = time.time()

        if kind == "stage":
            key = ev.get("key")
            if self.stage and self.stage not in self.stage_end:
                self.stage_end[self.stage] = t
            # stages that were skipped count as done
            if key in self.stage_keys:
                for k in self.stage_keys[: self.stage_keys.index(key)]:
                    self.stage_start.setdefault(k, t)
                    self.stage_end.setdefault(k, t)
            self.stage = key
            self.stage_start[key] = t
        elif kind == "log":
            text = str(ev.get("text", ""))
            level = ev.get("level") or "info"
            self.logs.append((t, text, level, wall))
            if len(self.logs) > 60:
                self.logs = self.logs[-LOG_LINES - 5:]
            self._parse_log(text, level)
        elif kind == "node":
            path = ev.get("path") or "/"
            status = ev.get("status")
            if ev.get("root"):
                self.root_status = status
                self.root_seen = True
            else:
                if self.plan is None:
                    self.plan = []
                if path not in self.plan:
                    self.plan.append(path)
                self.visits[path] = (status, wall)
        elif kind == "plan":
            paths = [p or "/" for p in (ev.get("paths") or [])]
            seen, plan = set(), []
            for p in paths:
                if p not in seen:
                    seen.add(p)
                    plan.append(p)
            for p in (self.plan or []):  # keep nodes that arrived before the plan
                if p not in seen:
                    plan.append(p)
            self.plan = plan
        elif kind == "bot":
            token = str(ev.get("token", ""))
            ok = bool(ev.get("ok"))
            for b in self.bots:
                if b["token"] == token:
                    b["ok"], b["at"] = ok, wall
                    break
            else:
                self.bots.append({"token": token, "ok": ok, "at": wall,
                                  "blocked": token in self.robots_block})
        elif kind == "done":
            self.done = True
            self.done_t = t
            if self.stage and self.stage not in self.stage_end:
                self.stage_end[self.stage] = t
            for k in self.stage_keys:
                self.stage_start.setdefault(k, t)
                self.stage_end.setdefault(k, t)

        lo, hi = self._progress()
        if abs(lo - self._prog[0]) > 1e-6:
            self._prog_at = wall
        self._prog = (lo, hi)

    def _parse_log(self, text, level):
        status = "ok" if level == "ok" else "warn"
        if text.startswith("robots.txt:"):
            self.res["robots"] = status
        elif text.startswith("llms.txt:"):
            self.res["llms"] = status
        elif text.startswith("Sitemap") or text.startswith("No sitemap"):
            self.res["sitemap"] = status
        m = ROBOTS_RULE_RE.match(text)
        if m:
            blocked = m.group(1) == "BLOCKS"
            token = m.group(2)
            if blocked:
                self.robots_block.add(token)
            for b in self.bots:
                if b["token"] == token:
                    b["blocked"] = blocked

    def _progress(self):
        """(lo, hi) in percent. The bar creeps from lo towards hi until the next event."""
        if self.done:
            return 100.0, 100.0
        total = sum(STAGE_WEIGHT.get(k, 1.0) for k in self.stage_keys) or 1.0
        if self.stage not in self.stage_keys:
            return 0.0, 100.0 * 0.85 * STAGE_WEIGHT.get("connect", 1.0) / total
        idx = self.stage_keys.index(self.stage)
        before = sum(STAGE_WEIGHT.get(k, 1.0) for k in self.stage_keys[:idx])
        w = STAGE_WEIGHT.get(self.stage, 1.0)
        frac, unit = 0.0, 1.0
        if self.stage == "crawl" and self.plan:
            n = len(self.plan)
            frac, unit = min(1.0, len(self.visits) / float(n)), 1.0 / n
        elif self.stage == "bots" and self.bots:
            n = len(self.bots)
            frac, unit = min(1.0, sum(1 for b in self.bots if b["ok"] is not None) / float(n)), 1.0 / n
        lo = (before + w * frac) / total
        hi = (before + w * min(1.0, frac + 0.85 * unit)) / total
        return 100.0 * lo, 100.0 * hi

    # -- rendering -----------------------------------------------------------------------
    def _schedule_flush(self, now):
        if self._timer is not None:
            return
        delay = max(0.02, MIN_INTERVAL - (now - self._last_render) + 0.01)
        timer = threading.Timer(delay, self._flush)
        timer.daemon = True
        if self._ctx is not None:
            try:
                from streamlit.runtime.scriptrunner import add_script_run_ctx
                add_script_run_ctx(timer, self._ctx)
            except Exception:  # noqa: BLE001
                pass
        self._timer = timer
        timer.start()

    def _flush(self):
        try:
            with self._lock:
                self._timer = None
                if self._closed or not self._dirty:
                    return
                self._render(time.time())
        except BaseException:  # noqa: BLE001 - background thread: swallow everything
            pass

    def _close(self):
        self._closed = True
        self._dirty = False
        if self._timer is not None:
            try:
                self._timer.cancel()
            except Exception:  # noqa: BLE001
                pass
            self._timer = None

    def _render(self, now):
        markup = self.to_html(now)
        self._frame += 1
        self._last_render = now
        self._dirty = False
        self.ph.markdown(markup, unsafe_allow_html=True)

    def to_html(self, now=None):
        """The current frame as one line of HTML (also handy for static previews)."""
        now = time.time() if now is None else now
        el = max(0.0, now - self.t0)
        tag = "section" if self._frame % 2 else "div"   # forces a fresh mount every frame
        state = "cv-done" if self.done else "cv-run"
        parts = ['<%s class="cv-root %s" style="animation-delay:%s">' % (tag, state, _phase(el, 2.4))]
        parts.append(self._html_head(el))
        parts.append(self._html_bar(now))
        parts.append('<div class="cv-body"><div class="cv-left">')
        parts.append(self._html_map(el, now))
        parts.append(self._html_bots(el, now))
        parts.append('</div><div class="cv-side">')
        parts.append(self._html_steps(el))
        parts.append(self._html_log(now))
        parts.append('</div></div></%s>' % tag)
        return "".join(parts).replace("\n", " ")

    # header
    def _html_head(self, el):
        if self.done:
            ic = icon("check-circle", 22, COL["ok"])
            title = 'Finished auditing <b>%s</b>' % _esc(self.short_domain)
            sub = "All %d steps done. Preparing your results." % len(self.stage_keys)
            secs = self.done_t if self.done_t is not None else el
            clock = '<span class="cv-stat-n">%.1f<small> s</small></span>' % secs
        else:
            ic = icon("globe", 22, COL["accent"])
            title = 'Crawling <b>%s</b>' % _esc(self.short_domain)
            label = self.stage_labels.get(self.stage, "Starting the audit")
            idx = self.stage_keys.index(self.stage) + 1 if self.stage in self.stage_keys else 0
            sub = ("Step %d of %d &middot; %s" % (idx, len(self.stage_keys), _esc(label))) if idx \
                else "Starting the audit"
            clock = ('<span class="cv-stat-n"><span class="cv-clock" style="animation-delay:-%.3fs,%s">'
                     '</span><small> s</small></span>' % (el, _phase(el, 1.0)))
        n_plan = len(self.plan) if self.plan is not None else 0
        pages = len(self.visits) + (1 if self.root_seen else 0)
        pages_total = n_plan + 1
        bots_done = sum(1 for b in self.bots if b["ok"] is not None)
        stats = (
            '<div class="cv-stats">'
            '<div class="cv-stat"><span class="cv-stat-n">%d<small> / %d</small></span>'
            '<span class="cv-stat-l">Pages</span></div>'
            '<div class="cv-stat"><span class="cv-stat-n">%d<small> / %d</small></span>'
            '<span class="cv-stat-l">Bots tested</span></div>'
            '<div class="cv-stat">%s<span class="cv-stat-l">Elapsed</span></div>'
            '</div>' % (pages, pages_total if self.plan is not None else max(pages, 1),
                        bots_done, len(self.bots), clock))
        return ('<div class="cv-head"><div class="cv-head-ic">%s</div><div class="cv-head-txt">'
                '<div class="cv-title">%s</div><div class="cv-sub">%s</div></div>%s</div>'
                % (ic, title, sub, stats))

    def _html_bar(self, now):
        lo, hi = self._prog
        since = max(0.0, now - self._prog_at)
        return ('<div class="cv-bar"><div class="cv-bar-fill" style="--w0:%s%%;--w1:%s%%;'
                'animation-delay:%s"></div></div>' % (_fmt(lo), _fmt(hi), _age_delay(since)))

    # map
    def _node_state(self, path):
        if path in self.visits:
            return _status_class(self.visits[path][0])
        if self.done or (self.stage in self.stage_keys and self.stage_keys.index(self.stage)
                         > self.stage_keys.index("crawl")):
            return "skip"
        if self.stage == "crawl":
            return "wait"
        return "pend"

    def _html_map(self, el, now):
        out = ['<div class="cv-map">', '<div class="cv-sweep" style="animation-delay:%s"></div>'
               % _phase(el, 4.8)]
        plan = list(self.plan or [])
        shown = plan[:MAX_NODES]
        pos = _ring_positions(len(shown))
        states = [self._node_state(p) for p in shown]

        # edges + guide rings
        svg = ['<svg class="cv-edges" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">']
        if len(shown) > 14:
            svg.append('<ellipse class="cv-ring" cx="%s" cy="%s" rx="42" ry="39" vector-effect="non-scaling-stroke"/>'
                       % (CX, CY))
            svg.append('<ellipse class="cv-ring" cx="%s" cy="%s" rx="25" ry="23.5" '
                       'vector-effect="non-scaling-stroke"/>' % (CX, CY))
        else:
            svg.append('<ellipse class="cv-ring" cx="%s" cy="%s" rx="41" ry="38" vector-effect="non-scaling-stroke"/>'
                       % (CX, CY))
            svg.append('<ellipse class="cv-ring" cx="%s" cy="%s" rx="22" ry="20" vector-effect="non-scaling-stroke"/>'
                       % (CX, CY))
        for (x, y), st in zip(pos, states):
            extra = ' style="animation-delay:%s"' % _phase(el, 1.0) if st == "wait" else ""
            svg.append('<line class="cv-e-%s" x1="%s" y1="%s" x2="%s" y2="%s" '
                       'vector-effect="non-scaling-stroke"%s/>' % (st, CX, CY, _fmt(x), _fmt(y), extra))
        svg.append('</svg>')
        out.append("".join(svg))

        # legend
        if plan:
            out.append('<div class="cv-legend"><span><i class="cv-lg-ok"></i>Visited</span>'
                       '<span><i class="cv-lg-warn"></i>Client error</span>'
                       '<span><i class="cv-lg-bad"></i>Failed</span>'
                       '<span><i class="cv-lg-pend"></i>Queued</span></div>')
        if self.plan is not None and not plan:
            out.append('<div class="cv-empty">No internal links found to follow from the main page</div>')
        if len(plan) > MAX_NODES:
            out.append('<div class="cv-more">+%d more pages</div>' % (len(plan) - MAX_NODES))

        # packets
        if not self.done:
            for i, ((x, y), st) in enumerate(zip(pos, states)):
                if st == "wait":
                    out.append('<div class="cv-pkt cv-pk-out" style="--x:%s%%;--y:%s%%;animation-delay:%s"></div>'
                               % (_fmt(x), _fmt(y), _phase(el, 1.3, i * 0.37)))
                elif st in ("ok", "warn", "bad"):
                    cls = "" if st == "ok" else " cv-pk-" + st
                    out.append('<div class="cv-pkt cv-pk-in%s" style="--x:%s%%;--y:%s%%;animation-delay:%s"></div>'
                               % (cls, _fmt(x), _fmt(y), _phase(el, 2.4, i * 0.53)))

        # page nodes + labels
        for i, (p, (x, y), st) in enumerate(zip(shown, pos, states)):
            cls = "cv-node cv-n-%s" % st
            style = "--x:%s%%;--y:%s%%" % (_fmt(x), _fmt(y))
            if p in self.visits:
                age = now - self.visits[p][1]
                if age < POP_S and not self.done:
                    cls += " cv-n-pop"
                    style += ";animation-delay:%s" % _age_delay(age)
            elif st == "wait":
                style += ";animation-delay:%s" % _phase(el, 1.4, i * 0.21)
            code = self.visits.get(p, (None, 0))[0]
            tip = "%s%s" % (p, (" (HTTP %s)" % code) if p in self.visits else "")
            ic_col = "currentColor"
            out.append('<div class="%s" style="%s" title="%s">%s</div>'
                       % (cls, style, _esc(tip), icon("file", 14, ic_col)))
            lbl = _short_path(p)
            if p in self.visits and st != "ok":
                lbl = "%s %s" % (_short_path(p, 11), code if code else "ERR")
            lcls = {"ok": "cv-l-ok", "warn": "cv-l-warn", "bad": "cv-l-bad", "wait": "cv-l-wait"}.get(st, "")
            out.append('<div class="cv-lbl %s" style="--x:%s%%;--y:%s%%">%s</div>'
                       % (lcls, _fmt(x), _fmt(y), _esc(lbl)))

        # the website in the centre
        hub_cls = "cv-hub"
        if not self.root_seen:
            hub_cls += " cv-hub-wait"
        elif _status_class(self.root_status) != "ok":
            hub_cls += " cv-hub-" + _status_class(self.root_status)
        out.append('<div class="%s" style="animation-delay:%s">%s</div>'
                   % (hub_cls, _phase(el, 2.4), icon("globe", 26, "currentColor")))
        out.append('<div class="cv-hub-lbl"><div class="cv-hub-name">%s</div><div class="cv-pills">%s</div></div>'
                   % (_esc(self.domain), self._html_pills(el)))

        # crawler bots
        out.append(self._html_map_bots(el, pos))
        out.append('</div>')
        return "".join(out)

    def _html_pills(self, el):
        spec = [("robots", "robots.txt", "robots"), ("llms", "llms.txt", "robots"),
                ("sitemap", "sitemap", "sitemap")]
        cur = self.stage_keys.index(self.stage) if self.stage in self.stage_keys else -1
        out = []
        for key, label, stage in spec:
            sidx = self.stage_keys.index(stage) if stage in self.stage_keys else 99
            res = self.res.get(key)
            extra = ""
            if res == "ok":
                cls, ic = "cv-p-ok", icon("check", 11, "currentColor", 2.5)
            elif res == "warn":
                cls, ic = "cv-p-warn", icon("x", 11, "currentColor", 2.5)
            elif self.done or cur > sidx:
                cls, ic = "cv-p-done", icon("file", 11, "currentColor")
            elif cur == sidx:
                cls, ic = "cv-p-act", icon("file", 11, "currentColor")
                extra = ' style="animation-delay:%s"' % _phase(el, 1.4)
            else:
                cls, ic = "cv-p-pend", icon("file", 11, "currentColor")
            out.append('<span class="cv-pill %s"%s>%s%s</span>' % (cls, extra, ic, label))
        return "".join(out)

    def _html_map_bots(self, el, pos):
        bot_ic = icon("bot", 17, "currentColor")
        out = []
        n = len(pos)
        if n == 0:
            # nothing planned (yet): the bots circle the website
            # elliptical orbits: x and y swing a quarter turn apart (direction = sign of shift)
            for i, (rx, ry, dur, shift) in enumerate([(41, 38, 9.0, 0.25), (41, 38, 9.0, -0.25),
                                                      (29, 31, 6.4, 0.25)]):
                half = dur / 2.0
                off = (0.0, 4.5, 1.1)[i]
                ydelay = _phase(el, dur, off)
                xdelay = _phase(el, dur, off + shift * dur)
                out.append('<div class="cv-orbit" style="--rx:%d%%;--ry:%d%%;--half:%ss;animation-delay:%s">'
                           '<div class="cv-bot" style="animation-delay:%s">%s</div></div>'
                           % (rx, ry, half, xdelay, ydelay, bot_ic))
            return "".join(out)
        # the bots hop from page to page (route fixed by the plan, so it never jumps)
        centre = (CX, CY)
        k = max(1, n // 3)
        s = max(1, n // 4) if n > 3 else 1
        for b, dur in enumerate([6.6, 7.8, 9.0]):
            a = (b * k) % n
            pts = [centre, pos[a], pos[(a + s) % n], pos[(a + 2 * s) % n]]
            if n == 1:
                pts = [centre, pos[0], centre, pos[0]]
            style = ";".join("--x%d:%s%%;--y%d:%s%%" % (j, _fmt(px), j, _fmt(py))
                             for j, (px, py) in enumerate(pts))
            style += ";--dur:%ss;animation-delay:%s" % (dur, _phase(el, dur, b * 1.7))
            out.append('<div class="cv-bot cv-bot-hop" style="%s">%s</div>' % (style, bot_ic))
        return "".join(out)

    # bot chips
    def _html_bots(self, el, now):
        in_bots = self.stage == "bots" and not self.done
        chips = []
        for b in self.bots:
            lock = ""
            if b["blocked"]:
                lock = '<span class="cv-c-lock" title="Blocked in robots.txt">%s</span>' \
                       % icon("lock", 11, COL["warn"], 2.4)
            if b["ok"] is True:
                cls, ic = "cv-c-ok", icon("check", 13, COL["ok"], 2.6)
            elif b["ok"] is False:
                cls, ic = "cv-c-bad", icon("x", 13, COL["bad"], 2.6)
            elif in_bots:
                cls, ic = "cv-c-test", icon("loader", 13, COL["accent"], 2.4)
            else:
                cls, ic = "cv-c-pend", icon("circle", 11, COL["faint"], 2)
            style = ""
            if b["at"] is not None and now - b["at"] < CHIP_IN_S and not self.done:
                cls += " cv-c-in"
                style = ' style="animation-delay:%s"' % _age_delay(now - b["at"])
            elif cls.startswith("cv-c-test"):
                style = ' style="animation-delay:%s"' % _phase(el, 0.9)
            chips.append('<span class="cv-chip %s"%s>%s%s%s</span>'
                         % (cls, style, ic, _esc(b["token"]), lock))
        key = ('<div class="cv-bots-k"><span>%s can reach the site</span><span>%s turned away</span>'
               '<span>%s blocked in robots.txt</span></div>'
               % (icon("check", 12, COL["ok"], 2.6), icon("x", 12, COL["bad"], 2.6),
                  icon("lock", 11, COL["warn"], 2.4)))
        return ('<div class="cv-bots"><div class="cv-bots-h"><div class="cv-bots-t">%s Search and AI bots '
                'knocking on the door</div>%s</div><div class="cv-chips">%s</div></div>'
                % (icon("bot", 15, COL["accent"]), key, "".join(chips)))

    # checklist
    def _html_steps(self, el):
        cur = self.stage_keys.index(self.stage) if self.stage in self.stage_keys else -1
        rows = []
        for i, key in enumerate(self.stage_keys):
            label = _esc(self.stage_labels.get(key, key))
            dur = ""
            if self.done or i < cur:
                cls = "cv-st-done"
                ic = icon("check", 13, "currentColor", 2.8)
                if key in self.stage_start and key in self.stage_end:
                    d = max(0.0, self.stage_end[key] - self.stage_start[key])
                    dur = '<span class="cv-step-d">%.1f s</span>' % d
            elif i == cur:
                cls = "cv-st-now"
                ic = icon("loader", 16, COL["accent"], 2.4)
            else:
                cls = "cv-st-pend"
                ic = icon("circle", 15, "#cbd5e1", 2)
            style = ' style="animation-delay:%s"' % _phase(el, 0.9) if cls == "cv-st-now" else ""
            rows.append('<div class="cv-step %s"%s><span class="cv-step-ic">%s</span>'
                        '<span class="cv-step-t">%s</span>%s</div>' % (cls, style, ic, label, dur))
        return '<div class="cv-steps">%s</div>' % "".join(rows)

    # log
    def _html_log(self, now):
        lines = self.logs[-LOG_LINES:]
        rows = []
        for i, (t, text, level, wall) in enumerate(lines):
            lvl = level if level in ("ok", "warn") else "info"
            ic = {"ok": icon("check", 12, COL["ok"], 2.6), "warn": icon("alert", 12, COL["warn"], 2.4),
                  "info": icon("arrow-right", 12, COL["faint"], 2.4)}[lvl]
            cls = "cv-ln cv-ln-%s" % lvl
            style = ""
            age = now - wall
            if i == len(lines) - 1 and age < LOG_IN_S and not self.done:
                cls += " cv-ln-new"
                style = ' style="animation-delay:%s"' % _age_delay(age)
            rows.append('<div class="%s"%s><span class="cv-ln-t">%.1fs</span>%s<span class="cv-ln-x">%s</span></div>'
                        % (cls, style, t, ic, _esc(text)))
        if not rows:
            rows.append('<div class="cv-ln-empty">Waiting for the first response</div>')
        live = "Finished" if self.done else "Live"
        return ('<div class="cv-log"><div class="cv-log-h">%s Activity log<span class="cv-live"><i></i>%s</span></div>%s</div>'
                % (icon("terminal", 13, COL["faint"]), live, "".join(rows)))
