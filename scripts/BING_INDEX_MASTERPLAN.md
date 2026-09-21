# Bing Index Masterplan — consulting24.co

As of 2026-09-21. Sources: Bing Webmaster Tools (Search Performance, Site Explorer, Sitemaps, IndexNow, Backlinks, AI Performance), live HTTP checks, repo audit. Living copy: https://claude.ai/code/artifact/b089d58a-4e40-41bd-ae36-49111b961b35

Bing indexes 968 of the 1,060 www pages, but the site earned only 59 clicks from 5.6K impressions in the last three months. The blockers are signal quality, not page quality: IndexNow flooding, a meaningless lastmod, an unredirected http duplicate, and a Blogger mirror that outranks the www blog.

## 1. Where Bing stands today

| Metric (BWT, 21 Sep 2026) | Value |
|---|---|
| Indexed / warning / excluded / error, www | 968 / 65 / 21 / 0 |
| Sitemap URLs, www | 1,060 (91 redirect stubs correctly excluded) |
| Sitemap URLs, blog.consulting24.co | 323 |
| Clicks / impressions, last 3 months | 59 / 5.6K (CTR 1.05%) |
| Clicks / impressions, last 24 months | 104 / 11.6K (CTR 0.89%) |
| Keywords / pages with impressions, 3M | 920 / 363 |
| AI citations (Copilot), 3M | 3.0K, ~10 cited pages/day |
| IndexNow URLs submitted, lifetime | 216.7K (~1.1K/day in September) |
| Referring domains / pages | 111 / 1.2K |
| Recommendations / Site Scan | none / never run (1,000-page scan started 21 Sep) |

~90% of two years of Bing traffic came in the last four months, so the June 2026 build is being crawled and shown. Top queries sit at avg position 2–7 with 0 clicks (mica license 54 impr, crypto otc desk license 48, msb license 17); most impressions are long Copilot grounding queries. Only the brand query converts (consulting24: 18.9% CTR).

On-page technicals are clean: self-canonical on all 1,060 pages, one H1 each, no duplicate titles/descriptions, no thin pages (min 458 words, median 3,087), FAQ + Article + Breadcrumb + Organization schema everywhere, robots.txt 0 errors.

## 2. Root causes, ranked

1. **IndexNow flooding.** `scripts/publish.py` sends all 1,060 URLs on every daily run (216.7K lifetime). Bing asks for changed URLs only; identical daily bulk pings train Bing to discount the signal and burn quota.
2. **Meaningless lastmod.** All 1,060 sitemap entries carry lastmod 2026-09-19: the site-wide header rewrite changed every file hash (`config/page_hashes.json`). Bing reads "everything changed" and ignores it.
3. **HTTP duplicate site.** `https_enforced: false` on Consulting24est/consulting24.co. `http://www.consulting24.co/` returns 200, not 301. Bing has both roots indexed; `/vasp-license/` recorded as non-https canonical source.
4. **Blogger mirror outranks www.** blog.consulting24.co republishes www posts in full (≥101 of 323 match a www /blog/ slug; sample copy 4,622 words, no canonical to www). Bing ranks the Blogger copies; www /blog/ posts are almost unlinked (268 of 333 have ≤2 inlinks, median 1).
5. **Legacy URL debris.** 33 dead Wix slugs still crawled (404), 40+ URLs "redirecting" via meta-refresh stubs, 2023 `pages-sitemap.xml` still registered but 404, `ru.consulting24.co` resolves to 404.
6. **Weak, spammy authority.** 62% of backlinks from two domains (darkschemedirectory.com 449, conquerclub.com 300); 32 anchor texts.
7. **Titles not written for the click.** Every non-brand top-25 query has 0% CTR at positions 2–7.

## 3. Phase 0 — this week (owner clicks, no code)

- [ ] GitHub → Consulting24est/consulting24.co → Settings → Pages → **Enforce HTTPS** (API change blocked from this machine). Verify: `curl -sI http://www.consulting24.co/` → 301.
- [ ] Bing → Sitemaps → delete `https://www.consulting24.co/pages-sitemap.xml`.
- [ ] Bing → Site Scan → read the 21 Sep scan; fix Errors first, then Warnings by count.
- [ ] DNS → remove the `ru` record (or 301 it to www).
- [ ] Bing → URL Inspection → Request indexing: Appendix B (11 pages) + Appendix C (10 money pages), ~10/day.
- [ ] Bing → Settings → Users: alerts go to info@aiangels.io; add mardo@consulting24.co as owner.
- [ ] Add Microsoft Clarity to the template (engagement signal for Bing + free heatmaps).

## 4. Phase 1 — next two weeks (pipeline fixes)

