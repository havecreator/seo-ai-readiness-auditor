"""
Plain-language and technical explanations for every check.

Each check has:
  name    – the technical SEO term (shown in Complex mode)
  plain   – the everyday-words name (shown in Simple mode)
  cat     – category key
  weight  – points the check is worth in its score
  why     – why it matters, in simple words
  fix     – what to do about it, in simple words
  tech    – the exact rule the tool applies (shown in Complex mode)

Keeping all wording in one file makes it easy to review, translate or adjust thresholds.
"""

# Category keys -> (simple title, technical title, icon name)
CATEGORIES = {
    "content":  ("Your content", "On-page content", "file"),
    "tech":     ("Technical setup", "Technical SEO", "settings"),
    "speed":    ("Speed", "Performance", "zap"),
    "security": ("Security", "Security", "shield"),
    "social":   ("Sharing and rich results", "Social & structured data", "share"),
    "links":    ("Links", "Link profile", "link"),
    "site":     ("Whole-site health", "Site-wide crawl", "sitemap"),
    "ai_access": ("Can AI reach you?", "AI crawler access", "bot"),
    "ai_understand": ("Can AI understand you?", "AI content extractability", "brain"),
    "ai_trust": ("Will AI trust you?", "Trust and E-E-A-T signals", "badge"),
}

SEO_CATS = ["content", "tech", "speed", "security", "social", "links", "site"]
AI_CATS = ["ai_access", "ai_understand", "ai_trust"]

STATUS_TEXT = {
    "pass": ("Good", "Pass"),
    "warn": ("Could be better", "Warning"),
    "fail": ("Needs fixing", "Fail"),
    "info": ("For your information", "Info"),
}

