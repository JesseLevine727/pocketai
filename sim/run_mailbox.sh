#!/usr/bin/env bash
# Standalone M1 mailbox protocol and IRQ-level regression.
set -euo pipefail
ulimit -c 0

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=env.sh
source env.sh

OUT="build/pa_mailbox"
mkdir -p "$OUT"

verilator --binary --timing -Wall -Wno-TIMESCALEMOD \
  --top-module pa_mailbox_tb \
  --Mdir "$OUT/obj" \
  -o Vpa_mailbox_tb \
  rtl/soc/pa_mailbox.sv sim/pa_mailbox/pa_mailbox_tb.sv

"$OUT/obj/Vpa_mailbox_tb"
