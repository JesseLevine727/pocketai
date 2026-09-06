#!/usr/bin/env python3
"""Reject an M5 hardware export that omitted the qualified CPU derivation."""
import hashlib
import sys
from pathlib import Path

EXPECTED = {
    'ibex_load_store_unit.sv': '7fe4d5c261420f9862783978c9d9370a65dae6f360b5780f7afca19b090a8791',
    'ibex_id_stage.sv': '1e9d382752cf9f13477f279ddc3f73a2b3d7bbd8e5cf8e4a7a9d755f6162c5f1',
}


def check(work_root: Path):
    rtl = work_root / 'src/lowrisc_ibex_ibex_core_0.1/rtl'
    for name, expected in EXPECTED.items():
        actual = hashlib.sha256((rtl / name).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f'M5 CPU source mismatch {name}: {actual} != {expected}; '
                               'run the exported m5_prepare_lsu.sh before compiling')
        print(f'M5 CPU SOURCE PASS {name} {actual}')


if __name__ == '__main__':
    check(Path(sys.argv[1]))
