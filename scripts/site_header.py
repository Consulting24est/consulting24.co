#!/usr/bin/env python3
"""Single source of truth for the Consulting24 site header.

- Generators import HEADER / HEAD_ASSETS / header_for(path) from here.
- Run directly to (re)inject the header into every page under the repo root:

    python3 scripts/site_header.py            # rewrite all pages
    python3 scripts/site_header.py --check    # report only, change nothing

Pages that are redirect stubs (no <header>) are left untouched. Re-running is
idempotent: an existing c24 header is replaced, assets are added once.
"""
import os, re, sys, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WA = "https://wa.me/37258155779?text=Hi%2C%20I%27d%20like%20to%20ask%20about%20a%20crypto%20company%20setup."
HEAD_ASSETS = '<link rel="stylesheet" href="/nav.css"><script src="/nav.js" defer></script>'

# ---------------------------------------------------------------- menu data
PANAMA = [
    ("Panama crypto license overview", "/", "€6,000 fixed · 2-3 weeks · 0% tax"),
    ("Cost: €6,000 all-in", "/cost/", None),
    ("Requirements", "/requirements/", None),
    ("Application process (7 steps)", "/application-process/", None),
    ("Company setup: S.A. vs Foundation", "/company-setup/", None),
    ("Panama crypto exchange license", "/exchange-license/", None),
    ("Ready-made crypto company", "/ready-made-crypto-license/", None),
    ("Why Panama vs other countries", "/best-country-crypto-license-panama/", None),
]

LICENSE_COLS = [
    ("By activity", [
        ("Crypto exchange license", "/exchange-license/"),
        ("Wallet & custody license", "/crypto-wallet-custody-license/"),
        ("Staking license", "/crypto-staking-license/"),
        ("Token issuance license", "/crypto-token-issuance-license/"),
        ("Stablecoin license", "/stablecoin-license/"),
        ("NFT marketplace license", "/crypto-nft-marketplace-license/"),
        ("OTC desk license", "/crypto-otc-desk-license/"),
        ("Ready-made crypto license", "/ready-made-crypto-license/"),
    ]),
    ("Regulatory frameworks", [
        ("VASP license", "/vasp-license/"),
        ("CASP license (EU)", "/casp-license/"),
        ("MiCA license", "/mica-license/"),
        ("VARA license (Dubai)", "/vara-license/"),
        ("MSB license (Canada)", "/msb-license/"),
        ("Crowdfunding license (ECSPR)", "/crowdfunding-license/"),
        ("Cryptocurrency license guide", "/cryptocurrency-license/"),
        ("Licensing index: cost & timeline", "/licensing-index/"),
    ]),
]
LICENSE_FOOT = [
    ("How to get a crypto license →", "/how-to-get-a-crypto-license/"),
]

REGIONS = [
    ("Europe", ["Estonia", "Lithuania", "Poland", "Czech Republic", "Malta", "Cyprus", "Switzerland",
                "Bulgaria", "Croatia", "France", "Germany", "Greece", "Hungary", "Ireland", "Italy",
                "Latvia", "Netherlands", "Portugal", "Romania", "Slovakia", "Spain", "Isle of Man", "Georgia"]),
    ("Middle East", ["Dubai", "Abu Dhabi", "UAE", "Qatar", "Saudi Arabia"]),
    ("Asia-Pacific", ["Singapore", "Hong Kong", "Labuan", "South Korea", "Marshall Islands", "Vanuatu"]),
    ("Americas & Caribbean", ["Panama", "El Salvador", "Canada", "USA", "Costa Rica", "Belize", "Bahamas",
                              "Bermuda", "BVI", "Cayman Islands", "Saint Lucia"]),
    ("Africa & Indian Ocean", ["South Africa", "Mauritius", "Seychelles", "Anjouan"]),
]
JURIS_FOOT = [
    ("Compare all jurisdictions →", "/jurisdictions/"),
    ("Best country", "/best-country-for-crypto-license/"),
    ("Cheapest", "/cheapest-crypto-license/"),
    ("Fastest", "/fastest-crypto-license/"),
    ("Easiest", "/easiest-crypto-license/"),
]

