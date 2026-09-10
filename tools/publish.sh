#!/bin/bash
# Publish the laptop's snapshots: pull CI's, rebuild the page data, commit, push.
# Runs every 30 minutes from launchd (see install_poller.sh).
#
# This laptop is the only thing that rewrites docs/data.json. CI appends its own
# polls to tools/data/ci/ and nothing else, so the two never conflict. Commits are
# pathspec-limited, so nothing else staged in this working copy is ever swept up.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
PY=/Users/liangshiting/opt/anaconda3/bin/python3
[ -x "$PY" ] || PY=$(command -v python3)
ts() { date '+%Y-%m-%d %H:%M'; }
PATHS=(tools/data docs/data.json tools/archive_cells.json)
ID=(-c user.name=citina -c user.email=43682583+citina@users.noreply.github.com)

git pull -q --rebase --autostash origin main || { echo "$(ts) pull failed"; exit 1; }
(cd tools && "$PY" build_data.py --out ../docs/data.json >/dev/null 2>&1) || { echo "$(ts) build failed"; exit 1; }
git add -- "${PATHS[@]}"
if git diff --cached --quiet -- "${PATHS[@]}"; then echo "$(ts) nothing new"; exit 0; fi
git "${ID[@]}" commit -q -m "laptop snapshots $(date -u +%Y-%m-%dT%H:%MZ)" -- "${PATHS[@]}" || exit 1
for i in 1 2 3; do
  git pull -q --rebase --autostash origin main && git push -q origin main && { echo "$(ts) published"; exit 0; }
  sleep 20
done
echo "$(ts) push failed after 3 tries"; exit 1
