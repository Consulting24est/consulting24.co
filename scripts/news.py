#!/usr/bin/env python3
"""news.py — the Consulting24 news desk (manually curated, Google News ready).

Google News eligibility is automatic these days, but it needs three things this site
did not have: genuinely timely dated items, NewsArticle markup, and a news sitemap
that only ever carries the last 48 hours. This builds all three off one JSON store.

The hard rule baked into publish(): every item must cite a reachable primary source
(a regulator, an official journal, a supervisory authority). The site has already been
burned once by invented laws and invented regulators, so an item with no source URL, or
a source URL that does not resolve, is refused rather than published.

    news.py new "ESMA publishes final MiCA guidance on ..."   # scaffold a draft
    news.py publish <slug>                                    # validate + publish it
    news.py build                                             # rebuild hub/sitemap/feed
    news.py list                                              # what is live, what is in the 48h window
    news.py correct <slug> "what was wrong and what it now says"

`build` is idempotent and is what the daily pipeline calls: items age out of
news-sitemap.xml on their own, with nobody having to remember to remove them.
"""
from __future__ import annotations
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://www.consulting24.co"
ORG_ID = f"{BASE}/#business"
AUTHOR_ID = f"{BASE}/about/#mardo-soo"
STORE = os.path.join(ROOT, "config", "news_items.json")
DRAFTS = os.path.join(ROOT, "news", "_drafts")
PUB_NAME = "Consulting24"           # must match the publication name in Publisher Center
LANG = "en"
WINDOW_HOURS = 48                   # Google News sitemap: last two days only
WA = "https://wa.me/37258155779?text=Hi%2C%20I%27d%20like%20to%20ask%20about%20a%20crypto%20company%20setup."
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_header import HEADER, HEAD_ASSETS  # shared site header (scripts/site_header.py)

# Markers from the 2026-07 fabrication incident. If any of these reappear in a news
# item it is almost certainly a hallucination resurfacing, so refuse the publish.
FORBIDDEN = [
    (r"\bAFIP\b", "AFIP is Argentina's tax agency; it has no Panama crypto role"),
    (r"\bLaw\s+697\b", "Law 697 does not exist as a Panama crypto law"),
    (r"\bLaw\s+61\s+of\s+2023\b", "invented law"),
    (r"\bLaw\s+164\s+of\s+2020\b", "invented law"),
    (r"Panama Financial Innovation Law", "invented law"),
    (r"\bSSNF\b[^.]{0,60}\blicen[cs]", "the SSNF does not license crypto (AML supervision only)"),
]


# ---------------------------------------------------------------- store / util

def _load() -> dict:
    if os.path.exists(STORE):
        with open(STORE, encoding="utf-8") as f:
            return json.load(f)
    return {"publication": PUB_NAME, "updated": None, "items": []}


def _save(store: dict) -> None:
    store["updated"] = _now().isoformat()
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    with open(STORE, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    if len(s) > 80:                      # trim on a word boundary, never mid-word
        s = s[:80].rsplit("-", 1)[0]
    return s.strip("-")


def _clean(text: str) -> str:
    """Match house style: no em/en dashes, no exclamation marks."""
    return (text.replace("—", ", ").replace("–", "-")
                .replace("!", ".").replace(" ", " "))


def _e(s: str) -> str:
    return html.escape(s, quote=True)


def _human_date(iso: str) -> str:
    d = dt.datetime.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B %Y')}"


def _rfc822(iso: str) -> str:
    d = dt.datetime.fromisoformat(iso)
    return d.strftime("%a, %d %b %Y %H:%M:%S +0000")


def _url_ok(url: str) -> tuple[bool, str]:
    """A source has to actually exist. HEAD first, GET as fallback (many sites 405 HEAD)."""
    hdr = {"User-Agent": "Mozilla/5.0 (compatible; Consulting24NewsDesk/1.0)"}
    last = "no response"
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers=hdr)
            with urllib.request.urlopen(req, timeout=20) as r:
                if 200 <= r.status < 400:
                    return True, f"HTTP {r.status}"
        except Exception as exc:  # noqa: BLE001 - any failure means "cannot verify"
            last = f"{type(exc).__name__}: {exc}"
    return False, last


