#!/usr/bin/env python3
"""Consulting24 / Crypto License Panama — daily Blogger content pipeline.

Posts AI-written, long-form SEO articles about crypto licensing to a Blogger
blog owned by mardo@consulting24.co, each linking back to consulting24.co
landing pages.

This is a SEPARATE project from boat-rental-marbella. It reuses the same
Google OAuth *desktop client* (the client_secret JSON is account-agnostic),
but authorises as mardo@consulting24.co and stores its own token at
  ~/.consulting24_blogger_token.json
so the two projects never share Blogger credentials.

State:  config/blog_posted.json   (keyed by article slug — each posted once)
Topics: ARTICLES list below (authored long-form content, text-only)

Setup:
  GOOGLE_CREDENTIALS=/path/to/client_secret_desktop.json   (in .env)
  BLOGGER_BLOG_ID=<consulting24 blog id>                    (in .env)
  python3 scripts/consulting24_blog.py --login        # one-time OAuth as mardo@
  python3 scripts/consulting24_blog.py --list         # show queue + posted state
  python3 scripts/consulting24_blog.py --dry-run      # render next post, no publish
  python3 scripts/consulting24_blog.py                # publish today's batch
  python3 scripts/consulting24_blog.py --once SLUG    # publish one specific slug
"""
from __future__ import annotations

import argparse, json, os, pathlib, sys, datetime, traceback, re, time

ROOT        = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH  = ROOT / "config" / "blog_posted.json"
LOG_DIR     = ROOT / "logs"
LOG_PATH    = LOG_DIR / "consulting24_blog.log"
TOKEN_PATH  = pathlib.Path.home() / ".consulting24_blogger_token.json"

SITE        = "https://www.consulting24.co"
EMAIL       = "mardo@consulting24.co"
PHONE       = "+372 58155779"
DAILY_LIMIT = 2          # articles published per run/day (owner cap, Sept 2026: max 1-2/day)

# Blogger only — no Drive access needed for this project.
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/blogger"]

LOG_DIR.mkdir(exist_ok=True)

# ── logging ────────────────────────────────────────────────────────────────

def log(msg: str):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a") as fh:
        fh.write(line + "\n")

# ── env ────────────────────────────────────────────────────────────────────

def load_env():
    for p in [ROOT / ".env", pathlib.Path.home() / ".env"]:
        if p.exists():
            for line in p.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    k = k.strip()
                    if k and k not in os.environ:
                        os.environ[k] = v.strip().strip('"').strip("'")

load_env()

def require_env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        sys.exit(f"ERROR: {name} is not set. See file header for setup instructions.")
    return v

# ── Google OAuth (Blogger) ──────────────────────────────────────────────────

def get_credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    # Preferred path: the saved token already carries client_id/secret/refresh_token,
    # so the daily job keeps working even if the original client_secrets file is gone.
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), GOOGLE_SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
        return creds

    # No usable token → need the client_secrets file for a one-time interactive login.
    from google_auth_oauthlib.flow import InstalledAppFlow
    creds_path = pathlib.Path(require_env("GOOGLE_CREDENTIALS"))
    if not creds_path.exists():
        sys.exit(f"ERROR: no valid token at {TOKEN_PATH} and GOOGLE_CREDENTIALS not found: {creds_path}")
    raw = json.loads(creds_path.read_text())
    if raw.get("type") == "service_account":
        sys.exit("ERROR: Blogger needs OAuth user credentials, not a service account.")
    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), GOOGLE_SCOPES)
    print("\n>>> A browser window will open. Sign in as", EMAIL, "<<<\n")
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.write_text(creds.to_json())
    return creds

def build_blogger(creds):
    from googleapiclient.discovery import build
    return build("blogger", "v3", credentials=creds, cache_discovery=False)

# ── state ───────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"posts": {}}

def save_state(state: dict):
    STATE_PATH.write_text(json.dumps(state, indent=2))

def posted(state: dict, slug: str) -> bool:
    return slug in state.get("posts", {})

def mark_posted(state: dict, slug: str, meta: dict):
    state.setdefault("posts", {})[slug] = {
        **meta, "posted_at": datetime.datetime.now().isoformat(),
    }

# ── shared HTML blocks ───────────────────────────────────────────────────────

def _cta(keyword: str, landing_path: str) -> str:
    url = f"{SITE}{landing_path}"
    wa = PHONE.replace("+", "").replace(" ", "")
    return f"""
<div style="background:#0b1f3a;color:#fff;padding:22px 26px;margin:34px 0;border-radius:8px;">
  <strong style="font-size:18px;">Ready to set up your {keyword}?</strong>
  <p style="margin:10px 0 16px;color:#cfe0f5;">Consulting24 has completed 200+ crypto company
  setups across 15+ jurisdictions. Talk to our team for a fixed-fee proposal and realistic timeline.</p>
  <a href="{url}" style="background:#1e88e5;color:#fff;padding:11px 22px;border-radius:5px;text-decoration:none;font-weight:bold;display:inline-block;margin-right:10px;">Learn more</a>
  <a href="https://wa.me/{wa}" style="background:#25D366;color:#fff;padding:11px 22px;border-radius:5px;text-decoration:none;font-weight:bold;display:inline-block;">WhatsApp us</a>
  <p style="margin:14px 0 0;color:#9fb6d4;font-size:13px;">Email <a href="mailto:{EMAIL}" style="color:#fff;">{EMAIL}</a> &middot; Phone {PHONE}</p>
</div>"""

def _faq(faqs: list[tuple[str, str]]) -> str:
    items = "".join(
        f'<h3 style="margin-top:22px;">{q}</h3><p>{a}</p>' for q, a in faqs
    )
    return f"<h2>Frequently Asked Questions</h2>{items}"

def _related(related: list[tuple[str, str]]) -> str:
    items = "".join(f'<li><a href="{SITE}{path}">{label}</a></li>' for label, path in related)
    return f"<h2>Related reading</h2><ul>{items}</ul>"

# ── consulting24.co keyword landing-page directory (built from real on-disk pages) ──
_SPECIAL = {
    "mica":"MiCA","vasp":"VASP","casp":"CASP","msb":"MSB","vara":"VARA","bvi":"BVI",
    "usa":"USA","uae":"UAE","eu":"EU","otc":"OTC","ieo":"IEO","nft":"NFT","ai":"AI",
    "and":"and","for":"for","vs":"vs","of":"of","a":"a","to":"to","the":"the",
    "el":"El","salvador":"Salvador","isle":"Isle","man":"Man","hong":"Hong","kong":"Kong",
    "south":"South","korea":"Korea","africa":"Africa","costa":"Costa","rica":"Rica",
    "saudi":"Saudi","arabia":"Arabia","czech":"Czech","republic":"Republic",
    "marshall":"Marshall","islands":"Islands","cayman":"Cayman","saint":"Saint","lucia":"Lucia",
    "abu":"Abu","dhabi":"Dhabi","saint-lucia":"Saint Lucia",
}
def _label_from_slug(slug: str) -> str:
    words = []
    for w in slug.split("-"):
        words.append(_SPECIAL.get(w.lower(), w.capitalize()))
    return " ".join(words)

def _scan_landings() -> list[tuple[str, str]]:
    """All real consulting24.co keyword landing pages (dir/index.html), as (label, path)."""
    skip = {"blog","scripts","config","img","logs","jurisdictions"}
    out = []
    for p in sorted(ROOT.glob("*/index.html")):
        slug = p.parent.name
        if slug in skip:
            continue
        out.append((_label_from_slug(slug), f"/{slug}/"))
    return out

LANDING_DIR: list[tuple[str, str]] = _scan_landings()

def _landing_directory(current_landing: str = "") -> str:
    """A SMALL, contextually-relevant crosslink block (3 core hubs + up to 3 topically
    related pages). Deliberately NOT the whole ~600-page directory: dumping every landing
    with exact-match anchors into every post was a link-scheme footprint (SEO strategy
    2026-07-21). A handful of natural links is the honest, penalty-safe crosslink."""
    core = [("compare crypto licence jurisdictions", "/jurisdictions/"),
            ("best country for a crypto licence", "/best-country-for-crypto-license/"),
            ("a Panama crypto company", "/")]
    toks = {t for t in current_landing.strip("/").split("-") if len(t) > 3
            and t not in ("crypto", "license", "licence")}
    related = []
    for lbl, path in LANDING_DIR:
        if path == current_landing or path in {p for _, p in core}:
            continue
        if toks & {t for t in path.strip("/").split("-") if len(t) > 3}:
            related.append((lbl + " guide", path))
        if len(related) >= 3:
            break
    picks = core + related
    items = "".join(f'<a href="{SITE}{path}" style="display:inline-block;margin:0 10px 8px 0;">{lbl}</a>'
                    for lbl, path in picks)
    return ("<h2>Related crypto licensing routes</h2>"
            "<p>A few relevant guides on consulting24.co, each with real cost, timeline and requirements:</p>"
            f"<div style='line-height:1.9;font-size:14px;'>{items}</div>")

def _labels_for(topic: dict, cap: int = 20, max_chars: int = 200) -> list[str]:
    """Build Blogger labels from the topic spec + keyword + jurisdiction terms.
    Capped at `cap` labels AND a `max_chars` budget on the comma-joined string,
    since Blogger rejects (HTTP 400) overly long total label strings."""
    seen, out = set(), []
    def add(x):
        x = (x or "").strip()
        if not x: return
        k = x.lower()
        if k in seen or len(out) >= cap: return
        joined = len(", ".join(out + [x]))
        if joined > max_chars: return
        seen.add(k); out.append(x)
    for l in topic.get("labels", []):
        add(l)
    kw = topic.get("keyword", "")
    add(kw.title())
    for w in re.split(r"[\s/]+", kw):
        if len(w) > 2 and w.lower() not in {"the","for","and","crypto","license"}:
            add(w.capitalize())
    # jurisdiction from landing slug
    land = topic.get("landing", "").strip("/")
    if land:
        base = land.replace("-crypto-license", "")
        if base and base not in {"cost","requirements","exchange-license","company-setup",
                                 "application-process","vs-lithuania"}:
            add(_label_from_slug(base))
    for g in ("Crypto License","Crypto Regulation","VASP","CASP","MiCA","Crypto Compliance",
              "Crypto Company","Consulting24","Crypto Licensing 2026","Fintech",
              "AML","Crypto Tax","Crypto Exchange","Blockchain","Web3"):
        add(g)
    return out[:cap]

def _disclaimer() -> str:
    return ("<p style='color:#777;font-size:13px;margin-top:28px;border-top:1px solid #eee;"
            "padding-top:14px;'><em>This article reflects 2026 market conditions and is general "
            "guidance, not legal or tax advice. Regulations change, so confirm specifics with "
            "qualified counsel before acting. Consulting24 (X24Consulting O&Uuml;, Estonian reg. "
            "16971898) introduces vetted local lawyers and tax advisors during every engagement.</em></p>")

def _evergreen_landscape(topic: dict) -> str:
    kw = topic["keyword"]
    return f"""
<h2>Crypto Licensing in {YEAR}: The Bigger Picture</h2>
<p>Choosing where to license a crypto business in {YEAR} is no longer a simple cost calculation.
The regulatory map has hardened considerably over the last three years. In the European Union, the
Markets in Crypto-Assets Regulation (MiCA) has replaced the patchwork of national VASP registers
with a single Crypto-Asset Service Provider (CASP) authorisation that passports across all 27 member
states. That passport is powerful, but it comes with capital requirements, governance
obligations and a multi-month authorisation process that smaller projects often underestimate.</p>
<p>Outside the EU, the picture is more varied. Offshore and territorial-tax jurisdictions compete on
speed, cost and privacy, while major financial centres such as Switzerland, the UAE and Singapore
compete on credibility and institutional access. The Financial Action Task Force (FATF) sits over all
of them: its &ldquo;travel rule&rdquo; and AML standards now apply, in some form, almost everywhere a
serious crypto business would consider basing itself. Jurisdictions that ignore FATF expectations end
up grey-listed, which quietly closes correspondent-banking doors for every company registered there.</p>
<p>This is why the question behind <strong>{kw}</strong> is rarely &ldquo;which licence is cheapest?&rdquo;
It is &ldquo;which regime matches my customers, my risk appetite and my banking needs?&rdquo; An EU-retail
exchange and an offshore OTC desk serving high-net-worth clients in Latin America have almost nothing in
common in terms of the right base. Getting this decision right at the start saves you from the single most
expensive mistake in the industry: licensing in the wrong place and having to re-domicile a live business.</p>
<p>Consulting24 has guided more than 200 crypto company setups across 15+ jurisdictions since 2017, which
means we have seen how each of these regimes behaves in practice rather than just on paper. The summary
below is the same framework we use with clients, and we are always happy to map it to your specific
model. Start with our <a href="{SITE}/vs-lithuania/">Panama vs Lithuania comparison</a> to see how the
trade-offs play out between an offshore base and an EU-passported one.</p>
"""