CHECKS = {
    # ---------------- Content ----------------
    "title": dict(
        name="Title tag", plain="Page title on Google", cat="content", weight=10,
        why="This is the blue headline people see in Google results. A clear title gets more clicks.",
        fix="Write a title of 30 to 60 characters that starts with what the page is about.",
        tech="<title> length 30–60 chars = pass; any other length = warn; missing = fail."),
    "meta_desc": dict(
        name="Meta description", plain="Short description on Google", cat="content", weight=8,
        why="The grey text under your Google headline. It is your chance to convince people to click.",
        fix="Add a 70 to 160 character summary of the page.",
        tech='<meta name="description"> length 70–160 = pass; other length = warn; missing = fail.'),
    "h1": dict(
        name="H1 heading", plain="Main heading", cat="content", weight=7,
        why="Each page needs one main heading that says what it is about, like a chapter title.",
        fix="Use exactly one H1 heading on the page.",
        tech="count(<h1>) == 1 = pass; more than 1 = warn; none = fail."),
    "h2": dict(
        name="H2 subheadings", plain="Section headings", cat="content", weight=4,
        why="Sub-headings split the page into sections so people and Google can scan it.",
        fix="Add an H2 heading for each main section of the page.",
        tech="at least one <h2> = pass."),
    "heading_order": dict(
        name="Heading hierarchy", plain="Headings in the right order", cat="content", weight=3,
        why="Headings should go in order (H1, then H2, then H3), like a table of contents.",
        fix="Don't skip levels, for example from H1 straight to H4.",
        tech="no jump of more than one level between consecutive headings = pass; 1–2 jumps = warn."),
    "word_count": dict(
        name="Content length", plain="Amount of text", cat="content", weight=7,
        why="Pages with very little text rarely rank. Google needs words to understand the topic.",
        fix="Aim for at least 600 useful words on important pages.",
        tech="visible words ≥ 600 = pass; 300–599 = warn; < 300 = fail."),
    "title_match": dict(
        name="Title / content relevance", plain="Title matches the content", cat="content", weight=4,
        why="The words in your title should also appear in the main heading or first paragraph, "
            "so the page delivers what the title promises.",
        fix="Repeat the main topic words from the title in the H1 and the opening paragraph.",
        tech="≥ 50% of title keywords (stop-words removed) appear in H1 + first 150 words = pass; "
             "≥ 25% = warn."),
    "alt_text": dict(
        name="Image alt attributes", plain="Image descriptions", cat="content", weight=6,
        why="Google cannot see pictures. Alt text tells it, and blind visitors, what each image shows.",
        fix="Add a short alt description to every meaningful image.",
        tech="alt coverage ≥ 90% = pass; ≥ 50% = warn; else fail. No images = pass."),

    # ---------------- Technical ----------------
    "https": dict(
        name="HTTPS / TLS", plain="Secure connection (padlock)", cat="tech", weight=6,
        why="Google prefers secure sites, and browsers warn visitors about insecure ones.",
        fix="Install a valid SSL certificate, including the full certificate chain.",
        tech="final URL is https and the certificate verifies = pass; unverifiable cert = warn; "
             "http = fail."),
    "viewport": dict(
        name="Mobile viewport", plain="Works on mobile phones", cat="tech", weight=7,
        why="Most searches happen on phones, and Google ranks the mobile version of your site.",
        fix='Add <meta name="viewport" content="width=device-width, initial-scale=1">.',
        tech="viewport meta with width=device-width = pass; fixed width = warn; missing = fail."),
    "canonical": dict(
        name="Canonical URL", plain="Preferred address set", cat="tech", weight=4,
        why="If one page opens at several addresses, this tells Google which one is the real one.",
        fix="Add a canonical link that points to the page's main address.",
        tech='<link rel="canonical"> present and pointing to this page = pass; points elsewhere or '
             "missing = warn."),
    "lang": dict(
        name="HTML lang attribute", plain="Language declared", cat="tech", weight=2,
        why="Tells Google and screen readers which language the page is written in.",
        fix='Add lang="en" (or your language) to the <html> tag.',
        tech="<html lang> present = pass."),
    "indexable": dict(
        name="Indexability", plain="Allowed to appear on Google", cat="tech", weight=8,
        why="A 'noindex' instruction hides the page from Google completely.",
        fix="Remove noindex if this page should appear in search results.",
        tech="no 'noindex' in meta robots, meta googlebot or X-Robots-Tag header = pass."),
    "robots": dict(
        name="robots.txt", plain="Instructions for search bots", cat="tech", weight=3,
        why="A small file that tells search bots which parts of the site they may visit.",
        fix="Create /robots.txt and list your sitemap in it.",
        tech="/robots.txt returns 200 with plain text (not an HTML error page) = pass."),
    "sitemap": dict(
        name="XML sitemap", plain="List of all your pages", cat="tech", weight=4,
        why="A sitemap helps Google discover every page quickly, including new ones.",
        fix="Publish sitemap.xml and submit it in Google Search Console.",
        tech="Sitemap: line in robots.txt, /sitemap.xml or /sitemap_index.xml with <urlset>/"
             "<sitemapindex> = pass."),
    "redirects": dict(
        name="Redirect chain", plain="Redirects", cat="tech", weight=3,
        why="Each redirect is an extra hop that slows visitors down and wastes Google's time.",
        fix="Link straight to the final address and keep to one redirect at most.",
        tech="0–1 redirect hops = pass; 2 = warn; 3 or more = fail."),
    "url": dict(
        name="URL structure", plain="Clean web address", cat="tech", weight=2,
        why="Short, readable addresses are easier to trust, share and remember.",
        fix="Use short lowercase addresses with hyphens instead of codes or underscores.",
        tech="length < 100, lowercase path, no underscores, ≤ 2 query parameters = pass."),
    "favicon": dict(
        name="Favicon", plain="Site icon", cat="tech", weight=1,
        why="Google shows this small icon next to your result on mobile.",
        fix="Add a favicon to the site.",
        tech='<link rel="icon"> or /favicon.ico present = pass.'),

    # ---------------- Speed ----------------
    "ttfb": dict(
        name="Time to first byte (TTFB)", plain="Server response speed", cat="speed", weight=6,
        why="How fast the server starts answering. A slow server makes every page slow.",
        fix="Use page caching, better hosting or a CDN.",
        tech="TTFB < 0.8 s = pass; < 1.8 s = warn; else fail (Google's 'good' threshold is 0.8 s)."),
    "html_size": dict(
        name="HTML document size", plain="Page code size", cat="speed", weight=2,
        why="Huge pages take longer to download, especially on mobile data.",
        fix="Remove unused code and large inline scripts or styles.",
        tech="HTML < 200 KB = pass; < 500 KB = warn; else fail."),
    "compression": dict(
        name="Text compression", plain="Compression switched on", cat="speed", weight=3,
        why="Compressing the page makes it download several times faster.",
        fix="Turn on gzip or brotli compression on the web server.",
        tech="Content-Encoding is gzip, br, zstd or deflate = pass (pages under 1.4 KB also pass)."),
    "render_blocking": dict(
        name="Render-blocking scripts", plain="Scripts that delay the page", cat="speed", weight=4,
        why="Scripts at the top of the page without async or defer make visitors stare at a blank "
            "screen.",
        fix="Add defer or async to scripts, or move them to the end of the page.",
        tech="<head> scripts with src and no async/defer/module: 0–2 = pass; 3–6 = warn; > 6 = fail."),
    "img_dims": dict(
        name="Image dimensions (CLS)", plain="Image sizes declared", cat="speed", weight=3,
        why="Without a width and height, the page jumps around while images load.",
        fix="Set width and height attributes on images.",
        tech="≥ 80% of <img> have width and height = pass; ≥ 40% = warn. No images = pass."),
    "lazy": dict(
        name="Lazy loading", plain="Images load only when needed", cat="speed", weight=2,
        why="Loading images only when they scroll into view makes the first screen appear faster.",
        fix='Add loading="lazy" to images further down the page.',
        tech='pages with more than 5 images use loading="lazy" on at least one = pass.'),
    "caching": dict(
        name="HTTP caching headers", plain="Browser caching", cat="speed", weight=2,
        why="Lets returning visitors reuse files they already downloaded instead of fetching them again.",
        fix="Send Cache-Control (or ETag / Last-Modified) headers from the server.",
        tech="Cache-Control, ETag or Last-Modified header present = pass."),

    # ---------------- Security ----------------
    "hsts": dict(
        name="HSTS header", plain="Always-secure setting", cat="security", weight=2,
        why="Forces browsers to always use the secure (https) version of the site.",
        fix="Send the Strict-Transport-Security header.",
        tech="Strict-Transport-Security header present on an https page = pass."),
    "mixed": dict(
        name="Mixed content", plain="Insecure files on a secure page", cat="security", weight=4,
        why="Loading images or scripts over http:// on a secure page breaks the padlock.",
        fix="Change every http:// file address on the page to https://.",
        tech="count of img/script/stylesheet/iframe/media loaded over http:// on an https page: "
             "0 = pass; 1–3 = warn; more = fail."),
    "sec_headers": dict(
        name="Security headers", plain="Protection settings", cat="security", weight=3,
        why="Extra server settings that protect visitors from common attacks.",
        fix="Add X-Content-Type-Options, X-Frame-Options (or CSP frame-ancestors) and "
            "Referrer-Policy headers.",
        tech="3 of 3 headers = pass; 1–2 = warn; 0 = fail."),

    # ---------------- Social ----------------
    "og": dict(
        name="Open Graph tags", plain="Preview on WhatsApp and LinkedIn", cat="social", weight=5,
        why="Controls the title, text and picture shown when someone shares your link.",
        fix="Add og:title, og:description and og:image tags.",
        tech="3 of 3 og tags = pass; 1–2 = warn; 0 = fail."),
    "twitter": dict(
        name="Twitter / X card", plain="Preview on X (Twitter)", cat="social", weight=2,
        why="Makes shared links on X show a large picture card.",
        fix='Add <meta name="twitter:card" content="summary_large_image">.',
        tech="twitter:card meta present = pass."),
    "schema": dict(
        name="Structured data (Schema.org)", plain="Rich result labels", cat="social", weight=6,
        why="Hidden labels that tell Google exactly what the page is (a product, an article, a "
            "business) and can earn star ratings or extra details in results.",
        fix="Add JSON-LD schema such as Organization, Article or Product.",
        tech="valid JSON-LD or microdata found = pass; found but some blocks invalid = warn; "
             "none = fail."),

    # ---------------- Links ----------------
    "internal_links": dict(
        name="Internal links", plain="Links to your other pages", cat="links", weight=4,
        why="Links between your pages help visitors and Google find more of your content.",
        fix="Link to related pages on your own site.",
        tech="≥ 5 unique internal links = pass; 1–4 = warn; 0 = fail."),
    "anchor_text": dict(
        name="Anchor text quality", plain="Clear link wording", cat="links", weight=3,
        why="Link text like 'click here' tells Google nothing about the page it points to.",
        fix="Use words that describe the destination, such as 'SEO course fees'.",
        tech="generic ('click here', 'read more', 'here', 'more') or empty anchors ≤ 10% = pass; "
             "≤ 25% = warn."),
    "broken_links": dict(
        name="Broken links", plain="Links that lead nowhere", cat="links", weight=6,
        why="Links to missing pages annoy visitors and waste Google's crawl time.",
        fix="Fix or remove links that return 'page not found' or server errors.",
        tech="crawled internal pages + one sampled link per external site returning 404/410/5xx or "
             "an unknown domain: 0 = pass; 1–2 = warn; more = fail. 401/403/429 answers, firewall "
             "challenges, timeouts and old-TLS failures are listed but not counted as broken."),
    "external_links": dict(
        name="External links", plain="Links to other websites", cat="links", weight=0,
        why="Linking to trusted sources is good, as long as they are relevant.",
        fix="Keep outgoing links relevant and up to date.",
        tech="informational, not scored."),

    # ---------------- Whole site (crawl) ----------------
    "crawl_errors": dict(
        name="Crawl errors", plain="Pages that failed to open", cat="site", weight=6,
        why="If linked pages return errors, visitors and Google hit dead ends.",
        fix="Repair or redirect pages that return errors.",
        tech="crawled pages returning 404/410/5xx or no response: 0 = pass; 1 = warn; more = fail. "
             "Pages that refuse the crawler (401/403/429 or a firewall challenge) are not counted."),
    "dup_titles": dict(
        name="Duplicate title tags", plain="Pages sharing the same title", cat="site", weight=4,
        why="When many pages share one title, Google can't tell them apart.",
        fix="Give every page its own title.",
        tech="no two crawled pages share a title = pass; ≤ 20% of pages = warn."),
    "dup_meta": dict(
        name="Duplicate meta descriptions", plain="Pages sharing the same description",
        cat="site", weight=3,
        why="Copy-pasted descriptions make every result look the same in Google.",
        fix="Write a unique description for each page.",
        tech="no duplicated non-empty descriptions = pass; ≤ 20% of pages = warn."),
    "site_missing": dict(
        name="Missing titles / descriptions", plain="Pages missing a title or description",
        cat="site", weight=4,
        why="Pages without a title or description look broken in search results.",
        fix="Add a title and description to every page.",
        tech="all crawled pages have both = pass; ≤ 25% missing = warn."),
    "thin_pages": dict(
        name="Thin content", plain="Pages with very little text", cat="site", weight=3,
        why="Many near-empty pages make the whole site look low quality.",
        fix="Add useful text to thin pages, or merge them.",
        tech="pages under 250 words ≤ 20% = pass; ≤ 50% = warn."),
    "site_speed": dict(
        name="Average response time", plain="Speed across the site", cat="site", weight=3,
        why="Speed matters on every page, not only the home page.",
        fix="Speed up slow templates and server pages.",
        tech="average crawled page download < 1.5 s = pass; < 3 s = warn."),

    # ---------------- AI access ----------------
    "ai_robots": dict(
        name="AI crawler access (robots.txt)", plain="AI assistants allowed in", cat="ai_access",
        weight=16,
        why="If robots.txt blocks ChatGPT, Perplexity or Claude's search bots, they cannot quote or "
            "recommend your site.",
        fix="Allow OAI-SearchBot, ChatGPT-User, PerplexityBot, Claude-SearchBot and Claude-User in "
            "robots.txt.",
        tech="RFC 9309 evaluation (longest match wins) for 7 search/answer bots: all allowed = pass; "
             "≥ 50% = warn."),
    "ai_firewall": dict(
        name="AI crawler reachability (live test)", plain="AI bots actually let in",
        cat="ai_access", weight=10,
        why="Even when robots.txt says yes, a firewall can still block AI bots. We knocked on the "
            "door as each bot to see who gets in.",
        fix="Ask your host or CDN (for example Cloudflare) to stop blocking AI search bots.",
        tech="GET the page with each AI answer bot's user-agent; 200 with real content = reachable. "
             "All reachable = pass; ≥ 50% = warn. (Sites that verify bots by IP address may still "
             "allow the real bots.)"),
    "llms": dict(
        name="llms.txt", plain="Guide file for AI (llms.txt)", cat="ai_access", weight=6,
        why="A new, optional file that gives AI tools a short map of your most important pages.",
        fix="Publish /llms.txt: a short Markdown list of your key pages with one-line summaries.",
        tech="/llms.txt returns 200 with non-HTML text longer than 20 characters = pass "
             "(proposal from llmstxt.org; not used by Google Search)."),
    "no_js": dict(
        name="Server-rendered content", plain="Readable without JavaScript", cat="ai_access",
        weight=10,
        why="Most AI crawlers do not run JavaScript. If your text only appears after scripts run, "
            "they see an empty page.",
        fix="Render important text on the server (server-side rendering or static HTML).",
        tech="words in raw HTML ≥ 300 = pass; ≥ 100 = warn; else fail."),

    # ---------------- AI understanding ----------------
    "faq_schema": dict(
        name="FAQ / HowTo schema", plain="Questions and answers labelled", cat="ai_understand",
        weight=8,
        why="Labelled questions and answers are easy for AI to lift straight into its replies.",
        fix="Mark up question-and-answer content with FAQPage or HowTo schema.",
        tech="FAQPage, QAPage or HowTo type present = pass."),
    "entity_schema": dict(
        name="Entity schema", plain="Says clearly who you are", cat="ai_understand", weight=6,
        why="Organization or Person labels tell AI exactly which business or author this is.",
        fix="Add Organization (or Person / LocalBusiness) schema with your name, logo and links.",
        tech="Organization, LocalBusiness, Person, WebSite or similar type present = pass."),
    "q_headings": dict(
        name="Question-style headings", plain="Headings people would ask", cat="ai_understand",
        weight=6,
        why="People ask AI questions. Headings like 'How much does it cost?' match those questions.",
        fix="Phrase some H2/H3 headings as real questions.",
        tech="≥ 2 H2/H3 headings ending in '?' or starting with a question word = pass; 1 = warn."),
    "answer_paras": dict(
        name="Answer-sized paragraphs", plain="Short, quotable paragraphs", cat="ai_understand",
        weight=6,
        why="AI tools quote short, self-contained paragraphs. Walls of text are hard to quote.",
        fix="Write paragraphs of 15 to 90 words that each answer one thing.",
        tech="≥ 60% of paragraphs are 15–90 words = pass; ≥ 30% = warn."),
    "lists_tables": dict(
        name="Lists and tables", plain="Lists and tables", cat="ai_understand", weight=5,
        why="Steps, bullet lists and comparison tables are the easiest content for AI to reuse.",
        fix="Use bullet lists for steps or features and tables for comparisons.",
        tech="list items (<li>, role=\"list\" or <dl>) or a <table> present = pass."),
    "summary": dict(
        name="Page summary (meta description)", plain="Clear page summary", cat="ai_understand",
        weight=4,
        why="A good description is often the first thing an AI model reads about your page.",
        fix="Write a clear one- or two-sentence description of the page.",
        tech="meta description present = pass."),
    "text_ratio": dict(
        name="Text-to-HTML ratio", plain="More words than code", cat="ai_understand", weight=4,
        why="Pages that are mostly code and very little text are harder for AI to read.",
        fix="Trim heavy inline code and add more real content.",
        tech="visible text bytes ÷ HTML bytes ≥ 15% = pass; ≥ 8% = warn."),

    # ---------------- AI trust ----------------
    "author_date": dict(
        name="Author and date signals", plain="Who wrote it, and when", cat="ai_trust", weight=6,
        why="Named authors and recent dates make content more trustworthy to Google and AI.",
        fix="Show the author's name and the 'last updated' date on the page.",
        tech="author (meta or schema) and a date (schema, article:*_time meta or <time>) = pass; "
             "one of them = warn."),
    "citations": dict(
        name="Outbound citations", plain="Links to sources", cat="ai_trust", weight=4,
        why="Pointing to trusted sources makes your claims easier to believe and cite.",
        fix="Link to the sources of your facts and statistics.",
        tech="≥ 3 unique external links = pass; 1–2 = warn."),
    "about_contact": dict(
        name="About and contact pages", plain="Shows who runs the site", cat="ai_trust", weight=5,
        why="Visitors, Google and AI trust sites that clearly say who is behind them.",
        fix="Add About and Contact pages and link to them from every page.",
        tech="links (to this site or its sub-domains) to an about/team page and a contact/support "
             "page, found by address or link words = pass; one of them = warn."),
    "secure_index": dict(
        name="Secure and indexable", plain="Safe and visible to search", cat="ai_trust", weight=4,
        why="AI search engines build on normal search indexes, so the basics still matter.",
        fix="Keep the site on HTTPS and don't block it with noindex.",
        tech="https with a valid certificate and no noindex = pass."),
}
