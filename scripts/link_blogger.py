#!/usr/bin/env python3
"""Link every published Blogger post & page from the consulting24.co website.

The Blogger feeder blog (blog.consulting24.co) links TO the consulting24.co money
pages; this script does the reverse — it keeps a complete, auto-generated list of
ALL Blogger guides on the site's /blog/ hub so every blog URL is linked from the
main site. Run daily after the Blogger poster.

- Source of truth: config/blog_posted.json  (posts + pages, written by consulting24_blog.py)
- Target: blog/index.html, between <!-- BLOGGER_GUIDES_START --> and <!-- BLOGGER_GUIDES_END -->
- Idempotent: regenerates the full block each run (so newly published items get linked).

Usage:
  python3 scripts/link_blogger.py            # update the block
  python3 scripts/link_blogger.py --check    # exit 1 if the block is out of date (no write)
"""
from __future__ import annotations
import json, pathlib, sys, html, re

ROOT   = pathlib.Path(__file__).resolve().parents[1]
STATE  = ROOT / "config" / "blog_posted.json"
TARGET = ROOT / "blog" / "index.html"
START  = "<!-- BLOGGER_GUIDES_START -->"
END    = "<!-- BLOGGER_GUIDES_END -->"

MARKER = "<!-- generated-redirect-stub -->"

def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", html.unescape(t).lower()).strip()

def www_titles(htmltext: str) -> set[str]:
    """Titles of the site's own /blog/ cards (outside the Blogger block)."""
    s, e = htmltext.find(START), htmltext.find(END)
    outside = htmltext if s < 0 or e < 0 else htmltext[:s] + htmltext[e:]
    return {_norm_title(t) for t in re.findall(r'<a class="post-card"[^>]*>.*?<h2>(.*?)</h2>', outside, re.S)}

def load_items(htmltext: str = "") -> list[dict]:
    """One card per topic: a Blogger guide is listed only when the site has no
    article of its own on that topic (same slug under /blog/, or same title)."""
    data = json.loads(STATE.read_text()) if STATE.exists() else {}
    seen_titles = www_titles(htmltext) if htmltext else set()
    items, skipped = [], 0
    for kind in ("pages", "posts"):                 # pillar pages first, then posts
        for slug, m in data.get(kind, {}).items():
            if not (m.get("url") and m.get("title")):
                continue
            twin = ROOT / "blog" / slug / "index.html"
            if kind == "posts" and twin.is_file() and MARKER not in twin.read_text()[:400]:
                skipped += 1; continue                # the site has its own article
            nt = _norm_title(m["title"])
            if nt in seen_titles:
                skipped += 1; continue                # same title already listed
            seen_titles.add(nt)
            url = m["url"].replace("https://consultinglegalnews.blogspot.com/", "https://blog.consulting24.co/")
            items.append({"title": m["title"], "url": url,
                          "kind": "Pillar guide" if kind == "pages" else "Guide"})
    if skipped:
        print(f"link_blogger: {skipped} Blogger items not listed (site already covers the topic).")
    return items

def render_block(items: list[dict]) -> str:
    if not items:
        cards = "<p>Guides coming soon.</p>"
    else:
        def _thumb(title: str) -> int:
            return (sum(ord(c) for c in title) % 9) + 1
        cards = "".join(
            f'<a class="post-card" href="{html.escape(i["url"])}" '
            f'rel="noopener">'
            f'<picture><source srcset="/img/gallery-{_thumb(i["title"]):02d}.webp" type="image/webp">'
            f'<img class="thumb" src="/img/gallery-{_thumb(i["title"]):02d}.jpg" '
            f'alt="{html.escape(i["title"])}" loading="lazy" width="600" height="360"></picture>'
            f'<span class="pc-body"><span class="cat">{i["kind"]}</span>'
            f'<h2>{html.escape(i["title"])}</h2>'
            f'<span class="meta">Consulting24 blog</span></span></a>'
            for i in items
        )
        cards = f'<div class="blog-grid">{cards}</div>'
    return f"{START}\n  {cards}\n  {END}"

def main():
    check = "--check" in sys.argv
    htmltext = TARGET.read_text()
    items = load_items(htmltext)
    if START not in htmltext or END not in htmltext:
        sys.exit(f"ERROR: markers not found in {TARGET}")
    new_block = render_block(items)
    updated = re.sub(re.escape(START) + r".*?" + re.escape(END), new_block,
                     htmltext, flags=re.S)
    if updated == htmltext:
        print(f"link_blogger: up to date ({len(items)} guides linked).")
        return
    if check:
        print(f"link_blogger: OUT OF DATE — {len(items)} guides should be linked.")
        sys.exit(1)
    TARGET.write_text(updated)
    print(f"link_blogger: linked {len(items)} Blogger guides into {TARGET.relative_to(ROOT)}.")

if __name__ == "__main__":
    main()
