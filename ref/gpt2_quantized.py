"""Full-model M4 *development* reference using the frozen M3 packet arithmetic.

This first candidate deliberately exposes clipping/quality failures; it is NOT
a qualified model pack. Float64 BLAS accelerates exact int8 dot products on
the host: each product/partial sum is an integer below 2^26, so binary64 is
exact. SFPU operations use the independent frozen Python-integer reference.
All floating calculations outside GEMM are explicit scale metadata, not fabric.
"""
from collections import Counter
from pathlib import Path
import numpy as np
from safetensors.numpy import load_file
from ref import sfpu_ref as sf


def rne_shift(values, shift):
    """Vectorized signed RNE using integer magnitudes; inputs fit int64."""
    values = np.asarray(values, dtype=np.int64)
    if not 0 <= shift <= 31 or np.any(values == np.iinfo(np.int64).min):
        raise ValueError('invalid signed shift domain')
    magnitude = np.abs(values)
    quotient = magnitude >> shift
    remainder = magnitude - (quotient << shift)
    denominator = 1 << shift
    quotient += ((2 * remainder > denominator) |
                 ((2 * remainder == denominator) & ((quotient & 1) != 0)))
    return np.where(values < 0, -quotient, quotient)


def quantize_columns(matrix):
    """Static float-checkpoint quantization with per-output-channel scales."""
    matrix = np.asarray(matrix, dtype=np.float64)
    maximum = np.abs(matrix).max(axis=0)
    scales = np.where(maximum == 0, 1.0, maximum / 127)
    quantized = np.clip(np.rint(matrix / scales), -127, 127).astype(np.int8)
    return quantized, scales


def dynamic_columns(raw, unit):
    """Exact M3 dynamic bridge independently applied to each column."""
    raw = np.asarray(raw, dtype=np.int64)
    maximum = np.abs(raw).max(axis=0)
    multipliers = np.asarray([sf.rne_div(127 << 24, int(a)) if a else 0 for a in maximum], dtype=np.int64)
    quantized = np.clip(rne_shift(raw * multipliers, 24), -128, 127).astype(np.int8)
    scales = np.asarray([(1 << 24) / int(m) * unit if m else 1.0 for m in multipliers])
    return quantized, scales


def affine_metadata(scales):
    scales = np.asarray(scales, dtype=np.float64)
    if np.any(~np.isfinite(scales)) or np.any(scales < 0):
        raise ValueError('nonnegative finite scales required')
    shift = 31
    while shift > 0 and np.any(np.rint(scales * (1 << shift)) >= (1 << 31)):
        shift -= 1
    multipliers = np.rint(scales * (1 << shift)).astype(np.int64)
    if np.any(multipliers >= (1 << 31)):
        raise ValueError('scale is unrepresentable')
    if np.any((multipliers == 0) & (scales != 0)):
        raise ValueError('nonzero scale underflows to zero')
    return multipliers, shift


