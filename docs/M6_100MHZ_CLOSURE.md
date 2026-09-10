# M6: full-system ASIC closure worklist

The user renewed the goal to finish all remaining work in
[M6_CLOSURE_GOAL.md](M6_CLOSURE_GOAL.md). That three-gate contract is current;
the dated experiments below remain historical evidence.

Approved by the user on 2026-09-08. Status: in progress, not timing-qualified.
Later that day the user explicitly accepted **95 MHz instead of 100 MHz**.
The filename and historical checkpoint clocks are retained for provenance.
The current target is 95 MHz. The user also accepted approximately +0.244 ns
setup headroom; +0.250 ns is preferred, not an exact hard cutoff. All other
checks remain, and further margin reductions are not automatically authorized.
This supersedes the earlier 100-MHz deferral, not the frozen FPGA release or
the explicit research-only SRAM-internal verification/power limitations.

## Objective

Implement the complete portable dual-RV32MFast-Ibex/GEMM/SFPU system in Sky130
at 95 MHz, verify useful functionality and throughput, complete the PPA report
with implementation and native TikZ figures, audit, commit and push the scoped
results. Preserve logical capacities, formats, coherent mirrors and autonomous
control. No fabrication, purchases, model simplification or unrelated edits.

## Ordered work and acceptance

1. **Baseline/resources:** preserve `7405919` and M6 checkpoint `082951b`; audit
   frozen evidence; provide enough durable storage before large physical runs.
   Initial free disk is approximately 7.1 GiB, below the 10-GiB physical-run
   guard. Prefer at least 30 GiB headroom. Do not delete retained evidence.
2. **Memory feasibility:** inspect the pinned Liberty periods, setup/hold,
   clock-to-output, transition/load limits and actual access requirements.
   The current 512x32 1RW macro needs about 5.516 ns minimum period at SS;
   the current 2x adapter requires 5 ns at a 100-MHz system clock. It cannot
   qualify unchanged. Compare a bounded smaller-macro/2x candidate with a
   100-MHz access-scheduled or suitable native independent-port alternative.
   Route a representative banked cluster including real periphery and clocks
   before scaling it to the full design. Test collisions, byte masks, holds,
   bank edges, reset retention and both read ports. Never infer timing from
   a behavioral memory model alone.
3. **Locality/block closure:** group memories with consumers, localize address
   fanout and bank return selection, pipeline only demonstrated critical paths.
   Preserve both fast multipliers and steady-state accelerator throughput where
   possible. Revalidate latency/handshake changes and quantify stall costs.
4. **Full implementation:** integrate proven clusters; place, CTS, route and
   extract parasitics; analyze all declared PVT/RC corners. Require setup/hold
   pass with zero negative totals, clock-period/pulse-width and electrical
   checks, constraint coverage and justified exceptions. Target +0.250 ns WNS;
   +0.500 ns is stretch. Resolve reset/gating, external-memory timing, loader,
   pads and power connectivity. Native AXI alone is not a complete physical
   DDR interface; a loader microtest is not full GPT-2 qualification.
5. **Bounded functional/performance qualification:** memory tests, real dual-
   hart firmware, GEMM/SFPU numerical oracles, backpressure and abort/restart;
   compare representative useful cycle counts with the frozen architecture.
   Reuse qualified FPGA full-model evidence; no new hours-long inference sweep.
6. **Report/release:** source-traceable full and per-block area/timing/throughput,
   explicit power coverage, tool/PDK/IP hashes, figures below, reproducible build,
   evidence audit and scoped commit/push. A passing probe is not M6 closure.

## Required figures

| Figure | Source | Required distinction |
|---|---|---|
| Vivado system block design | Actual qualified-release BD, exported by Vivado | Zynq PS/DDR shell versus portable inference core |
| ASIC physical implementation | Actual OpenROAD/KLayout database | Floorplan/placed/routed stage and exact run identity |
| High-level architecture | Native editable TikZ | Both harts, mirrors/scratchpad, GEMM, SFPU, transfer/control and external memory |
| FPGA/ASIC platform boundary | Native editable TikZ | Reused compute versus platform-specific clock/host/memory/pad integration |

Retain native sources and vector PDF/SVG exports, readable labels, consistent
colorblind-friendly styling, accurate arrows, captions and source hashes.
Render and visually inspect at report size. Tool screenshots/exports are real
implementation evidence; TikZ drawings are explanatory schematics. Neither
is a fabricated-silicon micrograph. A preliminary ASIC view must retain its
unqualified stage label until a qualified final view exists.

## Execution limits

