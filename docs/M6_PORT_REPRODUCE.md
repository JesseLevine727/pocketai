# M6 full-port reproduction and retained checkpoints

The commands below reproduce the **historical two-phase port**. The user has
reinstated 100-MHz full-system closure; the lower clocks below are retained
unqualified trials, not an alternative acceptance. For the new single-clock
candidate and its separate tests, see [M6_SINGLE_CLOCK_MEMORY.md](M6_SINGLE_CLOCK_MEMORY.md).

This is an intermediate port, not qualified M6 closure. All commands run from
the repository root and require the pinned tools and macro views described in
[preflight reproduction](M6_PREFLIGHT_REPRODUCE.md). Choose fresh `build/m6_*`
names. Never overwrite the retained trials or frozen M1–M5 artifacts.

## RTL, memories and functional checks

The accepted normalization, mapping and assembly are respectively
`build/m6_elaboration_v5`, `build/m6_memory_map_v2` and
`build/m6_portable_assemble_v5`. Reproduction uses the same transformations:

```sh
bash scripts/m6_normalize.sh build/m6_normalize_repro
python3 -m scripts.m6_map_memories build/m6_normalize_repro/normalized.json \
  build/m6_mapping_repro
bash scripts/m6_assemble.sh build/m6_mapping_repro build/m6_assembly_repro
bash scripts/m6_run_system_test.sh build/m6_assembly_repro build/m6_system_repro
```

The system test reuses the hash-checked frozen firmware, numerical oracle and
lifecycle checks. It must report two boots, 9,633 independent words per boot,
packet-abort recovery, 14 lifecycle cases and 16,477,049 system cycles.
Its compilation and simulation are bounded separately; no board inference
campaign is needed to reproduce this gate.

Generate and exercise the digital chip interface:

```sh
python3 -m scripts.m6_prepare_physical build/m6_assembly_repro build/m6_physical_repro
python3 -m scripts.m6_prepare_chip build/m6_physical_repro build/m6_chip_repro
bash scripts/m6_run_chip_test.sh build/m6_chip_repro build/m6_chip_test_repro
build/m6_tools_venv/bin/python -m unittest discover -s tests/m6 -v
```

The chip test loads and reads back firmware through SPI, boots both actual
fast-multiply harts, checks results 5,535 and 5,580, and receives two UART bytes.
`--x-initial-edge` is required to model an initially asserted asynchronous
reset in Verilator. The earlier default two-state reset trial is retained as a
failure; no expected answer or hardware behavior was changed to make it pass.
This test does not qualify physical pads or an external-memory controller.

## Full-core physical checkpoints

The current physical stage is `build/m6_core_physical_v4`. Its separate-phase
design passed synthesis at `runs/synth_v2/08-checker-yosyssynthchecks` and PDN
at `runs/floorplan_v1/12-openroad-generatepdn`. The stage was initially created
with a 20-ns memory period; `constraints_v1/soc.sdc` and a `CLOCK_PERIOD=40`
override select the current 12.5-MHz system candidate. The current preparation
script uses that 40-ns memory period by default. A fresh synthesis-through-PDN
reproduction therefore uses:

```sh
bash scripts/m6_run_physical.sh build/m6_physical_repro floorplan_repro \
  --to OpenROAD.GeneratePDN
```

Check strict synthesis diagnostics, all 292 placed SRAM macros, and zero
power-grid connectivity violations before proceeding. The die rectangle is
9,100 × 9,900 µm; it excludes a physical padframe and the serial host wrapper.
Synthesis-only area is not final routed area.

The earlier direct-clock-as-phase physical stage, `build/m6_core_physical_v3`,
is superseded. Its successful initial global placement is retained at
`runs/placement_v4/01-openroad-globalplacement`. It resumed the earlier
I/O-placement checkpoint with timing- and routability-driven *initial global
placement* disabled. Those settings do not remove subsequent repair, routing,
STA or DRC requirements. The preceding inflation-driven placement trial did
not converge and was stopped with its evidence retained.

Detailed placement before CTS is retained at
`runs/clocks_v1/06-openroad-detailedplacement`. The original CTS used an
incorrect generated-clock root after output-port buffering; later automatic
CTS trials also followed the clock's SRAM phase-data branches. None of these
trials is timing qualification. Current constraints select the divider Q
directly and stop clock propagation only at data branches; setup/hold data
arcs remain enabled. The M6 flow additionally selects the four real CTS nets
explicitly because the pinned tool's automatic block-input discovery also
includes SRAM data pins. The installed tool files are not modified. The later
separate-phase RTL avoids that direct clock-as-data topology. Do not resume
the old placement/CTS state as though it implements the revised design.

The next current-design stage did not start: `placement_v1_console.log` records
the storage guard rejection. After byte-identical view consolidation, about
7.4 GiB remained, below the runner's 10-GiB minimum. Provision more working
space before continuing; 30 GiB free is a practical recommended reserve.
With storage available, resume the current PDN checkpoint in a fresh run tag:

```sh
bash scripts/m6_run_physical.sh build/m6_core_physical_v4 placement_repro \
  --with-initial-state /work/runs/floorplan_v1/12-openroad-generatepdn/state_out.json \
  --from Odb.RemovePDNObstructions --to OpenROAD.GlobalPlacement \
  -c CLOCK_PERIOD=40 -c PNR_SDC_FILE=/work/constraints_v1/soc.sdc \
  -c SIGNOFF_SDC_FILE=/work/constraints_v1/soc.sdc \
  -c PL_TIME_DRIVEN=false -c PL_ROUTABILITY_DRIVEN=false
```

This resumes only placement. It cannot establish routed timing or M6 closure.

Snapshot constraints before every changed-constraint experiment:

```sh
python3 -m scripts.m6_stage_constraints build/m6_physical_repro/constraints_repro
```

Pass the snapshot as both `PNR_SDC_FILE` and `SIGNOFF_SDC_FILE`. Use a fresh
run tag and `--with-initial-state` for every resumed stage. The physical runner
limits each invocation to 1,800 s, eight CPUs and 12 GiB RAM and requires at
least 10 GiB free before starting. CLI path overrides are raw paths, not JSON
quoted strings. A one-element PDN connection list needs a trailing comma:

```text
-c 'PDN_MACRO_CONNECTIONS=.*u_sram vdd vss vdd vss,'
```

Each run retains its resolved configuration, commands, input/output state,
logs and views. `scripts/m6_deduplicate_views.py` can replace byte-identical
copies in its explicit list of completed runs with hard links. It checks full
contents before and after replacement and preserves every path. Such runs
must remain immutable; the physical runner rejects existing run tags.

## Evidence checks

The collectors read the selected retained paths, not a new reproduction trial.
After intentionally changing M6 source or selecting new results, regenerate
both JSON ledgers, then run their check modes:

```sh
python3 -m scripts.m6_preflight_evidence --check docs/m6_preflight_evidence.json
python3 -m scripts.m6_port_evidence --check docs/m6_port_evidence.json
python3 -m scripts.audit_m5_startup
git diff --check
```

An evidence-collector pass establishes consistency, not M6 closure. Routed
timing, public integration DRC/LVS, physical chip interfaces and scoped
activity-qualified PPA must be established separately.
