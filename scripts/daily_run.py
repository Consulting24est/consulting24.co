#!/usr/bin/env python3
"""
daily_run.py — fully autonomous daily content pipeline for consulting24.co.
Runs WITHOUT an interactive agent (designed for a macOS LaunchAgent / cron).
Publishes 40 keyword landing pages + 40 blog posts/day via DeepSeek + QC gate,
rebuilds indexes, links, sitemap/IndexNow, commits and pushes.

Brief composition is automated: known jurisdictions use a curated FACTS map
(accurate 2026 facts); long-tail items get a guard-railed generic brief and
rely on the generator's accuracy + QC gates. Deck-fed pages (e.g. Lithuania)
keep their hand-verified figures unless overwritten here.
"""
import json, os, re, sys, subprocess, importlib.util, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
N_LANDING = int(os.environ.get("N_LANDING", "40"))
N_BLOG = int(os.environ.get("N_BLOG", "40"))

spec = importlib.util.spec_from_file_location("gen", os.path.join(ROOT, "scripts", "generate.py"))
gen = importlib.util.module_from_spec(spec); spec.loader.exec_module(gen)

# Curated accurate facts for major jurisdictions (base slug -> brief facts).
FACTS = {
 "panama": "Panama | NO enacted crypto/VASP licence exists (2026). A draft framework, Anteproyecto 314 (tabled Jan 2026), is pending and NOT law; under it future supervision would sit with the SBP + UAF. The offering is a Panama company (Sociedad Anonima) + AML/CTF compliance programme, NOT a licence. DO NOT invent a Panama crypto law (there is no Law 697, no Law 61 of 2023), DO NOT invent a regulator that issues a Panama crypto licence (no 'AFIP', and the SSNF supervises non-financial businesses like casinos/real-estate for AML only, NOT crypto). DASP/CNAD/Ley de Activos Digitales belong to EL SALVADOR, never Panama. ~2-3 weeks; EUR 6,000 flat; 0% tax on foreign-source income. Consulting24 delivers Panama directly.",
 "lithuania": "Lithuania | Bank of Lithuania; MiCAR CASP; capital EUR 50k/125k/150k by activity; EU passporting; ~4-8 months; setup ~EUR 40,000 (estimated); Consulting24 delivers directly.",
 "estonia": "Estonia | Finantsinspektsioon; MiCA CASP (replaced FIU/VASP); capital 50k/125k/150k; 0% on retained profit, 22% on distribution; ~5-9 months; e-Residency; Consulting24 delivers directly.",
 "czech-republic": "Czech Republic | Czech National Bank; MiCA CASP; capital 50k/125k/150k; cost-efficient EU; ~4-8 months; Consulting24 advises and coordinates.",
 "poland": "Poland | KNF; MiCA CASP; capital 50k/125k/150k; cost-efficient EU; ~4-8 months; Consulting24 advises and coordinates.",
 "malta": "Malta | MFSA; MiCA CASP (built on VFA); capital 50k/125k/150k; English official; ~5-9 months; Consulting24 advises and coordinates.",
 "cyprus": "Cyprus | CySEC; MiCA CASP; capital 50k/125k/150k; English; favourable tax; ~5-9 months; Consulting24 advises and coordinates.",
 "switzerland": "Switzerland | non-EU; FINMA; SRO/VQF AML membership, DLT Act, fintech/banking licences; Crypto Valley; premium; ~6-12 months; Consulting24 advises and coordinates.",
 "cayman-islands": "Cayman Islands | CIMA; VASP Act; 0% direct tax; funds and token issuers; economic substance; ~3-6 months; Consulting24 advises and coordinates.",
 "bvi": "BVI | BVI FSC; VASP Act 2022; 0% corporate tax; token issuers/funds; ~3-6 months; Consulting24 advises and coordinates.",
 "seychelles": "Seychelles | FSA; VASP Act 2024; low cost; 0% foreign-source tax; ~2-4 months; Consulting24 advises and coordinates.",
 "canada": "Canada | FINTRAC MSB registration for virtual currency dealing; provincial securities for tokens; weeks-months; Consulting24 advises and coordinates.",
 "singapore": "Singapore | MAS; Payment Services Act DPT licence; high bar, base capital, local presence; ~9-18 months; Consulting24 advises and coordinates.",
 "hong-kong": "Hong Kong | SFC; VATP licensing since 2023; high bar, local presence; ~9-12 months; Consulting24 advises and coordinates.",
 "georgia": "Georgia | National Bank of Georgia; VASP registration (from 2023); low cost, fast ~1-3 months; Consulting24 advises and coordinates.",
 "mauritius": "Mauritius | FSC; VAITOS Act 2021 licence classes; ~3-6 months; Consulting24 advises and coordinates.",
 "gibraltar": "Gibraltar | GFSC; DLT Provider licence since 2018; reputable; ~3-6 months; Consulting24 advises and coordinates.",
 "bahamas": "Bahamas | Securities Commission; DARE Act 2024; 0% income tax; ~3-6 months; Consulting24 advises and coordinates.",
 "costa-rica": "Costa Rica | no dedicated crypto licence; general company + AML; strong Panama comparison; Consulting24 advises and coordinates.",
 "el-salvador": "El Salvador | CNAD; DASP (Digital Assets Issuance Law) + BSP (Bitcoin Law); Bitcoin legal tender; tax incentives; ~3-6 months; Consulting24 advises and coordinates.",
 "dubai": "Dubai | VARA category licences; premium; 0% personal, 9% corporate (free-zone reliefs); DIFC/ADGM separate; DELIVERY=comparison-only.",
 "abu-dhabi": "Abu Dhabi | ADGM FSRA crypto framework; premium; DELIVERY=comparison-only.",
}
# UAE VARA / ADGM is COMPARISON-ONLY (user directive 2026-05-27): never claim
# Consulting24 advises+coordinates or files a UAE licence. Match tokens ANYWHERE
# in the slug so compound slugs (fastest-crypto-license-dubai, vara-license,
# crypto-exchange-license-abu-dhabi, ...) are caught, not just exact bases.
COMPARISON_ONLY_TOKENS = ("dubai", "abu-dhabi", "uae", "vara", "adgm")

