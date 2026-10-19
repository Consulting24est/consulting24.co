#!/usr/bin/env python3
"""
autoseo_pull.py — import AutoSEO (getautoseo.com) articles into the site's /blog/.

AutoSEO has no GitHub Pages integration, so its "RSS/Feeds" option is used: AutoSEO
publishes finished articles to a token-protected JSON Feed, and this script pulls it and
renders each English article with the SAME template as every other /blog/ post
(generate.assemble: header, byline, schema, FAQPage, related guides, footer).

  feed URL   $AUTOSEO_FEED_URL or scripts/.autoseo_feed_url (gitignored; token is in the URL)
  state      config/autoseo_imported.json  {autoseo id: {slug, date_modified, date_published}}
  held       config/autoseo_held.json      articles that failed a YMYL honesty gate (never published)

Per article:
  - English only (the site's zh/es/ar copies come from scripts/translate_pages.py).
  - New id -> blog/<slug>/index.html. Changed date_modified -> re-render, keeping datePublished.
  - Never overwrites a post this script did not create (slug collision = skipped + logged).
  - AutoSEO's hero figure is dropped (gen_blog_images.py makes the site's branded hero set);
    its infographic is downloaded into img/blog/ (no hotlinking).
  - The "Table of Contents" block is dropped (its #anchors die in assemble's id-less <h2>s);
    the FAQ section becomes the template's FAQ block + FAQPage schema.
  - Links to consulting24.co become relative; every other external link gets
    rel="nofollow noopener" like the site's own source links. This also neutralises any
    links AutoSEO's backlink exchange inserts.
  - generate._clean house style (no em-dashes / AI-cliche words) + generate.qc honesty gates
    (fabricated approval stats, approval guarantees, invented Panama crypto licence).
    A hit holds the article in config/autoseo_held.json instead of publishing it.
  - Items that disappear from the feed are left alone (never delete published pages).

After importing anything: gen_blog_images.py (hero sets) -> blog_image_seo.py ->
rebuild_indexes.py (/blog/ hub cards) -> publish.py (sitemaps, inlinks, IndexNow).

Usage:
  python3 scripts/autoseo_pull.py                    # import into the working tree, no git
  python3 scripts/autoseo_pull.py --commit           # ...then commit + push (origin + live)
  python3 scripts/autoseo_pull.py --preview DIR      # render to DIR only; repo untouched
  python3 scripts/autoseo_pull.py --feed-file F.json # use a saved feed instead of fetching
"""
from __future__ import annotations
import argparse, datetime, html, importlib.util, json, os, re, subprocess, sys, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "config", "autoseo_imported.json")
HELD = os.path.join(ROOT, "config", "autoseo_held.json")
LOG = os.path.join(ROOT, "logs", "autoseo_pull.log")
UA = {"User-Agent": "Mozilla/5.0 (consulting24.co autoseo_pull)"}
OWN_HOSTS = {"consulting24.co", "www.consulting24.co"}
# generate.qc() failures that must never ship on a YMYL page (the rest are DeepSeek-length
# gates that do not apply to AutoSEO copy, so they are only logged)
HARD_FAILS = ("fabricated success/approval rate", "approval guarantee", "panama crypto-licence fabrication")

spec = importlib.util.spec_from_file_location("gen", os.path.join(ROOT, "scripts", "generate.py"))
gen = importlib.util.module_from_spec(spec); spec.loader.exec_module(gen)

def log(msg):
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f: f.write(line + "\n")

def load_json(p, default):
    try:
        with open(p, encoding="utf-8") as f: return json.load(f)
    except FileNotFoundError:
        return default

def save_json(p, data):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True); f.write("\n")

def feed_url():
    u = os.environ.get("AUTOSEO_FEED_URL", "").strip()
    p = os.path.join(ROOT, "scripts", ".autoseo_feed_url")
    if not u and os.path.exists(p): u = open(p).read().strip()
    if not u: sys.exit("No feed URL (set AUTOSEO_FEED_URL or scripts/.autoseo_feed_url)")
    return u

def fetch_feed(feed_file=None):
    if feed_file:
        with open(feed_file, encoding="utf-8") as f: return json.load(f)
    with urllib.request.urlopen(urllib.request.Request(feed_url(), headers=UA), timeout=60) as r:
        return json.load(r)

def slug_of(item):
    """Slug from the URL AutoSEO assigned (it already uses /blog/<slug>), else from the title."""
    path = urllib.parse.urlparse(item.get("url") or "").path.rstrip("/")
    s = path.rsplit("/", 1)[-1] if path.startswith("/blog/") else ""
    s = re.sub(r"[^a-z0-9]+", "-", (s or gen.plain(item.get("title", ""))).lower()).strip("-")
    return s[:90].rstrip("-")

