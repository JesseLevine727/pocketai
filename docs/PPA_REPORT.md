# PocketAI FPGA results and Sky130 port

Status: **preliminary M6 report; M6 is not closed.** The qualified FPGA release
is `7405919`. The full SRAM-backed digital system now passes functional tests,
synthesis and macro-placement/power-grid connectivity checks. These results
do not describe a routed, timing-closed chip or measured ASIC inference.
Acceptance is recorded in [M6_PLAN.md](M6_PLAN.md).

On 2026-09-08, the user deferred the 100-MHz ASIC closure requirement. M6 must
still report and verify timing at the implemented clock. The current candidate
is 12.5 MHz system / 25 MHz memory; it is not yet qualified. This acceptance
change does not alter the existing
100-MHz SRAM probe results. The user subsequently approved deferring SRAM-internal
verification and unavailable leakage data for a research-only result. Those
gaps remain unqualified; the deferrals do not waive our full-system functional,
macro-boundary timing, routing or power-connectivity checks.

## System and evidence boundary

PocketAI runs the full quantized GPT-2 model on two fast-multiply Ibex harts,
a GEMM engine and an SFPU in PYNQ-Z1 programmable logic. The numerical path
uses W8A8 weights/activations and int16 intermediate representations. The ARM
host provisions the model, controls requests and checks results; it does not
replace the inference computation in the reported measurements.

The ASIC port must retain both harts, the accelerators, autonomous transfer
control, scratchpad and coherent read mirrors. The Zynq processing system,
DDR controller/PHY, interconnect shell and FPGA-specific clock/pad primitives
are platform infrastructure. The external memory arena is not an on-chip SRAM.
An ASIC interface must replace that platform boundary before full-system
throughput can be evaluated. No FPGA-to-ASIC clock scaling is used here.

The [preflight ledger](m6_preflight_evidence.json) records primary-artifact
hashes and tool outputs. Physical-board measurements come from the frozen
[startup evidence](m5_startup_evidence.json); implementation area and static
timing are tool results, not physical ASIC measurements. Missing results are
marked unavailable. A missing number is not zero.
The newer [port ledger](m6_port_evidence.json) records full-system functional,
synthesis, block-area and floorplan evidence separately from that preflight.

## Qualified FPGA implementation

The frozen implementation operates at 91 MHz. Its reported setup slack is
+0.269 ns and hold slack is +0.008 ns, with zero total negative setup and hold
slack. Vivado reports 29,229 LUTs, 21,833 registers, 127.5 BRAM36 equivalents
and no DSP blocks. The FPGA audit passed again before starting M6. These
numbers are the qualified implementation, not a new ASIC result.

| Metric | Full FPGA system | Full-system ASIC |
|---|---:|---|
| Qualified operating clock | 91 MHz | Unavailable; 100-MHz requirement deferred |
| LUTs / registers | 29,229 / 21,833 | Not applicable |
| BRAM36 equivalents / DSPs | 127.5 / 0 | Not applicable |
| Standard-cell and macro area | Not inferred from LUTs | Unavailable |
| Full-layout setup / hold slack | +0.269 / +0.008 ns | Unavailable |
| Maximum achievable frequency | Not characterized by a clock sweep | Unavailable |
| Measured board watts | Explicitly deferred by user | No fabricated ASIC |
| Qualified activity-based ASIC power | Not applicable | Unavailable |

The qualified routed checkpoint was opened read-only for hierarchical
utilization reports and a primitive inventory. Synthesis had flattened much
of the combinational logic. Grouping remaining names therefore does not recover
reliable per-block LUT ownership, and shared LUT sites can appear in multiple
groups. Those diagnostic groups are retained but are not a per-block PPA table.
A separate hierarchy-preserving, out-of-context synthesis now provides block
attribution. It uses the same qualified functional sources and explicitly
forbids DSP inference in the fast multipliers. The initial experiment inferred
two DSPs despite the global limit and was rejected as a matched comparison.
The retained second run uses zero DSPs. Neither run replaces the qualified
routed checkpoint or its measured performance.