MAYBACH = [
    ("Luxury chauffeur service Dubai", "/luxury-chauffeur-service-dubai/", "Mercedes-Maybach S-Class"),
    ("Prices & rate card", "/luxury-chauffeur-service-dubai/prices/", None),
    ("Airport transfer", "/luxury-chauffeur-service-dubai/airport-transfer/", None),
    ("Car hire with driver", "/luxury-chauffeur-service-dubai/car-hire-with-driver/", None),
    ("Private chauffeur", "/luxury-chauffeur-service-dubai/private-chauffeur/", None),
    ("Hire a driver", "/luxury-chauffeur-service-dubai/hire-a-driver/", None),
    ("Dubai to Abu Dhabi transfer", "/luxury-chauffeur-service-dubai/dubai-to-abu-dhabi/", None),
    ("Chauffeur service Abu Dhabi", "/luxury-chauffeur-service-dubai/abu-dhabi/", None),
]

ABOUT = [
    ("About Consulting24 & our CEO", "/about/", "Mardo Soo · 500+ licenses since 2018"),
    ("Blog", "/blog/", None),
    ("News desk", "/news/", None),
    ("Editorial policy", "/editorial-policy/", None),
    ("Contact", "/contact/", None),
]

LOGO_SVG = ('<svg viewBox="0 0 512 512" aria-hidden="true" focusable="false">'
            '<rect width="512" height="512" rx="113" fill="#116dff"/>'
            '<path d="M256 103a153 153 0 1 0 118 251" fill="none" stroke="#fff" stroke-width="59" '
            'stroke-linecap="round" transform="rotate(-38 256 256)"/></svg>')


def _slug(name):
    return name.lower().replace("&", "and").replace(" ", "-")


def _href_for_country(name):
    return "/" if name == "Panama" else "/%s-crypto-license/" % _slug(name)


# ---------------------------------------------------------------- builders
def _a(label, href, current, sub=None, cls=None):
    cur = ' aria-current="page"' if href == current else ""
    c = ' class="%s"' % cls if cls else ""
    inner = html.escape(label)
    if sub:
        inner += "<small>%s</small>" % html.escape(sub)
    return '<a href="%s"%s%s>%s</a>' % (href, cur, c, inner)


def _list(items, current):
    out = []
    for it in items:
        label, href = it[0], it[1]
        sub = it[2] if len(it) > 2 else None
        out.append("<li>%s</li>" % _a(label, href, current, sub))
    return '<ul class="c24-list">%s</ul>' % "".join(out)


def _item(label, href, panel_html, current, hrefs, mega=False):
    active = " is-active" if current in hrefs else ""
    mega_cls = " c24-item--mega" if mega else ""
    lid = "c24-sub-" + _slug(label)
    return (
        '<li class="c24-item has-sub%s%s">'
        '<div class="c24-item__top">%s'
        '<button type="button" class="c24-sub-toggle" aria-expanded="false" aria-controls="%s" '
        'aria-label="Open %s menu"></button></div>'
        '<div class="c24-panel%s" id="%s">%s</div></li>'
    ) % (active, mega_cls, _a(label, href, current, cls="c24-link"), lid, html.escape(label),
         " c24-panel--cols c24-panel--mega" if mega else (" c24-panel--cols" if panel_html.startswith('<div class="c24-col">') else ""),
         lid, panel_html)


def _foot(links, current):
    return '<div class="c24-panel__foot">%s</div>' % "".join(_a(l, h, current) for l, h in links)


