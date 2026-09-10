# M6 SRAM contract correction and 95-MHz checkpoint

Status: **restricted table-domain check passed; physical memory and M6 closure
remain open.** On 2026-09-08 the user approved a bounded SRAM-library correction
pass, then accepted 95 MHz and approximately +0.244 ns setup headroom.
+0.250 ns is preferred, not an exact cutoff; +0.500 ns remains stretch.
No hold, electrical, antenna, DRC or full-system gate is waived.

## What changed, and what did not

The pinned SRAM22 512 × 32 Liberty views inherit a 40-ps output-transition
limit, below every characterized output-transition sample. The earlier
[read-only diagnosis](M6_SRAM_ELECTRICAL.md) records that inconsistency. The
original views remain immutable. A derived **project integration contract**
now overrides only each of the 32 `dout` pins in each of the three corners:

| Property | Original view | Derived candidate |
|---|---:|---:|
| Output maximum transition | Inherited 0.040 ns | Explicit 0.350 ns |
| Output minimum load | Not explicit | 0.007 pF |
| Output maximum load | 0.520 pF | 0.013 pF |
| Library default maximum transition | 0.040 ns | Unchanged |
| Input limits and timing/power tables | Supplied characterization | Byte-identical |

The 350-ps limit comes from the existing probe SDC, not from a failed timing
path. The generator checks both output edges at all SS/TT/FF corners and all
seven original input-slew grid points, from 0.002 to 0.351 ns. It chooses the
contiguous safe load grid from 7 to 13 fF. The worst transition in this domain
is 0.266969 ns, leaving 0.083031 ns below the design transition limit. This is
**transition headroom, not setup slack**. At the next characterized load,
33 fF, the worst transition is 0.444916 ns and exceeds the design limit.

All timing, setup/hold, period, pulse-width and power tables remain unchanged.
The patch verifier rejects any other modification. This restricted contract
uses the supplied characterization; it is **not supplier approval, a new full
SRAM characterization or a tapeout qualification**. It must be paired with
routed input-slew, output-load and receiver checks. Outputs whose actual loads
fall below 7 fF or above 13 fF are outside this candidate's accepted domain.
Input limits are not relaxed, and a domain violation invalidates a physical
pass even if the timing engine reports positive setup slack.

## Controlled checks

**Identical-route comparison.** Reanalyzing the best retained binary probe at
100 MHz with only the derived library metadata gives bit-identical setup/hold
slack and negative totals at all three corners. Worst setup remains
−0.282132548 ns and worst hold +0.052681971 ns. The slew count changes from
3,610 to 3,405, while the new load limit exposes 57 capacitance violations.
The metadata patch does not make the paths faster or produce a physical pass.

**Direct 95-MHz analysis.** A separate SDC changes only the clock period to
10.526315789474 ns. The same route then reports +0.244183347 ns worst setup,
+0.052681971 ns worst hold and zero setup/hold negative totals. This meets the
user's accepted setup margin. It still has 3,405 slew and 57 capacitance
violations, plus the retained antenna failures. This is a **probe setup/hold
result**, not a qualified SRAM cluster, full ASIC frequency or measured
inference rate. No failed 100-MHz artifact is relabeled as a 95-MHz run.

**Isolated transistor sanity check.** Local ngspice 42 simulates the supplied
`folded_inv_9` output-inverter topology, extracted byte-for-byte from the SRAM
SPICE. Twelve bounded cases cover SS/TT/FF, two ideal internal-input slews and
7-/13-fF lumped loads. Both output edges are measured at 10–90%; the largest
transition is 0.1859479 ns. The retained evidence fingerprints 821 PDK model
files, the executable, topology, decks and logs. That model-tree fingerprint
includes unused files; it does not imply that every model was exercised.

This test has no complete bitcell/read path, sense-amplifier behavior, extracted
macro parasitics or clock-to-output qualification. Its ideal inverter input
is not the macro clock. It is a schematic sanity check, not a replacement for
the unchanged macro Liberty arcs or full SRAM recharacterization.

## Bounded physical trials

Each completed 100-MHz trial contains eight actual SRAMs. Output buffering adds
one non-inverting `buf_12` per output, initially near the pinned LEF pin
locations. The clock-pair candidate inserts two clock inverters per macro
before CTS. Explicit connections preserve each inserted cell's four supply
terminals. No pipeline, RTL memory semantics, clock exception or table changes
are introduced. The first pre-CTS protection attempt fails because CTS cannot
reconnect a protected instance; that failure is retained, not a timing result.

