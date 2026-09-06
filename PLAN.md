# PocketAI-T — RISC-V + GEMM Transformer Inference on PYNQ Z1 → Sky130 ASIC

## Mission
Design a fabric-resident AI inference SoC (2× RISC-V cores + int8 GEMM unit +
special-function unit) on the PYNQ Z1 (Zynq-7020: 53,200 LUT, 106,400 FF,
630 KiB BRAM, 220 DSP48; M1/M2 qualified at 95 MHz, 100 MHz stretch).
Run GPT-2 124M (W8A8 GEMM arithmetic, int16 activation storage) with weight-streaming from DDR3.
Then port the *identical* RTL to Sky130 via
OpenLane and deliver a **PPA report** (fabric vs silicon: area, timing,
power, bandwidth) as a first-class deliverable.

## Architecture (target state)

```
 DDR3 ◄─ A9 ─┬─ AXI Stream (weight tiles) ─► ┌──────────────┐
              │                               │  GEMM 16×16  │ int8×int8→wide
              │  AXI slave (control/UART)     │  SFPU        │ (softmax, GELU,
              └─────────────────────────────► │  LayerNorm   │  scale/convert)
              │                               │  KV r/w port  │
              │                               └──────┬───────┘
              │        scratchpad ◄──── simple bus ─┤
              │        (activations,   ┌─────┬─────┴─────┐
              │         KV cache)      │Core0│  Core1     │
              │                        │Ibex │  Ibex      │  RV32IMC, in-order
              │                        └─────┴───────────┘
              └─ tokens/UART out
```

Design rules (non-negotiable):

- No Zynq DSP48 in datapath RTL → soft multipliers only (ASIC portability).
- int8 GEMM operands / int16 stored activations, with widened integer
  accumulators and explicit conversion interfaces defined in `docs/NUMERICS.md`.
  M2's legacy saturated-int16 interface remains supported; M3 must preserve wide
  results until scaling and bias are applied. No FP anywhere in fabric logic.
- Cores own control flow; units are descriptor-driven (ptr, M, N, K, flags).
- Every unit has a Python reference in `ref/` and a tile-level test vector.

## Repository layout
```
pocketai/
  PLAN.md
  rtl/            # all Verilog (fabric-only, no Zynq primitives)
  ref/            # Python golden models (numpy/torch), shared by sim+board
  sim/            # Verilator testbenches, C smoke tests
  zynq/           # PYNQ overlay .xsa/.bof, Python board code
  asic/           # OpenLane configs, reports, PPA artifacts
  docs/           # PPA_REPORT.md, notes
  tests/          # unit test vectors (hex/csv)
```

## Repo
Remote: `https://github.com/JesseLevine727/pocketai` (branch `main`). Make scoped
local milestone commits; push only when explicitly requested. Do not sweep up
unrelated work with `git_ship.sh`. Untracked (see README): `rtl/ibex-orig/`
(pinned `34b070576`), `rtl/ibex/` (CVE2 fork, ignore), `riscv-compliance/`
(pinned `844c666` + local patches in `patches/`), `build/`, and user-owned `NA/`.

## Milestones
Format: Deliverable / Verification (PASS = concrete evidence) / Risks / Agent plan.
Each milestone ends with a `reviewer` PASS against the written criteria before the next starts.

### M1 — Cluster on fabric: bus + Ibex + scratchpad  [~1 wk]
**Status (2026-09-04): M1 COMPLETE — PASS.** Local simulation/lint, the pinned
ISA suites, two clean 95 MHz implementations, and two physical-board runs have
passed. The final routed result is +0.330 ns setup WNS, 0.000 ns setup TNS,
+0.076 ns hold WNS, zero DSP48 primitives, zero DRC errors, and one explicitly
reviewed SmartConnect no-load warning. The exact final overlay passed the
10,000-round acceptance workload over SSH. See `docs/M1_VERIFICATION.md` for
the commands, qualified configuration, hashes, reports, memory map, result ABI,
and reviewed tool warnings. The preferred +0.500 ns margin and 100 MHz remain
stretch targets, not M1 claims.

