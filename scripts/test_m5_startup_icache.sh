#!/usr/bin/env bash
# Matched cache-off/on simulation of unchanged RV32 numerical qualification.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
source env.sh
STARTUP_ICACHE_BUILD=$(realpath -m "${M5_STARTUP_ICACHE_BUILD:?fresh startup test directory}")
if [[ -e "$STARTUP_ICACHE_BUILD" ]]; then echo 'fresh simulation directory required' >&2; exit 1; fi
mkdir -p "$STARTUP_ICACHE_BUILD"
fusesoc --cores-root=sim/pa_m5_cluster --cores-root=rtl/m5 --cores-root=rtl/soc \
  --cores-root=rtl/gemm --cores-root=rtl/sfpu --cores-root=rtl/ibex-orig \
  run --target=sim --work-root="$STARTUP_ICACHE_BUILD/sim" --setup pocketai:pa:pa_m5_numerics \
  >"$STARTUP_ICACHE_BUILD/setup.log" 2>&1
touch "$STARTUP_ICACHE_BUILD/sim/M5_FAST_TARGET" "$STARTUP_ICACHE_BUILD/sim/M5_FAST_PIPELINED"
(cd "$STARTUP_ICACHE_BUILD/sim" && bash ./m5_prepare_lsu.sh) >"$STARTUP_ICACHE_BUILD/lsu.log" 2>&1
python3 -m scripts.m5_fast_sources "$STARTUP_ICACHE_BUILD/sim" --prepare >"$STARTUP_ICACHE_BUILD/parent.log"
python3 -m scripts.m5_startup_icache "$STARTUP_ICACHE_BUILD" --prepare
for STARTUP_ICACHE_ENABLE in 0 1; do
  riscv64-unknown-elf-gcc -march=rv32imc_zicsr -mabi=ilp32 -O2 -fno-fast-math \
    -DSTARTUP_ICACHE_ENABLE="$STARTUP_ICACHE_ENABLE" -msmall-data-limit=0 -mno-relax \
    -Wall -Wextra -Werror -nostdlib -ffreestanding -fno-builtin -Wl,--fatal-warnings \
    -T firmware/m5/memory_test.ld -Iruntime/m5 "$STARTUP_ICACHE_BUILD/start.S" \
    firmware/m5/numerics_test.c runtime/m5_opt/pa_m5_metadata_opt.c -lgcc \
    -o "$STARTUP_ICACHE_BUILD/cache_$STARTUP_ICACHE_ENABLE.elf" \
    >"$STARTUP_ICACHE_BUILD/firmware_$STARTUP_ICACHE_ENABLE.log" 2>&1
  riscv64-unknown-elf-objcopy -O binary --gap-fill 0 --pad-to 65536 \
    "$STARTUP_ICACHE_BUILD/cache_$STARTUP_ICACHE_ENABLE.elf" "$STARTUP_ICACHE_BUILD/cache_$STARTUP_ICACHE_ENABLE.bin"
done
make -C "$STARTUP_ICACHE_BUILD/sim" -j8 >"$STARTUP_ICACHE_BUILD/build.log" 2>&1
for STARTUP_ICACHE_ENABLE in 0 1; do
  (cd "$STARTUP_ICACHE_BUILD/sim" && timeout 120 ./Vpa_m5_cluster_top "$STARTUP_ICACHE_BUILD/cache_$STARTUP_ICACHE_ENABLE.bin") \
    2>&1 | tee "$STARTUP_ICACHE_BUILD/cache_$STARTUP_ICACHE_ENABLE.log"
done
sha256sum "$STARTUP_ICACHE_BUILD/"*.bin "$STARTUP_ICACHE_BUILD/sim/Vpa_m5_cluster_top" >"$STARTUP_ICACHE_BUILD/artifacts.sha256"
echo "STARTUP ICACHE NUMERICAL SIMULATION PASS $STARTUP_ICACHE_BUILD"