1. **IndexNow delta only** in `publish.py`: submit only URLs whose content hash changed this run + new + removed; cap 200/day; log to `config/indexnow_submitted.json`. Target <30/day.
2. **Template-insensitive lastmod:** hash only `<main>` (strip header/nav/footer/news desk). One-time reset to last content commit: `git log -1 --format=%cs -- <path>`.
3. **Sitemap index:** `sitemap-hubs.xml` (jurisdiction/activity/comparison), `sitemap-blog.xml`, `sitemap-news.xml` under `sitemap_index.xml`; drop changefreq/priority.
4. **Blogger cross-posts become teasers:** first ~300 words + "Read the full guide on consulting24.co". Existing full copies → Blogger per-post Custom Robots Tags = noindex (Blogger cannot emit a cross-domain canonical).
5. **Blog internal linking ≥5 inlinks/post:** Guides block on each jurisdiction hub, 2 sibling-post links per post, related-posts block on activity pages; automate in `generate.py`.
6. **Redirect the 16 dead Wix slugs** (Appendix A) via `config/redirects.json` + `scripts/redirects.py`; leave junk as 404.
7. **Filter stubs out of the IndexNow list** (sitemap already excludes them).

## 5. Phase 2 — weeks 3–6 (clicks and authority)

1. **Rewrite titles/descriptions** on the 50 pages with most impressions and 0 clicks. Bing weights exact-match title terms: lead with the query phrase + cost/timeline anchors + year, e.g. "MSB License (2026): Cost, Timeline, Requirements". Start: /mica-license/, /crypto-otc-desk-license/, /msb-license/, /mauritius-crypto-license/, /costa-rica-crypto-license/.
2. **Turn AI citations into visits:** vara license (34.8% citation share), msb license (32.5%), crypto license providers low setup cost (24.6%), stablecoin infrastructure licenses (9.7%) → two-line direct answer + CTA at top of those pages.
3. **Topical backlinks:** work the 3,300-domain outreach list toward crypto/fintech/legal/expat-finance; 20 new topical referring domains per quarter. Bing has no disavow; ignore the directory spam.
4. **Bing Places** for Dubai and Panama offices (NAP = Organization schema).
5. **Bing PubHub** for the news desk if ≥1 dated, bylined item/day.
6. **After every build:** IndexNow (changed only) + Bing SubmitFeed for `sitemap_index.xml` (hook exists in `publish.py`; needs `scripts/.bing_api_key`).

## 6. KPIs — 90 days (to 21 Dec 2026)

| KPI | Now | Target |
|---|---|---|
| Indexed www URLs | 968 / 1,060 | ≥1,050 |
| IndexNow submissions/day | ~1,100 | <30 |
| http URLs indexed | yes | 0 |
| Blogger copies outranking www | yes | 0 |
| Clicks, trailing 3M | 59 | 250 |
| Avg CTR, trailing 3M | 1.05% | 3% |
| Referring domains | 111 | 150 (≥25 topical) |
| Warnings + excluded | 86 | <20 |

Weekly (10 min): Site Explorer counts, IndexNow/day, clicks + CTR, AI citations. Monthly: re-run Site Scan, backlink domain count.

## Appendix A — dead Wix slugs to add to `config/redirects.json`

| Old slug | Redirect to |
|---|---|
| /crypto-license-switzerland | /switzerland-crypto-license/ |
| /crypto-license-cyprus | /cyprus-crypto-license/ |
| /crypto-license-el-salvador | /el-salvador-crypto-license/ |
| /cryptocurrency-license-in-dubai | /dubai-crypto-license/ |
| /crypto-trading-license-dubai | /dubai-crypto-license/ |
| /lithuania-cryptocurrency-license | /lithuania-crypto-license/ |
| /estonia-crypto-license-list | /estonia-crypto-license/ |
| /cryptocurrency-company-in-estonia | /estonia-crypto-license/ |
| /register-a-company-in-estonia | /estonia-crypto-license/ |
| /guide-to-establish-company-estonia | /estonia-crypto-license/ |
| /crypto-exchange-licensein-estonia | /estonia-crypto-license/ |
| /grow-crypto-businesses-in-estonia | /estonia-crypto-license/ |
| /start-a-company-in-malta | /malta-crypto-license/ |
| /fastest-crypto-license-singapore | /singapore-crypto-license/ |
| /uk-crypto-regulation | /best-country-for-crypto-license/ |
| /government-crypto-regulation | /best-country-for-crypto-license/ |

## Appendix B — live pages Bing last saw as 404 (request indexing)

/slovakia-crypto-license/, /crypto-otc-desk-license-labuan/, /crypto-fund-license-hong-kong/, /crypto-payment-institution-license-hong-kong/, /crypto-token-issuance-license-cyprus/, /crypto-exchange-license-isle-of-man/, /crypto-payment-institution-license-cyprus/, /best-country-crypto-license-dubai/, /portugal-crypto-license/, /crypto-token-issuance-license-georgia/, /crypto-token-issuance-license-costa-rica/

## Appendix C — money pages to request after the HTTPS fix

/msb-license/, /mica-license/, /vara-license/, /vasp-license/, /stablecoin-license/, /crypto-otc-desk-license/, /usa-crypto-license/, /singapore-crypto-license/, /dubai-crypto-license/, /jurisdictions/
