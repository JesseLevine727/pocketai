#!/usr/bin/env bash
# M5-only FuseSoC pre-build hook. Never patch the frozen repository source.
set -euo pipefail
M5_LSU_TARGET=src/lowrisc_ibex_ibex_core_0.1/rtl/ibex_load_store_unit.sv
M5_LSU_ORIGINAL=e85e87c1eb3c77c5c78db67793383cd23480afdfedd79b39fedc3eff2cc6945d
M5_LSU_FIXED=7fe4d5c261420f9862783978c9d9370a65dae6f360b5780f7afca19b090a8791
test -f "$M5_LSU_TARGET"
test ! -L "$M5_LSU_TARGET"
test "$(realpath "$M5_LSU_TARGET")" = "$(pwd -P)/$M5_LSU_TARGET"
M5_LSU_ACTUAL=$(sha256sum "$M5_LSU_TARGET")
M5_LSU_ACTUAL=${M5_LSU_ACTUAL%% *}
if [[ "$M5_LSU_ACTUAL" = "$M5_LSU_ORIGINAL" ]]; then
  patch --batch --forward --fuzz=0 --no-backup-if-mismatch \
    "$M5_LSU_TARGET" m5_staged_misaligned.patch
elif [[ "$M5_LSU_ACTUAL" != "$M5_LSU_FIXED" ]]; then
  echo "M5 LSU ERROR: unexpected exported source identity" >&2
  exit 1
fi
M5_LSU_ACTUAL=$(sha256sum "$M5_LSU_TARGET")
test "${M5_LSU_ACTUAL%% *}" = "$M5_LSU_FIXED"
echo "M5 LSU DERIVATION PASS original=$M5_LSU_ORIGINAL compiled=$M5_LSU_FIXED"

M5_ID_TARGET=src/lowrisc_ibex_ibex_core_0.1/rtl/ibex_id_stage.sv
M5_ID_ORIGINAL=eb14d2cd21b6dae9432cd1e40ab7d512828de44f32c0a1fff86e725ed1cb8fe6
M5_ID_FIXED=1e9d382752cf9f13477f279ddc3f73a2b3d7bbd8e5cf8e4a7a9d755f6162c5f1
test -f "$M5_ID_TARGET"
test ! -L "$M5_ID_TARGET"
test "$(realpath "$M5_ID_TARGET")" = "$(pwd -P)/$M5_ID_TARGET"
M5_ID_ACTUAL=$(sha256sum "$M5_ID_TARGET")
M5_ID_ACTUAL=${M5_ID_ACTUAL%% *}
if [[ "$M5_ID_ACTUAL" = "$M5_ID_ORIGINAL" ]]; then
  patch --batch --forward --fuzz=0 --no-backup-if-mismatch \
    "$M5_ID_TARGET" m5_branch_stall.patch
elif [[ "$M5_ID_ACTUAL" != "$M5_ID_FIXED" ]]; then
  echo "M5 ID ERROR: unexpected exported source identity" >&2
  exit 1
fi
M5_ID_ACTUAL=$(sha256sum "$M5_ID_TARGET")
test "${M5_ID_ACTUAL%% *}" = "$M5_ID_FIXED"
echo "M5 ID DERIVATION PASS original=$M5_ID_ORIGINAL compiled=$M5_ID_FIXED"
