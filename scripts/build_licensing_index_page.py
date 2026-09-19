#!/usr/bin/env python3
"""Render the public /licensing-index/ report page (+ /licensing-index/methodology/).

Data layers (honest, no fabrication):
  - REFERENCE layer: /data/jurisdictions.json (regulator, service model, 2026 timeline) —
    already-published, verified facts. Renders now.
  - OPERATOR layer: /data/licensing-index.json (real aggregated data from 500+ Consulting24
    setups) — merged in by slug ONLY where the owner has filled it (build_licensing_index.py).
    Until filled, those cells stay blank; nothing is invented.

The page carries Dataset + Article schema (authored by Mardo Soo) and links the machine-readable
endpoints, so it is citable by search + AI engines. This is the strategic moat's public face.

Run in the pipeline after build_data_json.py / build_licensing_index.py.
"""
from __future__ import annotations
import html, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://www.consulting24.co"
ORG_ID = f"{BASE}/#business"; AUTHOR_ID = f"{BASE}/about/#mardo-soo"
WA = "https://wa.me/37258155779?text=Hi%2C%20I%27d%20like%20to%20ask%20about%20a%20crypto%20company%20setup."

MODEL_LABEL = {"direct": "We deliver directly", "advise-and-coordinate": "We advise &amp; coordinate",
               "comparison-only": "Comparison only"}

def _load(p):
    fp = os.path.join(ROOT, "data", p)
    return json.load(open(fp, encoding="utf-8")) if os.path.exists(fp) else None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_header import HEADER, HEAD_ASSETS  # shared site header (scripts/site_header.py)

FOOTER = '''<footer><div class="wrap"><div class="foot-grid">
  <div><h2>Consulting24</h2><p style="color:#a3a3a3">500+ crypto licenses across Estonia, Lithuania, Panama and beyond.</p><p style="margin-top:14px"><strong style="color:#fff">WhatsApp / email</strong><br>mardo@consulting24.co</p></div>
  <div><h2>Jurisdictions</h2><a href="/jurisdictions/">All jurisdictions</a><a href="/">Panama</a><a href="/lithuania-crypto-license/">Lithuania</a><a href="/estonia-crypto-license/">Estonia</a></div>
  <div><h2>Resources</h2><a href="/licensing-index/">Licensing Index</a><a href="/best-country-for-crypto-license/">Best country</a><a href="/cost/">Panama cost</a><a href="/blog/">Blog</a></div>
  <div><h2>Company</h2><a href="/about/">About Consulting24</a><a href="https://consulting24.co/">consulting24.co</a><a href="https://www.linkedin.com/in/mardo-s-00a05ab0/">Mardo Soo on LinkedIn</a></div>
</div><div class="foot-bottom">&copy; 2026 Consulting24 &middot; X24Consulting O&Uuml; &middot; Reg nr 16971898 &middot; Poordi 3-63, 10156 Tallinn, Estonia &middot; General guidance, not legal advice.</div></div></footer>'''

def _head(title, desc, canon, extra_ld):
    return f'''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<link rel="canonical" href="{canon}">
<meta property="og:title" content="{html.escape(title)}"><meta property="og:description" content="{html.escape(desc)}">
<meta property="og:type" content="article"><meta property="og:url" content="{canon}"><meta property="og:image" content="{BASE}/og-image.jpg">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{html.escape(title)}"><meta name="twitter:description" content="{html.escape(desc)}"><meta name="twitter:image" content="{BASE}/og-image.jpg">
<script type="application/ld+json">{extra_ld}</script>
<link rel="stylesheet" href="../styles.css">
<link rel="icon" href="/favicon.svg" type="image/svg+xml"><link rel="icon" href="/favicon.ico" sizes="32x32"><link rel="apple-touch-icon" href="/apple-touch-icon.png">
{HEAD_ASSETS}
</head><body>
<a href="#main" class="skip">Skip to main content</a>
{HEADER}'''

