#!/usr/bin/env bash
# Stage and run the exact M2 overlay acceptance suite over SSH on a PYNQ-Z1.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BOARD_HOST="${PYNQ_HOST:-xilinx@10.0.0.223}"
REMOTE_DIR="${PYNQ_M2_DIR:-/home/xilinx/pocketai_m2}"
BUILD_DIR="${M2_VIVADO_BUILD_DIR:-$ROOT/build/m2_pynq}"
BIT="$BUILD_DIR/m2_pynq.bit"
HWH="$BUILD_DIR/m2_pynq.hwh"
FIRMWARE="$ROOT/build/pa_cluster/cluster.bin"
BOARD_LOG="${M2_BOARD_LOG:-$ROOT/build/m2_board.log}"

for required in \
  "$BIT" \
  "$HWH" \
  "$FIRMWARE" \
  "$ROOT/zynq/m1_boot.py" \
  "$ROOT/zynq/m2_run.py" \
  "$ROOT/ref/__init__.py" \
  "$ROOT/ref/gemm_ref.py"; do
  if [[ ! -f "$required" ]]; then
    echo "[run_m2_board] FAIL: missing $required" >&2
    exit 1
  fi
done

ssh -o BatchMode=yes "$BOARD_HOST" "mkdir -p '$REMOTE_DIR/ref'"
scp -q \
  "$BIT" \
  "$HWH" \
  "$FIRMWARE" \
  "$ROOT/zynq/m1_boot.py" \
  "$ROOT/zynq/m2_run.py" \
  "$BOARD_HOST:$REMOTE_DIR/"
scp -q "$ROOT/ref/__init__.py" "$ROOT/ref/gemm_ref.py" \
  "$BOARD_HOST:$REMOTE_DIR/ref/"

# Qualify the two-hart M1 workload first, then reprogram the identical M2
# bitstream for the A9/DMA GEMM test. Stock PYNQ requires root for MMIO.
ssh -tt -o BatchMode=yes "$BOARD_HOST" \
  "bash -lc 'cd \"$REMOTE_DIR\" && \
    sudo -E /usr/local/share/pynq-venv/bin/python3 m1_boot.py \
      --bitstream m2_pynq.bit --firmware cluster.bin && \
    sudo -E /usr/local/share/pynq-venv/bin/python3 m2_run.py \
      --bitstream m2_pynq.bit'" | tee "$BOARD_LOG"
