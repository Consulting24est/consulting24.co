#!/usr/bin/env python3
"""
rebuild_indexes.py — regenerate the /jurisdictions/ hub grid and /blog/ card list
from whatever pages exist on disk, so new pages are always linked (no orphans).
Run in the daily pipeline after generating pages, before linkcheck/publish.
"""
import os, re, sys, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from htmltext import plain, esc_text, esc_attr

def title_of(path, fallback):
    """Heading text as plain characters. The <h1> on disk is escaped, so decode
    it here and let each caller escape once for its own context. Escaping the
    escaped text again is what rendered 'Costs &amp; Process' on the hub."""
    h = open(path, encoding="utf-8").read()
    m = re.search(r"<h1>(.*?)</h1>", h, re.S)
    t = re.sub("<[^>]+>", "", m.group(1)).strip() if m else fallback
    return plain(t)

def splice(file, start, end, block):
    s = open(file, encoding="utf-8").read()
    new = re.sub(re.escape(start) + r".*?" + re.escape(end), start + "\n" + block + "\n" + end, s, flags=re.S)
    open(file, "w", encoding="utf-8").write(new)

# --- Jurisdictions hub: link EVERY indexable landing page, grouped, so no page is
#     an orphan. Runs on every publish, so new pages are auto-wired in. ---
SYSTEM = {"blog","scripts","config","img","logs","jurisdictions","node_modules",
          "about","contact","privacy","terms","cookies","post",
          "zh","es","ar"}            # translated copies of the site (own hreflang set), not landing pages
ACT = ("exchange","broker","fund","gambling","nft-marketplace","otc-desk","payment-institution",
       "stablecoin","staking","token-issuance","wallet-custody","dealer","custody","mining","p2p")

esc = esc_text   # text-node escaping; title_of() already handed us plain text

def classify(slug):
    if "-vs-" in slug: return "compare"
    if slug.startswith(("best-country","cost-crypto","offshore-crypto","fastest-crypto",
                        "cheapest-crypto","easiest-crypto","ready-made-crypto","how-to-")):
        return "guide"
    if slug.startswith("crypto-") and any(f"crypto-{a}-license" in slug for a in ACT):
        return "activity"
    if slug.endswith("-crypto-license"): return "jurisdiction"
    return "guide"

groups = {"jurisdiction": [], "activity": [], "compare": [], "guide": []}
for d in sorted(glob.glob(os.path.join(ROOT, "*"))):
    if not os.path.isdir(d): continue
    slug = os.path.basename(d)
    idx = os.path.join(d, "index.html")
    if slug in SYSTEM or slug.startswith(".") or not os.path.exists(idx): continue
    h = open(idx, encoding="utf-8").read()
    if 'generated-redirect-stub' in h or 'content="noindex"' in h: continue   # skip stubs
    label = title_of(idx, slug.replace("-", " ").title())
    groups[classify(slug)].append((label, slug))

SUB = {"jurisdiction":"Requirements, cost &amp; timeline", "activity":"Licence type &amp; process",
       "compare":"Side-by-side comparison", "guide":"Guide"}
HEAD = {"jurisdiction":"Crypto license by country", "activity":"By licence type &amp; activity",
        "compare":"Compare jurisdictions", "guide":"Guides &amp; tools"}
sections = ['  <div class="jx-grid">\n    <a class="jx-card" href="/"><strong>Panama 🇵🇦</strong>'
            '<span>€6,000 fixed · 2-3 weeks · 0% foreign-income tax</span></a>\n  </div>']
total = 1
for key in ("jurisdiction", "activity", "compare", "guide"):
    items = groups[key]
    if not items: continue
    total += len(items)
    cards = "\n".join(
        f'    <a class="jx-card" href="/{slug}/"><strong>{esc(label)}</strong><span>{SUB[key]}</span></a>'
        for label, slug in items)
    sections.append(f'  <h2 class="jx-group">{HEAD[key]}</h2>\n  <div class="jx-grid">\n{cards}\n  </div>')
hub_block = "\n".join(sections)
splice(os.path.join(ROOT, "jurisdictions", "index.html"), "<!-- JURISDICTIONS_START -->", "<!-- JURISDICTIONS_END -->", hub_block)
print(f"hub: {total} landing pages linked across {sum(1 for k in groups if groups[k])} groups")

# --- Blog index: every blog/<slug>/ post, newest first by the post's own datePublished (JSON-LD).
#     File mtime is NOT a publication date: any site-wide sweep (image rewiring, schema repair) touches
#     every file at once and would shuffle the hub into reverse-alphabetical order. ---
import datetime as _dt
posts = []
for d in glob.glob(os.path.join(ROOT, "blog", "*")):
    idx = os.path.join(d, "index.html")
    if os.path.isdir(d) and os.path.exists(idx):
        bh = open(idx, encoding="utf-8").read()
        if 'generated-redirect-stub' in bh or 'content="noindex"' in bh:
            continue                      # skip redirect stubs (deduped comparison posts)
        m = re.search(r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})', bh)
        pub = m.group(1) if m else _dt.datetime.fromtimestamp(os.path.getmtime(idx)).strftime("%Y-%m-%d")
        posts.append((pub, os.path.basename(d), idx))
posts.sort(key=lambda p: (p[0], p[1]), reverse=True)
bcards = []
for n, (_, slug, idx) in enumerate(posts):
    t = title_of(idx, slug)
    lazy = 'loading="eager" fetchpriority="high"' if n < 2 else 'loading="lazy"'   # first row is above the fold
    if all(os.path.exists(os.path.join(ROOT, "img", "blog", slug + s)) for s in ("-thumb.jpg", "-thumb.webp", ".jpg", ".webp")):
        # the post's UNIQUE hero set (scripts/gen_blog_images.py): 600w thumb in the card, 1200w when it is wide
        sz = "(max-width: 679px) 100vw, 540px"
        pic = (f'<picture><source type="image/webp" srcset="/img/blog/{slug}-thumb.webp 600w, /img/blog/{slug}.webp 1200w" sizes="{sz}">'
               f'<img class="thumb" src="/img/blog/{slug}-thumb.jpg" srcset="/img/blog/{slug}-thumb.jpg 600w, /img/blog/{slug}.jpg 1200w" sizes="{sz}" '
               f'alt="" {lazy} decoding="async" width="600" height="338"></picture>')
    else:                                        # fallback until gen_blog_images.py has produced this slug's set
        gi = (sum(ord(c) for c in slug) % 9) + 1
        pic = (f'<picture><source srcset="/img/gallery-{gi:02d}.webp" type="image/webp">'
               f'<img class="thumb" src="/img/gallery-{gi:02d}.jpg" alt="" loading="lazy" width="600" height="360"></picture>')
    bcards.append(
        f'    <a class="post-card" href="/blog/{slug}/">{pic}'
        f'<span class="pc-body"><span class="cat">Guide</span><h2>{esc_text(t)}</h2>'
        f'<span class="meta">Consulting24</span></span></a>')
blog_block = '  <div class="blog-grid">\n' + "\n".join(bcards) + "\n  </div>"
splice(os.path.join(ROOT, "blog", "index.html"), "<!-- BLOG_POSTS_START -->", "<!-- BLOG_POSTS_END -->", blog_block)
print(f"blog index: {len(bcards)} post cards")
