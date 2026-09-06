#!/usr/bin/env bash
# Fresh M5-derived Ibex ISA regression; no legacy work directory is reused.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=env.sh
source env.sh

IBEX_DIR="$ROOT/rtl/ibex-orig"
COMPLIANCE_DIR="$ROOT/riscv-compliance"
M5_ISA_BUILD=$(mktemp -d "$ROOT/build/m5_compliance.XXXXXX")
SIM_WORK="$M5_ISA_BUILD/sim"
SIM="$SIM_WORK/Vibex_riscv_compliance"
SIM_CONFIG="$SIM_WORK/lowrisc_ibex_ibex_riscv_compliance_0.1.vc"
SIM_MODEL_HEADER="$SIM_WORK/Vibex_riscv_compliance___024root.h"

bash scripts/check_deps.sh all

echo "[run_compliance] building the M5-derived Ibex configuration ..."
fusesoc --cores-root="$IBEX_DIR" run --target=sim --work-root="$SIM_WORK" \
  --setup lowrisc:ibex:ibex_riscv_compliance \
  --BaseIsaCfg=ibex_pkg::BaseIsaRV32I \
  --RV32MCfg=ibex_pkg::RV32MSlow \
  --RV32BCfg=ibex_pkg::RV32BNone \
  --RV32ZCCfg=ibex_pkg::RV32Zca \
  --RegFileCfg=ibex_pkg::RegFileFPGA \
  --BranchTargetALU=0 --WritebackStage=1 --BranchPredictor=0 \
  --ICache=0 --ICacheECC=0 --PMPEnable=0 --SecureIbex=0 \
  >"$M5_ISA_BUILD/setup.log" 2>&1

# Apply the same source-identity-checked derivation used by the M5 RTL hook.
# Call the generated makefile directly: another FuseSoC --build re-exports the
# original dependencies during setup and would silently discard this patch.
cp rtl/m5/lsu_patch/staged_misaligned.patch "$SIM_WORK/m5_staged_misaligned.patch"
cp rtl/m5/lsu_patch/branch_stall.patch "$SIM_WORK/m5_branch_stall.patch"
(cd "$SIM_WORK" && bash "$ROOT/rtl/m5/lsu_patch/apply.sh") \
  >"$M5_ISA_BUILD/derivation.log" 2>&1
make -C "$SIM_WORK" \
  "VERILATOR=$VERILATOR_ROOT/bin/verilator $ROOT/rtl/m5/pa_m5_verilator_waiver.vlt" \
  >"$M5_ISA_BUILD/build.log" 2>&1 || { tail -n 70 "$M5_ISA_BUILD/build.log"; exit 1; }

if [[ ! -x "$SIM" ]]; then
  echo "[run_compliance] FAIL: simulator was not produced: $SIM" >&2
  exit 1
fi

# Guard against FuseSoC/Edalize silently retaining an enum parameter's default.
# This happened when enum-valued settings were represented as top-level defines
# that the compliance wrapper never consumed.
for required_setting in \
  '-DRV32MCfg=ibex_pkg::RV32MSlow' \
  '-DRV32BCfg=ibex_pkg::RV32BNone' \
  '-DRV32ZCCfg=ibex_pkg::RV32Zca' \
  '-DRegFileCfg=ibex_pkg::RegFileFPGA' \
  '-GBranchTargetALU=0' \
  '-GWritebackStage=1' \
  '-GBranchPredictor=0' \
  '-GICache=0' \
  '-GPMPEnable=0' \
  '-GSecureIbex=0'; do
  if ! grep -Fqx -- "$required_setting" "$SIM_CONFIG"; then
    echo "[run_compliance] FAIL: elaboration setting missing: $required_setting" >&2
    exit 1
  fi
done
if ! grep -Fq 'gen_multdiv_slow__DOT__multdiv_i__DOT__md_state_q' \
  "$SIM_MODEL_HEADER" ||
   ! grep -Fq 'gen_regfile_fpga__DOT__register_file_i' "$SIM_MODEL_HEADER"; then
  echo "[run_compliance] FAIL: generated model is not slow-M/FPGA-regfile M5" >&2
  exit 1
fi

declare -A expected_total=(
  [rv32imc]=25
  [rv32im]=8
  [rv32i]=48
  [rv32Zicsr]=6
  [rv32Zifencei]=1
)
declare -A expected_fail=(
  [rv32i/I-EBREAK-01]=1
  [rv32i/I-ECALL-01]=1
  [rv32i/I-MISALIGN_JMP-01]=1
  [rv32i/I-MISALIGN_LDST-01]=1
)

summary=()
for isa in rv32imc rv32im rv32i rv32Zicsr rv32Zifencei; do
  echo "[run_compliance] running $isa ..."
  make -s -C "$COMPLIANCE_DIR" RISCV_TARGET=ibex RISCV_DEVICE=rv32imc \
    RISCV_ISA="$isa" RISCV_PREFIX=riscv32-unknown-elf- TARGET_SIM="$SIM" \
    work_dir="$M5_ISA_BUILD/work" \
    TARGET_FLAGS="+ibex_tracer_enable=0" simulate >"$M5_ISA_BUILD/$isa.log" 2>&1

  suite="$COMPLIANCE_DIR/riscv-test-suite/$isa"
  output="$M5_ISA_BUILD/work/$isa"
  pass=0
  xfail=0
  total=0
  shopt -s nullglob
  for reference in "$suite"/references/*.reference_output; do
    ((total += 1))
    test_name="$(basename "$reference" .reference_output)"
    signature="$output/$test_name.signature.output"
    key="$isa/$test_name"
    matches=0
    if [[ -f "$signature" ]] && diff -q --strip-trailing-cr \
      "$reference" "$signature" >/dev/null; then
      matches=1
    fi

    if [[ -n "${expected_fail[$key]+x}" ]]; then
      if ((matches)); then
        echo "[run_compliance] FAIL: unexpected pass $key; review the whitelist" >&2
        exit 1
      fi
      ((xfail += 1))
    elif ((matches)); then
      ((pass += 1))
    else
      echo "[run_compliance] FAIL: $key" >&2
      exit 1
    fi
  done
  shopt -u nullglob

  if ((total != expected_total[$isa])); then
    echo "[run_compliance] FAIL: $isa has $total tests; expected ${expected_total[$isa]}" >&2
    exit 1
  fi
  if ((pass + xfail != total)); then
    echo "[run_compliance] FAIL: internal result count mismatch for $isa" >&2
    exit 1
  fi
  if ((xfail)); then
    summary+=("$isa=$pass/$total+$xfail-xfail")
  else
    summary+=("$isa=$pass/$total")
  fi
done

echo "M5 DERIVED-IBEX COMPLIANCE PASS ${summary[*]}" | tee "$M5_ISA_BUILD/result.log"
echo "M5 ISA EVIDENCE $M5_ISA_BUILD"
