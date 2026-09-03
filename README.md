# PocketAI-T

RISC-V transformer inference SoC: 2x lowRISC Ibex (RV32IMC) + int8 GEMM
accelerator + SFPU, targeting GPT-2 124M (int8 weights / int16 activations)
inference. Fabric-resident on a PYNQ Z1 (Zynq-7020), with a Sky130 ASIC
port; the PPA report (fabric vs. silicon) is the ship-gate.

See `PLAN.md` for milestones, acceptance criteria, and status.

## Dependencies (not tracked in this repo)

| Path                  | What                          | Pinned at                                        |
|-----------------------|-------------------------------|--------------------------------------------------|
| `rtl/ibex-orig/`      | lowRISC Ibex                  | `34b0705760ef3dfa00e99637432473d2be8f22f3`       |
| `riscv-compliance/`   | riscv-arch/riscv-compliance   | `844c6660ef3f0d9b96957991109dfd80cc4938e2` + local patches in `patches/` |

Fetch:

```bash
git clone git@github.com:lowRISC/ibex.git rtl/ibex-orig
cd rtl/ibex-orig && git checkout 34b0705760ef3dfa00e99637432473d2be8f22f3
git clone git@github.com:riscv-arch/riscv-compliance.git riscv-compliance
cd riscv-compliance && git checkout 844c6660ef3f0d9b96957991109dfd80cc4938e2
git apply ../patches/riscv-compliance-844c6660.local-patches.diff
```

Toolchain (riscv32-unknown-elf GCC, Verilator, FuseSoC, srecord): see
`env.sh`.

## Simulation entry points

```bash
source env.sh
bash sim/run_smoke.sh     # M1a: single-core boot smoke -> "PA M1 BOOT"
bash sim/run_cluster.sh   # M1b: 2-hart cluster + AXI4-Lite self-test -> PASS
```

## Repo hygiene

Commit after every little milestone: `bash git_ship.sh "message"`
(adds all tracked changes, commits, pushes).
