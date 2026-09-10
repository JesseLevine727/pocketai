"""Bind bounded memory-closure trials to primary artifacts; never certify M6."""
import argparse
import json
from pathlib import Path

from scripts.m6_100mhz_evidence import CORNERS, physical_summary
from scripts.m6_contract_evidence import check_95_constraints
from scripts.m6_preflight_evidence import ROOT, digest

STAGE = ROOT / "build/m6_contract_probe_v1"
ROUTED = ("local_inputs_95_v2", "allcorner_hold_95_v1", "close_halo_95_v1",
          "rcx_repair_route_95_v3", "rcx_direct_route_95_v1", "rcx_clock_route_95_v1",
          "rcx_timing_route_95_v2", "selective_driver_route_95_v1",
          "local_clock_ndr_route_95_v2", "boundary_drive_route_95_v1",
          "read_chain_route_95_v1")
FAILED = {"rcx_repair_route_95_v1": "GRT-0226",
          "rcx_repair_route_95_v2": "GRT-0226",
          "rcx_timing_route_95_v1": "dbAccessPoint::destroy"}


def collect():
    artifacts = {}

    def record(path):
        path = Path(path).resolve()
        relative = str(path.relative_to(ROOT))
        artifacts[relative] = digest(path)
        return path

    def read(path):
        return json.loads(record(path).read_text())

    def mounted(path):
        for prefix, local in (("/candidate/", STAGE),
                              ("/work/", ROOT/"build/m6_bank_1x_probe_v2"),
                              ("/m6_flow/", ROOT/"asic/m6")):
            if path.startswith(prefix):
                return local/path.removeprefix(prefix)
        raise ValueError("unreviewed artifact mount: " + path)

    check_95_constraints(record(ROOT/"asic/m6/bank_probe.sdc").read_text(),
                         record(ROOT/"asic/m6/bank_probe_95.sdc").read_text())
    physical = {}
    for run in ROUTED:
        directory = STAGE/"runs"/run
        config = read(directory/"resolved.json")
        if config["CLOCK_PERIOD"] != 10.526315789474 or config["STA_CORNERS"] != list(CORNERS):
            raise ValueError("95-MHz/all-corner contract changed")
        states = list(directory.glob("*-openroad-stapostpnr/state_out.json"))
        if len(states) != 1:
            raise ValueError("one completed extracted all-corner result required")
        state = read(states[0])
        physical[run] = physical_summary(state["metrics"])
        physical[run]["source"] = str(states[0].parent.relative_to(ROOT))
        for field in ("odb", "sdc", "spef", "nl", "pnl"):
            paths = state[field]
            for path in paths.values() if isinstance(paths, dict) else [paths]:
                record(mounted(path))
        for corner in CORNERS:
            record(states[0].parent/corner/"checks.rpt")
            record(states[0].parent/corner/"min.rpt")
            record(states[0].parent/corner/"max.rpt")
        record(STAGE/(run+"_console.log"))
    failures = {}
    for run, signal in FAILED.items():
        path = record(STAGE/(run+"_console.log"))
        if signal not in path.read_text() or list((STAGE/"runs"/run).glob("*-openroad-stapostpnr/state_out.json")):
            raise ValueError("retained failure signal/state changed")
        failures[run] = {"signal": signal, "routed_result_available": False}
    diagnostics = {}
    for name in ("m6_locality_direct_v2", "m6_locality_clock_v1", "m6_locality_timing_v1"):
        directory = ROOT/"build"/name
        value = read(directory/"diagnostic.json")
        for filename, expected in value["artifacts"].items():
            if digest(record(directory/filename)) != expected:
                raise ValueError("diagnostic artifact changed")
        from scripts.m6_locality_diagnostic import classify_constant_resets
        from scripts.m6_report_contract_boundary import evaluate_rows
        import csv
        with (directory/"pins.tsv").open() as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
        with (directory/"neighbours.tsv").open() as stream:
            neighbours = list(csv.DictReader(stream, delimiter="\t"))
        envelope = read(STAGE/"manifest.json")["contract"]["envelope"]
        observed = classify_constant_resets(rows, neighbours, evaluate_rows(rows, envelope))
        if observed != value["corners"]:
            raise ValueError("boundary diagnosis differs from primary pin data")
        diagnostics[name] = observed
    binding = read(ROOT/"build/m6_corner_binding_v2/binding.json")
    for name, expected in binding["artifacts"].items():
        if digest(record(ROOT/"build/m6_corner_binding_v2"/name)) != expected:
            raise ValueError("binding comparison artifact changed")
    for run in ("rcx_repair_95_v1", "rcx_repair_95_v2", "rcx_repair_direct_95_v1",
                "rcx_prime_95_v1", "rcx_direct_clock_95_v1", "rcx_timing_95_v1", "rcx_timing_95_v2"):
        record(STAGE/(run+"_console.log"))
        record(STAGE/(run+"_flow_sources.sha256"))
        for path in sorted((STAGE/(run+"_flow")).iterdir()):
            if path.is_file():
                record(path)
        for path in sorted((STAGE/"runs"/run).glob("*/state_out.json")):
            record(path)
    for pattern in ("scripts/m6_*.py", "scripts/m6_*.sh", "asic/m6/*.py", "asic/m6/*.tcl",
                    "tests/m6/test_*.py"):
        for path in sorted(ROOT.glob(pattern)):
            record(path)
    return {"schema": 1, "status": "MEMORY_CLOSURE_IN_PROGRESS_NOT_M6_PASS",
            "M6_PASS": False, "memory_gate_pass": False, "clock_mhz": 95,
            "physical": physical, "failed_trials": failures, "boundary_diagnostics": diagnostics,
            "corner_binding": binding["results"], "artifacts": artifacts}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output", type=Path)
    group.add_argument("--check", type=Path)
    args = parser.parse_args()
    value = collect()
    if args.output:
        args.output.write_text(json.dumps(value, indent=2, sort_keys=True)+"\n")
    elif json.loads(args.check.read_text()) != value:
        raise SystemExit("memory-closure evidence mismatch")
    print(value["status"])
