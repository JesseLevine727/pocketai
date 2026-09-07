#!/usr/bin/env bash
# Same qualified 91-MHz flow with explicit isolated fast-M source derivation.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
source env.sh
VIVADO_BIN="${VIVADO:-/home/elfo/Documents/2025.1/Vivado}/bin/vivado"
BOARD_REPO="${PYNQ_BOARD_REPO:-}"
BUILD_DIR=$(realpath -m "${M5_FAST_VIVADO_BUILD:-$ROOT/build/m5_fast_pynq_v1}")
SOURCE_WORK="$BUILD_DIR/resolved_sources"
EDA="$SOURCE_WORK/pocketai_pa_pa_cluster_m5_board_0.1.eda.yml"
SOURCE_TCL="$SOURCE_WORK/pocketai_sources.tcl"
test -x "$VIVADO_BIN"
test -f "$BOARD_REPO/pynq-z1/1.0/board.xml"
if [[ -e "$BUILD_DIR" ]]; then echo 'use a fresh fast-core build directory' >&2; exit 1; fi
python3 -m tests.m3.generate_sfpu_tables rtl/sfpu --check
mkdir -p "$BUILD_DIR/build_scripts"
cp zynq/build_m5_fast.sh zynq/build_m5.tcl zynq/eda_to_vivado.py \
  scripts/check_m5_sources.py scripts/m5_fast_sources.py "$BUILD_DIR/build_scripts/"
cp rtl/m5_fast/*.sv.inc "$BUILD_DIR/build_scripts/"
python3 -m scripts.m5_fast_sources "$BUILD_DIR/build_scripts/build_m5_fast.tcl" --emit-board-tcl
fusesoc --cores-root=zynq --cores-root=rtl/m5 --cores-root=rtl/soc \
  --cores-root=rtl/gemm --cores-root=rtl/sfpu --cores-root=rtl/ibex-orig \
  run --mapping=lowrisc:prim_xilinx:all:0.1 --target=sources \
  --work-root="$SOURCE_WORK" --setup pocketai:pa:pa_cluster_m5_board
(cd "$SOURCE_WORK" && bash ./m5_prepare_lsu.sh)
touch "$SOURCE_WORK/M5_FAST_TARGET"
if [[ "${M5_FAST_PIPELINED:-0}" = 1 ]]; then touch "$SOURCE_WORK/M5_FAST_PIPELINED"; fi
python3 -m scripts.m5_fast_sources "$SOURCE_WORK" --prepare | tee "$BUILD_DIR/source_configuration.log"
python3 zynq/eda_to_vivado.py "$EDA" "$SOURCE_TCL"
sha256sum "$BUILD_DIR/build_scripts/"* >"$BUILD_DIR/build_scripts.sha256"
export M5_SOURCE_TCL="$SOURCE_TCL" M5_VIVADO_BUILD_DIR="$BUILD_DIR" PYNQ_BOARD_REPO="$BOARD_REPO"
export M5_FAST_REPO_ROOT="$ROOT"
export M5_FAST_PYTHON="$(command -v python3)"
cd "$BUILD_DIR"
"$VIVADO_BIN" -mode batch -nojournal -log "$BUILD_DIR/vivado.log" \
  -source "$BUILD_DIR/build_scripts/build_m5_fast.tcl"
cd "$ROOT"
python3 -m scripts.m5_fast_sources "$SOURCE_WORK"
echo "M5 FAST VIVADO PASS $BUILD_DIR/m5_pynq.bit"