# ---------------------------------------------------------------- draft format

DRAFT_TEMPLATE = """title: {title}
summary:
source_name:
source_url:
source_date:
jurisdiction:
keywords:

Write the item below this blank line, one paragraph per block.

Rules that publish() enforces:
  - summary is the standfirst (60-300 chars) shown in the hub, RSS and search
  - source_url must be the PRIMARY source (regulator, official journal, supervisor)
    and must resolve, or the publish is refused
  - report what the source says, then add the Consulting24 operator read as its own
    paragraph starting with "What this means:" so opinion is visibly separated from fact

Use "## Subheading" on its own line for sections and [text](https://url) for links.
"""


def cmd_new(headline: str) -> None:
    slug = slugify(headline)
    os.makedirs(DRAFTS, exist_ok=True)
    path = os.path.join(DRAFTS, f"{slug}.md")
    if os.path.exists(path):
        sys.exit(f"draft already exists: {path}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(DRAFT_TEMPLATE.format(title=headline))
    print(f"draft created: {os.path.relpath(path, ROOT)}\nfill it in, then: python3 scripts/news.py publish {slug}")


def parse_draft(path: str) -> dict:
    raw = open(path, encoding="utf-8").read()
    meta, body_lines, in_body = {}, [], False
    for line in raw.splitlines():
        if not in_body:
            if not line.strip():
                in_body = True
                continue
            m = re.match(r"^([a-z_]+):\s*(.*)$", line)
            if m:
                meta[m.group(1)] = m.group(2).strip()
                continue
            in_body = True
        body_lines.append(line)
    return {"meta": meta, "body": "\n".join(body_lines).strip()}


def render_body(md: str) -> str:
    """Deliberately small markdown subset: paragraphs, ## headings, links, bullets."""
    out = []
    for block in re.split(r"\n\s*\n", md.strip()):
        block = block.strip()
        if not block:
            continue
        block = _e(block)
        block = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
                       lambda m: f'<a href="{m.group(2)}" rel="nofollow noopener" target="_blank">{m.group(1)}</a>',
                       block)
        if block.startswith("## "):
            out.append(f"<h2>{block[3:].strip()}</h2>")
        elif block.startswith("- "):
            items = "".join(f"<li>{l.lstrip('- ').strip()}</li>" for l in block.splitlines())
            out.append(f"<ul>{items}</ul>")
        else:
            text = block.replace("\n", " ")
            if text.startswith("What this means:"):
                out.append('<p class="callout"><strong>What this means:</strong>'
                           f'{text[len("What this means:"):]}</p>')
            else:
                out.append(f"<p>{text}</p>")
    return "\n  ".join(out)


# ---------------------------------------------------------------- publish