def header_for(current=None):
    """Return the header HTML with the item matching `current` (e.g. '/cost/') marked."""
    # Panama
    panama_hrefs = {h for _, h, _ in PANAMA}
    panama = _item("Panama Crypto License", "/", _list(PANAMA, current), current, panama_hrefs)

    # Licenses
    cols, lic_hrefs = [], set()
    for title, links in LICENSE_COLS:
        lic_hrefs.update(h for _, h in links)
        cols.append('<div class="c24-col"><h4>%s</h4>%s</div>' % (html.escape(title), _list(links, current)))
    lic_hrefs.update(h for _, h in LICENSE_FOOT)
    licenses = _item("Licenses", "/licensing-index/", "".join(cols) + _foot(LICENSE_FOOT, current), current, lic_hrefs)

    # Jurisdictions (mega)
    cols, jur_hrefs = [], set()
    for region, names in REGIONS:
        links = [(n, _href_for_country(n)) for n in names]
        jur_hrefs.update(h for _, h in links)
        wide = " c24-col--wide" if len(names) > 12 else ""
        cols.append('<div class="c24-col%s"><h4>%s</h4>%s</div>' % (wide, html.escape(region), _list(links, current)))
    jur_hrefs.update(h for _, h in JURIS_FOOT)
    jur_hrefs.discard("/")  # "/" belongs to the Panama item, not Jurisdictions
    jurisdictions = _item("Jurisdictions", "/jurisdictions/", "".join(cols) + _foot(JURIS_FOOT, current),
                          current, jur_hrefs, mega=True)

    # Maybach
    may_hrefs = {h for _, h, _ in MAYBACH}
    intro = ('<div class="c24-panel__intro"><b>MAYBACH/DXB</b>'
             '<span>Chauffeur-driven Mercedes-Maybach S-Class in Dubai. Book the drive, or book the CEO.</span></div>')
    maybach = _item("Maybach Service", "/luxury-chauffeur-service-dubai/", intro + _list(MAYBACH, current),
                    current, may_hrefs)

    # About
    about_hrefs = {h for _, h, _ in ABOUT}
    about = _item("About Us", "/about/", _list(ABOUT, current), current, about_hrefs)

    wa = ('<a href="%s" class="c24-wa%s"><span>Talk to an expert</span></a>')
    return (
        '<header class="c24-header" id="site-header">'
        '<div class="c24-header__inner">'
        '<a href="/" class="c24-logo" aria-label="Consulting24 home">%s'
        '<span class="c24-logo__text"><span class="c24-logo__name">Consulting24</span>'
        '<span class="c24-logo__tag">Crypto licensing</span></span></a>'
        '<button type="button" class="c24-burger" aria-expanded="false" aria-controls="c24-nav" aria-label="Open menu">'
        '<span></span><span></span><span></span></button>'
        '<nav class="c24-nav" id="c24-nav" aria-label="Main">'
        '<ul class="c24-menu">%s%s%s%s%s</ul>'
        '<div class="c24-nav__cta">%s</div>'
        '</nav>%s</div></header>'
    ) % (LOGO_SVG, panama, licenses, jurisdictions, maybach, about,
         wa % (WA, ""), wa % (WA, " c24-wa--bar"))


HEADER = header_for(None)

# ---------------------------------------------------------------- injector
HEADER_RE = re.compile(r'<header class="(?:top|c24-header)"[^>]*>.*?</header>', re.S)


def page_path(file_path):
    rel = os.path.relpath(os.path.dirname(file_path), ROOT).replace(os.sep, "/")
    return "/" if rel in (".", "") else "/%s/" % rel


def inject(file_path, write=True):
    with open(file_path, encoding="utf-8") as f:
        src = f.read()
    if not HEADER_RE.search(src):
        return None  # redirect stub or page without the shared header
    out = HEADER_RE.sub(lambda m: header_for(page_path(file_path)), src, count=1)
    if "/nav.css" not in out:
        out = out.replace("</head>", HEAD_ASSETS + "\n</head>", 1)
    changed = out != src
    if changed and write:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(out)
    return changed


def main(argv):
    check = "--check" in argv
    n_pages = n_changed = 0
    for dirpath, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "scripts", "logs")]
        if "index.html" in files:
            r = inject(os.path.join(dirpath, "index.html"), write=not check)
            if r is None:
                continue
            n_pages += 1
            n_changed += bool(r)
    print("pages with header: %d, %s: %d" % (n_pages, "would change" if check else "rewritten", n_changed))


if __name__ == "__main__":
    main(sys.argv[1:])
