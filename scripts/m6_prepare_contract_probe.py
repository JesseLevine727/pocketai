"""Stage a fresh probe using the reviewed restricted output contract."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from scripts.m6_memory_feasibility import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source, output = args.contract.resolve(), args.output.resolve()
    if any(p.parent != ROOT/"build" or not p.name.startswith("m6_") for p in (source, output)) or output.exists():
        parser.error("direct build/m6_* paths; fresh output required")
    contract = json.loads((source/"contract.json").read_text())
    if contract["envelope"]["design_transition_limit_ns"] != 0.35:
        raise ValueError("original design slew budget required")
    original = ROOT/"build/m6_bank_1x_probe_v2/config.json"
    def resolve(value):
        if isinstance(value, str):
            return value.replace("dir::", "/work/")
        if isinstance(value, list):
            return [resolve(item) for item in value]
        if isinstance(value, dict):
            return {key: resolve(item) for key, item in value.items()}
        return value
    config = resolve(json.loads(original.read_text()))
    output.mkdir()
    for name, sha in contract["outputs"].items():
        data = (source/name).read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            raise ValueError("changed contract view")
        shutil.copyfile(source/name, output/name)
    for corner, paths in config["MACROS"][contract["macro"]]["lib"].items():
        config["MACROS"][contract["macro"]]["lib"][corner] = ["/candidate/"+Path(p).name for p in paths]
    (output/"config.json").write_text(json.dumps(config, indent=2)+"\n")
    manifest = {"status": "STAGED_CONTRACT_PROBE_NOT_PHYSICAL_PASS", "macro_count": 8,
        "sources": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (source/"contract.json", original, Path(__file__).resolve())},
        "contract": contract, "baseline_readonly_mount": "build/m6_bank_1x_probe_v2 -> /work",
        "candidate_mount": "/candidate"}
    (output/"manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n")


if __name__ == "__main__":
    main()
