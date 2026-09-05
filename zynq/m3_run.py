#!/usr/bin/env python3
"""M3 exact-overlay physical qualification and explicitly bounded benchmarks.

Preparations/references/validation are outside timed execution. Timed chains
patch inputs from actual predecessor results, calculate dynamic row scales on
the A9, dispatch all work, transfer/cache-maintain, and publish final results.
No model/checkpoint/token throughput claim is made by this operator harness.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import platform
from pathlib import Path
import time
import numpy as np
from ref.m3_packets import read_packets, patch_input, runtime_requant_parameters
from ref.sfpu_stream import Op

FABRIC_HZ = 95_000_000


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_optional(path):
    try:
        return Path(path).read_text()
    except OSError as error:
        return f"unavailable: {error}"


def statistics(seconds):
    values = np.asarray(seconds, dtype=float)
    return {"median_ms": float(np.median(values) * 1000),
            "p95_ms": float(np.percentile(values, 95) * 1000),
            "min_ms": float(values.min() * 1000), "max_ms": float(values.max() * 1000),
            "mean_ms": float(values.mean() * 1000),
            "cv_percent": float(values.std() / values.mean() * 100)}


class Driver:
    def __init__(self, overlay, packets, timeout):
        from pynq import MMIO, allocate
        self.dma, self.timeout = overlay.axi_dma_0, timeout
        self.engines = [MMIO(0x43c13000, 0x1000), MMIO(0x43c14000, 0x400)]
        self.route = self.engines[1].read(0x50)
        self.tx = allocate((max(p.inputs.size for p in packets),), dtype=np.uint32)
        self.rx = allocate((max(p.expected.size for p in packets),), dtype=np.uint32)
        self.tx_array, self.rx_array = np.asarray(self.tx), np.asarray(self.rx)
        self.tx_views = {n: self.tx[:n] for n in {p.inputs.size for p in packets}}
        self.rx_views = {n: self.rx[:n] for n in {p.expected.size for p in packets}}

    def close(self):
        from m2_run import reset_dma
        # If reset fails, retain allocations: an active DMA must never use freed CMA.
        reset_dma(self.dma, self.timeout)
        self.rx.freebuffer()
        self.tx.freebuffer()

    def wait(self, channel):
        deadline = time.monotonic() + self.timeout
        while not channel.idle:
            if channel.error:
                raise RuntimeError("M3 DMA error")
            if time.monotonic() > deadline:
                raise TimeoutError("M3 DMA timeout")
        channel.wait()  # includes required S2MM cache invalidation

    def select(self, route):
        if route != self.route:
            self.engines[1].write(0x50, route)
            self.route = route

    def execute(self, packet, observed, prepared=False, parameters=None):
        # Completion of both previous channels precedes route/buffer reuse.
        self.select(packet.kind)
        engine = self.engines[packet.kind]
        for index, value in enumerate(parameters or packet.parameters):
            engine.write(8 + 4 * index, int(value))
        engine.write(0x18, packet.tag)
        if not prepared:
            self.tx_array[:packet.inputs.size] = packet.inputs
        engine.write(0x1c, 1)
        self.dma.recvchannel.transfer(self.rx_views[packet.expected.size])
        self.dma.sendchannel.transfer(self.tx_views[packet.inputs.size])
        self.wait(self.dma.sendchannel)
        self.wait(self.dma.recvchannel)
        observed[:] = self.rx_array[:packet.expected.size]

    def check(self, packet, observed, expected_count=None):
        if not np.array_equal(observed, packet.expected):
            index = int(np.flatnonzero(observed != packet.expected)[0])
            raise AssertionError(f"kind={packet.kind} tag={packet.tag} word={index} "
                                 f"got=0x{int(observed[index]):08x} "
                                 f"expected=0x{int(packet.expected[index]):08x}")
        engine = self.engines[packet.kind]
        expected = {0x20: packet.tag, 0x24: packet.cycles,
                    0x28: packet.parameters[1] if packet.kind else packet.macs,
                    0x2c: packet.inputs.size, 0x30: packet.expected.size, 0x38: 0}
        if expected_count is not None:
            expected[0x34] = expected_count & 0xffffffff
        actual = {offset: engine.read(offset) for offset in expected}
        if actual != expected or engine.read(4) & 2:
            raise AssertionError(f"completion mismatch tag={packet.tag}: {actual}, expected={expected}")

    def control_checks(self):
        gemm, sfpu = self.engines
        for engine in self.engines:
            engine.write(0x1c, 4)
            engine.write(0x40, 0)
        if (gemm.read(0), gemm.read(0x3c), gemm.read(0x44), gemm.read(0x48), gemm.read(0x4c)) != (
                0x50414732, 0x03001010, 1, 3072, 0x30001):
            raise AssertionError("M3 GEMM capabilities missing")
        if (sfpu.read(0), sfpu.read(0x3c), sfpu.read(0x44), sfpu.read(0x48), sfpu.read(0x4c)) != (
                0x50415333, 0x01000c00, 0xfe, 0x30001, 1024):
            raise AssertionError("M3 SFPU capabilities missing")
        self.select(0)
        for offset, value in ((8, 1), (12, 1), (16, 1), (20, 0), (28, 1)):
            gemm.write(offset, value)
        sfpu.write(0x50, 1)
        if sfpu.read(0x38) != 9 or sfpu.read(0x50) != 0:
            raise AssertionError("physical GEMM-busy route interlock failed")
        gemm.write(0x1c, 4)
        sfpu.write(0x1c, 2)
        self.select(1)
        for offset, value in ((8, 7), (12, 1), (16, 0), (20, 0), (28, 1)):
            sfpu.write(offset, value)
        sfpu.write(0x50, 0)
        if sfpu.read(0x38) != 9 or sfpu.read(0x50) != 1:
            raise AssertionError("physical SFPU-busy route interlock failed")
        sfpu.write(0x1c, 4)
        for op, length, shift, error in ((0, 1, 0, 1), (3, 1025, 0, 2), (1, 1, 1, 3)):
            sfpu.write(8, op)
            sfpu.write(12, length)
            sfpu.write(16, shift)
            sfpu.write(28, 1)
            if sfpu.read(0x38) != error or sfpu.read(4) & 2:
                raise AssertionError("physical descriptor rejection failed")
            sfpu.write(28, 2)
        self.select(0)
        print("M3 BOARD CONTROL PASS", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bitstream", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sfpu-vectors", type=Path, default=Path("sfpu.bin"))
    parser.add_argument("--gemm-vectors", type=Path, default=Path("gemm.bin"))
    parser.add_argument("--chain-vectors", type=Path, default=Path("chains.bin"))
    parser.add_argument("--output", type=Path, default=Path("m3_board.json"))
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    if args.warmups < 1 or args.repeats < 20 or args.timeout <= 0:
        parser.error("require >=1 warmup, >=20 repeats, positive timeout")
    manifest = json.loads(args.manifest.read_text())
    # Refuse programming if ANY staged source/vector/overlay differs from the
    # host-produced manifest. Host qualification must separately review timing.
    for filename, expected in manifest["sha256"].items():
        if digest(args.manifest.parent / filename) != expected:
            raise RuntimeError(f"staging hash mismatch: {filename}")
    for artifact in (args.bitstream, args.bitstream.with_suffix(".hwh"),
                     args.sfpu_vectors, args.gemm_vectors, args.chain_vectors):
        if manifest["sha256"].get(artifact.name) != digest(artifact):
            raise RuntimeError(f"requested artifact is not in the manifest: {artifact}")
    sfpu_packets, sfpu_seed = read_packets(args.sfpu_vectors)
    gemm_packets, gemm_seed = read_packets(args.gemm_vectors)
    chain_packets, chain_seed = read_packets(args.chain_vectors)
    all_packets = sfpu_packets + gemm_packets + chain_packets
    if (len(sfpu_packets) < 3472 or len(gemm_packets) < 1007 or len(chain_packets) != 315
            or {p.parameters[0] for p in sfpu_packets} != set(range(1, 8))):
        raise RuntimeError("incomplete M3 qualification vector set")
    import pynq
    from pynq import Clocks, MMIO, Overlay
    overlay = Overlay(str(args.bitstream.resolve()), download=True)
    reset = MMIO(0x43c20000, 0x10000)
    reset.write(4, 0)
    reset.write(0, 0)
    driver = Driver(overlay, all_packets, args.timeout)
    report = {"schema": 1, "status": "RUNNING", "manifest": manifest,
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "python": platform.python_version(), "numpy": np.__version__,
              "pynq": pynq.__version__, "platform": platform.platform(),
              "fabric_hz": FABRIC_HZ, "fclk0_config_mhz": Clocks.fclk0_mhz,
              "cpuinfo": read_optional("/proc/cpuinfo"),
              "cpu_governor": read_optional("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
              "clock_summary": read_optional("/sys/kernel/debug/clk/clk_summary"),
              "warmups": args.warmups, "repeats": args.repeats,
              "seeds": {"sfpu": sfpu_seed, "gemm": gemm_seed, "chains": chain_seed},
              "notes": ["A9 single-owner, harts held reset during timed measurements",
                        "M1 physical regression separately qualifies both harts on identical overlay",
                        "All validation/reference/allocation outside timed regions",
                        "All timed packets copied from prepacked ordinary DDR into reusable CMA",
                        "Operator result delivery is ordinary DDR; final chain delivery is shared scratchpad",
                        "Chains use actual prior results, A9 dynamic scaling/packing, no direct fabric forwarding",
                        "Fixed weights/coefficients prepared outside timing; no checkpoint/model inference",
                        "Full busy polling consumes one A9 thread; cache maintenance included",
                        "Compute counters overlap DMA and are not additive wall-time phases"],
              "operators": [], "chains": []}
    try:
        driver.control_checks()
        totals = [e.read(0x34) for e in driver.engines]
        initial_totals = totals.copy()
        for name, packets in (("wide_mixed_gemm", gemm_packets), ("sfpu", sfpu_packets)):
            counts = Counter()
            for index, packet in enumerate(packets):
                observed = np.empty_like(packet.expected)
                driver.execute(packet, observed)
                totals[packet.kind] += 1
                driver.check(packet, observed, totals[packet.kind])
                counts[int(packet.parameters[0]) if packet.kind else int(packet.parameters[3])] += 1
            report[name + "_qualification"] = {"cases": len(packets), "counts": dict(counts)}
            print(f"M3 BOARD {name.upper()} PASS cases={len(packets)} counts={dict(counts)}", flush=True)

        # Seven representative vectors. Prefer realistic chain operands; GELU
        # uses the separate maximum-length scalar sweep packet.
        choices = {int(op): max((p for p in sfpu_packets if p.parameters[0] == op),
                                key=lambda p: p.parameters[1]) for op in Op}
        for packet in chain_packets:
            if packet.kind:
                choices.setdefault(packet.parameters[0], packet)
        for op in (2, 3, 4, 5, 6, 7):
            choices[op] = max((p for p in chain_packets if p.kind and p.parameters[0] == op),
                              key=lambda p: p.parameters[1])
        order_rng = np.random.default_rng(0x50455233)
        operator_samples = {op: [] for op in choices}
        for iteration in range(-args.warmups, args.repeats):
            for op in order_rng.permutation(list(choices)):
                packet = choices[int(op)]
                observed = np.empty_like(packet.expected)
                begin = time.perf_counter()
                driver.execute(packet, observed)
                elapsed = time.perf_counter() - begin
                driver.check(packet, observed)
                if iteration >= 0:
                    operator_samples[int(op)].append(elapsed)
        for op, packet in sorted(choices.items()):
            entry = {"op": Op(op).name, "length": packet.parameters[1],
                     "input_bytes": packet.inputs.nbytes, "output_bytes": packet.expected.nbytes,
                     "compute_cycles": packet.cycles, "compute_ms": packet.cycles / FABRIC_HZ * 1000,
                     "samples_s": operator_samples[op], **statistics(operator_samples[op])}
            report["operators"].append(entry)
            print(f"M3 OP {entry['op']} L={entry['length']} compute_ms={entry['compute_ms']:.6f} "
                  f"delivered_median_ms={entry['median_ms']:.6f} p95_ms={entry['p95_ms']:.6f}", flush=True)

        for scenario, name, final_id, address in ((0, "MLP_768_3072_768", 9, 0x43c05000),
                                                  (1, "ATTENTION_64_1024_16", 25, 0x43c06000)):
            packets = [p for p in chain_packets if p.scenario == scenario]
            tensors, expected_tensors = {}, {}
            observed = [np.empty_like(p.expected) for p in packets]
            for packet in packets:
                size = max((p.offset + p.result_count for p in packets
                            if p.destination == packet.destination))
                tensors.setdefault(packet.destination, np.empty(size, dtype="<u4"))
                expected_tensors.setdefault(packet.destination, np.empty(size, dtype="<u4"))
                expected_tensors[packet.destination][packet.offset:packet.offset + packet.result_count] = packet.expected
            final = tensors[final_id]
            compact = np.empty(final.size, dtype="<i2")
            shared = MMIO(address, compact.nbytes).array
            samples = []
            for iteration in range(-args.warmups, args.repeats):
                # Input packet layout/weights are prepacked ordinary DDR. Its
                # one-off host packing cost is not a measured speedup claim.
                before_counts = [e.read(0x34) for e in driver.engines]
                begin = time.perf_counter()
                for index, packet in enumerate(packets):
                    driver.tx_array[:packet.inputs.size] = packet.inputs
                    parameters = None
                    if packet.source:
                        source = tensors[packet.source]
                        patch_input(packet, source, driver.tx_array[:packet.inputs.size])
                        if packet.kind and packet.parameters[0] == 5:
                            mult, shift = runtime_requant_parameters(source)
                            parameters = (5, packet.parameters[1], shift, mult)
                    driver.execute(packet, observed[index], prepared=True, parameters=parameters)
                    tensors[packet.destination][packet.offset:packet.offset + packet.result_count] = observed[index]
                compact[:] = final.view("<i4")
                shared[:] = compact.view("<u4")
                fence = int(shared[-1])
                elapsed = time.perf_counter() - begin
                # Exact checks only after the complete chain has been delivered.
                for packet, result in zip(packets, observed):
                    if not np.array_equal(result, packet.expected):
                        raise AssertionError(f"chain {name} mismatch at tag={packet.tag}")
                for tensor in tensors:
                    if not np.array_equal(tensors[tensor], expected_tensors[tensor]):
                        raise AssertionError(f"chain {name} tensor {tensor} mismatch")
                if fence != int(compact.view("<u4")[-1]) or not np.array_equal(np.array(shared), compact.view("<u4")):
                    raise AssertionError("chain publication mismatch")
                for kind in (0, 1):
                    index = max(i for i, p in enumerate(packets) if p.kind == kind)
                    expected_count = before_counts[kind] + sum(p.kind == kind for p in packets)
                    driver.check(packets[index], observed[index], expected_count)
                if iteration >= 0:
                    samples.append(elapsed)
            cycles = sum(p.cycles for p in packets)
            macs = sum(p.macs for p in packets)
            entry = {"name": name, "steps": len(packets),
                     "actual_result_patches": sum(bool(p.source) for p in packets),
                     "input_bytes": sum(p.inputs.nbytes for p in packets),
                     "output_bytes": sum(p.expected.nbytes for p in packets),
                     "publication_bytes": compact.nbytes,
                     "gemm_macs": macs, "all_engine_compute_cycles": cycles,
                     "all_engine_compute_ms": cycles / FABRIC_HZ * 1000,
                     "samples_s": samples, **statistics(samples)}
            entry["gemm_macs_per_wall_second"] = macs / (entry["median_ms"] / 1000)
            report["chains"].append(entry)
            print(f"M3 CHAIN {name} PASS steps={entry['steps']} "
                  f"median_ms={entry['median_ms']:.6f} p95_ms={entry['p95_ms']:.6f}", flush=True)
        driver.select(0)
        runs = args.warmups + args.repeats
        expected_totals = [initial_totals[0] + len(gemm_packets) +
                           runs * sum(p.kind == 0 for p in chain_packets),
                           initial_totals[1] + len(sfpu_packets) +
                           runs * (len(choices) + sum(p.kind == 1 for p in chain_packets))]
        completed = [e.read(0x34) for e in driver.engines]
        if completed != expected_totals:
            raise AssertionError(f"physical completion totals {completed} != {expected_totals}")
        report["completed_descriptors"] = {"gemm": completed[0], "sfpu": completed[1]}
        report["status"] = "PASS"
    finally:
        driver.close()
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"M3 BOARD PASS output={args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
