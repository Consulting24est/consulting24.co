#!/usr/bin/env python3
"""
translate_pages.py — Chinese (zh-Hans), Spanish and Arabic versions of every landing page,
translated by DeepSeek, published under /zh/<slug>/, /es/<slug>/ and /ar/<slug>/.

What a translated page is: a copy of the English page whose visible text (breadcrumbs,
article, FAQ, related blocks, primary sources, <title>, meta/og/twitter descriptions,
JSON-LD headline/description/FAQ/breadcrumbs) is translated, with
  - <html lang="zh-Hans"|"es"|"ar" dir="rtl">, /styles-rtl.css for Arabic,
  - canonical + og:url on its own URL, the same hreflang set (en, zh-Hans, es, ar,
    x-default=en) on every version incl. the English page,
  - internal links rewritten to the same-language version when one exists,
  - a language switcher inside the breadcrumbs nav (nav is outside the content hash, so
    adding it to English pages does not bump their sitemap lastmod).

Translation unit = the HTML between the breadcrumbs nav and <footer>, split at block
boundaries into ~9k-char chunks. Every chunk is verified: the tag sequence and the set of
href/src values must be identical before and after; a mismatch retries, then halves the
chunk, then keeps English for that fragment (logged). English pages are never modified
except for the hreflang links + switcher (--link).

State: config/translations.json  {"/slug/": {"zh": {"src": <content digest>, "date": ...}}}
A page is (re)translated when its English content digest changed since the last run.

  python3 scripts/translate_pages.py --translate [--langs zh,es,ar] [--workers 12] [--max-tasks N] [--only slug]
  python3 scripts/translate_pages.py --link          # refresh hreflang/switchers/internal links only (no API)
  python3 scripts/translate_pages.py --status
"""
from __future__ import annotations
import os, re, sys, json, html, time, glob, threading, datetime, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from content_hash import content_digest  # noqa: E402

BASE = "https://www.consulting24.co"
STATE = os.path.join(ROOT, "config", "translations.json")
LOG = os.path.join(ROOT, "logs", "translate.log")
EXCLUDE_DIRS = {"blog", "news", "luxury-chauffeur-service-dubai", "img", "data", "config",
                "scripts", "logs", "link-research", "research", "zh", "es", "ar"}
LANGS = {
    "zh": {"hreflang": "zh-Hans", "html_lang": "zh-Hans", "dir": "ltr", "label": "中文",
           "prompt": "Simplified Chinese (zh-Hans) as used in mainland China business writing"},
    "es": {"hreflang": "es", "html_lang": "es", "dir": "ltr", "label": "Español",
           "prompt": "neutral international Spanish for business readers in Spain and Latin America"},
    "ar": {"hreflang": "ar", "html_lang": "ar", "dir": "rtl", "label": "العربية",
           "prompt": "Modern Standard Arabic for business readers in the Gulf"},
}
CHUNK = 9000
MAX_TOKENS = 8192
_lock = threading.Lock()


# ----------------------------------------------------------------------------- helpers
def read(p):
    with open(p, encoding="utf-8", errors="ignore") as f:
        return f.read()


def write(p, s):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(s)
    os.replace(tmp, p)


def log(msg):
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    with _lock:
        print(line, flush=True)
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def deepseek_key():
    k = os.environ.get("DEEPSEEK_API_KEY")
    if k:
        return k.strip()
    p = os.path.join(ROOT, "scripts", ".deepseek_key")
    if os.path.exists(p):
        return read(p).strip()
    sys.exit("No DeepSeek key (DEEPSEEK_API_KEY or scripts/.deepseek_key)")


def landing_pages():
    """[(slug, path)] slug '' = homepage. Top-level directories only, no stubs, no noindex."""
    out = []
    root_index = os.path.join(ROOT, "index.html")
    if os.path.exists(root_index):
        out.append(("", root_index))
    for d in sorted(os.listdir(ROOT)):
        if d.startswith(".") or d in EXCLUDE_DIRS or not os.path.isdir(os.path.join(ROOT, d)):
            continue
        p = os.path.join(ROOT, d, "index.html")
        if not os.path.exists(p):
            continue
        head = read(p)[:1500]
        if "generated-redirect-stub" in head or 'content="noindex' in head:
            continue
        out.append((d, p))
    return out


