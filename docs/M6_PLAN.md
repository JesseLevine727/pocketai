# M6 — Sky130 port and evidence-led PPA report

Status: **ACTIVE; not qualified.** Baseline `7405919` was pushed to
`origin/main` on 2026-09-08 before this work began. M1–M5 and every subsequent
FPGA performance qualification remain frozen. This document records the M6
acceptance details before any ASIC RTL changes; it does not claim a port exists.

## Scope and explicit decisions

Preserve the qualified full portable system: both fast-multiply Ibex harts,
GEMM with wide results and K=3072 support, SFPU, autonomous transfer/memory
control, 64-KiB scratchpad and both coherent 64-KiB read mirrors. Preserve all
numerical formats, memory capacities, byte-write/coherence behavior, ownership
and abort/drain contracts. The Zynq processing system, its DDR PHY/controller,
SmartConnect and FPGA clock/pad primitives are platform infrastructure, not
portable RTL. Their replacement/external boundary must be explicit in the
report. The 266,289,152-byte external arena is not on-chip SRAM.

The original plan permits SPI or an on-chip micro-weight demonstration as the
chip loading interface. A reduced demonstration must not replace full-system
PPA or be reported as full GPT-2 inference. A logic-block implementation is an
intermediate gate, not chip closure. Do not book or pay for MPW fabrication.

The user explicitly deferred **measured physical-board watts** on 2026-09-08:
the PYNQ-Z1 has no accessible power/current sensor and no external meter is
available to this workflow. Mark that measurement deferred, never zero and
never replace it with nominal supply ratings. Any tool power analysis must
state its activity source, corner, voltage, frequency, scope and coverage.

## Ordered gates

1. **Baseline and feasibility.** Preserve/push the baseline; verify the frozen
   audit; inventory exact portable sources, memories, interfaces and platform
   exclusions. Pin tools/PDK/macros and check their actual views, timing and
   power coverage. Check disk before downloads and substantial physical runs.
2. **Port correctness.** Use new `asic/m6/`, `scripts/m6_*`, `tests/m6/` and
   `build/m6_*` paths only. Map memories to real Sky130 macros with matching
   port, mask and latency behavior; make any adapter changes explicit and test
   them against the qualified memories. No missing/black-box memory may make
   area or timing appear artificially favorable. Preserve fast multipliers.
3. **Implementation.** Run bounded synthesis/floorplan feasibility before full
   placement/routing. The original ASIC target remains **100 MHz**. Declare
   clock/I/O constraints and library/RC/PVT corners; verify setup, hold,
   unconstrained paths and macro boundary timing. Do not present typical-corner
   analysis as worst-corner or tapeout signoff. Timing failure is not a pass.
4. **Physical and interface checks.** Require routed convergence, zero reported
   routing/DRC errors and explicit LVS/antenna/pad/power-grid status. Exercise
   the actual chip loader and output interface with a finite known-answer
   workload. Do not infer full-chip correctness from a single MAC test.
5. **PPA report.** Produce `docs/PPA_REPORT.md` with traceable per-block and
   complete-scope area, timing, compute throughput, power analysis and weight
   interface bandwidth. Distinguish physical measurements, physical-design
   tool results, RTL simulation, analytic bounds, historical results and
   unavailable data. LUTs are not converted to mm². Do not scale FPGA token/s
   by an ASIC clock and call it measured ASIC inference.
6. **Review and release.** Audit each reported cell against a reproducible
   command and primary artifacts. Check prior frozen audits, review the actual
   diff and commit scoped changes. Push qualified M6 results as requested.
   Record the MPW decision as no submission in this workflow; costs or a
   fabrication-ready claim need separate evidence and authority.

## Bounded execution and stop conditions

Reuse the completed original-prompt/full-logit/KV and maximum-context FPGA
evidence. No new full-1024 physical prefill or endurance marathon is required.
Keep runs checkpointed, retain failed trials and avoid large parameter sweeps.
Do not remove old evidence or user files to make disk space. Tool installation
is local to M6 or an isolated container, without system upgrades or broad
container mounts. No agents are requested for this goal; perform a separate
evidence review locally without claiming independent human review.

Report only major completed gates or material blockers. If missing macro
views, storage, timing, chip integration or another requirement needs a material
scope/acceptance change, preserve the evidence and request direction. A useful
partial report is not M6 closure. The goal stays incomplete until the agreed
gates pass.

## Preflight decision checkpoint

The baseline push/audit, full RTL elaboration and single-SRAM extracted timing
checks completed. The SRAM probe reports zero detailed-routing and public
KLayout DRC violations with SRAM exclusions disabled. However, Magic rejects
SRAM GDS layers and a separate public KLayout LVS run does not match the
supplied SRAM schematic. The public extractor lacks the special SRAM device
models in that schematic; internal SRAM verification is not qualified.

No signoff switch was disabled to hide these results, and no SRAM internals
have been black-boxed for a claimed LVS pass. Before selecting this memory for
the full-system port on a third-party-IP basis, ask whether its internal
verification may be explicitly deferred for a research PPA release. That scope
would still require full-system functionality, macro-boundary timing, our
logic/routing/power connectivity checks and truthful PPA, and would not mean
fabrication-ready. The user has deferred only measured board watts so far.
The [preliminary report](PPA_REPORT.md) is not M6 closure.
