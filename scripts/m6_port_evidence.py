"""Collect full-port functional/synthesis/floorplan evidence, not M6 closure."""
import argparse
import json
from pathlib import Path
import re

from scripts.m6_preflight_evidence import ROOT, digest
from scripts.m6_block_areas import extract_asic, extract_fpga
from scripts.m6_check_phase_netlist import check as check_phase_netlist


def collect():
    artifacts={}
    def record(relative):
        path=ROOT/relative
        artifacts[relative]=digest(path)
        return path
    def read(relative): return json.loads(record(relative).read_text())
    baseline=read("docs/m5_startup_evidence.json")
    assert baseline["status"]=="PASS"
    stage=read("build/m6_elaboration_v5/manifest.json")
    for relative,entry in stage["sources"].items():
        assert digest(ROOT/entry["source"])==entry["sha256"]
        expected=stage["syntax_changes"].get(relative,stage["technology_bindings"].get(relative,entry))
        assert digest(ROOT/"build/m6_elaboration_v5"/relative)==expected["sha256"]
    for name in ("normalized.json","converted.v","conversion.stderr","elaboration.log"):
        record("build/m6_elaboration_v5/"+name)
    mapping=read("build/m6_memory_map_v2/mapping.json")
    assert mapping["total_macros"]==292 and len(mapping["memory_instances"])==47
    for name in ("mapped.json","wrappers.sv"): record("build/m6_memory_map_v2/"+name)
    for name in ("portable.v","portable.json","run.log"): record("build/m6_portable_assemble_v5/"+name)
    assert "Found and reported 0 problems." in (ROOT/"build/m6_portable_assemble_v5/run.log").read_text()
    adapter=record("build/m6_adapter_test_v5/run.log").read_text()
    assert "M6 MEMORY PHASE CONTRACT PASS" in adapter and adapter.count("M6 SRAM RESET RETENTION PASS")==3
    record("build/m6_adapter_test_v5/build.log")
    system=read("build/m6_system_test_v3/manifest.json")
    for path,sha in system["inputs"].items():
        assert digest(ROOT/path)==sha==baseline["artifacts"][path]
    for name in ("test.cc","test.bin","build.log"): record("build/m6_system_test_v3/"+name)
    log=record("build/m6_system_test_v3/run.log").read_text()
    expected="M5 ACTUAL DUAL-IBEX ACCELERATOR PASS boots=2 packet_abort=1 cycles=16477049 pte_reads=418 data_reads=20224 writes=132606"
    assert log.count(expected)==1 and log.count("independent_words=9633 PASS")==2
    assert "M5 ACCEL COMPONENT LIFECYCLE PASS cases=14" in log and "FAIL" not in log
    host=record("build/m6_host_test_v2/run.log").read_text()
    assert "M6 HOST TRANSPORT PASS masks=16 malformed=2 busy_reject=1 uart_bytes=2 writes=17 reads=26" in host
    record("build/m6_host_test_v2/build.log")
    chip_stage=read("build/m6_chip_logic_v2/manifest.json")
    for path,sha in chip_stage["sources"].items():
        assert digest(ROOT/path)==sha
        record(path)
    for path in sorted((ROOT/"build/m6_chip_logic_v2").glob("*.sv")):
        record(str(path.relative_to(ROOT)))
    for name in ("build.log","smoke.elf","smoke.bin"): record("build/m6_chip_test_v3/"+name)
    chip=record("build/m6_chip_test_v3/run.log").read_text()
    assert "M6 CHIP LOADER PASS firmware_bytes=188 spi_frames=208 harts=2 fast_mul=2 uart_bytes=2 memory_half_ticks=695760" in chip
    assert "FAIL" not in chip
    physical="build/m6_core_physical_v4/"
    for name in ("config.json","manifest.json","soc.sdc","pa_m6_soc.sv","portable.v",
                 "floorplan_v1_console.log","synth_v2_console.log", "phase_netlist_v2.json",
                 "constraints_v1/soc.sdc", "constraints_v1/clock_data_boundaries.tcl",
                 "constraints_v1/manifest.json"):
        record(physical+name)
    synth=read(physical+"runs/synth_v2/06-yosys-synthesis/state_out.json")["metrics"]
    assert synth["synthesis__check_error__count"]==synth["design__instance_unmapped__count"]==0
    for name in ("pre_synth_chk.rpt","chk.rpt","stat.json","stat.rpt"):
        record(physical+"runs/synth_v2/06-yosys-synthesis/reports/"+name)
    state=read(physical+"runs/floorplan_v1/12-openroad-generatepdn/state_out.json")
    config=read(physical+"runs/floorplan_v1/12-openroad-generatepdn/config.json")
    assert config["CLOCK_PERIOD"] == 40
    assert state["metrics"]["design__power_grid_violation__count"]==0
    assert state["metrics"]["design__instance__count__macros"]==292
    assert "Less than 10 GiB free" in record(physical+"placement_v1_console.log").read_text()
    storage=record(physical+"storage_gate_v1.txt").read_text().splitlines()
    available_kib=int(storage[1].split()[3])
    assert available_kib < 10*1024*1024
    for field in ("nl","pnl","def","odb","sdc"):
        path=state[field]
        assert path.startswith("/work/")
        record(physical+path.removeprefix("/work/"))
    for name in ("vdd-grid-errors.rpt", "vss-grid-errors.rpt"):
        record(physical+"runs/floorplan_v1/12-openroad-generatepdn/"+name)
    previous="build/m6_core_physical_v3/"
    for name in ("runs/clocks_v6/01-m6-cts/cts.rpt",
                 "runs/clocks_v6/01-m6-cts/state_out.json", "timing_clocked_v7.log",
                 "routing_v1_console.log", "routing_v1_stop.md"):
        record(previous+name)
    for name in ("portable.v", "portable.json"):
        record("build/m6_portable_assemble_v4/"+name)
    # The std-cell library sum is synthesis-only. Actual placement may add cells.
    netlist=record(physical+"runs/synth_v2/06-yosys-synthesis/pa_m6_soc.nl.v.json")
    phase=check_phase_netlist(json.loads(netlist.read_text()))
    assert phase["independent_phase_registers"]==47
    retained_phase=read(physical+"phase_netlist_v2.json")
    assert retained_phase == dict(phase, input_sha256=digest(netlist))
    liberty=record("build/m6_pdks/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib")
    macro_lef=record("build/m6_sram512_v1/sram22_512x32m4w8.lef")
    asic_area=extract_asic(netlist,liberty,macro_lef)
    assert abs(float(asic_area["total"]["standard_cell_um2"])-synth["design__instance__area"])<0.01
    fpga_area=extract_fpga(record("build/m6_fpga_blocks_v2/hierarchy.rpt"))
    record("build/m6_fpga_blocks_v2/full.rpt")
    record("build/m6_fpga_blocks_v2/primitives.tsv")
    record("build/m6_fpga_area_sources_v2/manifest.json")
    for directory in ("asic/m6","tests/m6"):
        for path in sorted((ROOT/directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts: record(str(path.relative_to(ROOT)))
    for pattern in ("m6_*.py","m6_*.sh"):
        for path in sorted((ROOT/"scripts").glob(pattern)): record(str(path.relative_to(ROOT)))
    return dict(schema=1,status="PORT_FUNCTIONAL_SYNTHESIS_PDN_PASS_M6_INCOMPLETE",m6_pass=False,
        snapshot_scope="Historical 2x port; new single-clock experiments in docs/m6_100mhz_evidence.json",
        acceptance=dict(asic_100mhz="REQUIRED_REINSTATED_2026_09_08",board_watts="USER_DEFERRED",
                        sram_internal_verification="USER_DEFERRED_THIRD_PARTY_IP_RESEARCH_ONLY",
                        missing_sram_leakage="USER_DEFERRED_UNAVAILABLE_NOT_ZERO"),
        mapping=mapping,
        functional=dict(status="PASS_RTL_NOT_TIMING_SIMULATION",full_test_cycles=16477049,
            full_boots=2,packet_abort=1,lifecycle_cases=14,independent_words_per_boot=9633,
            oracle_changes=False,firmware_changes=False,
            memory_adapter_cases=3,reset_retention_cases=3,
            host_test="PASS_SPI_MASKS_MALFORMED_BUSY_BACKPRESSURE_UART",
            chip_loader="PASS_SPI_SRAM_READBACK_TWO_ACTUAL_FAST_MULTIPLY_HARTS_UART",
            chip_reset_model="Verilator --x-initial-edge models X-to-low initial asynchronous reset edges",
            exclusions="pad/package timing and real external-memory interface not tested"),
        synthesis=synth,phase_netlist=phase,asic_synthesis_area=asic_area,fpga_synthesis_area=fpga_area,
        execution=dict(status="WAITING_FOR_STORAGE",available_kib_at_gate=available_kib,
                       minimum_free_gib=10,recommended_free_gib=30,
                       recommendation_is_measured_peak=False,
                       evidence_paths_and_contents_preserved=True),
        previous_topology=dict(status="SUPERSEDED_NOT_CURRENT_RTL_TIMING_QUALIFICATION",
            system_clock_mhz_candidate=25, placement_and_four_tree_cts_completed=True,
            setup_timing_pass=False, postcts_repair_stopped_after_plateau=True,
            direct_clock_as_phase_data=True),
        floorplan=dict(status="PLACED_MACROS_PDN_CONNECTIVITY_PASS_NOT_ROUTED",
            memory_clock_mhz_candidate=25,system_clock_mhz_candidate=12.5,
            achieved_clock_mhz=None,metrics={k:v for k,v in state["metrics"].items()
                if k.startswith(("design__instance","design__die","design__core","design__power_grid"))}),
        remaining=["routed timing closure and constraint coverage", "full-core public DRC and integration LVS",
                   "physical pad/chip integration", "activity-qualified partial power and throughput reporting",
                   "final evidence audit and release"],artifacts=dict(sorted(artifacts.items())))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check",type=Path)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    value=collect()
    # Decimal area values are emitted with enough precision to recheck tool sums.
    canonical=json.loads(json.dumps(value,default=float))
    assert not (args.check and args.output)
    if args.output:
        assert args.output.resolve() == ROOT / "docs/m6_port_evidence.json"
        args.output.write_text(json.dumps(canonical,indent=2,sort_keys=True)+"\n")
    elif args.check:
        assert json.loads(args.check.read_text())==canonical,"port ledger differs from primary artifacts"
        print("M6 PORT EVIDENCE PASS; this is not M6 closure")
    else: print(json.dumps(canonical,indent=2,sort_keys=True))


if __name__=="__main__": main()
