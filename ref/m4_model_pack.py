"""NumPy-only, hash-checked, read-only memory-mapped M4 model-pack reader.

No Torch, Transformers, safetensors, PYNQ or expanded floating weights needed
on the board. This is a storage contract, not a completed offload runtime.
"""
import hashlib
import json
from pathlib import Path
import numpy as np


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def tile_weights(weights):
    weights = np.asarray(weights)
    if weights.dtype != np.int8 or weights.ndim != 2 or not 1 <= weights.shape[0] <= 3072 or weights.shape[1] < 1:
        raise ValueError('expected signed int8 [K,N], K<=3072')
    k, n = weights.shape
    result = np.zeros(((n + 15) // 16, k, 16), dtype=np.int8)
    for tile in range(len(result)):
        count = min(16, n - tile * 16)
        result[tile, :, :count] = weights[:, tile * 16:tile * 16 + count]
    return result


class ModelPack:
    def __init__(self, directory, expected_candidate_sha256, verify=True):
        self.directory = Path(directory).resolve()
        self.manifest = json.loads((self.directory / 'manifest.json').read_text())
        if self.manifest['schema'] != 1 or self.manifest['candidate_sha256'] != expected_candidate_sha256:
            raise ValueError('model-pack version/candidate mismatch')
        if self.manifest['layout'] != 'N16_K_16_signed_int8':
            raise ValueError('unsupported model-pack layout')
        expected_linears = {f'h.{i}.{op}': list(shape) for i in range(12)
                            for op, shape in (('attn.c_attn', (768, 2304)), ('attn.c_proj', (768, 768)),
                                              ('mlp.c_fc', (768, 3072)), ('mlp.c_proj', (3072, 768)))}
        expected_linears['lm_head'] = [768, 50257]
        expected_norms = {f'h.{i}.ln_{j}' for i in range(12) for j in (1, 2)} | {'ln_f'}
        if self.manifest['linears'] != expected_linears or set(self.manifest['norms']) != expected_norms:
            raise ValueError('incomplete or incorrect GPT-2 operation inventory')
        self.arrays = {}
        for name, entry in self.manifest['arrays'].items():
            path = (self.directory / entry['file']).resolve()
            if path.parent != self.directory:
                raise ValueError('model-pack asset escapes pack directory')
            if verify and file_sha256(path) != entry['sha256']:
                raise ValueError('model-pack array hash mismatch: ' + name)
            array = np.load(path, mmap_mode='r', allow_pickle=False)
            if list(array.shape) != entry['shape'] or array.dtype.str != entry['dtype'] or not array.flags.c_contiguous:
                raise ValueError('model-pack array descriptor mismatch: ' + name)
            self.arrays[name] = array
        self.embedding = self.arrays['embedding']
        self.position = self.arrays['position']
        if self.embedding.shape != (50257, 768) or self.position.shape != (1024, 768):
            raise ValueError('GPT-2 embedding shape mismatch')
        if self.embedding.dtype != np.dtype('<i2') or self.position.dtype != np.dtype('<i2'):
            raise ValueError('GPT-2 embedding dtype mismatch')
        self.linears, self.norms, self.smoothing = {}, {}, {}
        for name, shape in self.manifest['linears'].items():
            k, n = shape
            weight, scale, bias = (self.arrays[name + '.' + suffix] for suffix in ('tiles', 'scale', 'bias'))
            if weight.shape != ((n + 15) // 16, k, 16) or weight.dtype != np.int8 or scale.shape != (n,) or bias.shape != (n,):
                raise ValueError('linear array shapes disagree: ' + name)
            if scale.dtype != np.dtype('<f8') or bias.dtype != np.dtype('<f8'):
                raise ValueError('linear metadata must be float64')
            if not np.all(np.isfinite(scale)) or np.any(scale <= 0) or not np.all(np.isfinite(bias)):
                raise ValueError('nonfinite or nonpositive linear metadata')
            if n % 16 and np.any(weight[-1, :, n % 16:]):
                raise ValueError('nonzero vocabulary/column padding')
            self.linears[name] = (weight, scale, bias, (k, n))
            smooth = self.arrays[name + '.smooth']
            if smooth.shape != (k,) or smooth.dtype != np.dtype('<f8'):
                raise ValueError('smoothing shape/dtype mismatch')
            if not np.all(np.isfinite(smooth)) or np.any(smooth <= 0):
                raise ValueError('smoothing must be finite and positive')
            self.smoothing[name] = smooth
        for name in self.manifest['norms']:
            self.norms[name] = (self.arrays[name + '.gain'], self.arrays[name + '.bias'])
            if any(x.shape != (768,) or x.dtype != np.dtype('<f8') for x in self.norms[name]):
                raise ValueError('normalization shape/dtype mismatch')
            if any(not np.all(np.isfinite(x)) for x in self.norms[name]):
                raise ValueError('nonfinite normalization metadata')

    @property
    def payload_bytes(self):
        return sum(array.nbytes for array in self.arrays.values())
