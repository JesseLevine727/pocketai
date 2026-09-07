#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
ITER_CLOCK_ROOT=$PWD
ITER_CLOCK_BUILD=$(realpath -m "${M5_ITER_CLOCK_BUILD:?set a fresh M5_ITER_CLOCK_BUILD}")
test ! -e "$ITER_CLOCK_BUILD"
mkdir -p "$ITER_CLOCK_BUILD"
ln -s "$ITER_CLOCK_ROOT/rtl/sfpu/gelu_q8.mem" "$ITER_CLOCK_BUILD/gelu_q8.mem"
ln -s "$ITER_CLOCK_ROOT/rtl/sfpu/exp_q24.mem" "$ITER_CLOCK_BUILD/exp_q24.mem"
for poll in 0 1; do
  riscv64-unknown-elf-gcc -march=rv32imc_zicsr -mabi=ilp32 -O2 -fno-fast-math \
    -msmall-data-limit=0 -mno-relax -Wall -Wextra -Werror -nostdlib -ffreestanding -fno-builtin \
    -Wl,--fatal-warnings -T firmware/m5/memory_test.ld -Iruntime/m5 -DITER_POLL=$poll \
    firmware/m5/memory_test_start.S firmware/m5_iterate/clock_test.c -lgcc \
    -o "$ITER_CLOCK_BUILD/clock_$poll.elf" >"$ITER_CLOCK_BUILD/firmware_$poll.log" 2>&1
  riscv64-unknown-elf-objcopy -O binary --gap-fill 0 --pad-to 65536 \
    "$ITER_CLOCK_BUILD/clock_$poll.elf" "$ITER_CLOCK_BUILD/clock_$poll.bin"
  set +e
  (cd "$ITER_CLOCK_BUILD" && timeout 120 "$ITER_CLOCK_ROOT/build/m5_fast_memory.ljzJvY/sim/Vpa_m5_cluster_top" "$ITER_CLOCK_BUILD/clock_$poll.bin") \
    >"$ITER_CLOCK_BUILD/simulation_$poll.log" 2>&1
  ITER_CLOCK_RC=$?
  set -e
  if [[ "$poll" = 0 ]]; then
    test "$ITER_CLOCK_RC" = 1
    rg -q 'hart=0 state=3 errors=00010000' "$ITER_CLOCK_BUILD/simulation_0.log"
    echo 'M5 ITERATE CLOCK RED: hart-0 WFI undercounts an independently timed wait'
  else
    test "$ITER_CLOCK_RC" = 0
    rg 'M5 ACTUAL DUAL-IBEX MEMORY SIMULATION PASS' "$ITER_CLOCK_BUILD/simulation_1.log"
    echo 'M5 ITERATE CLOCK GREEN: hart-0 polling includes elapsed service time'
  fi
done
sha256sum "$ITER_CLOCK_BUILD/"*.bin build/m5_fast_memory.ljzJvY/sim/Vpa_m5_cluster_top \
  firmware/m5_iterate/clock_test.c runtime/m5_iterate/mailbox_wait.c.inc >"$ITER_CLOCK_BUILD/artifacts.sha256"
