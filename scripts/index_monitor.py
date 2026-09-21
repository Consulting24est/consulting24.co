#!/usr/bin/env python3
"""
index_monitor.py — indexing watchdog for consulting24.co.

Every URL in sitemap.xml is tracked from the day it first appears. For pages
not yet confirmed indexed, it re-submits to IndexNow + Bing on an escalating
schedule (1, 2, 3 days after first seen). On day >=4 still-not-indexed it runs a
per-page QC audit, prints what to fix, does a FINAL resubmit, then marks the URL
"escalated" so it stops nagging (and burning Bing's daily submission quota).

Index status is a best-effort check via Bing's `url:` operator; if it can't be
determined the URL is treated as not-yet-indexed and keeps its place in the
schedule. Re-submitting an already-indexed URL is harmless (IndexNow/Bing dedupe).

State: config/index_status.json  (per-URL: first_seen, last_action, submits,
       indexed, escalated)

  python3 scripts/index_monitor.py             # run the watchdog (used by daily_run)
  python3 scripts/index_monitor.py --report    # print status table, no submits
  python3 scripts/index_monitor.py --indexed URL   # manually mark a URL indexed
"""
import os, re, json, sys, datetime, urllib.request, importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
BASE = "https://www.consulting24.co"
HOST = "www.consulting24.co"
STATE = os.path.join(ROOT, "config", "index_status.json")
TODAY = datetime.date.today()
ESCALATE_DAY = 4  # day on which we audit + final-resubmit, then stop nagging

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def load_state():
    if os.path.exists(STATE):
        return json.loads(read(STATE))
    return {}


def save_state(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, sort_keys=True)


def sitemap_urls():
    """Page URLs from sitemap.xml. Since 2026-09-21 sitemap.xml is a sitemap INDEX; follow
    its local children (sitemap-pages.xml, sitemap-blog.xml, ...) and dedupe."""
    sm = os.path.join(ROOT, "sitemap.xml")
    if not os.path.exists(sm):
        return []
    xml = read(sm)
    if "<sitemapindex" not in xml:
        return re.findall(r"<loc>(.*?)</loc>", xml)
    urls = []
    for child in re.findall(r"<loc>(.*?)</loc>", xml):
        local = os.path.join(ROOT, child.rsplit("/", 1)[-1])
        if os.path.exists(local):
            urls.extend(re.findall(r"<loc>(.*?)</loc>", read(local)))
    return list(dict.fromkeys(u for u in urls if u.startswith(BASE)))


def days_since(iso):
    return (TODAY - datetime.date.fromisoformat(iso)).days


