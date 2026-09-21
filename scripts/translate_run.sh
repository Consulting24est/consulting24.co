#!/bin/zsh
# translate_run.sh — translate every landing page into zh/es/ar in rounds and deploy each round.
#   ROUND=120 WORKERS=12 zsh scripts/translate_run.sh          (defaults)
# Each round: translate up to $ROUND page-language tasks, rebuild sitemaps + hreflang
# (no IndexNow ping here; the daily job drains the queue), commit, push origin + live (c24est).
# Stops when a round completes 0 tasks. Resumable: state lives in config/translations.json.
set -u
cd "$(dirname "$0")/.." || exit 1
ROUND=${ROUND:-120}; WORKERS=${WORKERS:-12}; LANGS=${LANGS:-zh,es,ar}
PY=${PY:-python3}
ts() { date "+%Y-%m-%d %H:%M:%S"; }
echo "[$(ts)] translate_run: start (round=$ROUND workers=$WORKERS langs=$LANGS)" >> logs/translate.log
while true; do
  out=$("$PY" scripts/translate_pages.py --translate --langs "$LANGS" --workers "$WORKERS" --max-tasks "$ROUND" 2>&1 | tail -3)
  echo "$out" | tail -1
  done_n=$(echo "$out" | grep -o "translate: done [0-9]*" | grep -o "[0-9]*$")
  [ -z "$done_n" ] && done_n=0
  INDEXNOW_SKIP=1 "$PY" scripts/publish.py > /dev/null 2>&1
  git add zh es ar config/translations.json config/page_hashes.json config/indexnow_queue.json \
          sitemap.xml 'sitemap-*.xml' styles-rtl.css index.html 2>/dev/null
  git add -u -- ':(glob)*/index.html' ':(exclude)editorial-policy/index.html' 2>/dev/null
  if ! git diff --cached --quiet 2>/dev/null; then
    n_zh=$(ls -d zh/*/ 2>/dev/null | wc -l | tr -d ' '); n_es=$(ls -d es/*/ 2>/dev/null | wc -l | tr -d ' '); n_ar=$(ls -d ar/*/ 2>/dev/null | wc -l | tr -d ' ')
    git commit -q -m "Translations: landing pages in zh/es/ar via DeepSeek (zh $n_zh, es $n_es, ar $n_ar)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
    git push -q origin main 2>>logs/translate.log && git push -q c24est main 2>>logs/translate.log \
      && echo "[$(ts)] deployed round: zh $n_zh es $n_es ar $n_ar" >> logs/translate.log
  fi
  if [ "$done_n" -eq 0 ]; then
    echo "[$(ts)] translate_run: nothing left to translate — finished" >> logs/translate.log
    break
  fi
done
