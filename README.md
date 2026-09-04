# PocketAI-T

RISC-V transformer inference SoC: 2x lowRISC Ibex (RV32IMC) + int8 GEMM
accelerator + SFPU, targeting GPT-2 124M (int8 weights / int16 activations)
inference. Fabric-resident on a PYNQ Z1 (Zynq-7020), with a Sky130 ASIC
port; the PPA report (fabric vs. silicon) is the ship-gate.

M1 and M2 are closed at 95 MHz on physical PYNQ-Z1 hardware. M2 adds a
double-buffered signed-int8 GEMM accelerator and DDR/DMA streaming, with exact
NumPy-checked results. M3 (SFPU) has not started. See `PLAN.md`,
`docs/M1_VERIFICATION.md`, and `docs/M2_VERIFICATION.md` for acceptance evidence.

## Dependencies (not tracked in this repo)

| Path                  | What                          | Pinned at                                        |
|-----------------------|-------------------------------|--------------------------------------------------|
| `rtl/ibex-orig/`      | lowRISC Ibex                  | `34b0705760ef3dfa00e99637432473d2be8f22f3`       |
| `riscv-compliance/`   | riscv-arch/riscv-compliance   | `844c6660ef3f0d9b96957991109dfd80cc4938e2` + local patches in `patches/` |

Fetch:

```bash
git clone git@github.com:lowRISC/ibex.git rtl/ibex-orig
git -C rtl/ibex-orig checkout 34b0705760ef3dfa00e99637432473d2be8f22f3
git -C rtl/ibex-orig apply ../../patches/ibex-34b0705.m1-timing.diff
git clone git@github.com:riscv-arch/riscv-compliance.git riscv-compliance
git -C riscv-compliance checkout 844c6660ef3f0d9b96957991109dfd80cc4938e2
git -C riscv-compliance apply ../patches/riscv-compliance-844c6660.local-patches.diff
bash scripts/check_deps.sh all
```

Toolchain (riscv32-unknown-elf GCC, Verilator, FuseSoC, srecord): see
`env.sh`.

## M1 verification

```bash
source env.sh
PA_CLEAN=1 bash sim/run_m1.sh    # focused tests + smoke + 2-hart workload + lint
PA_CLEAN=1 bash scripts/run_compliance.sh  # exact M1 Ibex configuration
```

The aggregate local gate requires exactly 10,000 interrupt-driven mailbox
rounds per hart, validates the result ABI and checksums, and treats RTL warnings
as errors apart from one narrow upstream Ibex waiver.

Build the PYNQ-Z1 overlay with Vivado 2025.1:

```bash
export PYNQ_BOARD_REPO=/path/to/board_files
PA_CLEAN=1 bash zynq/build_m1.sh
```

The final routed design has +0.330 ns setup WNS, 0.000 ns setup TNS, and
+0.076 ns hold WNS at 95 MHz, with no DSP48 primitives and no DRC errors. Its
single reviewed DRC warning is documented and enforced by the build gate. A
100 MHz implementation remains a stretch target rather than an M1 blocker.
Run that exact overlay on the board over SSH:

```bash
export PYNQ_HOST=xilinx@pynq-host-or-address  # optional; defaults to 10.0.0.223
bash zynq/run_m1_board.sh
```

The stock PYNQ image prompts for normal `sudo` authentication because overlay
programming and MMIO require root. The runner preserves the board's XRT
environment with `sudo -E`; JTAG is not used. See `docs/M1_VERIFICATION.md` for
the qualified configuration, memory map, result ABI, and recorded evidence.

## M2 verification

```bash
PA_CLEAN=1 bash sim/run_m2.sh
PA_CLEAN=1 bash scripts/run_compliance.sh
export PYNQ_BOARD_REPO=/path/to/board_files
PA_CLEAN=1 bash zynq/build_m2.sh
bash zynq/run_m2_board.sh
```

The engine accepts logical tiles up to 16x16 with K up to 768. A 4x16 physical
array uses 64 soft MAC lanes, 25-bit accumulation, and one final int16
saturation. Two tile buffers overlap input, compute, and output. All 1,007
deterministic numerical cases, protocol/error tests, and M1 regressions pass.

Two independent clean builds closed at +0.499/+0.486 ns setup WNS, zero TNS,
+0.018 ns hold slack, zero DSP48s, and zero DRC errors. The exact second overlay
passed both the M1 board workload and a 16x768x768 projection: all 12,288 int16
results and the shared-memory readback matched exactly.

Measured accelerator throughput is 5.793 GMAC/s from cycle counters at 95 MHz;
software-driven packed A/B input bandwidth is 29.821 MB/s. End-to-end latency
is 110.649 ms (0.085 GMAC/s), including DMA, validation, and A9 publication to
shared memory. These are not GPT-2 inference or CPU-speedup results.

See `docs/NUMERICS.md` and `docs/M2_ARCHITECTURE.md` for the contract and
`docs/M2_VERIFICATION.md` for exact artifact paths/hashes, reproduction commands,
performance boundaries, and reviewed warnings. The +0.500 ns margin and
100 MHz remain stretch targets; M3 requires independent timing qualification.

## Repo hygiene

Commit after every little milestone: `bash git_ship.sh "message"`
(adds all tracked changes, commits, pushes).
