"""Collect retained feasibility evidence, never an M6 closure certificate.

Run from any directory. JSON on stdout; --check verifies the saved ledger
against the local primary artifacts without rewriting it or running hardware.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def drc_result(path):
    report = ET.parse(path).getroot()
    if report.tag != "report-database" or report.find("items") is None:
        raise ValueError("missing DRC report/items, not a zero-violation result")
    items = report.findall("items/item")
    return {"top": report.findtext("top-cell"), "violation_items": len(items),
            "categories_with_violations": dict(sorted(Counter(
                item.findtext("category") for item in items).items()))}


def collect():
    artifacts = {}

    def record(relative):
        path = ROOT / relative
        artifacts[relative] = digest(path)
        return path

    def read_json(relative):
        return json.loads(record(relative).read_text())

    baseline = read_json("docs/m5_startup_evidence.json")
    assert baseline["status"] == "PASS"
    for name in ("2k_generation.log", "2k.lib", "2k.lef", "2k.v"):
        record("build/m6_macro_preflight_v1/" + name)
    full = baseline["summary"][baseline["selection"]["final_story"]]["full"]
    requests = {}
    for case in ("science", "computing", "story"):
        rows = [row for row in full if row["case"] == case and not row["trace"]]
        assert len(rows) == 3
        seconds = [row["delivered_seconds"] for row in rows]
        requests[case] = {"seconds": seconds, "mean_seconds": sum(seconds) / len(seconds),
            "output_tokens_per_request": rows[0]["output_tokens"],
            "pooled_output_tokens_per_second": sum(row["output_tokens"] for row in rows) / sum(seconds)}

    stage = read_json("build/m6_elaboration_v4/manifest.json")
    memories = read_json("build/m6_elaboration_v4/memories_checked.json")
    netlist = record("build/m6_elaboration_v4/elaborated.json")
    assert digest(netlist) == memories["netlist_sha256"]
    record("build/m6_elaboration_v4/converted.v")
    record("build/m6_elaboration_v4/conversion.stderr")
    record("build/m6_elaboration_v4/elaboration.log")

    probe = "build/m6_sram_probe_v4/runs/probe_v1/"
    state = read_json(probe + "55-openroad-irdropreport/state_out.json")
    timing = read_json(probe + "54-openroad-stapostpnr/state_out.json")
    metrics = {key: value for key, value in state["metrics"].items()
        if key.startswith(("timing__", "design__instance", "design__core__", "design__die__",
            "design__power_grid_violation", "route__drc", "antenna__"))}
    for name in ("timing__setup__ws", "timing__hold__ws"):
        assert timing["metrics"][name] == metrics[name]
    config = read_json("build/m6_sram_probe_v4/config.json")
    boundary = read_json("build/m6_sram_probe_v4/boundary_check.json")
    drc_path = record("build/m6_sram_klayout_drc_v1/drc.xml")
    drc = drc_result(drc_path)
    assert drc["top"] == "pa_m6_sram_probe"
    record("build/m6_sram_klayout_drc_v1/run.log")
    record("build/m6_pdks/sky130A/libs.tech/klayout/drc/sky130A_mr.drc")
    record(probe + "57-klayout-streamout/pa_m6_sram_probe.klayout.gds")
    for field in ("nl", "pnl", "def", "sdc", "sdf", "spef", "lib"):
        paths = timing.get(field)
        if isinstance(paths, dict):
            paths = list(paths.values())
        elif isinstance(paths, str):
            paths = [paths]
        else:
            paths = []
        for path in paths:
            assert path.startswith("/work/")
            record("build/m6_sram_probe_v4/" + path.removeprefix("/work/"))
    lvs = "build/m6_sram_klayout_lvs_v2/"
    lvs_log = record(lvs + "run.log").read_text()
    assert "ERROR : Netlists don't match" in lvs_log
    original_deck = record("build/m6_pdks/sky130A/libs.tech/klayout/lvs/sky130.lvs").read_text()
    actual_deck = record(lvs + "sky130.lvs").read_text()
    logger_line = '  "#{datetime}: Memory Usage (" + `pmap #{Process.pid} | tail -1`[10,40].strip + ") : #{msg}\\n"'
    assert original_deck.count(logger_line) == 1
    # apply_patch also normalized a final empty line; no rule text may differ.
    assert actual_deck.rstrip("\n") == original_deck.replace(
        logger_line, '  "#{datetime}: #{msg}\\n"').rstrip("\n")
    record(lvs + "extracted.cir")
    record(lvs + "lvs.lvsdb")

    for directory in ("asic/m6", "tests/m6", "build/m6_preflight_logs_v1",
                      "build/m6_sram512_v1"):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                record(str(path.relative_to(ROOT)))
    for path in sorted((ROOT / "scripts").glob("m6_*.py")):
        record(str(path.relative_to(ROOT)))
    for path in sorted((ROOT / "scripts").glob("m6_*.sh")):
        record(str(path.relative_to(ROOT)))
    for path in sorted((ROOT / "build/m6_fpga_inventory_v2").glob("*.rpt")):
        record(str(path.relative_to(ROOT)))

    return {"schema": 1, "status": "PREFLIGHT_ONLY_M6_INCOMPLETE", "m6_pass": False,
        "snapshot_scope": "Historical single-SRAM preflight; newer full-port progress is in docs/m6_port_evidence.json",
        "baseline_commit": "7405919", "artifacts": dict(sorted(artifacts.items())),
        "board_watts": {"status": "USER_DEFERRED", "value": None},
        "fpga": {"scope": "qualified full PYNQ-Z1 system; reused frozen physical measurements",
            "hardware": baseline["hardware"], "requests": requests,
            "per_block_luts": None,
            "per_block_lut_limitation": "Qualified DCP is flattened; name groups cannot recover block LUT ownership."},
        "elaboration": {"status": "PASS_NOT_ASIC_MAPPING_OR_EQUIVALENCE", "manifest": stage,
            "memory_inventory": memories},
        "sram_probe": {"scope": "one 512x32 SRAM plus registered interface, not PocketAI",
            "config": config, "boundary_metadata_check": boundary, "metrics": metrics,
            "public_klayout_drc": {**drc, "feol": True, "beol": True,
                "offgrid": True, "sram_exclude": False, "foundry_signoff": False},
            "classic_flow": "FAIL_AT_MAGIC_WRITELEF_UNRECOGNIZED_SRAM_LAYERS",
            "standalone_macro_lvs": {"status": "FAIL_NETLISTS_DO_NOT_MATCH",
                "scope": "original SRAM GDS versus supplied SPICE; public KLayout deck",
                "deck_change": "omit unavailable pmap from logging and normalize trailing blank line; extraction/comparison unchanged",
                "waiver": True, "acceptance": "USER_DEFERRED_INTERNAL_VERIFICATION_RESEARCH_ONLY"},
            "sram_leakage_data": "USER_DEFERRED_UNAVAILABLE_NOT_ZERO",
            "qualified_workload_power": None,
            "power_limitation": "Default activity only; SRAM Liberty leakage is zero/unqualified; no VSRC placement."},
        "full_system_asic": {"memory_mapping": "NOT_IMPLEMENTED", "chip_interface": "NOT_IMPLEMENTED",
            "functional_equivalence": "NOT_RUN", "pnr": "NOT_RUN", "timing_100mhz": "NOT_RUN",
            "timing_100mhz_gate": "USER_DEFERRED",
            "timing_at_declared_operating_clock": "REQUIRED_NOT_RUN",
            "declared_operating_clock_mhz": None,
            "area": None, "power": None, "throughput": None, "mpw_submission": "NONE"}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", type=Path)
    args = parser.parse_args()
    value = collect()
    if args.check:
        assert json.loads(args.check.read_text()) == value, "preflight ledger differs from retained evidence"
        print("M6 PREFLIGHT EVIDENCE MATCH; M6 REMAINS INCOMPLETE")
    else:
        print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
