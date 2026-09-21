# Yandex Masterplan — consulting24.co

As of 2026-09-21. Sources: Yandex Webmaster (all reports), yandex.com search operators, live HTTP checks as YandexBot, GitHub Pages API, repo audit. Companion to `scripts/BING_INDEX_MASTERPLAN.md`; items marked **[shared]** are already in the Bing plan and only need doing once.

## 1. The real situation

Yandex Webmaster looks catastrophic (0 pages in search, 538 removed on 25 Aug, 0 external links, no crawl since 22 Aug) but Yandex search still serves ~968 www pages and the site ranks #1–2 for its brand query. The reports are the robot's honest view of the August cut-over: the homepage returned 404 on 11 Aug, then the whole host 301'd for ~13 days until the Consulting24est repo went live on 24–25 Aug. Yandex marked crawled URLs as Redirect (616) / HTTP error (87), dropped 538 pages, and has not come back. The verification meta tag was only added on 20 Sep, but rights only gate viewing, not collection, so that is not the cause. Nothing is penalised: Security = clean, Diagnostics = clean, SQI = 10.

Traffic is the actual problem: 522 impressions, 0 clicks in 30 days. Four things hold it there.

| Root cause | Evidence |
|---|---|
| Crawl never restarted after the outage | Crawl statistics: 0 events after 22 Aug; IndexNow ping of all 1,060 URLs fires daily but fails on DNS several days a week |
| http://www is a full live mirror | `https_enforced=false`; http://www → 200, github.io and http-apex redirects point at **http**://www; 118 "Secondary mirror" exclusions |
| Blogger cannibalises www on the same titles | `site:consulting24.co` top-10 are all blog.* posts; ~155 same-slug and 64 identical-title pairs, each independently written, each self-canonical; the /blog/ hub links 353 Blogger URLs; blog.* is not a Webmaster property |
| No measurement, no alerts | No Metrica or GA on any page; notifications off; 1 dead URL in Important-page monitoring; region unset |

Legacy debt sits behind these: Yandex knows 13,464 historic URLs; /team/, /crypto-exchange-license-lithuania/, /crypto-licence-dubai/ are still indexed but 404; 10 hand-written redirect stubs are deleted by `publish.py --prune` on every daily run and will 404 the day someone commits with `git add -A`.

## 2. Plan

Owner key: **M** = Mardo clicks, **C** = code (PR on origin, push main to c24est). Effort S/M/L.

### Day 0 — today, under 2 hours

| # | What | How | Owner | Effort | Verify |
|---|---|---|---|---|---|
| 0.1 | **Enforce HTTPS [shared]** | Log in as the Consulting24est GitHub account (collaborators cannot; it is a user account) → repo Settings → Pages → tick Enforce HTTPS. Certificate is already approved. | M | S | `curl -sI http://www.consulting24.co/` → 301 to https://www; `gh api repos/Consulting24est/consulting24.co/pages --jq .https_enforced` → true |
| 0.2 | Confirm primary address | Webmaster → Indexing → *Relocate site*. If the page names https://www.consulting24.co as primary, stop. Only if it names another host: add that host as a property and submit Relocate site → "Add HTTPS"/"Add WWW" **from that host**. | M | S | Page shows https://www as primary, no pending move |
| 0.3 | Turn on alerts | Bell icon → Configure: "Updating the primary site address", "Site errors", "Search index update", "Modifying robots.txt", weekly summary; email mardo@ and Telegram. | M | S | Summary email within 7 days |
| 0.4 | Kick the crawl | Webmaster → Indexing → Reindex pages: read the real daily quota shown, then submit the 28 money pages (/, /cryptocurrency-license/, /cost/, /requirements/, /application-process/, /company-setup/, /dubai-crypto-license/, /lithuania-crypto-license/, /vara-license/, the 9 panama-vs-* pages, /jurisdictions/, /luxury-chauffeur-service-dubai/ + 10 EN spokes). Replace the dead /crypto-licence-dubai in Important-page monitoring with these. | M | S | Crawl statistics show events dated after 21 Sep within 7 days |
| 0.5 | Register the 10 orphan stubs | Add to `config/redirects.json`: the 6 `/blog/tags/*` → `/blog/`, `/nominee-director-risks` → `/company-setup/` (skips the stub chain), `/post/panama-vs-estonia-crypto-license` → `/panama-vs-estonia-crypto-license/`, `/post/benefits-of-a-digital-currency-license-for-crypto-businesses` → `/best-country-for-crypto-license/`, `/post/why-canada-msb-…` → `/canada-crypto-license/`. Add the 6 Yandex-indexed 404s: `/team` → `/about/`, `/crypto-exchange-license-lithuania` → `/lithuania-crypto-license/`, `/crypto-licence-dubai` → `/dubai-crypto-license/`, `/company-formation` → `/company-setup/`; leave `/banking` and `/starting-a-business-in-estonia` as 404. Run `python3 scripts/redirects.py`; stage only `config/redirects.json` and the stub dirs. | C | S | `git status` shows no ` D` stubs; each URL returns 200 with meta refresh |
| 0.6 | Add blog.consulting24.co as a property | Blogger → Theme → Edit HTML → paste `<meta content='e5cc92e827a2953d' name='yandex-verification'/>` after `<head>` → Webmaster → Add site → meta tag. DNS TXT cannot work (CNAME to ghs.google.com). | M | S | Property verified; Query statistics populate within 14 days |

