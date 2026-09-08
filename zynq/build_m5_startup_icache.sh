#!/usr/bin/env bash
# Isolated same-clock instruction-cache candidate. Final gates are inherited.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
source env.sh
VIVADO_BIN="${VIVADO:-/home/elfo/Documents/2025.1/Vivado}/bin/vivado"
BOARD_REPO="${PYNQ_BOARD_REPO:?set PYNQ_BOARD_REPO}"
STARTUP_BUILD=$(realpath -m "${M5_STARTUP_VIVADO_BUILD:?fresh startup Vivado path}")
SOURCE_WORK="$STARTUP_BUILD/resolved_sources"
EDA="$SOURCE_WORK/pocketai_pa_pa_cluster_m5_board_0.1.eda.yml"
SOURCE_TCL="$SOURCE_WORK/pocketai_sources.tcl"
test -x "$VIVADO_BIN"
test -f "$BOARD_REPO/pynq-z1/1.0/board.xml"
if [[ -e "$STARTUP_BUILD" || "$(basename "$STARTUP_BUILD")" != m5_startup_* ]]; then
  echo 'fresh startup build directory required' >&2; exit 1
fi
python3 -m tests.m3.generate_sfpu_tables rtl/sfpu --check
mkdir -p "$STARTUP_BUILD/build_scripts"
cp zynq/build_m5_startup_icache.sh scripts/m5_startup_icache.py \
  zynq/build_m5.tcl zynq/eda_to_vivado.py scripts/check_m5_sources.py \
  scripts/m5_fast_sources.py "$STARTUP_BUILD/build_scripts/"
cp rtl/m5_fast/*.sv.inc "$STARTUP_BUILD/build_scripts/"
STARTUP_RAM_FLAGS=()
if [[ "${M5_STARTUP_BLOCK_RAM:-0}" = 1 ]]; then STARTUP_RAM_FLAGS=(--block-ram); fi
python3 -m scripts.m5_startup_icache "$STARTUP_BUILD/build_scripts/build_startup.tcl" --emit-board-tcl "${STARTUP_RAM_FLAGS[@]}"
fusesoc --cores-root=zynq --cores-root=rtl/m5 --cores-root=rtl/soc \
  --cores-root=rtl/gemm --cores-root=rtl/sfpu --cores-root=rtl/ibex-orig \
  run --mapping=lowrisc:prim_xilinx:all:0.1 --target=sources \
  --work-root="$SOURCE_WORK" --setup pocketai:pa:pa_cluster_m5_board
(cd "$SOURCE_WORK" && bash ./m5_prepare_lsu.sh)
touch "$SOURCE_WORK/M5_FAST_TARGET" "$SOURCE_WORK/M5_FAST_PIPELINED" "$SOURCE_WORK/M5_STARTUP_ICACHE"
python3 -m scripts.m5_fast_sources "$SOURCE_WORK" --prepare
python3 -m scripts.m5_startup_icache "$SOURCE_WORK" --prepare-export "${STARTUP_RAM_FLAGS[@]}" | tee "$STARTUP_BUILD/source_configuration.log"
python3 zynq/eda_to_vivado.py "$EDA" "$SOURCE_TCL"
sha256sum "$STARTUP_BUILD/build_scripts/"* >"$STARTUP_BUILD/build_scripts.sha256"
export M5_SOURCE_TCL="$SOURCE_TCL" M5_VIVADO_BUILD_DIR="$STARTUP_BUILD" PYNQ_BOARD_REPO="$BOARD_REPO"
export M5_FAST_REPO_ROOT="$ROOT" M5_FAST_PYTHON="$(command -v python3)"
cd "$STARTUP_BUILD"
timeout 2700 "$VIVADO_BIN" -mode batch -nojournal -log "$STARTUP_BUILD/vivado.log" \
  -source "$STARTUP_BUILD/build_scripts/build_startup.tcl"
cd "$ROOT"
python3 -m scripts.m5_startup_icache "$SOURCE_WORK"
echo "STARTUP ICACHE VIVADO PASS $STARTUP_BUILD/m5_pynq.bit"
