# M6 — Sky130 port and evidence-led PPA report

The renewed [three-gate closure goal](M6_CLOSURE_GOAL.md) is the current
execution contract: complete memory qualification, full ASIC implementation,
and interface/PPA/report/release work. Progress checkpoints are not its exit.

Status: **95-MHz ASIC target approved; single-clock RTL/loader passed; physical closure open.** Baseline `7405919` was pushed to
`origin/main` on 2026-09-08 before this work began. M1–M5 and every subsequent
FPGA performance qualification remain frozen. This document records the M6
acceptance details before the ASIC RTL changes. The current port passes RTL
functional, synthesis and macro-placement/power-grid connectivity checks;
routed timing and chip-level physical qualification remain open.

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

The user initially deferred the **100-MHz ASIC closure requirement** on
2026-09-08, then explicitly reinstated it by approving the memory-first roadmap
and asking to execute the goal. On the same date, after reviewing the routed
probe results, the user explicitly accepted **95 MHz as the required ASIC
system clock** ("ok 95MHz is fine"). This supersedes the 100-MHz requirement.
The user also explicitly accepted approximately +0.244 ns setup headroom:
+0.250 ns is preferred, not an exact hard cutoff; do not chase the final 6 ps.
This approval does not waive hold, electrical, antenna, DRC, functional or
chip-integration gates, or authorize further margin reductions. Preserve
all historical 100-MHz results with their original clock labels.
The earlier candidate was 12.5 MHz system / 25 MHz memory; it remains historical
and unqualified, not an alternative acceptance clock.
The previous direct-clock-as-phase revision failed its 25-MHz system candidate;
the revised separate-phase-data netlist has passed functional/synthesis/PDN
checks but has not yet completed standard-cell placement or routed timing.
The port must still close setup and hold timing
at 95 MHz, with macro-boundary and constraint coverage
checked. Report the achieved clock and corresponding performance honestly;
do not relabel a failed 100-MHz run as passing. The existing 100-MHz SRAM probe
result and qualified 91-MHz FPGA baseline remain unchanged.

In a subsequent explicit approval on 2026-09-08, the user deferred
**SRAM-internal verification and unavailable SRAM leakage-power data** for a
research-only M6 result. SRAM22 may therefore be integrated as third-party IP.
Retain the failed standalone LVS result and distinguish this acceptance
deferral from verification success. Missing leakage stays unavailable, not
zero; do not claim complete power or energy per token from partial data.
These decisions do not waive full-system functional checks, memory-interface
equivalence, macro-boundary timing, routing/DRC, or our power connectivity.
They do not authorize fabrication or a fabrication-ready claim.

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
3. **Implementation.** Prove a representative banked-memory subsystem first,
   then bounded synthesis/floorplan feasibility before full placement/routing.
   **95-MHz system closure is required.** Approximately +0.244 ns setup
   headroom is explicitly accepted; +0.250 ns is preferred, not a hard cutoff;
   +0.500 ns is a stretch, not a substitute for all setup/hold checks passing.
   Declare
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
   Include actual Vivado block-design and ASIC physical-implementation figures,
   plus editable native TikZ high-level architecture and platform-boundary
   figures. Retain export scripts, vector outputs and artifact provenance.
   Intermediate floorplans must be labeled as such, never presented as routed
   100-MHz results. Review readability and connections in rendered figures.
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

## Resumed 100-MHz execution contract

The detailed worklist is [M6_100MHZ_CLOSURE.md](M6_100MHZ_CLOSURE.md). The
2026-09-08 approval permits ASIC-only latency/handshake adaptations proposed in
that roadmap, provided architectural results, ordering, capacities, coherence,
fast multiplication and abort/drain behavior remain correct. Such adaptations
must not be described as cycle-equivalent; useful workload throughput and
memory-stall costs must be requalified. No arbitrary bank-conflict assumption,
hidden lower-frequency compute domain or omitted macro timing may qualify the
approved 95-MHz target. A changed SRAM choice needs matching characterized timing and
physical views. Missing suitable IP is a feasibility blocker, not a waiver.

The goal service initially rejected a replacement while the earlier M6 goal
remained unfinished and blocked. Following the user's retry request, that
entry was absent and the new [three-gate closure goal](M6_CLOSURE_GOAL.md) was
successfully created in active state. Its objective uses the current 95-MHz
acceptance. No unfinished objective was falsely marked complete.

The post-storage pass now also qualifies the 1x digital SPI-loader integration.
It confirms an output-transition contract inconsistency in all three screened
SRAM sizes/corners; the local-clock physical candidate is not promoted because
worst setup worsens despite improved clock slew. Full routing remains gated on
usable SRAM characterization and representative memory closure, not disk space.
See [M6_SRAM_ELECTRICAL.md](M6_SRAM_ELECTRICAL.md). No electrical waiver is added.

The subsequent user-approved bounded SRAM-contract pass derives an output-only
project integration view from the unchanged timing tables. This is not full
macro recharacterization or supplier approval. Its load/input-slew envelope
must also pass in the physical design; the routed candidates do not yet do so.
See [M6_SRAM_CONTRACT.md](M6_SRAM_CONTRACT.md). The current 95-MHz requirement
is authoritative even where historical script, ledger and roadmap filenames
still contain `100mhz`.

## Preflight decision checkpoint

The baseline push/audit, full RTL elaboration and single-SRAM extracted timing
checks completed. The SRAM probe reports zero detailed-routing and public
KLayout DRC violations with SRAM exclusions disabled. However, Magic rejects
SRAM GDS layers and a separate public KLayout LVS run does not match the
supplied SRAM schematic. The public extractor lacks the special SRAM device
models in that schematic; internal SRAM verification is not qualified.

The user has now approved the third-party-IP research scope described above.
Internal SRAM checks may be excluded from the integration LVS scope only if
that boundary is explicit; never report an SRAM-internal LVS pass. Preserve
original GDS manufacturing layers, use KLayout for stream-out/public DRC, and
keep the failed Magic experiment. Full-system functionality, macro-boundary
timing, our logic/routing/power connectivity checks and truthful PPA remain
required. Deferral does not fix the failed comparison or supply missing data.
The [preliminary report](PPA_REPORT.md) is not M6 closure.