def cmd_publish(slug: str, verify: bool = True) -> None:
    path = slug if os.path.exists(slug) else os.path.join(DRAFTS, f"{slug}.md")
    if not os.path.exists(path):
        sys.exit(f"no draft at {path}")
    slug = os.path.splitext(os.path.basename(path))[0]
    d = parse_draft(path)
    meta, body = d["meta"], _clean(d["body"])
    errs = []

    title = _clean(meta.get("title", "")).strip()
    summary = _clean(meta.get("summary", "")).strip()
    src_name = meta.get("source_name", "").strip()
    src_url = meta.get("source_url", "").strip()
    src_date = meta.get("source_date", "").strip()

    if not title:
        errs.append("title is empty")
    elif len(title) > 110:
        errs.append(f"title is {len(title)} chars, keep a news headline under 110")
    if not (60 <= len(summary) <= 300):
        errs.append(f"summary is {len(summary)} chars, needs 60-300")
    if not src_name:
        errs.append("source_name is empty (name the regulator or official publisher)")
    if not src_url.startswith(("http://", "https://")):
        errs.append("source_url must be a primary-source http(s) URL, this is not optional")
    if src_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", src_date):
        errs.append("source_date must be YYYY-MM-DD")

    words = len(re.findall(r"\w+", body))
    if words < 120:
        errs.append(f"body is {words} words, a news item needs at least 120")

    for pat, why in FORBIDDEN:
        if re.search(pat, title + " " + summary + " " + body, re.I):
            errs.append(f"fabrication marker {pat!r}: {why}")

    if errs:
        print("REFUSED to publish:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    if verify:
        ok, detail = _url_ok(src_url)
        if not ok:
            sys.exit(f"REFUSED: source_url did not resolve ({detail})\n  {src_url}\n"
                     f"  Fix the link, or re-run with --no-verify if the source blocks bots "
                     f"(you are then vouching for it yourself).")
        print(f"source verified: {detail}")
    else:
        print("WARNING: --no-verify, source URL was NOT checked")

    store = _load()
    now = _now().isoformat()
    existing = next((i for i in store["items"] if i["slug"] == slug), None)
    item = {
        "slug": slug,
        "title": title,
        "summary": summary,
        "body_html": render_body(body),
        "source_name": src_name,
        "source_url": src_url,
        "source_date": src_date or None,
        "jurisdiction": meta.get("jurisdiction", "").strip() or None,
        "keywords": [k.strip() for k in meta.get("keywords", "").split(",") if k.strip()],
        "published": existing["published"] if existing else now,
        "modified": now,
        "corrections": existing.get("corrections", []) if existing else [],
    }
    if existing:
        store["items"] = [item if i["slug"] == slug else i for i in store["items"]]
        print(f"updated existing item /news/{slug}/")
    else:
        store["items"].append(item)
    _save(store)
    build()
    print(f"published: {BASE}/news/{slug}/")


def cmd_correct(slug: str, note: str) -> None:
    """Google News transparency: corrections are dated and visible, never silent edits."""
    store = _load()
    item = next((i for i in store["items"] if i["slug"] == slug), None)
    if not item:
        sys.exit(f"no published item with slug {slug}")
    item.setdefault("corrections", []).append(
        {"date": _now().date().isoformat(), "note": _clean(note).strip()})
    item["modified"] = _now().isoformat()
    _save(store)
    build()
    print(f"correction appended to /news/{slug}/")


# ---------------------------------------------------------------- rendering

def _head(title: str, desc: str, canon: str, ld: str, depth: int, keywords=None) -> str:
    css = "../" * depth + "styles.css"
    kw = f'\n<meta name="news_keywords" content="{_e(", ".join(keywords))}">' if keywords else ""
    return f'''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_e(title)}</title>
<meta name="description" content="{_e(desc)}">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">{kw}
<link rel="canonical" href="{canon}">
<meta property="og:title" content="{_e(title)}"><meta property="og:description" content="{_e(desc)}">
<meta property="og:type" content="article"><meta property="og:url" content="{canon}"><meta property="og:image" content="{BASE}/og-image.jpg">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{_e(title)}"><meta name="twitter:description" content="{_e(desc)}"><meta name="twitter:image" content="{BASE}/og-image.jpg">
<link rel="alternate" type="application/rss+xml" title="Consulting24 crypto licensing news" href="{BASE}/news/feed.xml">
<script type="application/ld+json">{ld}</script>
<link rel="stylesheet" href="{css}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml"><link rel="icon" href="/favicon.ico" sizes="32x32"><link rel="apple-touch-icon" href="/apple-touch-icon.png">
{HEAD_ASSETS}
</head><body>
<a href="#main" class="skip">Skip to main content</a>
{HEADER}'''


FOOTER = '''<footer><div class="wrap"><div class="foot-grid">
  <div><h2>Consulting24</h2><p style="color:#a3a3a3">500+ crypto licenses across Estonia, Lithuania, Panama and beyond.</p><p style="margin-top:14px"><strong style="color:#fff">WhatsApp / email</strong><br>mardo@consulting24.co</p></div>
  <div><h2>Jurisdictions</h2><a href="/jurisdictions/">All jurisdictions</a><a href="/">Panama</a><a href="/lithuania-crypto-license/">Lithuania</a><a href="/estonia-crypto-license/">Estonia</a></div>
  <div><h2>Resources</h2><a href="/news/">News</a><a href="/licensing-index/">Licensing Index</a><a href="/best-country-for-crypto-license/">Best country</a><a href="/blog/">Blog</a></div>
  <div><h2>Company</h2><a href="/about/">About Consulting24</a><a href="/editorial-policy/">Editorial policy</a><a href="/contact/">Contact</a><a href="https://www.linkedin.com/in/mardo-s-00a05ab0/">Mardo Soo on LinkedIn</a></div>
</div><div class="foot-bottom">&copy; 2026 Consulting24 &middot; X24Consulting O&Uuml; &middot; Reg nr 16971898 &middot; Poordi 3-63, 10156 Tallinn, Estonia &middot; General guidance, not legal advice.</div></div></footer>
</body></html>'''


def _org_node() -> dict:
    return {"@type": "NewsMediaOrganization", "@id": ORG_ID, "name": "Consulting24",
            "legalName": "X24Consulting OÜ", "url": f"{BASE}/",
            "logo": {"@type": "ImageObject", "url": f"{BASE}/img/mardo-soo-profile.jpg"},
            "ethicsPolicy": f"{BASE}/editorial-policy/",
            "correctionsPolicy": f"{BASE}/editorial-policy/#corrections",
            "identifier": {"@type": "PropertyValue", "propertyID": "Estonian Business Register",
                           "value": "16971898"},
            "address": {"@type": "PostalAddress", "streetAddress": "Poordi 3-63",
                        "addressLocality": "Tallinn", "postalCode": "10156", "addressCountry": "EE"},
            "sameAs": ["https://blog.consulting24.co/"]}


def _author_node() -> dict:
    return {"@type": "Person", "@id": AUTHOR_ID, "name": "Mardo Soo",
            "jobTitle": "Founder & CEO", "url": f"{BASE}/about/",
            "sameAs": ["https://www.linkedin.com/in/mardo-s-00a05ab0/"],
            "worksFor": {"@id": ORG_ID}}


def render_item(item: dict) -> str:
    canon = f"{BASE}/news/{item['slug']}/"
    pub, mod = item["published"], item["modified"]
    corrections = ""
    if item.get("corrections"):
        rows = "".join(f"<li><strong>{c['date']}:</strong> {_e(c['note'])}</li>"
                       for c in item["corrections"])
        corrections = ('<div id="corrections" style="border-left:4px solid #d97706;background:#fffbeb;'
                       'border-radius:8px;padding:14px 18px;margin:22px 0">'
                       f'<strong>Corrections</strong><ul style="margin:8px 0 0">{rows}</ul></div>')

    src_date = f" ({item['source_date']})" if item.get("source_date") else ""
    source_box = ('<div class="callout" style="margin:22px 0"><strong>Primary source:</strong> '
                  f'<a href="{item["source_url"]}" rel="nofollow noopener" target="_blank">'
                  f'{_e(item["source_name"])}</a>{src_date}. '
                  'Consulting24 reports what the source states and labels its own reading separately. '
                  'See our <a href="/editorial-policy/">editorial policy</a>.</div>')

    news = {"@type": "NewsArticle", "headline": item["title"], "description": item["summary"],
            "datePublished": pub, "dateModified": mod,
            "url": canon, "mainEntityOfPage": {"@type": "WebPage", "@id": canon},
            "image": [f"{BASE}/og-image.jpg"],
            "author": {"@id": AUTHOR_ID}, "publisher": {"@id": ORG_ID},
            "inLanguage": LANG, "isAccessibleForFree": True,
            "isBasedOn": item["source_url"],
            "citation": {"@type": "CreativeWork", "name": item["source_name"],
                         "url": item["source_url"]}}
    if item.get("keywords"):
        news["keywords"] = ", ".join(item["keywords"])
    if item.get("jurisdiction"):
        news["contentLocation"] = {"@type": "Place", "name": item["jurisdiction"]}
    if item.get("corrections"):
        news["correction"] = [f"{c['date']}: {c['note']}" for c in item["corrections"]]

    ld = json.dumps({"@context": "https://schema.org", "@graph": [
        _org_node(), _author_node(),
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{BASE}/"},
            {"@type": "ListItem", "position": 2, "name": "News", "item": f"{BASE}/news/"},
            {"@type": "ListItem", "position": 3, "name": item["title"], "item": canon}]},
        news]}, ensure_ascii=False)

    title_tag = f"{item['title']} | Consulting24"
    juris = f' &middot; {_e(item["jurisdiction"])}' if item.get("jurisdiction") else ""
    return f'''{_head(title_tag, item["summary"], canon, ld, 2, item.get("keywords"))}
<div class="wrap"><nav class="breadcrumbs"><a href="/">Home</a> &rsaquo; <a href="/news/">News</a> &rsaquo; {_e(item["title"])}</nav></div>
<article class="wrap" id="main">
  <p class="eyebrow">Regulatory news{juris}</p>
  <h1>{_e(item["title"])}</h1>
  <p class="byline" style="color:var(--muted);font-size:.9rem">By <a href="/about/" rel="author">Mardo Soo</a>, Founder &amp; CEO, Consulting24 &middot; Published <time datetime="{pub}">{_human_date(pub)}</time>{f' &middot; Updated <time datetime="{mod}">{_human_date(mod)}</time>' if mod[:10] != pub[:10] else ''}</p>
  <p class="lead">{_e(item["summary"])}</p>
  {source_box}
  {item["body_html"]}
  {corrections}
  <div class="cta-card"><h2>Does this change your licensing route?</h2><p>We deliver directly in Estonia, Lithuania and Panama, and advise on the rest. Ask what this means for your setup.</p>
  <a href="{WA}" class="btn btn-primary">&#128172; Talk to an expert</a><a href="/contact/" class="btn btn-ghost">Contact us</a></div>
  <p style="color:var(--muted);font-size:.85rem;margin-top:24px">General guidance, not legal advice. Regulations change, and we confirm current requirements for your case.</p>
</article>
{FOOTER}'''