def _fix_links(h):
    def repl(m):
        tag = m.group(0)
        href = html.unescape(m.group(1))
        u = urllib.parse.urlparse(href)
        if u.scheme in ("http", "https") and u.netloc.lower() in OWN_HOSTS:
            path = u.path or "/"
            if path != "/" and not path.endswith("/") and "." not in path.rsplit("/", 1)[-1]:
                path += "/"                                   # site URLs are directory-style
            rel = path + (("#" + u.fragment) if u.fragment else "")
            return re.sub(r'\s(?:target|rel)="[^"]*"', "", tag).replace(m.group(1), gen.esc_attr(rel), 1)
        if u.scheme in ("http", "https"):
            tag = re.sub(r'\s(?:target|rel)="[^"]*"', "", tag)
            return tag[:-1] + ' target="_blank" rel="nofollow noopener">'
        return tag
    return re.sub(r'<a\b[^>]*?href="([^"]*)"[^>]*>', repl, h)

def _download(url, dest):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        f.write(r.read())

def _localise_images(h, slug, img_dir):
    """Infographics/inline images: download into img/blog/ and point at the local copy."""
    n = 0
    def repl(m):
        nonlocal n
        src = html.unescape(m.group(1))
        if not src.startswith("http"): return m.group(0)
        n += 1
        ext = os.path.splitext(urllib.parse.urlparse(src).path)[1].lower()
        ext = ext if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif") else ".jpg"
        name = f"{slug}-autoseo-{n}{ext}"
        dest = os.path.join(img_dir, name)
        size = ""
        try:
            if not os.path.exists(dest): _download(src, dest)
            if os.path.exists(dest):
                from PIL import Image
                with Image.open(dest) as im: size = f' width="{im.width}" height="{im.height}"'
            local = f"/img/blog/{name}"
        except Exception as e:
            log(f"  image download failed ({e}); keeping remote {src}")
            local = src
        tag = re.sub(r'\s(?:style|loading|decoding|width|height)="[^"]*"', "", m.group(0))
        tag = tag.replace(m.group(1), gen.esc_attr(local), 1)
        tag = re.sub(r"\s*/?>$", "", tag)
        return (f'{tag}{size} loading="lazy" decoding="async" '
                f'style="width:100%;height:auto;border-radius:14px;border:1px solid var(--line)">')
    return re.sub(r'<img\b[^>]*?src="([^"]*)"[^>]*>', repl, h)

def to_d(item, slug, img_dir):
    """AutoSEO item -> the dict generate.assemble() renders (same shape DeepSeek returns)."""
    h = item.get("content_html") or ""
    h = re.sub(r'<figure class="autoseo-hero-image".*?</figure>', "", h, count=1, flags=re.S)
    h = _localise_images(_fix_links(h), slug, img_dir)
    parts = re.split(r"<h2\b[^>]*>(.*?)</h2>", h, flags=re.S)
    intro, sections, faq_html = parts[0].strip(), [], ""
    for i in range(1, len(parts), 2):
        title = re.sub(r"<[^>]+>", "", parts[i]).strip()
        body = parts[i + 1].strip()
        low = title.lower()
        if low in ("table of contents", "contents"): continue
        if "frequently asked" in low or low == "faq" or low == "faqs":
            faq_html = body; continue
        sections.append({"h2": gen.plain(title), "html": body})
    seo = item.get("_seo") or {}
    faqs = [{"q": gen.plain(f.get("question", "")), "a": gen.esc_text(gen.plain(f.get("answer", "")))}
            for f in (seo.get("faq_schema") or []) if f.get("question") and f.get("answer")]
    if not faqs and faq_html:   # fall back to the visible <h3>Q</h3><p>A</p> pairs
        for q, a in re.findall(r"<h3\b[^>]*>(.*?)</h3>\s*(.*?)(?=<h3\b|$)", faq_html, flags=re.S):
            faqs.append({"q": gen.plain(re.sub(r"<[^>]+>", "", q)).strip(),
                         "a": re.sub(r"</?p\b[^>]*>", "", a).strip()})
    title = gen.plain(item.get("title", ""))
    d = {"meta_title": title, "h1": title,
         "meta_description": gen.plain(seo.get("meta_description") or item.get("summary") or ""),
         "intro_html": intro, "sections": sections, "faqs": faqs, "authority_links": []}
    return gen._trim_meta(gen._clean_d(d))

def render(item, slug, d, date_published):
    words = [w for w in re.sub(r"[^A-Za-z0-9 ]", " ", d["h1"]).split()]
    crumb = " ".join(words[:8]) if len(d["h1"]) > 60 else d["h1"]
    page = gen.assemble(slug, crumb, d, "blog").replace("/panama-crypto-license/", "/").replace("/panama/", "/")
    page = gen._table_scope(gen._sanitize_internal_links(page))
    today = datetime.date.today().isoformat()
    modified = (item.get("date_modified") or "")[:10] or today
    page = page.replace(f'"datePublished":"{today}","dateModified":"{today}"',
                        f'"datePublished":"{date_published}","dateModified":"{modified}"', 1)
    page = page.replace(f"&middot; Updated {today}</p>", f"&middot; Updated {modified}</p>", 1)
    return page

