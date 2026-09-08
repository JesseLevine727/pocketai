# M6 SRAM electrical diagnosis after storage recovery

Status: **IP-contract inconsistency demonstrated; physical qualification open.**
The 100-MHz requirement is unchanged. The supplied Liberty files, timing arcs,
SDC constraints, antenna checks and electrical checks were not relaxed.

## Evidence and hypotheses

The retained 8-macro binary repair trial has −0.282133-ns worst setup, positive
hold, a 1.216720-ns critical SRAM clock slew and 3,610 SS slew violations.
The bounded investigation separates three predictions:

1. If the output-library default is inconsistent with the characterization,
   a table-domain audit will find no sample meeting that default, independently
   of clock-tree placement. **Confirmed for all three screened macro sizes and
   all three supplied corners.**
2. If shared clock-leaf loading causes the poor SRAM clock edge, dedicated
   local drivers will reduce that slew. **Confirmed, but not sufficient for
   timing closure:** extra clock latency and other paths still matter.
3. If return selection alone dominates, a shallower registered one-hot return
   should improve worst setup. The earlier one-hot experiment did not improve
   WNS. This rules out promoting that particular mapping, not every possible
   return-path optimization.

## Output-limit inconsistency

The pinned SRAM22 Liberty libraries declare `time_unit: "1ns"` and
`default_max_transition: 0.04`. The `dout` bus and its pins have no overriding
transition limit. Its characterized rise/fall tables use 10–90% slew thresholds.
The table minima below already exceed the default, including at the fastest
corner and smallest characterized load.

| Macro depth, 32-bit words | SS minimum output transition | TT minimum | FF minimum | Declared default |
|---|---:|---:|---:|---:|
| 128 | 0.157161 ns | 0.087407 ns | 0.062232 ns | 0.040 ns |
| 256 | 0.154113 ns | 0.080335 ns | 0.059360 ns | 0.040 ns |
| 512 | 0.163674 ns | 0.088208 ns | 0.062843 ns | 0.040 ns |

Each minimum spans 98 rise/fall samples; it is not one extracted timing path.
Interpolation within the table cannot produce a value below its minimum.
Extrapolation to an uncharacterized load or slew is not a qualification method.
This finding establishes an inconsistent integration contract, **not a silicon
defect or proof that Sky130 cannot reach 100 MHz**. Reducing the clock frequency
does not, by itself, repair an output-transition constraint.

The read-only screen records all source hashes and refuses unsupported units,
missing tables, malformed dimensions and unreviewed output overrides. It does
not modify any macro view. Primary data: [electrical_screen.json](evidence/m6_memory_resumed_v2/electrical_screen.json).

## Clock-drive screen and one routed candidate

The 512-word SRAM clock pin has SS rise/fall capacitances of 0.241128/0.233091 pF
and a 0.351-ns input transition limit. Sky130 HD standard-cell slews use 20–80%
thresholds. The screen normalizes these to the macro's 10–90% thresholds using
the linear 80/60 ratio; it does not claim a SPICE waveform measurement.

With no wire capacitance and the best characterized input slew, `clkbuf_16`
still predicts a 0.506735-ns rising transition at that macro load. `buf_16`
predicts 0.510218 ns. Merely placing either buffer closer cannot remove its
pin-load-only shortfall in this model. `clkinv_16` instead predicts minima of
0.323729/0.336905 ns for rise/fall. These are screening estimates, not a routed
clock-tree pass. A preceding `clkinv_2` preserves the original clock polarity.

The isolated `M6LeafProbe` flow inserts one such pair per macro after the pinned
CTS step, places it near the real LEF clock terminal, connects all four PG pins
and protects the pair from removal. No clock frequency, timing exception or
library value changes. The full-core historical CTS flow is untouched.

| Routed probe | Worst setup | Worst hold | Setup TNS | Hold TNS | SS slew violations | Antenna nets/pins |
|---|---:|---:|---:|---:|---:|---:|
| Prior binary repair | −0.282133 ns | +0.052682 ns | −2.137645 ns | 0 ns | 3,610 | 26 / 27 |
| Local inverter pairs | −0.386309 ns | +0.004979 ns | −5.904418 ns | 0 ns | 3,564 | 34 / 41 |