Delivered:
- Two fabric-resident lowRISC Ibex harts in one pinned RV32IMC configuration:
  iterative M, FPGA register file, writeback stage, two-cycle branches, no cache,
  predictor, PMP, secure mode, floating point, or DSP48 multiplication.
- A five-host, round-robin 32-bit shared bus for A9 AXI, both instruction ports,
  and both data ports. It supports legal back-to-back requests without starvation
  or duplicated transfers.
- One shared 64 KiB BRAM-inferred scratchpad, a synthesizable console FIFO, and
  two one-word mailboxes with sticky level interrupts and explicit W1C acknowledge.
- An AXI4-Lite control/data window at `0x43c00000` plus an AXI GPIO core reset at
  `0x43c20000`. System reset leaves the scratchpad and A9 path available while
  core reset is asserted, so the board host can load firmware safely.
- Bare-metal shared-image firmware that boots both harts, exercises integer and
  stack memory, and completes exactly 10,000 interrupt-driven request/response
  rounds with sequence and checksum validation.
- A Vivado 2025.1 PYNQ-Z1 overlay build and an SSH board runner. JTAG is not part
  of the M1 workflow.

Acceptance gates:
- `PA_CLEAN=1 bash sim/run_m1.sh` → `M1 LOCAL PASS`, including focused mailbox,
  back-to-back bus, single-core boot, dual-hart/AXI, and fatal-warning RTL lint.
- `PA_CLEAN=1 bash scripts/run_compliance.sh` → RV32IMC 25/25, RV32IM 8/8, RV32I 44/48
  plus the four explicit upstream expected failures, Zicsr 6/6, Zifencei 1/1.
- `PA_CLEAN=1 bash zynq/build_m1.sh` → reproducible routed 95 MHz PYNQ-Z1
  bitstream with at least +0.250 ns setup slack, zero setup TNS, positive hold
  slack, zero DSP48 primitives, zero DRC errors, and no unreviewed DRC warnings.
  The recorded result is +0.330/0.000/+0.076 ns. 100 MHz is retained as a
  stretch target rather than an M1 blocker.
- `bash zynq/run_m1_board.sh` → both readiness lines, exact counts/checksums,
  zero firmware error words, and `M1 BOARD PASS` on the physical PYNQ-Z1 over SSH.

Closed design decisions:
- The external source trees are revision-pinned and their required local changes
  are tracked as patches. `scripts/check_deps.sh` rejects missing, stale, or
  partially applied dependencies.
- The bus has one transaction per host outstanding and a registered issue path.
  This is the M1 protocol contract; M2 must add accelerator traffic without
  weakening fairness or changing the existing host-visible ABI.
- The "UART" acceptance stream is deliberately a small AXI-readable console FIFO,
  so simulation and the A9 observe the same synthesizable hardware interface.

### M2 — GEMM unit + weight streaming  [~1 wk]

**Status (2026-09-04): M2 COMPLETE — PASS.** Local numerical/protocol tests,
M1 regression and ISA checks, two clean 95 MHz implementations, and the exact
overlay's physical-board workload have passed. Final setup WNS is
+0.499/+0.486 ns, with zero TNS, +0.018 ns hold slack, full routing, zero DSP48s,
zero DRC errors, and reviewed warnings. `docs/M2_VERIFICATION.md` records the
acceptance review, source/artifact hashes, reports, board log, and limitations.

Delivered:

- `rtl/gemm/`: logical 16x16 signed-int8 GEMM, K=1..768, implemented as a
  4x16 physical soft-MAC array. Signed 25-bit accumulation preserves the full
  dot product before deterministic saturation to int16.
- Two ordered descriptor/tile slots with independent A/B/C storage, arbitrary
  ready/valid stalls, partial dimensions, tagged completion/cycle/MAC counters,
  IRQ control, full-width descriptor validation, and reset/error/abort recovery.
