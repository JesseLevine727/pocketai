#!/usr/bin/env python3
"""Fair G1 benchmark of the unchanged, hash-pinned M2 overlay (not M3 RTL).

Validation is outside timing. Dispatch, DMA/cache operations, result assembly,
scratchpad publication and completion fence remain inside. Policies are
interleaved per repeat; same deterministic logical inputs for CPU and FPGA.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np

BIT_SHA = "f196e92c4509ebad977521bf40a8cd30b0f3f131fbfe199515d6e0ff6600fa03"
HWH_SHA = "f77dfe909dd8a3d7d0266d4326c05ceb1eb97a0182bbd4d67acf25a96833c390"
FABRIC_HZ = 95_000_000
HIDDEN = 768
SEED = 0x50414D32
POLICIES = ("sleep_copy_packed", "spin_copy_packed", "spin_resident_packed",
            "spin_resident_logical", "spin_compact_packed", "spin_compact_logical",
            "cpu_logical")


def pack_projection(a: np.ndarray, b: np.ndarray, packets: np.ndarray) -> None:
    """Vectorized M2 A-then-B packing into existing ordinary or CMA memory.

    Benchmark-only full N=768/K=768 case; padding is not needed. The legacy
    packer remains authoritative and is independently compared in unit tests.
    """
    m, k = a.shape
    if (m not in (1, 16) or k != HIDDEN or b.shape != (k, HIDDEN)
            or a.dtype != np.int8 or b.dtype != np.int8
            or packets.shape != (48, m * k // 4 + 4 * k)
            or packets.dtype != np.uint32):
        raise ValueError("unexpected benchmark shape or dtype")
    byte_packets = packets.view(np.int8).reshape(48, -1)
    for tile in range(48):
        byte_packets[tile, :m * k] = a.reshape(-1)
        byte_packets[tile, m * k:].reshape(k, 16)[:] = b[:, tile * 16:(tile + 1) * 16]


def summary(samples: list[float], macs: int) -> dict:
    values = np.asarray(samples, dtype=np.float64)
    if not len(values) or np.any(values <= 0) or not np.all(np.isfinite(values)):
        raise ValueError("latencies must be nonempty, positive and finite")
    median = float(np.median(values))
    return {"median_ms": median * 1000, "p95_ms": float(np.percentile(values, 95)) * 1000,
            "min_ms": float(values.min()) * 1000, "max_ms": float(values.max()) * 1000,
            "mean_ms": float(values.mean()) * 1000,
            "std_ms": float(values.std()) * 1000,
            "cv_percent": float(values.std() / values.mean()) * 100,
            "delivered_gmac_s": macs / median / 1e9}


def load_cpu(path: Path):
    lib = ctypes.CDLL(str(path.resolve()))
    fn = lib.pa_cpu_gemm
    fn.argtypes = [np.ctypeslib.ndpointer(dtype=np.int8, flags="C_CONTIGUOUS"),
                   np.ctypeslib.ndpointer(dtype=np.int8, flags="C_CONTIGUOUS"),
                   np.ctypeslib.ndpointer(dtype=np.int16, flags="C_CONTIGUOUS"),
                   ctypes.c_int, ctypes.c_int, ctypes.c_int]
    fn.restype = ctypes.c_int
    lib.pa_cpu_backend.restype = ctypes.c_char_p
    return lib, fn


def qualify_cpu(fn) -> int:
    """Also exercises actual ARM NEON, including overflow/cancellation/tails."""
    rng = np.random.default_rng(SEED + 1)
    count = 0
    for m, n, k in ((1, 1, 1), (1, 16, 768), (16, 17, 768),
                    (3, 32, 3072), (16, 768, 768)):
        for mode in ("random", "positive", "negative", "cancel"):
            a = rng.integers(-128, 128, (m, k), dtype=np.int8)
            b = rng.integers(-128, 128, (k, n), dtype=np.int8)
            if mode != "random":
                a.fill(-128)
                b.fill(127 if mode == "negative" else -128)
                if mode == "cancel":
                    b[k // 2:] = 127
            expected = np.clip(a.astype(np.int64) @ b.astype(np.int64),
                               -32768, 32767).astype(np.int16)
            out = np.empty((m, n), dtype=np.int16)
            if fn(a, b, out, m, n, k) != 0 or not np.array_equal(out, expected):
                raise AssertionError(f"native CPU mismatch: {m,n,k,mode}")
            count += 1
    return count


def read_optional(path: str) -> str:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return "unavailable"


class Phases:
    """Disjoint host wall intervals; hardware cycles are NOT added to these."""
    def __init__(self):
        self.values = {}
        self.start = self.last = time.perf_counter()

    def mark(self, name):
        now = time.perf_counter()
        self.values[name] = self.values.get(name, 0.0) + now - self.last
        self.last = now

    def finish(self):
        self.mark("other_host")
        return {"seconds": self.last - self.start, "phases_s": self.values}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bitstream", type=Path, required=True)
    parser.add_argument("--cpu-lib", type=Path, default=Path("m3_cpu_gemm.so"))
    parser.add_argument("--output", type=Path, default=Path("m3_baseline.json"))
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    if args.warmups < 1 or args.repeats < 20 or args.timeout <= 0:
        parser.error("need >=1 warmup, >=20 repeats, positive timeout")
    hashes = {"bit_sha256": hashlib.sha256(args.bitstream.read_bytes()).hexdigest(),
              "hwh_sha256": hashlib.sha256(args.bitstream.with_suffix(".hwh").read_bytes()).hexdigest()}
    if hashes != {"bit_sha256": BIT_SHA, "hwh_sha256": HWH_SHA}:
        raise RuntimeError(f"not the qualified M2 overlay: {hashes}")

    # Kept out of module scope so packing, stats and native CPU can be tested
    # on an ordinary host with no PYNQ installation.
    import pynq
    from pynq import Clocks, MMIO, Overlay, allocate
    from m2_run import (CLUSTER_BASE, GEMM_BASE, GEMM_RANGE, RESET_BASE,
                        RESET_RANGE, GEMM_ID, GEMM_CAPS, REG_ID, REG_CAPS,
                        REG_STATUS, REG_ERROR, REG_COMPLETED_COUNT,
                        REG_COMPLETED_TAG, REG_LAST_CYCLES, REG_LAST_MACS,
                        RESULT_OFFSET, reset_dma, submit)
    from ref.gemm_ref import Descriptor

    cpu_lib, cpu = load_cpu(args.cpu_lib)
    cpu_cases = qualify_cpu(cpu)
    overlay = Overlay(str(args.bitstream.resolve()), download=True)
    dma = overlay.axi_dma_0
    gemm = MMIO(GEMM_BASE, GEMM_RANGE)
    reset = MMIO(RESET_BASE, RESET_RANGE)
    reset.write(4, 0)
    reset.write(0, 0)
    if gemm.read(REG_ID) != GEMM_ID or gemm.read(REG_CAPS) != GEMM_CAPS:
        raise RuntimeError("unexpected accelerator ID/caps")
    if gemm.read(REG_ERROR) or gemm.read(REG_STATUS) & 2:
        raise RuntimeError("accelerator not empty/clean")
    report = {"schema": 1, "milestone": "M3 G1 unchanged M2 baseline", **hashes,
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "seed": SEED, "warmups": args.warmups, "repeats": args.repeats,
              "fabric_hz": FABRIC_HZ, "fclk0_config_mhz": Clocks.fclk0_mhz,
              "python": platform.python_version(), "numpy": np.__version__,
              "pynq": pynq.__version__, "platform": platform.platform(),
              "cpu_backend": cpu_lib.pa_cpu_backend().decode(),
              "cpu_compile_flags": "-O3 -Wall -Wextra -Werror -shared -fPIC -mcpu=cortex-a9 -mfpu=neon",
              "cpu_library_sha256": hashlib.sha256(args.cpu_lib.read_bytes()).hexdigest(),
              "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "cpu_qualification_cases": cpu_cases,
              "cpuinfo": read_optional("/proc/cpuinfo"),
              "cpu_governor": read_optional("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
              "clock_summary": read_optional("/sys/kernel/debug/clk/clk_summary"),
              "notes": ["Same logical operands; FPGA packed policies exclude packing",
                        "Logical FPGA policy includes packing into preallocated CMA DDR",
                        "All policies deliver int16 output to shared scratchpad and fence",
                        "Validation and setup/allocation outside timing; warm data, single thread",
                        "Disjoint host phase instrumentation included in wall latency",
                        "Compute counters overlap transfers; do not add to host phases",
                        "Policies shuffled deterministically within each repetition"],
              "workloads": []}
    allocated = []

    def wait(channel, spin):
        deadline = time.monotonic() + args.timeout
        while not channel.idle:
            if channel.error:
                raise RuntimeError("DMA error")
            if time.monotonic() >= deadline:
                raise TimeoutError("DMA timeout")
            if not spin:
                time.sleep(0.0001)
        channel.wait()  # includes required receive cache invalidation

    try:
        for m in (1, 16):
            rng = np.random.default_rng(SEED)
            a = rng.integers(-32, 32, (m, HIDDEN), dtype=np.int8)
            b = rng.integers(-32, 32, (HIDDEN, HIDDEN), dtype=np.int8)
            expected = np.clip(a.astype(np.int64) @ b.astype(np.int64),
                               -32768, 32767).astype(np.int16)
            expected_words = expected.view(np.uint32)
            descriptors = [Descriptor(m, 16, HIDDEN, tag=t) for t in range(48)]
            words = descriptors[0].input_words
            packets = np.empty((48, words), dtype=np.uint32)
            pack_projection(a, b, packets)
            resident = allocate(shape=packets.shape, dtype=np.uint32)
            allocated.append(resident)
            resident[:] = packets
            # Slice once: PYNQ cache flushing uses the view's offset and length,
            # avoiding a whole-allocation flush for every small transfer.
            views = [resident[t] for t in range(48)]
            single = allocate(shape=(words,), dtype=np.uint32)
            allocated.append(single)
            output = allocate(shape=(m * 8,), dtype=np.uint32)
            allocated.append(output)
            observed = np.empty((m, HIDDEN), dtype=np.int16)
            observed_words = observed.view(np.uint32)
            # Plain NumPy views preserve the underlying DMA allocation and
            # required channel flush/invalidate operations. They avoid repeated
            # PynqBuffer view construction in the arithmetic-free copy path.
            resident_array = np.asarray(resident)
            output_array = np.asarray(output).reshape(m, 8)
            shared = MMIO(CLUSTER_BASE + RESULT_OFFSET, m * HIDDEN * 2).array.reshape(m, -1)
            samples = {policy: [] for policy in POLICIES}
            cycles_qualified = {}
            # Preparation is measured separately, not hidden in a resident claim.
            preparation = []
            for _ in range(args.repeats):
                begin = time.perf_counter()
                pack_projection(a, b, resident)
                preparation.append(time.perf_counter() - begin)

            def run(policy, capture=False):
                before_count = gemm.read(REG_COMPLETED_COUNT)
                counters = []
                timer = Phases()
                if policy == "cpu_logical":
                    rc = cpu(a, b, observed, m, HIDDEN, HIDDEN)
                    timer.mark("cpu_compute_ffi")
                    shared[:] = observed_words
                    timer.mark("publication")
                else:
                    rc = 0
                    spin = policy != "sleep_copy_packed"
                    compact = "compact" in policy
                    is_resident = "resident" in policy or compact
                    if policy.endswith("logical"):
                        pack_projection(a, b, resident_array if compact else resident)
                    timer.mark("packing")
                    for base in range(0, 48, 2):
                        submit(gemm, descriptors[base])
                        submit(gemm, descriptors[base + 1])
                        timer.mark("descriptor_dispatch")
                        dma.recvchannel.transfer(output)
                        timer.mark("receive_arm")
                        for tile in (base, base + 1):
                            if not is_resident:
                                single[:] = packets[tile]
                            timer.mark("input_copy")
                            dma.sendchannel.transfer(views[tile] if is_resident else single)
                            wait(dma.sendchannel, spin)
                            timer.mark("send_and_wait")
                        for tile in (base, base + 1):
                            if tile != base:
                                dma.recvchannel.transfer(output)
                            wait(dma.recvchannel, spin)
                            timer.mark("receive_and_wait")
                            observed_words[:, tile * 8:(tile + 1) * 8] = (
                                output_array if compact else output.reshape(m, 8))
                            timer.mark("result_assembly")
                            if not compact:
                                shared[:, tile * 8:(tile + 1) * 8] = observed_words[:, tile * 8:(tile + 1) * 8]
                            timer.mark("publication")
                            if capture:
                                counters.append((gemm.read(REG_LAST_CYCLES),
                                                 gemm.read(REG_LAST_MACS),
                                                 gemm.read(REG_COMPLETED_TAG)))
                                timer.mark("qualification_counters")
                    if compact:
                        shared[:] = observed_words
                        timer.mark("publication")
                # Ordered GP0 read after publication, not a numerical check.
                fence = int(shared[-1, -1])
                timer.mark("publication_fence")
                result = timer.finish()
                # ALL reference/error/counter checks below are outside timing.
                if rc or fence != int(expected_words[-1, -1]):
                    raise AssertionError(f"{policy}: return/fence mismatch")
                if not np.array_equal(observed, expected):
                    raise AssertionError(f"{policy}: DDR output mismatch")
                if not np.array_equal(np.array(shared), expected_words):
                    raise AssertionError(f"{policy}: shared output mismatch")
                if policy != "cpu_logical":
                    expected_cycles = ((m + 3) // 4) * (HIDDEN + 6) + 8 * m
                    expected_macs = m * 16 * HIDDEN
                    if (gemm.read(REG_COMPLETED_COUNT) - before_count) & 0xffffffff != 48:
                        raise AssertionError("completed descriptor count mismatch")
                    if gemm.read(REG_ERROR) or gemm.read(REG_STATUS) & 2:
                        raise AssertionError("accelerator error or not empty")
                    if (gemm.read(REG_LAST_CYCLES), gemm.read(REG_LAST_MACS),
                        gemm.read(REG_COMPLETED_TAG)) != (expected_cycles, expected_macs, 47):
                        raise AssertionError("final descriptor counters mismatch")
                    if capture:
                        if counters != [(expected_cycles, expected_macs, t) for t in range(48)]:
                            raise AssertionError("per-descriptor counters mismatch")
                        cycles_qualified[policy] = sum(c[0] for c in counters)
                return result

            order_rng = np.random.default_rng(SEED + m)
            for iteration in range(-args.warmups, args.repeats):
                for policy in order_rng.permutation(POLICIES):
                    result = run(str(policy), capture=iteration == -args.warmups)
                    if iteration >= 0:
                        result["iteration"] = iteration
                        samples[policy].append(result)
            macs = m * HIDDEN * HIDDEN
            workload = {"m": m, "n": HIDDEN, "k": HIDDEN, "macs": macs,
                        "descriptors": 48, "input_bytes": packets.nbytes,
                        "logical_input_bytes": a.nbytes + b.nbytes,
                        "output_bytes": expected.nbytes,
                        "resident_input_allocation_bytes": resident.nbytes,
                        "copy_input_allocation_bytes": single.nbytes,
                        "qualified_compute_cycles": cycles_qualified,
                        "packing_to_cma_seconds": preparation, "policies": {}}
            for policy, raw in samples.items():
                stats = summary([r["seconds"] for r in raw], macs)
                phase_names = sorted(set().union(*(r["phases_s"] for r in raw)))
                stats["mean_phases_ms"] = {
                    name: float(np.mean([r["phases_s"].get(name, 0) for r in raw])) * 1000
                    for name in phase_names}
                workload["policies"][policy] = {"summary": stats, "samples": raw}
                print(f"M3 G1 m={m} policy={policy} median_ms={stats['median_ms']:.3f} "
                      f"p95_ms={stats['p95_ms']:.3f} GMAC_s={stats['delivered_gmac_s']:.4f}", flush=True)
            report["workloads"].append(workload)
        report["status"] = "PASS"
    finally:
        # Never release DMA memory while a channel can still access it.
        reset_dma(dma, args.timeout)
        for buffer in reversed(allocated):
            buffer.freebuffer()
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"M3 G1 BENCHMARK PASS output={args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
