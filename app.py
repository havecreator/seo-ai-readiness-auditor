"""
SEO & AI Readiness Auditor
==========================
Industrial Training Project - Search Engine Optimization

Enter a website address and the tool:
  1. visits it the way Google and AI assistants do (engine.py), showing the crawl live
  2. scores 56 checks for Google search (SEO) and for AI assistants (GEO)
  3. explains every result in plain words (Simple mode) or with the exact rules (Complex mode)
  4. offers a downloadable report (report.py)

Run:  streamlit run app.py

Files: engine.py (crawler + checks), explanations.py (wording), ui.py (CSS + HTML pieces),
ui_crawl.py (live crawl animation), report.py (downloadable report), icons.py (SVG icons).
"""

import warnings

warnings.filterwarnings("ignore")  # hide harmless SSL / urllib3 warnings on macOS

import glob
import json
import os
from collections import Counter

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

import ui
from engine import STAGES, TIMEOUT, AuditError, Auditor, normalize_url
from explanations import AI_CATS, CATEGORIES, SEO_CATS

# Optional modules written in parallel. The app keeps working if one is missing or broken.
try:
    from ui_crawl import CRAWL_CSS, CrawlView
except Exception:  # noqa: BLE001
    CrawlView, CRAWL_CSS = None, ""
try:
    from report import build_report as _build_report
except Exception:  # noqa: BLE001
    _build_report = None

EXAMPLES = ["python.org", "moz.com/learn/seo", "bbc.com", "example.com"]

st.set_page_config(page_title="SEO & AI Readiness Auditor", page_icon=":material/travel_explore:",
                   layout="wide")
