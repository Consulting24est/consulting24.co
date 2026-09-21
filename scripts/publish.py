#!/usr/bin/env python3
"""
publish.py — regenerate sitemap.xml from all pages, refresh the blog index
card list, and ping IndexNow (Bing/Yandex) so new content is indexed fast.

Run after adding/updating blog posts:
    python3 scripts/publish.py

It is safe to run repeatedly; it derives everything from the files on disk.
"""
import os, re, json, glob, datetime, urllib.request, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://www.consulting24.co"
TODAY = datetime.date.today().isoformat()

# 0. Regenerate redirect stubs from config/redirects.json (legacy/404 -> live target)
try:
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "redirects.py"), "--prune"],
                   check=False)
except Exception as e:
    print(f"redirects step skipped (non-fatal): {e}")

# 0b. Rebuild the news desk BEFORE the sitemap so new /news/ pages land in it, and so
# items older than 48h drop out of news-sitemap.xml without anyone having to remember.
try:
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "news.py"), "build"],
                   check=False)
except Exception as e:
    print(f"news step skipped (non-fatal): {e}")

# 0c. Guarantee every /blog/ post has >= 5 internal inlinks (hub "guides" blocks + sibling
# ring). Runs before the sitemap so the content hashes below see the final HTML.
try:
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "blog_inlinks.py")], check=False)
except Exception as e:
    print(f"blog_inlinks step skipped (non-fatal): {e}")

# 0d. Keep hreflang sets, language switchers and same-language internal links in sync on the
# English pages and their /zh/ /es/ /ar/ versions (no API calls; translations themselves are
# produced by scripts/translate_pages.py --translate, run separately).
try:
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "translate_pages.py"), "--link"], check=False)
except Exception as e:
    print(f"translate --link step skipped (non-fatal): {e}")

def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()

def title_of(html):
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    return (m.group(1).strip() if m else "").replace(" | Consulting24", "")

def first_meta_desc(html):
    m = re.search(r'<meta name="description" content="(.*?)"', html, re.S)
    return m.group(1).strip() if m else ""

# 1. Collect all pages (index.html files), excluding redirect stubs and noindex pages
pages = []
for path in glob.glob(os.path.join(ROOT, "**", "index.html"), recursive=True):
    try:
        head = open(path, encoding="utf-8").read(1200)
    except Exception:
        head = ""
    if "generated-redirect-stub" in head or 'name="robots" content="noindex' in head:
        continue  # redirect stub or intentionally noindexed page — keep out of sitemap
    rel = os.path.relpath(path, ROOT)
    url_path = "" if rel == "index.html" else "/" + os.path.dirname(rel) + "/"
    pages.append((BASE + (url_path or "/"), path, url_path))

# 2. Build the sitemaps.
#    sitemap.xml is now a SITEMAP INDEX (same URL, so nothing has to be re-submitted in
#    Bing/GSC/Yandex) pointing at:
#      sitemap-pages.xml  — hubs, jurisdiction, activity, comparison and news pages
#      sitemap-blog.xml   — /blog/ posts
#      news-sitemap.xml   — Google-News-format feed built by news.py (48h window)
#    Bing reports "URLs discovered" per child sitemap, so an under-indexed bucket is visible.
#    changefreq/priority are dropped (ignored by every engine).
#
#    <lastmod> is a TEMPLATE-INSENSITIVE content hash (scripts/content_hash.py): a header,
#    footer or script change no longer bumps 1,060 dates (Bing audit 2026-09-21).
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from content_hash import content_digest
import json as _json
_HASHFILE = os.path.join(ROOT, "config", "page_hashes.json")
try:
    _store = _json.load(open(_HASHFILE))
except Exception:
    _store = {}
_prev = {u: dict(v) for u, v in _store.items()}   # snapshot for the IndexNow delta below
_today = datetime.date.today().isoformat()

def _lastmod(url, path):
    digest = content_digest(read(path))
    rec = _store.get(url)
    if rec and rec.get("hash") == digest:
        return rec["lastmod"]
    _store[url] = {"hash": digest, "lastmod": _today}
    return _today

def _urlset(rows):
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(f"  <url><loc>{u}</loc><lastmod>{lm}</lastmod></url>" for u, lm in rows)
            + "\n</urlset>\n")

LANG_PREFIXES = ("zh", "es", "ar")          # translated landing pages live under /<lang>/
buckets = {"sitemap-pages.xml": [], "sitemap-blog.xml": []}
for lp in LANG_PREFIXES:
    buckets[f"sitemap-{lp}.xml"] = []
for url, path, url_path in sorted(pages):
    row = (url, _lastmod(url, path))
    first = url_path.strip("/").split("/")[0] if url_path else ""
    if url_path.startswith("/blog/"):
        buckets["sitemap-blog.xml"].append(row)
    elif first in LANG_PREFIXES:
        buckets[f"sitemap-{first}.xml"].append(row)
    else:
        buckets["sitemap-pages.xml"].append(row)
page_rows, blog_rows = buckets["sitemap-pages.xml"], buckets["sitemap-blog.xml"]
for u in list(_store):                                   # forget pages that no longer exist
    if u not in {p[0] for p in pages}:
        _store.pop(u)

