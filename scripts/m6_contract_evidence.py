"""Audit the bounded SRAM contract and 95-MHz follow-up; never certify M6."""
import argparse
import csv
import json
import math
from pathlib import Path
import re

from scripts.m6_100mhz_evidence import CORNERS, physical_summary
from scripts.m6_electrical_screen import named_group, table
from scripts.m6_memory_feasibility import groups
from scripts.m6_preflight_evidence import ROOT, digest
from scripts.m6_report_contract_boundary import evaluate_rows
from scripts.m6_sram_contract import derive_envelope, verify_patch

STAGE = "build/m6_contract_probe_v1"
TRIALS = ("matched_sta_v1", "buffered_v1", "balanced_clock_v2",
          "electrical_repair_v1", "ss_repair_route_v1", "matched_95_v1", "local_inputs_95_v2")


def check_95_constraints(original, updated):
    def commands(text):
        return "\n".join(line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#"))
    old = commands(original)
    needle = "create_clock -name sys_clk -period 10 [get_ports clk]"
    if old.count(needle) != 1 or commands(updated) != old.replace(
            needle, "create_clock -name sys_clk -period 10.526315789474 [get_ports clk]"):
        raise ValueError("only the approved clock-period change is allowed")


def collect():
    artifacts = {}

    def record(relative):
        path = ROOT / relative
        artifacts[str(relative)] = digest(path)
        return path

    def read(relative):
        return json.loads(record(relative).read_text())

    def verify_sources(value):
        for path, sha in value["sources"].items():
            assert digest(record(path)) == sha, path

    def mounted(path):
        for prefix, local in (("/work/", "build/m6_bank_1x_probe_v2/"),
                              ("/candidate/", STAGE+"/")):
            if path.startswith(prefix):
                return local+path.removeprefix(prefix)
        raise ValueError("unreviewed retained state mount: "+path)

    contract = read("build/m6_sram_contract_v1/contract.json")
    verify_sources(contract)
    envelope = contract["envelope"]
    samples = []
    for name, sha in contract["outputs"].items():
        original = record("build/m6_sram512_v1/"+name).read_text()
        updated = record("build/m6_sram_contract_v1/"+name).read_text()
        assert digest(ROOT/"build/m6_sram_contract_v1"/name) == sha
        assert digest(record(STAGE+"/"+name)) == sha
        verify_patch(original, updated, 0.35, 0.007, 0.013)
        body = named_group(original, "bus", "dout")
        samples.extend(table(next(groups(body, edge+"_transition"))) for edge in ("rise", "fall"))
    assert len(samples) == 6 and derive_envelope(samples, 0.35) == envelope
    check_95_constraints(record("asic/m6/bank_probe.sdc").read_text(),
                         record("asic/m6/bank_probe_95.sdc").read_text())
    stage = read(STAGE+"/manifest.json")
    verify_sources(stage)
    assert stage["contract"] == contract and stage["macro_count"] == 8
    baseline_stage = read("build/m6_bank_1x_probe_v2/manifest.json")
    for path, sha in baseline_stage["sources"].items():
        assert digest(record("build/m6_bank_1x_probe_v2/"+Path(path).name)) == sha
    record(STAGE+"/config.json")
    spice_dir = "build/m6_output_spice_v2/"
    spice = read(spice_dir+"sanity.json")
    verify_sources(spice)
    for name, sha in spice["artifacts"].items():
        assert digest(record(spice_dir+name)) == sha
    lines = (ROOT/spice_dir/"model_sources.sha256").read_text().splitlines()
    assert len(lines) == spice["model_tree_files_fingerprinted"] == 821
    for line in lines:
        sha, path = line.split(maxsplit=1)
        assert digest(record(path)) == sha
    expected = {(c, s, load) for c in ("ss", "tt", "ff") for s in (0.002, 0.351) for load in (0.007, 0.013)}
    assert len(spice["results"]) == 12
    assert {(r["corner"], r["ideal_internal_input_slew_ns"], r["output_load_pf"]) for r in spice["results"]} == expected
    for row in spice["results"]:
        name = f'{row["corner"]}_s{row["ideal_internal_input_slew_ns"]:g}_c{row["output_load_pf"]:g}'
        log = (ROOT/spice_dir/(name+".log")).read_text()
        for edge in ("rise", "fall"):
            value = row[edge+"_transition_ns"]
            measured = float(re.search(r"^"+edge+r"_s\s*=\s*([0-9.eE+-]+)", log, re.M)[1])*1e9
            assert math.isfinite(value) and 0 < value <= 0.35 and value == measured
    physical, states = {}, {}
    for run in TRIALS:
        run_dir = STAGE+"/runs/"+run
        config = read(run_dir+"/resolved.json")
        period = 10.526315789474 if "95" in run else 10
        assert config["CLOCK_PERIOD"] == period and config["STA_CORNERS"] == list(CORNERS)
        if "95" in run:
            assert config["PNR_SDC_FILE"] == config["SIGNOFF_SDC_FILE"] == "/m6_flow/bank_probe_95.sdc"
        record(STAGE+"/"+run+"_console.log")
        paths = list((ROOT/run_dir).glob("*-openroad-stapostpnr/state_out.json"))
        assert len(paths) == 1, run+": completed post-route STA required"
        state = read(str(paths[0].relative_to(ROOT)))
        states[run] = state
        summary = physical_summary(state["metrics"])
        for row in [summary, *summary["corners"].values()]:
            assert all(math.isfinite(v) for v in row.values() if isinstance(v, (int, float)))
        summary.update({"period_ns": period, "source_state": str(paths[0].relative_to(ROOT)),
                        "promoted": False})
        physical[run] = summary
        for path in paths[0].parent.rglob("*.rpt"):
            record(str(path.relative_to(ROOT)))
        for field in ("odb", "sdc", "spef", "sdf", "nl", "pnl", "def"):
            values = state[field]
            for path in values.values() if isinstance(values, dict) else [values]:
                assert path is not None
                record(mounted(path))
    baseline = read("build/m6_bank_1x_probe_v2/runs/clock_repair_v2/22-openroad-stapostpnr/state_out.json")
    for field in ("odb", "sdc", "spef", "nl", "pnl"):
        assert baseline[field] == states["matched_sta_v1"][field] == states["matched_95_v1"][field]
    timing_keys = ("timing__setup__ws", "timing__setup__tns", "timing__hold__ws", "timing__hold__tns")
    for corner in ("", *("__corner:"+c for c in CORNERS)):
        for key in timing_keys:
            assert baseline["metrics"][key+corner] == states["matched_sta_v1"]["metrics"][key+corner]
    # The 95-MHz run explicitly reads the new SDC, although OpenLane retains
    # the original state's SDC path in state_out. Bind both command and report.
    clk_report = next((ROOT/STAGE/"runs/matched_95_v1").glob("*-openroad-stapostpnr/max_ss_100C_1v60/clock.rpt"))
    assert "Period: 10.526316" in clk_report.read_text()
    matched95 = physical["matched_95_v1"]
    assert matched95["timing__setup__ws"] >= 0.244 and matched95["timing__hold__ws"] > 0
    assert matched95["timing__setup__tns"] == matched95["timing__hold__tns"] == 0
    for run in ("buffered_v1", "balanced_clock_v1", "balanced_clock_v2", "local_inputs_95_v1", "local_inputs_95_v2"):
        for line in record(STAGE+"/"+run+"_flow_sources.sha256").read_text().splitlines():
            sha, path = line.split(maxsplit=1)
            snapshot = STAGE+"/"+run+"_flow/"+Path(path).name if path.startswith("asic/") else path
            assert digest(record(snapshot)) == sha
    failed = record(STAGE+"/balanced_clock_v1_console.log").read_text()
    assert "ODB-0370" in failed and "dont_touch" in failed
    failed = record(STAGE+"/local_inputs_95_v1_console.log").read_text()
    assert "ODB-0370" in failed and "dont_touch" in failed
    # Complete post-route electrical coverage, distinct from setup/hold.
    boundary_dir = "build/m6_contract_boundary_ss_v1/"
    boundary = read(boundary_dir+"boundary.json")
    verify_sources(boundary)
    for name, sha in boundary["artifacts"].items():
        assert digest(record(boundary_dir+name)) == sha
    with (ROOT/boundary_dir/"pins.tsv").open() as stream:
        calculated = evaluate_rows(list(csv.DictReader(stream, delimiter="\t")), envelope)
    assert calculated == boundary["corners"] and boundary["envelope_pass"] is False
    for path in ("ss_design_repair_v1/01-openroad-repairdesignpostgrt/state_out.json",
                 "ss_design_repair_v1/resolved.json"):
        record(STAGE+"/runs/"+path)
    record(STAGE+"/ss_design_repair_v1_console.log")
    extracts = read("docs/evidence/m6_sram_contract/manifest.json")
    for name, row in extracts["files"].items():
        assert digest(record("docs/evidence/m6_sram_contract/"+name)) == row["sha256"]
        assert digest(record(row["source"])) == row["sha256"]
    for directory in ("asic/m6", "tests/m6"):
        for path in (ROOT/directory).rglob("*"):
            if path.is_file() and path.suffix in (".py", ".sv", ".tcl", ".sdc", ".json"):
                record(str(path.relative_to(ROOT)))
    for pattern in ("m6_*.py", "m6_*.sh"):
        for path in (ROOT/"scripts").glob(pattern):
            record(str(path.relative_to(ROOT)))
    return {"schema": 1, "status": "CONTRACT_TABLE_CHECK_PASS_PHYSICAL_CLOSURE_OPEN", "m6_pass": False,
        "current_acceptance": {"system_mhz": 95, "accepted_approximate_setup_margin_ns": 0.244,
            "preferred_setup_margin_ns": 0.25, "stretch_setup_margin_ns": 0.5,
            "further_margin_reductions_authorized": False, "electrical_checks_waived": False},
        "contract": contract, "spice_sanity": spice, "physical_probes": physical,
        "final_100mhz_pin_audit": boundary,
        "matched_metadata_timing_unchanged": True,
        "matched_95mhz_setup_hold_only_pass": True,
        "remaining": ["macro input slew and restricted output-load closure",
            "banked-memory electrical, antenna and all-corner timing qualification",
            "full-system physical implementation, pads/external-memory integration and useful throughput",
            "final routed ASIC figures, qualified PPA report and M6 release"],
        "artifacts": dict(sorted(artifacts.items()))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output", type=Path)
    group.add_argument("--check", type=Path)
    args = parser.parse_args()
    result = collect()
    encoded = json.dumps(result, indent=2, sort_keys=True)+"\n"
    if args.check:
        assert args.check.read_text() == encoded, "stale contract evidence"
    else:
        args.output.write_text(encoded)
    print(result["status"], "M6_PASS=False")


if __name__ == "__main__":
    main()
