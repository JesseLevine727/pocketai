#!/usr/bin/env bash
# Verify that external source trees match the revisions used to qualify M1.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IBEX_DIR="$ROOT/rtl/ibex-orig"
COMPLIANCE_DIR="$ROOT/riscv-compliance"
IBEX_REV="34b0705760ef3dfa00e99637432473d2be8f22f3"
COMPLIANCE_REV="844c6660ef3f0d9b96957991109dfd80cc4938e2"
IBEX_PATCH="$ROOT/patches/ibex-34b0705.m1-timing.diff"
MODE="${1:-sim}"

check_checkout() {
  local label="$1"
  local dir="$2"
  local expected="$3"

  if [[ ! -d "$dir/.git" ]]; then
    echo "[check_deps] FAIL: $label checkout missing: $dir" >&2
    return 1
  fi

  local actual
  actual="$(git -C "$dir" rev-parse HEAD)"
  if [[ "$actual" != "$expected" ]]; then
    echo "[check_deps] FAIL: $label revision $actual; expected $expected" >&2
    return 1
  fi
  echo "[check_deps] $label revision OK: $actual"
}

check_patch_applied() {
  local label="$1"
  local dir="$2"
  local patch="$3"

  if ! (cd "$dir" && git apply --reverse --check "$patch"); then
    echo "[check_deps] FAIL: the tracked $label patch is not fully applied" >&2
    return 1
  fi
  if ! cmp -s <(git -C "$dir" diff --no-ext-diff --binary) "$patch"; then
    echo "[check_deps] FAIL: $label checkout differs from its tracked patch" >&2
    return 1
  fi
  echo "[check_deps] $label patch OK: ${patch#"$ROOT/"}"
}

case "$MODE" in
  sim)
    check_checkout "Ibex" "$IBEX_DIR" "$IBEX_REV"
    check_patch_applied "Ibex M1" "$IBEX_DIR" "$IBEX_PATCH"
    ;;
  all)
    check_checkout "Ibex" "$IBEX_DIR" "$IBEX_REV"
    check_patch_applied "Ibex M1" "$IBEX_DIR" "$IBEX_PATCH"
    check_checkout "riscv-compliance" "$COMPLIANCE_DIR" "$COMPLIANCE_REV"
    check_patch_applied "riscv-compliance" "$COMPLIANCE_DIR" \
      "$ROOT/patches/riscv-compliance-844c6660.local-patches.diff"
    ;;
  *)
    echo "usage: $0 [sim|all]" >&2
    exit 2
    ;;
esac