def _evergreen_banking(topic: dict) -> str:
    return f"""
<h2>Banking and Compliance: Where Most Setups Actually Stall</h2>
<p>Incorporation is the easy part of any crypto project. Banking is where timelines slip and where
under-prepared founders lose months. Since 2023, banks and payment processors worldwide have tightened
their onboarding of crypto-adjacent businesses, and they now expect a genuinely professional application
, not a one-page business summary. A thin file is simply rejected, and re-applying with the same bank
is far harder than getting it right the first time.</p>
<p>Three documents do the heavy lifting. The first is a written <strong>AML/KYC compliance program</strong>:
your customer-onboarding flow, transaction-monitoring rules, sanctions and PEP screening, a named compliance
officer, and record-keeping policies. The second is a clear, evidenced <strong>source-of-funds</strong> file
for both the company and its beneficial owners. The third is a coherent <strong>business description</strong>
that explains who your customers are, how money moves, and what volumes you project. Banks approve businesses
they understand; ambiguity reads as risk.</p>
<p>Sequencing matters as much as substance. The correct order is: incorporate the operating entity, build the
compliance program, assemble the source-of-funds package, and only then approach banking, ideally
through a warm introduction rather than a cold application. Founders who approach banks mid-setup, before
their file is complete, create the very delays they are trying to avoid. We make direct introductions to
banks and crypto-friendly payment rails as part of every engagement, but the introduction only works if the
file behind it is ready.</p>
<p>None of this is optional, and none of it changes much from one jurisdiction to the next, the
compliance bar is now broadly global. What changes is the appetite of local banks and the speed of
onboarding. Our <a href="{SITE}/requirements/">requirements checklist</a> sets out exactly what you need to
assemble before you approach a bank.</p>
"""

def _evergreen_choosing(topic: dict) -> str:
    return f"""
<h2>How to Choose the Right Jurisdiction</h2>
<p>Work the decision in this order: customers first, everything else second:</p>
<ul>
  <li><strong>Who are your customers?</strong> EU retail means you need a MiCA passport (Lithuania, Malta or
  another EU CASP). US customers mean state-by-state money-transmitter licensing or a FinCEN MSB, so consider
  a Canada MSB or a US setup. Latin America, Asia or HNW clients mean an offshore or territorial base such as
  Panama is usually the better fit.</li>
  <li><strong>Do you need a regulator badge?</strong> A public-facing exchange chasing institutional partners
  and fundraising often needs the reputational lift of an EU, Swiss or VARA licence. An OTC desk or token
  treasury usually does not.</li>
  <li><strong>What is your budget and timeline?</strong> Offshore and territorial routes set up in weeks for
  tens of thousands; premium onshore licences take many months and six figures.</li>
  <li><strong>What about tax?</strong> Territorial-tax jurisdictions like Panama charge 0% on foreign-source
  income; EU jurisdictions apply standard corporate tax. Factor total cost of ownership, not just setup fees.</li>
</ul>
<p>For many offshore-first founders, Panama lands at the intersection of fast incorporation, low cost and 0%
tax on foreign-source income, which is why it features so heavily in our work. But the honest answer is that
the &ldquo;best&rdquo; jurisdiction is the one that matches the four answers above, and that is a
conversation worth having before you spend a cent. See our <a href="{SITE}/cost/">cost breakdown</a> and
<a href="{SITE}/application-process/">application process</a> to ground the decision in real numbers.</p>
"""

def _evergreen_mistakes(topic: dict) -> str:
    kw = topic["keyword"]
    return f"""
<h2>Common Mistakes to Avoid</h2>
<p>The failures we see when founders research <strong>{kw}</strong> on their own are remarkably
consistent, and almost all of them are avoidable. The first is <em>licensing to the headline tax rate</em>.
A 0% jurisdiction is worthless if your customers legally require a regulated provider you cannot become
there, and you will simply have to start again. Decide who you are allowed to serve first, then optimise
for tax.</p>
<p>The second is <em>treating the compliance program as paperwork</em>. The AML/KYC program is not a
formality to satisfy a regulator; it is the document your bank reads most closely. A generic template
downloaded from the internet is transparent to any compliance officer and will sink your banking
application. It needs to reflect your actual product, customer base and risk profile.</p>
<p>The third is <em>underestimating banking lead time</em>. Founders routinely budget for incorporation and
forget that the bank account, the thing that actually lets the business operate, can take longer
than the licence itself. Build banking into your launch timeline from day one, not as an afterthought.</p>
<p>The fourth is <em>ignoring personal tax residency</em>. A company in a low-tax jurisdiction does not erase
your obligations where you personally live. Many founders create unexpected liabilities by structuring the
company perfectly and ignoring themselves. We introduce qualified tax advisors precisely to close this gap.</p>
<p>The fifth and most expensive is <em>choosing a provider on price alone</em>. The cheapest setup that
results in a rejected bank application or a re-domiciliation is far more expensive than doing it properly
once. Ask any provider to itemise their fee and explain their banking track record before you commit.</p>
"""

def _evergreen_aftercare(topic: dict) -> str:
    return f"""
<h2>What Happens After You Are Licensed</h2>
<p>Getting licensed and banked is the start, not the finish. Every regulated or registered crypto business
carries ongoing obligations, and letting them lapse is how companies lose their standing, and their
banking. At minimum you will maintain a registered agent or local presence, file annual renewals or
supervision fees, keep accounting records, and keep your compliance program live with periodic reviews and
updated sanctions and PEP screening lists.</p>
<p>Most jurisdictions also expect you to keep your beneficial-ownership information current and to report
material changes, new directors, new shareholders, a pivot in business activity, promptly.
Transaction monitoring is not a one-time setup either; screening rules need tuning as your volumes and
customer mix evolve. Banks may request periodic refreshes of your KYC and source-of-funds documentation,
particularly after a year of trading or a significant change in activity.</p>
<p>This is why we offer ongoing maintenance on an annual retainer rather than treating setup as a one-off
transaction. The cost of staying compliant is a fraction of the cost of losing a banking relationship and
having to rebuild one from scratch. Plan for it in your year-two budget from the outset, and treat your
compliance function as a living part of the business rather than a box you ticked at launch.</p>
<p>It is also worth planning ahead for growth. A structure that suits a pre-revenue startup may not suit
the same company once it is processing meaningful volume, adding new product lines, or expanding into new
markets. Many of the businesses we work with begin in a fast, low-cost offshore base to validate the model,
then add a second regulated entity, an EU CASP, for example, once revenue justifies the cost
and the market access genuinely matters. Designing the first structure with that possible second step in
mind keeps your options open and avoids a disruptive re-domiciliation later. We map this growth path out
with clients during the initial planning stage so the early decisions support, rather than constrain, where
the business is heading.</p>
"""

LINKEDIN = "https://www.linkedin.com/in/mardo-s-00a05ab0/"

def _why_consulting24() -> str:
    return f"""
<h2>About Consulting24 &amp; Mardo Soo</h2>
<div style="border:1px solid #e6eef7;border-radius:10px;padding:22px 24px;margin:14px 0 8px;background:#f7fafd;">
  <div style="display:flex;align-items:center;gap:16px;margin-bottom:14px;">
    <div style="flex:0 0 auto;width:58px;height:58px;border-radius:50%;background:#0b1f3a;color:#fff;
         font-family:Arial,Helvetica,sans-serif;font-weight:bold;font-size:20px;line-height:58px;text-align:center;">MS</div>
    <div style="line-height:1.4;">
      <strong style="font-size:17px;color:#0b1f3a;">Mardo Soo</strong><br>
      <span style="color:#56708f;">Founder &amp; CEO, Consulting24 &middot;
      <a href="{LINKEDIN}" rel="noopener nofollow" target="_blank">LinkedIn</a></span>
    </div>
  </div>
  <p style="margin:0 0 12px;">Consulting24 is an eight-year-old advisory firm that has completed
  <strong>200+ crypto company setups across 15+ jurisdictions</strong> since 2017. Founder and CEO
  <strong>Mardo Soo</strong> and the team specialise in
  crypto, VASP and exchange licensing, from Panama and the EU (MiCA) to Dubai, Canada and the
  offshore world. We don't push a single &ldquo;best&rdquo; jurisdiction; we map your business to the regime
  that actually fits, then handle incorporation, the AML/KYC compliance program, and banking and
  payment-processor introductions end to end.</p>
  <p style="margin:0 0 12px;">Every engagement begins with an honest conversation about your customers,
  budget and timeline and ends with a <strong>fixed-fee proposal</strong>, so you know the all-in number
  before you commit. We also introduce vetted local lawyers and tax advisors wherever your structure
  requires them.</p>
  <p style="margin:0;color:#56708f;font-size:14px;">Operated by <strong>X24Consulting O&Uuml;</strong>
  (Estonian Business Register code 16971898), P&otilde;rdi tn 3-63, 10156 Tallinn, Estonia &middot;
  <a href="mailto:{EMAIL}">{EMAIL}</a> &middot; {PHONE}</p>
</div>
"""

def _author_org_jsonld() -> str:
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "Organization", "name": "Consulting24", "legalName": "X24Consulting OÜ",
             "url": SITE, "email": EMAIL, "telephone": PHONE, "foundingDate": "2017",
             "taxID": "16971898",
             "address": {"@type": "PostalAddress", "streetAddress": "Põrdi tn 3-63",
                         "addressLocality": "Tallinn", "postalCode": "10156", "addressCountry": "EE"},
             "founder": {"@type": "Person", "name": "Mardo Soo"},
             "areaServed": "Worldwide",
             "knowsAbout": ["Crypto license", "VASP license", "Crypto exchange license",
                            "MiCA", "AML/KYC compliance"]},
            {"@type": "Person", "name": "Mardo Soo", "jobTitle": "Founder & CEO",
             "worksFor": {"@type": "Organization", "name": "Consulting24"},
             "sameAs": [LINKEDIN]},
        ],
    }
    return f'<script type="application/ld+json">{json.dumps(data)}</script>'

def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _hero_photo(headline: str, slug: str = "") -> str:
    """Real hosted raster image so Blogger has a usable thumbnail and a genuine
    photo (inline SVG is not picked up as a Blogger thumbnail). Each post/page has
    a UNIQUE branded hero at /img/blog/<slug>.jpg (generated by gen_blog_images.py);
    falls back to a varied gallery photo if a slug-specific image is not available."""
    h = _esc(headline.title() if headline.islower() else headline)
    if slug:
        src = f"{SITE}/img/blog/{slug}.jpg"
    else:
        idx = (sum(ord(c) for c in headline) % 9) + 1
        src = f"{SITE}/img/gallery-{idx:02d}.jpg"
    return (f"<div style='margin:0 0 18px;'><img src='{src}' alt='{h} &#8212; Consulting24' "
            "width='1200' height='630' loading='eager' "
            "style='display:block;width:100%;height:auto;border-radius:10px;'/></div>")

def _hero_image(headline: str, sub: str = "Crypto licensing across 15+ jurisdictions") -> str:
    """Always-present, on-brand inline-SVG hero banner (copyright-free, no hotlinking).
    Brand gradient + blockchain dot-grid + compliance-shield emblem + accent underline."""
    h = _esc(headline.title() if headline.islower() else headline)
    n = len(h)
    fs = 58 if n <= 22 else 46 if n <= 30 else 38 if n <= 40 else 31
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1200 480' width='100%' role='img' "
        f"aria-label='{h}' style='display:block;height:auto;border-radius:10px;'>"
        "<defs>"
        "<linearGradient id='cg' x1='0' y1='0' x2='1' y2='1'>"
        "<stop offset='0' stop-color='#08172b'/><stop offset='0.55' stop-color='#0b2a52'/>"
        "<stop offset='1' stop-color='#1e88e5'/></linearGradient>"
        "<radialGradient id='gl' cx='0.8' cy='0.28' r='0.55'>"
        "<stop offset='0' stop-color='#42a5f5' stop-opacity='0.5'/>"
        "<stop offset='1' stop-color='#42a5f5' stop-opacity='0'/></radialGradient>"
        "<pattern id='dots' width='34' height='34' patternUnits='userSpaceOnUse'>"
        "<circle cx='2' cy='2' r='2' fill='#ffffff' opacity='0.06'/></pattern>"
        "</defs>"
        "<rect width='1200' height='480' fill='url(#cg)'/>"
        "<rect width='1200' height='480' fill='url(#dots)'/>"
        "<rect width='1200' height='480' fill='url(#gl)'/>"
        # right-side compliance emblem (concentric rings + shield + check)
        "<g transform='translate(1015,238)'>"
        "<circle r='152' fill='none' stroke='#ffffff' stroke-opacity='0.10' stroke-width='2'/>"
        "<circle r='112' fill='none' stroke='#ffffff' stroke-opacity='0.14' stroke-width='2'/>"
        "<path d='M0,-72 L64,-45 L64,8 C64,54 34,80 0,94 C-34,80 -64,54 -64,8 L-64,-45 Z' "
        "fill='#ffffff' fill-opacity='0.10' stroke='#9fd0ff' stroke-width='2'/>"
        "<path d='M-27,4 L-6,27 L31,-23' fill='none' stroke='#25D366' stroke-width='11' "
        "stroke-linecap='round' stroke-linejoin='round'/></g>"
        # badge
        "<rect x='80' y='92' width='372' height='40' rx='20' fill='#ffffff' fill-opacity='0.12'/>"
        "<text x='102' y='118' fill='#cfe6ff' font-family='Arial,Helvetica,sans-serif' "
        "font-size='18' letter-spacing='2' font-weight='bold'>CRYPTO LICENSE GUIDE &#183; 2026</text>"
        # headline + accent underline
        f"<text x='80' y='248' fill='#ffffff' font-family='Arial,Helvetica,sans-serif' "
        f"font-size='{fs}' font-weight='bold'>{h}</text>"
        "<rect x='82' y='268' width='120' height='6' rx='3' fill='#25D366'/>"
        # subtitle
        f"<text x='80' y='318' fill='#bcd6f5' font-family='Arial,Helvetica,sans-serif' "
        f"font-size='25'>{_esc(sub)}</text>"
        # wordmark
        "<circle cx='86' cy='430' r='6' fill='#25D366'/>"
        "<text x='104' y='437' fill='#9fb6d4' font-family='Arial,Helvetica,sans-serif' "
        "font-size='22' letter-spacing='3' font-weight='bold'>CONSULTING24.CO</text>"
        "</svg>"
    )
    return f"<div style='margin:0 0 26px;'>{svg}</div>"

