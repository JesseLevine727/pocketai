#!/usr/bin/env bash
# Benchmark ONLY the hash-pinned qualified M2 overlay. No M3 RTL is programmed.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
BOARD_HOST="${PYNQ_HOST:-xilinx@10.0.0.223}"
REMOTE_DIR="${PYNQ_M3_BASELINE_DIR:-/home/xilinx/pocketai_m3_baseline}"
BUILD_DIR="${M3_BASELINE_BUILD_DIR:-$ROOT/build/m2_qual2}"
RESULT_DIR="${M3_BASELINE_RESULT_DIR:-$ROOT/build/m3_baseline}"
# These paths enter a remote shell; reject shell metacharacters explicitly.
if [[ ! "$REMOTE_DIR" =~ ^/[a-zA-Z0-9_./-]+$ ]]; then
  echo "[m3_baseline] unsafe remote directory" >&2
  exit 1
fi
for required in "$BUILD_DIR/m2_pynq.bit" "$BUILD_DIR/m2_pynq.hwh" \
  "$ROOT/build/pa_cluster/cluster.bin" "$ROOT/zynq/m1_boot.py" \
  "$ROOT/zynq/m2_run.py" "$ROOT/zynq/m3_benchmark.py" \
  "$ROOT/zynq/m3_cpu_gemm.c" "$ROOT/ref/__init__.py" "$ROOT/ref/gemm_ref.py"; do
  test -f "$required" || { echo "[m3_baseline] missing $required" >&2; exit 1; }
done
# Check before even M1 programs the board; no exploratory-overlay fallback.
if [[ "$(sha256sum "$BUILD_DIR/m2_pynq.bit" | cut -d ' ' -f 1)" != \
  f196e92c4509ebad977521bf40a8cd30b0f3f131fbfe199515d6e0ff6600fa03 ]] || \
   [[ "$(sha256sum "$BUILD_DIR/m2_pynq.hwh" | cut -d ' ' -f 1)" != \
  f77dfe909dd8a3d7d0266d4326c05ceb1eb97a0182bbd4d67acf25a96833c390 ]]; then
  echo "[m3_baseline] refusing non-qualified overlay" >&2
  exit 1
fi
mkdir -p "$RESULT_DIR"
ssh -o BatchMode=yes "$BOARD_HOST" "mkdir -p '$REMOTE_DIR/ref'"
scp -q "$BUILD_DIR/m2_pynq.bit" "$BUILD_DIR/m2_pynq.hwh" \
  "$ROOT/build/pa_cluster/cluster.bin" "$ROOT/zynq/m1_boot.py" \
  "$ROOT/zynq/m2_run.py" "$ROOT/zynq/m3_benchmark.py" \
  "$ROOT/zynq/m3_cpu_gemm.c" "$BOARD_HOST:$REMOTE_DIR/"
scp -q "$ROOT/ref/__init__.py" "$ROOT/ref/gemm_ref.py" "$BOARD_HOST:$REMOTE_DIR/ref/"
ssh -tt -o BatchMode=yes "$BOARD_HOST" \
  "bash -lc 'cd \"$REMOTE_DIR\" && \
    gcc -O3 -Wall -Wextra -Werror -shared -fPIC -mcpu=cortex-a9 -mfpu=neon \
      m3_cpu_gemm.c -o m3_cpu_gemm.so && gcc --version && \
    sudo -E /usr/local/share/pynq-venv/bin/python3 m1_boot.py \
      --bitstream m2_pynq.bit --firmware cluster.bin && \
    sudo -E /usr/local/share/pynq-venv/bin/python3 m3_benchmark.py \
      --bitstream m2_pynq.bit --cpu-lib m3_cpu_gemm.so --output m3_baseline.json'" \
  | tee "$RESULT_DIR/board.log"
scp -q "$BOARD_HOST:$REMOTE_DIR/m3_baseline.json" \
  "$BOARD_HOST:$REMOTE_DIR/m3_cpu_gemm.so" "$RESULT_DIR/"
sha256sum "$RESULT_DIR/board.log" "$RESULT_DIR/m3_baseline.json" \
  "$ROOT/zynq/m3_benchmark.py" "$ROOT/zynq/m3_cpu_gemm.c"
