#!/usr/bin/env python3
"""
generate.py — DeepSeek-powered landing/blog page generator for consulting24.co.
Claude is the "brain" (structure, QC spec, assembly, gating); DeepSeek writes the prose.

Usage:
  python3 scripts/generate.py landing <slug> "<primary keyword>" "<brief / jurisdiction facts>"
  python3 scripts/generate.py blog    <slug> "<primary keyword>" "<brief>"

Reads the DeepSeek key from $DEEPSEEK_API_KEY or scripts/.deepseek_key (gitignored).
Enforces the Consulting24 QC checklist: >=2000 words, >=8 FAQs, full section
structure, internal links, validated external authority links, schema, EEAT.
"""
import os, sys, re, json, html, urllib.request, urllib.error, hashlib, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://www.consulting24.co"
sys.path.insert(0, os.path.join(ROOT, "scripts"))
try:
    from regulators import sources_block as _sources_block
except Exception:
    def _sources_block(slug): return ""
WA = "https://wa.me/37258155779?text=Hi%2C%20I%27d%20like%20to%20ask%20about%20a%20crypto%20company%20setup."

def key():
    k = os.environ.get("DEEPSEEK_API_KEY")
    if k: return k.strip()
    p = os.path.join(ROOT, "scripts", ".deepseek_key")
    if os.path.exists(p): return open(p).read().strip()
    sys.exit("No DeepSeek key (set DEEPSEEK_API_KEY or scripts/.deepseek_key)")

# Known internal URLs the model may link to (prevents broken internal links)
INTERNAL = ["/", "/cost/", "/requirements/", "/application-process/", "/exchange-license/",
  "/best-country-for-crypto-license/",
  "/company-setup/", "/vs-lithuania/", "/jurisdictions/", "/blog/",
  "/lithuania-crypto-license/", "/estonia-crypto-license/", "/dubai-crypto-license/",
  "/el-salvador-crypto-license/", "/czech-republic-crypto-license/", "/poland-crypto-license/",
  "/malta-crypto-license/", "/switzerland-crypto-license/", "/cyprus-crypto-license/",
  "/cayman-islands-crypto-license/"]

SYSTEM = """You are a senior crypto-licensing copywriter for Consulting24 (X24Consulting OU, Tallinn, Estonia), a firm that has obtained 500+ crypto licenses, delivering directly in Estonia, Lithuania and Panama and advising/coordinating in all other jurisdictions. Panama company price is a flat EUR 6,000. Write in clear, confident, expert British/EU English for crypto founders.

Output STRICT JSON only, matching this schema:
{
 "meta_title": "50-60 chars, includes the primary keyword",
 "meta_description": "120-155 chars, human, value proposition/CTA, primary keyword; MUST end with a complete sentence and a full stop, never a trailing ellipsis",
 "h1": "includes the primary keyword",
 "intro_html": "2-3 <p> paragraphs; primary keyword in the first 100 words",
 "sections": [ {"h2": "...", "html": "valid HTML: <p>, <ul>, <ol>, <table class=\\"t-wrap-inner\\">, <h3> where useful"} , ... ],
 "faqs": [ {"q":"...","a":"..."}, ... ],
 "authority_links": [ {"title":"Official regulator name","url":"https://...official homepage..."} ]
}

Hard requirements (this is a strict QC gate — pages failing are rejected):
- TOTAL body length (intro + sections + FAQ answers) MUST be 2300-3500 words of UNIQUE, substantive content. This is strictly enforced. Write 13-16 sections; each main section 180-320 words with concrete detail, examples and at least one list or table where useful. Do NOT stop early or write thin sections.
- Include these sections in order: Overview/what it is; Who needs it; License type & regulator; Cost & timeline (with a table); Capital requirement; Tax treatment; Allowed activities; Step-by-step process; Banking & payments; Benefits; Compliance & trust; Common mistakes; Alternatives/comparison (vs Panama and 1-2 others).
- At least 8 FAQs (aim 10-12), each a real question with a 40-90 word answer.
- Weave 5-8 contextual internal links using ONLY paths from this allow-list (exact href): __INTERNAL__ . Always link Panama as <a href="/">Panama</a> and the hub as <a href="/jurisdictions/">jurisdictions</a> at least once.
- authority_links: 1-3 OFFICIAL regulator/government homepages you are highly confident exist (e.g. the financial regulator's main site). If unsure of a URL, omit it. Never invent URLs.
- FACTUAL ACCURACY (critical): treat the FACTS in the user brief as AUTHORITATIVE and current for 2026. Restate the brief's regulator, licence type, capital, tax and timeline EXACTLY — never override them with older/pre-MiCA information from your training. MiCA is FULLY IN FORCE in 2026: the EU CASP regime is live (not "upcoming"/"will expand"), and EU member states apply capital tiers of EUR 50,000 / 125,000 / 150,000 by service class. Do NOT describe EU crypto licensing as the old "VASP register / no minimum capital" model.
- FIGURES: you MAY and SHOULD state specific numbers (fees, capital, timelines, ongoing costs) that are EXPLICITLY GIVEN in the brief — treat brief figures as authoritative and present them clearly (e.g. in the cost table). Panama = EUR 6,000 fixed. You must NOT invent figures that are not in the brief: for anything not provided, use a hedged range and say exact pricing is confirmed in a consultation. No fabricated statistics, no invented laws. Hedge undocumented items with "typically", "as of 2026". Add 'general guidance, not legal advice' in compliance sections. Never promise approval or guarantees.
- Honest delivery framing: say Consulting24 delivers directly for Estonia/Lithuania/Panama; for others it 'advises and coordinates'. EXCEPTION: if the brief contains "DELIVERY=comparison-only" (e.g. UAE/Dubai/Abu Dhabi VARA), Consulting24 does NOT provide that licence — write the page as neutral, informational, and COMPARISON-focused (especially vs Panama); do NOT claim Consulting24 advises/coordinates/files that licence; the CTA must steer the reader to Panama and the jurisdictions Consulting24 does serve (Estonia/Lithuania), framing C24's role as "we help you choose the right route and set up where we operate".
- Every CTA points to talking to an expert on WhatsApp / booking a consultation (do not print the phone number as plain text).
- No keyword stuffing (primary keyword density ~0.8-1.8%). No markdown, valid HTML only inside html fields.
- STYLE/VOICE (anti-AI-detection, strict): write naturally for a professional founder audience, varied sentence length, concrete and specific. NEVER use em-dashes or en-dashes — use commas, hyphens, or rephrase. NO exclamation marks. Do NOT use these AI-cliche words/phrases at all: delve, leverage, seamless, robust, cutting-edge, groundbreaking, game-changing, harness, unleash, empower, paradigm, synergy, holistic, navigate/navigating the landscape, "in today's world", "when it comes to", "that being said", "in essence", "in short", "at the end of the day", "in conclusion", "it's worth noting", "rest assured", "look no further".""".replace("__INTERNAL__", ", ".join(INTERNAL))

