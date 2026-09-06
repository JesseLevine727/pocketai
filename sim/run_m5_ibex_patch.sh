#!/usr/bin/env bash
# Exercise the generated-build patch boundary; all mutations are test fixtures.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
M5_PATCH_TEST=$(mktemp -d "$ROOT/build/m5_ibex_patch.XXXXXX")
M5_PATCH_REL=src/lowrisc_ibex_ibex_core_0.1/rtl
prepare_case() {
  local case_name=$1
  mkdir -p "$M5_PATCH_TEST/$case_name/$M5_PATCH_REL"
  cp "$ROOT/rtl/m5/lsu_patch/staged_misaligned.patch" "$M5_PATCH_TEST/$case_name/m5_staged_misaligned.patch"
  cp "$ROOT/rtl/m5/lsu_patch/branch_stall.patch" "$M5_PATCH_TEST/$case_name/m5_branch_stall.patch"
  cp "$ROOT/rtl/ibex-orig/rtl/ibex_id_stage.sv" "$M5_PATCH_TEST/$case_name/$M5_PATCH_REL/ibex_id_stage.sv"
  if [[ "$case_name" != symlink ]]; then
    cp "$ROOT/rtl/ibex-orig/rtl/ibex_load_store_unit.sv" "$M5_PATCH_TEST/$case_name/$M5_PATCH_REL/ibex_load_store_unit.sv"
  fi
}
apply_case() {
  (cd "$M5_PATCH_TEST/$1" && bash "$ROOT/rtl/m5/lsu_patch/apply.sh")
}
expect_refusal() {
  if apply_case "$1" >"$M5_PATCH_TEST/$1.log" 2>&1; then
    echo "M5 PATCH FAIL: unsafe $1 input was accepted" >&2; exit 1
  fi
}
prepare_case normal
if python3 "$ROOT/scripts/check_m5_sources.py" "$M5_PATCH_TEST/normal" \
    >"$M5_PATCH_TEST/export_before.log" 2>&1; then
  echo "M5 PATCH FAIL: source-only export without derivation was accepted" >&2; exit 1
fi
apply_case normal >"$M5_PATCH_TEST/normal.log" 2>&1
apply_case normal >"$M5_PATCH_TEST/repeat.log" 2>&1
python3 "$ROOT/scripts/check_m5_sources.py" "$M5_PATCH_TEST/normal" \
  >"$M5_PATCH_TEST/export_after.log" 2>&1
prepare_case unknown_lsu
printf 'invalid test fixture\n' >"$M5_PATCH_TEST/unknown_lsu/$M5_PATCH_REL/ibex_load_store_unit.sv"
expect_refusal unknown_lsu
prepare_case unknown_id
printf 'invalid test fixture\n' >"$M5_PATCH_TEST/unknown_id/$M5_PATCH_REL/ibex_id_stage.sv"
expect_refusal unknown_id
prepare_case symlink
ln -s "$ROOT/rtl/ibex-orig/rtl/ibex_load_store_unit.sv" \
  "$M5_PATCH_TEST/symlink/$M5_PATCH_REL/ibex_load_store_unit.sv"
expect_refusal symlink
# Verify the original dependency trees still match their historical patch pins.
bash "$ROOT/scripts/check_deps.sh" all >"$M5_PATCH_TEST/deps.log" 2>&1
echo "M5 IBEX PATCH BOUNDARY PASS normal=1 idempotent=1 rejected=3 export_guard=1 frozen_deps=unchanged" \
  | tee "$M5_PATCH_TEST/result.log"
echo "M5 PATCH EVIDENCE $M5_PATCH_TEST"
