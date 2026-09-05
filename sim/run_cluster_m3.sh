#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source env.sh
OUT="$ROOT/build/pa_cluster_m3"
mkdir -p "$OUT"
bash scripts/build_m1_firmware.sh
python3 -m tests.m3.generate_chain_vectors "$OUT/chains.bin"
clean_args=()
if [[ "${PA_CLEAN:-0}" == 1 ]]; then clean_args+=(--clean); fi
fusesoc --cores-root=sim/pa_cluster --cores-root=rtl/soc --cores-root=rtl/gemm \
  --cores-root=rtl/sfpu --cores-root=rtl/ibex-orig \
  run --target=sim_m3 --work-root="$OUT/sim" "${clean_args[@]}" --build pocketai:pa:pa_cluster
cd "$OUT/sim"
PA_M3_CHAIN_VECTORS="$OUT/chains.bin" ./Vpa_cluster_top \
  --meminit="ram,$ROOT/build/pa_cluster/cluster.elf" | tee "$OUT/cluster.log"
rg -q 'M3 CLUSTER CHAINS PASS' "$OUT/cluster.log"
rg -q 'M1 RESULTS OK' "$OUT/cluster.log"
echo 'M3 CLUSTER PASS'