BANNED = ["delve","leverage","seamless","robust","cutting-edge","groundbreaking","game-changing",
  "harness","unleash","empower","paradigm","synergy","holistic","in today's world","when it comes to",
  "that being said","in essence","at the end of the day","in conclusion","it's worth noting","look no further"]

BANNED_MAP = {
  # inflected forms listed explicitly so word-boundary replace never mangles
  # (the old substring replace turned 'robustness' -> 'strongness' and missed 'leveraging')
  "seamlessly":"smoothly","seamless":"smooth",
  "robustness":"strength","robustly":"strongly","robust":"strong",
  "leveraging":"using","leverages":"uses","leveraged":"used","leverage":"use",
  "delving into":"examining","delve into":"examine","delves":"examines","delving":"examining","delve":"examine",
  "cutting-edge":"advanced","groundbreaking":"notable","game-changing":"significant",
  "harnessing":"using","harnessed":"used","harnesses":"uses","harness":"use",
  "unleashing":"releasing","unleashes":"releases","unleashed":"released","unleash":"release",
  "empowering":"enabling","empowered":"enabled","empowers":"enables","empower":"enable",
  "holistic":"complete","synergies":"alignment","synergy":"alignment","paradigm":"model",
  "it's worth noting that":"note that","that being said,":"still,","in essence,":"","in conclusion,":"",
  "when it comes to":"for","in today's world":"today","at the end of the day,":"ultimately,","look no further":"start here",
  # AI-tells the SYSTEM prompt bans but the sanitizer previously let through
  "navigating the regulatory landscape":"working through the regulatory rules",
  "navigate the regulatory landscape":"work through the regulatory rules",
  "navigating the landscape":"working through the rules","navigate the landscape":"work through the rules",
  "regulatory landscape":"regulatory environment","landscapes":"markets","landscape":"environment",
  "game-changer":"major advantage","testament to":"reflection of","testament":"reflection",
  "realm":"area","fostering":"supporting","fosters":"supports","fostered":"supported","foster":"support",
  "unlocking":"gaining","unlocks":"gains","unlocked":"gained","unlock":"gain",
  "ever-evolving":"changing","tapestry":"mix","embark on":"start","embarking on":"starting",
  "elevating":"improving","elevates":"improves","elevate":"improve"}

# Fabricated performance statistics: the SYSTEM prompt forbids them, but DeepSeek still
# emitted "98% success rate" / "near 100% approval rate" onto live YMYL pages. Scrub any
# invented success/approval percentage into an unquantified, defensible claim.
_STAT_RE = re.compile(
    r"(?:\ba\s+|\ban\s+)?(?:nearly\s+|near\s+|over\s+|about\s+|around\s+|approximately\s+)?"
    r"\b(?:[5-9]\d|100)\s*%\s+(success|approval)\s+rate\b", re.I)

def _scrub_stats(s):
    return _STAT_RE.sub(lambda m: f"a strong {m.group(1).lower()} record", s)

def _clean(s):
    if not isinstance(s, str): return s
    for a, b in (("—", "-"), ("–", "-"), ("&mdash;", "-"), ("&ndash;", "-"), ("!", ".")):
        s = s.replace(a, b)
    s = _scrub_stats(s)
    def _repl(good):
        return lambda m: (good[:1].upper() + good[1:]) if m.group(0)[:1].isupper() else good
    for bad in sorted(BANNED_MAP, key=len, reverse=True):   # longest first (phrases before words)
        good = BANNED_MAP[bad]
        if good == "":
            s = re.sub(r"\b" + re.escape(bad), "", s, flags=re.I)
        else:
            s = re.sub(r"\b" + re.escape(bad) + r"\b", _repl(good), s, flags=re.I)
    return re.sub(r"  +", " ", s)

