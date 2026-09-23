#!/usr/bin/env python3
"""
blog_image_seo.py — wire every /blog/ post to its UNIQUE hero image set (img/blog/<slug>*).

Run AFTER scripts/gen_blog_images.py. For each live post (redirect stubs / noindex skipped) it makes
the page's image markup match what Google, Bing, social cards and LLM crawlers look for:

  1. <meta property="og:image"> -> /img/blog/<slug>.jpg (1200x675) + og:image:width/height/type/alt,
     <meta name="twitter:image"> + twitter:image:alt        (was: one shared /og-image.jpg on 332 posts)
  2. Article JSON-LD "image": three ImageObjects (16:9, 4:3, 1:1 — the ratios Google's Article guidelines
     ask for) with width/height/caption, plus "thumbnailUrl"
  3. a visible hero <figure class="blog-hero"> straight after the answer box:
     <picture> WebP + JPEG, responsive srcset (600w thumb / 1200w master), explicit width/height (no CLS),
     fetchpriority="high" (it is the LCP element), a descriptive alt and a <figcaption> with the key facts
  4. blog/index.html gets its own og:image / twitter:image (img/blog/blog-index.jpg)

Idempotent (re-running changes nothing). `--check` reports and exits 1 if anything would change.
"""
from __future__ import annotations
import datetime, html, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from gen_blog_images import post_meta, outputs_for, SIZES, SITE   # noqa: E402

BLOG = ROOT / "blog"
IMG_W, IMG_H = SIZES["16x9"]
SIZES_ATTR = "(max-width: 760px) 100vw, 1100px"

