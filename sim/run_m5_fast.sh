#!/usr/bin/env bash
# Reuse qualified integration harnesses on freshly exported fast-M sources.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
source env.sh
M5_FAST_KIND=${1:-memory}
M5_FAST_TEST=$(mktemp -d "$ROOT/build/m5_fast_${M5_FAST_KIND}.XXXXXX")
case "$M5_FAST_KIND" in
  memory) M5_FAST_CORE=pa_m5_cluster; M5_FAST_FIRMWARE=firmware/m5_fast/arithmetic_test.c ;;
  accelerators) M5_FAST_CORE=pa_m5_accelerators; M5_FAST_FIRMWARE=firmware/m5/accelerator_test.c ;;
  numerics) M5_FAST_CORE=pa_m5_numerics; M5_FAST_FIRMWARE=firmware/m5/numerics_test.c ;;
  *) echo 'expected memory, accelerators or numerics' >&2; exit 1 ;;
esac
M5_FAST_EXTRA=()
if [[ "$M5_FAST_KIND" = numerics ]]; then M5_FAST_EXTRA=(runtime/m5_opt/pa_m5_metadata_opt.c); fi
riscv64-unknown-elf-gcc -march=rv32imc_zicsr -mabi=ilp32 -O2 -fno-fast-math \
  -msmall-data-limit=0 -mno-relax -Wall -Wextra -Werror -nostdlib -ffreestanding -fno-builtin \
  -Wl,--fatal-warnings -T firmware/m5/memory_test.ld -Iruntime/m5 \
  firmware/m5/memory_test_start.S "$M5_FAST_FIRMWARE" "${M5_FAST_EXTRA[@]}" -lgcc \
  -o "$M5_FAST_TEST/test.elf" >"$M5_FAST_TEST/firmware.log" 2>&1
riscv64-unknown-elf-objcopy -O binary --gap-fill 0 --pad-to 65536 \
  "$M5_FAST_TEST/test.elf" "$M5_FAST_TEST/test.bin"
fusesoc --cores-root=sim/pa_m5_cluster --cores-root=rtl/m5 --cores-root=rtl/soc \
  --cores-root=rtl/gemm --cores-root=rtl/sfpu --cores-root=rtl/ibex-orig \
  run --target=sim --work-root="$M5_FAST_TEST/sim" --setup "pocketai:pa:$M5_FAST_CORE" \
  >"$M5_FAST_TEST/setup.log" 2>&1
touch "$M5_FAST_TEST/sim/M5_FAST_TARGET"
if [[ "${M5_FAST_PIPELINED:-0}" = 1 ]]; then touch "$M5_FAST_TEST/sim/M5_FAST_PIPELINED"; fi
(cd "$M5_FAST_TEST/sim" && bash ./m5_prepare_lsu.sh) >"$M5_FAST_TEST/derivation.log" 2>&1
python3 -m scripts.m5_fast_sources "$M5_FAST_TEST/sim" --prepare | tee -a "$M5_FAST_TEST/derivation.log"
# A second FuseSoC build would re-export the slow wrapper; call make directly.
make -C "$M5_FAST_TEST/sim" -j8 >"$M5_FAST_TEST/build.log" 2>&1 || {
  tail -n 70 "$M5_FAST_TEST/build.log"; exit 1;
}
python3 -m scripts.m5_fast_sources "$M5_FAST_TEST/sim" --model | tee "$M5_FAST_TEST/configuration.log"
(cd "$M5_FAST_TEST/sim" && timeout 120 ./Vpa_m5_cluster_top "$M5_FAST_TEST/test.bin") \
  2>&1 | tee "$M5_FAST_TEST/test.log"
if [[ "$M5_FAST_KIND" = accelerators ]]; then
  (cd "$M5_FAST_TEST/sim" && PA_M5_AXI_DELAY=7 timeout 120 ./Vpa_m5_cluster_top "$M5_FAST_TEST/test.bin") \
    2>&1 | tee "$M5_FAST_TEST/delayed.log"
fi
sha256sum "$M5_FAST_TEST/test.bin" "$M5_FAST_TEST/sim/Vpa_m5_cluster_top" >"$M5_FAST_TEST/artifacts.sha256"
echo "M5 FAST $M5_FAST_KIND EVIDENCE $M5_FAST_TEST"