| FPGA block, separate synthesis | LUTs | Flip-flops | BRAM36 equivalents |
|---|---:|---:|---:|
| Hart 0 | 3,319 | 1,059 | 0 |
| Hart 1 | 3,215 | 1,059 | 0 |
| GEMM, including its buffers | 11,069 | 8,242 | 64 |
| SFPU, including its buffers/ROMs | 3,484 | 2,450 | 15 |
| Memory, mirrors, other control and boundary | 3,267 | 3,137 | 48.5 |
| Total portable core | 24,354 | 15,947 | 127.5 |

The final row excludes the Zynq platform shell. Inferred scratchpad/mirror
logic is included in the combined memory/control row because synthesis absorbs
those arrays into the enclosing module. This table reports synthesis resources,
not placed FPGA area, and does not convert LUTs into square millimeters.
Primary reports are `build/m6_fpga_blocks_v2/{full,hierarchy}.rpt`.

## Measured FPGA inference performance

Each row below contains three unprofiled requests using the original prompt
and complete model. Delivered time starts at START and ends after safe DMA
return and copying the output tokens. It includes actual prompt processing,
first-use preparation, inference and delivery control. Provisioning, model/
overlay/firmware loading and independent result checking are outside this
request interval and recorded separately in the frozen campaign.

| Request | Generated tokens | Mean delivered time | Pooled output throughput |
|---|---:|---:|---:|
| Science | 1 | 9.993854 s | 0.100061 token/s |
| Computing | 1 | 9.994739 s | 0.100053 token/s |
| Story | 2 | 16.603659 s | 0.120455 token/s |

The slowest one-token request took 9.996906 s, leaving approximately 3.094 ms
against the 10-s threshold. This is a narrow measured pass on these requests,
not a sustained-throughput, arbitrary-prompt or tail-latency guarantee. Cached
maximum-context forwards and cold derived-cache preparation are different
workloads; their results are retained in [M5_STARTUP_RESULTS.md](M5_STARTUP_RESULTS.md).

GEMM compute-only GMAC/s does not measure complete GPT-2 throughput. This report
does not reuse a historical microbenchmark as current end-to-end performance,
or infer an ASIC token rate from the FPGA clock ratio. Matched current compute
and interface-bandwidth measurements remain to be added for the ASIC scope.

## ASIC source and memory feasibility

The complete portable system elaborated through sv2v and Yosys with both fast
Ibex harts present. The stage checks 178 qualified source files against the
frozen evidence before copying them into an M6 directory. Two transformations
are explicit: binding the qualified generic latch-based clock gate in place of
the FPGA clock primitive, and rewriting two packed zero-valued I-cache
configuration patterns into equivalent replication syntax. The caches remain
disabled. Elaboration alone is not functional equivalence or ASIC synthesis.

The hierarchy inventory contains 70 memory instances and 3,509,017 logical
bits before memory optimization. It includes initialized ROMs and small
multiported arrays as well as the bulk data memories. These counts are neither
the physical SRAM allocation nor an ASIC area result. The read-clock masks are
observed before Yosys merges output registers into memories; they must not be
interpreted as evidence that every source memory has asynchronous reads.