def _clean_d(d):
    d["meta_title"] = _clean(d.get("meta_title", "")); d["meta_description"] = _clean(d.get("meta_description", ""))
    d["h1"] = _clean(d.get("h1", "")); d["intro_html"] = _clean(d.get("intro_html", ""))
    for s in d.get("sections", []): s["h2"] = _clean(s.get("h2", "")); s["html"] = _clean(s.get("html", ""))
    for f in d.get("faqs", []): f["q"] = _clean(f.get("q", "")); f["a"] = _clean(f.get("a", ""))
    return d

def call_deepseek(user):
    body = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role":"system","content":SYSTEM},{"role":"user","content":user}],
        "response_format": {"type":"json_object"},
        "max_tokens": 8000, "temperature": 0.6, "stream": False,
    }).encode()
    req = urllib.request.Request("https://api.deepseek.com/chat/completions", data=body,
        headers={"Content-Type":"application/json","Authorization":"Bearer "+key()})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.load(r)
    return json.loads(data["choices"][0]["message"]["content"])

def url_ok(u):
    if not u.startswith("https://"): return False
    try:
        req = urllib.request.Request(u, method="HEAD", headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            return r.status < 400
    except Exception:
        try:
            req = urllib.request.Request(u, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12) as r:
                return r.status < 400
        except Exception:
            return False

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_header import HEADER, HEAD_ASSETS  # shared site header (scripts/site_header.py)
ADVISOR = '''  <div class="advisor" style="display:flex;gap:18px;align-items:center;background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:20px;margin:28px 0">
    <picture><source srcset="/img/mardo-soo-profile.webp" type="image/webp"><img src="/img/mardo-soo-profile.jpg" alt="Mardo Soo, CEO of Consulting24" width="92" height="92" loading="lazy" style="width:92px;height:92px;border-radius:50%;object-fit:cover;flex:none;border:3px solid var(--accent-soft)"></picture>
    <div><strong style="display:block;font-size:1.05rem">Mardo Soo &middot; CEO, Consulting24</strong><span style="color:var(--ink-2);font-size:.92rem">Personally advises on jurisdiction selection. 500+ crypto licenses across Estonia, Lithuania &amp; Panama. <a href="https://www.linkedin.com/in/mardo-s-00a05ab0/" target="_blank" rel="noopener">LinkedIn &rarr;</a></span></div>
  </div>'''
def footer():
    return '''<footer><div class="wrap"><div class="foot-grid">
    <div><h2>Consulting24</h2><p style="color:#a3a3a3">500+ crypto licenses across Estonia, Lithuania, Panama and beyond.</p><p style="margin-top:14px"><strong style="color:#fff">WhatsApp / email</strong><br>mardo@consulting24.co</p></div>
    <div><h2>Jurisdictions</h2><a href="/jurisdictions/">All jurisdictions</a><a href="/">Panama</a><a href="/lithuania-crypto-license/">Lithuania</a><a href="/estonia-crypto-license/">Estonia</a></div>
    <div><h2>Resources</h2><a href="/cost/">Panama cost</a><a href="/best-country-for-crypto-license/">Best country for a crypto license</a><a href="/requirements/">Requirements</a><a href="/blog/">Blog</a></div>
    <div><h2>Company</h2><a href="/about/">About Consulting24</a><a href="/contact/">Contact</a><a href="https://consulting24.co/">consulting24.co</a><a href="https://www.linkedin.com/in/mardo-s-00a05ab0/">Mardo Soo on LinkedIn</a></div>
  </div><div class="foot-bottom">&copy; 2026 Consulting24 &middot; X24Consulting O&Uuml; &middot; Reg nr 16971898 &middot; Poordi 3-63, 10156 Tallinn, Estonia &middot; General guidance, not legal advice.</div></div></footer>
<div class="sticky-bar"><a href="''' + WA + '''" class="btn btn-secondary" style="background:var(--ink)">&#128172; WhatsApp</a><a href="/#contact-top" class="btn btn-primary">Free consultation</a></div>'''

def fig(src, alt):
    return f'  <figure style="margin:24px 0"><img src="{src}" alt="{html.escape(alt)}" loading="lazy" width="1200" height="320" style="width:100%;height:auto;border-radius:14px;border:1px solid var(--line)"></figure>'

_HUB_SPECIAL = {"mica":"MiCA","vasp":"VASP","casp":"CASP","msb":"MSB","vara":"VARA","bvi":"BVI",
 "usa":"USA","uae":"UAE","eu":"EU","el":"El","vs":"vs","and":"and","for":"for","of":"of",
 "hong":"Hong","kong":"Kong","south":"South","korea":"Korea","costa":"Costa","rica":"Rica",
 "saudi":"Saudi","arabia":"Arabia","czech":"Czech","republic":"Republic","marshall":"Marshall",
 "islands":"Islands","cayman":"Cayman","saint":"Saint","lucia":"Lucia","abu":"Abu","dhabi":"Dhabi"}
def _hub_label(slug):
    return " ".join(_HUB_SPECIAL.get(w.lower(), w.capitalize()) for w in slug.split("-"))
_CORE_LINKS = ["", "jurisdictions", "cost", "requirements", "mica-license",
               "casp-license", "lithuania-crypto-license", "estonia-crypto-license"]
def link_hub(self_slug="", cap=20):
    """Lean, contextual internal-link block (~20 relevant links, not the whole site).
    Picks: core money pages + same-jurisdiction/topic siblings + a deterministic slice."""
    skip = {"blog","scripts","config","img","logs","jurisdictions"}
    dirs = [n for n in sorted(os.listdir(ROOT))
            if n not in skip and os.path.isdir(os.path.join(ROOT, n))
            and os.path.exists(os.path.join(ROOT, n, "index.html"))]
    dset = set(dirs)
    picked, seen = [], {self_slug}
    def add(s):
        if s in seen: return
        if s == "" or s in dset:
            seen.add(s); picked.append(s)
    for c in _CORE_LINKS: add(c)                                  # core money pages
    toks = [t for t in self_slug.split("-") if len(t) > 3 and t != "crypto" and t != "license"]
    for s in dirs:                                                # topical siblings
        if len(picked) >= cap: break
        if any(t in s for t in toks): add(s)
    h = int(hashlib.md5(self_slug.encode()).hexdigest(), 16) if self_slug else 0
    rotated = dirs[h % len(dirs):] + dirs[:h % len(dirs)] if dirs else []
    for s in rotated:                                            # fill remainder, varied per page
        if len(picked) >= cap: break
        add(s)
    links = "".join(
        f'<a href="/{s}/" style="display:inline-block;margin:0 10px 8px 0">{_hub_label(s) if s else "Panama (EUR 6,000)"}</a>'
        for s in picked[:cap])
    if not links: return ""
    return ('<section class="wrap landing-link-hub" style="margin:8px auto 0">'
            '<h2 style="font-size:1.3rem">Related crypto license guides</h2>'
            '<p style="color:var(--ink-2)">Compare the most relevant routes, each with cost, capital, timeline and requirements:</p>'
            f'<div style="line-height:1.9;font-size:14px">{links}</div></section>')

_BLOG_STOP = {"crypto","license","licence","company","which","choose","should","your","panama",
              "for","the","and","vs","cost","take","2026","how","get","guide","in","to","of","a"}
def _blog_related(self_slug):
    """Blog footer: link the #2-ranking best-country money page + 2-3 topically related
    blog posts (token overlap) so posts form clusters instead of sitting siloed."""
    bdir = os.path.join(ROOT, "blog")
    try:
        cand = [n for n in os.listdir(bdir)
                if n != self_slug and os.path.isdir(os.path.join(bdir, n))
                and os.path.exists(os.path.join(bdir, n, "index.html"))]
    except FileNotFoundError:
        cand = []
    toks = {t for t in self_slug.split("-") if len(t) > 3 and t not in _BLOG_STOP}
    scored = sorted(cand, key=lambda s: -len(toks & set(s.split("-"))))
    rel = [s for s in scored if toks & set(s.split("-"))][:3] or scored[:3]
    posts = "".join(f'<a href="/blog/{s}/"><strong>{_hub_label(s)}</strong></a>' for s in rel)
    return ('<h2>Related guides</h2><div class="related">'
            '<a href="/best-country-for-crypto-license/"><strong>Best country for a crypto license</strong>'
            '<span>Compare every jurisdiction</span></a>' + posts + '</div>')

def assemble(slug, crumb, d, kind="landing"):
    sec_list = [f"  <h2>{html.escape(s['h2'])}</h2>\n{s['html']}" for s in d["sections"]]
    imgs = [("/img/graphic-process.svg", f"{crumb} crypto licence process: scope, incorporate, apply, operate"),
            ("/img/graphic-jurisdictions.svg", f"{crumb} crypto licence compared with Panama, EU/MiCA, Gulf and offshore options"),
            ("/img/graphic-trust.svg", "Consulting24: 500+ crypto licenses obtained, compliance-first")]
    out, placed = [], 0
    for i, block in enumerate(sec_list):
        out.append(block)
        if i in (0, 2, 4) and placed < len(imgs):
            out.append(fig(*imgs[placed])); placed += 1
    while placed < len(imgs):  # ensure all 3 land even on short pages
        out.append(fig(*imgs[placed])); placed += 1
    sections = "\n".join(out)
    faqs_html = '<section class="faq"><h2>Frequently asked questions</h2>' + "".join(
        f"<details><summary>{html.escape(f['q'])}</summary><p>{f['a']}</p></details>" for f in d["faqs"]) + "</section>"
    auth = [a for a in d.get("authority_links",[]) if url_ok(a.get("url",""))]
    auth_html = ""
    if auth:
        auth_html = '<h2>Official sources</h2><ul>' + "".join(
            f'<li><a href="{html.escape(a["url"])}" target="_blank" rel="nofollow noopener">{html.escape(a["title"])}</a></li>' for a in auth) + "</ul>"
    faq_schema = ",".join('{"@type":"Question","name":%s,"acceptedAnswer":{"@type":"Answer","text":%s}}' %
        (json.dumps(f["q"]), json.dumps(re.sub("<[^>]+>","",f["a"]))) for f in d["faqs"])
    canon = f"{BASE}/{slug}/" if kind=="landing" else f"{BASE}/blog/{slug}/"
    css = "../styles.css" if kind=="landing" else "../../styles.css"
    _pool = [("/lithuania-crypto-license/","Lithuania"),("/estonia-crypto-license/","Estonia"),("/dubai-crypto-license/","Dubai"),("/cyprus-crypto-license/","Cyprus"),("/malta-crypto-license/","Malta"),("/cayman-islands-crypto-license/","Cayman Islands"),("/switzerland-crypto-license/","Switzerland"),("/","Panama (EUR 6,000)")]
    _rel = [(h,n) for h,n in _pool if h.strip("/") != slug][:4]
    def _rel_anchor(h, n):
        label = n if "(" in n else f"{n} crypto license"   # descriptive partial-match anchor
        return f'<a href="{h}"><strong>{label}</strong><span>Requirements, cost &amp; timeline</span></a>'
    related_html = '<h2>Related jurisdictions</h2><div class="related">' + "".join(_rel_anchor(h, n) for h, n in _rel) + '</div>'
    blog_extra = '' if kind == "landing" else _blog_related(slug)
    topcta = '<div class="top-cta-row"><a href="'+WA+'" class="btn btn-primary">&#128172; Talk to an expert</a><a href="/#contact-top" class="btn btn-ghost">Free assessment</a></div>'
    trust = '<div class="trust-strip"><b>500+ crypto licenses obtained.</b> <span class="logos">Binance &middot; LBank &middot; Coinify &middot; MultiversX &middot; UPay &middot; Vitalum</span></div>'
    today = datetime.date.today().isoformat()
    # TL;DR answer box (LLM + featured-snippet friendly: a direct, quotable answer up top)
    _ans = html.escape(d.get("meta_description","").strip())
    tldr = (f'<div class="answer-box" style="background:var(--accent-soft);border-left:4px solid var(--accent);'
            f'border-radius:8px;padding:16px 20px;margin:0 0 22px"><strong style="color:var(--accent-dark)">Short answer:</strong> {_ans}</div>') if _ans else ""
    # Visible author byline (E-E-A-T)
    byline = (f'<p class="byline" style="color:var(--muted);font-size:.9rem;margin:0 0 18px">'
              f'By <a href="/about/" rel="author">Mardo Soo</a>, '
              f'Founder &amp; CEO, Consulting24 (X24Consulting O&Uuml;) &middot; Updated {today}</p>')
    _authorimg = f"{BASE}/img/mardo-soo-profile.jpg"
    # one canonical Organization (referenced by @id everywhere) + an on-site author entity
    ORG_ID = f"{BASE}/#business"; AUTHOR_ID = f"{BASE}/about/#mardo-soo"
    org_node = (
      f'{{"@type":"Organization","@id":"{ORG_ID}","name":"Consulting24","legalName":"X24Consulting O\\u00dc",'
      f'"url":"{BASE}/","logo":{{"@type":"ImageObject","url":"{_authorimg}"}},'
      f'"identifier":{{"@type":"PropertyValue","propertyID":"Estonian Business Register","value":"16971898"}},'
      f'"address":{{"@type":"PostalAddress","streetAddress":"Poordi 3-63","addressLocality":"Tallinn","postalCode":"10156","addressCountry":"EE"}},'
      f'"sameAs":["https://blog.consulting24.co/"]}}')
    # UAE VARA / ADGM comparison-only: never emit a Service node claiming we provide the licence
    _co = any(t in slug for t in ("dubai", "abu-dhabi", "uae", "vara", "adgm"))
    service_node = "" if _co else (
      f'{{"@type":"Service","name":{json.dumps(crumb+" Crypto License")},"provider":{{"@id":"{ORG_ID}"}}}},')
    _cr2_name, _cr2_item = ("Blog", f"{BASE}/blog/") if kind == "blog" else ("Jurisdictions", f"{BASE}/jurisdictions/")
    article_schema = (
      f'{{"@type":"Article","headline":{json.dumps(d.get("meta_title",""))},'
      f'"description":{json.dumps(d.get("meta_description",""))},'
      f'"datePublished":"{today}","dateModified":"{today}",'
      f'"image":"{BASE}/og-image.jpg","mainEntityOfPage":"{canon}",'
      f'"author":{{"@type":"Person","@id":"{AUTHOR_ID}","name":"Mardo Soo","jobTitle":"Founder & CEO",'
      f'"url":"{BASE}/about/","image":"{_authorimg}","sameAs":["https://www.linkedin.com/in/mardo-s-00a05ab0/"],'
      f'"worksFor":{{"@id":"{ORG_ID}"}}}},'
      f'"publisher":{{"@id":"{ORG_ID}"}}}}')
    return f'''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(d["meta_title"])}</title>
<meta name="description" content="{html.escape(d["meta_description"])}">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<link rel="canonical" href="{canon}">
<meta property="og:title" content="{html.escape(d["meta_title"])}"><meta property="og:description" content="{html.escape(d["meta_description"])}">
<meta property="og:type" content="article"><meta property="og:url" content="{canon}"><meta property="og:image" content="{BASE}/og-image.jpg">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{html.escape(d["meta_title"])}"><meta name="twitter:description" content="{html.escape(d["meta_description"])}"><meta name="twitter:image" content="{BASE}/og-image.jpg">
<script type="application/ld+json">
{{"@context":"https://schema.org","@graph":[
 {org_node},
 {{"@type":"BreadcrumbList","itemListElement":[
   {{"@type":"ListItem","position":1,"name":"Home","item":"{BASE}/"}},
   {{"@type":"ListItem","position":2,"name":"{_cr2_name}","item":"{_cr2_item}"}},
   {{"@type":"ListItem","position":3,"name":{json.dumps(crumb)},"item":"{canon}"}}]}},
 {service_node}
 {article_schema},
 {{"@type":"FAQPage","mainEntity":[{faq_schema}]}}
]}}
</script>
<link rel="stylesheet" href="{css}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml"><link rel="icon" href="/favicon.ico" sizes="32x32"><link rel="apple-touch-icon" href="/apple-touch-icon.png">
{HEAD_ASSETS}
</head><body>
<a href="#main" class="skip">Skip to main content</a>
{HEADER}
<div class="wrap"><nav class="breadcrumbs"><a href="/">Home</a> &rsaquo; <a href="{'/blog/' if kind=='blog' else '/jurisdictions/'}">{'Blog' if kind=='blog' else 'Jurisdictions'}</a> &rsaquo; {html.escape(crumb)}</nav></div>
<article class="wrap" id="main">
  <h1>{html.escape(d["h1"])}</h1>
{byline}
{tldr}
{d["intro_html"]}
{topcta}
{trust}
{sections}
{faqs_html}
{auth_html}
{_sources_block(slug)}
{related_html}
{ADVISOR}
  <div class="cta-card"><h2>Talk to a crypto-licensing expert</h2><p>500+ licenses across Estonia, Lithuania, Panama and beyond. Tell us your model and we'll map the right route, honestly.</p>
  <a href="{WA}" class="btn btn-primary">&#128172; Talk to an expert</a><a href="/#contact-top" class="btn btn-ghost">Free consultation</a></div>
  <p style="color:var(--muted);font-size:.85rem;margin-top:24px">General guidance, not legal advice. Rules and fees evolve, and we confirm current requirements for your case.</p>
</article>
{link_hub(slug) if kind=="landing" else blog_extra}
{footer()}
</body></html>
'''

def tidy_desc(s):
    """Trim a meta description to a COMPLETE sentence <=155 chars, never a mid-word
    cut with a trailing ellipsis (the pre-2026-07 bug left 380 pages ending in '…')."""
    s = re.sub(r"\s*(?:\.{2,}|…)+\s*$", "", (s or "").strip()).strip()
    if len(s) <= 158 and s[-1:] in ".!?":
        return s
    cut = s[:156].rstrip()
    ends = [m.end() - 1 for m in re.finditer(r"[.!?]", cut)]
    if ends and ends[-1] >= 90:                       # keep to last full sentence
        return cut[:ends[-1] + 1].strip()
    commas = [i for i, c in enumerate(cut) if c == "," and i >= 60]
    base = cut[:commas[-1]] if commas else cut.rsplit(" ", 1)[0]   # drop trailing incomplete clause
    return base.rstrip(" ,;:-") + "."

def _trim_meta(d):
    # auto-fix near-miss meta lengths so overflow never wastes a good page
    t = (d.get("meta_title") or "").strip()
    if len(t) > 60: t = t[:60].rsplit(" ", 1)[0].rstrip(" -|:&")   # <=~600px, no dangling punct
    d["meta_title"] = t
    d["meta_description"] = tidy_desc(d.get("meta_description") or "")
    return d

def _repair(d, keyword):
    """Auto-fix the deterministic QC failures (keyword-in-H1/title, title length)
    so quality pages are never dropped for a mechanical SEO miss. Keyword is always
    prepended to the front, so any right-side trim preserves it."""
    kw = (keyword or "").strip()
    if not kw:
        return d
    kwl = kw.lower()
    _keep = {"and","for","of","to","the","vs","a","in"}
    kwt = " ".join(_HUB_SPECIAL.get(w.lower(), w if w.isupper() else (w.lower() if w.lower() in _keep else w.capitalize()))
                   for w in kw.split())
    if kwt[:1].islower():
        kwt = kwt[:1].upper() + kwt[1:]
    # Keyword is "present" if every keyword token already appears as a whole word,
    # even reordered (e.g. kw "crypto staking license portugal" vs title
    # "Portugal Crypto License: Crypto Staking"). This prevents re-prepending the
    # keyword onto a title that already covers it, which produced duplicated junk
    # like "Crypto Staking License Portugal Crypto License: Crypto Staking".
    def _covers(text):
        low = text.lower()
        return all(re.search(r'\b' + re.escape(tok) + r'\b', low) for tok in kwl.split())
    # H1 must contain the keyword
    h1 = (d.get("h1") or "").strip()
    if not _covers(h1):
        d["h1"] = f"{kwt}: {h1}" if h1 else f"{kwt}: 2026 Guide"
    # Title must contain the keyword
    t = (d.get("meta_title") or "").strip()
    if not _covers(t):
        t = f"{kwt}: {t}".strip() if t else kwt
    # Title must be 50-65 chars
    if len(t) < 50:
        base = t.rstrip(" .:")
        # avoid a double year / double colon when the title already reads cleanly
        t = (base + " - Cost, Requirements & Timeline") if "2026" in base \
            else (base + " 2026: Cost, Requirements & Timeline")
    if len(t) > 65:
        t = t[:65].rsplit(" ", 1)[0].rstrip(" .,:;&-")
    d["meta_title"] = t
    # Description must be 110-165 chars. The build() retry only re-asks DeepSeek when the
    # WORD COUNT fails, so without this a merely-short description would fail qc() with no
    # retry and discard an otherwise-good page (daily_run gives up after MAX_ATTEMPTS).
    # Titles were already auto-padded here; descriptions were not. Symmetry restored.
    ds = (d.get("meta_description") or "").strip()
    if len(ds) < 110:
        base = ds.rstrip(" .")
        # append factual clauses until the 110 floor is cleared (one clause is not always enough)
        for tail in (f"Requirements, cost and timeline for {kwt}, explained for crypto founders.",
                     "Talk to Consulting24 about the right route for your setup.",
                     "General guidance for founders comparing jurisdictions in 2026."):
            base = (base + ". " + tail.rstrip()).strip(" .") if base else tail.rstrip(".")
            if len(base) + 1 >= 110:
                break
        ds = base.rstrip(" .") + "."
    if len(ds) > 165:
        ds = ds[:164].rsplit(" ", 1)[0].rstrip(" .,:;&-") + "."
    d["meta_description"] = ds
    return d

def qc(d, page_html, keyword=""):
    text = re.sub("<[^>]+>"," "," ".join([d["intro_html"]] + [s["html"] for s in d["sections"]] + [f["a"] for f in d["faqs"]]))
    words = len(text.split())
    internal = len(set(re.findall(r'href="(/[^"]*)"', page_html)))
    images = page_html.count("<img ")
    kw = (keyword or "").lower().strip()
    density = round(100 * text.lower().count(kw) * len(kw.split()) / max(words,1), 2) if kw else 0
    report = {
        "words": words, "faqs": len(d["faqs"]), "images": images, "internal_links": internal,
        "title_len": len(d["meta_title"]), "desc_len": len(d["meta_description"]), "kw_density%": density,
    }
    fails = []
    if words < 2000: fails.append(f"words {words} < 2000")
    if len(d["faqs"]) < 8: fails.append(f"faqs {len(d['faqs'])} < 8")
    if images < 3: fails.append(f"images {images} < 3")
    if internal < 5: fails.append(f"internal_links {internal} < 5")
    if 'href="/"' not in page_html: fails.append("no homepage link")
    if not (50 <= len(d["meta_title"]) <= 65): fails.append(f"title len {len(d['meta_title'])}")
    if not (110 <= len(d["meta_description"]) <= 165): fails.append(f"desc len {len(d['meta_description'])}")
    # token-coverage (reordered keyword counts as present), matching _repair
    _toks = lambda s: all(re.search(r'\b'+re.escape(t)+r'\b', s.lower()) for t in kw.split())
    if kw and not _toks(d["h1"]): fails.append("keyword not in H1")
    if kw and not _toks(d["meta_title"]): fails.append("keyword not in title")
    if density > 3.0: fails.append(f"keyword stuffing {density}%")
    low=text.lower()
    banned=[w for w in BANNED if w in low]
    report["banned"]=banned
    dashes = ("\u2014" in low) or ("\u2013" in low) or ("!" in re.sub(r"&[a-z]+;"," ",low))
    if dashes: fails.append("em/en-dash or ! present")
    # YMYL honesty gates: _clean already scrubs these, so a hit here means the sanitizer
    # was bypassed. Fabricated performance stats and approval guarantees must never ship.
    if _STAT_RE.search(text): fails.append("fabricated success/approval rate")
    if re.search(r"\b(guarantee[ds]?|guaranteed)\s+(approval|licence|license|success)\b", low):
        fails.append("approval guarantee")
    # Panama fabrication guard: DeepSeek repeatedly invents that Panama ISSUES a crypto licence
    # (via SBP/UAF/CNV, under a mislabeled "Law 23 ... on Digital Commerce/digital assets").
    # Truth: Panama has no crypto/VASP licence; Law 23 of 2015 is its AML/CFT law only.
    if (re.search(r"panama[^.]{0,40}crypto licen[sc]e is issued", low)
            or re.search(r"law 23 of 2015 on (digital commerce|digital assets|virtual asset)", low)
            or re.search(r"(sbp|superintendencia de bancos|uaf|financial analysis unit|cnv|"
                         r"national securities commission)[^.]{0,45}(issues?|grants?)[^.]{0,25}"
                         r"(crypto|virtual asset)[^.]{0,15}licen", low)
            or "provider of virtual asset services" in low):
        fails.append("panama crypto-licence fabrication")
    # banned words are auto-replaced in _clean; report only, don't hard-fail
    report["pass"] = not fails
    report["fails"] = fails
    return report

_INTERNAL_SET = set(INTERNAL)
def _sanitize_internal_links(page_html):
    """Unwrap internal <a href="/X"> whose target is neither allow-listed nor on disk —
    kills DeepSeek-hallucinated links (/compliance/, /banking/, ...) before they ship,
    so the linkcheck 'broken internal links' class cannot recur."""
    def ok(href):
        h = href.split("#")[0].split("?")[0]
        if not h.startswith("/") or h == "/": return True
        if h in _INTERNAL_SET or h.rstrip("/") + "/" in _INTERNAL_SET: return True
        p = h.strip("/")
        return (os.path.exists(os.path.join(ROOT, p, "index.html")) or
                os.path.exists(os.path.join(ROOT, p)))
    def repl(m):
        return m.group(2) if m.group(1).startswith("/") and not ok(m.group(1)) else m.group(0)
    return re.sub(r'<a\b[^>]*?href="([^"]*)"[^>]*?>(.*?)</a>', repl, page_html, flags=re.S)

_TH_NOSCOPE = re.compile(r"<th(?![^>]*\bscope=)(\s[^>]*)?>", re.I)

def _table_scope(page_html):
    """Give DeepSeek's data tables proper header scope (WCAG 1.3.1): <th> in a header row
    becomes scope="col", leading <th> in body rows become scope="row"."""
    def one_table(m):
        tbl = m.group(0)
        add = lambda x, v: f'<th scope="{v}"{x.group(1) or ""}>'
        if re.search(r"<thead>", tbl, re.I):
            tbl = re.sub(r"<thead>.*?</thead>",
                         lambda t: _TH_NOSCOPE.sub(lambda x: add(x, "col"), t.group(0)), tbl, flags=re.S | re.I)
            return re.sub(r"<tbody>.*?</tbody>",
                          lambda t: _TH_NOSCOPE.sub(lambda x: add(x, "row"), t.group(0)), tbl, flags=re.S | re.I)
        rows = list(re.finditer(r"<tr>.*?</tr>", tbl, flags=re.S | re.I))
        out, last = [], 0
        for i, r in enumerate(rows):
            out.append(tbl[last:r.start()])
            out.append(_TH_NOSCOPE.sub(lambda x: add(x, "col" if i == 0 else "row"), r.group(0)))
            last = r.end()
        out.append(tbl[last:])
        return "".join(out)
    return re.sub(r"<table\b.*?</table>", one_table, page_html, flags=re.S | re.I)

def build(kind, slug, keyword, brief):
    crumb = brief.split("|")[0].strip() if "|" in brief else slug.replace("-crypto-license","").replace("-"," ").title()
    user = f"Write a {kind} page. Primary keyword: \"{keyword}\". Slug: /{slug}/. Brief & facts: {brief}\nReturn STRICT JSON per the schema. Remember: 2000+ words, 8+ FAQs, full section structure, internal links from the allow-list, validated official authority links only."
    d = _repair(_trim_meta(_clean_d(call_deepseek(user))), keyword)
    page = assemble(slug, crumb, d, kind).replace('/panama-crypto-license/', '/').replace('/panama/', '/')  # guard: old project path → root
    page = _table_scope(_sanitize_internal_links(page))  # strip hallucinated links + scope table headers
    report = qc(d, page, keyword)
    # auto-expand if the only failure is word count (up to 2 retries)
    tries = 0
    while not report["pass"] and any("words" in f for f in report["fails"]) and tries < 2:
        tries += 1
        cur = report["words"]
        exp = (f"This draft is only {cur} words; it MUST reach 2300+. Expand it: deepen every section with more concrete detail, examples, a worked cost/timeline table, more on banking, compliance and common mistakes, and lengthen FAQ answers. Keep all existing internal links and authority_links. Return the SAME strict JSON schema with the fuller content.\n\nCURRENT JSON:\n" + json.dumps(d)[:12000])
        d = _repair(_trim_meta(_clean_d(call_deepseek(exp))), keyword)
        page = assemble(slug, crumb, d, kind).replace('/panama-crypto-license/', '/').replace('/panama/', '/')  # guard: old project path → root
        page = _table_scope(_sanitize_internal_links(page))  # strip hallucinated links + scope table headers
        report = qc(d, page, keyword)
        print(f"  expand retry {tries}: {report['words']} words")
    outdir = os.path.join(ROOT, slug) if kind=="landing" else os.path.join(ROOT, "blog", slug)
    if report["pass"]:
        os.makedirs(outdir, exist_ok=True)
        with open(os.path.join(outdir,"index.html"),"w",encoding="utf-8") as f: f.write(page)
        print(f"WROTE /{slug}/  {report}")
    else:
        print(f"QC FAIL /{slug}/  {report}  (not written)")
    return report

if __name__ == "__main__":
    if len(sys.argv) < 5:
        sys.exit("usage: generate.py <landing|blog> <slug> <keyword> <brief>")
    build(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