### Week 1 — pipeline fixes (all [shared] with the Bing plan)

1. **IndexNow delta-only + retry** in `scripts/publish.py`: submit only URLs whose content hash changed, cap ~200/day, retry the LaunchAgent DNS failure (`nodename nor servname provided`), log to `config/indexnow_submitted.json`. Yandex consumes IndexNow and its docs ask for changed URLs only.
2. **Chrome-insensitive lastmod**: hash the page with `<head>`, `<header>`, `<nav>`, `<footer>` stripped (there is no `<main>`; the wrapper is `<article id="main">`, homepage `<section id="main">`). Migrate `config/page_hashes.json` by rewriting hashes while keeping dates; do not reseed from git (bulk commits would fabricate dates). Set sitemap `priority` 1.0 for Panama money pages, 0.5 for comparisons/chauffeur locales — Yandex documents that it loads by priority.
3. **Stop re-pruning stubs**: change `scripts/redirects.py` so `--check --prune` exits 1 when anything is pruned, run it in CI (commit the untracked `.github/`), or drop `--prune` from `publish.py` step 0.
4. **robots.txt**: add `Clean-param: lang&gclid&fbclid&yclid&ysclid` (utm_* is auto-stripped by Yandex) and mirror it in Webmaster → Indexing → Configure GET parameters. Do not touch the 12 `?lang=en` links — they are outbound regulator citations. Optional Yandex-only group to hide `/pricing.md`, `/llms.txt`, `/llms-full.txt`, `/pages.md` from Yandex results.
5. **Purge the spam residue**: add https://consulting24.co as a property (apex DNS TXT already exists) and submit https://consulting24.co/vara-license via Reindex pages so Yandex refetches the 301 and drops the "WATITOTO" snippet. The URL-removal tool rejects 301s.

### Weeks 2–4 — the Blogger decision and content ownership

6. **Read blog.* query data for 14 days**, then decide (see §3). Default: www owns every topic.
7. **De-duplicate the queue at the source [shared]**: `gen_blogger_posts.py` must skip titles whose slug exists under `blog/`; `daily_run.py` must skip slugs in `config/blog_posted.json`; unify `slugify()` (80 vs 70 chars). Each future topic lands on one host.
8. **Fix the /blog/ hub**: `link_blogger.py` currently double-lists ~155 topics and links 363 Blogger URLs (10 via consultinglegalnews.blogspot.com). One card per topic, www URL when a www article exists, rewrite the blogspot hosts.
9. **Retitle one side of the 64 identical-title pairs** (cheapest: Blogger `posts().patch` title-only), then Reindex the www side.
10. **If www wins the decision**: Blogger → Theme → after `all-head-content` add `<meta name='yandex' content='noindex, follow'/>` (Yandex-only directive, Google untouched); submit the 323 post + 40 page URLs in one batch to Tools → Remove pages (quota 500/day). Blogger keeps its ~20 links/post to www. Do **not** add a cross-domain canonical — Yandex documents it as ignored, and Blogger paths cannot map to www slugs.
11. **Blogger snippets** (cheap, do regardless): Layout → Header → untick "Show description" (the 430-char blog blurb is what Yandex lifts into snippets); Settings → Meta tags → enable search description; in `consulting24_blog.py` put the lede before the SVG hero and strip the SVG `<text>` nodes.

### Ongoing / monthly

