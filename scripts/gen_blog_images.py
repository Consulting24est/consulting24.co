#!/usr/bin/env python3
"""
gen_blog_images.py — one UNIQUE, branded, SEO-ready hero image SET per blog post.

Covers BOTH the site's /blog/<slug>/ posts and the Blogger posts/pages (config/blog_posted.json +
the queued config/extra_posts.json). For every slug it writes, under img/blog/:

  <slug>.jpg          1200x675  (16:9)  og:image, twitter:image, on-page hero, Article image #1
  <slug>.webp         1200x675          WebP twin for <picture>
  <slug>-4x3.jpg      1200x900  (4:3)   Article image #2  (Google Article rich results want 16x9, 4x3, 1x1)
  <slug>-1x1.jpg      1200x1200 (1:1)   Article image #3
  <slug>-thumb.jpg    600x338           blog index card
  <slug>-thumb.webp   600x338

Composition (deterministic per slug, hash-seeded):
  base photo (img/gallery-*.jpg Panama scenes or img/photo-*.jpg founder/team photos, cover-cropped
  around a per-photo focal point with a little zoom/offset jitter)
  + brand gradient panel (navy, tinted by a per-jurisdiction / per-category hue)
  + category eyebrow with icon + the post TITLE + jurisdiction FLAG chip(s)
  + fact chips (regulator / timeline / cost from data/jurisdictions.json)
  + Consulting24 wordmark.
Flags and icons are img/flags/*.png (Apple Color Emoji rendered once via scripts/emoji_render.swift).

Why: 332 www posts shared one og:image and the index cycled 9 stock photos (Sept 2026). Unique,
descriptive images per URL help Google Images / Discover, social previews and multimodal LLM crawlers.

Idempotent: regenerates only slugs whose set is incomplete unless --force.
Usage:
  python3 scripts/gen_blog_images.py                    # missing/incomplete sets only
  python3 scripts/gen_blog_images.py --force            # regenerate everything
  python3 scripts/gen_blog_images.py --only SLUG ...    # specific slugs (implies --force)
  python3 scripts/gen_blog_images.py --preview DIR SLUG ...   # 16:9 + 1:1 to DIR, repo untouched
  python3 scripts/gen_blog_images.py --list             # print slug | category | jurisdictions
"""
from __future__ import annotations
import argparse, colorsys, glob, hashlib, html, json, os, pathlib, random, re, sys
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "config" / "blog_posted.json"
EXTRA = ROOT / "config" / "extra_posts.json"
JURIS = ROOT / "data" / "jurisdictions.json"
OUTDIR = ROOT / "img" / "blog"
FLAGDIR = ROOT / "img" / "flags"
SITE = "https://www.consulting24.co"

SIZES = {"16x9": (1200, 675), "4x3": (1200, 900), "1x1": (1200, 1200)}
THUMB = (600, 338)

_FONT = "/System/Library/Fonts/Avenir Next.ttc"          # 0 Bold, 2 Demi Bold, 5 Medium
_FONT_FALLBACK = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

# ── base photo pool: (file, focal_x, focal_y, preferred layout, kind, scope) ─────────────────
#    scope: "panama" = recognisably Panama (canal locks) -> only for Panama / no-jurisdiction posts;
#           "generic" = skyline / port scenes usable for any jurisdiction; "people" = founder / team.
PHOTOS = [
    ("gallery-01.jpg", 0.50, 0.50, "any", "place", "generic"),   # Panama City skyline at night
    ("gallery-02.jpg", 0.60, 0.40, "any", "place", "generic"),   # towers through glass
    ("gallery-03.jpg", 0.50, 0.50, "any", "place", "generic"),   # aerial city
    ("gallery-04.jpg", 0.55, 0.50, "any", "place", "generic"),   # bay and towers
    ("gallery-05.jpg", 0.55, 0.50, "any", "place", "panama"),    # canal lock building
    ("gallery-06.jpg", 0.50, 0.50, "any", "place", "panama"),    # canal locks
    ("gallery-07.jpg", 0.50, 0.50, "any", "place", "panama"),    # bridge over locks
    ("gallery-08.jpg", 0.50, 0.50, "any", "place", "generic"),   # container ship
    # (gallery-09, a stock model at a desk, and the two-person selfie are deliberately NOT in the pool:
    #  faces ended up cropped or under the text panel in QA, and neither is on-brand for a founder-led firm)
    # focal = the founder's face (x, y as a fraction of the frame); "left" layouts auto-zoom so it clears the panel
    ("photo-mardo-soo-desk.jpg", 0.43, 0.36, "left", "people", "people"),
    ("photo-mardo-soo-office.jpg", 0.45, 0.36, "left", "people", "people"),
    ("photo-mardo-soo-laptop-1.jpg", 0.52, 0.40, "left", "people", "people"),
    ("photo-mardo-soo-laptop-2.jpg", 0.49, 0.32, "left", "people", "people"),
    ("photo-consulting24-conference.jpg", 0.50, 0.30, "bottom", "people", "people"),
]
RENDER_VERSION = 3          # bump when PHOTOS / CATS / JMAP / layout change: sets re-render without --force
MANIFEST = OUTDIR / ".manifest.json"