children = []
for name, rows in buckets.items():
    fpath = os.path.join(ROOT, name)
    if not rows:                                   # no pages in that language yet
        if os.path.exists(fpath):
            os.remove(fpath)
        continue
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(_urlset(rows))
    children.append((name, max((lm for _, lm in rows), default=_today)))
if os.path.exists(os.path.join(ROOT, "news-sitemap.xml")):
    children.append(("news-sitemap.xml", _today))
index_xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
             + "\n".join(f"  <sitemap><loc>{BASE}/{n}</loc><lastmod>{lm}</lastmod></sitemap>" for n, lm in children)
             + "\n</sitemapindex>\n")
with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8") as f:
    f.write(index_xml)
_json.dump(_store, open(_HASHFILE, "w"), indent=0)   # persist content hashes for next build
print("sitemap.xml (index): " + ", ".join(f"{n} {len(r)}" for n, r in buckets.items() if r))

# 3. IndexNow (Bing, Yandex, Seznam, Naver share the protocol) — DELTA ONLY.
#    Submit just the URLs whose content changed since the last build (plus new and removed
#    ones), through a persistent queue capped at INDEXNOW_CAP per calendar day. Before
#    2026-09-21 every build pushed all ~1,060 URLs (216.7K lifetime submissions), which Bing
#    treats as noise. INDEXNOW_SKIP=1 only queues (use before a deploy); INDEXNOW_FORCE_ALL=1
#    queues every URL once (after a genuine site-wide content change).
INDEXNOW_CAP = int(os.environ.get("INDEXNOW_CAP", "200"))
_QUEUE = os.path.join(ROOT, "config", "indexnow_queue.json")
_LOG = os.path.join(ROOT, "config", "indexnow_submitted.json")
_cur = {u for (u, _, _) in pages}
changed = [u for u in sorted(_cur) if _prev.get(u, {}).get("hash") != _store[u]["hash"]]
removed = sorted(set(_prev) - _cur)
if os.environ.get("INDEXNOW_FORCE_ALL"):
    changed = sorted(_cur)
try:
    queue = _json.load(open(_QUEUE))
except Exception:
    queue = []
queue = list(dict.fromkeys(queue + changed + removed))          # dedupe, keep order
try:
    submitted_log = _json.load(open(_LOG))
except Exception:
    submitted_log = {}
already_today = len(submitted_log.get(_today, []))
print(f"IndexNow delta: {len(changed)} changed, {len(removed)} removed, {len(queue)} queued, "
      f"{already_today}/{INDEXNOW_CAP} submitted today")
keyfile = os.path.join(ROOT, ".indexnow-key")
if os.environ.get("INDEXNOW_SKIP"):
    print("IndexNow: INDEXNOW_SKIP set — queued only, nothing submitted")
elif not os.path.exists(keyfile):
    print("No .indexnow-key found; skipping IndexNow ping (queue kept)")
elif queue and already_today < INDEXNOW_CAP:
    key = read(keyfile).strip()
    batch = queue[:INDEXNOW_CAP - already_today]
    payload = json.dumps({
        "host": "www.consulting24.co",
        "key": key,
        "keyLocation": f"{BASE}/{key}.txt",
        "urlList": batch,
    }).encode()
    req = urllib.request.Request(
        "https://api.indexnow.org/indexnow",
        data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f"IndexNow: HTTP {r.status} for {len(batch)} URLs")
        queue = queue[len(batch):]
        submitted_log.setdefault(_today, []).extend(batch)
        for d in [d for d in submitted_log if d < (datetime.date.today() - datetime.timedelta(days=60)).isoformat()]:
            submitted_log.pop(d)                                  # keep the log to ~60 days
    except Exception as e:
        print(f"IndexNow ping failed (non-fatal, queue kept): {e}")
elif queue:
    print(f"IndexNow: daily cap reached, {len(queue)} URLs stay queued for tomorrow")
else:
    print("IndexNow: nothing changed, nothing submitted")
_json.dump(queue, open(_QUEUE, "w"), indent=0)
_json.dump(submitted_log, open(_LOG, "w"), indent=0)

# 4. Submit sitemap to Bing Webmaster Tools via its API (SubmitFeed).
# Key from Bing Webmaster Tools > Settings > API access > API Key.
# Bing dedupes feeds, so re-submitting the same sitemap is harmless.
bing_keyfile = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".bing_api_key")
if os.path.exists(bing_keyfile):
    bing_key = read(bing_keyfile).strip()
    payload = json.dumps({
        "siteUrl": BASE + "/",
        "feedUrl": f"{BASE}/sitemap.xml",
    }).encode()
    req = urllib.request.Request(
        f"https://ssl.bing.com/webmaster/api.svc/json/SubmitFeed?apikey={bing_key}",
        data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f"Bing SubmitFeed: HTTP {r.status} for {BASE}/sitemap.xml")
    except Exception as e:
        print(f"Bing SubmitFeed failed (non-fatal): {e}")
else:
    print("No scripts/.bing_api_key found; skipping Bing sitemap submission")
