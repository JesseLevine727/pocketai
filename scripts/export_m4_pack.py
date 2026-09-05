"""Export the frozen host candidate to compact mmap-ready board storage.

This does not program a board or claim physical qualification. Refuse existing
output directories so a failed/new pack never overwrites accepted evidence.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from ref.gpt2_scaled import ScaledGPT2
from ref.m4_model_pack import ModelPack, file_sha256, tile_weights
from tests.m4.qualify_scaled_quality import verify_frozen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('build/m4_pack_v2'))
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('refusing to overwrite existing model-pack directory')
    freeze = verify_frozen()
    candidate_hash = file_sha256('tests/m4/scaled_candidate.json')
    model = ScaledGPT2('build/m4_model', 'build/m4_calibration.json', freeze['alpha'])
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {'schema': 1, 'status': 'EXPORTED_NOT_PHYSICALLY_QUALIFIED',
                'candidate_sha256': candidate_hash, 'layout': 'N16_K_16_signed_int8',
                'exporter_sha256': file_sha256(__file__), 'arrays': {}, 'linears': {}, 'norms': list(model.norms),
                'notes': ['Int8 tiled weights, int16 embedding storage, float64 scale metadata only.',
                          'Read-only mmap arrays; no full floating-weight expansion on A9.',
                          'Tied embedding and balanced output views derive from the same checkpoint.']}

    def save(name, array):
        array = np.ascontiguousarray(array)
        path = args.output / (name + '.npy')
        np.save(path, array, allow_pickle=False)
        manifest['arrays'][name] = {'file': path.name, 'shape': list(array.shape),
                                    'dtype': array.dtype.str, 'sha256': file_sha256(path), 'payload_bytes': array.nbytes}

    save('embedding', model.embedding.astype('<i2'))
    save('position', model.position.astype('<i2'))
    for name, (weights, scales, bias) in model.linears.items():
        k, n = weights.shape
        codes = weights.astype(np.int8)
        if not np.array_equal(codes, weights):
            raise AssertionError('reference contains a non-int8 weight')
        tiles = tile_weights(codes)
        # Full reconstruction comparison, including the 50257 vocabulary tail.
        reconstructed = tiles.transpose(1, 0, 2).reshape(k, -1)[:, :n]
        np.testing.assert_array_equal(reconstructed, codes)
        save(name + '.tiles', tiles)
        save(name + '.scale', scales.astype('<f8'))
        save(name + '.bias', bias.astype('<f8'))
        save(name + '.smooth', model.smoothing[name].astype('<f8'))
        manifest['linears'][name] = [k, n]
    for name, (gain, bias) in model.norms.items():
        save(name + '.gain', gain.astype('<f8'))
        save(name + '.bias', bias.astype('<f8'))
    manifest['payload_bytes'] = sum(x['payload_bytes'] for x in manifest['arrays'].values())
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    pack = ModelPack(args.output, candidate_hash)
    if pack.payload_bytes != manifest['payload_bytes'] or len(pack.linears) != 49 or len(pack.norms) != 25:
        raise AssertionError('model-pack completeness mismatch')
    for name, (tiles, scales, bias, shape) in pack.linears.items():
        expected, es, eb = model.linears[name]
        for tile in range(len(tiles)):
            n = min(16, shape[1] - tile * 16)
            np.testing.assert_array_equal(tiles[tile, :, :n], expected[:, tile * 16:tile * 16 + n])
        np.testing.assert_array_equal(scales, es)
        np.testing.assert_array_equal(bias, eb)
        np.testing.assert_array_equal(pack.smoothing[name], model.smoothing[name])
    np.testing.assert_array_equal(pack.embedding, model.embedding)
    np.testing.assert_array_equal(pack.position, model.position)
    for name in pack.norms:
        for actual, expected in zip(pack.norms[name], model.norms[name]):
            np.testing.assert_array_equal(actual, expected)
    print('M4 PACK EXPORT EXACT PASS', json.dumps({'arrays': len(pack.arrays), 'linears': len(pack.linears),
          'norms': len(pack.norms), 'payload_bytes': pack.payload_bytes, 'payload_mib': pack.payload_bytes / 2 ** 20,
          'manifest_sha256': file_sha256(args.output / 'manifest.json')}), flush=True)


if __name__ == '__main__':
    main()
