"""Package immutable primary extracts from the post-storage M6 memory pass."""
import json
from pathlib import Path
import shutil

from scripts.m6_package_results import ROOT, digest


def main():
    destination = ROOT / "docs/evidence/m6_memory_resumed_v2"
    prefix = "build/m6_bank_1x_probe_v2/runs/local_leaf_v2/22-openroad-stapostpnr/"
    sources = {
        "electrical_screen.json": "build/m6_electrical_screen_v1/electrical.json",
        "local_leaf_state.json": prefix+"state_out.json",
        "local_leaf_summary.rpt": prefix+"summary.rpt",
        "local_leaf_ss_checks.rpt": prefix+"max_ss_100C_1v60/checks.rpt",
        "local_leaf_resolved.json": "build/m6_bank_1x_probe_v2/runs/local_leaf_v2/resolved.json",
        "local_leaf_topology.log": "build/m6_bank_1x_probe_v2/local_leaf_v2_topology.log",
        "failed_leaf_disconnected.txt": "build/m6_bank_1x_probe_v2/runs/local_leaf_v1/15-odb-reportdisconnectedpins/full_disconnected_pins_table.txt",
        "chip_1x.log": "build/m6_chip_1x_test_v2/run.log",
        "chip_1x_manifest.json": "build/m6_chip_1x_logic_v2/single_clock_manifest.json",
    }
    destination.mkdir(parents=True, exist_ok=True)
    for name, source in sources.items():
        target = destination/name
        if target.exists():
            assert digest(target) == digest(ROOT/source), "retain previous evidence"
        else:
            shutil.copyfile(ROOT/source, target)
    manifest = {"schema": 1, "status": "PRIMARY_EXTRACTS_NOT_M6_CLOSURE",
        "files": {name: {"source": source, "sha256": digest(ROOT/source)} for name, source in sources.items()}}
    encoded = json.dumps(manifest, indent=2, sort_keys=True)+"\n"
    path = destination/"manifest.json"
    if path.exists():
        assert path.read_text() == encoded
    else:
        path.write_text(encoded)
    print("M6 resumed primary extracts packaged; historical package unchanged")


if __name__ == "__main__":
    main()
