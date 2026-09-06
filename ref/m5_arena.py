"""M5 ABI-v1 bounded arena and byte-preserving frozen-M4 serialization.

Provisioning only: this module does not schedule inference or service a run.
"""
import hashlib
import json
import math
import mmap
import os
from pathlib import Path
import struct

from ref.m4_model_pack import ModelPack, file_sha256

PACK_SHA = 'd2aafeffd3e4b8a134b8e48796a1b0cf8f296a3bd150b79f07e2de037fae8fd6'
CANDIDATE_SHA = 'a8d80d03c1aacc8a40f0f84962acd4033f0a1afb1343fd9e1ab0e9c50d0c397d'
ARENA_BASE = 0x40000000
ARENA_BYTES = 256 * 1024 * 1024
HEADER_BYTES = 65536
PAGE_BYTES = 4096
ARRAY_TABLE = 128
REGION_TABLE = 8192
CHUNK_BYTES = 1024 * 1024
DTYPES = {'|i1': (1, 1), '<i2': (2, 2), '<f8': (3, 8)}


def align(value, alignment):
    return (value + alignment - 1) // alignment * alignment


def array_specs():
    """Fixed numerical-layer order; never filesystem/dict/alphabetical order."""
    specs = [('embedding', '<i2', [50257, 768]), ('position', '<i2', [1024, 768])]

    def linear(name, k, n):
        specs.extend([(name + '.tiles', '|i1', [(n + 15) // 16, k, 16]),
                      (name + '.scale', '<f8', [n]), (name + '.bias', '<f8', [n]),
                      (name + '.smooth', '<f8', [k])])

    def norm(name):
        specs.extend([(name + '.gain', '<f8', [768]), (name + '.bias', '<f8', [768])])

    for layer in range(12):
        for op, k, n in (('attn.c_attn', 768, 2304), ('attn.c_proj', 768, 768),
                         ('mlp.c_fc', 768, 3072), ('mlp.c_proj', 3072, 768)):
            linear(f'h.{layer}.{op}', k, n)
        norm(f'h.{layer}.ln_1')
        norm(f'h.{layer}.ln_2')
    norm('ln_f')
    linear('lm_head', 768, 50257)
    return specs


def build_layout(pack_manifest):
    specs = array_specs()
    arrays = pack_manifest['arrays']
    if (pack_manifest['schema'] != 1 or pack_manifest['candidate_sha256'] != CANDIDATE_SHA
            or pack_manifest['layout'] != 'N16_K_16_signed_int8'
            or set(arrays) != {name for name, _, _ in specs}):
        raise ValueError('not the complete accepted model inventory')
    entries, cursor, payload_bytes = [], HEADER_BYTES, 0
    for index, (name, dtype, shape) in enumerate(specs):
        source = arrays[name]
        size = math.prod(shape) * DTYPES[dtype][1]
        if source['shape'] != shape or source['dtype'] != dtype or source['payload_bytes'] != size:
            raise ValueError('source array descriptor mismatch: ' + name)
        cursor = align(cursor, 64)
        entries.append({'id': index, 'name': name, 'offset': cursor, 'bytes': size,
                        'dtype': dtype, 'shape': shape,
                        'source_file': source['file'], 'source_sha256': source['sha256']})
        cursor += size
        payload_bytes += size
    if payload_bytes != pack_manifest['payload_bytes']:
        raise ValueError('model payload accounting mismatch')
    model_end = align(cursor, PAGE_BYTES)
    regions = []
    cursor = 0

    def region(name, size, permissions):
        nonlocal cursor
        if size <= 0 or size % PAGE_BYTES or cursor + size > ARENA_BYTES:
            raise ValueError('invalid or overflowing arena region: ' + name)
        regions.append({'id': len(regions), 'name': name, 'offset': cursor,
                        'bytes': size, 'permissions': permissions})
        cursor += size

    region('model', model_end, 1)
    for name, size in (('k', 12 * 12 * 1024 * 64 * 2), ('v', 12 * 12 * 1024 * 64 * 2),
                       ('k8', 12 * 12 * 1024 * 64), ('kunits', 12 * 12 * 1024 * 8),
                       ('work', 4 * 1024 * 1024), ('trace', 8 * 1024 * 1024)):
        region('guard_before_' + name, PAGE_BYTES, 0)
        region(name, size, 3)
    region('guard_after_trace', PAGE_BYTES, 0)
    region('unused', ARENA_BYTES - cursor, 0)
    if len(entries) != 248 or ARRAY_TABLE + len(entries) * 32 > REGION_TABLE:
        raise ValueError('array table does not fit ABI header')
    if REGION_TABLE + len(regions) * 32 > HEADER_BYTES:
        raise ValueError('region table does not fit ABI header')
    return {'schema': 1, 'status': 'SERIALIZED_NOT_PHYSICALLY_QUALIFIED',
            'source_pack_sha256': PACK_SHA, 'candidate_sha256': CANDIDATE_SHA,
            'arena_base': ARENA_BASE, 'arena_bytes': ARENA_BYTES, 'header_bytes': HEADER_BYTES,
            'model_bytes': model_end, 'model_payload_bytes': payload_bytes,
            'mapped_bytes': sum(x['bytes'] for x in regions if x['permissions']),
            'unmapped_bytes': sum(x['bytes'] for x in regions if not x['permissions']),
            'arrays': entries, 'regions': regions}


def make_header(layout):
    header = bytearray(HEADER_BYTES)
    fields = [0x354d4150, 1, HEADER_BYTES, ARENA_BYTES, len(layout['arrays']), 32,
              ARRAY_TABLE, len(layout['regions']), 32, REGION_TABLE,
              layout['model_bytes'], 1024, 12, 12, 768, 50257]
    struct.pack_into('<16I', header, 0, *fields)
    header[64:96] = bytes.fromhex(PACK_SHA)
    header[96:128] = bytes.fromhex(CANDIDATE_SHA)
    for entry in layout['arrays']:
        shape = entry['shape'] + [0] * (3 - len(entry['shape']))
        struct.pack_into('<8I', header, ARRAY_TABLE + entry['id'] * 32,
                         entry['id'], entry['offset'], entry['bytes'], DTYPES[entry['dtype']][0],
                         len(entry['shape']), *shape)
    for entry in layout['regions']:
        struct.pack_into('<8I', header, REGION_TABLE + entry['id'] * 32,
                         entry['id'], entry['offset'], entry['bytes'], entry['permissions'], 0, 0, 0, 0)
    return bytes(header)


def load_frozen_pack(directory):
    if file_sha256(Path(directory) / 'manifest.json') != PACK_SHA:
        raise ValueError('not the frozen accepted M4 model-pack manifest')
    return ModelPack(directory, CANDIDATE_SHA, verify=True)


def chunks(array):
    view = memoryview(array).cast('B')
    for start in range(0, len(view), CHUNK_BYTES):
        yield view[start:start + CHUNK_BYTES]


def export_model(pack_directory, output_directory):
    output_directory = Path(output_directory)
    if output_directory.exists():
        raise ValueError('refusing to overwrite existing M5 export directory')
    pack = load_frozen_pack(pack_directory)
    layout = build_layout(pack.manifest)
    output_directory.mkdir(parents=True, exist_ok=False)
    model_path = output_directory / 'model.bin'
    with model_path.open('xb') as target:
        target.truncate(layout['model_bytes'])
        target.write(make_header(layout))
        for entry in layout['arrays']:
            target.seek(entry['offset'])
            digest = hashlib.sha256()
            for chunk in chunks(pack.arrays[entry['name']]):
                target.write(chunk)
                digest.update(chunk)
            entry['payload_sha256'] = digest.hexdigest()
        target.flush()
        os.fsync(target.fileno())
    layout['model_sha256'] = file_sha256(model_path)
    layout['serialization_source_sha256'] = file_sha256(__file__)
    (output_directory / 'layout.json').write_text(json.dumps(layout, indent=2) + '\n')
    return verify_export(pack_directory, output_directory)


def verify_export(pack_directory, output_directory):
    pack = load_frozen_pack(pack_directory)
    output_directory = Path(output_directory)
    layout = json.loads((output_directory / 'layout.json').read_text())
    expected_layout = build_layout(pack.manifest)
    for key, value in expected_layout.items():
        if key == 'arrays':
            if len(layout[key]) != len(value):
                raise ValueError('exported array count mismatch')
            for expected, actual in zip(value, layout[key]):
                if any(actual.get(k) != v for k, v in expected.items()):
                    raise ValueError('exported array layout mismatch')
        elif layout.get(key) != value:
            raise ValueError('exported layout mismatch: ' + key)
    model_path = output_directory / 'model.bin'
    if model_path.stat().st_size != layout['model_bytes'] or file_sha256(model_path) != layout['model_sha256']:
        raise ValueError('exported model file identity mismatch')
    compared = 0
    with model_path.open('rb') as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as model:
        if model[:HEADER_BYTES] != make_header(expected_layout):
            raise ValueError('binary header differs from accepted model layout')
        cursor = HEADER_BYTES
        for entry in layout['arrays']:
            if any(model[cursor:entry['offset']]):
                raise ValueError('nonzero model alignment padding')
            cursor = entry['offset']
            digest = hashlib.sha256()
            for chunk in chunks(pack.arrays[entry['name']]):
                actual = model[cursor:cursor + len(chunk)]
                if actual != chunk:
                    raise ValueError('delivered array differs from M4: ' + entry['name'])
                digest.update(actual)
                cursor += len(chunk)
                compared += len(chunk)
            if digest.hexdigest() != entry['payload_sha256']:
                raise ValueError('delivered array digest mismatch')
        if any(model[cursor:]):
            raise ValueError('nonzero trailing model padding')
    return {'status': 'M5_MODEL_SERIALIZATION_EXACT_PASS_NOT_BOARD_QUALIFIED',
            'arrays_compared': len(layout['arrays']), 'payload_bytes_compared': compared,
            'model_bytes': layout['model_bytes'], 'mapped_bytes': layout['mapped_bytes'],
            'unmapped_bytes': layout['unmapped_bytes'], 'arena_bytes': ARENA_BYTES,
            'model_sha256': layout['model_sha256'],
            'layout_sha256': file_sha256(output_directory / 'layout.json')}
