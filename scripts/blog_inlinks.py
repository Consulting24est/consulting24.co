#!/usr/bin/env python3
"""
blog_inlinks.py — guarantee every /blog/ post has at least 5 internal inlinks.

Bing audit 2026-09-21: 268 of 333 www blog posts had <= 2 inlinks (median 1), so Bing
ranked the Blogger mirror copies instead. Two idempotent, marker-wrapped blocks fix that:

1. HUB BLOCK  (<!-- BLOG_GUIDES_START/END -->) on every jurisdiction hub
   (/<jurisdiction>-crypto-license/, or /crypto-exchange-license-<jurisdiction>/ when there
   is no hub): "<Jurisdiction> guides & checklists" listing every /blog/ post about it.
2. SIBLING RING (<!-- BLOG_SIBLINGS_START/END -->) in every post: posts are sorted by
   (jurisdiction, slug) and post i links to the next 5 posts, so every post receives exactly
   5 sibling inlinks (mostly same-jurisdiction) on top of the hub link.

Run from publish.py before the sitemap build. Safe to re-run: blocks are regenerated.
  python3 scripts/blog_inlinks.py            # write
  python3 scripts/blog_inlinks.py --check    # report what would change, exit 1 if anything
"""
from __future__ import annotations
import os, re, sys, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLOG = os.path.join(ROOT, "blog")
RING = 5
HUB_START, HUB_END = "<!-- BLOG_GUIDES_START -->", "<!-- BLOG_GUIDES_END -->"
SIB_START, SIB_END = "<!-- BLOG_SIBLINGS_START -->", "<!-- BLOG_SIBLINGS_END -->"
NOT_JURISDICTIONS = {"how-to-get-a", "ready-made", "best-country-for", "cheapest", "fastest", "easiest"}
STUB = "generated-redirect-stub"


def read(p):
    with open(p, encoding="utf-8", errors="ignore") as f:
        return f.read()


def write(p, s):
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)


def is_page(d):
    p = os.path.join(d, "index.html")
    return os.path.isfile(p) and STUB not in read(p)[:600]


def title_of(p):
    m = re.search(r"<title>(.*?)</title>", read(p), re.S)
    t = html.unescape(m.group(1).strip()) if m else os.path.basename(os.path.dirname(p))
    return re.sub(r"\s*\|\s*Consulting24\s*$", "", t)


def pretty(j):
    special = {"bvi": "BVI", "uae": "UAE", "usa": "USA", "el-salvador": "El Salvador",
               "isle-of-man": "Isle of Man", "hong-kong": "Hong Kong"}
    return special.get(j, " ".join(w.capitalize() for w in j.split("-")))


def jurisdictions():
    """jurisdiction token -> hub dir (relative), longest tokens first for matching."""
    out = {}
    for d in os.listdir(ROOT):
        if not os.path.isdir(os.path.join(ROOT, d)):
            continue
        m = re.fullmatch(r"([a-z-]+)-crypto-license", d)
        if m and "-vs-" not in d and m.group(1) not in NOT_JURISDICTIONS \
                and not d.startswith(("cost-", "offshore-")) and is_page(os.path.join(ROOT, d)):
            out[m.group(1)] = d
    for d in os.listdir(ROOT):
        m = re.fullmatch(r"crypto-exchange-license-([a-z-]+)", d)
        if m and m.group(1) not in out and is_page(os.path.join(ROOT, d)):
            out[m.group(1)] = d
    return out


def jurisdiction_of(slug, jurs):
    toks = slug.split("-")
    best = None
    for j in jurs:
        jt = j.split("-")
        n = len(jt)
        if any(toks[i:i + n] == jt for i in range(len(toks) - n + 1)):
            if best is None or len(j) > len(best):
                best = j
    return best


def replace_block(page, start, end, block, insert_before):
    """Replace an existing marked block, or insert it before the first of insert_before."""
    if start in page and end in page:
        a, b = page.index(start), page.index(end) + len(end)
        return page[:a] + (block or "") + page[b:]
    if not block:
        return page
    for needle in insert_before:
        i = page.find(needle)
        if i != -1:
            return page[:i] + block + page[i:]
    return page


def main():
    check = "--check" in sys.argv
    jurs = jurisdictions()
    posts = sorted(d for d in os.listdir(BLOG) if is_page(os.path.join(BLOG, d)))
    meta = {s: {"title": title_of(os.path.join(BLOG, s, "index.html")),
                "jur": jurisdiction_of(s, jurs)} for s in posts}
    order = sorted(posts, key=lambda s: (meta[s]["jur"] or "zzz-general", s))
    changed = 0

    # 1. hub blocks
    by_jur = {}
    for s in posts:
        if meta[s]["jur"]:
            by_jur.setdefault(meta[s]["jur"], []).append(s)
    for j, hub in jurs.items():
        p = os.path.join(ROOT, hub, "index.html")
        page = read(p)
        items = sorted(by_jur.get(j, []), key=lambda s: meta[s]["title"])
        block = ""
        if items:
            links = "".join(
                f'<a href="/blog/{s}/" style="display:inline-block;margin:0 10px 8px 0">{html.escape(meta[s]["title"])}</a>'
                for s in items)
            block = (f'{HUB_START}<section class="wrap landing-link-hub" style="margin:8px auto 0">'
                     f'<h2 style="font-size:1.3rem">{html.escape(pretty(j))} guides &amp; checklists</h2>'
                     f'<p style="color:var(--ink-2)">Step-by-step guides, cost breakdowns and compliance checklists for {html.escape(pretty(j))}:</p>'
                     f'<div style="line-height:1.9;font-size:14px">{links}</div></section>{HUB_END}')
        new = replace_block(page, HUB_START, HUB_END, block,
                            ['<section class="primary-sources"', "<footer"])
        if new != page:
            changed += 1
            print(f"hub {hub}: {len(items)} guides")
            if not check:
                write(p, new)

    # 2. sibling ring
    n = len(order)
    for i, s in enumerate(order):
        p = os.path.join(BLOG, s, "index.html")
        page = read(p)
        sibs = [order[(i + k) % n] for k in range(1, RING + 1) if order[(i + k) % n] != s]
        links = "".join(
            f'<a href="/blog/{t}/"><strong>{html.escape(meta[t]["title"])}</strong></a>' for t in sibs)
        j = meta[s]["jur"]
        heading = f"More {html.escape(pretty(j))} guides" if j else "More crypto licensing guides"
        block = f'{SIB_START}<h2>{heading}</h2><div class="related">{links}</div>{SIB_END}'
        # insert right after the existing "Related guides" card row, else before the footer
        anchor = re.search(r'<h2>Related guides</h2><div class="related">.*?</div>', page, re.S)
        if SIB_START in page and SIB_END in page:
            new = replace_block(page, SIB_START, SIB_END, block, [])
        elif anchor:
            new = page[:anchor.end()] + block + page[anchor.end():]
        else:
            new = replace_block(page, SIB_START, SIB_END, block, ["<footer"])
        if new != page:
            changed += 1
            if not check:
                write(p, new)

    print(f"blog_inlinks: {len(posts)} posts, {len(jurs)} jurisdictions, "
          f"{sum(1 for s in posts if meta[s]['jur'])} posts mapped to a hub, "
          f"{changed} files {'would change' if check else 'updated'}")
    if check and changed:
        sys.exit(1)


if __name__ == "__main__":
    main()