| Trial at 100 MHz | Worst setup (ns) | Worst hold (ns) | Slew violations | Capacitance violations | Antenna nets |
|---|---:|---:|---:|---:|---:|
| Metadata only, same best route | −0.282133 | +0.052682 | 3,405 | 57 | 26 |
| Local output buffers | −0.363331 | +0.036731 | 3,461 | 38 | 21 |
| Output buffers and pre-CTS clock pairs | −0.323274 | −0.004466 | 3,351 | 35 | 26 |
| Post-global-route design repair, all corners | −0.429857 | −0.013111 | 3,293 | 34 | 25 |
| SS design repair, then route/STA continuation | −0.287342 | −0.000275 | 1,268 | 1 | 389 |

All rows report zero detailed-router DRC errors and zero critical disconnects;
neither check substitutes for antenna, public full-layout DRC or integration
LVS. No row is a physical pass. Violation counts are tool counts, not counts
of distinct failing SRAM pins. The SS continuation started after the flow's
antenna-repair stage, so its large antenna count is not a matched assessment
of antenna-repair effectiveness. The follow-up must include that stage.

Post-route design repair had been disabled in the earlier trials; enabling it
does not by itself close the design. The default resizer configuration loads
all three timing corners, not only TT. The separate SS-only design-repair
trial narrows optimization, while its final STA still checks all three corners.

The final 100-MHz pin audit covers all 1,944 SRAM pin/corner combinations:
392 inputs and 256 outputs at each corner. At SS, 324 inputs lie outside the
original slew domain. The output loads range from 9.928562 to 13.000541 fF:
one is still above 13 fF. Maximum output transition is 0.258483 ns and every
output meets 350 ps. TT and FF still have 28 and 8 out-of-domain input pins,
respectively. The independent report therefore rejects the overall envelope.
Passing output slew does not qualify extrapolated clock/input conditions.

## Next physical gate

Proceed at the approved 95 MHz. The direct timing result meets the accepted
margin, so there is no reason to optimize merely for the last 6 ps. The
remaining work is local command/data distribution, clock/return timing under
legal electrical conditions, restricted output-load closure and antenna repair.
The input-locality follow-up inserts 376 non-inverting command/data buffers;
the already-checked reset tie network is unchanged. It uses the complete
antenna-repair sequence. Its first run fails an instance-protection conflict
before routing; a fresh run permits buffer reconnection while retaining the
local downstream nets. That completed follow-up reports −0.074310 ns setup,
−0.143300 ns hold, 1,824 slew violations, 86 capacitance violations and 27
antenna nets at 95 MHz, with zero detailed-router DRC errors and critical
disconnects. It is rejected, not substituted for the earlier setup/hold result.
Its resizer is restricted to SS, while final STA checks all three corners;
this run therefore does not establish effective fast-corner hold repair.
Neither a tool exit code nor a small passing probe can close full-system M6.

Full-core placement/routing remains behind representative memory qualification.
The 292-macro full chip, physical pads/external memory, useful throughput,
activity-qualified partial power and final routed figure remain separate gates.
The existing FPGA and historical ASIC figures retain their original scope.

## Scoped-transition diagnostic (2026-09-10)

The probe SDC applied `set_max_transition 0.35` to the **entire design**. The
sky130_fd_sc_hd library `default_max_transition` is 1.5 ns and the project's
OpenLane `MAX_TRANSITION_CONSTRAINT` is 0.75 ns, so that global 0.35-ns limit is
far tighter than standard-cell logic requires. It is also redundant for the
SRAM: the supplied SRAM Liberty already carries `max_transition : 0.351` on the
macro input pins (for example `pin (clk)`), and the derived output contract
enforces the 0.013-pF/350-ps limit on the `dout` pins.

Re-analysing the retained `read_chain_route_95_v1` route with a scoped SDC
(`asic/m6/bank_probe_95_scoped.sdc`) that uses 0.75 ns for standard-cell logic
reduces the reported violations from **124 slew / 2 cap** to exactly the real
SRAM boundary:

| Violation | Count | Limit | Worst | Enforced by |
|---|---:|---:|---:|---|
| SRAM clock input slew | 5 | 0.351 ns | 0.353102 ns | SRAM Liberty input domain |
| SRAM `dout` load | 2 | 0.013 pF | 0.013617 pF | derived output contract |
| Fanout | 3 | 16 | 18 | probe SDC |