def url_for(slug, lang=None):
    path = f"/{slug}/" if slug else "/"
    return BASE + (f"/{lang}{path}" if lang else path)


def out_path(slug, lang):
    return os.path.join(ROOT, lang, slug, "index.html") if slug else os.path.join(ROOT, lang, "index.html")


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def save_state(st):
    with _lock:
        write(STATE, json.dumps(st, indent=1, ensure_ascii=False, sort_keys=True))


# ----------------------------------------------------------------------------- DeepSeek
SYSTEM = (
    "You are a professional translator for a crypto-licensing consultancy website. You translate "
    "HTML fragments into {lang}. RULES: (1) Output ONLY the translated HTML fragment — no code "
    "fences, no commentary. (2) Keep every HTML tag, attribute and attribute value EXACTLY as is "
    "(href, src, class, id, style, data-*, target, rel). Never add, remove, reorder or rename tags. "
    "(3) Translate all human-visible text nodes, plus alt and title attribute text. (4) Do NOT "
    "translate: URLs, code, the brand 'Consulting24', product/company names (Binance, LBank, "
    "Mercedes-Maybach), currency codes and amounts (EUR 6,000, USD, AED), regulator names and law "
    "acronyms — keep MiCA, CASP, VASP, MSB, VARA, KYC, AML, FIU, SEC, FinCEN, FINTRAC, MAS, SFC, "
    "DFSA, ADGM, EMI, OTC, NFT, DeFi, ICO in Latin letters. (5) Keep numbers, dates, percentages "
    "and HTML entities (&amp; &rsaquo; &middot;) unchanged. (6) Use natural, fluent, professional "
    "wording; keep headings concise. (7) Preserve whitespace between tags."
)


def call_deepseek(system, user, temperature=0.2, json_mode=False, retries=4):
    body = {"model": "deepseek-chat",
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": MAX_TOKENS, "temperature": temperature, "stream": False}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    data = json.dumps(body).encode()
    last = None
    for attempt in range(retries):
        req = urllib.request.Request("https://api.deepseek.com/chat/completions", data=data,
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Bearer " + deepseek_key()})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                j = json.load(r)
            msg = j["choices"][0]["message"]["content"]
            usage = j.get("usage", {})
            return msg, usage
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code} {e.read()[:200]!r}"
            if e.code in (400, 401, 403):
                break
        except Exception as e:  # timeouts, connection resets
            last = repr(e)
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"DeepSeek failed: {last}")


# ----------------------------------------------------------------------------- chunking
_SPLIT_AT = re.compile(r"(</(?:p|h1|h2|h3|h4|ul|ol|table|details|section|figure|div|nav|blockquote|dl)>)")


def chunks(fragment, size=CHUNK):
    """Split at closing block tags (delimiters kept with the preceding piece) into ~size chars."""
    bits = _SPLIT_AT.split(fragment)
    pieces = ["".join(bits[i:i + 2]) for i in range(0, len(bits), 2)]
    parts, cur = [], ""
    for piece in pieces:
        if cur and len(cur) + len(piece) > size:
            parts.append(cur); cur = ""
        cur += piece
    if cur:
        parts.append(cur)
    return parts


def tag_seq(h):
    return re.findall(r"<(/?[a-zA-Z][a-zA-Z0-9]*)", h)


def refs(h):
    return sorted(re.findall(r'\b(?:href|src)="([^"]*)"', h))


def strip_fences(s):
    s = s.strip()
    s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s


KEPT_ENGLISH = []          # chars of fragments that could not be translated structurally (per process)


