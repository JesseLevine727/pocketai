"""Audit the bounded single-clock M6 experiments; never certify full M6."""
import argparse
import json
from pathlib import Path

from scripts.m6_preflight_evidence import ROOT, digest

CORNERS = ("min_ff_n40C_1v95", "nom_tt_025C_1v80", "max_ss_100C_1v60")


def physical_summary(metrics):
    # Access required keys directly: absent checks are not zero violations.
    names = ("timing__setup__ws", "timing__setup__tns", "timing__hold__ws",
             "timing__hold__tns", "design__max_slew_violation__count",
             "design__max_cap_violation__count")
    result = {"corners": {c: {n: metrics[n+"__corner:"+c] for n in names} for c in CORNERS}}
    result.update({n: metrics[n] for n in names})
    for name in ("route__drc_errors", "design__power_grid_violation__count",
                 "antenna__violating__nets", "antenna__violating__pins",
                 "timing__unannotated_net_filtered__count"):
        result[name] = metrics[name]
    result["qualification"] = "UNQUALIFIED_PROBE_NOT_FULL_SYSTEM"
    return result


def collect():
    artifacts = {}
    def record(relative):
        path = ROOT / relative
        artifacts[relative] = digest(path)
        return path
    def read(relative):
        return json.loads(record(relative).read_text())
    def tree(relative, suffixes):
        for path in sorted((ROOT/relative).rglob("*")):
            if path.is_file() and path.suffix in suffixes and "obj" not in path.parts:
                record(str(path.relative_to(ROOT)))
    baseline = read("docs/m5_startup_evidence.json")
    assert baseline["status"] == "PASS"
    mapping = read("build/m6_memory_map_v2/mapping.json")
    assert mapping["total_macros"] == 292 and len(mapping["memory_instances"]) == 47
    screen = read("build/m6_memory_screen_v1/screen.json")
    for name, row in screen["artifacts"].items():
        assert digest(record("build/m6_memory_screen_v1/"+name)) == row["sha256"]
    assembly = "build/m6_portable_1x_candidate_v1/"
    for line in record(assembly+"inputs.sha256").read_text().splitlines():
        sha, path = line.split(maxsplit=1)
        assert digest(record(path)) == sha, path
    for name in ("portable.v", "portable.json", "run.log"):
        record(assembly+name)
    assert "Found and reported 0 problems." in (ROOT/assembly/"run.log").read_text()
    assertion = read("build/m6_portable_1x_assertions_v1/consumer_manifest.json")
    assert assertion["input_sha256"] == digest(ROOT/assembly/"portable.v")
    assert assertion["output_sha256"] == digest(record("build/m6_portable_1x_assertions_v1/portable.v"))
    assert len(assertion["assertion_targets"]) == 4 and assertion["formal_proof"] is False
    expected = "M5 ACTUAL DUAL-IBEX ACCELERATOR PASS boots=2 packet_abort=1 cycles=16477049 pte_reads=418 data_reads=20224 writes=132606"
    for run in ("m6_system_1x_candidate_v1", "m6_system_1x_assertions_v1"):
        prefix = "build/"+run+"/"
        manifest = read(prefix+"manifest.json")
        for path, sha in manifest["inputs"].items():
            assert digest(record(path)) == sha == baseline["artifacts"][path]
        for name in ("test.cc", "test.bin", "build.log"):
            record(prefix+name)
        log = record(prefix+"run.log").read_text()
        assert log.count(expected) == 1 and log.count("independent_words=9633 PASS") == 2
        assert "M5 ACCEL COMPONENT LIFECYCLE PASS cases=14" in log and "FAIL" not in log
    for run in ("m6_sram_1x_binary_test_v3", "m6_sram_1x_onehot_test_v1"):
        prefix = "build/"+run+"/"
        for line in record(prefix+"inputs.sha256").read_text().splitlines():
            sha, path = line.split(maxsplit=1)
            assert digest(record(path)) == sha
        record(prefix+"build.log")
        log = record(prefix+"run.log").read_text()
        assert log.count("M6 SRAM 1X PASS") == 3 and log.count("M6 SRAM 1X RETENTION PASS") == 3
        assert "M6 SINGLE-CLOCK STORAGE CONTRACT PASS" in log and "FAIL" not in log
    trials = {
        "binary_default_cts": ("m6_bank_1x_probe_v2", "route_v2", "32-openroad-stapostpnr"),
        "binary_clock_repair": ("m6_bank_1x_probe_v2", "clock_repair_v2", "22-openroad-stapostpnr"),
        "onehot_return": ("m6_bank_1x_onehot_v1", "route_v1", "55-openroad-stapostpnr"),
    }
    physical = {}
    for label, (stage, run, step) in trials.items():
        prefix = "build/"+stage+"/"
        manifest = read(prefix+"manifest.json")
        assert manifest["macro_count"] == 8 and manifest["clock_mhz_target"] == 100
        # Compare staged RTL/Liberty/SDC with their original input identities.
        # Generator changes after staging do not rewrite the retained config.
        for path, sha in manifest["sources"].items():
            assert digest(record(prefix+Path(path).name)) == sha
        config = read(prefix+"runs/"+run+"/resolved.json")
        assert config["CLOCK_PERIOD"] == 10 and config["STA_CORNERS"] == list(CORNERS)
        record(prefix+run+"_console.log")
        state = read(prefix+"runs/"+run+"/"+step+"/state_out.json")
        physical[label] = physical_summary(state["metrics"])
        physical[label]["source"] = prefix+"runs/"+run+"/"+step
        tree(prefix+"runs/"+run+"/"+step, {".rpt", ".json"})
        for field in ("odb", "sdc", "spef", "sdf", "nl", "pnl"):
            values = state.get(field)
            values = list(values.values()) if isinstance(values, dict) else [values]
            for path in values:
                if path is not None:
                    assert path.startswith("/work/")
                    record(prefix+path.removeprefix("/work/"))
    figures = read("docs/figures/m6/manifest.json")
    for path, sha in figures["sources"].items():
        assert digest(record(path)) == sha
    for name, row in figures["outputs"].items():
        assert digest(record("docs/figures/m6/"+name)) == row["sha256"]
        assert digest(record(row["source"])) == row["sha256"]
    extracts = read("docs/evidence/m6_100mhz/manifest.json")
    for name, row in extracts["files"].items():
        assert digest(record("docs/evidence/m6_100mhz/"+name)) == row["sha256"]
        assert digest(record(row["source"])) == row["sha256"]
    for directory in ("asic/m6", "tests/m6"):
        tree(directory, {".py", ".sv", ".v", ".tcl", ".sdc", ".json"})
    for pattern in ("m6_*.py", "m6_*.sh"):
        for path in sorted((ROOT/"scripts").glob(pattern)):
            record(str(path.relative_to(ROOT)))
    return {"schema": 1, "status": "SINGLE_CLOCK_FUNCTIONAL_PASS_PHYSICAL_CLOSURE_OPEN",
            "m6_pass": False, "target_system_mhz": 100,
            "acceptance": {"asic_100mhz": "REQUIRED", "wns_target_ns": 0.25,
                           "wns_stretch_ns": 0.5, "electrical_checks_waived": False},
            "single_clock_functional": {"full_test_cycles": 16477049, "cycle_delta": 0,
                "boots": 2, "independent_words_per_boot": 9633, "lifecycle_cases": 14,
                "consumer_assertion_module_types": 4, "formal_equivalence": False,
                "macro_count": 292, "logical_arrays": 47, "firmware_or_oracle_changes": False,
                "test_harness": "Retained two-phase harness; candidate SRAM samples system clock only",
                "general_1w2r_equivalence": False, "chip_loader_requalified_with_1x": False},
            "memory_screen": screen["macros"], "physical_probes": physical,
            "onehot_candidate": {"local_contract_pass": True, "full_system_test": "NOT_RUN",
                                  "promoted": False, "reason": "No worst-setup improvement"},
            "figures": figures,
            "remaining": ["SRAM clock/input slew and output-library default transition review",
                          "100-MHz banked-memory setup and antenna closure",
                          "durable disk space: full-core guard 10 GiB; 30 GiB recommended",
                          "full-system 1x physical integration, locality, CTS, route and all-corner checks",
                          "1x chip loader, external-memory/pad integration and useful throughput qualification",
                          "final routed ASIC figure, PPA report and release"],
            "artifacts": dict(sorted(artifacts.items()))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", type=Path)
    group.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = collect()
    encoded = json.dumps(result, indent=2, sort_keys=True)+"\n"
    if args.check:
        assert json.loads(args.check.read_text()) == result, "100-MHz experiment ledger differs"
        print("M6 100-MHZ EXPERIMENT EVIDENCE PASS; M6 PHYSICAL CLOSURE REMAINS OPEN")
    elif args.output:
        assert args.output.resolve() == ROOT/"docs/m6_100mhz_evidence.json"
        args.output.write_text(encoded)
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
