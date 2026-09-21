#!/usr/bin/env python3
"""
redirects.py — generate static redirect stubs for GitHub Pages.

GitHub Pages can't do server-side 301s, so for each legacy URL in
config/redirects.json we write a tiny HTML file that:
  - <meta http-equiv="refresh" content="0;url=TARGET">   (instant client redirect)
  - <link rel="canonical" href="TARGET">                  (consolidates ranking to target)
  - <meta name="robots" content="noindex">                (don't index the stub itself)
  - a JS + visible fallback link

Google treats a 0-second meta-refresh with a matching canonical as a 301-equivalent,
so the old URL's signals flow to the live target instead of sitting as a 404.

Usage:
  python3 scripts/redirects.py            # generate/refresh all stubs
  python3 scripts/redirects.py --check    # list what would change, exit 1 if out of date or invalid
  python3 scripts/redirects.py --prune    # also delete stubs whose 'from' was removed from the map
  python3 scripts/redirects.py --check --prune   # CI mode: also fails on unmanaged (hand-written) stubs

Validation: a target may not be another redirect key (no chains) and must exist as a real page.

Map format (config/redirects.json):
  {"redirects": {"/old-wix-page/": "/lithuania-crypto-license/", "/blog/old/": "/blog/"}}
"""
from __future__ import annotations
import json, pathlib, sys, re

ROOT = pathlib.Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "config" / "redirects.json"
SITE = "https://www.consulting24.co"
MARKER = "<!-- generated-redirect-stub -->"

def abs_url(target: str) -> str:
    target = target.strip()
    if target.startswith(("http://", "https://")):
        return target
    if not target.startswith("/"):
        target = "/" + target
    return SITE.rstrip("/") + target

def norm_from(path: str) -> str:
    """Normalize a 'from' path to a directory-style index.html location."""
    p = path.strip()
    if p.startswith(("http://", "https://")):
        p = re.sub(r"^https?://[^/]+", "", p)
    if not p.startswith("/"):
        p = "/" + p
    # strip query/fragment
    p = p.split("?", 1)[0].split("#", 1)[0]
    return p

def out_file(from_path: str) -> pathlib.Path:
    p = norm_from(from_path).strip("/")
    if not p:
        # cannot redirect the site root via a stub (it's the homepage)
        return None
    if p.lower().endswith((".html", ".htm")):
        return ROOT / p
    return ROOT / p / "index.html"

def stub_html(target_abs: str, from_path: str) -> str:
    return (f'<!DOCTYPE html>{MARKER}\n<html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta http-equiv="refresh" content="0;url={target_abs}">'
            f'<meta name="robots" content="noindex">'
            f'<link rel="canonical" href="{target_abs}">'
            f'<title>Redirecting…</title>'
            f'<script>location.replace({json.dumps(target_abs)});</script>'
            f'</head><body style="font-family:-apple-system,Arial,sans-serif;padding:40px">'
            f'<p>This page has moved. If you are not redirected, '
            f'<a href="{target_abs}">continue here</a>.</p></body></html>\n')

def load_map() -> dict:
    data = json.loads(MAP_PATH.read_text()) if MAP_PATH.exists() else {}
    red = data.get("redirects", {}) if isinstance(data, dict) else {}
    return {k: v for k, v in red.items() if not k.startswith("_")}

def main():
    check = "--check" in sys.argv
    prune = "--prune" in sys.argv
    red = load_map()
    written = skipped = pruned = bad = 0
    managed = set()
    sources = {norm_from(k).rstrip("/") + "/" for k in red}
    for src, target in red.items():
        of = out_file(src)
        if of is None:
            print(f"SKIP (cannot stub site root): {src}"); bad += 1; continue
        # validate the target: no stub->stub chains, and the target page must exist
        tpath = re.sub(r"^https?://[^/]+", "", abs_url(target))
        if tpath.rstrip("/") + "/" in sources:
            print(f"CHAIN (target is itself a redirect key): {src} -> {target}"); bad += 1; continue
        if not target.startswith(("http://", "https://")) and tpath != "/":
            tfile = ROOT / tpath.strip("/") / "index.html"
            if tpath.lower().endswith((".html", ".htm", ".xml", ".txt", ".md")):
                tfile = ROOT / tpath.strip("/")
            if not tfile.exists():
                print(f"TARGET MISSING: {src} -> {target} ({tfile.relative_to(ROOT)})"); bad += 1; continue
        # never clobber a real (non-stub) page
        if of.exists() and MARKER not in of.read_text():
            print(f"SKIP (real page exists, not overwriting): {of.relative_to(ROOT)}"); bad += 1; continue
        managed.add(of.resolve())
        html = stub_html(abs_url(target), norm_from(src))
        if of.exists() and of.read_text() == html:
            skipped += 1; continue
        if check:
            print(f"WOULD WRITE: {of.relative_to(ROOT)} -> {abs_url(target)}"); written += 1; continue
        of.parent.mkdir(parents=True, exist_ok=True)
        of.write_text(html); written += 1
        print(f"redirect: {norm_from(src)} -> {abs_url(target)}")
    if prune:
        for f in ROOT.glob("**/index.html"):
            try:
                if MARKER in f.read_text() and f.resolve() not in managed:
                    if not check:
                        f.unlink()
                    pruned += 1
                    print(f"prune stale stub: {f.relative_to(ROOT)}")
            except Exception:
                pass
    print(f"redirects: {written} written, {skipped} unchanged, {pruned} pruned, {bad} skipped "
          f"({len(red)} in map)")
    if check and (written or pruned or bad):
        sys.exit(1)

if __name__ == "__main__":
    main()
