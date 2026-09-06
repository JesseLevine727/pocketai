#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
source env.sh
VIVADO_BIN="${VIVADO:-/home/elfo/Documents/2025.1/Vivado}/bin/vivado"
BOARD_REPO="${PYNQ_BOARD_REPO:-}"
BUILD_DIR=$(realpath -m "${M5_VIVADO_BUILD_DIR:-$ROOT/build/m5_pynq}")
SOURCE_WORK="$BUILD_DIR/resolved_sources"
EDA="$SOURCE_WORK/pocketai_pa_pa_cluster_m5_board_0.1.eda.yml"
SOURCE_TCL="$SOURCE_WORK/pocketai_sources.tcl"
if [[ ! -x "$VIVADO_BIN" ]]; then
  echo "[build_m5] FAIL: Vivado executable missing: $VIVADO_BIN" >&2; exit 1
fi
if [[ -z "$BOARD_REPO" || ! -f "$BOARD_REPO/pynq-z1/1.0/board.xml" ]]; then
  echo "[build_m5] FAIL: set PYNQ_BOARD_REPO to the PYNQ-Z1 board-files directory" >&2; exit 1
fi
if [[ -e "$BUILD_DIR/m5_pynq.xpr" ]]; then
  echo "[build_m5] FAIL: use a fresh build directory" >&2; exit 1
fi
python3 -m tests.m3.generate_sfpu_tables rtl/sfpu --check
mkdir -p "$BUILD_DIR/build_scripts"
cp zynq/build_m5.sh zynq/build_m5.tcl zynq/eda_to_vivado.py \
  tests/m3/generate_sfpu_tables.py scripts/check_m5_sources.py "$BUILD_DIR/build_scripts/"
fusesoc --cores-root=zynq --cores-root=rtl/m5 --cores-root=rtl/soc \
  --cores-root=rtl/gemm --cores-root=rtl/sfpu --cores-root=rtl/ibex-orig \
  run --mapping=lowrisc:prim_xilinx:all:0.1 --target=sources \
  --work-root="$SOURCE_WORK" --setup pocketai:pa:pa_cluster_m5_board
# --setup exports hooks but does not execute pre_build. This flow invokes
# Vivado directly, so apply the same fail-closed derivation used by simulation.
(cd "$SOURCE_WORK" && bash ./m5_prepare_lsu.sh)
python3 scripts/check_m5_sources.py "$SOURCE_WORK"
python3 zynq/eda_to_vivado.py "$EDA" "$SOURCE_TCL"
export M5_SOURCE_TCL="$SOURCE_TCL" M5_VIVADO_BUILD_DIR="$BUILD_DIR" PYNQ_BOARD_REPO="$BOARD_REPO"
cd "$BUILD_DIR"
"$VIVADO_BIN" -mode batch -nojournal -log "$BUILD_DIR/vivado.log" \
  -source "$ROOT/zynq/build_m5.tcl"
echo "[build_m5] M5 VIVADO PASS: $BUILD_DIR/m5_pynq.bit"