st.markdown(ui.CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Developer hook: ?demo=bbc loads a saved result instead of crawling.
# Only active when the SEO_AUDIT_SAMPLES environment variable points to a folder with
# sample_result_*.json files, so normal users never see it.
# ---------------------------------------------------------------------------
def load_demo():
    folder = os.environ.get("SEO_AUDIT_SAMPLES")
    name = st.query_params.get("demo")
    if not folder or not name or st.session_state.get("demo_loaded") == name:
        return
    files = sorted(glob.glob(os.path.join(folder, "sample_result_*%s*.json" % name.replace("/", ""))))
    if files:
        with open(files[0], encoding="utf-8") as fh:
            st.session_state["res"] = json.load(fh)
        st.session_state["res_id"] = st.session_state.get("res_id", 0) + 1
        st.session_state.pop("error", None)
    st.session_state["demo_loaded"] = name


load_demo()


# ---------------------------------------------------------------------------
# Running an audit
# ---------------------------------------------------------------------------
class SimpleCrawlView:
    """Fallback progress display used when ui_crawl.py is not available."""

    def __init__(self, url):
        self.labels = dict(STAGES)
        self.status = st.status("Auditing %s" % ui.md_escape(url), expanded=True)
        with self.status:
            self.box = st.empty()
        self.lines = []

    def handle(self, ev):
        kind = ev.get("kind")
        if kind == "stage":
            self.status.update(label=self.labels.get(ev.get("key"), "Working"))
        elif kind == "log":
            self.lines.append("%5.1fs  %s" % (ev.get("t", 0), ev.get("text", "")))
            self.box.code("\n".join(self.lines[-14:]), language=None)

    def finish(self):
        self.status.update(label="Audit finished", state="complete", expanded=False)


def friendly_error(exc, url):
    """-> (title, message, hint) in plain words."""
    if isinstance(exc, AuditError):
        return "This site could not be audited", str(exc), ""
    if isinstance(exc, requests.exceptions.SSLError):
        text = str(exc).upper()
        if "PROTOCOL_VERSION" in text or "HANDSHAKE" in text:
            return ("Secure connection failed",
                    "This site only accepts a newer TLS version than this computer's Python supports.",
                    "Run the app with Python 3.10 or newer from python.org, or try another address.")
        return ("Secure connection failed",
                "A secure HTTPS connection to the site could not be made.",
                "Try the http:// version of the address.")
    if isinstance(exc, requests.exceptions.Timeout):
        return ("The website did not answer in time",
                "The website took longer than %d seconds to respond." % TIMEOUT,
                "Try again in a moment, or try another address.")
    if isinstance(exc, (requests.exceptions.InvalidURL, requests.exceptions.MissingSchema,
                        requests.exceptions.InvalidSchema, UnicodeError)):
        return ("That address does not look right",
                "“%s” does not look like a valid web address." % url,
                "Example: https://example.com")
    if isinstance(exc, requests.exceptions.ConnectionError):
        return ("Could not connect",
                "Could not connect to %s." % url,
                "Check the spelling of the address and your internet connection.")
    return "The audit stopped unexpectedly", "Audit failed: %s" % str(exc)[:300], ""


def run_audit(url):
    """Crawl `url` with the live animation, store the result and rerun to show it."""
    opts = dict(max_pages=st.session_state.get("opt_pages", 12),
                check_links=st.session_state.get("opt_links", True),
                screenshots=st.session_state.get("opt_shots", True))
    view, ph = None, None
    if CrawlView is not None:
        try:
            if CRAWL_CSS:
                st.markdown(CRAWL_CSS, unsafe_allow_html=True)
            ph = st.empty()
            view = CrawlView(ph, url)
        except Exception:  # noqa: BLE001
            view = None
    if view is None:
        view = SimpleCrawlView(url)
    # Hide the previous page (landing or old results) below the animation while it runs.
    marker = st.empty()
    marker.markdown('<div class="run-end"></div><style>[data-stale="true"],'
                    '[data-testid="stElementContainer"]:has(.run-end) ~ *{display:none !important;}</style>',
                    unsafe_allow_html=True)
    try:
        res = Auditor(url, min_seconds=10, progress=view.handle, **opts).run()
    except Exception as exc:  # noqa: BLE001 - every problem becomes a friendly message
        try:
            marker.empty()
            getattr(view, "stop", view.finish)()
            if ph is not None:
                ph.empty()  # remove the half-finished animation
        except Exception:  # noqa: BLE001
            pass
        st.session_state["error"] = friendly_error(exc, url)
        st.session_state.pop("res", None)
        return
    try:
        view.finish()
    except Exception:  # noqa: BLE001
        pass
    st.session_state["res"] = res
    st.session_state["res_id"] = st.session_state.get("res_id", 0) + 1
    st.session_state.pop("error", None)
    st.rerun()


def queue_example(addr):
    st.session_state["url_in"] = addr
    st.session_state["run_url"] = addr


# ---------------------------------------------------------------------------
# Header and search
# ---------------------------------------------------------------------------
h_left, h_right = st.columns([4.2, 1.5], vertical_alignment="center")
h_left.markdown(ui.app_header(), unsafe_allow_html=True)
with h_right, st.container(horizontal=True, horizontal_alignment="right"):
    st.toggle("Complex mode", key="complex",
              help="Shows technical names, weights, the exact rules and raw data such as HTTP "
                   "headers and robots.txt.")
cx = bool(st.session_state.get("complex"))

st.write("")
with st.form("search", border=True):
    c_in, c_btn = st.columns([5, 1], vertical_alignment="bottom")
    url_in = c_in.text_input("Website address", key="url_in", placeholder="https://example.com",
                             label_visibility="collapsed")
    submitted = c_btn.form_submit_button("Analyze", type="primary", icon=":material/search:",
                                         width="stretch")
    with st.expander("Options", icon=":material/tune:"):
        o1, o2 = st.columns([2, 1.4])
        o1.slider("Pages to crawl", 5, 20, 12, key="opt_pages",
                  help="How many pages of the site to visit, including the main page.")
        with o2:
            st.checkbox("Check outgoing links", True, key="opt_links",
                        help="Tests up to 15 links to other websites for errors.")
            st.checkbox("Capture screenshots", True, key="opt_shots",
                        help="Desktop and phone screenshots using Chrome or Edge, if installed.")

with st.container(horizontal=True, gap="small", vertical_alignment="center"):
    st.markdown('<div class="ui examples-label">Try an example:</div>', unsafe_allow_html=True,
                width="content")
    for ex in EXAMPLES:
        st.button(ex, key="ex_" + ex, on_click=queue_example, args=(ex,), type="tertiary",
                  icon=":material/arrow_outward:")

run_url = st.session_state.pop("run_url", None)
if submitted:
    run_url = url_in
if run_url is not None:
    run_audit(normalize_url(run_url))

err = st.session_state.get("error")
if err:
    st.markdown(ui.banner("bad", *err), unsafe_allow_html=True)

res = st.session_state.get("res")


# ---------------------------------------------------------------------------
# Landing page
# ---------------------------------------------------------------------------
def render_landing():
    head, body = ui.landing(ui.check_counts())
    st.markdown(head, unsafe_allow_html=True)
    st.markdown(body, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Result tabs
# ---------------------------------------------------------------------------
FILTERS = ["All", "Problems", "Passed"]


def filter_checks(checks, mode):
    if mode == "Problems":
        return [c for c in checks if c["status"] in ("fail", "warn")]
    if mode == "Passed":
        return [c for c in checks if c["status"] == "pass"]
    return list(checks)


def render_checks(res, checks, cats, key):
    scored = [c for c in checks if c["status"] != "info"]
    passed = sum(1 for c in scored if c["status"] == "pass")
    probs = sum(1 for c in scored if c["status"] in ("fail", "warn"))
    left, right = st.columns([3, 2], vertical_alignment="center")
    left.markdown('<div class="ui note" style="font-size:14.5px"><b style="color:#0f172a">%d of %d</b> checks '
                  'look good, <b style="color:#0f172a">%d</b> need a look.</div>' % (passed, len(scored), probs),
                  unsafe_allow_html=True)
    with right:
        mode = st.segmented_control("Show", FILTERS, default="All", key=key,
                                    label_visibility="collapsed") or "All"
    shown_any = False
    for cat in cats:
        in_cat = [c for c in checks if c["cat"] == cat]
        visible = filter_checks(in_cat, mode)
        if not visible:
            continue
        shown_any = True
        st.markdown(ui.cat_header(cat, res.get("cat_scores", {}).get(cat, 0), in_cat, cx),
                    unsafe_allow_html=True)
        st.markdown(ui.cards(visible, cx), unsafe_allow_html=True)
    if not shown_any:
        st.markdown('<div class="ui empty">Nothing matches this filter.</div>', unsafe_allow_html=True)


def tab_overview(res):
    left, right = st.columns([1.35, 1], gap="large")
    with left:
        issues = ui.top_issues(res, 6)
        st.markdown(ui.section("Fix these first", "The changes that would raise the score the most.",
                               "flag"), unsafe_allow_html=True)
        st.markdown(ui.fix_list(issues, cx), unsafe_allow_html=True)
    with right:
        st.markdown(ui.section("Score by area", "Each area is scored out of 100.", "bar-chart"),
                    unsafe_allow_html=True)
        st.markdown('<div class="ui card"><div class="grouplabel" style="margin-top:0">Google search</div>%s'
                    '<div class="grouplabel">AI assistants</div>%s</div>'
                    % (ui.cat_bars(res, SEO_CATS, cx), ui.cat_bars(res, AI_CATS, cx)),
                    unsafe_allow_html=True)
        st.write("")
        st.markdown(ui.section("What's working", "", "check-circle"), unsafe_allow_html=True)
        st.markdown(ui.good_list(ui.top_passes(res, 6), cx), unsafe_allow_html=True)

    st.write("")
    if cx:
        with st.expander("How the score is calculated", icon=":material/calculate:"):
            st.markdown(
                "Each check has a **weight** (how many points it is worth). *Pass* earns the full "
                "weight, *Warning* half, *Fail* nothing; *Info* checks are not counted.  \n"
                "Score = points earned / points possible x 100, calculated separately for SEO "
                "(%d) and AI readiness (%d). Overall = the average of the two (%d)."
                % (res["seo_score"], res["ai_score"], res["overall"]))
            rows = [{"Score": "SEO" if c["cat"] in SEO_CATS else "AI readiness",
                     "Area": CATEGORIES[c["cat"]][1], "Check": c["name"],
                     "Status": ui.status_word(c["status"], True), "Weight": c["weight"],
                     "Earned": c.get("earned", 0), "Value": str(c["value"])}
                    for c in ui.all_checks(res)]
            df = pd.DataFrame(rows)
            st.dataframe(df, hide_index=True, width="stretch",
                         height=min(36 * (len(df) + 1) + 4, 640),
                         column_config={"Weight": st.column_config.NumberColumn(format="%d"),
                                        "Earned": st.column_config.NumberColumn(format="%.1f")})
            tot = df.groupby("Score")[["Weight", "Earned"]].sum()
            st.caption(" | ".join("%s: %.1f of %d points" % (k, v["Earned"], v["Weight"])
                                  for k, v in tot.iterrows()))
    else:
        st.markdown('<div class="ui note">How scoring works: every check is worth some points. '
                    '<b>Good</b> earns all of them, <b>Could be better</b> half, <b>Needs fixing</b> '
                    'none. Switch on Complex mode to see the exact maths.</div>', unsafe_allow_html=True)


def tab_ai(res):
    st.markdown('<div class="ui soft geo">%s<p>%s</p></div>' % (ui.icon("brain", 24, "#2563eb"), ui.GEO_TEXT),
                unsafe_allow_html=True)
    st.write("")
    bots = res.get("bots", [])
    st.markdown(ui.section("Can AI assistants read this site?",
                           "Two tests per bot: what the site's robots.txt rules say, and whether the "
                           "page actually opened when we visited using that bot's name.", "bot"),
                unsafe_allow_html=True)
    if not (res.get("robots") or {}).get("found"):
        st.markdown(ui.banner("info", "No robots.txt rules found",
                              "Without a robots.txt file every bot is allowed by default."),
                    unsafe_allow_html=True)
    if cx:
        rows = [{"Bot": b["label"], "Token": b["token"], "Company": b["company"],
                 "Purpose": b["purpose"], "Scored": "yes" if b["robots_scored"] else "no",
                 "Answer bot": "yes" if b["answer_bot"] else "no",
                 "robots.txt": "allow" if b["robots_allowed"] else "disallow",
                 "Live HTTP": b.get("live_status"),
                 "Time (ms)": round(b["live_time"] * 1000) if b.get("live_time") else None,
                 "Reachable": ("-" if not b.get("live_tested") else
                               "yes" if b.get("live_reachable") else "no"),
                 "Note": b.get("live_note") or ""}
                for b in bots]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     height=36 * (len(rows) + 1) + 4,
                     column_config={"Live HTTP": st.column_config.NumberColumn(format="%d"),
                                    "Time (ms)": st.column_config.NumberColumn(format="%d")})
        st.caption("Scored = counts toward the robots.txt check (ai_robots). Answer bot = used for "
                   "the live reachability check (ai_firewall). Tokens without a real crawler "
                   "(Google-Extended, Applebot-Extended) are only checked against robots.txt.")
    else:
        answer = [b for b in bots if b.get("robots_scored")]
        training = [b for b in bots if not b.get("robots_scored")]
        st.markdown('<div class="ui grouplabel">Search engines and AI assistants that can quote you</div>',
                    unsafe_allow_html=True)
        st.markdown(ui.bot_table(answer), unsafe_allow_html=True)
        st.markdown('<div class="ui grouplabel">Bots that collect text to train AI models (not scored)</div>',
                    unsafe_allow_html=True)
        st.markdown(ui.bot_table(training), unsafe_allow_html=True)
        st.markdown('<div class="ui note" style="margin-top:8px">Blocking training bots is a business '
                    'choice and does not lower the score. Blocking the assistants above means they '
                    'cannot show or quote this site.</div>', unsafe_allow_html=True)
    st.write("")
    render_checks(res, res.get("ai", []), AI_CATS, "flt_ai")


def tab_pages(res):
    pages = res.get("pages", [])
    with_probs = sum(1 for p in pages if any(t in ("bad", "warn") for t, _ in ui.page_problems(p)))
    st.markdown(ui.section("Pages crawled",
                           "We opened %d page%s of this site, starting from the address you entered. "
                           "%d %s something to fix." % (len(pages), "" if len(pages) == 1 else "s",
                                                         with_probs, "has" if with_probs == 1 else "have"),
                           "sitemap"), unsafe_allow_html=True)
    if not cx:
        st.markdown(ui.page_list(pages), unsafe_allow_html=True)
        return
    rows = [{"Path": p.get("path"), "Status": p.get("status"),
             "Time (s)": round(p["time"], 2) if p.get("time") else None,
             "Size (KB)": round(p.get("size_kb") or 0, 1), "Title": p.get("title"),
             "Title len": len(p.get("title") or ""), "Desc len": len(p.get("meta_desc") or ""),
             "H1": p.get("h1"), "Words": p.get("words"), "Images": p.get("imgs"),
             "No alt": p.get("imgs_no_alt"), "Canonical": p.get("canonical"),
             "Noindex": bool(p.get("noindex")), "Blocked": bool(p.get("blocked")),
             "Error": p.get("error") or "", "URL": p.get("url")}
            for p in pages]
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, width="stretch", height=min(35 * (len(df) + 1) + 4, 560),
                 column_config={"URL": st.column_config.LinkColumn(),
                                "Status": st.column_config.NumberColumn(format="%d"),
                                "Time (s)": st.column_config.NumberColumn(format="%.2f")})
    timed = df.dropna(subset=["Time (s)"])
    if not timed.empty:
        st.markdown(ui.section("Response time per page", "Seconds to download each page's HTML.",
                               "clock"), unsafe_allow_html=True)
        time_chart(timed)
    ok = [p for p in pages if p.get("status") and p["status"] < 400 and not p.get("error")]
    groups = []
    for field, label in (("title", "title"), ("meta_desc", "description")):
        counts = Counter(p.get(field) for p in ok if p.get(field))
        for value, n in counts.items():
            if n > 1:
                groups.append({"Shared": label, "Text": value, "Pages": n,
                               "Paths": ", ".join(p["path"] for p in ok if p.get(field) == value)})
    st.markdown(ui.section("Duplicate titles and descriptions",
                           "Pages that share exactly the same text.", "layers"), unsafe_allow_html=True)
    if groups:
        st.dataframe(pd.DataFrame(groups), hide_index=True, width="stretch")
    else:
        st.markdown('<div class="ui empty">No duplicates among the crawled pages.</div>',
                    unsafe_allow_html=True)