def run(cmd):
    r = subprocess.run(cmd, cwd=ROOT, shell=True, text=True, capture_output=True)
    if r.returncode: log(f"  '{cmd}' exit {r.returncode}: {(r.stderr or r.stdout)[-400:]}")
    return r

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--commit", action="store_true", help="commit + push to origin and the live repo")
    ap.add_argument("--preview", metavar="DIR", help="render into DIR only (repo untouched)")
    ap.add_argument("--feed-file", help="read a saved JSON feed instead of fetching")
    a = ap.parse_args()
    dry = bool(a.preview)

    feed = fetch_feed(a.feed_file)
    state, held = load_json(STATE, {}), load_json(HELD, {})
    imported = []
    for item in feed.get("items", []):
        aid = str(item.get("id"))
        if (item.get("language") or "en")[:2] != "en":
            continue
        slug = slug_of(item)
        prev = state.get(aid)
        if prev and prev.get("date_modified") == item.get("date_modified") and not dry:
            continue                                            # already live, unchanged
        if prev: slug = prev["slug"]                            # keep the URL stable on updates
        out_root = a.preview if dry else ROOT
        post_dir = os.path.join(out_root, "blog", slug)
        if not prev and os.path.exists(os.path.join(ROOT, "blog", slug, "index.html")):
            log(f"SKIP {aid} /blog/{slug}/: a post this importer did not create already lives there")
            continue
        img_dir = os.path.join(out_root, "img", "blog"); os.makedirs(img_dir, exist_ok=True)
        d = to_d(item, slug, img_dir)
        date_published = (prev or {}).get("date_published") or (item.get("date_published") or "")[:10] \
            or datetime.date.today().isoformat()
        page = render(item, slug, d, date_published)
        report = gen.qc(d, page)
        hard = [f for f in report["fails"] if f in HARD_FAILS]
        if hard:
            held[aid] = {"slug": slug, "title": d["h1"], "reasons": hard, "date_modified": item.get("date_modified")}
            log(f"HOLD {aid} /blog/{slug}/: {hard} (not published; fix it in AutoSEO)")
            continue
        os.makedirs(post_dir, exist_ok=True)
        with open(os.path.join(post_dir, "index.html"), "w", encoding="utf-8") as f: f.write(page)
        held.pop(aid, None)
        state[aid] = {"slug": slug, "title": d["h1"], "date_published": date_published,
                      "date_modified": item.get("date_modified"),
                      "imported_at": datetime.datetime.now().isoformat(timespec="seconds")}
        imported.append(slug)
        log(f"{'UPDATE' if prev else 'NEW'} {aid} /blog/{slug}/ words={report['words']} faqs={report['faqs']} "
            f"internal_links={report['internal_links']} soft_fails={report['fails']}")

    if dry:
        if imported:   # --preview writes the jpg crops only; derive the webp/thumb twins the <picture> asks for
            run(f"{sys.executable} scripts/gen_blog_images.py --preview {a.preview}/img/blog {' '.join(imported)}")
            from PIL import Image
            for s in imported:
                with Image.open(os.path.join(a.preview, "img", "blog", f"{s}.jpg")) as im:
                    im.save(os.path.join(a.preview, "img", "blog", f"{s}.webp"), "WEBP", quality=80)
                    th = im.resize((600, 338))
                    th.save(os.path.join(a.preview, "img", "blog", f"{s}-thumb.jpg"), "JPEG", quality=78)
                    th.save(os.path.join(a.preview, "img", "blog", f"{s}-thumb.webp"), "WEBP", quality=78)
        log(f"preview: {len(imported)} article(s) rendered into {a.preview}")
        return
    save_json(HELD, held)
    if not imported:
        log("no new or updated AutoSEO articles")
        return
    save_json(STATE, state)
    run(f"{sys.executable} scripts/gen_blog_images.py --only {' '.join(imported)}")
    run(f"{sys.executable} scripts/blog_image_seo.py")
    run(f"{sys.executable} scripts/rebuild_indexes.py")
    run(f"{sys.executable} scripts/publish.py")
    if a.commit:
        run("git add blog/ img/blog config/autoseo_imported.json config/autoseo_held.json sitemap.xml 'sitemap-*.xml' "
            "news-sitemap.xml config/page_hashes.json config/indexnow_queue.json config/indexnow_submitted.json "
            "zh es ar")
        if run("git diff --cached --quiet").returncode:
            run(f"git commit -q -m 'autoseo: import {len(imported)} article(s)'")
            ok = run("git push -q origin main").returncode == 0 and run("git push -q c24est main").returncode == 0
            log(f"pushed (origin + live): {imported}" if ok else "push FAILED, commit is local only")
    log(f"done: {len(imported)} article(s) imported")

if __name__ == "__main__":
    main()