def is_comparison_only(slug):
    s = slug.lower()
    return any(tok in s for tok in COMPARISON_ONLY_TOKENS)

def sh(cmd):
    return subprocess.run(cmd, cwd=ROOT, shell=True, text=True, capture_output=True)

def base_of(slug):
    return slug.replace("-crypto-license", "")

def landing_brief(slug):
    b = base_of(slug)
    if is_comparison_only(slug):
        # Comparison-only overrides even a FACTS entry, so a compound UAE slug can
        # never inherit an advise+coordinate brief.
        base = FACTS[b] if b in FACTS else (b.replace("-", " ").title() + " | Use accurate, current 2026 "
               "facts for this crypto-licensing topic: regulator, licence type, capital, tax, timeline, allowed activities.")
        if "comparison-only" not in base.lower():
            base += " DELIVERY=comparison-only."
        return (base + " Consulting24 covers this jurisdiction for comparison ONLY — never claim we advise, "
                "coordinate, or file the licence here; we deliver directly only in Panama, Estonia, and Lithuania.")
    if b in FACTS: return FACTS[b]
    name = b.replace("-", " ").title()
    extra = " Consulting24 advises and coordinates."
    return (f"{name} | Use accurate, current 2026 facts for this crypto-licensing topic: the relevant "
            f"regulator, licence/registration type, capital, tax, timeline and allowed activities. "
            f"If unsure of a specific figure, give a hedged range and defer exact pricing to a consultation."
            f"{extra}")

def keyword_from(slug):
    return base_of(slug).replace("-", " ").strip() + " crypto license"

def next_unchecked(md_path, n):
    out = []
    for line in open(md_path, encoding="utf-8"):
        m = re.match(r"- \[ \] (.+)", line.strip())
        if m: out.append(m.group(1).strip())
        if len(out) >= n: break
    return out

def mark_done(md_path, needle):
    s = open(md_path, encoding="utf-8").read()
    s = s.replace(f"- [ ] {needle}", f"- [x] {needle}", 1)
    open(md_path, "w", encoding="utf-8").write(s)

MAX_ATTEMPTS = 3
_ATTEMPTS = os.path.join(ROOT, "logs", "gen_attempts.json")
def _attempts():
    import json
    try: return json.load(open(_ATTEMPTS))
    except Exception: return {}
def _bump(key):
    import json
    a = _attempts(); a[key] = a.get(key, 0) + 1
    os.makedirs(os.path.dirname(_ATTEMPTS), exist_ok=True)
    json.dump(a, open(_ATTEMPTS, "w")); return a[key]
def _fail_log(kind, ident, reason):
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    with open(os.path.join(ROOT, "logs", "failed_pages.log"), "a") as fh:
        fh.write(f"{datetime.date.today()} {kind} {ident} :: {reason}\n")

def slugify(title):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:70]