# ── jurisdictions: slug token -> (ISO code, display name, data/jurisdictions.json slug) ───────
JMAP = {
    "panama": ("PA", "Panama", "panama"), "estonia": ("EE", "Estonia", "estonia"),
    "lithuania": ("LT", "Lithuania", "lithuania"), "dubai": ("AE", "Dubai", "dubai"),
    "abu-dhabi": ("AE", "Abu Dhabi", "abu-dhabi"), "uae": ("AE", "UAE", "dubai"),
    "cyprus": ("CY", "Cyprus", "cyprus"), "malta": ("MT", "Malta", "malta"),
    "poland": ("PL", "Poland", "poland"), "czech": ("CZ", "Czech Republic", "czech-republic"),
    "switzerland": ("CH", "Switzerland", "switzerland"), "cayman": ("KY", "Cayman Islands", "cayman-islands"),
    "bvi": ("VG", "BVI", "bvi"), "british-virgin": ("VG", "BVI", "bvi"),
    "bahamas": ("BS", "Bahamas", "bahamas"), "bahrain": ("BH", "Bahrain", None),
    "canada": ("CA", "Canada", "canada"), "singapore": ("SG", "Singapore", "singapore"),
    "hong-kong": ("HK", "Hong Kong", "hong-kong"), "el-salvador": ("SV", "El Salvador", "el-salvador"),
    "georgia": ("GE", "Georgia", "georgia"), "germany": ("DE", "Germany", None),
    "ireland": ("IE", "Ireland", None), "kazakhstan": ("KZ", "Kazakhstan", None),
    "liechtenstein": ("LI", "Liechtenstein", None), "portugal": ("PT", "Portugal", None),
    "seychelles": ("SC", "Seychelles", "seychelles"), "mauritius": ("MU", "Mauritius", "mauritius"),
    "gibraltar": ("GI", "Gibraltar", "gibraltar"), "costa-rica": ("CR", "Costa Rica", "costa-rica"),
    "slovakia": ("SK", "Slovakia", None), "labuan": ("MY", "Labuan", None), "malaysia": ("MY", "Malaysia", None),
    "isle-of-man": ("IM", "Isle of Man", None), "japan": ("JP", "Japan", None),
    "south-korea": ("KR", "South Korea", None), "south-africa": ("ZA", "South Africa", None),
    "qatar": ("QA", "Qatar", None), "saudi": ("SA", "Saudi Arabia", None), "turkey": ("TR", "Turkey", None),
    "vietnam": ("VN", "Vietnam", None), "usa": ("US", "USA", None), "united-states": ("US", "USA", None),
    "uk": ("GB", "UK", None), "united-kingdom": ("GB", "UK", None), "bulgaria": ("BG", "Bulgaria", None),
    "romania": ("RO", "Romania", None), "luxembourg": ("LU", "Luxembourg", None), "jersey": ("JE", "Jersey", None),
    "saint-lucia": ("LC", "Saint Lucia", None), "st-lucia": ("LC", "Saint Lucia", None),
    "philippines": ("PH", "Philippines", None), "indonesia": ("ID", "Indonesia", None),
    "thailand": ("TH", "Thailand", None), "marshall": ("MH", "Marshall Islands", None),
    "belize": ("BZ", "Belize", None), "anjouan": ("KM", "Anjouan", None), "bermuda": ("BM", "Bermuda", None),
    "vanuatu": ("VU", "Vanuatu", None), "france": ("FR", "France", None), "spain": ("ES", "Spain", None),
    "italy": ("IT", "Italy", None), "netherlands": ("NL", "Netherlands", None), "latvia": ("LV", "Latvia", None),
    "hungary": ("HU", "Hungary", None), "greece": ("GR", "Greece", None), "croatia": ("HR", "Croatia", None),
    "austria": ("AT", "Austria", None), "india": ("IN", "India", None), "australia": ("AU", "Australia", None),
    "mica": ("EU", "EU / MiCA", None), "casp": ("EU", "EU / MiCA", None), "european-union": ("EU", "EU", None),
}
_JKEYS = sorted(JMAP, key=len, reverse=True)     # longest token first ("abu-dhabi" before "uae")
EU = {"EE", "LT", "PL", "CZ", "MT", "CY", "IE", "PT", "DE", "FR", "ES", "IT", "NL", "SK", "RO", "BG", "LI",
      "LV", "HU", "GR", "HR", "AT", "SE", "DK", "FI", "BE", "LU", "EU"}
# pleasant, distinct accent hue per jurisdiction (degrees); others hash to a hue
HUE = {"PA": 212, "EE": 198, "LT": 44, "CH": 4, "MT": 348, "CY": 28, "PL": 354, "CZ": 216, "KY": 192,
       "VG": 152, "SG": 356, "AE": 132, "SV": 222, "GE": 350, "IE": 142, "PT": 120, "SC": 186, "MU": 24,
       "BH": 355, "LI": 224, "ZA": 138, "NL": 20, "RO": 50, "KZ": 184, "FR": 226, "DE": 46, "BG": 130,
       "ES": 40, "IT": 128, "SK": 214, "EU": 220, "CA": 2, "HK": 349, "CR": 214, "BS": 178, "GB": 230,
       "US": 220, "JP": 350, "KR": 210, "QA": 340, "SA": 140, "TR": 0, "VN": 8, "LU": 200, "JE": 8}
REG_SHORT = {"canada": "FINTRAC (MSB)", "dubai": "VARA", "abu-dhabi": "ADGM FSRA", "georgia": "NBG",
             "czech-republic": "CNB", "bahamas": "SCB", "costa-rica": None, "panama": None}

