#!/usr/bin/env python3
"""
backfill_seo.py — retrofit SEO/LLM upgrades onto all existing pages WITHOUT
regenerating content (no DeepSeek cost). For every landing + blog page:
  1. inject Article JSON-LD (author Mardo Soo, datePublished from git, dateModified today)
  2. add a TL;DR "Short answer" box (from the meta description) after the <h1>
  3. add a visible author byline (E-E-A-T) after the <h1>
  4. (landing pages) replace the bloated 77-link hub with a lean ~20-link contextual block

Idempotent: skips pages already carrying the answer-box marker.
Usage: python3 scripts/backfill_seo.py [--limit N]
"""
from __future__ import annotations
import os, re, sys, json, html, subprocess, datetime, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = "https://www.consulting24.co"
TODAY = datetime.date.today().isoformat()
SKIP = {"blog","scripts","config","img","logs","jurisdictions"}

sys.path.insert(0, str(ROOT / "scripts"))
from htmltext import plain, esc_text
import importlib.util
_spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts" / "generate.py")
gen = importlib.util.module_from_spec(_spec)
try: _spec.loader.exec_module(gen)
except SystemExit: pass

def git_add_date(path: pathlib.Path) -> str:
    try:
        out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%aI", "-1", "--", str(path)],
                             cwd=ROOT, capture_output=True, text=True, timeout=20).stdout.strip()
        if out: return out[:10]
    except Exception: pass
    return TODAY

def first(rx, s, d=""):
    m = re.search(rx, s, re.S | re.I)
    return m.group(1).strip() if m else d

def backfill(path: pathlib.Path, slug: str, kind: str) -> bool:
    h = path.read_text(encoding="utf-8")
    if "answer-box" in h or "generated-redirect-stub" in h:
        return False
    # Both are read back out of rendered HTML, so they arrive already escaped.
    # Keep them plain here and escape once per destination below.
    title = plain(first(r"<title>(.*?)</title>", h))
    desc = plain(first(r'<meta name="description" content="(.*?)"', h))
    canon = first(r'<link rel="canonical" href="(.*?)"', h) or f"{BASE}/{slug}/"
    pub = git_add_date(path)

    # 1) Article JSON-LD (separate block is valid alongside existing @graph)
    art = ('<script type="application/ld+json">' + json.dumps({
        "@context":"https://schema.org","@type":"Article","headline":title,
        "description":desc,"datePublished":pub,"dateModified":TODAY,
        "image":(f"{BASE}/img/blog/{slug}.jpg" if kind == "blog" and (ROOT / "img" / "blog" / f"{slug}.jpg").exists()
                 else f"{BASE}/og-image.jpg"),"mainEntityOfPage":canon,
        "author":{"@type":"Person","name":"Mardo Soo","jobTitle":"Founder & CEO",
                  "url":"https://www.linkedin.com/in/mardo-s-00a05ab0/",
                  "image":f"{BASE}/img/mardo-soo-profile.jpg",
                  "worksFor":{"@type":"Organization","name":"Consulting24","url":"https://consulting24.co/"}},
        "publisher":{"@type":"Organization","name":"Consulting24","url":"https://consulting24.co/",
                     "logo":{"@type":"ImageObject","url":f"{BASE}/img/mardo-soo-profile.jpg"}}},
        ensure_ascii=False) + "</script>")
    if "</head>" in h:
        h = h.replace("</head>", art + "\n</head>", 1)

    # 2+3) TL;DR + byline after the first <h1>...</h1>
    byline = (f'<p class="byline" style="color:var(--muted);font-size:.9rem;margin:0 0 18px">'
              f'By <a href="https://www.linkedin.com/in/mardo-s-00a05ab0/" rel="author">Mardo Soo</a>, '
              f'Founder &amp; CEO, Consulting24 (X24Consulting O&Uuml;) &middot; Updated {TODAY}</p>')
    ans = esc_text(desc)   # desc is plain; escape exactly once for the text node
    tldr = (f'<div class="answer-box" style="background:var(--accent-soft);border-left:4px solid var(--accent);'
            f'border-radius:8px;padding:16px 20px;margin:0 0 22px"><strong style="color:var(--accent-dark)">'
            f'Short answer:</strong> {ans}</div>') if ans else '<div class="answer-box"></div>'
    h = re.sub(r"(</h1>)", r"\1\n" + byline + "\n" + tldr, h, count=1)

    # 4) landing pages: replace the bloated link hub with a lean ~20-link block
    if kind == "landing":
        lean = gen.link_hub(slug)
        h = re.sub(r'<section class="wrap landing-link-hub".*?</section>', lean, h, count=1, flags=re.S)

    path.write_text(h, encoding="utf-8")
    return True

def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit")+1])
    targets = []
    for d in sorted(os.listdir(ROOT)):
        if d in SKIP: continue
        p = ROOT / d / "index.html"
        if p.exists(): targets.append((p, d, "landing"))
    for p in sorted((ROOT / "blog").glob("*/index.html")):
        targets.append((p, p.parent.name, "blog"))
    done = skipped = 0
    for p, slug, kind in targets:
        if limit and done >= limit: break
        try:
            if backfill(p, slug, kind): done += 1
            else: skipped += 1
        except Exception as e:
            print(f"ERR {slug}: {e}")
    print(f"backfill: {done} updated, {skipped} already current ({len(targets)} pages)")

if __name__ == "__main__":
    main()
