#!/usr/bin/env python3
"""Run the PocketAI-T M2 projection acceptance workload on a PYNQ-Z1."""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pynq import MMIO, Overlay, allocate

from ref.gemm_ref import Descriptor, gemm_int8_int16, pack_input_words, pack_output_words


CLUSTER_BASE = 0x43C0_0000
CLUSTER_RANGE = 0x0002_0000
GEMM_BASE = CLUSTER_BASE + 0x0001_3000
GEMM_RANGE = 0x0000_1000
RESET_BASE = 0x43C2_0000
RESET_RANGE = 0x0001_0000

REG_ID = 0x00
REG_STATUS = 0x04
REG_M = 0x08
REG_N = 0x0C
REG_K = 0x10
REG_FLAGS = 0x14
REG_TAG = 0x18
REG_COMMAND = 0x1C
REG_COMPLETED_TAG = 0x20
REG_LAST_CYCLES = 0x24
REG_LAST_MACS = 0x28
REG_INPUT_WORDS = 0x2C
REG_OUTPUT_WORDS = 0x30
REG_COMPLETED_COUNT = 0x34
REG_ERROR = 0x38
REG_CAPS = 0x3C

GEMM_ID = 0x5041_4732
GEMM_CAPS = 0x0300_1010
FABRIC_HZ = 95_000_000
TOKENS = 16
HIDDEN = 768
TILE_N = 16
RANDOM_SEED = 0x5041_4D32
RESULT_OFFSET = 0x4000


@dataclass(frozen=True)
class TileCase:
    descriptor: Descriptor
    input_words: np.ndarray
    expected_words: np.ndarray


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bitstream", type=Path, default=Path("m2_pynq.bit"))
    parser.add_argument("--timeout", type=float, default=10.0)
    return parser.parse_args()


def fail(message: str) -> int:
    print(f"M2 BOARD FAIL: {message}", file=sys.stderr)
    return 1


def submit(gemm: MMIO, descriptor: Descriptor) -> None:
    gemm.write(REG_M, descriptor.m)
    gemm.write(REG_N, descriptor.n)
    gemm.write(REG_K, descriptor.k)
    gemm.write(REG_FLAGS, descriptor.flags)
    gemm.write(REG_TAG, descriptor.tag)
    gemm.write(REG_COMMAND, 1)
    error = gemm.read(REG_ERROR)
    if error:
        raise RuntimeError(
            f"descriptor tag={descriptor.tag} rejected with error={error}"
        )


def wait_channel(channel: object, timeout: float, description: str) -> None:
    deadline = time.monotonic() + timeout
    while not channel.idle:
        if channel.error:
            raise RuntimeError(f"DMA error during {description}")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"timeout waiting for {description}")
        time.sleep(0.0001)
    channel.wait()


def reset_dma(dma: object, timeout: float) -> None:
    """Reset both channels before releasing any possibly active CMA buffer."""
    dma.mmio.write(0x00, 4)
    deadline = time.monotonic() + timeout
    while dma.mmio.read(0x00) & 4:
        if time.monotonic() >= deadline:
            raise TimeoutError("DMA reset did not finish; buffers retained")
        time.sleep(0.0001)


