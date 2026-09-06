#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source env.sh
# Always use a fresh build; no M1-M4 artifacts or prior M5 evidence overwritten.
M5_TRANSLATION_BUILD="$(mktemp -d "$ROOT/build/m5_translation.XXXXXX")"
verilator --binary --timing --assert -Wall --top-module pa_m5_page_translate_tb \
  --Mdir "$M5_TRANSLATION_BUILD" \
  rtl/m5/pa_m5_page_translate.sv tests/m5/pa_m5_page_translate_tb.sv \
  > "$M5_TRANSLATION_BUILD/build.log" 2>&1 || {
    tail -n 80 "$M5_TRANSLATION_BUILD/build.log"
    exit 1
  }
"$M5_TRANSLATION_BUILD/Vpa_m5_page_translate_tb" | tee "$M5_TRANSLATION_BUILD/test.log"
echo "M5 TRANSLATION EVIDENCE $M5_TRANSLATION_BUILD"
