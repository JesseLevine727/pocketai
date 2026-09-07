#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
ITER_WAIT_BUILD=$(realpath -m "${M5_ITER_WAIT_BUILD:?set a fresh M5_ITER_WAIT_BUILD}")
test ! -e "$ITER_WAIT_BUILD"
mkdir -p "$ITER_WAIT_BUILD"
python3 -m scripts.m5_fast_sources build/m5_fast_memory.ljzJvY/sim --model >"$ITER_WAIT_BUILD/model_identity.log"
riscv64-unknown-elf-gcc -march=rv32imc_zicsr -mabi=ilp32 -O2 -fno-fast-math \
  -msmall-data-limit=0 -mno-relax -Wall -Wextra -Werror -nostdlib -ffreestanding -fno-builtin \
  -Wl,--fatal-warnings -T firmware/m5/memory_test.ld -Iruntime/m5 \
  firmware/m5/memory_test_start.S firmware/m5_iterate/wait_test.c -lgcc \
  -o "$ITER_WAIT_BUILD/wait.elf" >"$ITER_WAIT_BUILD/firmware.log" 2>&1
riscv64-unknown-elf-objcopy -O binary --gap-fill 0 --pad-to 65536 \
  "$ITER_WAIT_BUILD/wait.elf" "$ITER_WAIT_BUILD/wait.bin"
ITER_WAIT_ROOT=$PWD
ln -s "$ITER_WAIT_ROOT/rtl/sfpu/gelu_q8.mem" "$ITER_WAIT_BUILD/gelu_q8.mem"
ln -s "$ITER_WAIT_ROOT/rtl/sfpu/exp_q24.mem" "$ITER_WAIT_BUILD/exp_q24.mem"
(cd "$ITER_WAIT_BUILD" && timeout 120 "$ITER_WAIT_ROOT/build/m5_fast_memory.ljzJvY/sim/Vpa_m5_cluster_top" "$ITER_WAIT_BUILD/wait.bin") \
  | tee "$ITER_WAIT_BUILD/simulation.log"
sha256sum "$ITER_WAIT_BUILD/wait.bin" build/m5_fast_memory.ljzJvY/sim/Vpa_m5_cluster_top \
  firmware/m5_iterate/wait_test.c runtime/m5_iterate/mailbox_wait.c.inc >"$ITER_WAIT_BUILD/artifacts.sha256"
echo 'M5 ITERATE WFI BOTH-HART NO-TRAP AND MEMORY/RESET REGRESSION PASS'