def render_hub(items: list) -> str:
    canon = f"{BASE}/news/"
    cards = []
    for i in items:
        juris = f'<span class="cat">{_e(i["jurisdiction"])}</span>' if i.get("jurisdiction") else '<span class="cat">Regulatory</span>'
        cards.append(
            f'<li style="border-bottom:1px solid var(--line,#e5e7eb);padding:18px 0">'
            f'{juris} <time datetime="{i["published"]}" style="color:var(--muted);font-size:.88rem">{_human_date(i["published"])}</time>'
            f'<h2 style="margin:6px 0 4px;font-size:1.18rem"><a href="/news/{i["slug"]}/">{_e(i["title"])}</a></h2>'
            f'<p style="margin:0;color:var(--muted)">{_e(i["summary"])}</p>'
            f'<p style="margin:6px 0 0;font-size:.85rem;color:var(--muted)">Source: {_e(i["source_name"])}</p></li>')
    body = ("<ul style='list-style:none;padding:0;margin:0'>" + "".join(cards) + "</ul>") if cards else (
        "<p>No items published yet. This desk only publishes when a regulator or official "
        "source actually issues something, so quiet weeks stay quiet.</p>")

    ld = json.dumps({"@context": "https://schema.org", "@graph": [
        _org_node(), _author_node(),
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{BASE}/"},
            {"@type": "ListItem", "position": 2, "name": "News", "item": canon}]},
        {"@type": "CollectionPage", "@id": canon, "name": "Crypto licensing news",
         "description": "Regulatory developments affecting crypto licensing, each sourced to a primary regulator publication.",
         "isPartOf": {"@id": ORG_ID}, "publisher": {"@id": ORG_ID},
         "mainEntity": {"@type": "ItemList", "itemListElement": [
             {"@type": "ListItem", "position": n + 1, "url": f"{BASE}/news/{i['slug']}/"}
             for n, i in enumerate(items[:30])]}}]}, ensure_ascii=False)

    title = "Crypto licensing news: regulators, MiCA and VASP rules | Consulting24"
    desc = ("Dated regulatory news for crypto founders: MiCA, CASP and VASP developments, "
            "each item sourced to the regulator publication it reports on.")
    return f'''{_head(title, desc, canon, ld, 1)}
<div class="wrap"><nav class="breadcrumbs"><a href="/">Home</a> &rsaquo; News</nav></div>
<article class="wrap" id="main">
  <h1>Crypto licensing news</h1>
  <p class="lead">Regulatory developments that change how, where and how fast a crypto business can be licensed. Every item names the primary source it reports on and links straight to it.</p>
  <p style="color:var(--muted);font-size:.9rem">Written by <a href="/about/" rel="author">Mardo Soo</a>, Founder &amp; CEO of Consulting24, who has delivered 500+ crypto company and licence setups since 2018. How we source and correct: <a href="/editorial-policy/">editorial policy</a>. Feed: <a href="/news/feed.xml">RSS</a>.</p>
  {body}
  <div class="cta-card"><h2>Need this read for your own setup?</h2><p>Rules move. We tell you what a change means for your jurisdiction and timeline, honestly, including when it means "wait".</p>
  <a href="{WA}" class="btn btn-primary">&#128172; Talk to an expert</a><a href="/contact/" class="btn btn-ghost">Contact us</a></div>
</article>
{FOOTER}'''