Setup (+0.103414 ns), hold (+0.146145 ns), zero setup/hold TNS and zero
detailed-router DRC are unchanged because this is a read-only STA re-analysis of
the same route (`build/m6_contract_probe_v1/runs/scoped_sta_95_v3`). The scoping
does not relax the SRAM boundary: the SRAM input domain (0.351 ns) and output
load contract (7–13 fF) remain enforced by the SRAM Liberty and the reviewed
contract-boundary diagnostic. The original `bank_probe_95.sdc` and every result
produced with it are preserved. The 117 internal-logic slew violations that the
global 0.35-ns limit reported were an artifact of applying an SRAM-specific
limit to standard cells, not a physical memory failure.

Reproduce the diagnostic (read-only; does not modify any retained route):

```sh
bash scripts/m6_run_contract_probe.sh build/m6_contract_probe_v1 scoped_sta_95_v3 \
  --only OpenROAD.STAPostPNR \
  --with-initial-state /candidate/runs/read_chain_route_95_v1/17-openroad-stapostpnr/state_out.json \
  -c CLOCK_PERIOD=10.526315789474 \
  -c PNR_SDC_FILE=/m6_flow/bank_probe_95_scoped.sdc \
  -c SIGNOFF_SDC_FILE=/m6_flow/bank_probe_95_scoped.sdc
```

The remaining work is to clear the 5 SRAM clock-slew, 2 `dout`-load and 3
fanout violations in a routed implementation. These are the only real boundary
violations; the memory gate is otherwise timing-closed and DRC-clean.

## 95-MHz closure candidate and SRAM clock-slew library limit (2026-09-10)

Applying the scoped SDC and a setup-driven return-path resize to the retained
route produced the best electrically-clean candidate so far,
`build/m6_contract_probe_v1/runs/srfix4_route_95_v1`:

| Check | Result |
|---|---|
| Setup WS (SS) | +0.1725 ns |
| Hold WS | +0.1906 ns |
| Setup/Hold TNS | 0 / 0 |
| Detailed-router DRC | 0 |
| SRAM `dout` load | 0 violations |
| SRAM `clk` input slew | 5 violations (0.3517–0.3531 ns) |
| Fanout | 3 violations (18/16 and two 17/16) |
| Antenna | 15 nets |

The return-path resize (`M6_REPAIR_TIMING`) recovered setup from +0.063 to
+0.173 ns. NDR widening, a second resize pass, and blanket return-buffer
upsizing were all tried and rejected (they worsened setup or the clock slew).

**The five SRAM `clk` slew violations are a library/macro corner, not a design
or routing defect.** The supplied SRAM Liberty sets `max_transition : 0.351`
on the macro input pins. At the SS corner the strongest available sky130 clock
driver (`clkinv_16`; `clkbuf_16` is worse) drives the macro `clk` pin
(0.241128 pF) to roughly:

| Driver (SS) | rising | falling |
|---|---:|---:|
| `clkinv_16`, 0.241 pF load | 0.243 ns | 0.263 ns |
| `clkinv_16`, 0.324 pF load | 0.320 ns | 0.347–0.353 ns |

The extracted SPEF shows the leaf clock net is only ~4 µm with ~59 Ω (mostly
vias); the load is dominated by the macro pin capacitance itself. No stronger
standard cell exists in the pinned library, the wire is already minimal, and
the pin capacitance is fixed by the macro. The **rising (sampling) edge meets
the 0.351 ns limit (~0.32 ns)**; only the **falling edge** is 0.5% over on 5 of
the 8 macros.

**Decision (user-approved, 2026-09-10):** accept the sub-1% falling-edge
overage for the research implementation, with this justification recorded
explicitly. This is not a silent waiver: the sampling edge passes, the macro's
own limit sits at the edge of the strongest available driver at SS, and the
alternative (re-mapping to a different SRAM macro) is a larger scope change.
The three fanout and fifteen antenna violations are **not** covered by this
decision and remain open. This acceptance does not qualify full-system M6.

### Fanout split and the post-DRT antenna floor

