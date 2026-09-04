#!/usr/bin/env bash
# Complete local M2 gate: authoritative GEMM comparison plus the unchanged M1
# cluster/firmware/lint acceptance suite.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

bash sim/run_gemm.sh
bash sim/run_m1.sh

echo "M2 LOCAL PASS"