EDITORIAL = None  # built in build(), needs the item list for the "how many" line


def render_editorial() -> str:
    canon = f"{BASE}/editorial-policy/"
    ld = json.dumps({"@context": "https://schema.org", "@graph": [
        _org_node(), _author_node(),
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{BASE}/"},
            {"@type": "ListItem", "position": 2, "name": "Editorial policy", "item": canon}]},
        {"@type": "WebPage", "@id": canon, "name": "Editorial policy",
         "description": "How Consulting24 sources, writes, funds and corrects its published content.",
         "publisher": {"@id": ORG_ID}}]}, ensure_ascii=False)
    title = "Editorial policy | Consulting24"
    desc = ("How Consulting24 sources, writes, funds and corrects what it publishes: named author, "
            "primary sources, dated corrections, and a clear statement of commercial interest.")
    return f'''{_head(title, desc, canon, ld, 1)}
<div class="wrap"><nav class="breadcrumbs"><a href="/">Home</a> &rsaquo; Editorial policy</nav></div>
<article class="wrap" id="main">
  <h1>Editorial policy</h1>
  <p class="lead">Consulting24 publishes regulatory news and licensing guidance that founders use to make expensive decisions. This page states who writes it, where the facts come from, how it is funded, and what happens when we get something wrong.</p>

  <h2>Who publishes this</h2>
  <p>Consulting24 is the trading name of X24Consulting O&Uuml; (Estonian Business Register 16971898), Poordi 3-63, 10156 Tallinn, Estonia. Editorial responsibility sits with <a href="/about/">Mardo Soo</a>, Founder and CEO, who has delivered 500+ crypto company and licence setups since 2018. Reach the newsroom at mardo@consulting24.co or via the <a href="/contact/">contact page</a>.</p>

  <h2>Sourcing</h2>
  <p>Every news item cites a primary source: a regulator, a supervisory authority, an official journal, or a published statute. The source is named and linked in the item itself, not buried. Our publishing tool refuses to publish a news item whose source link is missing or does not resolve.</p>
  <p>We report what the source says first. Our own interpretation is labelled separately in each item under "What this means", so a reader can tell the record apart from the opinion.</p>

  <h2>Accuracy and AI</h2>
  <p>Reference and guidance pages on this site are drafted with AI assistance and reviewed against published regulator sources before release. News items are written and checked by a person. No law, regulator, case number or fine appears on this site unless it exists in a source we can link. Where a jurisdiction has no licensing regime, we say so plainly rather than describing one that does not exist.</p>

  <h2 id="corrections">Corrections</h2>
  <p>When we get something wrong we correct it in place, add a dated correction note at the foot of the item, and update the modification date. We do not delete an item to hide an error. To report one, email mardo@consulting24.co with the URL and what is wrong; substantive reports are answered.</p>

  <h2>Funding and commercial interest</h2>
  <p>Consulting24 earns money from licensing and company-formation engagements. That is a real interest and we state it rather than hiding it: we deliver directly in Estonia, Lithuania and Panama, advise and coordinate in most other jurisdictions, and provide comparison-only information for the UAE, where we do not provide licensing. We do not sell sponsored posts, paid placements or paid links, and no third party pays to influence what appears in our news or guidance.</p>

  <h2>Independence from the sale</h2>
  <p>Coverage does not change to suit the sale. If a jurisdiction we deliver in becomes slower, more expensive or riskier, we publish that. Our <a href="/licensing-index/">Licensing Index</a> exists to hold us to figures drawn from real deliveries rather than marketing claims.</p>

  <p style="color:var(--muted);font-size:.85rem;margin-top:24px">Everything we publish is general guidance, not legal advice. Regulations change, and we confirm current requirements for your specific case before you act.</p>
</article>
{FOOTER}'''


