#!/usr/bin/env python3
"""
gen_blogger_posts.py — DeepSeek-powered Blogger POST generator (sustainable 40/day).

Blogger posts were a fixed templated set (60, all published). This generates fresh
ARTICLE dicts from the blog topic queue (blog/topics.md) via DeepSeek and appends
them to config/extra_posts.json, which consulting24_blog.py loads and merges into
ARTICLES so the daily Blogger run keeps publishing new content.

Claude = brain (topics, schema, fact-grounding, cleaning); DeepSeek writes prose.
Reads DeepSeek key from $DEEPSEEK_API_KEY or scripts/.deepseek_key.

Usage:
  python3 scripts/gen_blogger_posts.py 40     # generate up to 40 new posts
"""
from __future__ import annotations
import json, os, pathlib, sys, urllib.request, re, hashlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "config" / "extra_posts.json"
POSTED = ROOT / "config" / "blog_posted.json"
TOPICS_MD = ROOT / "blog" / "topics.md"
SITE = "https://www.consulting24.co"

def key() -> str:
    k = os.environ.get("DEEPSEEK_API_KEY")
    if k: return k.strip()
    p = ROOT / "scripts" / ".deepseek_key"
    if p.exists(): return p.read_text().strip()
    sys.exit("No DeepSeek key")

SYSTEM = (
 "You are a senior crypto-licensing consultant writing an authoritative blog post for "
 "Consulting24 (X24Consulting OU, Estonia; founder Mardo Soo). Clear professional English for "
 "crypto founders. Be accurate. MiCA is in force across the EU in 2026; EU CASP capital tiers are "
 "EUR 50,000 / 125,000 / 150,000 by activity class. Panama has no dedicated crypto licence "
 "(incorporate a Sociedad Anonima; 0% tax on foreign-source income; 2-3 week setup). Do not invent "
 "precise figures; hedge with ranges when unsure. "
 "STYLE: no em dashes or en dashes, no exclamation marks, avoid 'seamless, robust, leverage, "
 "navigate, landscape, realm, delve, unlock, elevate, tapestry, game-changer, cutting-edge'. "
 "Return ONLY JSON: {\"lede\": \"1-2 sentence hook\", "
 "\"sections\": [{\"heading\":\"...\",\"paras\":[\"...\",\"...\"]} x4-6], "
 "\"faqs\": [{\"q\":\"...\",\"a\":\"...\"} x8] }. Each section 2-3 substantial paragraphs."
)

BANNED = {"seamless":"smooth","robust":"strong","leverage":"use","navigate":"handle",
 "landscape":"market","realm":"area","delve":"look","unlock":"open","elevate":"improve",
 "tapestry":"mix","game-changer":"major shift","cutting-edge":"modern"}

# landing target by keyword heuristics (map topic to the most relevant live page)
JUR_SLUGS = [d.name for d in ROOT.glob("*/") if (d / "index.html").exists()
             and d.name not in {"blog","scripts","config","img","logs","jurisdictions"}]

def clean(s: str) -> str:
    if not s: return s
    s = s.replace("—", ", ").replace("–", "-").replace("!", ".")
    for b, r in BANNED.items():
        s = re.sub(rf"\b{re.escape(b)}\b", r, s, flags=re.I)
    return re.sub(r"\s+,", ",", s).strip()

def landing_for(title: str) -> str:
    t = title.lower()
    for slug in sorted(JUR_SLUGS, key=len, reverse=True):
        base = slug.replace("-crypto-license", "").replace("-", " ")
        if base and base in t:
            return f"/{slug}/"
    return "/"

def related_for(landing: str) -> list:
    pool = [("Panama crypto company (EUR 6,000)", "/"),
            ("Compare all jurisdictions", "/jurisdictions/"),
            ("Lithuania MiCA CASP", "/lithuania-crypto-license/"),
            ("Estonia crypto license", "/estonia-crypto-license/"),
            ("Crypto license cost", "/cost/"),
            ("Requirements checklist", "/requirements/")]
    return [(l, p) for l, p in pool if p != landing][:4]

def call_deepseek(user: str) -> dict:
    body = json.dumps({"model": "deepseek-chat",
        "messages": [{"role":"system","content":SYSTEM},{"role":"user","content":user}],
        "response_format": {"type":"json_object"}, "max_tokens": 6000,
        "temperature": 0.6, "stream": False}).encode()
    req = urllib.request.Request("https://api.deepseek.com/chat/completions", data=body,
        headers={"Content-Type":"application/json","Authorization":"Bearer "+key()})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(json.load(r)["choices"][0]["message"]["content"])

def slugify(t: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")
    return s[:80].rstrip("-")

def build_post(title: str) -> dict:
    landing = landing_for(title)
    user = (f"Write a blog post titled '{title}'. Primary keyword: '{' '.join(title.split()[:4])}'. "
            f"The relevant on-site page is {SITE}{landing}. Write 4-6 sections and 8 FAQs per schema.")
    d = call_deepseek(user)
    sections = [[clean(s.get("heading","")), [clean(p) for p in s.get("paras",[]) if p.strip()]]
                for s in d.get("sections", [])[:6]]
    sections = [s for s in sections if s[0] and s[1]]
    faqs = [[clean(f.get("q","")), clean(f.get("a",""))] for f in d.get("faqs", [])[:8]]
    faqs = [f for f in faqs if f[0] and f[1]]
    while len(faqs) < 8:
        faqs.append(["Does Consulting24 help with this?",
                     "Yes. Consulting24 advises on jurisdiction choice and delivers or coordinates the setup. Contact mardo@consulting24.co."])
    return {"slug": slugify(title), "title": title,
            "keyword": " ".join(title.split()[:4]),
            "landing": landing, "lede": clean(d.get("lede","")),
            "sections": sections or [["Overview", [clean(title)]]],
            "faqs": faqs[:8], "related": related_for(landing),
            "labels": []}

def next_topics(n: int, have: set) -> list:
    out = []
    for line in TOPICS_MD.read_text().splitlines():
        m = re.match(r"- \[ \]\s*(.+)", line)
        if m:
            t = m.group(1).strip()
            s = slugify(t)
            if s not in have and s[:70].rstrip("-") not in have:   # daily_run.py cuts slugs at 70
                out.append(t)
        if len(out) >= n: break
    return out

def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    existing = json.loads(OUT.read_text()) if OUT.exists() else []
    have = {p["slug"] for p in existing}
    if POSTED.exists():
        have |= set(json.loads(POSTED.read_text()).get("posts", {}).keys())
    # topics the website already covers under /blog/<slug>/ stay on www (no Blogger twin)
    for d in (ROOT / "blog").iterdir():
        f = d / "index.html"
        if f.is_file() and "generated-redirect-stub" not in f.read_text()[:400]:
            have.add(d.name)
    made = 0
    for title in next_topics(n, have):
        try:
            post = build_post(title)
            if post["slug"] in have: continue
            existing.append(post); have.add(post["slug"]); made += 1
            OUT.write_text(json.dumps(existing, indent=1, ensure_ascii=False))
            print(f"generated [{made}] {post['slug']} ({len(post['sections'])} sec, {len(post['faqs'])} faq)")
        except Exception as e:
            print(f"ERROR '{title}': {e}")
    print(f"done. {made} new posts; {len(existing)} total in {OUT}")

if __name__ == "__main__":
    main()