def _process_graphic() -> str:
    """In-content infographic: the 4 stages of getting a crypto licence (SVG, copyright-free)."""
    steps = [("1", "Choose jurisdiction", "match your customers"),
             ("2", "Incorporate", "set up the entity"),
             ("3", "AML / KYC program", "the banking key"),
             ("4", "Open banking", "fiat on/off-ramps")]
    xs = [180, 460, 740, 1020]
    nodes = ""
    for (num, lbl, sub), x in zip(steps, xs):
        nodes += (
            f"<circle cx='{x}' cy='96' r='40' fill='#0b1f3a'/>"
            f"<circle cx='{x}' cy='96' r='40' fill='none' stroke='#25D366' stroke-width='3'/>"
            f"<text x='{x}' y='108' fill='#ffffff' text-anchor='middle' "
            f"font-family='Arial,Helvetica,sans-serif' font-size='30' font-weight='bold'>{num}</text>"
            f"<text x='{x}' y='168' fill='#0b1f3a' text-anchor='middle' "
            f"font-family='Arial,Helvetica,sans-serif' font-size='22' font-weight='bold'>{lbl}</text>"
            f"<text x='{x}' y='196' fill='#56708f' text-anchor='middle' "
            f"font-family='Arial,Helvetica,sans-serif' font-size='17'>{sub}</text>")
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1200 230' width='100%' role='img' "
        "aria-label='The four stages of getting a crypto licence' "
        "style='display:block;height:auto;'>"
        "<rect width='1200' height='230' rx='12' fill='#f2f7fc' stroke='#e6eef7'/>"
        "<text x='40' y='44' fill='#0b1f3a' font-family='Arial,Helvetica,sans-serif' "
        "font-size='20' font-weight='bold'>The 4 stages of getting licensed</text>"
        "<line x1='180' y1='96' x2='1020' y2='96' stroke='#cfe0f5' stroke-width='4'/>"
        + nodes + "</svg>")
    return f"<div style='margin:26px 0;'>{svg}</div>"

def _blog_pillar_links_html(current_slug: str = "") -> str:
    """Links to the blog's own pillar PAGES (read live URLs from state). Hub-and-spoke."""
    try:
        pages = json.loads(STATE_PATH.read_text()).get("pages", {})
    except Exception:
        pages = {}
    picked = [(s, m) for s, m in pages.items() if s != current_slug and m.get("url")][:3]
    items = "".join(f'<li><a href="{m["url"]}">{_esc(m.get("title",""))}</a></li>' for s, m in picked)
    if not items:
        return ""
    return ("<h2>More crypto-license guides on this blog</h2>"
            f"<ul>{items}</ul>")

