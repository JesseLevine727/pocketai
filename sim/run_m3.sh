#!/usr/bin/env bash
# Complete LOCAL gate only. FPGA implementation/physical acceptance are separate.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python3 -m unittest discover -s tests/m3 -v
python3 -m tests.m3.qualify_numerics --random-cases 10000 \
  --output build/m3_numerics_final.json
bash sim/run_gemm_v3.sh
bash sim/run_sfpu_alu.sh
bash sim/run_sfpu.sh
bash sim/run_cluster_m3.sh
bash sim/run_m2.sh
bash scripts/lint_m3.sh
bash scripts/run_compliance.sh
echo "M3 LOCAL PASS"
