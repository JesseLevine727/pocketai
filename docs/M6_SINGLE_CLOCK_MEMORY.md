# M6 single-clock memory experiment

Status: full-system RTL and consumer-assertion tests pass; 100-MHz physical
qualification remains open. FPGA release `7405919` and the historical two-phase
adapter are unchanged. Evidence: [m6_100mhz_evidence.json](m6_100mhz_evidence.json).

## Why change the memory schedule?

The 512 × 32 SRAM22 macro has one read-or-write port. The historical adapter
preserves arbitrary logical read/write overlap by clocking SRAM at twice the
system rate. At a 100-MHz system clock, its 5-ns memory period is shorter than
the slow-corner Liberty minimum-period table maximum of 5.51622 ns. The
256- and 128-word alternatives leave only 0.03207 and 0.15141 ns, respectively,
in that **period-only** screen. These differences exclude path delay, skew,
setup/hold and electrical checks; none is a physical pass.

The new candidate uses the system clock for SRAM and gives writes priority.
Both physical read copies receive every byte-masked write. A read is accepted
only when no write is active. Bank selection updates on accepted reads and
holds otherwise. SRAM contents survive reset; output validity must be
re-established with an accepted read after reset. Capacities and formats stay
unchanged: 47 logical arrays, 292 macros and 584 KiB of physical storage.

**This is not a general cycle-equivalent replacement for a 1W2R RAM.** A client
that consumes a simultaneous read and write must not use it unchanged. The
refinement depends on the actual PocketAI consumers below.

## Consumer-access contract

| Consumer | Why a write-cycle read is not needed | Check |
|---|---|---|
| GEMM tile buffers | Loading writes the inactive slot; issued computation reads the active slot | Runtime active-slot exclusion assertion |
| SFPU vector buffers | Load and compute phases are separate; operand/output reads occur outside buffer-write phases | Runtime operand/output issue assertions and state-machine review |
| Instruction mirror | Mirror writes suppress actual and predicted read requests | Runtime request exclusion assertion |
| Data mirror | Mirror writes suppress data-read grants | Runtime grant exclusion assertion |
| Shared scratchpad | A store acknowledgment is retained; its readback data is not an architectural load result | Source review, byte-mask storage test and unchanged dual-hart firmware oracle |
| AXI burst buffer | Burst loading/filling and draining use disjoint controller states; it is not a simultaneously streaming FIFO | Runtime `!(mem_we && mem_re)` assertion |

The assertions are inserted in an isolated simulation netlist, not the physical
candidate. The manifest binds their inputs to the tested assembly. SFPU enum
encodings are reviewed against that exact pre-synthesis source; the checks are
not a generic assertion library for later RTL revisions. Runtime coverage and
source review are not a formal equivalence proof.

## Functional results

Both the ordinary and assertion-enabled full-system tests pass two boots,
packet-abort recovery, 9,633 independently checked words per boot and all
14 lifecycle cases. Each takes 16,477,049 system cycles, exactly matching the
retained baseline. Frozen firmware and numerical/lifecycle oracles are unchanged.
The existing harness still evaluates the old memory-clock input, but the new
adapter ignores that input and samples SRAM only on the system clock.

Local tests cover 32-bit × 2,048-word/two-read, 36-bit × 256-word/one-read and
32-bit × 16,384-word/two-read configurations. All pass masked writes, bank
boundaries, concurrent write-priority behavior, disabled-read holds, synchronous
command capture and reset retention. The isolated one-hot return alternative
also passes these local tests; it is not promoted or full-system qualified.
The chip SPI-loader smoke must still be rerun after integrating the 1x clock
binding into the chip wrapper. Old 2x loader evidence is not a 1x loader pass.

## Representative routed experiment

Eight actual SRAM macros implement a 2,048 × 32 two-read banked memory with
registered command inputs and result outputs. The 10-ns clock, 0.25-ns
uncertainty, declared I/O budgets and all three PVT/RC corners are unchanged
across the completed trials. Extracted SPEF and real SRAM Liberty are used.

| Trial | Worst setup slack | Worst hold slack | Setup TNS | Hold TNS | Outcome |
|---|---:|---:|---:|---:|---|
| Binary selector, default CTS | −0.495889 ns | −0.126829 ns | −4.443952 ns | −0.927285 ns | Fails setup and hold |
| Binary selector, SS CTS/tighter clustering and post-route-estimate repair | −0.282133 ns | +0.052682 ns | −2.137645 ns | 0 ns | Hold passes; setup fails |
| One-hot registered bank selector, same repair settings | −0.329493 ns | +0.035324 ns | −1.517167 ns | 0 ns | No worst-setup improvement; not promoted |

The second trial requests one-sink clustering, a 20-µm clustering diameter,
SS-corner CTS characterization, and clock buffers of strengths 16/8/4. It also
enables post-global-route timing repair with 0.15-ns hold and 0.25-ns setup
margins. The pinned CTS tool nevertheless ends H-tree subdivision at larger
leaf groups; requesting one-sink clustering does not guarantee one sink per
physical leaf. Its slow-corner critical macro clock has 1.216720-ns slew,
outside the macro's 0.351-ns input limit. The SRAM read then crosses three
return-selection logic cells before the result register.

The binary repair trial reports zero detailed-router DRC errors and zero
power-grid disconnects, but still has 26 antenna-violating nets and 3,610
slow-corner slew violations. The SRAM Liberty also defaults output transition
limits to 0.040 ns; that metadata must be checked against its characterized
output tables and actual loads, not silently relaxed. Positive setup alone
would not resolve these electrical failures. None of these probes is qualified.

Next: dedicated local SRAM clock leaves, localized command/return buffering,
and explicit review of macro transition limits. If the existing macro cannot
meet its boundary limits, select or characterize a suitable memory before
scaling up. Do not apply false paths, change clocks or waive electrical checks
to obtain a pass. Full-chip placement additionally needs more durable storage.

## Reproduction

Use fresh output names; existing trials are immutable evidence. The generator
and runners have finite timeouts and a separate 4-GiB guard for the small probe.
The full-core runner retains its 10-GiB minimum and 30-GiB recommended reserve.

```sh
bash scripts/m6_assemble_1x_candidate.sh build/m6_memory_map_v2 build/m6_1x_new
bash scripts/m6_run_1x_memory_test.sh build/m6_1x_memory_new binary
python3 scripts/m6_check_1x_consumers.py build/m6_1x_new build/m6_1x_assert_new
bash scripts/m6_run_1x_consumer_test.sh build/m6_1x_assert_new build/m6_1x_system_new
python3 scripts/m6_prepare_bank_probe.py build/m6_bank_new
bash scripts/m6_run_bank_probe.sh build/m6_bank_new route_v1 --to OpenROAD.STAPostPNR
python3 -m scripts.m6_100mhz_evidence --check docs/m6_100mhz_evidence.json
```

The CLI in the pinned OpenLane version expects whitespace-separated list
overrides, despite its help text saying JSON values. The rejected
`clock_repair_v1` used JSON-array strings and failed before CTS; it is not a
timing result. The accepted `clock_repair_v2` resolved configuration contains
the intended actual corner/library lists. Earlier SDC and reset-harness failures
are retained separately and are not relabeled as hardware failures or passes.