# ---------------------------------------------------------------- feeds

def build_news_sitemap(items: list) -> int:
    """Google News sitemap: last 48h only. Older items drop out on the next build."""
    cutoff = _now() - dt.timedelta(hours=WINDOW_HOURS)
    fresh = [i for i in items if dt.datetime.fromisoformat(i["published"]) >= cutoff][:1000]
    urls = "".join(
        f'''  <url>
    <loc>{BASE}/news/{i["slug"]}/</loc>
    <news:news>
      <news:publication><news:name>{_e(PUB_NAME)}</news:name><news:language>{LANG}</news:language></news:publication>
      <news:publication_date>{i["published"]}</news:publication_date>
      <news:title>{_e(i["title"])}</news:title>
    </news:news>
  </url>\n''' for i in fresh)
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
           '        xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">\n'
           f'{urls}</urlset>\n')
    with open(os.path.join(ROOT, "news-sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(xml)
    return len(fresh)


def build_feed(items: list) -> None:
    entries = "".join(f'''    <item>
      <title>{_e(i["title"])}</title>
      <link>{BASE}/news/{i["slug"]}/</link>
      <guid isPermaLink="true">{BASE}/news/{i["slug"]}/</guid>
      <pubDate>{_rfc822(i["published"])}</pubDate>
      <description>{_e(i["summary"])}</description>
      <source url="{_e(i["source_url"])}">{_e(i["source_name"])}</source>
    </item>\n''' for i in items[:20])
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Consulting24 crypto licensing news</title>
    <link>{BASE}/news/</link>
    <atom:link href="{BASE}/news/feed.xml" rel="self" type="application/rss+xml"/>
    <description>Regulatory developments affecting crypto licensing, each sourced to a primary regulator publication.</description>
    <language>{LANG}</language>
    <lastBuildDate>{_rfc822(_now().isoformat())}</lastBuildDate>
{entries}  </channel>
</rss>
'''
    with open(os.path.join(ROOT, "news", "feed.xml"), "w", encoding="utf-8") as f:
        f.write(xml)


def build() -> None:
    store = _load()
    items = sorted(store["items"], key=lambda i: i["published"], reverse=True)
    os.makedirs(os.path.join(ROOT, "news"), exist_ok=True)
    for i in items:
        d = os.path.join(ROOT, "news", i["slug"])
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
            f.write(render_item(i))
    with open(os.path.join(ROOT, "news", "index.html"), "w", encoding="utf-8") as f:
        f.write(render_hub(items))
    os.makedirs(os.path.join(ROOT, "editorial-policy"), exist_ok=True)
    with open(os.path.join(ROOT, "editorial-policy", "index.html"), "w", encoding="utf-8") as f:
        f.write(render_editorial())
    fresh = build_news_sitemap(items)
    build_feed(items)
    print(f"news: {len(items)} items, {fresh} in the {WINDOW_HOURS}h news-sitemap window")


def cmd_list() -> None:
    store = _load()
    items = sorted(store["items"], key=lambda i: i["published"], reverse=True)
    cutoff = _now() - dt.timedelta(hours=WINDOW_HOURS)
    if not items:
        print("no published news items yet")
    for i in items:
        live = "IN news-sitemap" if dt.datetime.fromisoformat(i["published"]) >= cutoff else "aged out"
        print(f"{i['published'][:16]}  [{live:16}]  /news/{i['slug']}/  ({i['source_name']})")
    live = {i["slug"] for i in items}
    drafts = sorted(f[:-3] for f in os.listdir(DRAFTS)
                    if f.endswith(".md") and f[:-3] not in live) if os.path.isdir(DRAFTS) else []
    if drafts:
        print("\ndrafts awaiting publish: " + ", ".join(drafts))


def cmd_wire() -> None:
    """Link /news/ and /editorial-policy/ from every page footer.

    A news section nobody links to is a news section Google will not crawl often enough
    to matter, and Google News wants the publisher/editorial info reachable from anywhere.
    Idempotent: pages that already carry the links are skipped.
    """
    import glob
    add = '<a href="/news/">News</a><a href="/editorial-policy/">Editorial policy</a>'
    touched = 0
    for path in glob.glob(os.path.join(ROOT, "**", "index.html"), recursive=True):
        rel = os.path.relpath(path, ROOT)
        if rel.startswith(("news/", "editorial-policy/")):
            continue
        h = open(path, encoding="utf-8").read()
        if "<footer" not in h or 'href="/news/"' in h:
            continue
        # most pages have a Resources column; the homepage does not, so fall back to
        # the first footer column heading whatever it is called
        new = re.sub(r"(<h2>Resources</h2>\s*)", r"\1" + add, h, count=1)
        if new == h:
            new = re.sub(r"(<footer[^>]*>.*?<h2>[^<]*</h2>\s*)", r"\1" + add, h,
                         count=1, flags=re.S)
        if new != h:
            open(path, "w", encoding="utf-8").write(new)
            touched += 1
    print(f"wire: added news + editorial-policy footer links to {touched} pages")


USAGE = __doc__


def main(argv: list) -> None:
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return
    cmd, rest = argv[0], argv[1:]
    if cmd == "new" and rest:
        cmd_new(" ".join(rest))
    elif cmd == "publish" and rest:
        cmd_publish(rest[0], verify="--no-verify" not in rest)
    elif cmd == "build":
        build()
    elif cmd == "wire":
        cmd_wire()
    elif cmd == "list":
        cmd_list()
    elif cmd == "correct" and len(rest) >= 2:
        cmd_correct(rest[0], " ".join(rest[1:]))
    else:
        print(USAGE)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv[1:])
