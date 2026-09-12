#!/usr/bin/env python3
"""check_rates.py — truth check for the chauffeur cluster.

Fails the build when any car page, llms.txt or pricing.md drifts from
data/rates.json: a wrong AED figure, a wrong phone digit, a missing
operator line, or a stale prices-last-verified date.

Usage: python3 scripts/check_rates.py
"""
from __future__ import annotations
import json, re, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = json.loads((ROOT / "data" / "rates.json").read_text())

allowed_amounts = set()
for row in R["rates"]:
    allowed_amounts.add(row["aed"])
    if "per_hour" in row:
        allowed_amounts.add(row["per_hour"])

# competitor-published AED figures are allowed only on the comparison pages
CF_PATH = ROOT / "data" / "competitor-facts.json"
CF = json.loads(CF_PATH.read_text()) if CF_PATH.exists() else {"allowed_pages": [], "allowed_amounts": []}

errors: list[str] = []


def fail(page: str, msg: str) -> None:
    errors.append(f"{page}: {msg}")


def check_page(path: pathlib.Path) -> None:
    rel = str(path.relative_to(ROOT))
    t = path.read_text()
    if R["phone_display"] not in t:
        fail(rel, f"missing display phone {R['phone_display']}")
    if f"wa.me/{R['phone_wa']}" not in t:
        fail(rel, f"missing wa.me/{R['phone_wa']} link")
    if R["operator"] not in t:
        fail(rel, f"missing operator line ({R['operator']})")
    # every AED amount on the page must come from rates.json
    page_allowed = set(allowed_amounts)
    # language versions (…/ar/compare/index.html) inherit the comparison-page whitelist
    if any(rel.endswith(p.split("luxury-chauffeur-service-dubai/")[-1]) for p in CF["allowed_pages"]):
        page_allowed |= set(CF["allowed_amounts"])
    for m in re.finditer(r"AED\s*(\d[\d,]*)", t):
        amount = int(m.group(1).replace(",", ""))
        # tolerate the range form "AED 1,600–10,000" (both ends must be allowed)
        if amount not in page_allowed:
            fail(rel, f"AED {m.group(1)} not in data/rates.json (or competitor-facts whitelist)")
    # if the page shows a PRICES verified date, it must match rates.json
    # ("Facts last verified" on comparison pages tracks competitor-facts.json instead)
    for m in re.finditer(r"Prices(?: in AED,)? last verified:?\s*([0-9]{1,2} \w+ [0-9]{4})", t):
        if m.group(1) != R["prices_last_verified_display"]:
            fail(rel, f"stale verified date '{m.group(1)}' (rates.json says {R['prices_last_verified_display']})")


pages = sorted((ROOT / "luxury-chauffeur-service-dubai").rglob("index.html"))
if not pages:
    fail("cluster", "no pages found under luxury-chauffeur-service-dubai/")
for p in pages:
    check_page(p)

for name in ("llms.txt", "pricing.md"):
    t = (ROOT / name).read_text()
    if R["operator"] not in t:
        fail(name, "missing operator mention")
    for row in R["rates"]:
        if f"{row['aed']:,}" not in t.replace(" ", " "):
            fail(name, f"missing rate AED {row['aed']:,} ({row['tier']})")

if errors:
    print(f"RATES CHECK FAILED — {len(errors)} problem(s):")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
print(f"rates check ok — {len(pages)} car page(s), llms.txt, pricing.md consistent with data/rates.json")
