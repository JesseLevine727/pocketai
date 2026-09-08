# PocketAI FPGA results and Sky130 feasibility

Status: **preliminary M6 report; M6 is not closed.** The qualified FPGA release
is `7405919`. The ASIC results below apply only to an SRAM integration probe.
They do not describe a routed PocketAI processor, a complete chip, or measured
ASIC inference. Acceptance is recorded in [M6_PLAN.md](M6_PLAN.md).

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

## Qualified FPGA implementation

The frozen implementation operates at 91 MHz. Its reported setup slack is
+0.269 ns and hold slack is +0.008 ns, with zero total negative setup and hold
slack. Vivado reports 29,229 LUTs, 21,833 registers, 127.5 BRAM36 equivalents
and no DSP blocks. The FPGA audit passed again before starting M6. These
numbers are the qualified implementation, not a new ASIC result.

| Metric | Full FPGA system | Full-system ASIC |
|---|---:|---|
| Qualified operating clock | 91 MHz | Unavailable; 100 MHz target |
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
Per-block area for each hart, GEMM, SFPU, memory and control remains an M6 report
requirement. A new hierarchy-preserving synthesis would be a separately labeled
implementation, not a retroactive measurement of the qualified checkpoint.

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
unqualified. Treating the memory as externally verified third-party IP would
require an explicit acceptance decision before proceeding on that basis.

Default-activity power output is retained but not promoted to a PPA result.
The SRAM Liberty leakage value is zero, workload switching activity has not
been supplied, and source locations for a qualified IR-drop analysis are absent.
These limitations prevent a credible total power or energy-per-token claim.

## Reproduction and remaining gates

The tool and library revisions are in [tools.json](../asic/m6/tools.json).
Run the read-only evidence check with:

```sh
python3 -m scripts.m6_preflight_evidence --check docs/m6_preflight_evidence.json
build/m6_tools_venv/bin/python -m unittest discover -s tests/m6 -v
python3 -m scripts.audit_m5_startup
```

The source stage and isolated macro run use fresh directories and retain failed
trials. See [M6_PREFLIGHT_REPRODUCE.md](M6_PREFLIGHT_REPRODUCE.md) for commands.

M6 still needs complete SRAM mapping with tested port/mask/latency semantics,
whole-system functional checks, a usable chip/loading boundary, full-system
placement/routing and 100-MHz timing, qualified physical verification and the
missing PPA entries. The SRAM experiment cannot replace those gates. Measured
board watts are explicitly deferred; no other gate has been waived. There is
no MPW submission or fabrication-ready claim in this release.
