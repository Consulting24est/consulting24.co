#!/usr/bin/env python3
"""
fix_double_escape.py — repair double-escaped HTML entities across the site.

Background: several generators read text back out of already-escaped HTML
(<h1>, <meta name="description">) and escaped it a second time, so the browser
renders the entity itself: "Panama&#x27;s" instead of "Panama's", and
"Costs &amp; Process" instead of "Costs & Process".

This collapses "&amp;<entity>;" back to "&<entity>;", repeatedly, so triple and
deeper escapes are handled too. It is idempotent: a correctly escaped page has
no "&amp;" immediately followed by an entity reference, so a second run is a
no-op.

Safety: only visible text nodes and text-bearing attributes (meta content, alt,
title, aria-label) are touched. URLs in href/src are left alone, because
"?a=1&amp;b=2" is correct there. <style>, comments and ordinary <script> are skipped.
JSON-LD blocks get their own pass: entities inside JSON string values are decoded to
plain characters, because nothing ever decodes them there.

Usage:
  python3 scripts/fix_double_escape.py            # fix in place
  python3 scripts/fix_double_escape.py --check    # report only, exit 1 if dirty
  python3 scripts/fix_double_escape.py --verbose  # list every file changed
"""
from __future__ import annotations
import os, re, sys, pathlib
from html.entities import html5

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "node_modules", "scripts", "__pycache__", ".claude", "logs"}

# Segments we must never rewrite, kept whole by the splitter below.
OPAQUE = re.compile(r"(<script\b[^>]*>.*?</script\s*>|<style\b[^>]*>.*?</style\s*>|<!--.*?-->)",
                    re.S | re.I)
# Any remaining tag, so tag internals are handled separately from text nodes.
TAG = re.compile(r"(<[^>]*>)", re.S)

# "&amp;" followed by a further entity reference == one layer of over-escaping.
DOUBLE = re.compile(r"&amp;(#[0-9]{1,7};|#[xX][0-9a-fA-F]{1,6};|[a-zA-Z][a-zA-Z0-9]{1,31};)")

# Attributes that carry human-readable text rather than a URL or a token.
TEXT_ATTR = re.compile(r'\b(content|alt|title|aria-label|placeholder)\s*=\s*"([^"]*)"', re.I)
URLISH_TAG = re.compile(r"^<\s*(a|link|base|form)\b", re.I)


def _valid(ref: str) -> bool:
    """True when '&<ref>' names a real character reference."""
    if ref.startswith("#"):
        return True
    return ref in html5


def _collapse(s: str) -> tuple[str, int]:
    """Strip every extra escaping layer from a fragment. Returns (text, n_fixed)."""
    fixed = 0
    while True:
        hits = 0

        def sub(m):
            nonlocal hits
            if not _valid(m.group(1)):
                return m.group(0)      # "&amp;notanentity;" is literal text, leave it
            hits += 1
            return "&" + m.group(1)

        out = DOUBLE.sub(sub, s)
        if not hits:                   # count real replacements, never bare matches,
            return s, fixed            # so an unfixable match cannot spin forever
        s, fixed = out, fixed + hits


def _fix_tag(tag: str) -> tuple[str, int]:
    """Repair text-bearing attributes inside one tag, leaving URLs untouched."""
    # <a href="...?x=1&amp;y=2"> and friends: never rewrite link targets.
    if URLISH_TAG.match(tag) and not TEXT_ATTR.search(tag):
        return tag, 0
    total = 0

    def sub(m):
        nonlocal total
        val, n = _collapse(m.group(2))
        total += n
        return f'{m.group(1)}="{val}"'

    return TEXT_ATTR.sub(sub, tag), total


LDJSON = re.compile(r'(<script type="application/ld\+json">)(.*?)(</script\s*>)', re.S | re.I)
ENTITY = re.compile(r"&(#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[a-zA-Z][a-zA-Z0-9]{1,31});")


def _fix_ldjson(block: str) -> tuple[str, int]:
    """JSON-LD is raw text: browsers and crawlers never decode entities inside it, so any
    '&amp;' or '&#x27;' in a string value is shown literally ('Cost &amp; Setup'). Decode
    every string value to plain characters and re-serialise only when something changed."""
    import json
    sys.path.insert(0, str(ROOT / "scripts"))
    from htmltext import plain
    try:
        data = json.loads(block)
    except Exception:
        return block, 0                # never touch a block we cannot parse
    hits = 0

    def walk(o):
        nonlocal hits
        if isinstance(o, str):
            if ENTITY.search(o):
                p = plain(o)
                if p != o:
                    hits += 1
                    return p
            return o
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        if isinstance(o, list):
            return [walk(v) for v in o]
        return o

    data = walk(data)
    if not hits:
        return block, 0
    out = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return out.replace("</", "<\\/"), hits    # a decoded '</script>' must not end the block


def fix_html(h: str) -> tuple[str, int]:
    """Repair one document. Returns (new_html, occurrences_fixed)."""
    total = 0
    out = []
    for chunk in OPAQUE.split(h):
        if OPAQUE.fullmatch(chunk or ""):
            m = LDJSON.fullmatch(chunk or "")
            if m:                      # structured data: decode entities in string values
                body, n = _fix_ldjson(m.group(2))
                total += n
                chunk = m.group(1) + body + m.group(3) if n else chunk
            out.append(chunk)          # script / style / comment otherwise verbatim
            continue
        for part in TAG.split(chunk or ""):
            if part.startswith("<") and part.endswith(">"):
                part, n = _fix_tag(part)
            else:
                part, n = _collapse(part)
            total += n
            out.append(part)
    return "".join(out), total


def targets() -> list[pathlib.Path]:
    found = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        if "index.html" in filenames:
            found.append(pathlib.Path(dirpath) / "index.html")
    return sorted(found)


def main() -> int:
    check = "--check" in sys.argv
    verbose = "--verbose" in sys.argv
    files = targets()
    changed, occurrences = [], 0
    for p in files:
        h = p.read_text(encoding="utf-8")
        new, n = fix_html(h)
        if n:
            changed.append((p, n))
            occurrences += n
            if not check:
                p.write_text(new, encoding="utf-8")
    if verbose:
        for p, n in changed:
            print(f"  {n:4d}  {p.relative_to(ROOT)}")
    verb = "would fix" if check else "fixed"
    print(f"double-escape: {verb} {occurrences} entities in {len(changed)} of {len(files)} pages")
    return 1 if (check and changed) else 0


if __name__ == "__main__":
    sys.exit(main())