Both report zero detailed-router DRC errors and zero power-grid violations;
these are not clean all-checks physical results. The local trial's critical
macro rising-clock slew is 0.348873 ns, but its clock arrives at 2.401708 ns and
worst setup is worse. Six SRAM clock pins still violate the effective 0.350-ns
design slew limit, with a reported maximum of 0.358384 ns. Other command,
return and output-limit failures remain. **The local candidate is not promoted.**

The first local trial, `local_leaf_v1`, failed with 32 critical supply-pin
disconnects: `make_instance` did not populate the new cells' PG connections,
and `dont_touch` prevented later automatic repair. Explicit PG connections
before `dont_touch` fix that implementation error in `local_leaf_v2`.
The post-route regression rejects v1 and accepts v2, verifying 8 macros,
16 correctly paired inverters and all 64 PG connections. The first failure is
retained; passing topology does not imply passing timing. Primary reports:
[summary](evidence/m6_memory_resumed_v2/local_leaf_summary.rpt),
[SS checks](evidence/m6_memory_resumed_v2/local_leaf_ss_checks.rpt).

## Single-clock loader integration

The new digital chip stage directly binds the legacy-named `clk_mem_i` input
to the system clock; no divider remains. The retained v2 test explicitly pins
1-ns/1-ps timescale and advances 5,000 precision ticks per half-cycle, giving a
10-ns period. Runtime assertions check that precision and the direct 1x clock
binding. The first v1 harness used 5 precision ticks, not 5 ns; its zero-delay
functional pass is retained but is not the 10-ns-period evidence. Clock/UART
sampling and these additional checks change; the firmware and useful
oracles are unchanged. The 188-byte firmware loads and reads back over SPI;
both real Ibex harts return their expected fast-multiply results, 5,535 and
5,580, and UART returns both expected bytes. The test passes 208 SPI frames.
The source manifest and [primary log](evidence/m6_memory_resumed_v2/chip_1x.log)
bind this result to the single-clock assembly.

This closes the SRAM-only **RTL loader integration** gap. It does not test
physical pads, external DRAM, extracted chip timing or full GPT-2 inference.

## Reproduction and next decision

Use fresh build names and run from the repository root. Failed and completed
run directories are immutable evidence.

```sh
python3 -m scripts.m6_electrical_screen build/m6_electrical_new
bash scripts/m6_run_leaf_probe.sh build/m6_bank_1x_probe_v2 local_leaf_new \
  --from M6Leaf.CTS \
  --with-initial-state /work/runs/route_v2/11-openroad-detailedplacement/state_out.json \
  --to OpenROAD.STAPostPNR \
  -c 'CTS_SINK_CLUSTERING_SIZE=1' -c 'CTS_SINK_CLUSTERING_MAX_DIAMETER=20' \
  -c 'CTS_CORNERS=max_ss_100C_1v60' \
  -c 'CTS_CLK_BUFFERS=sky130_fd_sc_hd__clkbuf_16 sky130_fd_sc_hd__clkbuf_8 sky130_fd_sc_hd__clkbuf_4' \
  -c 'RUN_POST_GRT_RESIZER_TIMING=true' \
  -c 'GRT_RESIZER_HOLD_SLACK_MARGIN=0.15' -c 'GRT_RESIZER_SETUP_SLACK_MARGIN=0.25'
python3 -m scripts.m6_prepare_1x_chip build/m6_portable_1x_candidate_v1 \
  build/m6_soc_1x_new build/m6_chip_1x_new
bash scripts/m6_run_1x_chip_test.sh build/m6_chip_1x_new build/m6_chip_test_new
python3 -m scripts.m6_100mhz_evidence --check docs/m6_100mhz_evidence.json
```

`asic/m6/check_leaf_probe.tcl` runs read-only in the pinned OpenROAD container;
set `M6_LEAF_ODB` to the desired probe's post-route ODB. It intentionally fails
on the retained first local trial. The runner limits each physical experiment
to 900 s; this pass used one clock topology plus its PG correction, not a sweep.

Storage no longer blocks implementation: approximately 135 GiB was available
after the authorized cleanup. The next required resource is a defensible SRAM
integration contract: reviewed corrected characterization, a bounded dedicated
recharacterization effort, or alternative compatible IP with usable timing and
physical views. A substitute value for the 40-ps limit cannot be chosen merely
to eliminate violations. The bounded screen and physical experiment do not
establish that replacement contract. Resolve it before full-system routing;
clock/command/return timing and antenna closure will still be necessary.