- Weekly (5 min): Crawl statistics events/day, Pages in search, Excluded buckets, Query statistics clicks, IndexNow log lines.
- Monthly: mine Webmaster → Crawl statistics → All pages (CSV, 13,464 rows) for 404s with a real successor; add via `redirects.json` (cap homepage targets at ~15). Leave `/profile/*`, carbon-calculator, Wix `copy-of-*`, tag/category pagination as 404; optionally `Disallow: /profile/` so the 2 req/s crawl is not spent on 353 Wix member-spam paths.
- Snippet upkeep: validate FAQPage/BreadcrumbList in Tools → Structured Data Validator; sitelinks appear automatically once www traffic returns; collect Yandex Business reviews (0 today).
- DNS: delete the dangling `ru.` and `no.` CNAMEs to Wix [shared].
- Keep both verification anchors (meta tag in `index.html`, apex TXT). Add a guard in `scripts/qc_audit.py` that the yandex-verification tag is present.

## 3. Decisions Mardo must make

| Decision | Recommendation |
|---|---|
| Which host owns article topics in Yandex: www or blog.consulting24.co? | **www.** Conversions, schema, Webmaster control and the Bing/Google strategy all sit on www. Confirm with 14 days of blog.* query data first; if blog.* has real clicks, migrate those titles to www before noindexing Blogger. |
| Install Yandex Metrica? | **Yes, but behind a consent gate.** The site has no analytics at all, and Metrica unlocks "crawl via tag" plus real Yandex click data. It sets cookies and sends data to Russia; the company is an Estonian OÜ selling compliance. Add a minimal consent banner, WebVisor off, name Metrica in the privacy page. Inject via `/nav.js` (loaded on all 1,060 pages) — `site_header.py` HEAD_ASSETS is a no-op for existing pages. Do not expect SQI to move from this. |
| Set a site region? | **No.** Click "No region" in View in search → Site region. Tallinn stays on the Yandex Business card; a Webmaster region would bias geo queries toward Estonia against the English/Panama/Dubai focus. |
| Russian-language landing pages for Yandex? | **Not now.** Check Wordstat for "криптолицензия панама/дубай", "лицензия vara"; revisit only if combined volume ≥ 500/month. Keeps the English-only rule. |
| Cloudflare in front of GitHub Pages? | **Not yet.** It would give true 301s for the 101 stubs (Yandex treats meta refresh as a temporary redirect) and HSTS, at the cost of another DNS layer. Revisit after the crawl has recovered. |

## 4. KPIs — 30 / 60 / 90 days (baseline 21 Sep 2026)

| KPI (Webmaster, www property) | Now | 21 Oct | 21 Nov | 21 Dec |
|---|---|---|---|---|
| Crawl events/day | 0 (since 22 Aug) | > 50 | > 100 | steady |
| Pages in search | 0 (report) / ~968 (search) | > 400 | > 800 | ≥ 1,000 of 1,060 |
| Excluded: Redirect / Secondary mirror / HTTP error | 616 / 118 / 87 | falling | < 300 / < 20 / < 30 | stubs only / 0 / < 20 |
| Impressions / clicks, trailing 30 days | 522 / 0 | 700 / 5 | 1,000 / 15 | 1,500 / 30 |
| External links / sites (report) | 0 / 0 | recovering | > 150 / > 100 | > 200 / > 150 |
| SQI | 10 | 10 | 10–20 | 20 |
| blog.* posts in `site:consulting24.co` top-10 | 10 of 10 | 10 | ≤ 5 | 0 |
| IndexNow submissions/day | ~1,060 (when DNS works) | < 50 | < 30 | < 30 |

## 5. What we ruled out

- **"www was re-glued as a secondary mirror of http://www."** No substitution notice, reports populated, `Relocate site` shows www as main, canonical/og:url/sitemap all vote https. The 118 exclusions are URLs met on alternate addresses during the redirect window.
- **"The freeze is a verification lapse."** Rights only gate viewing; sitemap loaded 19 Sep and query stats run to 19 Sep while crawl stopped 22 Aug.
- **"Blogger and www are duplicate content."** Same titles, different prose (8-gram overlap 0–0.4%); Yandex treats the subdomain as a separate site and ignores cross-host canonical. It is title cannibalisation, fixed by ownership and retitling, not by canonicals.
- **"Chauffeur hi/ru/ar titles are 2–3× too long."** Byte-count artefact (shell `${#var}` under LC_CTYPE=C). Real lengths are in range; only /hi/ hub title is 71 chars.
- **A `/post/<slug>` → `/blog/<slug>/` rewriter.** 0 exact matches between Wix/Webflow slugs and 2026 slugs; curated mapping only.
- **Deleting and re-adding sitemap.xml, removing the empty news-sitemap.** Inert for Yandex.
