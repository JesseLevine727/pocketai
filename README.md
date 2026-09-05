# PocketAI-T

RISC-V transformer inference SoC: 2x lowRISC Ibex (RV32IMC) + int8 GEMM
accelerator + SFPU, targeting GPT-2 124M (W8A8 GEMM with int16 activation storage)
inference. Fabric-resident on a PYNQ Z1 (Zynq-7020), with a Sky130 ASIC
port; the PPA report (fabric vs. silicon) is the ship-gate.

M1, M2 and M3 are closed at 95 MHz on physical PYNQ-Z1 hardware. M3 adds
GPT-2-correct integer LayerNorm, masked softmax, GELU and scale/vector support,
plus wide-result K=3072 GEMM. Two clean builds and exact-overlay board tests
pass. M4 full-model reference/quantization work is in progress; physical model
inference is not qualified. M5 autonomous control is not started.
See [M3 closure evidence](docs/M3_VERIFICATION.md), [performance](docs/M3_PERFORMANCE.md),
`PLAN.md`, `docs/M1_VERIFICATION.md`, and `docs/M2_VERIFICATION.md`.

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
100 MHz remain stretch targets; M3's independent qualification is below.

## M3 verification — closed

The [M3 plan](docs/M3_PLAN.md) has passed all required gates. Seven SFPU
operations, wide-result GEMM and representative MLP/attention-head chains pass
exact RTL and physical tests under the frozen [numerical contract](docs/NUMERICS.md)
and [interface design](docs/M3_ARCHITECTURE.md). Clean builds close at
**+0.483 / +0.400 ns setup WNS**, zero TNS, **+0.018 / +0.016 ns hold**,
95 MHz, zero DSPs and reviewed DRC/methodology warnings. The physically
qualified overlay is `build/m3_qual3/m3_pynq.bit`.

The [fair physical M2 baseline](docs/M3_PERFORMANCE.md) also passed as an M3
prerequisite. For 16x768x768, the improved host path measures 0.140 GMAC/s including
packing and shared-result delivery (0.164 with prepacked resident inputs).
The matching native CPU baseline measures 0.383 GMAC/s: the current offload
path does not yet beat it. These measurements do not replace the historical
M2 acceptance evidence. On M3, the measured single-row MLP sub-block delivers
in **344.7 ms median**, and the one-head/16-column attention test in **78.0 ms**,
including A9 control, DMA and final publication. These are synthetic operator
chains, not a GPT-2 layer, full-model inference, token rate or CPU speedup.

```bash
PA_CLEAN=1 bash sim/run_m3.sh
# Use a fresh directory for each independent implementation.
PYNQ_BOARD_REPO=/path/to/board_files M3_VIVADO_BUILD_DIR=build/m3_repro1 \
  PA_CLEAN=1 bash zynq/build_m3.sh
M3_VIVADO_BUILD_DIR=build/m3_repro1 bash zynq/run_m3_board.sh
```

The board runner requires a full build PASS, checks source/vector/bit/HWH
hashes before programming over SSH, and runs M1/M2/M3/M1 acceptance. The
[closure record](docs/M3_VERIFICATION.md) contains both accepted build hashes,
complete numerical/protocol/ISA evidence and physical results.

## M4 progress

The [M4 goal](docs/M4_PLAN.md) is active. The real checkpoint/tokenizer are
pinned and an independent floating reference passes three 20-token generations,
cache equivalence and context-boundary checks against Transformers. The first
integer candidate is **not qualified**: real GPT-2 residual outliers exceed
M3's fixed activation range and degrade model quality. Explicit scale/calibration
work is required before FPGA integration; [evidence](docs/M4_VERIFICATION.md)
records the rejected candidate. No full-model hardware performance is claimed.
M5/M6 remain unstarted.

## Repo hygiene

Stage only the intended milestone files, inspect the staged diff, and commit.
Remote pushes require an explicit request. `git_ship.sh` stages all files and
pushes; do not use it when unrelated work is present (including `NA/`).
