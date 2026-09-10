# M6 closure goal: finish all three remaining gates

Approved by the user on 2026-09-08 after checkpoint `d328dd8`.
Status: **active goal; all three closure gates remain unfinished**.

The user explicitly requested a goal to complete and fix all three remaining
points: representative-memory electrical/antenna failures, full-system ASIC
implementation, and physical-interface integration plus final PPA/reporting.
This is an outcome goal, not another goal merely to run a bounded experiment
or publish a progress checkpoint.

## Fixed acceptance and preserved scope

- Implement the actual complete dual-RV32MFast-Ibex/GEMM/SFPU system at
  **95 MHz**. Approximately **+0.244 ns setup headroom is accepted**;
  +0.250 ns is preferred, not an exact cutoff, and +0.500 ns is stretch.
  Do not spend a separate optimization pass chasing the last 6 ps.
- Preserve the numerical formats, logical memory capacities, coherent mirrors,
  scratchpad, both fast multipliers, autonomous control, ordering and abort/drain
  behavior. A toy workload or an eight-SRAM probe cannot replace the full ASIC.
- Require positive hold, zero setup/hold negative totals, legal clock period
  and pulse width, electrical-domain and constraint coverage, and passing
  in-scope DRC, antenna and connectivity checks at all declared PVT/RC corners.
  A reported positive slack is insufficient when its electrical conditions
  are outside the characterized domain.
- Preserve the frozen FPGA release `7405919`, all M1–M5/startup evidence,
  retained failed/completed M6 artifacts and unrelated `NA/`. Keep original
  SRAM views immutable; derived views need explicit provenance and validation.
- Retain the approved research-only deferrals for measured board watts,
  SRAM-internal verification and unavailable leakage data. These are disclosed
  omissions, not passes or zero-valued measurements. Macro-boundary checks,
  our logic/routing and power connectivity remain required.
- No fabricated-silicon measurement or paid fabrication is required for this
  research implementation goal. No purchases, MPW submission, public issues
  or messages, agents, credential storage, broad cleanup or unrelated changes.

## Gate 1 — Qualify the representative memory implementation

Starting evidence: the matched 95-MHz probe reports +0.244183 ns setup,
+0.052682 ns hold and zero negative totals, but also 3,405 slew violations,
57 capacitance violations and 26 antenna-violating nets. It is unqualified.
The subsequent local-input-buffer candidate also fails and is not promoted.

Work:

1. Use the retained all-corner STA, per-pin slew/load reports and exact source
   snapshots as the reproducible failure signal. Separate true boundary
   violations, optimization-corner coverage and flow-stage omissions.
2. Close local clock/command distribution, fanout and read-return routing within
   the SRAM's characterized input domain and reviewed output-load contract.
   Test ranked, falsifiable hypotheses with controlled finite comparisons;
   avoid a broad parameter sweep or arbitrary library/SDC relaxation.
3. Repair hold with all-corner checks, run antenna repair in the complete flow,
   and re-extract parasitics after every physical change. Never combine the
   best timing from one route with electrical results from another route.
4. Recheck byte masks, collisions/ownership, bank edges, holds and reset
   retention. If an ASIC-only latency/handshake change is needed, requalify the
   affected consumers and full dual-hart oracle and quantify the cycle/stall
   cost. Do not describe changed latency as cycle-equivalent.

Exit: one retained, reproducible representative implementation meets the
accepted 95-MHz timing margin and all applicable functional, electrical,
antenna, physical-verification and coverage gates. A successful script exit or
an evidence checker accurately recording failures does not meet this exit.

## Gate 2 — Qualify the complete ASIC

Starting evidence: the complete single-clock architecture passes RTL/consumer
and digital-loader tests. Historical synthesis and macro-placement/PDN results
do not qualify the new single-clock physical implementation. The retained
mapping has 47 logical arrays and 292 SRAM macros.

Work:

1. Integrate the qualified memory solution into the actual portable system;
   retain complete memory capacity and both harts/accelerators. Re-inventory
   and explain any legitimate mapping changes rather than silently dropping
   memories or replacing bulk SRAM with unreported registers.
