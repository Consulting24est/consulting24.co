#!/usr/bin/env python3
"""
content_hash.py — template-insensitive digest of a page.

Strips site-wide chrome (header nav, footer, <script>/<style>, <link>, verification metas,
HTML comments) before hashing, so a template change (new header, new footer link, analytics
snippet) does NOT bump every page's sitemap <lastmod> and does NOT push 1,000 unchanged URLs
to IndexNow. Only a change to the page's own content changes the digest.

Bing audit 2026-09-21: the 19 Sep header rewrite gave all 1,060 URLs the same lastmod and
one more full-site IndexNow ping; Bing discounts both signals when that happens.
"""
import re, hashlib

_STRIP = [
    re.compile(r'<header\b.*?</header>', re.S),   # site header (any generation of it)
    re.compile(r'<nav\b.*?</nav>', re.S),         # main nav + breadcrumbs (derived, not content)
    re.compile(r'<footer\b.*?</footer>', re.S),
    re.compile(r'<script\b.*?</script>', re.S),
    re.compile(r'<style\b.*?</style>', re.S),
    re.compile(r'<link\b[^>]*>', re.S),
    re.compile(r'<meta name="(?:generator|yandex-verification|msvalidate\.01|google-site-verification)"[^>]*>', re.S),
    re.compile(r'<!--.*?-->', re.S),
]

def content_digest(html: str) -> str:
    body = html
    for rx in _STRIP:
        body = rx.sub("", body)
    body = re.sub(r"\s+", " ", body).strip()
    return hashlib.md5(body.encode("utf-8", "ignore")).hexdigest()

if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        print(content_digest(open(p, encoding="utf-8", errors="ignore").read()), p)
