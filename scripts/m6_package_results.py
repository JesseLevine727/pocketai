"""Retain small primary M6 result extracts in Git; full EDA runs stay in build/."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "docs/evidence/m6_100mhz"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    sources = {
        "system_binary.log": "build/m6_system_1x_candidate_v1/run.log",
        "system_assertions.log": "build/m6_system_1x_assertions_v1/run.log",
        "consumer_manifest.json": "build/m6_portable_1x_assertions_v1/consumer_manifest.json",
        "memory_binary.log": "build/m6_sram_1x_binary_test_v3/run.log",
        "memory_onehot.log": "build/m6_sram_1x_onehot_test_v1/run.log",
        "liberty_screen.json": "build/m6_memory_screen_v1/screen.json",
    }
    trials = {
        "binary_default": "build/m6_bank_1x_probe_v2/runs/route_v2/32-openroad-stapostpnr",
        "binary_repair": "build/m6_bank_1x_probe_v2/runs/clock_repair_v2/22-openroad-stapostpnr",
        "onehot": "build/m6_bank_1x_onehot_v1/runs/route_v1/55-openroad-stapostpnr",
    }
    for label, prefix in trials.items():
        sources[label+"_state.json"] = prefix+"/state_out.json"
        sources[label+"_summary.rpt"] = prefix+"/summary.rpt"
    sources["binary_repair_ss_checks.rpt"] = trials["binary_repair"]+"/max_ss_100C_1v60/checks.rpt"
    sources["binary_repair_resolved.json"] = "build/m6_bank_1x_probe_v2/runs/clock_repair_v2/resolved.json"
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for name, source in sources.items():
        path = ROOT/source
        if (DESTINATION/name).exists():
            assert digest(DESTINATION/name) == digest(path), "retain existing result extracts"
        else:
            shutil.copyfile(path, DESTINATION/name)
    manifest = {"schema": 1, "status": "PRIMARY_EXTRACTS_NOT_M6_CLOSURE",
                "note": "Byte-identical selected logs/metrics; full configs, netlists, SPEF and all-corner reports retained in build/ and hashed in the experiment ledger.",
                "files": {name: {"source": source, "sha256": digest(ROOT/source)}
                          for name, source in sources.items()}}
    encoded = json.dumps(manifest, indent=2, sort_keys=True)+"\n"
    if (DESTINATION/"manifest.json").exists():
        assert (DESTINATION/"manifest.json").read_text() == encoded
    else:
        (DESTINATION/"manifest.json").write_text(encoded)
    print("M6 small primary result extracts packaged without modifying retained runs")


if __name__ == "__main__":
    main()