- Portable accelerator RTL and a PYNQ integration using A9 GP0 control plus
  AXI DMA through HP0 to DDR3. DMA returns results to DDR; the A9 publishes them
  into shared scratchpad `0x43c04000..0x43c09fff` with exact readback.
- `ref/gemm_ref.py`, deterministic vectors, five reference unit tests,
  standalone Verilator tests, and GEMM activity while both simulated harts run.
- `zynq/m2_run.py` and `zynq/run_m2_board.sh`: SSH-only programming and a
  16x768x768 projection through 48 descriptors in 24 double-buffered pairs.

Acceptance evidence:

- `PA_CLEAN=1 bash sim/run_m2.sh` → 1000 randomized + 7 directed exact NumPy
  comparisons, protocol/lifecycle tests, active two-hart integration, and
  `M2 LOCAL PASS` including the complete M1 local suite.
- `PA_CLEAN=1 bash scripts/run_compliance.sh` → 84 passing tests and the same
  four named upstream expected failures as M1.
- `PA_CLEAN=1 bash zynq/build_m2.sh` → two independently clean implementations
  (`build/m2_qual1`, `build/m2_qual2`) exceeding the +0.250 ns hard setup gate.
  Both have positive hold slack and zero unconstrained endpoints.
- `bash zynq/run_m2_board.sh` with `M2_VIVADO_BUILD_DIR` set to the qualified
  second build → M1's 10000-round workload and `M2 BOARD PASS`; all 12288 int16
  results and 6144 shared words match exactly.
- Board counters: 154752 compute/pack cycles for 9437184 MACs, yielding
  5.793 GMAC/s at 95 MHz. Observed packed A/B input throughput is 29.821 MB/s;
  end-to-end workload latency is 110.649 ms (0.085 GMAC/s), including DMA,
  validation, and shared-memory publication.

Closed design decisions and limits:

- The 16x16 logical tile contract is preserved by a 4x16 physical array.
  The original 256-lane / approximately 25 GMAC/s estimate was not achieved;
  the implemented tradeoff retains FPGA space and repeatable timing margin.
- Input streaming, widened accumulation, saturation, padding, and descriptor
  ABI are defined in `docs/NUMERICS.md` and `docs/M2_ARCHITECTURE.md`.
- The board projection is A9-driven with harts held in reset; M1 runs separately
  on the identical overlay, and concurrent core/GEMM activity passes simulation.
- Measured payload throughput is not isolated DDR peak or GPT-2 tokens/s.
  No full-model inference, application speedup, or power claim is made.
- +0.500 ns margin and 100 MHz remain stretch targets. M3 must close its own
  implementation timing; M2 closure does not qualify future additions.

### M3 — GPT-2 SFPU, numerical interfaces, and measured dataflow

**Status (2026-09-05): COMPLETE — qualified at 95 MHz on PYNQ-Z1.**

The comprehensive staged goal and acceptance checklist are in
[`docs/M3_PLAN.md`](docs/M3_PLAN.md). Its ordered gates are:

1. Measure the exact qualified M2 overlay fairly: single-row and multi-row
   workloads, repeated timing without validation in the timed region, explicit
   residency/transfer boundaries, phase profiling, and a matching CPU baseline.
   Measure justified host/dataflow improvements before claiming speedup.
2. Pin GPT-2-small reference semantics; freeze numerical formats, quantitative
   error budgets, and ABI before arithmetic RTL changes. Resolve int16 storage
   versus int8 GEMM inputs and K=3072 MLP reduction without early saturation.
3. Implement stable masked softmax, LayerNorm with learned affine parameters,
   GPT-2's tanh GELU, and necessary scale/conversion/vector support. GPT-2 uses
   learned position embeddings: RMSNorm, SiLU, and RoPE are not M3 operations.
4. Pass bit-exact and high-precision numerical tests, protocol/lifecycle and
   integrated-chain tests, and all M1/M2 local and ISA regressions.
5. Pass two independent clean 95 MHz full-design builds (WNS >= +0.250 ns,
   TNS=0, positive hold, fully routed/constrained, DSP=0, clean DRC, all warnings
   reviewed), then physical SSH qualification of the exact accepted overlay.
