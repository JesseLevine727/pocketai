"""Snapshot M6 constraints in a fresh directory, preserving prior run inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    assert out.parent.parent == ROOT / "build" and out.parent.name.startswith("m6_")
    assert not out.exists()
    out.mkdir()
    records = {}
    for name in ("soc.sdc", "clock_data_boundaries.tcl"):
        source = ROOT / "asic/m6" / name
        shutil.copyfile(source, out / name)
        records[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    (out / "manifest.json").write_text(json.dumps(records, indent=2) + "\n")
    print(f"M6 constraints snapshotted: {out}")


if __name__ == "__main__":
    main()
