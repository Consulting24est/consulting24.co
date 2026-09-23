#!/bin/bash
# Daily Consulting24 Blogger pipeline:
#   1) publish today's batch of Blogger posts (consulting24_blog.py)
#   2) re-sync the site's /blog/ hub so EVERY Blogger guide is linked (link_blogger.py)
#   3) commit + push so the new links deploy live to www.consulting24.co
# Wired into the com.consulting24.blog LaunchAgent (runs daily).
set -u
REPO=/Users/mardosoo/consulting24
PY=/opt/homebrew/bin/python3
cd "$REPO" || exit 1

# Owner cap (Sept 2026): max 1-2 posts/day. Skip cleanly until Blogger is authorised on this machine
# (one-time: python3 scripts/consulting24_blog.py --login).
if [ ! -f "$HOME/.consulting24_blogger_token.json" ]; then
  mkdir -p logs; echo "[$(date '+%Y-%m-%d %H:%M:%S')] daily_blog: SKIPPED — not authorised (run: python3 scripts/consulting24_blog.py --login)" >> logs/daily_blog.log; exit 0
fi

mkdir -p logs
ts() { date "+%Y-%m-%d %H:%M:%S"; }
echo "[$(ts)] daily_blog: start" >> logs/daily_blog.log

# 1a) generate up to 2 fresh DeepSeek posts into the queue (config/extra_posts.json)
"$PY" scripts/gen_blogger_posts.py 2 >> logs/daily_blog.log 2>&1 || echo "[$(ts)] post-gen nonzero" >> logs/daily_blog.log

# 1a1) generate a UNIQUE branded hero image SET per queued/published post/page (gen_blog_images.py also
#      covers the queued config/extra_posts.json slugs), wire the site's own posts, and deploy the images
#      FIRST so they are already live when Blogger renders today's posts.
"$PY" scripts/gen_blog_images.py >> logs/daily_blog.log 2>&1 || echo "[$(ts)] image gen nonzero" >> logs/daily_blog.log
"$PY" scripts/blog_image_seo.py >> logs/daily_blog.log 2>&1 || echo "[$(ts)] image seo nonzero" >> logs/daily_blog.log
git add img/blog 2>/dev/null
git add -u blog 2>/dev/null          # only tracked posts the sweep rewired, never unrelated WIP
if git diff --cached --name-only 2>/dev/null | grep -q '^blog/'; then
  # rewired pages change content hashes: refresh sitemap lastmod / image entries and the IndexNow queue with them
  "$PY" scripts/publish.py >> logs/daily_blog.log 2>&1 || echo "[$(ts)] publish (images) nonzero" >> logs/daily_blog.log
  git add sitemap.xml 'sitemap-*.xml' config/page_hashes.json config/indexnow_queue.json config/indexnow_submitted.json 2>/dev/null
fi
if ! git diff --cached --quiet 2>/dev/null; then
  git commit -q -m "daily: unique blog hero images" >> logs/daily_blog.log 2>&1
  git push -q origin main >> logs/daily_blog.log 2>&1 && git push -q c24est main >> logs/daily_blog.log 2>&1 && echo "[$(ts)] images pushed (origin + live)" >> logs/daily_blog.log
  sleep 90   # let GitHub Pages deploy the new images before Blogger fetches them
fi

# 1a2) publish any remaining pillar PAGES (no-op once all are live)
"$PY" scripts/consulting24_blog.py --pages --limit 1 --delay 25 >> logs/daily_blog.log 2>&1 || echo "[$(ts)] pages nonzero" >> logs/daily_blog.log
# 1b) publish max 2 POSTS (throttled; backoff handles Blogger rate limits)
"$PY" scripts/consulting24_blog.py --limit 2 --delay 25 >> logs/daily_blog.log 2>&1 || echo "[$(ts)] poster nonzero" >> logs/daily_blog.log

# 1d) attach now-live unique images to any post/page that still needs it, then audit+fix
"$PY" scripts/consulting24_blog.py --update-images >> logs/daily_blog.log 2>&1 || echo "[$(ts)] update-images nonzero" >> logs/daily_blog.log
"$PY" scripts/consulting24_blog.py --audit-images --fix >> logs/daily_blog.log 2>&1 || echo "[$(ts)] image audit found/repaired missing images" >> logs/daily_blog.log

# 2) link ALL published Blogger guides from the site blog hub
"$PY" scripts/link_blogger.py >> logs/daily_blog.log 2>&1 || echo "[$(ts)] linker nonzero" >> logs/daily_blog.log

# 2b) NEWS DESK: poll regulator feeds and publish anything new that clears the grounding
#     gate. Publishing nothing is a normal day, not an error.
"$PY" scripts/news_auto.py >> logs/daily_blog.log 2>&1 || echo "[$(ts)] news_auto nonzero" >> logs/daily_blog.log
# Always rebuild, even when nothing published: this is what ages items out of the 48h
# Google News window. Skipping it on a quiet day would leave a stale news sitemap.
"$PY" scripts/news.py build >> logs/daily_blog.log 2>&1 || echo "[$(ts)] news build nonzero" >> logs/daily_blog.log
# Only run the full publish (sitemap rebuild + IndexNow ping) when a news page actually
# appeared, so a quiet day does not re-ping 950 unchanged URLs.
if [ -n "$(git status --porcelain news/ | grep -v '_drafts')" ]; then
  "$PY" scripts/publish.py >> logs/daily_blog.log 2>&1 || echo "[$(ts)] publish nonzero" >> logs/daily_blog.log
fi

# 3) deploy if anything changed
git add blog/ config/blog_posted.json config/extra_posts.json config/extra_pages.json img/blog \
        news/ news-sitemap.xml sitemap.xml sitemap-pages.xml sitemap-blog.xml \
        config/news_items.json config/news_seen.json config/page_hashes.json \
        config/indexnow_queue.json config/indexnow_submitted.json \
        zh es ar config/translations.json 'sitemap-*.xml' \
        '*-crypto-license/index.html' 'crypto-exchange-license-*/index.html' 2>/dev/null
if ! git diff --cached --quiet 2>/dev/null; then
  git commit -q -m "daily: publish Blogger batch + sync site blog links + news desk" >> logs/daily_blog.log 2>&1
  git push -q origin main >> logs/daily_blog.log 2>&1 && git push -q c24est main >> logs/daily_blog.log 2>&1 && echo "[$(ts)] pushed (origin + live)" >> logs/daily_blog.log
else
  echo "[$(ts)] no changes to deploy" >> logs/daily_blog.log
fi
echo "[$(ts)] daily_blog: done" >> logs/daily_blog.log
