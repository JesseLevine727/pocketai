#!/usr/bin/env bash
# Exact qualified M3 overlay: hash preflight, M1/M2, all M3 operators/chains,
# and repeated performance measurements. Requires interactive board sudo only.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
BOARD_HOST="${PYNQ_HOST:-xilinx@10.0.0.223}"
REMOTE_DIR="${PYNQ_M3_DIR:-/home/xilinx/pocketai_m3}"
BUILD_DIR="$(realpath "${M3_VIVADO_BUILD_DIR:-$ROOT/build/m3_qual2}")"
BOARD_LOG="${M3_BOARD_LOG:-$BUILD_DIR/board.log}"
if [[ ! "$REMOTE_DIR" =~ ^/home/xilinx/[a-zA-Z0-9_./-]+$ ]]; then
  echo "[run_m3_board] FAIL: unsafe remote staging path" >&2
  exit 1
fi
for required in "$BUILD_DIR/m3_pynq.bit" "$BUILD_DIR/m3_pynq.hwh" \
    "$ROOT/build/pa_cluster/cluster.bin" "$ROOT/build/pa_sfpu/vectors.bin" \
    "$ROOT/build/pa_gemm_v3/vectors.bin" "$ROOT/build/pa_cluster_m3/chains.bin"; do
  test -f "$required"
done
STAGE="$(mktemp -d "$ROOT/build/m3_board_stage.XXXXXX")"
mkdir -p "$STAGE/ref"
cp "$BUILD_DIR/m3_pynq.bit" "$BUILD_DIR/m3_pynq.hwh" \
  "$ROOT/build/pa_cluster/cluster.bin" \
  "$ROOT/zynq/m1_boot.py" "$ROOT/zynq/m2_run.py" \
  "$ROOT/zynq/m3_run.py" "$ROOT/zynq/m3_manifest.py" "$STAGE/"
cp "$ROOT/ref/__init__.py" "$ROOT/ref/gemm_ref.py" "$ROOT/ref/sfpu_ref.py" \
  "$ROOT/ref/sfpu_stream.py" "$ROOT/ref/m3_packets.py" "$STAGE/ref/"
cp "$ROOT/build/pa_sfpu/vectors.bin" "$STAGE/sfpu.bin"
cp "$ROOT/build/pa_gemm_v3/vectors.bin" "$STAGE/gemm.bin"
cp "$ROOT/build/pa_cluster_m3/chains.bin" "$STAGE/chains.bin"
python3 zynq/m3_manifest.py "$STAGE/manifest.json" --build "$BUILD_DIR"
python3 zynq/m3_manifest.py "$STAGE/manifest.json" --check
ssh -o BatchMode=yes "$BOARD_HOST" "mkdir -p '$REMOTE_DIR'"
scp -qr "$STAGE/." "$BOARD_HOST:$REMOTE_DIR/"
ssh -tt -o BatchMode=yes "$BOARD_HOST" \
  "bash -lc 'cd \"$REMOTE_DIR\" && \
    /usr/local/share/pynq-venv/bin/python3 m3_manifest.py manifest.json --check && \
    sudo -E /usr/local/share/pynq-venv/bin/python3 m1_boot.py \
      --bitstream m3_pynq.bit --firmware cluster.bin && \
    sudo -E /usr/local/share/pynq-venv/bin/python3 m2_run.py --bitstream m3_pynq.bit && \
    sudo -E /usr/local/share/pynq-venv/bin/python3 m3_run.py \
      --bitstream m3_pynq.bit --manifest manifest.json && \
    sudo -E /usr/local/share/pynq-venv/bin/python3 m1_boot.py \
      --bitstream m3_pynq.bit --firmware cluster.bin'" | tee "$BOARD_LOG"
scp -q "$BOARD_HOST:$REMOTE_DIR/m3_board.json" "$BUILD_DIR/board.json"
cp "$STAGE/manifest.json" "$BUILD_DIR/board_manifest.json"
echo "M3 PHYSICAL ACCEPTANCE PASS log=$BOARD_LOG report=$BUILD_DIR/board.json"
