#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source env.sh
fusesoc --cores-root=rtl/soc --cores-root=rtl/gemm --cores-root=rtl/sfpu \
  --cores-root=rtl/ibex-orig run --target=lint_m3 --clean --build \
  pocketai:pa:pa_cluster_rtl
echo "M3 LINT PASS"