# ── categories: (key, regex on slug+title, eyebrow label, icon file, hue, photo kind bias, chip text) ──
#    Most specific first: a "substance requirements" post is SUBSTANCE, not CHECKLIST.
#    Matched against "<slug> <title-as-slug>", so \b boundaries sit at hyphens ("costa-rica" must not match "cost").
CATS = [
    ("vs",          r"-vs-|\bvs\b|\bversus\b|which-(should-you|to)-choose|\bcompares?-(to|with)\b|\bcompared\b", "JURISDICTION COMPARISON", "icon-vs", 265, "place", "Side-by-side comparison"),
    ("ubo",         r"beneficial-ownership|\bubo\b", "BENEFICIAL OWNERSHIP & KYC", "icon-ubo", 205, "people", "UBO & KYC guide"),
    ("aml",         r"\baml\b|\bkyc\b|travel-rule|transaction-monitoring|compliance-program|compliance-officer", "AML / KYC COMPLIANCE", "icon-aml", 200, "people", "AML & KYC guide"),
    ("substance",   r"\bsubstance\b|\bdirectors?\b|\bmlro\b|office-requirement", "SUBSTANCE & GOVERNANCE", "icon-substance", 205, "people", "Substance guide"),
    ("migrate",     r"\bmigrat|moving-an|\brelocat", "RELOCATING A CRYPTO BUSINESS", "icon-migrate", 30, "place", "Migration checklist"),
    ("maintenance", r"\bannual\b|\bmaintenance\b|\brenewals?\b", "ANNUAL MAINTENANCE", "icon-maintenance", 60, "people", "Ongoing obligations"),
    ("regulator",   r"regulators-assess|how-regulators", "HOW REGULATORS ASSESS", "icon-regulator", 210, "people", "Regulator's view"),
    ("token",       r"\btokens?\b|\btokenomics\b|\bstablecoins?\b|\bico\b|\bieo\b|white-paper", "TOKENS & STABLECOINS", "icon-token", 285, "place", "Token guide"),
    ("fund",        r"\bfunds?\b", "CRYPTO FUNDS", "icon-fund", 170, "place", "Fund structuring"),
    ("nft",         r"\bnfts?\b", "NFT MARKETPLACES", "icon-nft", 300, "place", "NFT licensing"),
    ("otc",         r"\botc\b|\bcustody\b", "OTC & CUSTODY", "icon-otc", 190, "people", "OTC & custody guide"),
    ("bank",        r"\bbank|\bemi\b|\bpayments?\b|\bibans?\b|debit-cards?|\bsettlement\b|\brails\b", "BANKING & PAYMENTS", "icon-bank", 215, "people", "Banking guide"),
    ("tax",         r"\btax(es|ation)?\b|\bterritorial\b", "CRYPTO TAX GUIDE", "icon-tax", 25, "place", "Tax guide"),
    ("mistakes",    r"\bmistakes?\b|\bdelayed\b|\brejected\b|\bpitfalls?\b", "COMMON MISTAKES TO AVOID", "icon-mistakes", 15, "people", "Mistakes to avoid"),
    ("timeline",    r"how-long|\btimelines?\b|\bfastest\b|\beasiest\b", "LICENSING TIMELINE", "icon-timeline", 55, "place", "Timelines by jurisdiction"),
    ("checklist",   r"\bchecklists?\b|\brequirements?\b", "REQUIREMENTS CHECKLIST · 2026", "icon-checklist", 150, "place", "Requirements checklist"),
    ("cost",        r"\bcosts?\b|\bprices?\b|\bpricing\b|\bfees?\b|\bquotes?\b|\bbudget\b|\bcheapest\b|how-much", "COST BREAKDOWN · 2026", "icon-cost", 40, "place", "Cost breakdown"),
    ("decision",    r"\bdecision\b|do-you-need|\bchoosing\b|direct-delivery|\broadmap\b", "DECISION GUIDE", "icon-decision", 160, "people", "Decision guide"),
    ("howto",       r"how-to|step-by-step|\bapply(ing)?\b|\bapplications?\b|\bsetup\b|set-up", "STEP-BY-STEP GUIDE", "icon-howto", 175, "people", "Step-by-step guide"),
    ("panama",      r"\bpanama\b", "PANAMA CRYPTO COMPANY", "flag-pa", 212, "place", "Panama company guide"),
]
CAT_DEFAULT = ("guide", r".", "CRYPTO LICENCE GUIDE", "icon-guide", 210, "people", "Licensing guide")
CAT_INDEX = ("index", r"^$", "CONSULTING24 BLOG", "icon-guide", 212, "people", "500+ licences since 2018")


# ═══════════════════════════════════════ metadata ═══════════════════════════════════════════
def hkey(s: str) -> int:
    return int(hashlib.md5(s.encode()).hexdigest(), 16)


_ACRONYMS = {"AML", "KYC", "OTC", "NFT", "UBO", "EU", "MICA", "CASP", "VASP", "VARA", "MSB", "ADGM", "FSRA", "&", "/"}


def nice_label(label: str) -> str:
    """'AML / KYC COMPLIANCE' -> 'AML / KYC compliance' (acronyms kept, the rest sentence-cased)."""
    words = []
    for i, w in enumerate(label.split()):
        if w.upper() in _ACRONYMS:
            words.append("MiCA" if w.upper() == "MICA" else w.upper())
        else:
            words.append(w.capitalize() if i == 0 else w.lower())
    return " ".join(words)


@lru_cache(maxsize=None)
def _juris_data() -> dict:
    try:
        return {j["slug"]: j for j in json.loads(JURIS.read_text())["jurisdictions"]}
    except Exception:
        return {}