def build():
    ref = _load("jurisdictions.json")
    if not ref:
        print("licensing-index page: data/jurisdictions.json missing — run build_data_json.py first"); return
    op = _load("licensing-index.json") or {}
    # operator data lives under each row's "operator" sub-object, present ONLY where the owner
    # has filled real delivery figures. have_operator is true only if at least one is filled.
    op_by = {j["slug"]: j["operator"] for j in op.get("jurisdictions", []) if j.get("operator")}
    js = ref["jurisdictions"]
    direct = [j for j in js if j["service_model"] == "direct"]
    have_operator = bool(op_by)

    # comparison table rows
    rows = []
    for j in js:
        o = op_by.get(j["slug"], {})
        cost = ""
        c = (o.get("setup_cost_eur") or {})
        if c.get("typical") is not None:
            cost = f"EUR {c['typical']:,}" + (f" ({c.get('low'):,}-{c.get('high'):,})" if c.get("low") else "")
        sample = str(o.get("sample_size")) if o.get("sample_size") else ""
        model = MODEL_LABEL.get(j["service_model"], j["service_model"])
        reg = (j.get("regulator") or "").split(".")[0].strip()
        if "NO enacted" in reg or "no dedicated" in reg.lower():
            reg = "Company + AML (no licence)"
        elif len(reg) > 52:
            reg = reg[:52].rsplit(" ", 1)[0] + "&hellip;"
        op_cells = (f'<td>{cost or "n/a"}</td><td>{sample or "n/a"}</td>') if have_operator else ""
        rows.append(
            f'<tr><td><a href="{j["page"]}">{html.escape(j["name"])}</a></td>'
            f'<td>{model}</td><td>{reg}</td>'
            f'<td>{html.escape(j.get("timeline") or "on request")}</td>{op_cells}</tr>')
    # operator columns appear only once real delivery data is filled (no empty "—" columns)
    op_head = "<th scope=\"col\">Setup (operator)</th><th scope=\"col\">Sample</th>" if have_operator else ""
    table = ("<div class='t-wrap'><table class='t-wrap-inner'><thead><tr>"
             "<th scope=\"col\">Jurisdiction</th><th scope=\"col\">What we do</th><th scope=\"col\">Regulator / framework</th>"
             f"<th scope=\"col\">Typical timeline</th>{op_head}</tr></thead><tbody>"
             + "".join(rows) + "</tbody></table></div>")

    op_note = ("" if have_operator else
        '<p style="color:var(--muted);font-size:.9rem">The <strong>operator columns</strong> '
        '(setup cost and sample size, aggregated from 500+ real Consulting24 setups) are being '
        'compiled from anonymized delivery records and will populate here per jurisdiction. The '
        'reference columns reflect current 2026 regulatory facts.</p>')

    title = "Crypto Licensing Index 2026: Cost, Timeline &amp; Regulator"
    desc = ("The Consulting24 Crypto Licensing Index: regulator, service model and 2026 timeline "
            "for 20+ jurisdictions, plus aggregated setup data from 500+ real deliveries.")
    canon = f"{BASE}/licensing-index/"
    ld = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "Organization", "@id": ORG_ID, "name": "Consulting24", "legalName": "X24Consulting OÜ",
         "url": f"{BASE}/", "sameAs": ["https://blog.consulting24.co/"]},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{BASE}/"},
            {"@type": "ListItem", "position": 2, "name": "Licensing Index", "item": canon}]},
        {"@type": "Dataset", "name": "Consulting24 Crypto Licensing Index",
         "description": "Regulator, service model, timeline and (where available) aggregated setup cost per jurisdiction, from 500+ real crypto-company/licence setups.",
         "creator": {"@id": ORG_ID}, "license": f"{BASE}/licensing-index/methodology/",
         "distribution": [
             {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{BASE}/data/licensing-index.json"},
             {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{BASE}/data/jurisdictions.json"}],
         "isAccessibleForFree": True},
        {"@type": "Article", "headline": html.unescape(title),
         "author": {"@type": "Person", "@id": AUTHOR_ID, "name": "Mardo Soo", "url": f"{BASE}/about/",
                    "sameAs": ["https://www.linkedin.com/in/mardo-s-00a05ab0/"], "worksFor": {"@id": ORG_ID}},
         "publisher": {"@id": ORG_ID}, "mainEntityOfPage": canon,
         "dateModified": ref.get("updated", "2026-07-21")}]}, ensure_ascii=False)

    body = f'''{_head(html.unescape(title), html.unescape(desc), canon, ld)}
<div class="wrap"><nav class="breadcrumbs"><a href="/">Home</a> &rsaquo; Licensing Index</nav></div>
<article class="wrap" id="main">
  <h1>Crypto Licensing Index 2026</h1>
  <p class="byline" style="color:var(--muted);font-size:.9rem">By <a href="/about/" rel="author">Mardo Soo</a>, Founder &amp; CEO, Consulting24 &middot; Updated {ref.get("updated","2026-07-21")} &middot; <a href="/licensing-index/methodology/">Methodology</a></p>
  <div class="answer-box" style="background:var(--accent-soft);border-left:4px solid var(--accent);border-radius:8px;padding:16px 20px;margin:0 0 22px"><strong style="color:var(--accent-dark)">Short answer:</strong> This is where Consulting24 publishes what it actually sees delivering crypto companies and licences: the regulator, service model and 2026 timeline for {len(js)} jurisdictions, and, per jurisdiction, aggregated setup data from 500+ real deliveries. Consulting24 delivers directly in {", ".join(html.escape(j["name"]) for j in direct)}.</div>
  <h2>Jurisdiction comparison</h2>
  {table}
  {op_note}
  <h2>How to read this</h2>
  <ul>
    <li><strong>What we do</strong>: direct delivery (we incorporate and file), advise &amp; coordinate (we guide you and coordinate local partners), or comparison-only (we do not provide that licence). Note: Panama is a company + AML programme, not a licence.</li>
    <li><strong>Operator columns</strong>: aggregated, anonymized figures from real Consulting24 engagements. No client-identifying detail. See the <a href="/licensing-index/methodology/">methodology</a>.</li>
    <li>Machine-readable: <a href="/data/licensing-index.json">licensing-index.json</a> and <a href="/data/jurisdictions.json">jurisdictions.json</a>.</li>
  </ul>
  <div class="cta-card"><h2>Not sure which jurisdiction fits?</h2><p>Tell us your model and we will map the right route from real experience, honestly.</p>
  <a href="{WA}" class="btn btn-primary">&#128172; Talk to an expert</a><a href="/#contact-top" class="btn btn-ghost">Free consultation</a></div>
  <p style="color:var(--muted);font-size:.85rem;margin-top:24px">Aggregated, anonymized outcomes; general guidance, not legal advice. Regulations change, and we confirm current requirements for your case.</p>
</article>
{FOOTER}
</body></html>'''
    os.makedirs(os.path.join(ROOT, "licensing-index"), exist_ok=True)
    open(os.path.join(ROOT, "licensing-index", "index.html"), "w", encoding="utf-8").write(body)

    # methodology page
    m_ld = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "Organization", "@id": ORG_ID, "name": "Consulting24", "url": f"{BASE}/"},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{BASE}/"},
            {"@type": "ListItem", "position": 2, "name": "Licensing Index", "item": canon},
            {"@type": "ListItem", "position": 3, "name": "Methodology", "item": f"{canon}methodology/"}]}]}, ensure_ascii=False)
    m_head = _head("Crypto Licensing Index: Methodology | Consulting24",
                   "How the Consulting24 Crypto Licensing Index is built: first-party delivery data, anonymized, no PII, dated and versioned.",
                   f"{canon}methodology/", m_ld).replace('href="../styles.css"', 'href="../../styles.css"')
    m_body = f'''{m_head}
<div class="wrap"><nav class="breadcrumbs"><a href="/">Home</a> &rsaquo; <a href="/licensing-index/">Licensing Index</a> &rsaquo; Methodology</nav></div>
<article class="wrap" id="main">
  <h1>Crypto Licensing Index: Methodology</h1>
  <p>The Index publishes aggregated outcomes from 500+ real crypto-company and licence setups Consulting24 has delivered over 8 years. It is first-party data no law firm or content farm can reproduce.</p>
  <h2>What it publishes</h2>
  <ul><li>Sample size (engagements the figures are drawn from)</li><li>Setup cost (low / typical / high, from actual engagements)</li><li>Timeline (kick-off to completion)</li><li>Top reasons applications were delayed or rejected</li><li>An operator note (no client-identifying detail)</li></ul>
  <h2>Rules</h2>
  <ul>
    <li><strong>Only real, first-hand data.</strong> Every figure comes from Consulting24 delivery records; nothing is estimated or borrowed. Placeholder jurisdictions are not published until real data exists.</li>
    <li><strong>No PII.</strong> No client or company names; aggregates only. Jurisdictions with a very small sample are withheld to prevent re-identification.</li>
    <li><strong>Honest framing.</strong> Panama is a company + AML programme, not a licence. Direct delivery: Estonia, Lithuania, Panama; others advise-and-coordinate; UAE is comparison-only.</li>
    <li><strong>Dated and versioned</strong>, refreshed annually.</li>
  </ul>
  <p style="color:var(--muted);font-size:.85rem;margin-top:24px">General guidance, not legal advice.</p>
</article>
{FOOTER}'''.replace(FOOTER, FOOTER)  # methodology reuses footer
    os.makedirs(os.path.join(ROOT, "licensing-index", "methodology"), exist_ok=True)
    open(os.path.join(ROOT, "licensing-index", "methodology", "index.html"), "w", encoding="utf-8").write(m_body + "\n</body></html>")

    print(f"licensing-index page built ({len(js)} jurisdictions, operator-data={'yes' if have_operator else 'pending'})")

if __name__ == "__main__":
    build()