The first dual-port OpenRAM candidate was rejected as simulated timing/power
evidence because its retained generation log explicitly uses analytical Elmore
characterization. The SRAM22 candidate provides Liberty views with a Liberate
characterization header at slow, typical and fast corners. Its original GDS,
LEF, behavioral model, SPICE and Liberty files are pinned and retained.
The authors describe SRAM22 as work in progress and distinguish its external
installation from proprietary DRC/LVS/PEX/simulation integrations.
[SRAM22 documentation](https://github.com/ucb-substrate/sram22).

## Complete memory port and functional results

The ASIC stage additionally binds Ibex's resettable flip-flop register file;
both `RV32MFast` units remain unchanged. Forty-seven logical arrays map to
292 physical 512 × 32 SRAM22 macros. They contain 3,449,856 logical mapped bits
and allocate 4,784,128 physical bits (584 KiB). Twenty-one small asynchronous
buffers, control arrays and constant ROM instances remain explicit synthesized
logic. They are included in area, not omitted memories.

SRAM22 has one read-or-write port. The adapter services a read and then a write
at twice the system clock, preserving simultaneous logical reads/writes and
read-before-write collisions. Two-read arrays have two physical copies with
broadcast writes. Banking, byte masks, width padding and duplication are fully
charged to area. The [memory contract](M6_MEMORY_PORT.md) defines the clock phase
and reset behavior. This port does not reduce the logical model or memory sizes.
The current revision uses a separate set-high phase-data register in each
logical adapter. Synthesis retains all 47 phase registers separately from the
reset-low system-clock divider. The memory test checks their phase alignment
through reset, and both full-system and digital-chip tests pass again.

Three adapter configurations passed byte masks, bank boundaries, concurrent
collisions, disabled-read hold, command capture and reset retention. The full
dual-hart accelerator oracle then passed two boots, packet-abort recovery,
9,633 independently checked words per boot and all 14 lifecycle cases.
The total 16,477,049 system cycles match the frozen FPGA-model baseline exactly.
Firmware and numerical/lifecycle oracles were unchanged; only the top name and
two-phase clock servicing changed. These are RTL simulation results, not
post-layout timing or physical ASIC measurements.

The first assembled netlist left padded out-of-range ROM values as undriven
wires. Its final optimized synthesis check was clean, but the pre-synthesis
check reported 39,127 undriven-bit problems. The next assembly explicitly normalizes
undriven values to Verilog unknowns with `opt_expr -undriven`, preserving
don't-care semantics rather than silently supplying a RAM implementation.
That assembly passes strict `check -assert`, the complete unchanged firmware
oracle and the synthesis checker. Failed trials remain available.

## ASIC block area and physical progress

The following values sum actual mapped standard-cell library areas and the
pinned SRAM LEF area. They are **synthesis-only instance areas**, not routed
die areas. The hierarchy-preserving synthesis retains ownership before final
flattening; every final cell is assigned once. The [area extractor](../scripts/m6_block_areas.py)
checks the standard-cell sum against the synthesis report.

| ASIC block | Standard cells (mm²) | SRAM macros | SRAM (mm²) | Total instances (mm²) |
|---|---:|---:|---:|---:|
| Hart 0 | 0.170121 | 0 | 0 | 0.170121 |
| Hart 1 | 0.170121 | 0 | 0 | 0.170121 |
| GEMM and buffers | 1.338738 | 112 | 22.277763 | 23.616501 |
| SFPU and buffers/ROM logic | 0.191877 | 18 | 3.580355 | 3.772231 |
| Scratchpad | 0.011869 | 32 | 6.365075 | 6.376944 |
| Instruction mirror | 0.023798 | 64 | 12.730151 | 12.753948 |
| Data mirror | 0.023798 | 64 | 12.730151 | 12.753948 |
| Other control and native-AXI boundary | 0.232068 | 2 | 0.397817 | 0.629885 |
| Total | 2.162388 | 292 | 58.081312 | 60.243699 |

The SRAM contribution dominates this implementation. Its area reflects the
available macro granularity and read-port replication, not extra model
capacity. The candidate core floorplan is 9.1 × 9.9 mm (90.09 mm²); this chosen
rectangle is not an optimized die or a pad-inclusive chip. Floorplanning places
all 292 macros. Power-grid checks report zero disconnects on both `vdd` and
`vss`. Standard-cell area after tap insertion differs from synthesis because
physical-only cells are added. The previous direct-clock-as-phase revision
completed initial global/detailed placement and a four-tree CTS run with
6,331 inserted buffers, but failed 25-MHz setup timing. The revised phase-data
design has passed synthesis and macro-placement/PDN checks; it has not yet
completed standard-cell placement, CTS or routing. Earlier physical progress
does not qualify the changed netlist.

The generated-clock constraint uses the actual falling-edge divider output pin:
25-MHz memory clock, 12.5-MHz system clock, with rising system edges at 20 and
100 ns. Native AXI uses the exported system clock. The intermediate boundary
assumes 0.5–8 ns input/output delays, 0.1-pF loads and 0.25-ns clock uncertainty.
These are declared controller-interface assumptions, not package measurements.
Unbuffered pre-placement timing is not an achieved frequency or a usable fmax.

Output-port buffering initially moved the generated-clock constraint away
from the divider. Selecting the actual divider Q corrected that constraint.
The system clock also controls the SRAM adapter's read/write phase; clock
propagation now stops at its data-only branches without disabling data timing
arcs. The automatic CTS traversal nevertheless treated SRAM data inputs as
clock sinks. The M6 flow therefore explicitly selects memory, system and the
two Ibex gated-clock nets. That trial's tree construction is retained in
`build/m6_core_physical_v3/runs/clocks_v6`; earlier trials remain unqualified.
This adaptation follows the pinned tool's separate explicit-net path, not a
timing-check waiver. [Pinned OpenROAD CTS implementation](https://github.com/The-OpenROAD-Project/OpenROAD/blob/edf00dff99f6c40d67a30c0e22a8191c5d2ed9d6/src/cts/src/TritonCTS.cpp).
The subsequent RTL change removes the direct clock-as-phase data branches.
It retains the memory contract and is not an added timing exception.

## Loading, console and external-memory boundary

The integrated digital chip-core test loads and reads back 188 firmware bytes
over SPI into actual SRAM. Both real Ibex harts execute fast multiplies and
return 5,535 and 5,580 in separate scratchpad words; their two console bytes
arrive through the UART. The test uses the real clock divider and memory
adapter. The serial component test additionally checks all 16 byte masks,
malformed frames, busy-command rejection, independent AXI AW/W backpressure,
invalid addresses and UART ordering. These finite interface tests supplement,
not replace, the complete accelerator workload above.

The chip simulation enables Verilator's `--x-initial-edge` option to model
initial unknown-to-low asynchronous reset edges. Without it, internal reset
nets already held low by the host controller do not initialize all Ibex reset
values in the two-state simulator. The initial failed smoke is retained; the
corrected simulator configuration passes without changing RTL or answers.

The [interface contract](M6_CHIP_INTERFACE.md) specifies a mode-0 SPI register
loader and an 8-N-1 UART that drains the existing console FIFO. Full-model data
still require an **external RAM controller** on the native 32-bit AXI master.
The complete 266,289,152-byte arena and its DDR PHY/controller are not on-chip.
At the candidate 12.5-MHz system clock, AXI's analytic payload ceiling is
50 MB/s; no physical ASIC bandwidth measurement is claimed. SPI controls
firmware/configuration and existing DMA, not a substitute writable SPI-flash
KV store. Physical I/O cells, pad-ring integration and package timing are not
qualified by the digital test.

## Single-SRAM implementation experiment

The probe contains one `sram22_512x32m4w8` memory and a registered interface.
It contains no Ibex, GEMM, SFPU or chip pads. OpenLane uses the pinned Sky130
high-density standard-cell library and a 10-ns clock. The timing corners are
FF at −40 °C/1.95 V with minimum RC, TT at 25 °C/1.80 V with nominal RC, and SS
at 100 °C/1.60 V with maximum RC. The probe uses fallback I/O constraints;
those constraints do not specify a production chip interface.

| Probe result | Value | Evidence scope |
|---|---:|---|
| Standard-cell area | 5,575.35 µm² | Post-route tool output |
| SRAM macro area | 198,909 µm² | Rounded tool output; not whole-system memory |
| Total instance area | 204,484 µm² | Rounded tool output; includes only probe |
| Die area | 390,600 µm² | Chosen 620 × 630 µm floorplan |
| Worst setup slack | +2.270197 ns | Extracted static timing across declared corners |
| Worst hold slack | +0.109013 ns | Extracted static timing across declared corners |
| Setup / hold violating paths | 0 / 0 | Probe only |
| Detailed-router DRC violations | 0 | Routing rule checks |
| Power-grid connectivity violations | 0 | Connectivity; not qualified IR-drop/power |
| Public KLayout DRC violation items | 0 | FEOL, BEOL and grid checks; SRAM exclusion off |
| Full OpenLane Classic flow | Failed | Magic rejected SRAM layout layers |
| Standalone SRAM LVS | Failed | Public KLayout extraction did not match supplied SPICE |
| Full-probe LVS | Not qualified | No matching result established |

The SRAM supplies are exposed on metal 2. An explicit metal-2-to-metal-4 PDN
connection fixed the disconnected supply network seen with the default macro
grid. A new GDS copy adds only a missing PR-boundary rectangle from the LEF.
The preparation tool checks every other layer's geometry and all instance
transforms before and after writing; manufacturing mask layers are preserved.
Neither change is a DRC or LVS waiver.

KLayout streamed the complete probe GDS and its public periphery-rule runset
reported zero items with FEOL, BEOL and manufacturing-grid checks enabled and
`sram_exclude=false`. This is a result for that runset, not foundry signoff.
Magic cannot faithfully ingest several SRAM layers, including mask-add layers.
The Classic flow therefore remains failed rather than hiding those errors.
The distinction matters because macro abstract views are not a substitute for
complete layout verification. OpenLane also warns that missing macro timing
views can hide boundary failures; this probe uses the actual Liberty views.
[OpenLane macro integration](https://openlane2.readthedocs.io/en/stable/usage/using_macros.html).

A separate bounded KLayout LVS run compared the original SRAM GDS with its
supplied SPICE and reported that the netlists do not match. The only runset
change removed a logging dependency on the unavailable `pmap` utility; no
extraction or comparison rule was changed. The supplied SPICE contains special
SRAM transistor models that the public extraction deck does not name. This is
an identified coverage gap, not proof of a defective SRAM and not permission
to relabel the failed comparison as a pass. Internal SRAM verification remains
unqualified. The user explicitly approved integrating the memory as third-party
IP with its internal verification deferred for this research-only result.
This approval is not evidence that the memory is externally verified.

Default-activity power output is retained but not promoted to a PPA result.
The SRAM Liberty leakage value is zero, workload switching activity has not
been supplied, and source locations for a qualified IR-drop analysis are absent.
These limitations prevent a credible total power or energy-per-token claim.

## Reproduction and remaining gates

The tool and library revisions are in [tools.json](../asic/m6/tools.json).
Run the read-only evidence check with:

```sh
python3 -m scripts.m6_preflight_evidence --check docs/m6_preflight_evidence.json
python3 -m scripts.m6_port_evidence --check docs/m6_port_evidence.json
build/m6_tools_venv/bin/python -m unittest discover -s tests/m6 -v
python3 -m scripts.audit_m5_startup
```

The source stage and isolated macro run use fresh directories and retain failed
trials. See [M6_PORT_REPRODUCE.md](M6_PORT_REPRODUCE.md) for the current port and
[M6_PREFLIGHT_REPRODUCE.md](M6_PREFLIGHT_REPRODUCE.md) for earlier macro checks.

The full memory mapping, whole-system RTL functional checks, digital loader
test and synthesis/floorplan gates have passed. M6 still needs full-system
placement/routing and timing closure at the declared operating clock, physical
pad/chip integration, scoped physical verification, activity-qualified partial
power and the remaining performance/report entries. The SRAM probe cannot
replace those gates. Measured board watts and the 100-MHz ASIC requirement are
explicitly deferred, as are SRAM-internal verification and unavailable leakage
data under the approved research-only scope. There is no MPW submission or
fabrication-ready claim in this release.

The current checkpoint is **waiting for storage**, not awaiting another timing
or SRAM acceptance waiver. On 2026-09-08, approximately 7.4 GiB remained after
byte-identical completed views were consolidated into hard links. Every
original evidence path and its full-content hash was preserved. The physical
runner rejected the next placement stage below its 10-GiB minimum. Additional
working space is required for routing, extraction and chip-level artifacts;
30 GiB free is a practical recommended starting reserve, not a measured peak.
