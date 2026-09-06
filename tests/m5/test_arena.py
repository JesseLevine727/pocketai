import copy
import struct
import unittest
from pathlib import Path
from unittest import mock

from ref.m5_arena import (ARENA_BYTES, ARRAY_TABLE, CANDIDATE_SHA, DTYPES, HEADER_BYTES,
                          PACK_SHA, REGION_TABLE, array_specs, build_layout, export_model,
                          load_frozen_pack, make_header)


def source_manifest():
    arrays = {}
    for name, dtype, shape in array_specs():
        count = DTYPES[dtype][1]
        for dimension in shape:
            count *= dimension
        arrays[name] = {'dtype': dtype, 'shape': shape, 'payload_bytes': count,
                        'file': name + '.npy', 'sha256': '0' * 64}
    return {'schema': 1, 'candidate_sha256': CANDIDATE_SHA, 'layout': 'N16_K_16_signed_int8',
            'arrays': arrays, 'payload_bytes': sum(x['payload_bytes'] for x in arrays.values())}


class ArenaTests(unittest.TestCase):
    def setUp(self):
        self.source = source_manifest()
        self.layout = build_layout(self.source)

    def test_exact_inventory_and_numeric_layer_order(self):
        entries = self.layout['arrays']
        self.assertEqual(len(entries), 248)
        self.assertEqual(entries[2]['name'], 'h.0.attn.c_attn.tiles')
        self.assertEqual(entries[202]['name'], 'h.10.attn.c_attn.tiles')
        self.assertEqual(entries[-1]['name'], 'lm_head.smooth')
        self.assertEqual(self.layout['model_payload_bytes'], 205271824)

    def test_full_cache_and_fit(self):
        regions = {x['name']: x for x in self.layout['regions']}
        self.assertEqual(sum(regions[n]['bytes'] for n in ('k', 'v', 'k8', 'kunits')), 48365568)
        self.assertEqual(self.layout['mapped_bytes'] + self.layout['unmapped_bytes'], ARENA_BYTES)
        self.assertGreater(regions['unused']['bytes'], 1024 * 1024)
        self.assertEqual(regions['work']['bytes'], 4 * 1024 * 1024)
        self.assertEqual(regions['trace']['bytes'], 8 * 1024 * 1024)

    def test_page_partition_permissions_and_guards(self):
        cursor = 0
        for region in self.layout['regions']:
            self.assertEqual(region['offset'], cursor)
            self.assertEqual(region['offset'] % 4096, 0)
            self.assertEqual(region['bytes'] % 4096, 0)
            if region['name'] == 'model':
                self.assertEqual(region['permissions'], 1)
            elif region['name'].startswith('guard_') or region['name'] == 'unused':
                self.assertEqual(region['permissions'], 0)
            else:
                self.assertEqual(region['permissions'], 3)
            cursor += region['bytes']
        self.assertEqual(cursor, ARENA_BYTES)

    def test_arrays_aligned_bounded_nonoverlapping(self):
        cursor = HEADER_BYTES
        for array in self.layout['arrays']:
            self.assertGreaterEqual(array['offset'], cursor)
            self.assertEqual(array['offset'] % 64, 0)
            cursor = array['offset'] + array['bytes']
        self.assertLessEqual(cursor, self.layout['model_bytes'])

    def test_binary_header_has_exact_tables(self):
        header = make_header(self.layout)
        self.assertEqual(len(header), HEADER_BYTES)
        fixed = struct.unpack_from('<16I', header)
        self.assertEqual(fixed[:4], (0x354d4150, 1, HEADER_BYTES, ARENA_BYTES))
        self.assertEqual(fixed[11:], (1024, 12, 12, 768, 50257))
        self.assertEqual(header[64:96].hex(), PACK_SHA)
        self.assertEqual(header[96:128].hex(), CANDIDATE_SHA)
        for array in self.layout['arrays']:
            entry = struct.unpack_from('<8I', header, ARRAY_TABLE + array['id'] * 32)
            self.assertEqual(entry[:3], (array['id'], array['offset'], array['bytes']))
            self.assertEqual(entry[3], DTYPES[array['dtype']][0])
            self.assertEqual(entry[4], len(array['shape']))
            self.assertEqual(list(entry[5:]), array['shape'] + [0] * (3 - len(array['shape'])))
        for region in self.layout['regions']:
            entry = struct.unpack_from('<8I', header, REGION_TABLE + region['id'] * 32)
            self.assertEqual(entry[:4], (region['id'], region['offset'], region['bytes'], region['permissions']))
            self.assertEqual(entry[4:], (0, 0, 0, 0))
        self.assertFalse(any(header[REGION_TABLE + len(self.layout['regions']) * 32:]))

    def test_bad_source_inventory_and_descriptors_rejected(self):
        for field, bad in (('dtype', '|u1'), ('shape', [50257, 767]), ('payload_bytes', 2 ** 32)):
            source = copy.deepcopy(self.source)
            source['arrays']['embedding'][field] = bad
            with self.assertRaises(ValueError):
                build_layout(source)
        del self.source['arrays']['lm_head.tiles']
        with self.assertRaises(ValueError):
            build_layout(self.source)

    def test_bad_identity_and_payload_total_rejected(self):
        for field, bad in (('schema', 2), ('candidate_sha256', '0' * 64), ('payload_bytes', 1)):
            source = copy.deepcopy(self.source)
            source[field] = bad
            with self.assertRaises(ValueError):
                build_layout(source)

    def test_refuses_existing_destination_before_reading_pack(self):
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            export_model('not-a-pack', Path(__file__).parent)

    def test_checks_pinned_manifest_before_model_reader(self):
        with mock.patch('ref.m5_arena.file_sha256', return_value='0' * 64), \
                mock.patch('ref.m5_arena.ModelPack') as reader:
            with self.assertRaisesRegex(ValueError, 'frozen'):
                load_frozen_pack('untrusted')
            reader.assert_not_called()


if __name__ == '__main__':
    unittest.main()