6. Complete `docs/M3_VERIFICATION.md` with hashes, reproducible commands,
   operator/integrated measurements and limitations; scoped local commit.

All required gates passed; see [`docs/M3_VERIFICATION.md`](docs/M3_VERIFICATION.md)
and [`docs/M3_PERFORMANCE.md`](docs/M3_PERFORMANCE.md). Clean builds qual3/qual5
close at +0.483/+0.400 ns setup, +0.018/+0.016 ns hold, zero TNS, zero DSPs,
fully routed/constrained with reviewed warnings. The exact qual3 bit passes
physical M1/M2/M3/M1, 1007 mixed GEMM cases, 3472 SFPU cases, and repeated
actual-result MLP/attention chains. The frozen v1 numerics/ABI and all M1/M2
regressions remain intact. The fair M2 baseline, matching CPU comparison,
measured host improvements and all timing boundaries are recorded honestly.

+0.500 ns and 100 MHz are stretch only. No M4/M5 implementation, autonomous
KV management, full-model throughput, token-rate claim, or remote push in M3.

### M4 — Hybrid GPT-2 124M offload  [~1.5 wk]

**Status (2026-09-06 UTC): CLOSED — all M4 physical, quality, performance and evidence gates PASS.**
The comprehensive acceptance contract is [`docs/M4_PLAN.md`](docs/M4_PLAN.md).
It adds explicit floating-model quality gates, full-model/cache/tensor checks,
bounded board memory and repeated fair CPU comparisons to the sketch below.
The qualified baseline is 95 MHz; CPU-relative performance is measured, and
positive speedup is not required or presumed.
The pinned floating reference and scaled W8A8 candidate pass: held-out perplexity
ratio 1.01634, top-1 agreement 89.37%, no unintended clipping, and exact cached
versus recomputed generation. The rejected direct fixed-Q8 diagnostic is retained.
A compact model pack and range-safe v3 revision pass, including 1024-token
cache/range checks and native A9 operator tests. The bounded A9 offload runtime
is implemented: physical CPU/FPGA 3×20 generation, all tensor/logit/KV cases
and M1/M2/M3/M1 compatibility pass. Repeated resident performance is now exact
and audited: FPGA takes 433.008 s versus CPU 113.483 s for prefill plus 20 tokens
(0.04619 vs 0.17624 tokens/s), a 3.816x FPGA slowdown. Physical CPU and FPGA
1024-context/cache/overflow checks pass with zero process swap. Peak RSS is
219,244/261,840 KiB respectively. Supplemental process-cold observations also
pass; all eleven machine checks and the manual G0–G7 closure review pass.
The closure commit is local only; M5/M6 remain unstarted. See `docs/M4_VERIFICATION.md`,
`docs/M4_RUNTIME.md` and the full results/frozen sampling in `docs/SPEEDUP.md`.

Deliverables:
- GPT-2 124M loaded on A9 using the quantization and pinned reference established
  in M3. Int8 GEMM inputs imply W8A8 arithmetic even if activations are stored
  as int16; do not label this weight-only W8A16.
- `zynq/m4_offload.py`: A9 dispatches linear→GEMM and softmax/LayerNorm/GELU→SFPU;
  embedding lookup (including learned positions) and other glue stay on A9.
- Generate 20 tokens from a fixed prompt; verify greedy decoding against a
  pinned CPU implementation of the same quantized numerical contract.

Verification: PASS = 20 new tokens on each of 3 frozen prompts matching the
quantized CPU reference, separate frozen floating-model quality gates, full
physical/regression evidence, and repeated per-op/integrated performance
comparisons (including slowdowns) in `docs/SPEEDUP.md`; see the full M4 plan.

Risks: glue overhead dominating at 95 MHz, accumulated quantization error,
full-vocabulary projection and DDR/CMA capacity. Instrument early. RTL bugs
require a dedicated fix/regression/requalification cycle, not unreviewed edits.