def make_cases() -> list[TileCase]:
    rng = np.random.default_rng(RANDOM_SEED)
    activations = rng.integers(-32, 32, size=(TOKENS, HIDDEN), dtype=np.int8)
    weights = rng.integers(-32, 32, size=(HIDDEN, HIDDEN), dtype=np.int8)
    cases: list[TileCase] = []
    for column in range(0, HIDDEN, TILE_N):
        descriptor = Descriptor(TOKENS, TILE_N, HIDDEN, tag=column // TILE_N)
        weight_tile = weights[:, column : column + TILE_N]
        expected = gemm_int8_int16(activations, weight_tile)
        cases.append(
            TileCase(
                descriptor=descriptor,
                input_words=np.asarray(
                    pack_input_words(descriptor, activations, weight_tile),
                    dtype=np.uint32,
                ),
                expected_words=np.asarray(
                    pack_output_words(descriptor, expected), dtype=np.uint32
                ),
            )
        )
    return cases


def main() -> int:
    args = parse_args()
    bitstream = args.bitstream.resolve()
    hwh = bitstream.with_suffix(".hwh")
    for required in (bitstream, hwh):
        if not required.is_file():
            return fail(f"missing {required}")

    cases = make_cases()
    if len(cases) != 48:
        return fail(f"internal workload has {len(cases)} descriptors, expected 48")

    print(f"M2 artifact bit_sha256={hashlib.sha256(bitstream.read_bytes()).hexdigest()} "
          f"hwh_sha256={hashlib.sha256(hwh.read_bytes()).hexdigest()}", flush=True)

    overlay = Overlay(str(bitstream), download=True)
    if not hasattr(overlay, "axi_dma_0"):
        return fail(f"overlay has no axi_dma_0; IPs={sorted(overlay.ip_dict)}")
    dma = overlay.axi_dma_0
    gemm = MMIO(GEMM_BASE, GEMM_RANGE)
    reset = MMIO(RESET_BASE, RESET_RANGE)
    results = MMIO(CLUSTER_BASE + RESULT_OFFSET, TOKENS * HIDDEN * 2)
    shared_words = results.array.reshape(TOKENS, HIDDEN // 2)
    expected_shared = np.zeros((TOKENS, HIDDEN // 2), dtype=np.uint32)

    # The accelerator uses the system reset and remains available while both
    # Ibex harts are held in reset for this A9-driven acceptance workload.
    reset.write(0x04, 0x0)
    reset.write(0x00, 0x0)

    if gemm.read(REG_ID) != GEMM_ID:
        return fail(f"ID is 0x{gemm.read(REG_ID):08x}, expected 0x{GEMM_ID:08x}")
    if gemm.read(REG_CAPS) != GEMM_CAPS:
        return fail(
            f"caps are 0x{gemm.read(REG_CAPS):08x}, expected 0x{GEMM_CAPS:08x}"
        )
    if gemm.read(REG_ERROR) != 0:
        return fail(f"accelerator starts with error={gemm.read(REG_ERROR)}")

    max_input_words = max(case.input_words.size for case in cases)
    max_output_words = max(case.expected_words.size for case in cases)
    input_buffer = allocate(shape=(max_input_words,), dtype=np.uint32)
    output_buffer = allocate(shape=(max_output_words,), dtype=np.uint32)

    total_input_bytes = 0
    total_output_bytes = 0
    total_macs = 0
    total_cycles = 0
    mm2s_seconds = 0.0
    publish_seconds = 0.0
    workload_start = time.monotonic()

    try:
        for pair_base in range(0, len(cases), 2):
            pair = cases[pair_base : pair_base + 2]
            for case in pair:
                submit(gemm, case.descriptor)

            occupied = (gemm.read(REG_STATUS) >> 8) & 0x3
            if occupied != len(pair):
                raise RuntimeError(
                    f"pair {pair_base // 2} reserved {occupied} slots, "
                    f"expected {len(pair)}"
                )

            first = pair[0]
            dma.recvchannel.transfer(
                output_buffer, nbytes=first.expected_words.nbytes
            )

            # Feed both reserved slots before waiting for the first result. The
            # second packet therefore loads while the first tile computes.
            for case in pair:
                input_count = case.input_words.size
                input_buffer[:input_count] = case.input_words
                send_start = time.monotonic()
                dma.sendchannel.transfer(
                    input_buffer, nbytes=case.input_words.nbytes
                )
                wait_channel(dma.sendchannel, args.timeout, "MM2S input")
                mm2s_seconds += time.monotonic() - send_start

            for pair_index, case in enumerate(pair):
                if pair_index == 0:
                    wait_channel(dma.recvchannel, args.timeout, "S2MM output")
                else:
                    dma.recvchannel.transfer(
                        output_buffer, nbytes=case.expected_words.nbytes
                    )
                    wait_channel(dma.recvchannel, args.timeout, "S2MM output")

                observed = np.array(
                    output_buffer[: case.expected_words.size],
                    dtype=np.uint32,
                    copy=True,
                )
                mismatch = np.flatnonzero(observed != case.expected_words)
                if mismatch.size:
                    index = int(mismatch[0])
                    raise RuntimeError(
                        f"tag={case.descriptor.tag} output word {index} mismatch: "
                        f"got 0x{int(observed[index]):08x}, "
                        f"expected 0x{int(case.expected_words[index]):08x}"
                    )

                # Publish the result into the same scratchpad visible to both
                # harts. The A9 performs this DDR-to-scratchpad copy via GP0.
                column_word = case.descriptor.tag * (TILE_N // 2)
                expected_shared[:, column_word : column_word + TILE_N // 2] = (
                    case.expected_words.reshape(TOKENS, TILE_N // 2)
                )
                publish_start = time.monotonic()
                shared_words[:, column_word : column_word + TILE_N // 2] = (
                    observed.reshape(TOKENS, TILE_N // 2)
                )
                publish_seconds += time.monotonic() - publish_start

                expected_cycles = ((case.descriptor.m + 3) // 4) * (
                    case.descriptor.k + 6
                ) + case.descriptor.m * 8
                last_cycles = gemm.read(REG_LAST_CYCLES)
                last_macs = gemm.read(REG_LAST_MACS)
                if last_cycles != expected_cycles:
                    raise RuntimeError(
                        f"tag={case.descriptor.tag} cycles={last_cycles}, "
                        f"expected {expected_cycles}"
                    )
                if last_macs != case.descriptor.macs:
                    raise RuntimeError(
                        f"tag={case.descriptor.tag} macs={last_macs}, "
                        f"expected {case.descriptor.macs}"
                    )
                if gemm.read(REG_INPUT_WORDS) != case.descriptor.input_words:
                    raise RuntimeError("input word-count register mismatch")
                if gemm.read(REG_OUTPUT_WORDS) != case.descriptor.output_words:
                    raise RuntimeError("output word-count register mismatch")
                if gemm.read(REG_ERROR) != 0:
                    raise RuntimeError(f"accelerator error={gemm.read(REG_ERROR)}")

                total_input_bytes += case.input_words.nbytes
                total_output_bytes += case.expected_words.nbytes
                total_macs += case.descriptor.macs
                total_cycles += expected_cycles

        if not np.array_equal(np.array(shared_words, copy=True), expected_shared):
            raise RuntimeError("shared scratchpad projection readback mismatch")
        workload_seconds = time.monotonic() - workload_start
        completed = gemm.read(REG_COMPLETED_COUNT)
        completed_tag = gemm.read(REG_COMPLETED_TAG)
        if completed != len(cases):
            raise RuntimeError(f"completed_count={completed}, expected {len(cases)}")
        if completed_tag != cases[-1].descriptor.tag:
            raise RuntimeError(
                f"completed_tag={completed_tag}, expected {cases[-1].descriptor.tag}"
            )

        accelerator_gmac_s = total_macs * FABRIC_HZ / total_cycles / 1.0e9
        end_to_end_gmac_s = total_macs / workload_seconds / 1.0e9
        mm2s_mb_s = total_input_bytes / mm2s_seconds / 1.0e6
        effective_mb_s = (
            (total_input_bytes + total_output_bytes) / workload_seconds / 1.0e6
        )
        print(
            "M2 transfer: "
            f"input_bytes={total_input_bytes} output_bytes={total_output_bytes} "
            f"mm2s_s={mm2s_seconds:.6f} mm2s_MB_s={mm2s_mb_s:.3f} "
            f"effective_MB_s={effective_mb_s:.3f}"
        )
        print(f"M2 shared-memory publication: A9_copy_s={publish_seconds:.6f} "
              f"bytes={expected_shared.nbytes}")
        print(
            "M2 performance: "
            f"cycles={total_cycles} macs={total_macs} "
            f"workload_s={workload_seconds:.6f} "
            f"accelerator_GMAC_s={accelerator_gmac_s:.3f} "
            f"end_to_end_GMAC_s={end_to_end_gmac_s:.3f}"
        )
    except (RuntimeError, TimeoutError) as error:
        return fail(str(error))
    finally:
        reset_dma(dma, args.timeout)
        input_buffer.freebuffer()
        output_buffer.freebuffer()

    print(
        "M2 BOARD PASS "
        f"projection={TOKENS}x{HIDDEN}x{HIDDEN} "
        f"descriptors={len(cases)} pairs={len(cases) // 2} "
        f"result_i16={TOKENS * HIDDEN} exact_words={total_output_bytes // 4} "
        f"shared_exact_words={expected_shared.size} shared_offset=0x{RESULT_OFFSET:04x}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