# ---- index-status check (best-effort) -------------------------------------
def check_indexed(url):
    """Best-effort: True only if the URL appears inside a Bing ORGANIC result
    block, False if Bing clearly returns nothing, None if uncertain.

    NB: Bing echoes the queried URL back into the page <title>, og:title and the
    search-box <input value="url:...">, so a naive `url in html` substring test
    marks EVERY url indexed (the pre-2026-07 bug). We drop those echo sites first
    and require the URL inside an actual `b_algo` result. This scrape is still
    fragile (locale pages, layout changes); the durable fix is the GSC URL
    Inspection API or Bing Webmaster GetUrlInfo — see SEO audit 2026-07."""
    q = urllib.request.quote(f"url:{url}")
    req = urllib.request.Request(f"https://www.bing.com/search?q={q}",
                                 headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", "ignore")
    except Exception:
        return None
    # Strip the places Bing echoes our own query back, so we never count it.
    body = html.split("</head>", 1)[-1]                       # drop <title>/og echo
    body = re.sub(r"<input\b[^>]*>", " ", body)               # drop search box value="url:..."
    body = re.sub(r"url:\s*https?://[^\s\"'&<]+", " ", body)  # drop any echoed url: query
    no_results = any(p in html for p in (
        "There are no results", "did not match any", "No results found",
        "Es gibt keine Ergebnisse", "ei andnud tulemusi", "Tulemusi ei"))
    has_results = "b_algo" in body
    hostpath = url.rstrip("/").split("://", 1)[-1]            # protocol-agnostic host+path
    if has_results and hostpath in body:
        return True
    if no_results or not has_results:
        return False
    return None


# ---- submission ------------------------------------------------------------
def submit_indexnow(urls):
    keyfile = os.path.join(ROOT, ".indexnow-key")
    if not (urls and os.path.exists(keyfile)):
        return
    key = read(keyfile).strip()
    payload = json.dumps({
        "host": HOST, "key": key,
        "keyLocation": f"{BASE}/{key}.txt", "urlList": urls,
    }).encode()
    req = urllib.request.Request("https://api.indexnow.org/indexnow",
                                 data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f"IndexNow resubmit: HTTP {r.status} for {len(urls)} URLs")
    except Exception as e:
        print(f"IndexNow resubmit failed (non-fatal): {e}")


def submit_bing(urls):
    keyfile = os.path.join(SCRIPTS, ".bing_api_key")
    if not urls:
        return
    if not os.path.exists(keyfile):
        # Loud, not silent: a missing key meant every Bing submission no-op'd
        # invisibly for weeks (SEO audit 2026-07). Owner: add scripts/.bing_api_key.
        print(f"WARNING: {len(urls)} URLs NOT submitted to Bing — scripts/.bing_api_key "
              f"missing. Create it in Bing Webmaster Tools > Settings > API access.")
        return
    key = read(keyfile).strip()
    payload = json.dumps({"siteUrl": BASE + "/", "urlList": urls}).encode()
    req = urllib.request.Request(
        f"https://ssl.bing.com/webmaster/api.svc/json/SubmitUrlbatch?apikey={key}",
        data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f"Bing SubmitUrlBatch: HTTP {r.status} for {len(urls)} URLs")
    except Exception as e:
        print(f"Bing SubmitUrlBatch failed (non-fatal): {e}")


# ---- per-page QC audit (reuse qc_audit.audit) ------------------------------
def _load_audit():
    spec = importlib.util.spec_from_file_location("qc", os.path.join(SCRIPTS, "qc_audit.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m.audit


def path_for(url):
    rel = url[len(BASE):].strip("/")
    return os.path.join(ROOT, rel, "index.html") if rel else os.path.join(ROOT, "index.html")


def audit_url(url, auditfn):
    p = path_for(url)
    if not os.path.exists(p):
        return ["page-missing"]
    _, fails = auditfn(p)
    return fails


def main():
    state = load_state()

    if "--indexed" in sys.argv:
        u = sys.argv[sys.argv.index("--indexed") + 1]
        state.setdefault(u, {"first_seen": TODAY.isoformat(), "submits": 0})
        state[u]["indexed"] = True
        save_state(state)
        print(f"marked indexed: {u}")
        return

    report_only = "--report" in sys.argv
    urls = sitemap_urls()

    # register newly-seen URLs
    for u in urls:
        if u not in state:
            state[u] = {"first_seen": TODAY.isoformat(), "submits": 0,
                        "indexed": None, "escalated": False, "last_action": None}

    due_resubmit, escalated_now = [], []
    auditfn = _load_audit()

    for u in urls:
        s = state[u]
        if s.get("indexed"):
            continue
        age = days_since(s["first_seen"])

        # refresh index status (cheap days 1..ESCALATE_DAY window)
        if 1 <= age <= ESCALATE_DAY and not report_only:
            res = check_indexed(u)
            if res is True:
                s["indexed"] = True
                continue
            s["indexed"] = res  # True/False/None

        if s.get("escalated"):
            continue
        if s.get("last_action") == TODAY.isoformat():
            continue  # already acted today

        if 1 <= age < ESCALATE_DAY:
            due_resubmit.append(u)
            s["last_action"] = TODAY.isoformat()
            s["submits"] = s.get("submits", 0) + 1
        elif age >= ESCALATE_DAY:
            fails = audit_url(u, auditfn)
            print(f"ESCALATE day{age} {u}"
                  + (f"  -> QC fix: {', '.join(fails)}" if fails else "  (QC ok; likely needs more authority/links)"))
            due_resubmit.append(u)
            escalated_now.append(u)
            s["last_action"] = TODAY.isoformat()
            s["submits"] = s.get("submits", 0) + 1
            s["escalated"] = True

    if report_only:
        print(f"index_monitor report: {len(urls)} tracked")
        for u in urls:
            s = state[u]
            print(f"  age{days_since(s['first_seen']):>2}d submits{s.get('submits',0)} "
                  f"indexed={s.get('indexed')} esc={s.get('escalated')}  {u}")
        return

    if due_resubmit:
        submit_indexnow(due_resubmit)
        submit_bing(due_resubmit)
    print(f"index_monitor: {len(due_resubmit)} resubmitted "
          f"({len(escalated_now)} escalated/audited), {len(urls)} tracked")
    save_state(state)


if __name__ == "__main__":
    main()