RX_OG_IMAGE = re.compile(r'<meta property="og:image" content="[^"]*">')
RX_OG_EXTRA = re.compile(r'\s*<meta property="og:image:(?:width|height|type|alt|secure_url)" content="[^"]*">')
RX_TW_IMAGE = re.compile(r'<meta name="twitter:image" content="[^"]*">')
RX_TW_ALT = re.compile(r'\s*<meta name="twitter:image:alt" content="[^"]*">')
RX_LD = re.compile(r'(<script type="application/ld\+json">)(.*?)(</script>)', re.S)
RX_OLD_HERO = re.compile(r'\s*<figure class="blog-hero(?:-photo)?"[^>]*>.*?</figure>', re.S)
RX_ANSWER = re.compile(r'<div class="answer-box"[^>]*>.*?</div>', re.S)


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def h1_of(h: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", h, re.S)
    return html.unescape(re.sub("<[^>]+>", "", m.group(1))).strip() if m else ""


def image_urls(slug: str) -> dict:
    o = outputs_for(slug)
    rel = lambda p: "/" + p.relative_to(ROOT).as_posix()          # noqa: E731
    return {k: rel(p) for k, p in o.items()}


def image_objects(slug: str, caption: str, title: str = "") -> list[dict]:
    """Three ImageObjects (16:9, 4:3, 1:1). Beyond url/width/height the fields Google Images and AI search use for
    attribution are filled: name, description/caption, creator (the site's Organization @id), creditText,
    copyrightNotice and representativeOfPage on the master."""
    u = image_urls(slug)
    objs = []
    for key, (w, h) in SIZES.items():
        objs.append({"@type": "ImageObject", "url": SITE + u[key], "contentUrl": SITE + u[key], "width": w, "height": h,
                     "name": title or caption, "caption": caption, "description": caption,
                     "representativeOfPage": key == "16x9",
                     "creator": {"@id": f"{SITE}/#business"}, "creditText": "Consulting24",
                     "copyrightNotice": "Consulting24, 2026"})
    return objs


def set_social_meta(h: str, img_url: str, alt: str) -> str:
    """Point og:image / twitter:image at img_url and add the dimension + alt companions (idempotent)."""
    h = RX_OG_EXTRA.sub("", h)
    h = RX_TW_ALT.sub("", h)
    og = (f'<meta property="og:image" content="{SITE}{img_url}">'
          f'<meta property="og:image:width" content="{IMG_W}"><meta property="og:image:height" content="{IMG_H}">'
          f'<meta property="og:image:type" content="image/jpeg"><meta property="og:image:alt" content="{esc(alt)}">')
    tw = f'<meta name="twitter:image" content="{SITE}{img_url}"><meta name="twitter:image:alt" content="{esc(alt)}">'
    h, n1 = RX_OG_IMAGE.subn(og, h, count=1)
    h, n2 = RX_TW_IMAGE.subn(tw, h, count=1)
    if not n1:                                                    # no og:image at all: add after og:type or in <head>
        h = h.replace("</head>", og + "\n</head>", 1)
    if not n2:
        h = h.replace("</head>", tw + "\n</head>", 1)
    return h


def _is_article(node) -> bool:
    t = node.get("@type") if isinstance(node, dict) else None
    return t == "Article" or (isinstance(t, list) and "Article" in t) or t in ("BlogPosting", "NewsArticle")


def set_article_images(h: str, slug: str, caption: str, thumb_url: str, title: str = "") -> str:
    imgs = image_objects(slug, caption, title)

    def patch(obj) -> bool:
        changed = False
        if isinstance(obj, dict):
            if _is_article(obj):
                if obj.get("image") != imgs:
                    obj["image"] = imgs; changed = True
                if obj.get("thumbnailUrl") != SITE + thumb_url:
                    obj["thumbnailUrl"] = SITE + thumb_url; changed = True
            for v in obj.values():
                changed = patch(v) or changed
        elif isinstance(obj, list):
            for v in obj:
                changed = patch(v) or changed
        return changed

    def repl(m: re.Match) -> str:
        raw = m.group(2)
        try:
            data = json.loads(raw)
        except Exception:
            return m.group(0)
        if not patch(data):
            return m.group(0)
        return m.group(1) + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + m.group(3)

    return RX_LD.sub(repl, h)


def hero_figure(slug: str, alt: str, caption: str) -> str:
    u = image_urls(slug)
    return (
        '<figure class="blog-hero" style="margin:18px 0 26px">'
        f'<picture><source type="image/webp" srcset="{u["thumbwebp"]} 600w, {u["webp"]} 1200w" sizes="{SIZES_ATTR}">'
        f'<img src="{u["16x9"]}" srcset="{u["thumb"]} 600w, {u["16x9"]} 1200w" sizes="{SIZES_ATTR}" '
        f'alt="{esc(alt)}" width="{IMG_W}" height="{IMG_H}" fetchpriority="high" decoding="async" '
        'style="width:100%;height:auto;border-radius:14px;display:block"></picture>'
        f'<figcaption style="font-size:.85rem;color:var(--muted);margin-top:8px">{html.escape(caption, quote=False)}</figcaption>'
        '</figure>'
    )


def set_hero(h: str, fig: str) -> str:
    h = RX_OLD_HERO.sub("", h)
    m = RX_ANSWER.search(h)
    if m:
        return h[:m.end()] + "\n" + fig + h[m.end():]
    m = re.search(r'<p class="byline"[^>]*>.*?</p>', h, re.S) or re.search(r"<h1[^>]*>.*?</h1>", h, re.S)
    if m:
        return h[:m.end()] + "\n" + fig + h[m.end():]
    return h


def process_post(path: pathlib.Path) -> tuple[str, str | None]:
    """Returns (status, new_html_or_None): status in {'stub','no-image','same','changed'}."""
    h = path.read_text(encoding="utf-8")
    head = h[:1500]
    if "generated-redirect-stub" in head or 'content="noindex"' in head:
        return "stub", None
    slug = path.parent.name
    if not all(p.exists() for p in outputs_for(slug).values()):
        return "no-image", None
    title = h1_of(h) or slug.replace("-", " ").capitalize()
    meta = post_meta(slug, title)
    u = image_urls(slug)
    new = set_social_meta(h, u["16x9"], meta["alt"])
    new = set_article_images(new, slug, meta["caption"], u["thumb"], title)
    new = set_hero(new, hero_figure(slug, meta["alt"], meta["caption"]))
    if new != h:
        new = bump_dates(new)      # a new hero + schema is a real modification: keep dateModified, the visible
    return ("changed" if new != h else "same"), (new if new != h else None)   # byline and sitemap lastmod in step


TODAY = datetime.date.today().isoformat()
RX_DATE_MOD = re.compile(r'("dateModified"\s*:\s*")\d{4}-\d{2}-\d{2}')
RX_BYLINE = re.compile(r'(&middot; Updated )\d{4}-\d{2}-\d{2}')


def bump_dates(h: str) -> str:
    h = RX_DATE_MOD.sub(lambda m: m.group(1) + TODAY, h)
    return RX_BYLINE.sub(lambda m: m.group(1) + TODAY, h, count=1)


def process_index() -> tuple[str, str | None]:
    path = BLOG / "index.html"
    h = path.read_text(encoding="utf-8")
    if not all(p.exists() for p in outputs_for("blog-index").values()):
        return "no-image", None
    meta = post_meta("blog-index", "Crypto Licensing Blog")
    alt = "Consulting24 crypto licensing blog cover: guides on costs, requirements, tax, banking and compliance"
    new = set_social_meta(h, image_urls("blog-index")["16x9"], alt)
    return ("changed" if new != h else "same"), (new if new != h else None)


def main():
    check = "--check" in sys.argv
    counts = {"stub": 0, "no-image": 0, "same": 0, "changed": 0}
    missing = []
    targets = sorted(BLOG.glob("*/index.html"))
    for p in targets:
        status, new = process_post(p)
        counts[status] += 1
        if status == "no-image":
            missing.append(p.parent.name)
        if new is not None and not check:
            p.write_text(new, encoding="utf-8")
    status, new = process_index()
    counts[status] += 1
    if new is not None and not check:
        (BLOG / "index.html").write_text(new, encoding="utf-8")
    print(f"blog_image_seo: {counts['changed']} changed, {counts['same']} already current, "
          f"{counts['stub']} stubs skipped, {counts['no-image']} without a full image set"
          + (f" (run gen_blog_images.py): {', '.join(missing[:8])}{' …' if len(missing) > 8 else ''}" if missing else ""))
    if counts["no-image"]:
        sys.exit(2)            # a live post without its image set is a pipeline failure, not a warning
    if check and counts["changed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