def jurisdictions_of(slug: str) -> list[tuple[str, str, str | None]]:
    """[(ISO, name, data-slug)] in slug order; both sides of a '-vs-' are detected."""
    found = []
    s = "-" + slug.lower() + "-"
    for key in _JKEYS:
        m = re.search(r"-" + re.escape(key) + r"-", s)
        if m:
            found.append((m.start(), JMAP[key]))
            s = s[:m.start()] + "-" + "#" * (len(key)) + "-" + s[m.end():]   # blank out, keep positions
    out, seen = [], set()
    for _, j in sorted(found):
        if j[0] not in seen:                      # dedupe on ISO: "dubai-uae-…" is one flag, not two
            seen.add(j[0]); out.append(j)
    if any(j[0] != "EU" for j in out):            # "mica"/"casp" only count as a jurisdiction on their own
        out = [j for j in out if j[0] != "EU"]
    return out[:2]


_SUBTOPICS = ("cost", "checklist", "timeline", "tax", "bank")
_CAT_BY_KEY = {c[0]: c for c in CATS}


def category_of(slug: str, title: str, njur: int = 0) -> tuple:
    if slug == "blog-index":
        return CAT_INDEX
    text = slug.lower() + " " + re.sub(r"[^a-z0-9]+", "-", title.lower())
    # "<X> Crypto License 2026: Cost, Requirements and Timeline" is an overview guide, not a timeline post
    if re.search(r"-(2026-)?guide$", slug) or \
            sum(bool(re.search(_CAT_BY_KEY[k][1], text)) for k in _SUBTOPICS) >= 2:
        if not any(re.search(_CAT_BY_KEY[k][1], text) for k in ("vs", "aml", "ubo", "mistakes")):
            return CAT_DEFAULT
    for cat in CATS:
        if not re.search(cat[1], text):
            continue
        # "fixed fee vs variable cost" is not a JURISDICTION comparison: 'vs' needs two jurisdictions or comparison wording
        if cat[0] == "vs" and njur < 2 and not re.search(r"which-(should-you|to)-choose|compar|jurisdiction", text):
            continue
        return cat
    return CAT_DEFAULT


def _fact_chips(jur: list, is_vs: bool = False) -> list[tuple[str | None, str]]:
    """Up to 3 chips: (icon-file or None, text)."""
    chips = []
    data = _juris_data()
    for iso, name, dslug in jur:
        chips.append((f"flag-{iso.lower()}", name))
    if len(jur) == 1:
        iso, name, dslug = jur[0]
        if dslug == "panama":
            chips += [(None, "EUR 6,000 flat"), (None, "2-3 weeks · 0% foreign-source tax")]
        elif dslug and dslug in data:
            j = data[dslug]
            reg = REG_SHORT.get(dslug, j.get("regulator"))
            if reg and len(reg) <= 22:
                chips.append((None, f"Regulator: {reg}"))
            if j.get("timeline"):
                chips.append((None, f"Timeline: {j['timeline']}"))
        elif iso in EU:
            chips.append((None, "MiCA CASP regime · EU passport"))
    elif len(jur) == 2:
        chips.append((None, "Side-by-side · 2026" if is_vs else "Consulting24 guide · 2026"))
    return chips[:3]


def post_meta(slug: str, title: str) -> dict:
    """Everything the image + the on-page markup need for one post (also used by blog_image_seo.py)."""
    jur = jurisdictions_of(slug)
    title_jur = jurisdictions_of(re.sub(r"[^a-z0-9]+", "-", title.lower()))
    if not jur:                                   # Blogger slugs like "vara-license-guide": read the title
        jur = title_jur
    cat = category_of(slug, title, max(len(jur), len(title_jur)))
    if cat[0] == "vs" and len(jur) < 2:           # "…: how it compares to Panama" -> both flags
        jur = (jur + [j for j in title_jur if j not in jur])[:2]
    key, _, label, icon, chue, kind, chip_text = cat
    if key == "index":
        jur = []
    if key == "panama" and not (jur and jur[0][0] == "PA"):
        # "…: how it compares to Panama" on an Abu Dhabi guide is NOT a Panama post: plain guide eyebrow
        key, _, label, icon, chue, kind, chip_text = CAT_DEFAULT
    hue = HUE.get(jur[0][0], hkey("hue" + jur[0][0]) % 360) if jur else chue
    chips = _fact_chips(jur, key == "vs") or [(icon, chip_text), (None, "Consulting24 guide · 2026")]
    if key == "index":
        chips = [("flag-pa", "Panama"), ("flag-ee", "Estonia"), ("flag-lt", "Lithuania"), (None, chip_text)]
    names = [{"AE": "UAE", "EU": "EU"}.get(j[0], j[1]) for j in jur]     # the chip shows the UAE flag for Dubai
    flags_desc = ("the " + " and ".join(names) + (" flags" if len(names) > 1 else " flag")) if names else ""
    generic = {"Consulting24 guide · 2026"}
    facts = [c[1] for c in chips if c[0] is None and c[1] not in generic]
    nice = nice_label(label.split(" ·")[0])
    # alt describes what is IN the picture (title text, flag, facts); caption lists the facts for readers + LLMs
    facts_desc = ", ".join(re.sub(r"^(Regulator|Timeline): ", lambda m: m.group(1).lower() + " ", f) for f in facts[:2]) if facts and jur else ""
    parts = [x for x in (flags_desc, facts_desc) if x]
    alt = f"{title.rstrip('?.!: ')}: cover image" + (" with " + " and ".join(parts) if parts else "") + f" ({nice}, Consulting24)"
    cap_parts = [c[1] for c in chips if c[1] not in generic] + [nice, "Consulting24, 2026"]
    seen_cap, cap = set(), []
    for p in cap_parts:
        if p.lower() not in seen_cap:
            seen_cap.add(p.lower()); cap.append(p)
    caption = " · ".join(cap)
    return {"slug": slug, "title": title, "category": key, "label": label, "icon": icon, "hue": hue,
            "jurisdictions": jur, "chips": chips, "photo_kind": kind, "alt": alt, "caption": caption}