def time_chart(df):
    """Horizontal bars, slowest page first, coloured like the rest of the app."""
    try:
        import altair as alt

        data = df[["Path", "Time (s)"]].copy()
        data["Speed"] = data["Time (s)"].map(lambda t: "Fast (under 1.5 s)" if t < 1.5 else
                                             ("Slow (1.5 to 3 s)" if t < 3 else "Very slow (3 s or more)"))
        chart = alt.Chart(data).mark_bar(cornerRadiusEnd=4, height=18).encode(
            x=alt.X("Time (s):Q", title="Seconds", scale=alt.Scale(domainMin=0)),
            y=alt.Y("Path:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260)),
            color=alt.Color("Speed:N", title=None, legend=alt.Legend(orient="top"),
                            scale=alt.Scale(domain=["Fast (under 1.5 s)", "Slow (1.5 to 3 s)",
                                                    "Very slow (3 s or more)"],
                                            range=["#059669", "#d97706", "#dc2626"])),
            tooltip=["Path", "Time (s)"],
        ).properties(height=max(160, 26 * len(data) + 40))
        st.altair_chart(chart, use_container_width=True)
    except Exception:  # noqa: BLE001 - fall back to the built-in chart
        st.bar_chart(df.set_index("Path")[["Time (s)"]], horizontal=True, color="#2563eb")


def tab_details(res):
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown(ui.section("On Google", "Roughly how the page appears in search results.", "search"),
                    unsafe_allow_html=True)
        st.markdown(ui.google_preview(res), unsafe_allow_html=True)
    with c2:
        st.markdown(ui.section("When shared", "The preview card on WhatsApp, LinkedIn or Slack.", "share"),
                    unsafe_allow_html=True)
        st.markdown(ui.share_preview(res), unsafe_allow_html=True)

    st.write("")
    st.markdown(ui.section("Screenshots", "Captured with a real browser at desktop and phone size.",
                           "monitor"), unsafe_allow_html=True)
    s1, s2 = st.columns([3, 1], gap="large")
    s1.markdown(ui.shot_desktop(res), unsafe_allow_html=True)
    s2.markdown(ui.shot_mobile(res), unsafe_allow_html=True)

    st.write("")
    images = res.get("images", [])
    items = ui.unique_images(images)
    described = sum(1 for i in images if i.get("has_alt"))
    g_left, g_right = st.columns([3, 2], vertical_alignment="bottom")
    g_left.markdown(ui.section("Images on this page",
                               "%d images, %d with a description (alt text) and %d without."
                               % (len(images), described, len(images) - described), "image"),
                    unsafe_allow_html=True)
    with g_right:
        flt = st.segmented_control("Images", ["All", "No description", "Described"], default="All",
                                   key="flt_img", label_visibility="collapsed") or "All"
    if flt == "No description":
        items = [(i, n) for i, n in items if not i.get("has_alt")]
    elif flt == "Described":
        items = [(i, n) for i, n in items if i.get("has_alt")]
    limit = 48
    st.markdown(ui.gallery(items[:limit], cx), unsafe_allow_html=True)
    if len(items) > limit:
        st.caption("Showing the first %d of %d different images." % (limit, len(items)))

    st.write("")
    heads = res.get("headings", [])
    st.markdown(ui.section("Heading outline", "The page's table of contents, as Google reads it.",
                           "heading", right=ui.heading_summary(heads)), unsafe_allow_html=True)
    st.markdown(ui.heading_outline(heads), unsafe_allow_html=True)

    if cx:
        st.write("")
        st.markdown(ui.section("Technical details", "Raw data collected during the audit.", "code"),
                    unsafe_allow_html=True)
        render_raw(res)


def render_raw(res):
    e = ui.esc
    with st.expander("HTTP response and redirects", icon=":material/http:", expanded=True):
        st.markdown(ui.kv([
            ("Status", "%s %s" % (e(res.get("status_code")), e(res.get("reason", "")))),
            ("Final URL", e(res.get("final_url"))),
            ("Time to first byte", "%.3f s" % (res.get("ttfb") or 0)),
            ("Full download", "%.3f s" % (res.get("load_time") or 0)),
            ("HTML size", "%.1f KB" % (res.get("size_kb") or 0)),
            ("Certificate verified", "yes" if res.get("ssl_ok") else "no"),
            ("Canonical", e(res.get("canonical") or "-")),
            ("lang", e(res.get("lang") or "-")),
            ("Viewport", e(res.get("viewport") or "-")),
            ("Robots meta / X-Robots-Tag", e(res.get("robots_meta") or "-")),
            ("hreflang", e(", ".join(res.get("hreflang") or []) or "-")),
            ("Twitter card", e(res.get("twitter_card") or "-")),
        ]), unsafe_allow_html=True)
        st.markdown('<div class="ui grouplabel">Redirect chain</div>', unsafe_allow_html=True)
        st.markdown(ui.redirect_chain(res.get("redirect_chain") or []), unsafe_allow_html=True)
    with st.expander("Response headers", icon=":material/list_alt:"):
        hdrs = res.get("headers") or {}
        st.dataframe(pd.DataFrame([{"Header": k, "Value": v} for k, v in hdrs.items()]),
                     hide_index=True, width="stretch")
    with st.expander("Open Graph tags", icon=":material/share:"):
        st.dataframe(pd.DataFrame([{"Tag": k, "Value": v or "(missing)"}
                                   for k, v in (res.get("og") or {}).items()]),
                     hide_index=True, width="stretch")
    rob = res.get("robots") or {}
    with st.expander("robots.txt", icon=":material/rule:"):
        if rob.get("found"):
            st.caption("%d rule groups, %d sitemap line(s)" % (rob.get("groups", 0), len(rob.get("sitemaps") or [])))
            st.code(rob.get("text") or "", language=None)
        else:
            st.write("Not found (HTTP %s)." % (rob.get("status") or "no answer"))
    sm = res.get("sitemap") or {}
    with st.expander("Sitemap", icon=":material/account_tree:"):
        if sm.get("url"):
            st.markdown(ui.kv([("Sitemap", e(sm["url"])), ("Pages listed", ui.fmt_int(sm.get("count", 0))),
                               ("Child sitemaps", ui.fmt_int(sm.get("children", 0))),
                               ("Last modified", e(sm.get("lastmod") or "-"))]), unsafe_allow_html=True)
            if sm.get("sample"):
                st.dataframe(pd.DataFrame({"First URLs listed": sm["sample"][:50]}), hide_index=True,
                             width="stretch", height=260)
        else:
            st.write("No sitemap found at the robots.txt Sitemap: lines, /sitemap.xml or /sitemap_index.xml.")
    llms = res.get("llms") or {}
    with st.expander("llms.txt", icon=":material/description:"):
        if llms.get("found"):
            st.code(llms.get("text") or "", language="markdown")
        else:
            st.write("Not found.")
    with st.expander("Structured data (JSON-LD)", icon=":material/data_object:"):
        st.write("Types found: " + (", ".join(res.get("schema_types") or []) or "none"))
        for block in res.get("jsonld") or []:
            st.code(block, language="json")
    rs = res.get("resources") or {}
    with st.expander("Resources and render-blocking scripts", icon=":material/speed:"):
        st.markdown(ui.kv([("External scripts", rs.get("scripts", 0)), ("Inline scripts", rs.get("inline_scripts", 0)),
                           ("Stylesheets", rs.get("stylesheets", 0)), ("Images", rs.get("images", 0)),
                           ("iframes", rs.get("iframes", 0)),
                           ("Render-blocking scripts", len(rs.get("blocking") or [])),
                           ("Mixed-content files", len(res.get("mixed") or []))]), unsafe_allow_html=True)
        if rs.get("blocking"):
            st.dataframe(pd.DataFrame({"Blocking script in <head>": rs["blocking"]}), hide_index=True,
                         width="stretch")
        if res.get("mixed"):
            st.dataframe(pd.DataFrame({"Insecure http:// file": res["mixed"]}), hide_index=True,
                         width="stretch")
    with st.expander("Links", icon=":material/link:"):
        l1, l2 = st.columns(2)
        l1.dataframe(pd.DataFrame({"Internal links (%d)" % len(res.get("internal", [])): res.get("internal", [])}),
                     hide_index=True, width="stretch", height=300)
        l2.dataframe(pd.DataFrame({"External links (%d)" % len(res.get("external", [])): res.get("external", [])}),
                     hide_index=True, width="stretch", height=300)
        if res.get("link_results"):
            def verdict(s):
                if s is None or s in (404, 410) or s >= 500:
                    return "broken"
                return "restricted" if s >= 400 else "ok"
            st.caption("Outgoing link check")
            st.dataframe(pd.DataFrame([{"URL": u, "Status": s if s else None, "Result": verdict(s)}
                                       for u, s in res["link_results"]]),
                         hide_index=True, width="stretch",
                         column_config={"Status": st.column_config.NumberColumn(format="%d")})
        if res.get("link_unverified"):
            st.caption("Links that could not be checked (not counted as broken)")
            st.dataframe(pd.DataFrame([{"URL": u, "Reason": note} for u, note in res["link_unverified"]]),
                         hide_index=True, width="stretch")


def get_report(res):
    """Build the HTML report once per result (falls back to a minimal report)."""
    key = st.session_state.get("res_id", 0)
    cached = st.session_state.get("report_cache")
    if cached and cached[0] == key:
        return cached[1], cached[2]
    html_text, problem = None, None
    if _build_report is not None:
        try:
            html_text = _build_report(res)
        except Exception as exc:  # noqa: BLE001
            problem = "The full report could not be built (%s), so a short version is offered." % type(exc).__name__
    else:
        problem = "report.py is not available, so a short version of the report is offered."
    if not html_text:
        html_text = minimal_report(res)
    st.session_state["report_cache"] = (key, html_text, problem)
    return html_text, problem


def minimal_report(res):
    e = ui.esc
    rows = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                   % (e(ui.status_word(c["status"])), e(c["plain"]), e(c["value"]),
                      "" if c["status"] == "pass" else e(c["fix"])) for c in ui.all_checks(res))
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Audit %s</title>"
            "<style>body{font-family:Arial,sans-serif;max-width:960px;margin:24px auto;color:#0f172a}"
            "td,th{border-bottom:1px solid #e2e8f0;padding:6px;text-align:left;vertical-align:top}"
            "table{border-collapse:collapse;width:100%%}</style></head><body><h1>SEO &amp; AI readiness: %s</h1>"
            "<p>SEO %d, AI readiness %d, overall %d. Audited %s.</p><table><tr><th>Status</th><th>Check</th>"
            "<th>Found</th><th>Fix</th></tr>%s</table></body></html>"
            % (e(res.get("domain")), e(res.get("final_url")), res.get("seo_score", 0), res.get("ai_score", 0),
               res.get("overall", 0), e(res.get("audited_at")), rows))


