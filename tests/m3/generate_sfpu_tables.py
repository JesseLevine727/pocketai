#!/usr/bin/env python3
"""Reproduce/check v1 ROM data from the frozen numerical reference."""
import argparse
import hashlib
from pathlib import Path
from ref.sfpu_ref import GELU_TABLE, EXP_TABLE


def tables():
    return {"gelu_q8.mem": "".join(f"{v:04x}\n" for v in GELU_TABLE),
            "exp_q24.mem": "".join(f"{v:07x}\n" for v in EXP_TABLE)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        args.directory.mkdir(parents=True, exist_ok=True)
    for name, data in tables().items():
        path = args.directory / name
        if args.check:
            if path.read_text() != data:
                raise SystemExit(f"ROM mismatch: {path}")
        else:
            path.write_text(data)
        print(f"{hashlib.sha256(data.encode()).hexdigest()}  {path}")
    print("M3 SFPU ROM PASS")


if __name__ == "__main__":
    main()