def _dedupe_links(html: str, seen=None) -> str:
    """Keep only the first link to each URL; unlink later repeats (avoid over-linking).
    Pre-seed `seen` with hub URLs so the body won't duplicate links that live in the
    curated Related / More-guides lists."""
    seen = set(seen or [])
    def repl(mo):
        href = mo.group(1)
        if href in seen:
            return mo.group(2)        # drop the <a> wrapper, keep the anchor text
        seen.add(href)
        return mo.group(0)
    return re.sub(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', repl, html, flags=re.S)

def render_article(topic: dict) -> str:
    """Build the full ~2000-word post HTML from a topic spec."""
    body = [_hero_photo(topic["keyword"], topic.get("slug","")), _hero_image(topic["keyword"]),
            f"<p><strong>{topic['lede']}</strong></p>"]
    for i, (heading, paras) in enumerate(topic["sections"]):
        body.append(f"<h2>{heading}</h2>")
        for p in paras:
            body.append(f"<p>{p}</p>")
        if i == 0:
            body.append(_process_graphic())   # in-content visual after first section
    body.append(_evergreen_choosing(topic))
    body.append(_evergreen_banking(topic))
    body.append(_evergreen_landscape(topic))
    body.append(_evergreen_mistakes(topic))
    body.append(_evergreen_aftercare(topic))
    related_html = _related(topic["related"])       # → consulting24.co landing pages (hub)
    blog_html = _blog_pillar_links_html()            # → blog's own pillar pages (hub)
    directory_html = _landing_directory(topic.get("landing", ""))  # → all keyword landing pages
    hub = set(re.findall(r'href="([^"]+)"', related_html + blog_html + directory_html))
    parts = [_dedupe_links("\n".join(body), seen=hub),  # body links to hub URLs unlinked
             _cta(topic["keyword"], topic["landing"]),
             _why_consulting24(),
             _faq(topic["faqs"]),
             related_html,
             blog_html,
             directory_html,
             _disclaimer(),
             _author_org_jsonld()]
    return "\n".join(parts)

# ── articles ────────────────────────────────────────────────────────────────
# Each topic: slug, title, keyword, landing (internal path), labels (Blogger
# tags), lede, sections [(h2, [paragraphs])], faqs [(q, a)], related [(label,path)].

PANAMA_ARTICLES: list[dict] = [
    {
        "slug": "crypto-license-panama-2026-guide",
        "title": "Crypto License in Panama 2026: The Complete Setup Guide",
        "keyword": "crypto license in Panama",
        "landing": "/",
        "labels": ["Panama", "Crypto License", "Guide"],
        "lede": "Panama has quietly become one of the most practical bases for crypto businesses "
                "that serve Latin America, Asia and high-net-worth clients rather than EU retail. "
                "Here is exactly how a crypto company is set up in Panama in 2026, what it costs, "
                "and when it is the right choice.",
        "sections": [
            ("Does Panama Have a Crypto License?",
             ["Panama does <strong>not</strong> have a single dedicated crypto or VASP license as of 2026. "
              "Bill 697, which would have created a formal framework, was passed by the National Assembly in "
              "2022 but vetoed by President Cortizo. Reform discussions continue, but no standalone regime "
              "has been enacted.",
              "Instead, crypto activities operate under Panama's existing financial-services frameworks. "
              "Money-services activities fall under the Superintendency of Banks of Panama (SBP), and AML/CFT "
              "supervision sits with UAF Panama (Unidad de An&aacute;lisis Financiero), the local equivalent of "
              "FinCEN in the US or FINTRAC in Canada. In practice, most crypto operators incorporate a Panama "
              "Sociedad An&oacute;nima and run a documented AML/KYC program rather than holding a named license."]),
            ("The Two Core Structures",
             ["<strong>Panama Sociedad An&oacute;nima (S.A.)</strong> is the workhorse corporation for exchanges, "
              "brokers and payment processors. It incorporates in 2-3 weeks, requires three directors "
              "(nominees are permitted), and has no minimum paid-up capital.",
              "<strong>Panama Private Interest Foundation</strong> is an asset-protection structure used for "
              "token treasuries, family-office crypto holdings and DAO foundations. It requires a minimum "
              "endowment of roughly $10,000 and is frequently paired with an operating S.A."]),
            ("What It Costs and How Long It Takes",
             ["Budget $15,000-$45,000 all-in for the first year, depending on whether you need a full "
              "AML/KYC compliance program, banking introductions and ongoing nominee services. Annual "
              "maintenance runs $5,000-$15,000.",
              "End-to-end timelines are typically 6-12 weeks, materially faster than the 4-8 months "
              "a Lithuania MiCA VASP authorisation now takes. See our full "
              f"<a href='{SITE}/cost/'>cost breakdown</a> and "
              f"<a href='{SITE}/application-process/'>application process</a> for the line-item detail."]),
            ("Tax and Banking Reality",
             ["Panama runs a territorial tax system: foreign-source income is taxed at 0%. The country also uses "
              "the US dollar as legal tender alongside the balboa at a 1:1 peg, so there is no FX risk on "
              "USD-denominated crypto operations.",
              "Banking is the real bottleneck. Panamanian banks have tightened KYC for crypto-adjacent businesses "
              "since 2023, so expect 2-5 weeks for onboarding and a properly documented source-of-funds and "
              "compliance file. Panama was removed from the FATF grey list in October 2023 and is FATF-compliant "
              "in 2026, which has helped restore correspondent-banking confidence."]),
        ],
        "faqs": [
            ("Is crypto legal in Panama?",
             "Yes. Holding, trading and operating crypto businesses is legal. There is simply no dedicated "
             "licensing regime; activities run under existing financial-services and AML law."),
            ("How fast can I incorporate?",
             "A Panama S.A. incorporates in 2-3 weeks. Full operational readiness including banking and a "
             "compliance program is usually 6-12 weeks."),
            ("Do I need to live in Panama?",
             "No. Directors and shareholders can be non-resident, and nominee directors are permitted. You do "
             "need a registered agent in Panama, which we arrange."),
        ],
        "related": [
            ("Panama crypto company setup", "/company-setup/"),
            ("Requirements checklist", "/requirements/"),
            ("Panama vs Lithuania", "/vs-lithuania/"),
        ],
    },
    {
        "slug": "panama-vs-lithuania-crypto-license",
        "title": "Panama vs Lithuania for a Crypto License: Which Should You Choose in 2026?",
        "keyword": "crypto license comparison",
        "landing": "/vs-lithuania/",
        "labels": ["Panama", "Lithuania", "Comparison", "MiCA"],
        "lede": "The single most common question we get: should I license in Panama or Lithuania? "
                "The honest answer depends entirely on who your customers are. Here is the decision "
                "framework we use with clients.",
        "sections": [
            ("The Headline Trade-off",
             ["Lithuania gives you an EU MiCA passport, the ability to serve EU retail customers under a "
              "recognised European regulator. That credibility costs money and time: roughly $50,000-$120,000 "
              "to set up and 4-8 months to authorise.",
              "Panama gives you speed, low cost and territorial-tax efficiency, but no EU passport. Setup is "
              "$15,000-$45,000 and 6-12 weeks. It is built for offshore-first operations that do not need "
              "to touch EU retail."]),
            ("Choose Lithuania If...",
             ["You are launching a public-facing exchange targeting EU retail customers and need the MiCA "
              "passport to operate legally across the bloc.",
              "You want the reputational lift of an EU regulator badge for institutional partners, banking and "
              "fundraising. For many CEX projects this badge alone justifies the cost."]),
            ("Choose Panama If...",
             ["Your customers are in Latin America, Asia, or you serve high-net-worth individuals rather than EU "
              "retail. You do not need a MiCA passport and would rather not pay for one.",
              "You prioritise fast incorporation and a lower regulatory burden, and you value Panama's 0% tax on "
              "foreign-source income. Many token treasuries and brokers fit this profile precisely.",
              f"See the side-by-side detail on our <a href='{SITE}/vs-lithuania/'>Panama vs Lithuania</a> page."]),
            ("What About Other Jurisdictions?",
             ["<strong>Canada MSB (FINTRAC):</strong> $8,000-$25,000, 3-6 weeks, strong North American fiat "
              "rails, best for crypto-to-fiat exchanges. <strong>BVI VASP:</strong> a similar offshore profile "
              "to Panama with slightly higher cost and more legal certainty post-VASP Act 2022. "
              "<strong>Estonia VASP:</strong> largely deprecated after the 2024 crackdown; most operators have "
              "migrated to Lithuania."]),
        ],
        "faqs": [
            ("Can I start in Panama and move to Lithuania later?",
             "Yes, and many do. Launching offshore in Panama to validate the business, then adding an EU entity "
             "for MiCA passporting once revenue justifies it, is a common staged approach."),
            ("Does Panama recognise MiCA?",
             "No. Panama is outside the EU and not bound by MiCA. If your business model depends on serving EU "
             "retail, Panama alone is not sufficient."),
            ("Which is cheaper to maintain?",
             "Panama. Annual maintenance is $5,000-$15,000 versus materially higher ongoing compliance and "
             "reporting costs under an EU MiCA framework."),
        ],
        "related": [
            ("Panama crypto license overview", "/"),
            ("Cost breakdown", "/cost/"),
            ("Exchange license options", "/exchange-license/"),
        ],
    },
    {
        "slug": "panama-crypto-company-cost-breakdown-2026",
        "title": "How Much Does a Panama Crypto Company Cost in 2026? Full Breakdown",
        "keyword": "Panama crypto company cost",
        "landing": "/cost/",
        "labels": ["Panama", "Cost", "Crypto License"],
        "lede": "Crypto setup quotes vary wildly because providers bundle different things. Here is an "
                "honest, line-item view of what a Panama crypto company actually costs in 2026, "
                "first year and ongoing.",
        "sections": [
            ("First-Year Total: $15,000-$45,000",
             ["The range is wide because it depends on how much you need. A lean Sociedad An&oacute;nima with a "
              "registered agent and basic structure sits near the bottom. A full build, S.A. plus a "
              "documented AML/KYC program, banking introductions, nominee directors and a foundation for the "
              "treasury, sits near the top.",
              f"Our <a href='{SITE}/cost/'>cost page</a> breaks these into fixed packages so there are no surprises."]),
            ("Where the Money Goes",
             ["<strong>Incorporation of the Sociedad An&oacute;nima:</strong> government fees, registered agent, "
              "and corporate documents. <strong>AML/KYC compliance program:</strong> from roughly $8,000, and this "
              "is the documented program banks and payment processors require before onboarding. "
              "<strong>Banking and payment-processor introductions:</strong> direct introductions to Panamanian "
              "banks and crypto-friendly rails.",
              "<strong>Optional:</strong> a Private Interest Foundation (minimum endowment ~$10,000) for "
              "token-treasury or family-office holdings, and nominee director services where privacy matters."]),
            ("Ongoing Annual Cost: $5,000-$15,000",
             ["Annual maintenance covers the registered agent, the franchise tax, accounting and the ongoing "
              "upkeep of the compliance program. Because Panama taxes foreign-source income at 0%, there is no "
              "corporate income-tax drag on offshore revenue, a meaningful structural saving versus many "
              "onshore alternatives."]),
            ("Hidden Costs to Plan For",
             ["The two costs founders underestimate are <em>banking lead time</em> and <em>compliance "
              "documentation</em>. Panamanian banks tightened KYC after 2023; a thin file gets rejected and "
              "wastes weeks. Budget for a proper source-of-funds package up front. It is cheaper than a "
              "re-application."]),
        ],
        "faqs": [
            ("Is there a minimum capital requirement?",
             "No. A Panama Sociedad An&oacute;nima has no minimum paid-up capital, unlike many EU regimes."),
            ("Are nominee directors extra?",
             "Yes, nominee services are a separate annual line item. They are optional but common where founders "
             "want privacy on the public register."),
            ("Can you give a fixed quote?",
             "Yes. Once we understand your model and target markets we provide a fixed-fee proposal rather than "
             "an open-ended hourly arrangement."),
        ],
        "related": [
            ("Application process", "/application-process/"),
            ("Requirements checklist", "/requirements/"),
            ("Company setup", "/company-setup/"),
        ],
    },
    {
        "slug": "panama-crypto-license-requirements-checklist",
        "title": "Panama Crypto License Requirements: The 2026 Documentation Checklist",
        "keyword": "Panama crypto license requirements",
        "landing": "/requirements/",
        "labels": ["Panama", "Requirements", "Compliance"],
        "lede": "The single biggest cause of delay in a Panama crypto setup is incomplete paperwork. "
                "This is the exact documentation checklist we work through with clients before "
                "incorporation and banking.",
        "sections": [
            ("Corporate Documents",
             ["You will need passport copies and proof of address for every director and beneficial owner, "
              "a chosen company name (we check availability), and the intended business activity description. "
              "A Panama S.A. needs three directors; nominees are permitted where you prefer privacy.",
              f"The full intake list is on our <a href='{SITE}/requirements/'>requirements page</a>."]),
            ("AML/KYC Compliance Program",
             ["Banks and payment processors will not onboard a crypto business without a documented compliance "
              "program. This covers your KYC onboarding flow, transaction-monitoring rules, sanctions screening, "
              "a designated compliance officer, and record-keeping policies aligned with UAF Panama expectations.",
              "This is not a box-ticking PDF. It is the document that determines whether your banking application "
              "succeeds, so it is worth doing properly the first time."]),
            ("Source-of-Funds and Banking File",
             ["Expect to evidence the source of the company's funds and the personal wealth of beneficial owners. "
              "Since 2023, Panamanian banks scrutinise crypto-adjacent applicants closely. A clean, complete file "
              "moves through onboarding in 2-5 weeks; a thin one stalls."]),
            ("Ongoing Obligations",
             ["After setup you maintain the registered agent, pay the annual franchise tax, keep accounting "
              "records, and keep the compliance program live (periodic reviews, updated screening lists). "
              "We handle these on an annual retainer so nothing lapses."]),
        ],
        "faqs": [
            ("How many directors are required?",
             "Three. They can be non-resident, and nominee directors are permitted."),
            ("Do beneficial owners appear on a public register?",
             "Directors appear on the public register; using nominees keeps beneficial owners off it. Beneficial "
             "ownership is still disclosed to the registered agent under Panama's transparency rules."),
            ("How long does document collection take?",
             "Usually a few days if everyone responds promptly. It is the most controllable part of the timeline."),
        ],
        "related": [
            ("Cost breakdown", "/cost/"),
            ("Application process", "/application-process/"),
            ("Panama crypto license guide", "/"),
        ],
    },
    {
        "slug": "panama-crypto-exchange-license-explained",
        "title": "Setting Up a Crypto Exchange in Panama: License, Structure and Banking",
        "keyword": "Panama crypto exchange license",
        "landing": "/exchange-license/",
        "labels": ["Panama", "Exchange", "Crypto License"],
        "lede": "Running an exchange from Panama is entirely viable in 2026, provided you understand "
                "that there is no named exchange license and that your real gating factor is banking "
                "and compliance, not a regulator badge.",
        "sections": [
            ("There Is No Named Exchange License",
             ["Because Panama has no dedicated VASP regime, you do not apply for an 'exchange license' as such. "
              "You incorporate a Sociedad An&oacute;nima, run the exchange under existing financial-services and "
              "AML law, and operate a compliance program supervised in spirit by UAF Panama.",
              f"Our <a href='{SITE}/exchange-license/'>exchange license page</a> walks through how this works in "
              "practice for order-book, brokerage and OTC models."]),
            ("Structuring the Operating Entity",
             ["Most exchange operators use a Panama S.A. as the operating company and, where there is a token or "
              "treasury, a Private Interest Foundation to hold it separately. Keeping operations and treasury in "
              "distinct vehicles is cleaner for both risk and banking.",
              "If you serve EU retail you will additionally need an EU-licensed entity under MiCA, Panama "
              "alone does not passport into Europe."]),
            ("Banking and Payment Rails",
             ["This is where exchanges live or die. You need fiat on/off-ramps, so the priority is securing a "
              "Panamanian bank account and crypto-friendly payment-processor relationships. We make direct "
              "introductions, but you must arrive with a complete compliance program and source-of-funds file. "
              "Panama's USD legal tender removes FX risk on USD settlement."]),
            ("Who This Suits",
             ["Panama exchanges work best for operators targeting Latin America and Asia, OTC desks serving HNW "
              "clients, and brokerages that do not need EU retail access. For a public CEX chasing EU customers, "
              "pair Panama with a Lithuania MiCA entity or start in Lithuania directly."]),
        ],
        "faqs": [
            ("Can I serve US customers from Panama?",
             "Not without separate US compliance. US money transmission needs state-by-state licensing or a "
             "FinCEN MSB registration; Panama does not cover it. Consider a Canada MSB or US setup for that."),
            ("Do I need a local Panamanian director?",
             "You need a registered agent in Panama and three directors who may be non-resident. We can supply "
             "nominees."),
            ("How long until I can take customers?",
             "Realistically 6-12 weeks once banking and the compliance program are in place."),
        ],
        "related": [
            ("Panama vs Lithuania", "/vs-lithuania/"),
            ("Company setup", "/company-setup/"),
            ("Requirements checklist", "/requirements/"),
        ],
    },
    {
        "slug": "panama-territorial-tax-crypto-business",
        "title": "Panama's Territorial Tax System: What It Means for a Crypto Business",
        "keyword": "Panama crypto tax",
        "landing": "/company-setup/",
        "labels": ["Panama", "Tax", "Crypto License"],
        "lede": "Panama's 0% tax on foreign-source income is the structural reason many crypto founders "
                "choose it. But the rule has nuance, and getting it wrong is expensive. Here is how "
                "territorial taxation actually works for a crypto company.",
        "sections": [
            ("How Territorial Taxation Works",
             ["Panama taxes income generated <em>within</em> Panama. Income from foreign sources, customers, "
              "trades and revenue arising outside Panama, is taxed at 0%. For an offshore-facing crypto "
              "business serving Latin America, Asia or global HNW clients, the bulk of revenue is foreign-source.",
              "Combined with the US dollar as legal tender (1:1 with the balboa), this gives a USD-denominated "
              "crypto operation a clean, low-friction base with no FX exposure on settlement."]),
            ("Where Founders Get It Wrong",
             ["The 0% rate applies to <em>foreign-source</em> income, not automatically to everything. Revenue "
              "with a genuine Panamanian nexus, local customers, local operations, can be taxable. "
              "Mischaracterising income source is the classic mistake. Document where value is actually generated.",
              "Your home country's tax residency rules also still apply to you personally. A Panama company does "
              "not erase your individual tax obligations where you live. This is why we introduce qualified tax "
              "advisors as part of every setup."]),
            ("Substance and Reputation",
             ["Post-FATF-grey-list (Panama exited in October 2023), substance matters more than it used to. "
              "Banks and counterparties increasingly want to see real operational substance, not just a shell. "
              "Plan for genuine management, record-keeping and a credible compliance function.",
              f"Our <a href='{SITE}/company-setup/'>company setup</a> guidance covers building appropriate "
              "substance from day one."]),
            ("The Net Effect",
             ["For the right business, offshore-facing, USD-settled, not chasing EU retail, Panama's "
              "territorial system is a legitimate and meaningful efficiency. For an EU-retail exchange, the tax "
              "saving rarely outweighs the lack of a MiCA passport."]),
        ],
        "faqs": [
            ("Is the 0% rate a loophole?",
             "No. Territorial taxation is Panama's longstanding, lawful system. The key is correctly classifying "
             "foreign-source versus Panamanian-source income."),
            ("Do I still pay tax at home?",
             "Likely yes, depending on your personal tax residency. A Panama company does not remove your "
             "individual obligations. Take local advice."),
            ("Is there VAT on crypto services?",
             "Panama's ITBMS (its VAT equivalent) generally applies to services consumed in Panama. Foreign-facing "
             "services are typically outside its scope, but confirm specifics with counsel."),
        ],
        "related": [
            ("Cost breakdown", "/cost/"),
            ("Panama crypto license guide", "/"),
            ("Requirements checklist", "/requirements/"),
        ],
    },
    {
        "slug": "panama-private-interest-foundation-crypto-treasury",
        "title": "Panama Private Interest Foundation: The Crypto Treasury Structure Explained",
        "keyword": "Panama foundation crypto treasury",
        "landing": "/company-setup/",
        "labels": ["Panama", "Foundation", "Treasury", "DAO"],
        "lede": "Token treasuries, DAO foundations and family-office crypto holdings need a structure "
                "that separates assets from operations. In Panama, that structure is the Private "
                "Interest Foundation. Here is how it is used in crypto.",
        "sections": [
            ("What a Private Interest Foundation Is",
             ["A Panama Private Interest Foundation is an orphan legal entity with no shareholders, it owns "
              "itself and is governed by a foundation charter and a council. It is built for asset protection "
              "and succession, which makes it well suited to holding a token treasury or long-term crypto "
              "reserves separate from any operating company.",
              "The minimum endowment is roughly $10,000. It is frequently paired with an operating Sociedad "
              "An&oacute;nima: the S.A. runs the business, the foundation holds the treasury."]),
            ("Why DAOs and Token Projects Use It",
             ["A foundation can act as the legal wrapper for a DAO, signing contracts, holding the treasury, "
              "and providing a point of legal responsibility that a purely on-chain DAO lacks. Because it has no "
              "owners, it aligns with the ownerless ethos of a DAO while still being able to interface with banks, "
              "exchanges and counterparties.",
              f"We cover wrapper options in our <a href='{SITE}/company-setup/'>company setup</a> guidance."]),
            ("Asset Protection and Succession",
             ["Assets endowed to the foundation are legally separated from the founder's personal estate, which "
              "provides protection and a clear succession path defined in the charter. For family offices holding "
              "significant crypto, this separation is the entire point."]),
            ("Practical Considerations",
             ["A foundation still needs a registered agent, a council, and, for banking, the same "
              "compliance and source-of-funds rigour as any other crypto-adjacent applicant. It is not a way to "
              "avoid KYC; it is a way to structure ownership and protection cleanly."]),
        ],
        "faqs": [
            ("Can a foundation trade actively?",
             "It can hold and manage assets, but active trading or customer-facing operations usually belong in "
             "an operating S.A. The common pattern is foundation-holds, company-operates."),
            ("Who controls the foundation?",
             "A council, guided by the charter and optional by-laws. The founder can retain influence through the "
             "charter while keeping legal separation."),
            ("What is the minimum endowment?",
             "Around $10,000. This is the asset base the foundation is established with."),
        ],
        "related": [
            ("Panama crypto license guide", "/"),
            ("Cost breakdown", "/cost/"),
            ("Requirements checklist", "/requirements/"),
        ],
    },
    {
        "slug": "panama-crypto-banking-guide-2026",
        "title": "Banking a Panama Crypto Company in 2026: How to Get Approved",
        "keyword": "Panama crypto banking",
        "landing": "/application-process/",
        "labels": ["Panama", "Banking", "Compliance"],
        "lede": "Incorporation is the easy part. Banking is where most Panama crypto setups stall. "
                "Here is what Panamanian banks actually want to see in 2026 and how to get approved "
                "the first time.",
        "sections": [
            ("Why Banking Is the Hard Part",
             ["Since 2023, Panamanian banks have tightened KYC for crypto-adjacent businesses, partly in response "
              "to FATF scrutiny (Panama exited the grey list in October 2023). Banks now expect a complete, "
              "professional application. A thin file is rejected, and re-applying wastes weeks.",
              f"Our <a href='{SITE}/application-process/'>application process</a> sequences incorporation and "
              "banking so the file is ready when you approach the bank."]),
            ("What the Bank Wants to See",
             ["A documented AML/KYC compliance program with a named compliance officer. A clear, evidenced "
              "source-of-funds for both the company and beneficial owners. A coherent business description "
              "explaining who your customers are and how money moves. And realistic projected volumes.",
              "The narrative matters as much as the documents: banks approve businesses they understand."]),
            ("Timeline and Sequencing",
             ["Expect 2-5 weeks for banking onboarding once the file is complete. Sequencing is everything: "
              "incorporate the S.A., build the compliance program, assemble the source-of-funds package, then "
              "approach the bank with introductions in hand. Approaching banks cold, mid-setup, is the most "
              "common self-inflicted delay."]),
            ("Payment Processors and Fiat Rails",
             ["Alongside a bank account, crypto-friendly payment processors give you usable fiat on/off-ramps. "
              "We make direct introductions to rails that work with Panama-incorporated crypto businesses. "
              "Panama's USD legal tender means no FX conversion friction on USD settlement."]),
        ],
        "faqs": [
            ("Can you guarantee a bank account?",
             "No reputable advisor can guarantee a bank decision. What we do is maximise approval odds with a "
             "complete file and the right introductions, which is the difference between approval and "
             "rejection in practice."),
            ("How many banks should I apply to?",
             "Usually we target the best-fit introductions first rather than spraying applications, which can "
             "harm your profile. Quality of file beats quantity of applications."),
            ("Do payment processors need the same documents?",
             "Largely yes, the same compliance program and source-of-funds file serves both bank and "
             "processor onboarding."),
        ],
        "related": [
            ("Requirements checklist", "/requirements/"),
            ("Cost breakdown", "/cost/"),
            ("Exchange license options", "/exchange-license/"),
        ],
    },
]

# ── keyword-driven generator (other jurisdictions) ───────────────────────────
# Facts are best-effort 2026 ranges and general guidance, not legal advice
# (every article carries the disclaimer). Panama is hand-authored above; this
# generator covers the other jurisdictions Consulting24 serves and always
# links back to consulting24.co landing pages.

YEAR = 2026
PANAMA_COST = "$15,000–$45,000"
PANAMA_TIME = "6–12 weeks"

JURISDICTIONS: list[dict] = [
    {"name": "Lithuania", "slug": "lithuania",
     "regime": "EU MiCA CASP authorisation (transitioned from the old VASP register)",
     "authority": "the Bank of Lithuania",
     "cost": "$50,000–$120,000", "timeline": "4–8 months",
     "tax": "15% corporate income tax, with reliefs for small companies",
     "region": "the European Union",
     "best_for": "exchanges and wallets that need to serve EU retail customers under a MiCA passport",
     "not_for": "founders who only need an offshore base and have no EU retail ambitions",
     "note": "Lithuania absorbed most operators who left Estonia after the 2024 crackdown and is now the default EU crypto base."},
    {"name": "Dubai (VARA)", "slug": "dubai-vara",
     "regime": "a VARA virtual-asset licence (with ADGM and DFSA as alternative routes)",
     "authority": "the Virtual Assets Regulatory Authority (VARA)",
     "cost": "$100,000+ all-in", "timeline": "6–12 months",
     "tax": "0% personal income tax and 9% corporate tax above the threshold",
     "region": "the UAE and wider MENA region",
     "best_for": "institutional and MENA-facing exchanges that want a top-tier regulator badge",
     "not_for": "early-stage projects on a tight budget",
     "note": "VARA is rigorous and expensive but carries strong international credibility."},
    {"name": "Canada (MSB)", "slug": "canada-msb",
     "regime": "a FINTRAC money-services-business (MSB) registration",
     "authority": "FINTRAC",
     "cost": "$8,000–$25,000", "timeline": "3–6 weeks",
     "tax": "standard Canadian corporate tax",
     "region": "North America",
     "best_for": "crypto-to-fiat exchanges that need North American fiat rails",
     "not_for": "businesses targeting EU retail, since there is no MiCA passport",
     "note": "Fast, affordable and credible for North-American-facing operations."},
    {"name": "BVI", "slug": "bvi",
     "regime": "registration under the BVI VASP Act 2022",
     "authority": "the BVI Financial Services Commission",
     "cost": "$25,000–$60,000", "timeline": "8–16 weeks",
     "tax": "0% on corporate income",
     "region": "the Caribbean offshore market",
     "best_for": "offshore operators who want more legal certainty than a pure-offshore shell",
     "not_for": "businesses needing EU retail access",
     "note": "A stronger statutory framework than many pure-offshore alternatives since the 2022 VASP Act."},
    {"name": "Estonia", "slug": "estonia",
     "regime": "VASP authorisation, now folded into the EU MiCA regime",
     "authority": "the Estonian FIU",
     "cost": "$30,000–$70,000", "timeline": "4–6 months",
     "tax": "0% on retained profits and 20% on distributions",
     "region": "the European Union",
     "best_for": "operators with existing Estonian substance",
     "not_for": "new entrants — most now migrate to Lithuania",
     "note": "The 2024 crackdown sharply reduced Estonia's appeal; approach with caution."},
    {"name": "El Salvador", "slug": "el-salvador",
     "regime": "a Digital Asset Service Provider (DASP) registration under the Bitcoin Law framework",
     "authority": "the National Digital Assets Commission (CNAD)",
     "cost": "$30,000–$100,000", "timeline": "2–5 months",
     "tax": "0% on digital-asset gains",
     "region": "Latin America",
     "best_for": "Bitcoin-native and LATAM-facing businesses",
     "not_for": "businesses needing an EU passport",
     "note": "Bitcoin is legal tender; the framework is pioneering but still young."},
    {"name": "Switzerland", "slug": "switzerland",
     "regime": "FINMA authorisation or SRO membership",
     "authority": "FINMA",
     "cost": "$80,000–$200,000", "timeline": "4–9 months",
     "tax": "competitive cantonal corporate rates",
     "region": "Europe (non-EU)",
     "best_for": "high-credibility token issuers and institutional players",
     "not_for": "budget-constrained startups",
     "note": "The Zug 'Crypto Valley' ecosystem gives Switzerland a premium reputation."},
    {"name": "Malta", "slug": "malta",
     "regime": "MiCA CASP authorisation (formerly the VFA Act)",
     "authority": "the MFSA",
     "cost": "$40,000–$90,000", "timeline": "4–8 months",
     "tax": "a low effective rate via Malta's refund system",
     "region": "the European Union",
     "best_for": "EU-facing operators who want an established crypto-friendly regulator",
     "not_for": "those chasing the lowest possible cost",
     "note": "An early mover ('Blockchain Island'), now operating under MiCA."},
    {"name": "Cayman Islands", "slug": "cayman",
     "regime": "registration or licensing under the Cayman VASP Act",
     "authority": "the Cayman Islands Monetary Authority (CIMA)",
     "cost": "$30,000–$80,000", "timeline": "3–6 months",
     "tax": "0% on corporate income",
     "region": "the Caribbean offshore market",
     "best_for": "crypto funds and institutional vehicles",
     "not_for": "low-budget startups",
     "note": "Particularly favoured by crypto funds and structured vehicles."},
    {"name": "Czech Republic", "slug": "czech-republic",
     "regime": "EU MiCA CASP authorisation (historically a light-touch trade licence)",
     "authority": "the Czech National Bank",
     "cost": "$15,000–$40,000", "timeline": "2–4 months",
     "tax": "19% corporate income tax",
     "region": "the European Union",
     "best_for": "cost-sensitive operators who want an EU base",
     "not_for": "those needing a premium regulator badge",
     "note": "Historically one of the cheapest EU routes; tightening under MiCA."},
    {"name": "Poland", "slug": "poland",
     "regime": "EU MiCA CASP authorisation (from the former VASP register)",
     "authority": "the Polish Financial Supervision Authority (KNF)",
     "cost": "$15,000–$45,000", "timeline": "2–5 months",
     "tax": "19% corporate income tax",
     "region": "the European Union",
     "best_for": "cost-sensitive EU operators",
     "not_for": "premium-badge seekers",
     "note": "An affordable EU base now transitioning fully to MiCA."},
    {"name": "Georgia", "slug": "georgia",
     "regime": "VASP registration, with free-industrial-zone options",
     "authority": "the National Bank of Georgia",
     "cost": "$10,000–$30,000", "timeline": "3–8 weeks",
     "tax": "0% inside the free industrial zones",
     "region": "the Eurasia region",
     "best_for": "a low-cost, fast offshore-style base outside the EU",
     "not_for": "businesses needing EU retail access or top-tier recognition",
     "note": "Cheap and fast, but with lower international recognition than EU or major offshore hubs."},
    {"name": "Seychelles", "slug": "seychelles",
     "regime": "registration under the Seychelles VASP Act 2024",
     "authority": "the Financial Services Authority (FSA)",
     "cost": "$15,000–$40,000", "timeline": "6–12 weeks",
     "tax": "0% on foreign-source income",
     "region": "the offshore market",
     "best_for": "offshore exchanges and token projects on a budget",
     "not_for": "EU retail or premium-badge needs",
     "note": "A popular budget offshore option, newly formalised by the 2024 VASP Act."},
]

# Internal landing page per angle (all real consulting24.co pages).
_ANGLE_LANDING = {
    "guide": "/",
    "cost": "/cost/",
    "requirements": "/requirements/",
    "vs-panama": "/vs-lithuania/",
}

def _related_for(angle: str) -> list[tuple[str, str]]:
    base = [
        ("Panama crypto license guide", "/"),
        ("Cost breakdown", "/cost/"),
        ("Panama vs Lithuania", "/vs-lithuania/"),
        ("Requirements checklist", "/requirements/"),
        ("Application process", "/application-process/"),
        ("Exchange license options", "/exchange-license/"),
    ]
    # rotate so related lists differ a little per angle
    order = {"guide": 0, "cost": 1, "requirements": 3, "vs-panama": 2}.get(angle, 0)
    rotated = base[order:] + base[:order]
    return rotated[:3]

def _gen_guide(j: dict) -> dict:
    n = j["name"]
    return {
        "slug": f"{j['slug']}-crypto-license-{YEAR}-guide",
        "title": f"{n} Crypto License {YEAR}: Cost, Requirements and Timeline",
        "keyword": f"{n} crypto license",
        "labels": [n.split(" (")[0], "Crypto License", "Guide"],
        "lede": f"Thinking about a {n} crypto license? Here is a clear {YEAR} overview of the "
                f"regime, what it costs, how long it takes, and whether {n} is the right base for "
                f"your business — with an honest comparison to Panama.",
        "sections": [
            (f"How {n} Regulates Crypto",
             [f"{n} works through {j['regime']}, supervised by {j['authority']}. {j['note']}",
              f"Whether that fits depends on your customers and goals. {n} is generally the right "
              f"choice for {j['best_for']}, and a poor fit for {j['not_for']}."]),
            ("Cost and Timeline",
             [f"Budget roughly {j['cost']} to set up in {n}, with a realistic timeline of {j['timeline']}. "
              f"By comparison, a Panama Sociedad An&oacute;nima sets up in {PANAMA_TIME} for {PANAMA_COST} all-in "
              f"the first year — faster and cheaper, but without an EU passport.",
              f"See our <a href='{SITE}/cost/'>cost breakdown</a> for how Panama's line items compare, and "
              f"our <a href='{SITE}/application-process/'>application process</a> for the end-to-end steps."]),
            ("Tax and Banking",
             [f"On tax, {n} applies {j['tax']}. Banking, as everywhere in crypto, is the real gating factor: "
              f"expect to present a documented AML/KYC program and a clean source-of-funds file before any "
              f"bank or payment processor will onboard you.",
              f"Panama, by contrast, taxes foreign-source income at 0% and uses the US dollar as legal tender, "
              f"which removes FX risk on USD settlement — one reason offshore-facing operators shortlist it."]),
            (f"Is {n} Right for You?",
             [f"Choose {n} if your priority is {j['best_for']}. Look elsewhere if you are {j['not_for']}.",
              f"If you are weighing {n} against an offshore base, read our "
              f"<a href='{SITE}/vs-lithuania/'>Panama vs Lithuania</a> comparison — the same decision "
              f"framework applies, and we are happy to map it to {n} for your specific model."]),
        ],
        "faqs": [
            (f"How much does a {n} crypto license cost?",
             f"Roughly {j['cost']} to set up, plus ongoing annual maintenance. The range depends on scope — "
             f"compliance program, banking introductions and any nominee or substance requirements."),
            (f"How long does {n} take?",
             f"Around {j['timeline']} end to end, assuming a complete application. Incomplete documentation is "
             f"the most common cause of delay anywhere."),
            (f"Is {n} better than Panama?",
             f"It depends on your customers. {n} suits {j['best_for']}; Panama wins on speed, cost and "
             f"territorial-tax efficiency for offshore-facing businesses. We help clients choose objectively."),
        ],
    }

def _gen_cost(j: dict) -> dict:
    n = j["name"]
    return {
        "slug": f"{j['slug']}-crypto-license-cost",
        "title": f"How Much Does a {n} Crypto License Cost in {YEAR}?",
        "keyword": f"{n} crypto license cost",
        "labels": [n.split(" (")[0], "Cost", "Crypto License"],
        "lede": f"Quotes for a {n} crypto license vary widely because providers bundle different things. "
                f"Here is an honest view of what it actually costs in {YEAR} — and how that stacks up "
                f"against Panama.",
        "sections": [
            (f"The Headline Number: {j['cost']}",
             [f"A {n} setup typically runs {j['cost']} in the first year. That covers {j['regime']} via "
              f"{j['authority']}, plus the compliance and corporate work around it. {j['note']}",
              f"Panama, for comparison, is {PANAMA_COST} all-in for year one — useful as a price anchor when "
              f"you read a {n} quote. See our <a href='{SITE}/cost/'>full cost breakdown</a>."]),
            ("What Drives the Cost",
             [f"The big cost drivers are the same everywhere: the licensing/registration fees, a documented "
              f"AML/KYC compliance program, banking and payment-processor onboarding, and any nominee or local "
              f"substance requirements. In {n}, the {j['regime'].split('(')[0].strip()} is the largest single line.",
              "A thin compliance file is a false economy — it gets rejected at the banking stage and costs you "
              "weeks. Budget for it properly up front."]),
            ("Ongoing Annual Cost",
             [f"On top of setup, plan for annual maintenance: renewal/supervision fees, accounting, and keeping "
              f"the compliance program live. Tax treatment matters too — {n} applies {j['tax']}, versus Panama's "
              f"0% on foreign-source income.",
              f"Our <a href='{SITE}/requirements/'>requirements checklist</a> shows what you maintain after "
              f"go-live so nothing lapses."]),
            ("Getting an Honest Quote",
             [f"Ask any provider to itemise: incorporation, licence/registration, compliance program, banking "
              f"introductions, and year-two maintenance. Open-ended hourly arrangements are where {n} budgets "
              f"overrun.",
              "Consulting24 provides fixed-fee proposals once we understand your model and target markets, so "
              "you know the all-in number before you commit."]),
        ],
        "faqs": [
            (f"What is the cheapest way to get a {n} crypto license?",
             f"Keep scope tight, but never cut the compliance program — that is what unlocks banking. Expect at "
             f"least the lower end of {j['cost']}."),
            ("Are there hidden costs?",
             "The two most underestimated are banking lead time and compliance documentation. Both are "
             "controllable with a complete file."),
            ("How does this compare to Panama?",
             f"Panama is {PANAMA_COST} for year one in {PANAMA_TIME}, with 0% tax on foreign-source income — "
             f"often the cheaper, faster route for offshore-facing businesses."),
        ],
    }

def _gen_requirements(j: dict) -> dict:
    n = j["name"]
    return {
        "slug": f"{j['slug']}-crypto-license-requirements",
        "title": f"{n} Crypto License Requirements: {YEAR} Checklist",
        "keyword": f"{n} crypto license requirements",
        "labels": [n.split(" (")[0], "Requirements", "Compliance"],
        "lede": f"Incomplete paperwork is the number-one cause of delay in any crypto licensing project. "
                f"Here is what {n} actually requires in {YEAR}, and how to assemble a file that gets "
                f"approved the first time.",
        "sections": [
            ("Corporate and Licensing Requirements",
             [f"To operate in {n} you work through {j['regime']}, supervised by {j['authority']}. That means a "
              f"local operating entity, fit-and-proper directors, and a clearly described business activity.",
              f"{j['note']} We confirm the current requirements with local counsel for every engagement, since "
              f"crypto rules change frequently."]),
            ("AML/KYC Compliance Program",
             ["No bank or payment processor will onboard a crypto business without a documented compliance "
              "program: a KYC onboarding flow, transaction monitoring, sanctions screening, a designated "
              "compliance officer, and record-keeping policies.",
              f"This is the document that determines whether banking succeeds in {n}, so it is worth doing "
              f"properly. Our <a href='{SITE}/requirements/'>requirements checklist</a> shows the full intake."]),
            ("Documentation and Timeline",
             [f"Expect to evidence source of funds for the company and beneficial owners, plus standard KYC on "
              f"directors. With a complete file, {n} runs about {j['timeline']}.",
              f"Sequencing matters: incorporate, build the compliance program, assemble the source-of-funds "
              f"package, then approach banking with introductions in hand."]),
            ("Common Pitfalls",
             [f"The usual failures are a thin compliance program, an unexplained source of funds, and approaching "
              f"banks cold mid-setup. Each one costs weeks.",
              f"If {n}'s requirements feel heavy for your stage, Panama is a lighter, faster alternative for "
              f"offshore-facing businesses — see our <a href='{SITE}/'>Panama crypto license guide</a>."]),
        ],
        "faqs": [
            (f"What documents do I need for {n}?",
             "Passports and proof of address for directors and beneficial owners, a business description, and a "
             "documented AML/KYC program with source-of-funds evidence."),
            ("Do I need a local director?",
             f"Requirements vary by jurisdiction; some need local substance. We confirm {n}'s current rules with "
             f"local counsel and arrange what is needed."),
            ("What slows applications down most?",
             "Incomplete documentation and a weak compliance file. Both are within your control."),
        ],
    }

def _gen_vs_panama(j: dict) -> dict:
    n = j["name"]
    return {
        "slug": f"{j['slug']}-vs-panama-crypto-license",
        "title": f"{n} vs Panama for a Crypto License: Which Should You Choose?",
        "keyword": f"{n} vs Panama crypto license",
        "labels": [n.split(" (")[0], "Panama", "Comparison"],
        "lede": f"Should you license in {n} or Panama? The right answer depends entirely on who your "
                f"customers are. Here is the decision framework we use with clients.",
        "sections": [
            ("The Core Trade-off",
             [f"{n} works through {j['regime']} ({j['authority']}), costs about {j['cost']}, and takes "
              f"{j['timeline']}. Panama uses a Sociedad An&oacute;nima with no dedicated VASP regime, costs "
              f"{PANAMA_COST}, and takes {PANAMA_TIME}.",
              f"In short: {n} typically buys you regulatory standing in {j['region']}; Panama buys you speed, "
              f"low cost and 0% tax on foreign-source income."]),
            (f"When {n} Wins",
             [f"Pick {n} if your priority is {j['best_for']}. {j['note']}",
              f"On tax, {n} applies {j['tax']} — factor that into the total cost of ownership, not just the "
              f"setup fee."]),
            ("When Panama Wins",
             ["Panama wins for offshore-first operations that do not need an EU or onshore passport: businesses "
              "targeting Latin America, Asia or HNW clients, founders who value fast incorporation, and anyone "
              "prioritising territorial-tax efficiency.",
              f"It is the wrong choice if you specifically need {n}'s market access or regulator badge — be "
              f"honest with yourself about which you actually require."]),
            ("How to Decide",
             [f"Map it to customers first, cost second. If you need {j['region']} access, lean {n}. If you are "
              f"offshore-facing and want to move fast, lean Panama.",
              f"Our <a href='{SITE}/vs-lithuania/'>Panama vs Lithuania</a> page lays out the same logic in "
              f"detail, and we will happily map it to {n} for your exact model."]),
        ],
        "faqs": [
            (f"Is {n} more expensive than Panama?",
             f"Generally yes — {n} runs {j['cost']} versus Panama at {PANAMA_COST}. You pay for {n}'s market "
             f"access and regulatory standing."),
            ("Can I start in Panama and move later?",
             f"Yes. Many founders launch offshore in Panama to validate the business, then add a {n} entity once "
             f"revenue justifies the cost and the market access is needed."),
            (f"Which is faster, {n} or Panama?",
             f"Panama, almost always — {PANAMA_TIME} versus {j['timeline']} for {n}."),
        ],
    }

_GENERATORS = {
    "guide": _gen_guide, "cost": _gen_cost,
    "requirements": _gen_requirements, "vs-panama": _gen_vs_panama,
}

def _generate() -> list[dict]:
    out = []
    for j in JURISDICTIONS:
        for angle, fn in _GENERATORS.items():
            topic = fn(j)
            topic["landing"] = _ANGLE_LANDING[angle]
            topic["related"] = _related_for(angle)
            out.append(topic)
    return out

# Final queue: hand-authored Panama articles first, then generated coverage.
ARTICLES: list[dict] = PANAMA_ARTICLES + _generate()

# Merge DeepSeek-generated posts (config/extra_posts.json) so Blogger keeps fresh
# content daily. Each entry: {slug,title,keyword,landing,lede,sections:[[h,[p]]],faqs:[[q,a]],related:[[l,p]],labels:[]}
_EXTRA_POSTS_PATH = ROOT / "config" / "extra_posts.json"
if _EXTRA_POSTS_PATH.exists():
    try:
        _seenp = {a["slug"] for a in ARTICLES}
        for _a in json.loads(_EXTRA_POSTS_PATH.read_text()):
            if _a.get("slug") and _a["slug"] not in _seenp:
                _a["sections"] = [tuple(s) for s in _a.get("sections", [])]
                _a["faqs"] = [tuple(f) for f in _a.get("faqs", [])]
                _a["related"] = [tuple(r) for r in _a.get("related", [])]
                ARTICLES.append(_a); _seenp.add(_a["slug"])
    except Exception as _e:
        print(f"WARN: could not load extra_posts.json: {_e}", file=sys.stderr)

# ── pillar PAGES (head keywords, LLM + SEO optimised) ────────────────────────
# Blogger Pages are static cornerstone pages. They target broad head terms and
# act as the hubs of the topic cluster; the daily posts are the long-tail spokes.
# Each page is answer-first (TL;DR), carries a citable comparison table and
# FAQPage JSON-LD schema, and cross-links the other pages + consulting24.co.

def _tldr(text: str) -> str:
    return (f'<div style="background:#eef4ff;border:1px solid #cfe0f5;border-radius:8px;'
            f'padding:16px 20px;margin:0 0 26px;">'
            f'<strong style="color:#0b1f3a;">In short:</strong> {text}</div>')

def _comparison_table() -> str:
    rows = [
        ("Panama", "Sociedad An&oacute;nima (no dedicated VASP regime)", PANAMA_COST,
         PANAMA_TIME, "0% on foreign-source income", "Offshore / LatAm / Asia / HNW"),
    ]
    pick = {"Lithuania", "Canada (MSB)", "Dubai (VARA)", "BVI", "Estonia"}
    for j in JURISDICTIONS:
        if j["name"] in pick:
            rows.append((j["name"], j["regime"].split("(")[0].strip(), j["cost"],
                         j["timeline"], j["tax"].split(",")[0], j["region"]))
    head = ("<tr style='background:#0b1f3a;color:#fff;'>"
            "<th style='padding:8px;text-align:left;'>Jurisdiction</th>"
            "<th style='padding:8px;text-align:left;'>Regime</th>"
            "<th style='padding:8px;text-align:left;'>Setup cost</th>"
            "<th style='padding:8px;text-align:left;'>Timeline</th>"
            "<th style='padding:8px;text-align:left;'>Tax</th>"
            "<th style='padding:8px;text-align:left;'>Best for</th></tr>")
    body = ""
    for i, r in enumerate(rows):
        bg = "#f7fafd" if i % 2 else "#ffffff"
        body += f"<tr style='background:{bg};'>" + "".join(
            f"<td style='padding:8px;border-bottom:1px solid #e6eef7;'>{c}</td>" for c in r
        ) + "</tr>"
    return ("<h2>Crypto License Comparison by Jurisdiction (2026)</h2>"
            "<div style='overflow-x:auto;'><table style='border-collapse:collapse;width:100%;"
            "font-size:14px;margin:8px 0 4px;'>" + head + body + "</table></div>"
            "<p style='font-size:13px;color:#777;'>Figures are indicative 2026 ranges. "
            "Ask us for a fixed-fee proposal for your specific model.</p>")

def _faq_jsonld(faqs: list[tuple[str, str]]) -> str:
    import json as _json, re as _re
    entities = []
    for q, a in faqs:
        clean = _re.sub("<[^>]+>", "", a)
        entities.append({"@type": "Question", "name": q,
                         "acceptedAnswer": {"@type": "Answer", "text": clean}})
    data = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": entities}
    return f'<script type="application/ld+json">{_json.dumps(data)}</script>'

PAGES: list[dict] = [
    {
        "slug": "crypto-license-panama",
        "title": "Crypto License in Panama: Cost, Requirements & Setup (2026)",
        "keyword": "crypto license Panama",
        "landing": "/",
        "tldr": "Panama has no single dedicated crypto/VASP licence. Crypto businesses incorporate a "
                "Panama Sociedad An&oacute;nima (2-3 weeks, no minimum capital) and operate under "
                "existing financial-services and AML law, supervised in spirit by UAF Panama. Expect "
                f"{PANAMA_COST} all-in for year one, {PANAMA_TIME} end to end, and 0% tax on "
                "foreign-source income. Best for offshore-facing businesses serving LatAm, Asia or HNW "
                "clients, not EU retail (use a MiCA jurisdiction for that).",
        "table": True,
        "sections": [
            ("How Crypto Is Regulated in Panama",
             ["Panama does not have a standalone crypto or VASP licence as of 2026. Bill 697, which would "
              "have created one, was vetoed in 2022 and reform is still pending. Instead, crypto activities "
              "run under Panama's existing financial-services frameworks, with AML/CFT supervised by UAF "
              "Panama (the local FinCEN equivalent) and money-services activity falling under the "
              "Superintendency of Banks of Panama.",
              "In practice this means you incorporate a Panama Sociedad An&oacute;nima, run a documented "
              "AML/KYC program, and operate lawfully, rather than applying for a named licence. For "
              "asset-holding structures such as token treasuries, a Panama Private Interest Foundation is "
              f"paired with the operating company. See our <a href='{SITE}/company-setup/'>company setup</a> "
              "guidance for the full picture."]),
            ("Cost, Timeline and Tax",
             [f"Budget {PANAMA_COST} all-in for the first year and {PANAMA_TIME} end to end, materially "
              "faster and cheaper than an EU MiCA authorisation. Annual maintenance runs $5,000-$15,000.",
              "Panama's territorial tax system charges 0% on foreign-source income, and the country uses the "
              "US dollar as legal tender (1:1 with the balboa), removing FX risk on USD settlement. See the "
              f"full <a href='{SITE}/cost/'>cost breakdown</a> and <a href='{SITE}/requirements/'>requirements "
              "checklist</a>."]),
        ],
        "faqs": [
            ("Does Panama have a crypto license?",
             "No. Panama has no dedicated crypto/VASP licence as of 2026. Businesses incorporate a Sociedad "
             "An&oacute;nima and operate under existing financial-services and AML law."),
            ("How much does a Panama crypto setup cost?",
             f"Around {PANAMA_COST} all-in for year one, with $5,000-$15,000 annual maintenance."),
            ("Is crypto income taxed in Panama?",
             "Foreign-source income is taxed at 0% under Panama's territorial system. Panama-source income "
             "can be taxable."),
            ("Who should choose Panama?",
             "Offshore-facing businesses serving Latin America, Asia or high-net-worth clients. EU-retail "
             "exchanges should use a MiCA jurisdiction such as Lithuania."),
        ],
    },
    {
        "slug": "crypto-exchange-license",
        "title": "Crypto Exchange License: How and Where to Get One in 2026",
        "keyword": "crypto exchange license",
        "landing": "/exchange-license/",
        "tldr": "There is no single global “crypto exchange license.” The right route depends on your "
                "customers: EU retail needs a MiCA CASP authorisation (e.g. Lithuania); North American "
                "fiat exchanges fit a Canada MSB; offshore/HNW operators often choose Panama or BVI; "
                "institutional MENA players choose Dubai VARA. Cost ranges from ~$8,000 (Canada MSB) to "
                "$120,000+ (EU/VARA), and timelines from 3 weeks to 12 months.",
        "table": True,
        "sections": [
            ("There Is No Universal Exchange License",
             ["“Crypto exchange license” is shorthand for several very different regimes. What you "
              "actually need is determined by where your customers are and whether you require a regulator "
              "badge. An EU-retail order-book exchange needs a MiCA CASP authorisation to passport across "
              "Europe. A crypto-to-fiat exchange serving North America fits a FINTRAC MSB registration in "
              "Canada. An OTC desk serving offshore and HNW clients often runs from Panama or the BVI.",
              "The most expensive mistake is licensing to the wrong audience and having to re-domicile a live "
              f"exchange. Map customers first. Our <a href='{SITE}/exchange-license/'>exchange license "
              "page</a> walks through order-book, brokerage and OTC structures."]),
            ("Structure, Banking and Fiat Rails",
             ["Most exchange operators use a clean operating entity plus a separate vehicle for any token or "
              "treasury. Banking is the real gating factor everywhere: you need fiat on/off-ramps, which means "
              "a bank account and crypto-friendly payment-processor relationships, backed by a documented "
              "compliance program and source-of-funds file.",
              "If you serve EU retail you additionally need an EU-licensed entity under MiCA, an offshore "
              f"base alone does not passport into Europe. Compare the routes on our "
              f"<a href='{SITE}/vs-lithuania/'>Panama vs Lithuania</a> page."]),
        ],
        "faqs": [
            ("What license do I need to run a crypto exchange?",
             "It depends on your customers: MiCA CASP for EU retail, Canada MSB for North American fiat, "
             "Panama or BVI for offshore/HNW, Dubai VARA for institutional MENA."),
            ("How much does a crypto exchange license cost?",
             "From roughly $8,000 (Canada MSB) to $120,000+ (EU MiCA or Dubai VARA), depending on the regime."),
            ("Can one license cover the whole world?",
             "No. There is no global passport. Many operators combine an offshore base with a regulated EU "
             "entity to cover both markets."),
            ("What is the fastest exchange license to get?",
             "A Canada MSB registration is among the fastest at 3-6 weeks; Panama incorporation is "
             "2-3 weeks."),
        ],
    },
    {
        "slug": "crypto-license-cost",
        "title": "Crypto License Cost by Jurisdiction: 2026 Comparison",
        "keyword": "crypto license cost",
        "landing": "/cost/",
        "tldr": "Crypto licence costs in 2026 range from ~$8,000 (Canada MSB) and ~$15,000 (Panama) at the "
                "low end to $120,000+ for EU MiCA and Dubai VARA. The setup fee is only part of the picture "
                ", budget for the AML/KYC compliance program, banking introductions, and year-two "
                "maintenance. The cheapest licence that gets your bank application rejected is the most "
                "expensive option of all.",
        "table": True,
        "sections": [
            ("What Drives Crypto License Cost",
             ["Across every jurisdiction the cost drivers are the same: the licence or registration fee, a "
              "documented AML/KYC compliance program, banking and payment-processor onboarding, corporate "
              "incorporation, and any nominee or local-substance requirements. The jurisdiction's regime is "
              "usually the largest single line, but compliance is the one founders underbudget.",
              f"Panama sits near the affordable end at {PANAMA_COST} all-in for year one; EU MiCA and Dubai "
              "VARA sit at the premium end because you are paying for market access and a regulator badge. "
              f"See the itemised <a href='{SITE}/cost/'>Panama cost breakdown</a>."]),
            ("Ongoing Costs and Total Cost of Ownership",
             ["Setup is one-time; maintenance is forever. Plan for annual renewal/supervision fees, "
              "accounting, and keeping the compliance program live. Tax treatment matters too, a 0% "
              "territorial regime like Panama's can outweigh a lower headline setup fee elsewhere over a few "
              "years.",
              "Always ask a provider to itemise setup versus year-two costs, and to explain their banking "
              "track record. Open-ended hourly engagements are where budgets overrun."]),
        ],
        "faqs": [
            ("What is the cheapest crypto license?",
             "A Canada MSB (~$8,000) and Panama (~$15,000) are among the most affordable credible routes in "
             "2026."),
            ("Why are EU and Dubai licenses so expensive?",
             "You pay for market access and a top-tier regulator badge, MiCA passporting and VARA "
             "credibility carry higher capital, governance and process costs."),
            ("What hidden costs should I expect?",
             "The two most underestimated are banking lead time and a proper compliance program. Skimping on "
             "either causes rejections and delays."),
            ("Is a cheaper license worse?",
             "Not necessarily, it is about fit. A cheap offshore base is ideal for offshore-facing "
             "businesses but useless if you legally need an EU passport."),
        ],
    },
    {
        "slug": "best-crypto-license-jurisdiction",
        "title": "Best Country for a Crypto License in 2026: Jurisdiction Guide",
        "keyword": "best crypto license jurisdiction",
        "landing": "/vs-lithuania/",
        "tldr": "There is no single “best” crypto jurisdiction, only the best fit for your "
                "customers. EU retail → Lithuania or Malta (MiCA). North American fiat → Canada MSB. "
                "Offshore / LatAm / Asia / HNW → Panama or BVI. Institutional MENA → Dubai VARA. "
                "Premium token issuance → Switzerland. Decide on customers and the need for a regulator "
                "badge first; optimise for cost and tax second.",
        "table": True,
        "sections": [
            ("The “Best” Jurisdiction Depends on Your Customers",
             ["Every ranking you read online is really answering a different question. The honest framework "
              "is simple: who are you allowed and required to serve, and do you need a regulator badge? EU "
              "retail forces a MiCA route; US customers force money-transmitter or MSB routes; offshore-facing "
              "businesses get to optimise for speed, cost and tax.",
              "For offshore-first founders, Panama frequently lands at the sweet spot of fast incorporation, "
              "low cost and 0% tax on foreign-source income. For EU retail, Lithuania is the default. For "
              f"North American fiat, Canada. Read the full logic on our "
              f"<a href='{SITE}/vs-lithuania/'>Panama vs Lithuania</a> comparison."]),
            ("Matching Profile to Jurisdiction",
             ["Use the comparison table below as a starting shortlist, then pressure-test it against your real "
              "banking needs. A jurisdiction is only as good as the banking and payment rails your business "
              "can actually access from it, which is why we pair every recommendation with a realistic "
              "banking plan.",
              f"When you are ready, our <a href='{SITE}/application-process/'>application process</a> shows the "
              "end-to-end steps for the Panama route, and we can map the same sequence to any jurisdiction on "
              "the list."]),
        ],
        "faqs": [
            ("What is the best country for a crypto license?",
             "It depends on your customers. Lithuania for EU retail, Canada for North American fiat, Panama or "
             "BVI for offshore/HNW, Dubai for institutional MENA, Switzerland for premium token issuance."),
            ("What is the best low-cost crypto jurisdiction?",
             "Panama and Canada MSB are among the most affordable credible routes; Georgia and Seychelles are "
             "cheaper offshore options with lower international recognition."),
            ("Which jurisdiction is best for an EU exchange?",
             "An EU MiCA jurisdiction such as Lithuania or Malta, which passports across all 27 member states."),
            ("Can I start offshore and move later?",
             "Yes. Many founders validate in a fast offshore base like Panama, then add an EU entity once "
             "revenue justifies MiCA."),
        ],
    },
    {
        "slug": "how-to-get-crypto-license",
        "title": "How to Get a Crypto License: Step-by-Step Guide (2026)",
        "keyword": "how to get a crypto license",
        "landing": "/application-process/",
        "table": True,
        "tldr": "Getting a crypto licence in 2026 follows the same five steps everywhere: (1) choose the "
                "jurisdiction that matches your customers; (2) incorporate the operating entity; (3) build a "
                "documented AML/KYC compliance program; (4) assemble a source-of-funds file and open banking "
                "and payment rails; (5) maintain the licence with ongoing compliance. Timelines run from "
                "3 weeks (Canada MSB / Panama incorporation) to 12 months (EU MiCA / Dubai VARA).",
        "sections": [
            ("The Five Steps to a Crypto License",
             ["<strong>1. Choose the jurisdiction.</strong> Start with your customers and whether you need a "
              "regulator badge. This single decision drives cost, timeline and everything downstream. "
              "<strong>2. Incorporate the operating entity.</strong> A Panama Sociedad An&oacute;nima takes "
              "2-3 weeks; EU entities take longer. "
              "<strong>3. Build the AML/KYC compliance program</strong>, the document your bank reads "
              "most closely.",
              "<strong>4. Open banking and payment rails.</strong> Assemble a clean source-of-funds file and "
              "approach banks through warm introductions, not cold applications. "
              "<strong>5. Maintain the licence</strong> with renewals, accounting and live compliance. "
              f"Our <a href='{SITE}/application-process/'>application process</a> details each step for "
              "Panama."]),
            ("How Long It Takes and What Trips People Up",
             ["End-to-end timelines range from about 3 weeks for a Canada MSB or Panama incorporation to "
              "6-12 months for EU MiCA or Dubai VARA. The controllable parts, document collection "
              "and the compliance program, are also the ones founders most often rush, which is exactly "
              "why banking then stalls.",
              f"Get the file right once and the process is smooth. See the "
              f"<a href='{SITE}/requirements/'>requirements checklist</a> for everything you need to assemble "
              "before you start."]),
        ],
        "faqs": [
            ("How do I get a crypto license?",
             "Choose a jurisdiction that matches your customers, incorporate, build an AML/KYC compliance "
             "program, open banking with a source-of-funds file, then maintain the licence."),
            ("How long does it take to get a crypto license?",
             "From about 3 weeks (Canada MSB / Panama incorporation) to 6-12 months (EU MiCA / Dubai "
             "VARA)."),
            ("Do I need a lawyer to get a crypto license?",
             "You need qualified local counsel for most regimes. Consulting24 coordinates incorporation, "
             "compliance and banking and introduces vetted local lawyers."),
            ("What is the hardest part of getting a crypto license?",
             "Banking. Incorporation is straightforward; opening bank and payment-processor accounts requires "
             "a complete compliance program and source-of-funds file."),
        ],
    },
]

# Merge DeepSeek-generated pillar pages (config/extra_pages.json).
# Each entry: {slug,title,keyword,landing,tldr,table,sections:[[h,[p,...]],...],faqs:[[q,a],...]}
_EXTRA_PAGES_PATH = ROOT / "config" / "extra_pages.json"
if _EXTRA_PAGES_PATH.exists():
    try:
        _extra = json.loads(_EXTRA_PAGES_PATH.read_text())
        _seen = {p["slug"] for p in PAGES}
        for _p in _extra:
            if _p.get("slug") and _p["slug"] not in _seen:
                _p["sections"] = [tuple(s) for s in _p.get("sections", [])]
                _p["faqs"] = [tuple(f) for f in _p.get("faqs", [])]
                PAGES.append(_p)
                _seen.add(_p["slug"])
    except Exception as _e:
        print(f"WARN: could not load extra_pages.json: {_e}", file=sys.stderr)

def _page_related(current_slug: str, blog_url: str = "", url_map: dict | None = None) -> str:
    base = blog_url.rstrip("/") if blog_url else "https://consultinglegalnews.blogspot.com"
    url_map = url_map or {}
    sib = "".join(
        f'<li><a href="{url_map.get(p["slug"], base + "/p/" + p["slug"] + ".html")}">{p["title"]}</a></li>'
        for p in PAGES if p["slug"] != current_slug
    )
    ext = "".join(f'<li><a href="{SITE}{path}">{label}</a></li>' for label, path in [
        ("Panama crypto license, consulting24.co", "/"),
        ("Cost breakdown", "/cost/"),
        ("Application process", "/application-process/"),
    ])
    return f"<h2>Related guides</h2><ul>{sib}{ext}</ul>"

def render_page(page: dict) -> str:
    body = [_hero_photo(page["keyword"], page.get("slug","")), _hero_image(page["keyword"]), _tldr(page["tldr"])]
    for i, (heading, paras) in enumerate(page["sections"]):
        body.append(f"<h2>{heading}</h2>")
        for p in paras:
            body.append(f"<p>{p}</p>")
        if i == 0:
            body.append(_process_graphic())   # in-content visual after first section
    if page.get("table"):
        body.append(_comparison_table())
    body.append(_evergreen_choosing(page))
    body.append(_evergreen_banking(page))
    body.append(_evergreen_landscape(page))
    body.append(_evergreen_mistakes(page))
    body.append(_evergreen_aftercare(page))
    related_html = _page_related(page["slug"])
    hub = set(re.findall(r'href="([^"]+)"', related_html))
    directory_html = _landing_directory(page.get("landing", ""))
    hub |= set(re.findall(r'href="([^"]+)"', directory_html))
    parts = [_dedupe_links("\n".join(body), seen=hub),
             _cta(page["keyword"], page["landing"]),
             _why_consulting24(),
             _faq(page["faqs"]),
             _faq_jsonld(page["faqs"]),
             related_html,
             directory_html,
             _disclaimer(),
             _author_org_jsonld()]
    return "\n".join(parts)

# ── posting ───────────────────────────────────────────────────────────────

def _is_rate_limit(e: Exception) -> bool:
    s = str(e)
    status = getattr(getattr(e, "resp", None), "status", None)
    if status in (429, 403, 500, 502, 503, 504): return True
    sl = s.lower()
    return ("ratelimit" in sl or "resource has been exhausted" in sl or "quota" in sl
            or "no route to host" in sl or "timed out" in sl or "connection reset" in sl
            or "temporarily unavailable" in sl or "broken pipe" in sl
            or isinstance(e, (TimeoutError, ConnectionError, OSError)))

def with_retry(fn, *args, max_tries: int = 6, base: int = 30, **kwargs):
    """Call fn with exponential backoff on Blogger rate-limit / quota (429/403)."""
    for attempt in range(max_tries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if _is_rate_limit(e) and attempt < max_tries - 1:
                wait = base * (2 ** attempt)  # 30,60,120,240,480s
                log(f"rate-limited (attempt {attempt+1}/{max_tries}); backing off {wait}s")
                time.sleep(wait)
                continue
            raise

def insert_post(blogger, blog_id: str, topic: dict, dry_run: bool) -> dict:
    html = render_article(topic)
    body = {
        "kind": "blogger#post",
        "blog": {"id": blog_id},
        "title": topic["title"],
        "content": html,
        "labels": _labels_for(topic),
    }
    if dry_run:
        log(f"[dry-run] would publish '{topic['title']}' ({len(html)} chars, "
            f"{len(_labels_for(topic))} labels)")
        return {"id": "(dry-run)", "url": f"{SITE}{topic['landing']}"}
    resp = blogger.posts().insert(blogId=blog_id, body=body, isDraft=False).execute()
    return resp

def insert_page(blogger, blog_id: str, page: dict, blog_url: str, dry_run: bool) -> dict:
    # re-render related links against the real blog URL so cross-links resolve
    html = render_page(page).replace(
        _page_related(page["slug"]), _page_related(page["slug"], blog_url))
    body = {
        "kind": "blogger#page",
        "blog": {"id": blog_id},
        "title": page["title"],
        "content": html,
    }
    if dry_run:
        log(f"[dry-run] would publish PAGE '{page['title']}' ({len(html)} chars)")
        return {"id": "(dry-run)", "url": f"{blog_url.rstrip('/')}/p/{page['slug']}.html"}
    return blogger.pages().insert(blogId=blog_id, body=body, isDraft=False).execute()

def update_post(blogger, blog_id: str, post_id: str, topic: dict) -> dict:
    html = render_article(topic)
    body = {"kind": "blogger#post", "blog": {"id": blog_id}, "id": post_id,
            "title": topic["title"], "content": html, "labels": _labels_for(topic)}
    return blogger.posts().update(blogId=blog_id, postId=post_id, body=body).execute()

def update_page(blogger, blog_id: str, page_id: str, page: dict, blog_url: str) -> dict:
    html = render_page(page).replace(
        _page_related(page["slug"]), _page_related(page["slug"], blog_url))
    body = {"kind": "blogger#page", "blog": {"id": blog_id}, "id": page_id,
            "title": page["title"], "content": html}
    return blogger.pages().update(blogId=blog_id, pageId=page_id, body=body).execute()

def next_unposted(state: dict) -> list[dict]:
    return [a for a in ARTICLES if not posted(state, a["slug"])]

def next_unposted_pages(state: dict) -> list[dict]:
    done = state.get("pages", {})
    return [p for p in PAGES if p["slug"] not in done]

def cmd_list(state: dict):
    done = set(state.get("posts", {}).keys())
    print(f"\nArticles: {len(ARTICLES)} total, {len(done)} posted, "
          f"{len(ARTICLES) - len(done)} remaining\n")
    for a in ARTICLES:
        mark = "✓" if a["slug"] in done else " "
        url = state.get("posts", {}).get(a["slug"], {}).get("url", "")
        print(f"  [{mark}] {a['slug']}{('  → ' + url) if url else ''}")
    print()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true", help="run OAuth as mardo@consulting24.co and exit")
    ap.add_argument("--list", action="store_true", help="show queue + posted state and exit")
    ap.add_argument("--dry-run", action="store_true", help="render next post without publishing")
    ap.add_argument("--once", metavar="SLUG", help="publish one specific article slug")
    ap.add_argument("--pages", action="store_true", help="publish unpublished pillar PAGES and exit")
    ap.add_argument("--limit", type=int, default=DAILY_LIMIT)
    ap.add_argument("--delay", type=int, default=20, help="seconds to wait between publishes (rate-limit spacing)")
    ap.add_argument("--update-images", action="store_true",
                    help="re-render and update already-published posts/pages (adds the hero image)")
    ap.add_argument("--force", action="store_true",
                    help="with --update-images, re-update even items already marked current")
    ap.add_argument("--audit-images", action="store_true",
                    help="fetch every published post/page and verify a real image is present")
    ap.add_argument("--fix", action="store_true",
                    help="with --audit-images, re-render+update any item missing an image")
    args = ap.parse_args()

    state = load_state()

    if args.list:
        cmd_list(state)
        return

    if args.login:
        get_credentials()
        log(f"OAuth complete. Token saved to {TOKEN_PATH}")
        return

    blog_id = require_env("BLOGGER_BLOG_ID")

    creds = get_credentials()
    blogger = build_blogger(creds)

    # confirm blog access early
    try:
        info = blogger.blogs().get(blogId=blog_id).execute()
        log(f"Connected to blog: {info.get('name')} ({info.get('url')})")
    except Exception as e:
        sys.exit(f"ERROR: cannot access BLOGGER_BLOG_ID={blog_id}: {e}")

    blog_url = info.get("url", "https://consultinglegalnews.blogspot.com")

    if args.audit_images:
        import re as _re
        art_by_slug = {a["slug"]: a for a in ARTICLES}
        page_by_slug = {p["slug"]: p for p in PAGES}
        ok = missing = errors = fixed = 0
        miss_list = []
        def _has_real_img(html: str) -> bool:
            # quote-agnostic; any http(s) <img> counts (Blogger may rehost to googleusercontent
            # with no file extension, and our markup uses single-quoted src attributes)
            for mo in _re.finditer(r'''<img\b[^>]*\bsrc=["']([^"']+)["']''', html or "", _re.I):
                src = mo.group(1).strip()
                if src.lower().startswith(("http://", "https://", "/")) and not src.lower().startswith("data:"):
                    return True
            return False
        for kind, store, by_slug in (("post", state.get("posts",{}), art_by_slug),
                                     ("page", state.get("pages",{}), page_by_slug)):
            for slug, meta in list(store.items()):
                _id = meta.get("post_id") or meta.get("page_id")
                if not _id:
                    continue
                try:
                    if kind == "post":
                        r = blogger.posts().get(blogId=blog_id, postId=_id, fields="content,url").execute()
                    else:
                        r = blogger.pages().get(blogId=blog_id, pageId=_id, fields="content,url").execute()
                    if _has_real_img(r.get("content","")):
                        ok += 1
                    else:
                        missing += 1; miss_list.append((kind, slug, meta.get("url","")))
                        log(f"MISSING IMAGE: {kind} {slug} -> {meta.get('url','')}")
                        if args.fix:
                            spec = by_slug.get(slug)
                            if spec:
                                try:
                                    if kind == "post":
                                        with_retry(update_post, blogger, blog_id, _id, spec)
                                    else:
                                        with_retry(update_page, blogger, blog_id, _id, spec, blog_url)
                                    fixed += 1; log(f"  fixed: re-rendered {kind} {slug} with image")
                                    time.sleep(args.delay)
                                except Exception as fe:
                                    log(f"  fix FAILED for {slug}: {fe}")
                except Exception as e:
                    errors += 1; log(f"ERROR auditing {kind} {slug}: {e}")
        log(f"AUDIT images: {ok} OK, {missing} missing, {fixed} fixed, {errors} errors "
            f"(total checked {ok+missing})")
        if missing and not args.fix:
            log("Re-run with --audit-images --fix to repair the items above.")
        # non-zero exit if anything is still missing after a fix pass
        if (missing - fixed) > 0:
            sys.exit(1)
        return

    if args.update_images:
        IMG_V = 2  # bump to force a re-update of all items
        art_by_slug = {a["slug"]: a for a in ARTICLES}
        page_by_slug = {p["slug"]: p for p in PAGES}
        done = skipped = 0
        # posts
        for slug, meta in list(state.get("posts", {}).items()):
            topic = art_by_slug.get(slug)
            pid = meta.get("post_id")
            if not topic or not pid:
                log(f"skip post {slug} (no spec or id)"); continue
            if not args.force and meta.get("img_v", 0) >= IMG_V:
                skipped += 1; continue
            try:
                if done and not args.dry_run:
                    time.sleep(args.delay)
                if args.dry_run:
                    log(f"[dry-run] would update post {slug}"); done += 1; continue
                with_retry(update_post, blogger, blog_id, pid, topic)
                meta["img_v"] = IMG_V; save_state(state)
                done += 1
                log(f"updated post [{done}]: {topic['title']}")
            except Exception as e:
                log(f"ERROR updating post {slug}: {e}")
        # pages
        for slug, meta in list(state.get("pages", {}).items()):
            page = page_by_slug.get(slug)
            pgid = meta.get("page_id")
            if not page or not pgid:
                log(f"skip page {slug} (no spec or id)"); continue
            if not args.force and meta.get("img_v", 0) >= IMG_V:
                skipped += 1; continue
            try:
                if done and not args.dry_run:
                    time.sleep(args.delay)
                if args.dry_run:
                    log(f"[dry-run] would update page {slug}"); done += 1; continue
                with_retry(update_page, blogger, blog_id, pgid, page, blog_url)
                meta["img_v"] = IMG_V; save_state(state)
                done += 1
                log(f"updated page [{done}]: {page['title']}")
            except Exception as e:
                log(f"ERROR updating page {slug}: {e}")
        log(f"update-images done: {done} updated, {skipped} already current")
        return

    if args.pages:
        page_targets = next_unposted_pages(state)[: args.limit]
        if not page_targets:
            log("No pages to publish — all pillar pages already published.")
            return
        for idx, page in enumerate(page_targets):
            try:
                if idx and not args.dry_run:
                    time.sleep(args.delay)
                resp = with_retry(insert_page, blogger, blog_id, page, blog_url, args.dry_run)
                if not args.dry_run:
                    state.setdefault("pages", {})[page["slug"]] = {
                        "title": page["title"], "url": resp.get("url", ""),
                        "page_id": resp.get("id", ""),
                        "posted_at": datetime.datetime.now().isoformat(),
                    }
                    save_state(state)
                    log(f"Published PAGE: {page['title']} → {resp.get('url','')}")
            except Exception as e:
                log(f"ERROR publishing page {page['slug']}: {e}")
                log(traceback.format_exc())
        return

    if args.once:
        topic = next((a for a in ARTICLES if a["slug"] == args.once), None)
        if not topic:
            sys.exit(f"ERROR: no article with slug '{args.once}'")
        targets = [topic]
    else:
        targets = next_unposted(state)[: args.limit]

    if not targets:
        log("Nothing to publish — all articles posted.")
        return

    for idx, topic in enumerate(targets):
        try:
            if idx and not args.dry_run:
                time.sleep(args.delay)
            resp = with_retry(insert_post, blogger, blog_id, topic, args.dry_run)
            if not args.dry_run:
                mark_posted(state, topic["slug"], {
                    "title": topic["title"], "url": resp.get("url", ""),
                    "post_id": resp.get("id", ""),
                })
                save_state(state)
                log(f"Published: {topic['title']} → {resp.get('url','')}")
        except Exception as e:
            log(f"ERROR publishing {topic['slug']}: {e}")
            log(traceback.format_exc())

if __name__ == "__main__":
    main()
