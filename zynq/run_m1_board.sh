#!/usr/bin/env bash
# Stage the M1 overlay/firmware and execute it over SSH on a PYNQ-Z1.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BOARD_HOST="${PYNQ_HOST:-xilinx@10.0.0.223}"
REMOTE_DIR="${PYNQ_M1_DIR:-/home/xilinx/pocketai_m1}"
BUILD_DIR="${M1_VIVADO_BUILD_DIR:-$ROOT/build/m1_pynq}"
BIT="$BUILD_DIR/m1_pynq.bit"
HWH="$BUILD_DIR/m1_pynq.hwh"
FIRMWARE="$ROOT/build/pa_cluster/cluster.bin"

for required in "$BIT" "$HWH" "$FIRMWARE" "$ROOT/zynq/m1_boot.py"; do
  if [[ ! -f "$required" ]]; then
    echo "[run_m1_board] FAIL: missing $required" >&2
    exit 1
  fi
done

ssh -o BatchMode=yes "$BOARD_HOST" "mkdir -p '$REMOTE_DIR'"
scp -q "$BIT" "$HWH" "$FIRMWARE" "$ROOT/zynq/m1_boot.py" \
  "$BOARD_HOST:$REMOTE_DIR/"
# Programming and MMIO require root on the stock PYNQ image. Preserve the
# login-shell XRT environment and allocate a TTY for the normal sudo prompt.
ssh -tt -o BatchMode=yes "$BOARD_HOST" \
  "bash -lc 'cd \"$REMOTE_DIR\" && sudo -E /usr/local/share/pynq-venv/bin/python3 m1_boot.py'"