def tab_report(res):
    st.markdown(ui.report_intro(), unsafe_allow_html=True)
    st.write("")
    html_text, problem = get_report(res)
    if problem:
        st.markdown(ui.banner("warn", "Short report", problem), unsafe_allow_html=True)
    fname = "seo-ai-report-%s.html" % (res.get("domain") or "site").replace(":", "_")
    b1, b2, _ = st.columns([1.2, 1.2, 2])
    b1.download_button("Download report (HTML)", html_text, file_name=fname, mime="text/html",
                       type="primary", icon=":material/download:", on_click="ignore",
                       width="stretch")
    if cx:
        export = {k: v for k, v in res.items() if k != "shots"}
        b2.download_button("Download raw data (JSON)", json.dumps(export, indent=2, default=str),
                           file_name=fname.replace(".html", ".json"), mime="application/json",
                           icon=":material/data_object:", on_click="ignore", width="stretch")
    with st.expander("Preview the report", icon=":material/visibility:"):
        components.html(html_text, height=760, scrolling=True)


def render_results(res):
    if not res.get("ssl_ok", True):
        st.markdown(ui.banner("warn", "Certificate could not be verified",
                              "This site's HTTPS certificate is expired or incomplete. The audit "
                              "continued anyway, but browsers and crawlers may distrust the site."),
                    unsafe_allow_html=True)
    st.markdown(ui.results_header(res, cx), unsafe_allow_html=True)
    st.markdown(ui.facts_row(res), unsafe_allow_html=True)
    tabs = st.tabs([":material/dashboard: Overview", ":material/travel_explore: SEO",
                    ":material/smart_toy: AI search", ":material/account_tree: Pages crawled",
                    ":material/web: Page details", ":material/download: Report"])
    with tabs[0]:
        tab_overview(res)
    with tabs[1]:
        render_checks(res, res.get("seo", []), SEO_CATS, "flt_seo")
    with tabs[2]:
        tab_ai(res)
    with tabs[3]:
        tab_pages(res)
    with tabs[4]:
        tab_details(res)
    with tabs[5]:
        tab_report(res)


st.write("")
if res:
    render_results(res)
else:
    render_landing()