Prefer one or two well-motivated candidates per decision, checkpointed physical
stages and finite timeouts over large sweeps. Report major gates or material
blockers. If SRAM/IP, storage or physical-interface resources prevent closure,
retain evidence and request the missing resource; never reduce acceptance or
claim full-system PASS. The goal remains unfinished until all gates pass.

## First bounded execution checkpoint

- Frozen FPGA audit: passed again; no FPGA source or firmware changes.
- Single-clock binary-selector candidate: local storage and full dual-hart
  oracle passed, including runtime assertions in four consumer module types.
  Both runs retained the exact 16,477,049-cycle baseline.
- Representative 8-macro P&R: three completed trials. Best worst setup is
  −0.282133 ns at 100 MHz; worst hold is +0.052682 ns. Setup, electrical and
  antenna checks remain open. The one-hot-return experiment did not improve
  worst setup and is not promoted.
- Figure package: native editable TikZ architecture and platform boundaries,
  actual read-only Vivado BD export, actual OpenROAD macro-floorplan view and
  labeled vector geometry are included in the preliminary report. The final
  routed ASIC figure still requires the final implementation.
- Full-chip runs: not launched below the unchanged 10-GiB guard. Approximately
  3 GiB remains (below that level at the final audit); request enough durable
  space, preferably 30 GiB free. No
  original artifacts or unrelated files were deleted.

Details: [single-clock contract/results](M6_SINGLE_CLOCK_MEMORY.md),
[experiment ledger](m6_100mhz_evidence.json), [report](PPA_REPORT.md).
This checkpoint is not M6 closure and does not revive the 100-MHz deferral.

## Post-storage execution checkpoint

- **Storage gate cleared:** the user-authorized Ollama model removal recovered
  approximately 132 GiB. About 135 GiB was available at resumption, above both
  the full-core guard and recommended reserve. The low-space observations above
  describe the previous checkpoint. No retained M6 evidence was removed.
- **SRAM electrical screen completed:** every supplied corner of the 128-,
  256- and 512-word candidates has a 0.040-ns default output limit below every
  characterized output-transition sample. This is an IP-contract inconsistency,
  not proof that the physical memories cannot operate. No limit was changed.
- **Local-clock experiment completed, not promoted:** dedicated non-inverting
  pairs of clock inverters reduce the new critical macro's rising clock slew
  to 0.348873 ns. Worst setup nevertheless worsens to −0.386309 ns; worst hold
  is +0.004979 ns. Electrical and antenna violations remain. A first trial
  failed PG connectivity; explicit connections fix that error and the retained
  post-route topology/PG regression passes. The prior best setup remains
  −0.282133 ns. No full-system physical result is inferred.
- **Single-clock loader simulation passed:** direct 1x clock binding, unchanged
  188-byte firmware, SPI load/readback, both real fast-MUL Ibex results and both
  UART bytes pass. This is a digital SRAM-only integration test, not a pad,
  external-DRAM or full GPT-2 qualification.
- **Next gate:** resolve the SRAM timing contract through reviewed corrected
  characterization or suitable alternative IP, then close the representative
  clock/command/return network. Recharacterization is additional IP work, not
  permission to substitute an arbitrary output limit. Full-chip routing remains
  behind this gate even though storage is now sufficient.

See [electrical diagnosis and reproduction](M6_SRAM_ELECTRICAL.md) and the
[new primary extracts](evidence/m6_memory_resumed_v2/manifest.json). M6 remains
unfinished; the 100-MHz acceptance and frozen FPGA release are unchanged.

## Approved clock and library-contract revision

The user subsequently approved a bounded library-correction pass and accepted
95 MHz as the ASIC system target. The statements above describe earlier
checkpoints, not the current clock requirement. New constraints are separate
from the unchanged 100-MHz SDC. Approximately +0.244-ns setup headroom is
explicitly acceptable; +0.250 ns is preferred and +0.500 ns is stretch. Positive
hold, electrical/domain, antenna, DRC and full-system gates remain.

The correction changes only the 32 output-pin metadata entries per library,
restricting load to 7–13 fF and transition to 350 ps. Input constraints and every
timing/power table remain unchanged. All three corners support that restricted
table domain, but the routed implementation still violates its input/load
conditions. The isolated output-inverter SPICE check is not full SRAM
recharacterization. No repaired physical candidate is promoted.

See [contract, trials and remaining work](M6_SRAM_CONTRACT.md). Memory-local
command distribution, clock/return timing and antenna repair remain the next
physical gate; lowering frequency is not a substitute for these checks.