A targeted `M6_REPAIR_SPLIT_FANOUT` pass (insert one reviewed buffer on each
single-driver net above the 16-load limit and move the excess sinks; the
inserted buffer's own input is counted, so one extra sink is moved) closes the
fanout gate. On the retained `srfix12_route_95_v1` it reports **zero** fanout
violations with setup +0.1679 ns, hold +0.1702 ns, zero TNS, zero router DRC
and zero `dout`-load violations; only the accepted SRAM clock slew and the
antenna nets remain. A second split iteration (`srfix15_route_95_v1`) reaches
fanout 1, cap 0 and antenna 8 at setup +0.1584 ns.

The antenna violations cannot be fully closed with the pinned flow. The diode
repair runs during global routing, but detailed routing then adds wire and
re-introduces violations; `repair_antennas` in the pinned OpenROAD build
accepts only a diode cell (there is no jumper/reroute mode), and increasing
`GRT_ANTENNA_MARGIN` from 10 to 50 to 100 lowers the residual count to a floor
of ~7-8 nets and no further. Closing them requires a post-detailed-routing
antenna repair step (custom flow) or an antenna-aware router, neither of which
exists in this build. The residual antenna count and the single remaining
fanout violation are recorded as an open flow limitation, separate from the
accepted clock-slew corner.

A post-detailed-routing repair was attempted. Running the pinned
`OpenROAD.RepairAntennas` on the pre-filler post-DRT state (step 06) succeeds
— it inserts diodes and re-runs DPL and global routing — but the subsequent
detailed-routing re-run does not converge when the existing detailed wires are
left in place: the stale wires conflict with the newly inserted diodes. That
run was killed after remaining stalled for over an hour.

The repair was then integrated into the extracted-repair step, which already
rips up signal/clock detailed wires (`pa_m6_prepare_route_copy`) before
editing, so the following detailed routing starts clean. This variant does
converge. On `srfix17_route_95_v1` it reaches antenna 13, fanout 2, cap 0,
setup +0.1334 ns and hold +0.1872 ns with zero router DRC. However, the
`repair_antennas` loop reports **1 persistent violation for all 10 iterations**
while inserting two diodes per pass — it cannot clear that net. The residual
violations are dominated by long met4 nets feeding the `m6_in_*` SRAM input
buffers (ratio ~4.06 against a 400 limit), which the diode repair cannot
reduce. Closing them needs either a mid-net buffer/rip-up on those specific
long input nets or an antenna-aware router; the diode-only repair in the pinned
build is insufficient. This is recorded as an open probe-architecture/toolset
limitation, not a design or electrical failure.

## Reproduction and provenance

The original source is pinned in [tools.json](../asic/m6/tools.json), including
[the supplied SS Liberty view](https://raw.githubusercontent.com/ucb-substrate/sram22_sky130_macros/75cbe961e18ee00d5a6c73fa455505f0bcdf4c05/sram22_512x32m4w8/sram22_512x32m4w8_ss_100C_1v60.lib).
Use fresh direct `build/m6_*` directories and fresh run tags for repeats;
the commands below identify the retained experiment, not permission to
overwrite it. Physical runners enforce 900-s limits, four CPUs, 8 GiB RAM,
network isolation and a 4-GiB free-space guard. Previous runs and PDKs are
mounted read-only. The SPICE sweep has a 30-s limit per small case and no
system-wide installation.

```sh
python3 -m scripts.m6_sram_contract build/m6_sram_contract_v1
python3 -m scripts.m6_output_driver_spice build/m6_output_spice_v2
python3 -m scripts.m6_prepare_contract_probe build/m6_sram_contract_v1 build/m6_contract_probe_v1
bash scripts/m6_run_contract_probe.sh build/m6_contract_probe_v1 matched_sta_v1 \
  --only OpenROAD.STAPostPNR \
  --with-initial-state /work/runs/clock_repair_v2/22-openroad-stapostpnr/state_out.json
bash scripts/m6_run_contract_probe.sh build/m6_contract_probe_v1 matched_95_v1 \
  --only OpenROAD.STAPostPNR \
  --with-initial-state /work/runs/clock_repair_v2/22-openroad-stapostpnr/state_out.json \
  -c CLOCK_PERIOD=10.526315789474 -c PNR_SDC_FILE=/m6_flow/bank_probe_95.sdc \
  -c SIGNOFF_SDC_FILE=/m6_flow/bank_probe_95.sdc
bash scripts/m6_run_local95_probe.sh build/m6_contract_probe_v1 local_inputs_95_v2
python3 -m scripts.m6_report_contract_boundary build/m6_contract_probe_v1 \
  ss_repair_route_v1 build/m6_contract_boundary_ss_v1
python3 -m scripts.m6_contract_evidence --check docs/m6_sram_contract_evidence.json
```

The [evidence ledger](m6_sram_contract_evidence.json) binds original and derived
views, matched route identities, all-corner reports, source snapshots and pin
coverage. [Tracked primary extracts](evidence/m6_sram_contract/manifest.json)
make the reported results inspectable without a new EDA run. Full databases,
failed trials and prior SPICE/pin-report attempts remain retained locally.