class QuantizedGPT2:
    def __init__(self, directory):
        raw = load_file(str(Path(directory) / 'model.safetensors'))
        self.stats = Counter()
        self.maxima = {}
        self.embedding = self.narrow(np.rint(raw['wte.weight'].astype(np.float64) * 256), 'weight.embedding')
        self.position = self.narrow(np.rint(raw['wpe.weight'].astype(np.float64) * 256), 'weight.position')
        self.norms, self.linears = {}, {}
        for name in [f'h.{i}.ln_{j}' for i in range(12) for j in (1, 2)] + ['ln_f']:
            gain, bias = raw[name + '.weight'].astype(np.float64), raw[name + '.bias'].astype(np.float64)
            factor = 1
            while np.max(gain / factor) > 32767 / 4096 or np.min(gain / factor) < -8:
                factor *= 2
            # Represent out-of-range gamma without clipping it: LN(gamma/f,0)
            # followed by AFFINE(f,beta). Extra rounding is part of this model,
            # not a change to the frozen M3 LN operator equation.
            self.norms[name] = (np.rint(gain * 4096 / factor).astype(np.int16),
                                self.narrow(np.rint(bias * 256), 'weight.' + name), factor)
        for layer in range(12):
            for operation in ('attn.c_attn', 'attn.c_proj', 'mlp.c_fc', 'mlp.c_proj'):
                name = f'h.{layer}.{operation}'
                q, scale = quantize_columns(raw[name + '.weight'])
                self.linears[name] = (q.astype(np.float64), scale,
                                      np.rint(raw[name + '.bias'].astype(np.float64) * 256).astype(np.int64))
        q, scale = quantize_columns(raw['wte.weight'].T)
        self.linears['lm_head'] = (q.astype(np.float64), scale, np.zeros(50257, dtype=np.int64))

    def narrow(self, value, name):
        value = np.asarray(value, dtype=np.int64)
        self.stats[name + '.elements'] += value.size
        self.stats[name + '.clipped'] += int(np.count_nonzero((value < -32768) | (value > 32767)))
        self.maxima[name] = max(self.maxima.get(name, 0), int(np.abs(value).max(initial=0)))
        return np.clip(value, -32768, 32767).astype(np.int16)

    def affine(self, raw, scales, bias, name):
        mult, shift = affine_metadata(scales)
        out = rne_shift(np.asarray(raw, dtype=np.int64) * mult, shift) + bias
        return self.narrow(out, name)

    def norm(self, x, name):
        gain, bias, factor = self.norms[name]
        if factor == 1:
            return np.stack([sf.layernorm_int(row, gain, bias) for row in x])
        self.stats[name + '.decomposed_rows'] += len(x)
        first = np.stack([sf.layernorm_int(row, gain, np.zeros_like(bias)) for row in x])
        return self.narrow(first.astype(np.int64) * factor + bias, name + '.postscale')

    def linear(self, x, name):
        weights, scale, bias = self.linears[name]
        rows = []
        for row in x:
            q, s = dynamic_columns(row[:, None], 1 / 256)
            # All int8 products/partial sums fit signed 27 bits; binary64
            # accumulation is exact. No float32 or reduced-precision BLAS.
            sums = (q[:, 0].astype(np.float64) @ weights).astype(np.int64)
            rows.append(self.affine(sums, s[0] * scale * 256, bias, name))
        return np.stack(rows)

    def forward(self, tokens, cache=None, all_logits=False, capture=False):
        tokens = np.asarray(tokens)
        if tokens.ndim != 1 or tokens.size == 0 or not np.issubdtype(tokens.dtype, np.integer) or np.any(tokens < 0) or np.any(tokens >= 50257):
            raise ValueError('nonempty batch-one token vector required')
        if cache is not None and len(cache) != 12:
            raise ValueError('cache must have twelve layers')
        past = 0 if cache is None else cache[0][0].shape[1]
        if past + tokens.size > 1024:
            raise ValueError('position limit exceeded')
        x = self.narrow(self.embedding[tokens].astype(np.int64) + self.position[past:past + len(tokens)], 'embedding')
        trace = {'embedding': x.copy()} if capture else {}
        next_cache = []
        for layer in range(12):
            prefix = f'h.{layer}'
            n1 = self.norm(x, prefix + '.ln_1')
            qkv = self.linear(n1, prefix + '.attn.c_attn')
            q, k, v = (part.reshape(-1, 12, 64).transpose(1, 0, 2) for part in np.split(qkv, 3, axis=-1))
            if cache is not None:
                pk, pv = cache[layer]
                if pk.shape != (12, past, 64) or pv.shape != pk.shape:
                    raise ValueError('inconsistent cache shape')
                k, v = np.concatenate((pk, k), axis=1), np.concatenate((pv, v), axis=1)
            next_cache.append((k.copy(), v.copy()))
            context = np.empty((len(tokens), 12, 64), dtype=np.int16)
            for head in range(12):
                # K has a scale per token/column: adding later tokens cannot
                # change the already-cached K quantization.
                k8, sk = dynamic_columns(k[head].T, 1 / 256)
                for row in range(len(tokens)):
                    length = past + row + 1
                    q8, sq = dynamic_columns(q[head, row, :, None], 1 / 256)
                    sums = q8[:, 0].astype(np.int64) @ k8[:, :length].astype(np.int64)
                    scores = self.affine(sums, sq[0] * sk[:length] * 32, np.zeros(length, dtype=np.int64), prefix + '.scores')
                    prob = sf.softmax_int(scores, np.ones(length, dtype=bool))
                    p8, sp = dynamic_columns(prob[:, None], 1 / 32768)
                    # V scale is per feature over ONLY the causal prefix.
                    # Including future values here would violate causality and
                    # make cached decode differ from complete prefill.
                    v8, sv = dynamic_columns(v[head, :length], 1 / 256)
                    value = p8[:, 0].astype(np.int64) @ v8.astype(np.int64)
                    context[row, head] = self.affine(value, sp[0] * sv * 256, np.zeros(64, dtype=np.int64), prefix + '.context')
            context = context.reshape(-1, 768)
            attn = self.linear(context, prefix + '.attn.c_proj')
            residual = self.narrow(x.astype(np.int64) + attn, prefix + '.residual')
            n2 = self.norm(residual, prefix + '.ln_2')
            up = self.linear(n2, prefix + '.mlp.c_fc')
            gelu = np.stack([sf.gelu_int(row) for row in up])
            down = self.linear(gelu, prefix + '.mlp.c_proj')
            x = self.narrow(residual.astype(np.int64) + down, prefix + '.output')
            if capture:
                for name, value in (('ln1', n1), ('qkv', qkv), ('context', context),
                                    ('attn', attn), ('residual', residual), ('ln2', n2),
                                    ('up', up), ('gelu', gelu), ('down', down), ('output', x)):
                    trace[f'{prefix}.{name}'] = value.copy()
        x = self.norm(x, 'ln_f')
        if capture:
            trace['ln_f'] = x.copy()
        logits = self.linear(x if all_logits else x[-1:], 'lm_head')
        return logits, next_cache, trace

    def generate(self, tokens, count=20):
        if count < 1 or len(tokens) + count > 1024:
            raise ValueError('invalid generation length')
        logits, cache, _ = self.forward(tokens)
        generated = []
        for step in range(count):
            token = int(np.argmax(logits[-1]))
            generated.append(token)
            if step + 1 < count:
                logits, cache, _ = self.forward([token], cache)
        return generated
