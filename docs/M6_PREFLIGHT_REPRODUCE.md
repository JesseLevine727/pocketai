# M6 preflight reproduction

These commands reproduce feasibility checks, not M6 closure. Use new trial
directories; retain the existing `build/m6_*` results, including failures.
The frozen startup audit must not gain any new `build/m5_startup_*` artifacts.
No command here programs the board, runs long inference, or submits a chip.

## Pinned tools

The container digest, OpenLane version, Sky130 PDK revision, standard-cell
library, sv2v release and SRAM22 commit are in [tools.json](../asic/m6/tools.json).
The isolated host virtual environment contains OpenLane 2.3.10, Volare 0.20.6
and KLayout 0.29.12. It lives at `build/m6_tools_venv`; the PDK root is
`build/m6_pdks`. No global PDK or qualified FPGA source was changed.

Installation used `python3 -m venv build/m6_tools_venv`, followed by the venv's
`pip install openlane==2.3.10 volare==0.20.6 klayout==0.29.12`, `docker pull`
of the pinned digest, and:

```sh
build/m6_tools_venv/bin/volare enable --pdk-root "$PWD/build/m6_pdks" \
  --pdk sky130 0fe599b2afb6708d281543108caf8310912f54af
```

The official sv2v v0.0.13 Linux archive was downloaded from the URL in
`tools.json` and extracted to `build/m6_sv2v_tools/sv2v-Linux`. Its SHA-256 is
`552799a1d76cd177b9b4cc63a3e77823a3d2a6eb4ec006569288abeff28e1ff8`.
Check disk before installation: the PDK/container together occupy several GiB.
Do not delete earlier evidence to make room.

## Frozen FPGA and source elaboration

```sh
python3 -m scripts.audit_m5_startup
vivado -mode batch -source asic/m6/fpga_inventory.tcl -notrace -nojournal \
  -log /tmp/m6_fpga_inventory_repro.log -tclargs \
  build/m5_startup_data_finish_v1/m5_pynq_final.dcp build/m6_fpga_inventory_repro
python3 -m scripts.m6_stage_rtl build/m6_elaboration_repro \
  --generic-clock-gate --portable-syntax
```

From inside that fresh elaboration directory:

```sh
mapfile -t m6_sv_args < sv2v.args
timeout 180s ../m6_sv2v_tools/sv2v-Linux/sv2v "${m6_sv_args[@]}" \
  > converted.v 2> conversion.stderr
m6_image=$(jq -r .container ../../asic/m6/tools.json)
timeout 180s docker run --rm --network none \
  --mount "type=bind,src=$PWD,dst=/work" --workdir /work \
  --user "$(id -u):$(id -g)" --entrypoint yosys "$m6_image" -Q -T -p \
  'read_verilog -sv converted.v; hierarchy -check -top pa_cluster_m5_board; proc; opt_clean; memory_collect; stat; write_json elaborated.json' \
  > elaboration.log 2>&1
```

Back at the repository root:

```sh
python3 -m scripts.m6_memory_inventory build/m6_elaboration_repro/elaborated.json \
  > build/m6_elaboration_repro/memories_checked.json
```

The retained successful elaboration is `build/m6_elaboration_v4`. Earlier
Synlig/sv2v trials are retained; they exposed the packed-pattern frontend issue.
The memory inventory rejects unresolved or explicitly opaque modules. It is
not SRAM mapping, formal equivalence, or a memory-latency qualification.

## Single SRAM and physical checks

The original macro download is `build/m6_sram512_v1`; the fetch command was:

```sh
bash scripts/m6_fetch_sram.sh build/m6_sram512_v1 sram22_512x32m4w8
```

Use another directory if downloading again. The probe runner expects that
original pinned download directory and a populated local PDK/container.
The fourth retained probe was run with:

```sh
M6_SRAM_ADD_BOUNDARY=1 bash scripts/m6_run_sram_probe.sh build/m6_sram_probe_v4
```

Do not rerun over `v4`; choose a new `m6_` name. The runner limits OpenLane to
900 s, eight CPUs and 12 GiB RAM, and stops only its named container on timeout.
The design reached routed/extracted timing and connected PDN, then **failed**
at `Magic.WriteLEF`. Do not disable the error checker and call that a pass.
The original and metadata-only boundary GDS copies are both retained.

The separate public KLayout DRC used the emitted **KLayout** GDS, not Magic's
partially interpreted SRAM. Create a new output directory and mount it as
`/work`, the retained `57-klayout-streamout` directory read-only as `/input`,
and `build/m6_pdks` read-only as `/pdk` in the pinned container. The invocation
was:

```sh
klayout -b -r /pdk/sky130A/libs.tech/klayout/drc/sky130A_mr.drc \
  -rd input=/input/pa_m6_sram_probe.klayout.gds -rd top_cell=pa_m6_sram_probe \
  -rd report=/work/drc.xml -rd feol=true -rd beol=true -rd offgrid=true \
  -rd sram_exclude=false -rd thr=8
```

The run was bounded to 300 s with the same eight-CPU/12-GiB limits; it completed
and reported zero violation items. Results are in
`build/m6_sram_klayout_drc_v1`. Enabled public-rule coverage is not foundry
signoff; the report preserves that distinction.

Standalone SRAM LVS used the original macro GDS and SPICE mounted read-only
at `/input`. The public deck first failed because its logger invokes `pmap`,
which is absent from the container. The second run copied that deck into its
new output directory and changed only its logger's returned string to
`"#{datetime}: #{msg}\n"`. The evidence collector verifies that exact one-line
difference. No device/extraction/comparison rule changed. Its invocation was:

```sh
klayout -b -r /work/sky130.lvs -rd input=/input/sram22_512x32m4w8.gds.gz \
  -rd schematic=/input/sram22_512x32m4w8.spice -rd report=/work/lvs.lvsdb \
  -rd target_netlist=/work/extracted.cir -rd run_mode=deep -rd lvs_sub=vss -rd thr=8
```

This run was also bounded to 300 s. It finished with exit code 1 and
`ERROR : Netlists don't match`. The extracted netlist, database and modified
logging-only deck are retained in `build/m6_sram_klayout_lvs_v2`. This is a
failed comparison, not a waived or completed LVS gate.

## Evidence and report checks

`docs/m6_preflight_evidence.json` is generated from the retained paths named
inside `scripts/m6_preflight_evidence.py`. It hashes the source/configuration,
macros, SDC/netlists/RC views, timing states, GDS and DRC/LVS artifacts; it also
copies the exact selected FPGA measurements and probe metrics into the ledger.
It permanently labels the current result `PREFLIGHT_ONLY_M6_INCOMPLETE`.
It cannot issue an M6 PASS.

```sh
python3 -m scripts.m6_preflight_evidence --check docs/m6_preflight_evidence.json
build/m6_tools_venv/bin/python -m unittest discover -s tests/m6 -v
python3 -m scripts.audit_m5_startup
```

The prose audit uses the installed IEEE-writing skill:

```sh
python3 /home/elfo/.codex/skills/humanize-ieee-papers/scripts/audit_draft.py docs/PPA_REPORT.md
```

These tests validate the preflight helpers and evidence boundary. They do not
substitute for the pending full-system port and chip verification.
