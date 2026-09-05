#!/usr/bin/env bash
# Fatal-warning Verilator lint for the complete synthesizable M1 cluster.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=env.sh
source env.sh

bash scripts/check_deps.sh sim
fusesoc --cores-root=rtl/soc --cores-root=rtl/gemm --cores-root=rtl/sfpu --cores-root=rtl/ibex-orig \
  run --target=lint --clean --build pocketai:pa:pa_cluster_rtl
echo "M1 LINT PASS"