def translate_fragment(fragment, lang, depth=0):
    """Translate one chunk; verify structure; retry / split / fall back to English."""
    if not re.search(r"[A-Za-z]{3,}", re.sub(r"<[^>]+>", " ", fragment)):
        return fragment, 0                      # nothing to translate (tags only)
    system = SYSTEM.format(lang=LANGS[lang]["prompt"])
    src_tags, src_refs = tag_seq(fragment), refs(fragment)
    tokens = 0
    for attempt in range(2):
        user = fragment if attempt == 0 else (
            "IMPORTANT: your previous answer changed the HTML structure. Return the SAME tags in "
            "the SAME order with the SAME attributes; translate only text.\n\n" + fragment)
        out, usage = call_deepseek(system, user)      # API failure aborts the whole page (never ship English under /zh/)
        tokens += usage.get("total_tokens", 0)
        out = strip_fences(out)
        if tag_seq(out) == src_tags and refs(out) == src_refs:
            return out, tokens
    if depth < 2 and len(fragment) > 1500:
        halves = chunks(fragment, size=max(800, len(fragment) // 2 + 1))
        if len(halves) > 1:
            outs = []
            for h in halves:
                o, t = translate_fragment(h, lang, depth + 1)
                outs.append(o); tokens += t
            return "".join(outs), tokens
    log(f"  structure mismatch kept English fragment ({lang}, {len(fragment)} chars)")
    KEPT_ENGLISH.append(len(fragment))
    return fragment, tokens


def translate_meta(title, desc, lang):
    system = ("You translate web page metadata into {lang}. Reply with a JSON object "
              '{"title": "...", "description": "..."}. Keep brand names, acronyms (MiCA, CASP, VASP, '
              "MSB, VARA, KYC, AML), currency codes/amounts and years unchanged. Title <= 65 characters "
              "where the language allows, description <= 160 characters, both natural and specific.").format(
        lang=LANGS[lang]["prompt"])
    user = json.dumps({"title": title, "description": desc}, ensure_ascii=False)
    try:
        out, usage = call_deepseek(system, user, json_mode=True)
        j = json.loads(out)
        t = str(j.get("title") or title).strip()
        d = str(j.get("description") or desc).strip()
        return t, d, usage.get("total_tokens", 0)
    except Exception as e:
        log(f"  meta translation failed ({lang}): {e}")
        return title, desc, 0


# ----------------------------------------------------------------------------- page assembly
def region_bounds(page):
    a = page.find('<nav class="breadcrumbs"')
    if a == -1:
        a = page.find("<article")
    b = page.find("<footer")
    if a == -1 or b == -1 or b <= a:
        return None
    return a, b


def hreflang_block(slug, available):
    """<link rel=alternate> set for every version that exists (+ en, x-default)."""
    lines = [f'<link rel="alternate" hreflang="en" href="{url_for(slug)}">']
    for lang in LANGS:
        if lang in available:
            lines.append(f'<link rel="alternate" hreflang="{LANGS[lang]["hreflang"]}" href="{url_for(slug, lang)}">')
    lines.append(f'<link rel="alternate" hreflang="x-default" href="{url_for(slug)}">')
    return "\n".join(lines)


_HREFLANG_RE = re.compile(r'\n?<link rel="alternate" hreflang="[^"]*" href="https://www\.consulting24\.co/[^"]*">', re.S)
_SWITCH_RE = re.compile(r'<!-- LANG_SWITCH_START -->.*?<!-- LANG_SWITCH_END -->', re.S)


def switcher(slug, current, available):
    items = [("en", "EN", url_for(slug))]
    for lang in LANGS:
        if lang in available:
            items.append((lang, LANGS[lang]["label"], url_for(slug, lang)))
    parts = []
    for code, label, href in items:
        if code == current:
            parts.append(f'<strong aria-current="true">{label}</strong>')
        else:
            hl = "en" if code == "en" else LANGS[code]["html_lang"]
            parts.append(f'<a href="{href}" hreflang="{hl}" lang="{hl}">{label}</a>')
    return ('<!-- LANG_SWITCH_START --><span class="lang-switch" style="display:inline-block;'
            'margin-inline-start:14px;font-size:13px;white-space:nowrap">' + " &middot; ".join(parts)
            + '</span><!-- LANG_SWITCH_END -->')


def apply_links(page, slug, current, available):
    """Idempotent: refresh hreflang set (after canonical) and the switcher in the breadcrumbs."""
    page = _HREFLANG_RE.sub("", page)
    block = hreflang_block(slug, available)
    m = re.search(r'<link rel="canonical" href="[^"]*">', page)
    if m:
        page = page[:m.end()] + "\n" + block + page[m.end():]
    page = _SWITCH_RE.sub("", page)
    nav = re.search(r'(<nav class="breadcrumbs"[^>]*>)(.*?)(</nav>)', page, re.S)
    if nav:
        page = page[:nav.start(3)] + switcher(slug, current, available) + page[nav.start(3):]
    return page


def rewrite_internal_links(fragment, lang, translated_slugs):
    def repl(m):
        href = m.group(1)
        path = href.split("#")[0].split("?")[0]
        if path == "/" or path == BASE + "/":
            return f'href="/{lang}/"' if "" in translated_slugs else m.group(0)
        mm = re.fullmatch(r"(?:https://www\.consulting24\.co)?/([a-z0-9-]+)/", path)
        if mm and mm.group(1) in translated_slugs:
            return f'href="/{lang}/{mm.group(1)}/"'
        return m.group(0)
    return re.sub(r'href="([^"]*)"', repl, fragment)


def rebuild_jsonld(page, lang, slug, title_t, desc_t, title_en, desc_en):
    """Translate the language-bearing JSON-LD fields; FAQ + breadcrumbs from the translated HTML."""
    faqs = re.findall(r"<details><summary>(.*?)</summary><p>(.*?)</p></details>", page, re.S)
    crumbs = None
    nav = re.search(r'<nav class="breadcrumbs"[^>]*>(.*?)</nav>', page, re.S)
    if nav:
        inner = _SWITCH_RE.sub("", nav.group(1))
        crumbs = []
        for m in re.finditer(r'<a href="([^"]+)">(.*?)</a>|([^<>]+)$', inner.strip(), re.S):
            if m.group(1):
                crumbs.append((html.unescape(re.sub("<[^>]+>", "", m.group(2))).strip(), m.group(1)))
            elif m.group(3):
                last = html.unescape(m.group(3).replace("&rsaquo;", "")).strip(" ›")
                if last:
                    crumbs.append((last, url_for(slug, lang)))

    def fix(obj):
        if isinstance(obj, list):
            return [fix(o) for o in obj]
        if not isinstance(obj, dict):
            return obj
        t = obj.get("@type")
        if t in ("Article", "BlogPosting", "WebPage", "Service"):
            for k in ("headline", "name"):
                if obj.get(k) == html.unescape(title_en) or k == "headline":
                    if k in obj:
                        obj[k] = html.unescape(title_t)
            if obj.get("description") and desc_en and obj["description"] == html.unescape(desc_en):
                obj["description"] = html.unescape(desc_t)
            obj["inLanguage"] = LANGS[lang]["html_lang"]
            for k in ("url", "mainEntityOfPage"):
                v = obj.get(k)
                if isinstance(v, str) and v == url_for(slug):
                    obj[k] = url_for(slug, lang)
                elif isinstance(v, dict) and v.get("@id") == url_for(slug):
                    v["@id"] = url_for(slug, lang)
        if t == "FAQPage" and faqs:
            obj["mainEntity"] = [{"@type": "Question", "name": html.unescape(re.sub("<[^>]+>", "", q)),
                                  "acceptedAnswer": {"@type": "Answer",
                                                     "text": html.unescape(re.sub("<[^>]+>", "", a))}}
                                 for q, a in faqs]
        if t == "BreadcrumbList" and crumbs:
            obj["itemListElement"] = [{"@type": "ListItem", "position": i + 1, "name": n,
                                       "item": (BASE + u if u.startswith("/") else u)}
                                      for i, (n, u) in enumerate(crumbs)]
        for k, v in list(obj.items()):
            if isinstance(v, (dict, list)) and k != "mainEntity" or (k == "mainEntity" and t != "FAQPage"):
                obj[k] = fix(v)
        return obj

    def repl(m):
        try:
            d = json.loads(m.group(1))
        except Exception:
            return m.group(0)
        return ('<script type="application/ld+json">' + json.dumps(fix(d), ensure_ascii=False)
                + "</script>")
    return re.sub(r'<script type="application/ld\+json">(.*?)</script>', repl, page, flags=re.S)


def build_translation(slug, src_path, lang, translated_slugs):
    """Return (translated_page_html, tokens_used)."""
    page = read(src_path)
    bounds = region_bounds(page)
    if not bounds:
        raise RuntimeError("no article/footer region")
    a, b = bounds
    head, region, tail = page[:a], page[a:b], page[b:]
    tokens = 0
    # 1. visible content, chunk by chunk
    out_parts = []
    kept_before = sum(KEPT_ENGLISH)
    for ch in chunks(region):
        o, t = translate_fragment(ch, lang)
        out_parts.append(o); tokens += t
    kept = sum(KEPT_ENGLISH) - kept_before
    if kept > 0.15 * len(region):
        raise RuntimeError(f"{kept} of {len(region)} chars could not be translated structurally")
    region_t = rewrite_internal_links("".join(out_parts), lang, translated_slugs)
    # 2. head metadata
    title_en = (re.search(r"<title>(.*?)</title>", head, re.S) or [None, ""])[1].strip()
    desc_en = (re.search(r'<meta name="description" content="(.*?)"', head, re.S) or [None, ""])[1].strip()
    title_t, desc_t, t = translate_meta(html.unescape(title_en), html.unescape(desc_en), lang)
    tokens += t
    title_t, desc_t = html.escape(title_t, quote=False), html.escape(desc_t, quote=True)
    head = re.sub(r"<title>.*?</title>", lambda m: f"<title>{title_t}</title>", head, count=1, flags=re.S)
    for attr in ('name="description"', 'property="og:description"', 'name="twitter:description"'):
        head = re.sub(rf'(<meta {attr} content=")[^"]*(")', lambda m: m.group(1) + desc_t + m.group(2), head)
    for attr in ('property="og:title"', 'name="twitter:title"'):
        head = re.sub(rf'(<meta {attr} content=")[^"]*(")', lambda m: m.group(1) + html.escape(html.unescape(title_t), quote=True) + m.group(2), head)
    head = head.replace(f'rel="canonical" href="{url_for(slug)}"', f'rel="canonical" href="{url_for(slug, lang)}"')
    head = head.replace(f'property="og:url" content="{url_for(slug)}"', f'property="og:url" content="{url_for(slug, lang)}"')
    head = re.sub(r'<html lang="en">', f'<html lang="{LANGS[lang]["html_lang"]}"' + (' dir="rtl"' if LANGS[lang]["dir"] == "rtl" else "") + ">", head, count=1)
    head = re.sub(r'<meta property="og:locale" content="[^"]*">', "", head)
    head = head.replace('href="../styles.css"', 'href="/styles.css"').replace('href="styles.css"', 'href="/styles.css"')
    if LANGS[lang]["dir"] == "rtl" and "/styles-rtl.css" not in head:
        head = head.replace('<link rel="stylesheet" href="/styles.css">',
                            '<link rel="stylesheet" href="/styles.css">\n<link rel="stylesheet" href="/styles-rtl.css">', 1)
    # tail (footer) keeps English but its home links point to the language home
    tail = rewrite_internal_links(tail, lang, translated_slugs) if "" in translated_slugs else tail
    page_t = head + region_t + tail
    page_t = rebuild_jsonld(page_t, lang, slug, title_t, desc_t, title_en, desc_en)
    return page_t, tokens


# ----------------------------------------------------------------------------- drivers
def available_langs(slug):
    return {lang for lang in LANGS if os.path.exists(out_path(slug, lang))}


def priority(slug):
    if slug == "":
        return 0
    if slug in ("jurisdictions", "cost", "about", "contact", "requirements", "application-process"):
        return 1
    if re.fullmatch(r"[a-z-]+-crypto-license", slug) and "-vs-" not in slug:
        return 2
    if slug.startswith(("mica", "msb", "vasp", "vara", "casp", "stablecoin", "crypto-otc", "exchange", "crypto-exchange")):
        return 3
    if "-vs-" in slug:
        return 5
    return 4


def do_link(pages):
    """Refresh hreflang + switcher on English pages and every translated page; rewrite links."""
    translated_slugs = {slug for slug, _ in pages if available_langs(slug)}
    changed = 0
    for slug, src in pages:
        avail = available_langs(slug)
        if not avail:
            continue
        s = read(src)
        n = apply_links(s, slug, "en", avail)
        if n != s:
            write(src, n); changed += 1
        for lang in avail:
            p = out_path(slug, lang)
            s = read(p)
            n = apply_links(s, slug, lang, avail)
            n = rewrite_internal_links(n, lang, translated_slugs)
            if n != s:
                write(p, n); changed += 1
    print(f"translate --link: {len(translated_slugs)} pages with translations, {changed} files refreshed")


def do_translate(pages, langs, workers, max_tasks, only):
    st = load_state()
    all_slugs = {slug for slug, _ in pages}
    tasks = []
    for slug, src in sorted(pages, key=lambda x: (priority(x[0]), x[0])):
        if only and slug != only:
            continue
        digest = content_digest(read(src))
        for lang in langs:
            rec = st.get(url_for(slug), {}).get(lang)
            if rec and rec.get("src") == digest and os.path.exists(out_path(slug, lang)):
                continue
            tasks.append((slug, src, lang, digest))
    if max_tasks:
        tasks = tasks[:max_tasks]
    log(f"translate: {len(tasks)} page-language tasks pending (workers={workers})")
    if not tasks:
        return 0
    done = fails = 0
    total_tokens = 0
    t0 = time.time()

    def run(task):
        slug, src, lang, digest = task
        t1 = time.time()
        page_t, tokens = build_translation(slug, src, lang, all_slugs)
        write(out_path(slug, lang), page_t)
        return slug, lang, digest, tokens, time.time() - t1

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(run, t): t for t in tasks}
        for f in as_completed(futs):
            slug, src, lang, digest = futs[f]
            try:
                slug, lang, digest, tokens, secs = f.result()
            except Exception as e:
                fails += 1
                log(f"FAIL {url_for(slug, lang)}: {e}")
                continue
            done += 1; total_tokens += tokens
            st = load_state()
            st.setdefault(url_for(slug), {})[lang] = {"src": digest, "date": datetime.date.today().isoformat(),
                                                      "tokens": tokens}
            save_state(st)
            log(f"ok {done}/{len(tasks)} {url_for(slug, lang)} {tokens} tok {secs:.0f}s "
                f"(elapsed {(time.time()-t0)/60:.0f} min, {total_tokens/1e6:.2f}M tok)")
    log(f"translate: done {done}, failed {fails}, {total_tokens/1e6:.2f}M tokens, "
        f"{(time.time()-t0)/60:.0f} min")
    return done


def do_status(pages):
    st = load_state()
    per = {lang: 0 for lang in LANGS}
    stale = {lang: 0 for lang in LANGS}
    for slug, src in pages:
        d = content_digest(read(src))
        for lang in LANGS:
            rec = st.get(url_for(slug), {}).get(lang)
            if rec and os.path.exists(out_path(slug, lang)):
                per[lang] += 1
                if rec.get("src") != d:
                    stale[lang] += 1
    print(f"landing pages: {len(pages)}")
    for lang in LANGS:
        print(f"  {lang}: {per[lang]} translated, {stale[lang]} stale")


def main(argv):
    pages = landing_pages()
    if "--status" in argv:
        return do_status(pages)
    if "--link" in argv:
        return do_link(pages)
    if "--translate" in argv:
        langs = argv[argv.index("--langs") + 1].split(",") if "--langs" in argv else list(LANGS)
        workers = int(argv[argv.index("--workers") + 1]) if "--workers" in argv else 12
        max_tasks = int(argv[argv.index("--max-tasks") + 1]) if "--max-tasks" in argv else 0
        only = argv[argv.index("--only") + 1] if "--only" in argv else None
        n = do_translate(pages, langs, workers, max_tasks, only)
        do_link(pages)
        return n
    print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
