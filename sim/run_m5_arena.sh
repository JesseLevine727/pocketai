#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
M5_ARENA_PYTHON=${M5_ARENA_PYTHON:-"$ROOT/build/m4_venv/bin/python"}
M5_ARENA_BUILD=$(mktemp -d "$ROOT/build/m5_arena.XXXXXX")
"$M5_ARENA_PYTHON" -m unittest discover -s tests/m5 -p 'test_arena.py' -v \
  2>&1 | tee "$M5_ARENA_BUILD/unit.log"
"$M5_ARENA_PYTHON" -m scripts.export_m5_model --output "$M5_ARENA_BUILD/model" \
  | tee "$M5_ARENA_BUILD/export.log"
"$M5_ARENA_PYTHON" -m scripts.export_m5_model --output "$M5_ARENA_BUILD/model" --verify-only \
  | tee "$M5_ARENA_BUILD/recheck.log"
cmp "$M5_ARENA_BUILD/export.log" "$M5_ARENA_BUILD/recheck.log"
echo "M5 ARENA EVIDENCE $M5_ARENA_BUILD"
