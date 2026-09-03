#!/usr/bin/env bash
# PocketAI-T repo ship helper: commit all changes and push.
# Usage: bash git_ship.sh "milestone message"
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

MSG="${1:-pocketai: $(date -u +%Y-%m-%dT%H:%M:%SZ) update}"

if [ -z "$(git status --porcelain)" ]; then
  echo "[git_ship] nothing to commit"
else
  git add -A
  git commit -m "$MSG"
fi

git push origin HEAD
echo "[git_ship] pushed $MSG"