def run():
    sh("git pull --no-edit origin main")
    published = []
    CHUNK = int(os.environ.get("CHUNK", "5"))   # commit+push every CHUNK pages so a kill never loses progress

    def checkpoint(force=False):
        if not published: return
        if not force and len(published) % CHUNK != 0: return
        sh("python3 scripts/build_data_json.py")
        sh("python3 scripts/build_licensing_index.py")
        sh("python3 scripts/build_licensing_index_page.py")
        for _step in ("scripts/gen_blog_images.py", "scripts/blog_image_seo.py"):   # hero sets + page wiring
            _r = sh(f"python3 {_step}")
            if _r.returncode:                       # a post without its image set must not slip through silently
                print(f"WARNING: {_step} exit {_r.returncode}: {(_r.stdout + _r.stderr)[-300:]}")
        sh("python3 scripts/rebuild_indexes.py")
        sh("python3 scripts/publish.py")
        sh("git add -A")
        sh(f'git commit -q -m "Auto-publish checkpoint: {len(published)} pages ({datetime.date.today()})\n\nCo-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"')
        out = sh("git push origin main")
        print(f"checkpoint pushed at {len(published)} pages {out.stderr[-120:]}")

    # --- landing pages ---
    for entry in next_unchecked(os.path.join(ROOT, "pages.md"), N_LANDING):
        m = re.search(r"([a-z0-9-]+)\s*(?:→|->)\s*/([a-z0-9-]+)/", entry)
        slug = (m.group(2) if m else entry.split()[0]).strip("/")
        ok, reason = False, ""
        try:
            rep = gen.build("landing", slug, keyword_from(slug), landing_brief(slug))
            ok = bool(rep.get("pass")); reason = "" if ok else "QC fail"
            if ok: published.append("/"+slug+"/")
        except Exception as e:
            reason = f"exception: {e}"; print("landing err", slug, e)
        if ok:
            mark_done(os.path.join(ROOT, "pages.md"), entry)
        else:
            n = _bump("landing:"+slug); _fail_log("landing", slug, reason)
            if n >= MAX_ATTEMPTS:          # give up (don't block the queue forever), but LOUDLY
                mark_done(os.path.join(ROOT, "pages.md"), entry)
                _fail_log("landing", slug, f"GAVE UP after {n} attempts")
                print(f"WARNING: landing {slug} failed {n}x, giving up (see logs/failed_pages.log)")
        checkpoint()
    # --- blog posts ---
    _blog_queue = next_unchecked(os.path.join(ROOT, "blog", "topics.md"), N_BLOG)
    if not _blog_queue:
        print("WARNING: blog/topics.md is EXHAUSTED - 0 posts will publish. Refill the queue (quality over volume).")
    _blogger_slugs = set()
    for _f in ("config/blog_posted.json", "config/extra_posts.json"):
        try:
            _j = json.load(open(os.path.join(ROOT, _f)))
            _blogger_slugs |= set(_j.get("posts", {}).keys()) if isinstance(_j, dict) else {p.get("slug") for p in _j}
        except Exception:
            pass
    for title in _blog_queue:
        slug = slugify(title)
        _s80 = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80].rstrip("-")
        if slug in _blogger_slugs or _s80 in _blogger_slugs:
            print(f"skip blog '{title}': already published on blog.consulting24.co")
            mark_done(os.path.join(ROOT, "blog", "topics.md"), title)
            continue
        kw = " ".join(title.split()[:4])
        brief = f"{title} | Educational, accurate 2026 guidance for crypto founders. Internal-link to relevant jurisdiction pages and Panama. Consulting24 context."
        ok, reason = False, ""
        try:
            rep = gen.build("blog", slug, kw, brief)
            ok = bool(rep.get("pass")); reason = "" if ok else "QC fail"
            if ok: published.append("/blog/"+slug+"/")
        except Exception as e:
            reason = f"exception: {e}"; print("blog err", slug, e)
        if ok:
            mark_done(os.path.join(ROOT, "blog", "topics.md"), title)
        else:
            n = _bump("blog:"+slug); _fail_log("blog", slug, reason)
            if n >= MAX_ATTEMPTS:
                mark_done(os.path.join(ROOT, "blog", "topics.md"), title)
                _fail_log("blog", slug, f"GAVE UP after {n} attempts")
                print(f"WARNING: blog {slug} failed {n}x, giving up (see logs/failed_pages.log)")
        checkpoint()
    _lc = sh("python3 scripts/linkcheck.py"); print(_lc.stdout[-400:])
    _mb = re.search(r"BROKEN internal links:\s*([1-9]\d*)", _lc.stdout)
    if _mb: print(f"WARNING: linkcheck found {_mb.group(1)} broken internal links (fix before they compound)")
    checkpoint(force=True)   # final flush of the remainder
    # indexing watchdog: re-submit / audit pages not indexed within a few days
    print(sh("python3 scripts/index_monitor.py").stdout[-600:])
    sh("git add config/index_status.json")
    sh(f'git commit -q -m "index_monitor: indexing status checkpoint ({datetime.date.today()})"')
    sh("git push origin main")
    print(f"DONE: published {len(published)} pages")

if __name__ == "__main__":
    run()
