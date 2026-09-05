#!/usr/bin/env python3
"""Create/check an exact staged-board manifest; no PYNQ or root required."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stage = args.manifest.resolve().parent
    if args.check:
        manifest = json.loads(args.manifest.read_text())
        for name, expected in manifest["sha256"].items():
            if sha256(stage / name) != expected:
                raise SystemExit(f"M3 MANIFEST FAIL {name}")
        print(f"M3 MANIFEST PASS files={len(manifest['sha256'])} "
              f"bit_sha256={manifest['sha256']['m3_pynq.bit']}")
        return
    if args.build is None:
        parser.error("--build required when creating manifest")
    build = args.build.resolve()
    log = (build / "vivado.log").read_text()
    passed = [line for line in log.splitlines() if line.startswith("M3 VIVADO PASS clock_mhz=")]
    if len(passed) != 1:
        raise SystemExit("Build lacks the complete timing/resource/DRC gate PASS")
    manifest = {"schema": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
                "build_directory": str(build), "build_gate": passed[0],
                "sha256": {str(p.relative_to(stage)): sha256(p)
                           for p in sorted(stage.rglob("*")) if p.is_file()
                           and p.resolve() != args.manifest.resolve()},
                "build_evidence_sha256": {str(p.relative_to(build)): sha256(p)
                                          for root in (build / "reports", build / "resolved_sources",
                                                       build / "build_scripts")
                                          for p in sorted(root.rglob("*")) if p.is_file()}}
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"M3 MANIFEST CREATED files={len(manifest['sha256'])}")


if __name__ == "__main__":
    main()
