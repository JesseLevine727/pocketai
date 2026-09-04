#!/usr/bin/env python3
"""Load and run the PocketAI-T M1 acceptance image on a PYNQ-Z1."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
from pynq import MMIO, Overlay


CLUSTER_BASE = 0x43C0_0000
CLUSTER_RANGE = 0x0002_0000
RESET_BASE = 0x43C2_0000
RESET_RANGE = 0x0001_0000

CONSOLE_DATA = 0x0001_1000
CONSOLE_STATUS = 0x0001_1004

RESULTS = {
    "done0": (0x0000_D000, 0x4D31_4830),
    "done1": (0x0000_D004, 0x4D31_4831),
    "count0": (0x0000_D008, 10_000),
    "count1": (0x0000_D00C, 10_000),
    "msgsum0": (0x0000_D010, 0x468A_AD43),
    "msgsum1": (0x0000_D014, 0x8555_8C0A),
    "work0": (0x0000_D018, 0x29C4_C2C2),
    "work1": (0x0000_D01C, 0xA3E3_16EC),
    "error0": (0x0000_D020, 0),
    "error1": (0x0000_D024, 0),
    "ready0": (0x0000_D028, 0x4952_5152),
    "ready1": (0x0000_D02C, 0x4952_5152),
}
RESULT_HOST_ACK = 0x0000_D030
HOST_ACK_MAGIC = 0x484F_5354


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bitstream", type=Path, default=Path("m1_pynq.bit"))
    parser.add_argument("--firmware", type=Path, default=Path("cluster.bin"))
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args()


def drain_console(cluster: MMIO, output: bytearray) -> tuple[bool, bool]:
    status = cluster.read(CONSOLE_STATUS)
    count = status & 0xFFFF
    overflow = bool(status & (1 << 16))
    done = bool(status & (1 << 31))
    for _ in range(count):
        output.append(cluster.read(CONSOLE_DATA) & 0xFF)
    return done, overflow


def fail(message: str, console: bytearray) -> int:
    if console:
        print("M1 console:")
        print(console.decode("ascii", errors="replace"), end="")
    print(f"M1 BOARD FAIL: {message}", file=sys.stderr)
    return 1


def main() -> int:
    args = parse_args()
    bitstream = args.bitstream.resolve()
    firmware = args.firmware.resolve()
    hwh = bitstream.with_suffix(".hwh")

    for required in (bitstream, hwh, firmware):
        if not required.is_file():
            print(f"M1 BOARD FAIL: missing {required}", file=sys.stderr)
            return 1

    image = firmware.read_bytes()
    if len(image) != 64 * 1024:
        print(
            f"M1 BOARD FAIL: firmware is {len(image)} bytes; expected 65536",
            file=sys.stderr,
        )
        return 1

    Overlay(str(bitstream), download=True)
    cluster = MMIO(CLUSTER_BASE, CLUSTER_RANGE)
    reset = MMIO(RESET_BASE, RESET_RANGE)

    # AXI GPIO channel 1: DATA at +0, TRI at +4. Keep the cores reset while
    # the A9 initializes and verifies the shared 64 KiB scratchpad.
    reset.write(0x04, 0x0)
    reset.write(0x00, 0x0)

    words = np.frombuffer(image, dtype="<u4")
    cluster.array[: words.size] = words
    readback = np.array(cluster.array[: words.size], dtype="<u4", copy=True)
    mismatch = np.flatnonzero(readback != words)
    if mismatch.size:
        index = int(mismatch[0])
        return fail(
            "firmware readback mismatch at "
            f"0x{index * 4:08x}: wrote 0x{int(words[index]):08x}, "
            f"read 0x{int(readback[index]):08x}",
            bytearray(),
        )

    reset.write(0x00, 0x1)
    start = time.monotonic()
    console = bytearray()

    while time.monotonic() - start < args.timeout:
        _, overflow = drain_console(cluster, console)
        if overflow:
            return fail("console FIFO overflow", console)
        if (
            cluster.read(RESULTS["done0"][0]) == RESULTS["done0"][1]
            and cluster.read(RESULTS["done1"][0]) == RESULTS["done1"][1]
        ):
            break
        time.sleep(0.005)
    else:
        observed = {
            name: cluster.read(offset) for name, (offset, _) in RESULTS.items()
        }
        return fail(f"timeout; observed={observed}", console)

    observed = {
        name: cluster.read(offset) for name, (offset, _) in RESULTS.items()
    }
    failures = {
        name: (observed[name], expected)
        for name, (_, expected) in RESULTS.items()
        if observed[name] != expected
    }
    if failures:
        return fail(f"result ABI mismatch: {failures}", console)

    cluster.write(RESULT_HOST_ACK, HOST_ACK_MAGIC)
    done_deadline = time.monotonic() + 2.0
    software_done = False
    while time.monotonic() < done_deadline:
        software_done, overflow = drain_console(cluster, console)
        if overflow:
            return fail("console FIFO overflow", console)
        if software_done:
            break
        time.sleep(0.005)
    if not software_done:
        return fail("firmware did not acknowledge host completion", console)

    elapsed = time.monotonic() - start
    print("M1 console:")
    print(console.decode("ascii", errors="replace"), end="")
    print(
        "M1 results: "
        f"count0={observed['count0']} count1={observed['count1']} "
        f"msg0={observed['msgsum0']:08x} msg1={observed['msgsum1']:08x} "
        f"work0={observed['work0']:08x} work1={observed['work1']:08x}"
    )
    print(f"M1 BOARD PASS elapsed_s={elapsed:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
