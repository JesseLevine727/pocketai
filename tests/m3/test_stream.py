import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import struct
import numpy as np
from ref.sfpu_ref import dynamic_int8_parameters
from ref.sfpu_stream import Op, SfpuDescriptor, evaluate_and_pack
from ref.m3_packets import Packet, patch_input, read_packets, runtime_requant_parameters
from tests.m3.generate_sfpu_tables import tables
from tests.m3.generate_chain_vectors import build_chains


class StreamTests(unittest.TestCase):
    def test_descriptor_domains(self):
        for d in (SfpuDescriptor(0, 1), SfpuDescriptor(8, 1),
                  SfpuDescriptor(1, 0), SfpuDescriptor(1, 3073),
                  SfpuDescriptor(3, 1025), SfpuDescriptor(2, 768, shift=1),
                  SfpuDescriptor(4, 1, multiplier=1),
                  SfpuDescriptor(5, 1, multiplier=1 << 31),
                  SfpuDescriptor(5, 1, shift=32), SfpuDescriptor(7, 1, tag=-1)):
            with self.assertRaises(ValueError):
                d.validate()
        for op in Op:
            SfpuDescriptor(op, 1024 if op == Op.SOFTMAX else 3072).validate()

    def test_signed_planes_and_probability_endpoint(self):
        d = SfpuDescriptor(Op.ADD, 2)
        inputs, outputs = evaluate_and_pack(d, ([-32768, 32767], [-1, 1]))
        self.assertEqual(inputs.tolist(), [0xffff8000, 0x7fff, 0xffffffff, 1])
        self.assertEqual(outputs.tolist(), [0xffff8000, 0x7fff])
        inputs, outputs = evaluate_and_pack(SfpuDescriptor(3, 2),
                                            ([-1, 0], [False, True]))
        self.assertEqual(inputs.tolist(), [0xffff, 0x10000])
        self.assertEqual(outputs.tolist(), [0, 32768])
        with self.assertRaises(ValueError):
            evaluate_and_pack(d, ([1], [2]))

    def test_actual_result_patching(self):
        for mode, expected in ((1, [0xffffffff, 0x1234, 0x10000]),
                               (2, [0x134ff, 0x10000, 0x10000]),
                               (3, [0x1ffff, 0x11234, 0x10000])):
            # Mode2 writes the first two bytes only, preserving upper bytes.
            target = np.full(3, 0x10000, dtype="<u4")
            packet = Packet(1, (), 0, target, target, 0, mode=mode, count=2)
            patch_input(packet, np.array([0xffffffff, 0x1234], dtype="<u4"), target)
            self.assertEqual(target.tolist(), expected)

    def test_pinned_rom_reproduction(self):
        root = Path(__file__).resolve().parents[2]
        for name, contents in tables().items():
            self.assertEqual((root / "rtl/sfpu" / name).read_text(), contents)

    def test_packet_reader_rejects_truncation_and_trailing_data(self):
        data = struct.pack("<13I", 0x33504653, 1, 42, 1, 1, 0, 0, 7, 1, 1, 6, 0, 0)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "vectors.bin"
            path.write_bytes(data)
            packets, seed = read_packets(path)
            self.assertEqual((len(packets), seed, packets[0].cycles), (1, 42, 6))
            for invalid in (data[:-1], data + b"x"):
                path.write_bytes(invalid)
                with self.assertRaises(ValueError):
                    read_packets(path)

    def test_runtime_dynamic_scale_matches_frozen_reference(self):
        rng = np.random.default_rng(0x44594e33)
        cases = [np.array([0, 0]), np.array([32768, 0]),
                 np.array([-32768, 32767]), np.array([32] * 1024)]
        cases.extend(rng.integers(-32768, 32769, 768) for _ in range(100))
        for case in cases:
            self.assertEqual(runtime_requant_parameters(case.astype("<i4").view("<u4")),
                             dynamic_int8_parameters(case))

    def test_full_shape_chain_packet_dependencies(self):
        steps, _ = build_chains()
        tensors = {}
        patches = 0
        for m, inputs, expected in steps:
            packet = Packet(m[0], tuple(m[1:5]), m[5], inputs, expected, m[8], *m[9:16])
            if packet.source:
                source = tensors[packet.source]
                patched = inputs.copy()
                patch_input(packet, source, patched)
                np.testing.assert_array_equal(patched, inputs)
                if packet.kind and packet.parameters[0] == 5:
                    multiplier, shift = runtime_requant_parameters(source)
                    self.assertEqual((shift, multiplier), packet.parameters[2:])
                patches += 1
            old = tensors.get(packet.destination, np.empty(0, dtype="<u4"))
            updated = np.zeros(max(old.size, packet.offset + packet.result_count), dtype="<u4")
            updated[:old.size] = old
            updated[packet.offset:packet.offset + packet.result_count] = expected
            tensors[packet.destination] = updated
        self.assertEqual((len(steps), patches, tensors[9].size, tensors[25].size),
                         (315, 250, 768, 16))


if __name__ == "__main__":
    unittest.main()