# ═══════════════════════════════════════ items ══════════════════════════════════════════════
def _h1(path: pathlib.Path) -> str:
    h = path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"<h1[^>]*>(.*?)</h1>", h, re.S)
    return html.unescape(re.sub("<[^>]+>", "", m.group(1))).strip() if m else ""


def site_posts() -> dict[str, str]:
    out = {}
    for p in sorted((ROOT / "blog").glob("*/index.html")):
        head = p.read_text(encoding="utf-8", errors="ignore")[:1500]
        if "generated-redirect-stub" in head or 'content="noindex"' in head:
            continue
        t = _h1(p)
        if t:
            out[p.parent.name] = t
    return out


def blogger_items() -> dict[str, str]:
    out = {}
    if STATE.exists():
        try:                                      # one bad Blogger record must not block the site's own posts
            st = json.loads(STATE.read_text())
            for kind in ("posts", "pages"):
                for slug, m in (st.get(kind) or {}).items():
                    if isinstance(m, dict) and m.get("title"):
                        out[slug] = m["title"]
        except Exception as e:                    # noqa: BLE001
            print(f"WARNING: {STATE.name} unreadable ({e}); Blogger items skipped this run")
    if EXTRA.exists():
        try:
            for p in json.loads(EXTRA.read_text()):
                if isinstance(p, dict) and p.get("slug") and p.get("title"):
                    out.setdefault(p["slug"], p["title"])
        except Exception:
            pass
    return out


def all_items() -> dict[str, tuple[str, bool]]:
    """slug -> (title, full). full=True (site posts + index) also gets the 4:3 and 1:1 Article-schema
    variants; Blogger-only slugs get the 16:9 master, WebP twin and card thumbs (keeps the repo lean)."""
    items = {s: (t, False) for s, t in blogger_items().items()}
    items.update({s: (t, True) for s, t in site_posts().items()})          # the site's own H1 wins
    items["blog-index"] = ("Crypto Licensing Blog: Costs, Requirements, Tax, Banking and Compliance Guides", True)
    return items


def outputs_for(slug: str, full: bool = True) -> dict[str, pathlib.Path]:
    b = OUTDIR / slug
    out = {"16x9": b.with_suffix(".jpg"), "webp": b.with_suffix(".webp"),
           "thumb": OUTDIR / f"{slug}-thumb.jpg", "thumbwebp": OUTDIR / f"{slug}-thumb.webp"}
    if full:
        out.update({"4x3": OUTDIR / f"{slug}-4x3.jpg", "1x1": OUTDIR / f"{slug}-1x1.jpg"})
    return out


# ═══════════════════════════════════════ drawing ════════════════════════════════════════════
@lru_cache(maxsize=64)
def font(size: int, weight: str = "bold") -> ImageFont.FreeTypeFont:
    idx = {"bold": 0, "demi": 2, "medium": 5}[weight]
    try:
        return ImageFont.truetype(_FONT, size, index=idx)
    except Exception:
        return ImageFont.truetype(_FONT_FALLBACK, size)


@lru_cache(maxsize=32)
def photo(name: str) -> Image.Image:
    im = Image.open(ROOT / "img" / name)
    im = ImageOps.exif_transpose(im).convert("RGB")
    if im.width > 1800:
        im = im.resize((1800, round(im.height * 1800 / im.width)), Image.LANCZOS)
    return im


@lru_cache(maxsize=256)
def icon(name: str, height: int) -> Image.Image | None:
    p = FLAGDIR / f"{name}.png"
    if not p.exists():
        return None
    im = Image.open(p).convert("RGBA")
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    return im.resize((max(1, round(im.width * height / im.height)), height), Image.LANCZOS)


