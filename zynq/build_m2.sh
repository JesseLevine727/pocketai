#!/usr/bin/env bash
# Build the routed PYNQ-Z1 M2 cluster/GEMM/AXI-DMA overlay with Vivado 2025.1.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=env.sh
source env.sh

VIVADO_BIN="${VIVADO:-/home/elfo/Documents/2025.1/Vivado}/bin/vivado"
BOARD_REPO="${PYNQ_BOARD_REPO:-}"
BUILD_DIR="$(realpath -m "${M2_VIVADO_BUILD_DIR:-$ROOT/build/m2_pynq}")"
# Keep resolved sources and logs private to this build, including when two
# independent clean qualification builds run concurrently.
SOURCE_WORK="$BUILD_DIR/resolved_sources"
EDA="$SOURCE_WORK/pocketai_pa_pa_cluster_m2_board_0.1.eda.yml"
SOURCE_TCL="$SOURCE_WORK/pocketai_sources.tcl"

if [[ ! -x "$VIVADO_BIN" ]]; then
  echo "[build_m2] FAIL: Vivado executable missing: $VIVADO_BIN" >&2
  exit 1
fi
if [[ -z "$BOARD_REPO" || ! -f "$BOARD_REPO/pynq-z1/1.0/board.xml" ]]; then
  echo "[build_m2] FAIL: set PYNQ_BOARD_REPO to a board-files directory containing pynq-z1/1.0/board.xml" >&2
  exit 1
fi

bash scripts/build_m1_firmware.sh

clean_args=()
if [[ "${PA_CLEAN:-0}" == "1" ]]; then
  clean_args+=(--clean)
fi
fusesoc --cores-root=zynq --cores-root=rtl/soc --cores-root=rtl/gemm \
  --cores-root=rtl/ibex-orig \
  run --mapping=lowrisc:prim_xilinx:all:0.1 --target=sources \
  --work-root="$SOURCE_WORK" "${clean_args[@]}" --setup \
  pocketai:pa:pa_cluster_m2_board

python3 zynq/eda_to_vivado.py "$EDA" "$SOURCE_TCL"

export M2_SOURCE_TCL="$SOURCE_TCL"
export M2_VIVADO_BUILD_DIR="$BUILD_DIR"
export PYNQ_BOARD_REPO="$BOARD_REPO"
"$VIVADO_BIN" -mode batch -nojournal -log "$BUILD_DIR/vivado.log" \
  -source zynq/build_m2.tcl

echo "[build_m2] M2 VIVADO PASS: $BUILD_DIR/m2_pynq.bit"