2. Stage a fresh reproducible build with consumer-local placement, a complete
   clock/reset strategy and explicit physical constraints. Complete standard-
   cell placement, CTS, routing and parasitic extraction for the full system.
3. Close full-system setup/hold and electrical timing at every declared corner.
   Check all generated/gated clocks, reset paths, minimum periods/pulse widths,
   unconstrained paths, justified exceptions, power connectivity and the agreed
   physical-verification scope. Macro-internal deferral does not waive our
   integration checks.
4. Re-run finite numerical, backpressure, abort/restart and dual-hart tests
   against any changed implementation. Measure useful cycle counts and memory
   stalls instead of extrapolating token throughput from clock frequency.

Exit: the complete system, not only a representative cluster or selected
blocks, has a reproducible routed implementation that passes the declared
95-MHz and research-scope qualification gates.

## Gate 3 — Finish interfaces, PPA, figures and release

Work:

1. Integrate and constrain the real SPI loader, UART, clock/reset and Sky130
   I/O boundary. Finish the documented external-memory interface with a
   concrete external-controller endpoint and defensible signal/timing/loading
   assumptions. Native AXI is not itself a DDR controller/PHY; SPI flash is not
   a substitute for the full writable external arena. Identify any missing
   endpoint, package or IP resource explicitly before relying on it.
2. Exercise the integrated interface and full compute system with finite known-
   answer workloads, malformed frames, backpressure and safe abort/drain/reset.
   Separate simulations and timing analysis from physical-link measurements.
   A firmware-only loader smoke test is not full-model inference evidence.
3. Finish `docs/PPA_REPORT.md`: source-traceable full/per-block area and timing,
   useful compute throughput, interface bandwidth and the available activity-
   qualified power components. Record workload, clock, voltage/corner and
   coverage. Keep unavailable leakage/total power unavailable; do not invent
   ASIC token/s, measured watts or energy/token.
4. Retain the actual qualified-release Vivado block-design export. Add the
   actual final routed ASIC figure and update editable native TikZ architecture
   and platform-boundary figures to the qualified implementation. Preserve
   historical preliminary images and label their stages. Render and inspect
   final figures at report size; bind outputs to their source databases.
5. Audit the report against primary artifacts, refresh all affected evidence
   ledgers, run regressions and the frozen FPGA audit, review the scoped diff,
   commit and push the completed results. Ensure the remote commit matches.

Exit: the integrated research ASIC, verified interfaces, qualified results,
final report/figures and reproducible evidence package are complete and pushed.
The disclosure of approved deferrals remains visible in the final report.

## Execution and completion rules

Use bounded experiments, finite timeouts and checkpointed physical stages.
Reuse the qualified FPGA full-model evidence; no new hours-long 1024-token
prefill/endurance campaign is required. Do not rerun passing frozen workloads
without a relevant source or acceptance change. Check disk/resource guards
before substantial runs; preserve failed artifacts for comparison.

Proceed through all three gates. A commit, a completed trial, passing unit
tests or a truthful preliminary report is progress, not completion. Only mark
the goal complete once all three exits are met. If an external resource,
material interface choice, cost or scope change is genuinely required, exhaust
safe in-scope checks, state the exact dependency and request that input. Do not
turn a hard physical problem into a waiver or claim impossibility from a few
failed trials. Report major completed gates or material problems.

## Goal-service state

The first renewed `create_goal` request was rejected because an unfinished
earlier M6 goal remained in `blocked` state. After the user requested a retry,
the goal service returned no existing goal and successfully created this
**active** three-gate closure goal. Its objective explicitly uses 95 MHz and
the accepted approximately +0.244-ns margin. The earlier goal was not falsely
marked complete to bypass the restriction. No further goal-activation action
is required.

References: [M6 acceptance](M6_PLAN.md), [memory contract and results](M6_SRAM_CONTRACT.md),
[chip-interface boundary](M6_CHIP_INTERFACE.md), [historical worklist](M6_100MHZ_CLOSURE.md).