### M5 — Autonomous decode on the RISC-V cores  [~2 wk]

**Status (2026-09-06 UTC): IN PROGRESS / NOT QUALIFIED.** The user authorized M5
and explicitly made **>=1 token/s a stretch target**, not a hard closure gate.
The complete contract and test-cost policy are in [`docs/M5_PLAN.md`](docs/M5_PLAN.md).

Deliverables:

- Bare-metal two-hart runtime owns the complete model loop, metadata/scales,
  descriptors/transfers/IRQs, DDR KV and greedy selection; explicit hart roles.
- Preserve M4's actual adaptive-v3 GPT-2, W8A8/int16 numerical contract, full
  heads/vocabulary and **1024-position context**. The former int8/200-token
  scratchpad-ring sketch is superseded; full model/KV live in safely owned DDR.
- A9 may provision firmware/model/memory and submit/receive token IDs, but
  performs no in-run tensor processing, transfer service or operator scheduling.
- Autonomous board harness, exact model/ownership/lifecycle qualification,
  one clean timing-qualified overlay and honest real performance. The lean
  implementation uses 91 MHz, WNS >= +0.250 ns; the accepted artifact has
  +0.433 ns WNS, zero TNS, positive hold and no DSPs.

Verification follows the user's lean side-project policy: all three original
prompts, with at least five exact generated tokens for one and one for each
other prompt, final full-logit/KV hashes, selected intermediate traces and
affected regressions. Bounded 1024-limit/overflow checks remain required; the
new empty-cache 1024-position marathon and duplicate build are optional.
Reuse unchanged M4 CPU/FPGA endurance evidence. Keep one decode warmup plus
three measured samples and record the precise timing boundaries.
Measured speedup and >=1 token/s are not prerequisites for correctness closure.

Risks: safe DDR provisioning outside the 128-MiB CMA limit, variable-latency
memory, ownership/recovery, faithful metadata arithmetic on RV32IMC, code/buffer
capacity and timing. Boot/kernel/global board changes need approval before use.
No unrequested agents, no automatic push, and no M6 work in this goal.

### M6 — Sky130 port + PPA REPORT (headline deliverable, not a bonus)  [~1.5 wk + MPW wait]
Deliverables:
- OpenLane config: Ibex cores (published case study as sanity anchor), GEMM, SFPU, RAMs → sky130 SRAM macros.
- Chip top: UART pads, weight-in interface (SPI/QDR or preloaded micro-weights for on-chip demo).
- `docs/PPA_REPORT.md` — the flagship artifact:

| Metric | Zynq fabric (measured) | Sky130 (P&R) |
|---|---|---|
| area (K-LUT → mm²) | from .xsa | OpenLane report |
| max fmax, achieved @100 MHz timing util | measured | report |
| GEMM GMAC/s (sim-timed) | board-measured | sim-timed |
| power (DC estimate vs board watt) | A9+fabric P meas | OpenROAD power |
| bandwidth to weights | DDR3-measured | interface spec |

Plus: per-block table, screenshots, methodology section (reproducible commands).
- MPW submission decision gate at end of M6 (cost ~$200-500/person) — only after PPA table is real.

Verification: P&R converges (no DRC errors), timing met at 100 MHz, PPA table filled with *measured or simulated* numbers only — no estimates.
Agents: implementer (one OpenLane run), reviewer (checks report has evidence for every cell).

## PPA Report = ship gate
The project is "done" only when `docs/PPA_REPORT.md` exists, every number traces
to a command in the report, and `reviewer` PASSes on that evidence.

## Standing rules
- Every milestone: written acceptance criteria above *before* first RTL edit.
- No file touched by two subagents concurrently; parallel work only on disjoint paths.
- Numerical formats (int8/int16 fixed-point, saturation, LUT error bounds) live in `docs/NUMERICS.md` and are the contract between RTL and `ref/`.
- Fabric RTL purity check (no DSP/Zynq-specific primitives) is a reviewer checklist item at every milestone.