def hsv(h: float, s: float, v: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb((h % 360) / 360.0, s, v)
    return (round(r * 255), round(g * 255), round(b * 255))


def cover_crop(im: Image.Image, W: int, H: int, fx: float, fy: float, tx: float, ty: float, zoom: float) -> Image.Image:
    """Scale to cover WxH (times zoom) and place so the focal point (fx,fy) of the photo lands at (tx,ty).
    Upscaled photos (the gallery scenes are only ~940px wide) get a light unsharp mask."""
    pw, ph = im.size
    scale = max(W / pw, H / ph) * zoom
    sw, sh = round(pw * scale), round(ph * scale)
    im = im.resize((sw, sh), Image.LANCZOS)
    ox = min(max(round(fx * sw - tx * W), 0), sw - W)
    oy = min(max(round(fy * sh - ty * H), 0), sh - H)
    out = im.crop((ox, oy, ox + W, oy + H))
    if scale > 1.15:
        out = out.filter(ImageFilter.UnsharpMask(radius=1.2, percent=55, threshold=2))
    return out


def gradient_mask(W: int, H: int, stops: list[tuple[float, float]], axis: str) -> Image.Image:
    """1-D piecewise-linear alpha ramp (position 0..1 -> alpha 0..1) stretched over the canvas."""
    n = W if axis == "x" else H
    strip = Image.new("L", (n, 1) if axis == "x" else (1, n))
    px = strip.load()
    for i in range(n):
        t = i / (n - 1)
        a = stops[-1][1]
        for (p0, a0), (p1, a1) in zip(stops, stops[1:]):
            if p0 <= t <= p1:
                a = a0 + (a1 - a0) * ((t - p0) / (p1 - p0) if p1 > p0 else 0)
                break
        if t < stops[0][0]:
            a = stops[0][1]
        if axis == "x":
            px[i, 0] = round(a * 255)
        else:
            px[0, i] = round(a * 255)
    return strip.resize((W, H))


def wrap(text: str, f: ImageFont.FreeTypeFont, maxw: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if f.getlength(cand) <= maxw or not cur:
            cur = cand
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_title(title: str, maxw: int, maxh: int, sizes: tuple[int, ...]) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """Largest size whose wrapped lines fit maxw x maxh; last resort: smallest size, lines cut with an ellipsis."""
    for s in sizes:
        f = font(s, "bold")
        lines = wrap(title, f, maxw)
        lh = round(s * 1.14)
        if len(lines) * lh <= maxh and all(f.getlength(l) <= maxw for l in lines):
            return f, lines, lh
    s = sizes[-1]; f = font(s, "bold"); lh = round(s * 1.14)
    lines = wrap(title, f, maxw)[: max(1, maxh // lh)]
    if lines and f.getlength(lines[-1] + "…") > maxw:
        lines[-1] = lines[-1].rsplit(" ", 1)[0]
    lines[-1] = lines[-1].rstrip(",:;") + "…"
    return f, lines, lh


def draw_chip(base: Image.Image, x: int, y: int, ic: Image.Image | None, text: str, f: ImageFont.FreeTypeFont,
              accent: tuple[int, int, int], h: int = 50) -> int:
    """Rounded translucent chip with optional icon; returns its width."""
    pad = 18
    tw = round(f.getlength(text))
    iw = (ic.width + 12) if ic is not None else 0
    w = pad * 2 + iw + tw
    ov = Image.new("RGBA", (w + 4, h + 4), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.rounded_rectangle([1, 1, w + 1, h + 1], radius=h // 2, fill=(255, 255, 255, 34),
                         outline=(accent[0], accent[1], accent[2], 150), width=2)
    base.alpha_composite(ov, (x - 2, y - 2))
    cx = x + pad
    if ic is not None:
        base.alpha_composite(ic, (cx, y + (h - ic.height) // 2))
        cx += ic.width + 12
    d = ImageDraw.Draw(base)
    d.text((cx, y + (h - f.size) // 2 - 3), text, font=f, fill=(245, 248, 255, 255))
    return w


def draw_wordmark(base: Image.Image, x: int, y: int, size: int = 26) -> None:
    d = ImageDraw.Draw(base)
    s = round(size * 1.15)
    d.rounded_rectangle([x, y, x + s, y + s], radius=round(s * 0.24), fill=(17, 109, 255, 255))
    r = round(s * 0.30)
    cx, cy = x + s / 2, y + s / 2
    d.arc([cx - r, cy - r, cx + r, cy + r], start=35, end=325, fill=(255, 255, 255, 255), width=max(3, round(s * 0.13)))
    f = font(size, "demi")
    d.text((x + s + 12, y + (s - size) // 2 - 3), "consulting24.co", font=f, fill=(226, 234, 250, 255))


def compose(meta: dict, W: int, H: int, variant: str) -> Image.Image:
    slug, title = meta["slug"], meta["title"]
    rng = random.Random(hkey(slug + "|" + variant))
    hue = meta["hue"]
    accent = hsv(hue, 0.70, 0.98)
    panel = tuple(round(0.72 * a + 0.28 * b) for a, b in zip((10, 21, 42), hsv(hue, 0.55, 0.32)))

    # ── base photo: chosen with a SLUG-ONLY seed so the 16:9, 4:3 and 1:1 variants share one photo ──
    prng = random.Random(hkey("photo|" + slug))
    is_pa = meta["category"] == "panama" or (meta["jurisdictions"] and meta["jurisdictions"][0][0] == "PA")
    pool = PHOTOS
    if meta["jurisdictions"] and not is_pa:       # an Abu Dhabi guide should not sit on the Panama Canal locks
        pool = [p for p in pool if p[5] != "panama"]
    if meta["category"] == "index":
        cand = [p for p in pool if p[0] == "photo-mardo-soo-office.jpg"]
    elif is_pa:
        prefer = [p for p in pool if p[4] == "place"]
        cand = prefer if prng.random() < 0.85 else pool
    else:
        prefer = [p for p in pool if p[4] == meta["photo_kind"]]
        cand = prefer if prng.random() < 0.65 else pool
    # rendezvous hashing: adding/removing a photo later only re-rolls the slugs that used it
    pf, fx, fy, pref_layout, pkind, _scope = min(cand, key=lambda p: hkey(f"photo|{slug}|{p[0]}"))
    group = pf == "photo-consulting24-conference.jpg"
    if group and variant == "1x1":                # six people do not fit a square crop: single portrait instead
        pf, fx, fy = "photo-mardo-soo-office.jpg", 0.45, 0.36
        group = False
    layout = "bottom" if variant != "16x9" else (pref_layout if pref_layout != "any" else rng.choice(["left", "bottom", "left"]))
    zoom = 1.0 + rng.random() * 0.22
    src = photo(pf)

    def needed_zoom(tx: float, ty: float, Wc: int, Hc: int) -> float:
        """Smallest zoom that lets the focal point actually reach (tx,ty) on a Wc x Hc canvas."""
        pw, ph = src.size
        s0 = max(Wc / pw, Hc / ph)
        need = 1.0
        if fx < tx:   need = max(need, (tx / fx) * Wc / (pw * s0))
        if fx > tx:   need = max(need, ((1 - tx) / (1 - fx)) * Wc / (pw * s0))
        if fy < ty:   need = max(need, (ty / fy) * Hc / (ph * s0))
        if fy > ty:   need = max(need, ((1 - ty) / (1 - fy)) * Hc / (ph * s0))
        return need

    if layout == "left":
        tx, ty = 0.76 + (rng.random() - 0.5) * 0.05, 0.50 + (rng.random() - 0.5) * 0.06
        zoom = max(zoom, min(needed_zoom(tx, ty, W, H), 1.75))
        if needed_zoom(tx, ty, W, H) > 1.75:           # subject too central to clear the panel: use bottom layout
            layout = "bottom"
    if layout == "left":
        img = cover_crop(src, W, H, fx, fy, tx, ty, zoom)
        split = None
    else:
        split = {"16x9": 0.48, "4x3": 0.50, "1x1": 0.52}[variant]
        # Only the band above the panel is visible, so the photo covers just that band: the ~940px gallery
        # scenes are then upscaled ~1.3x for a square instead of ~2.3x (QA: soft 4:3 / 1:1 variants).
        Hv = round(H * (split + 0.10))
        # faces must sit fully above the dark panel: people photos land around 27% of the canvas height
        ty0 = (0.27 if pkind == "people" else 0.40) if variant == "16x9" else (0.28 if pkind == "people" else 0.30)
        tx = 0.50 + (rng.random() - 0.5) * 0.10
        ty = (ty0 + (rng.random() - 0.5) * (0.02 if pkind == "people" else 0.05)) * H / Hv
        zoom = max(1.0 + rng.random() * (0.06 if pkind == "people" else 0.12), min(needed_zoom(tx, ty, W, Hv), 1.35))
        if group and variant == "4x3":            # 4:3 photo: show all six people, no jitter, no zoom
            tx, ty, zoom = 0.50, fy, 1.0
        band = cover_crop(src, W, Hv, fx, fy, tx, ty, zoom)
        img = Image.new("RGB", (W, H), panel)
        img.paste(band, (0, 0))

    # ── tint + panel gradient (people photos stay brighter: the founder must be recognisable) ──
    img = Image.blend(img, Image.new("RGB", (W, H), panel), 0.08 if pkind == "people" else 0.14)
    if layout == "left":
        mask = gradient_mask(W, H, [(0.0, 0.97), (0.40, 0.95), (0.56, 0.62), (0.70, 0.10), (1.0, 0.06)], "x")
    else:
        # short ramp: the photo stays clear until ~11% above the panel so chins are not dimmed
        mask = gradient_mask(W, H, [(0.0, 0.04), (split - 0.11, 0.10), (split, 0.90), (0.72, 0.96), (1.0, 0.98)], "y")
    img = Image.composite(Image.new("RGB", (W, H), panel), img, mask)
    base = img.convert("RGBA")

    # decorative ring (position/size hash-varied) for depth
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); od = ImageDraw.Draw(ov)
    rr = rng.randint(180, 340)
    if layout == "left":
        cx, cy = rng.randint(-60, 160), rng.randint(H - 200, H + 80)
    else:
        cx, cy = rng.randint(W - 260, W + 60), rng.randint(round(H * 0.55), H + 60)
    od.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(accent[0], accent[1], accent[2], 46), width=3)
    base.alpha_composite(ov)

    # ── text geometry ────────────────────────────────────────────────────────────────────────
    M = 72
    if layout == "left":
        x0, textw = M, round(W * 0.58) - M
        top = 66
        title_sizes = (62, 56, 50, 46, 42, 38, 34)
    else:
        x0, textw = M, W - 2 * M
        top = round(H * {"16x9": 0.49, "4x3": 0.52, "1x1": 0.54}[variant]) + 8
        title_sizes = {"16x9": (58, 52, 47, 42, 38, 34), "4x3": (62, 56, 50, 46, 42, 38), "1x1": (66, 60, 54, 48, 44, 40)}[variant]
    chip_h = 50

    # chips are laid out into rows FIRST (first chip top-left) so the title is fitted to the space that is
    # actually left above them (QA: five-line titles used to run into the chip row when chips wrapped)
    cf = font(23, "demi")
    rows, row, cx = [], [], 0
    for ic_name, text in meta["chips"]:
        ci = icon(ic_name, 32) if ic_name else None
        w = 36 + (ci.width + 12 if ci is not None else 0) + round(cf.getlength(text))
        if row and cx + w > textw:
            rows.append(row); row, cx = [], 0
        row.append((ci, text, w)); cx += w + 12
    if row:
        rows.append(row)
    chips_h = len(rows) * chip_h + (len(rows) - 1) * 12
    chips_top = H - 62 - 20 - chips_h                  # wordmark row is the last 62px
    bottom_reserved = (H - chips_top) + 52             # + accent underline and breathing room
    d = ImageDraw.Draw(base)

    # eyebrow
    ef = font(24, "demi")
    ic = icon(meta["icon"], 30)
    ex = x0
    if ic is not None:
        base.alpha_composite(ic, (ex, top - 2)); ex += ic.width + 12
    d = ImageDraw.Draw(base)
    d.text((ex, top), meta["label"], font=ef, fill=(accent[0], accent[1], accent[2], 255))
    y = top + 30 + 26

    # title (fitted to the space above the chip block)
    maxh = H - y - bottom_reserved
    tf, lines, lh = fit_title(title, textw, maxh, title_sizes)
    for ln in lines:
        d.text((x0 + 1, y + 3), ln, font=tf, fill=(0, 0, 0, 110))          # soft shadow
        d.text((x0, y), ln, font=tf, fill=(255, 255, 255, 255))
        y += lh
    d.rounded_rectangle([x0, y + 12, x0 + 120, y + 12 + 7], radius=4, fill=accent + (255,))

    # chips
    cy = chips_top
    for row in rows:
        cx = x0
        for ci, text, w in row:
            draw_chip(base, cx, cy, ci, text, cf, accent, chip_h)
            cx += w + 12
        cy += chip_h + 12

    # wordmark + right-side tag
    draw_wordmark(base, x0, H - 62)
    tag = "Crypto licensing guides"
    tf2 = font(20, "medium")
    d = ImageDraw.Draw(base)
    if layout != "left":
        d.text((W - M - tf2.getlength(tag), H - 62 + 5), tag, font=tf2, fill=(180, 196, 226, 255))
    return base.convert("RGB")


def fingerprint(title: str, full: bool) -> str:
    return hashlib.md5(f"{RENDER_VERSION}|{title}|{int(full)}".encode()).hexdigest()


def load_manifest() -> dict:
    try:
        return json.loads(MANIFEST.read_text())
    except Exception:
        return {}


def render_set(slug: str, title: str, force: bool = False, full: bool = True) -> str:
    meta = post_meta(slug, title)
    outs = outputs_for(slug, full)
    if not force and all(p.exists() and p.stat().st_size > 0 for p in outs.values()):
        return "skip"
    OUTDIR.mkdir(parents=True, exist_ok=True)
    master = compose(meta, *SIZES["16x9"], "16x9")
    master.save(outs["16x9"], "JPEG", quality=74, optimize=True, progressive=True)
    master.save(outs["webp"], "WEBP", quality=70, method=6)
    if full:
        compose(meta, *SIZES["4x3"], "4x3").save(outs["4x3"], "JPEG", quality=66, optimize=True, progressive=True)
        compose(meta, *SIZES["1x1"], "1x1").save(outs["1x1"], "JPEG", quality=66, optimize=True, progressive=True)
    th = master.resize(THUMB, Image.LANCZOS)
    th.save(outs["thumb"], "JPEG", quality=72, optimize=True, progressive=True)
    th.save(outs["thumbwebp"], "WEBP", quality=66, method=6)
    return "made"


def _work(args):
    slug, title, force, full = args
    try:
        return slug, render_set(slug, title, force, full), ""
    except Exception as e:                       # noqa: BLE001
        return slug, "error", f"{type(e).__name__}: {e}"


# ═══════════════════════════════════════ main ═══════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", nargs="+", metavar="SLUG")
    ap.add_argument("--preview", nargs="+", metavar="ARG", help="DIR SLUG [SLUG...]: write 16:9 + 1:1 previews to DIR")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--jobs", type=int, default=max(2, (os.cpu_count() or 4) - 1))
    a = ap.parse_args()
    items = all_items()

    if a.list:
        for s, (t, full) in sorted(items.items()):
            m = post_meta(s, t)
            print(f"{s} | {'site' if full else 'blogger'} | {m['category']} | {','.join(j[0] for j in m['jurisdictions'])} | {t[:60]}")
        return
    if a.preview:
        outdir = pathlib.Path(a.preview[0]); outdir.mkdir(parents=True, exist_ok=True)
        for s in a.preview[1:]:
            t = items[s][0] if s in items else s.replace("-", " ").capitalize()
            m = post_meta(s, t)
            compose(m, *SIZES["16x9"], "16x9").save(outdir / f"{s}.jpg", "JPEG", quality=80)
            compose(m, *SIZES["1x1"], "1x1").save(outdir / f"{s}-1x1.jpg", "JPEG", quality=74)
            compose(m, *SIZES["4x3"], "4x3").save(outdir / f"{s}-4x3.jpg", "JPEG", quality=74)
            print(f"preview {s}: {m['category']} {[j[0] for j in m['jurisdictions']]} chips={[c[1] for c in m['chips']]}")
        return

    # A set is re-rendered when forced, when a file is missing/empty, or when its fingerprint (RENDER_VERSION +
    # title) changed since it was last written: a retitled post or a new layout never leaves a stale image.
    manifest = load_manifest()
    fps = {s: fingerprint(t, full) for s, (t, full) in items.items()}
    only = set(a.only or [])
    todo = [(s, t, a.force or bool(only) or manifest.get(s) != fps[s], full)
            for s, (t, full) in items.items() if not only or s in only]
    made = skipped = errors = 0
    from multiprocessing import Pool
    with Pool(a.jobs) as pool:
        for slug, status, err in pool.imap_unordered(_work, todo, chunksize=4):
            if status == "made":
                made += 1; manifest[slug] = fps[slug]
            elif status == "skip":
                skipped += 1; manifest[slug] = fps[slug]
            else:
                errors += 1; print(f"ERROR {slug}: {err}")
    OUTDIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({s: manifest[s] for s in sorted(manifest) if s in items}, indent=0))
    nfull = sum(1 for _, full in items.values() if full)
    print(f"blog images: {made} generated, {skipped} complete already, {errors} errors "
          f"({len(items)} items: {nfull} site posts with 4:3/1:1 variants, {len(items) - nfull} Blogger-only; "
          f"{len(PHOTOS)} base photos, render v{RENDER_VERSION})")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
