"""M4 scaled/smoothed development candidate; NOT a qualified model pack.

M3 operator v1 is unchanged. Residual/logit int16 storage has explicit per-row
power-of-two units. The A9 computes scale/epsilon metadata. Linear inputs are
channel-balanced using TRAIN calibration, then W8A8; no float matrix operation
substitutes for a GEMM. Float64 BLAS represents the bounded integer sums exactly.
"""
import hashlib
import json
import math
from pathlib import Path
from collections import Counter
import numpy as np
from safetensors.numpy import load_file
from ref import sfpu_ref as sf
from ref.gpt2_quantized import (QuantizedGPT2, affine_metadata, dynamic_columns,
                                quantize_columns, rne_shift)


def storage_exponent(maximum):
    """Smallest nonnegative exponent giving 32700 raw headroom, per row."""
    maximum = np.asarray(maximum, dtype=np.float64)
    if np.any(~np.isfinite(maximum)) or np.any(maximum < 0):
        raise ValueError('finite nonnegative range required')
    return np.maximum(0, np.ceil(np.log2(np.maximum(maximum * 256 / 32700, 1)))).astype(np.int32)


def epsilon_correction(raw, exponent):
    """Correct LN(x/2^e, eps) to LN(x, eps) through gain metadata.

    Use exact integer variance numerator to avoid cancellation. This CPU
    metadata work must be included in the hybrid performance boundary.
    """
    raw = np.asarray(raw, dtype=np.int64)
    if raw.ndim != 1 or not len(raw) or not 0 <= exponent <= 30:
        raise ValueError('invalid scaled LayerNorm domain')
    length = len(raw)
    variance = int(length * (raw @ raw) - int(raw.sum()) ** 2)
    epsilon = sf.EPSILON * 256 ** 2 * length ** 2
    return math.sqrt((variance + epsilon) / (variance + epsilon / 2.0 ** (2 * exponent)))


def channel_balance(maxima, weights, alpha, gain=None):
    """Positive s: (x/s)@(s*W) preserves the original float linear map.

    A common normalization exploits int16/gain resolution without changing
    relative channel balancing. All observed ranges come from TRAIN only.
    """
    if not 0 <= alpha <= 1:
        raise ValueError('alpha outside [0,1]')
    maxima = np.maximum(np.asarray(maxima, dtype=np.float64), 1e-8)
    wmax = np.maximum(np.abs(weights).max(axis=1), 1e-8)
    scales = maxima ** alpha / wmax ** (1 - alpha)
    normalization = float(np.max(maxima / scales) / 64)
    if gain is not None:
        normalization = max(normalization, float(np.max(np.abs(gain) / scales) / 7.5))
    return scales * max(normalization, 1e-8)


class ScaledGPT2(QuantizedGPT2):
    def __init__(self, directory, calibration, alpha=0.5):
        directory, calibration = Path(directory), Path(calibration)
        metadata = json.loads(calibration.read_text())
        if metadata['source_split'] != 'train':
            raise ValueError('only training calibration is allowed')
        policy_hash = hashlib.sha256(Path('tests/m4/quality_policy.json').read_bytes()).hexdigest()
        if metadata['policy_sha256'] != policy_hash:
            raise ValueError('calibration quality policy mismatch')
        self.identity = {'version': 'm4-scaled-v2-development', 'alpha': alpha,
                         'calibration_sha256': hashlib.sha256(calibration.read_bytes()).hexdigest(),
                         'policy_sha256': policy_hash}
        raw = load_file(str(directory / 'model.safetensors'))
        self.stats, self.maxima = Counter(), {}
        self.embedding = self.narrow(np.rint(raw['wte.weight'].astype(np.float64) * 256), 'weight.embedding')
        self.position = self.narrow(np.rint(raw['wpe.weight'].astype(np.float64) * 256), 'weight.position')
        self.norms, self.linears, self.smoothing = {}, {}, {}
        consumers = {f'h.{i}.attn.c_attn': f'h.{i}.ln_1' for i in range(12)}
        consumers.update({f'h.{i}.mlp.c_fc': f'h.{i}.ln_2' for i in range(12)})
        consumers['lm_head'] = 'ln_f'
        names = [f'h.{i}.{op}' for i in range(12)
                 for op in ('attn.c_attn', 'attn.c_proj', 'mlp.c_fc', 'mlp.c_proj')] + ['lm_head']
        for name in names:
            weight = raw['wte.weight'].T if name == 'lm_head' else raw[name + '.weight']
            norm = consumers.get(name)
            gain = raw[norm + '.weight'].astype(np.float64) if norm else None
            smooth = channel_balance(metadata['channel_amax'][name], weight, alpha, gain)
            self.smoothing[name] = smooth
            q, scale = quantize_columns(weight.astype(np.float64) * smooth[:, None])
            bias = np.zeros(50257) if name == 'lm_head' else raw[name + '.bias'].astype(np.float64)
            self.linears[name] = (q.astype(np.float64), scale, bias)
            if norm:
                self.norms[norm] = (gain / smooth, raw[norm + '.bias'].astype(np.float64) / smooth)

    def norm(self, x, exponent, name):
        gain, bias = self.norms[name]
        result = []
        for row, exp in zip(x, exponent):
            corrected = gain * epsilon_correction(row, int(exp))
            factor = 1
            while np.max(np.abs(corrected / factor)) > 32767 / 4096:
                factor *= 2
            g = np.rint(corrected * 4096 / factor).astype(np.int16)
            b = np.rint(bias * 256).astype(np.int64)
            values = [int(a) for a in row]
            length, total = len(values), sum(values)
            variance = length * sum(a * a for a in values) - total * total
            denominator = math.isqrt((variance << 24) + sf.rne_div(length * length * (1 << 40), 100000))
            unbounded = np.asarray([sf.rne_div((length * a - total) * int(gg) * 256, denominator)
                                    for a, gg in zip(values, g)], dtype=np.int64)
            if factor == 1:
                # M3 LN rounds, adds bias, THEN saturates (not before bias).
                result.append(self.narrow(unbounded + b, name + '.out'))
            else:
                first = self.narrow(unbounded, name + '.core')
                result.append(self.narrow(first.astype(np.int64) * factor + b, name + '.out'))
            self.stats[name + '.epsilon_metadata_rows'] += int(exp != 0)
            self.stats[name + '.gain_decomposed_rows'] += int(factor != 1)
        return np.stack(result)

    def smooth(self, x, name):
        return self.affine(x, 1 / self.smoothing[name], np.zeros(x.shape[1], dtype=np.int64), name + '.smooth')

    def scores(self, sums, scales, name):
        # AFFINE's common bias removes the exact rounded maximum BEFORE
        # signed16 saturation. A common offset leaves softmax unchanged.
        # Only negative tails can saturate; their difference is already far
        # beyond M3's 4096-raw exp cutoff and hence has exactly zero weight.
        mult, shift = affine_metadata(scales)
        raw = rne_shift(sums * mult, shift)
        maximum = int(raw.max())
        if not -(1 << 31) <= -maximum < (1 << 31):
            raise ValueError('score centering bias exceeds M3 int32')
        centered = raw - maximum
        self.stats[name + '.intentional_zero_tail_clamps'] += int((centered < -32768).sum())
        self.stats[name + '.elements'] += len(raw)
        self.maxima[name + '.before_centering'] = max(self.maxima.get(name + '.before_centering', 0), int(np.abs(raw).max()))
        return np.clip(centered, -32768, 0).astype(np.int16)

    def wide_linear(self, x, name):
        weights, scale, bias = self.linears[name]
        q, units = dynamic_columns(x.T, 1 / 256)
        sums = (q.T.astype(np.float64) @ weights).astype(np.int64)
        return sums, units[:, None] * scale[None, :], bias

    def project(self, x, name, residual=None):
        sums, scales, bias = self.wide_linear(x, name)
        logical = sums * scales + bias
        if residual is None and name != 'lm_head':
            return np.stack([self.affine(s, c * 256, np.rint(bias * 256).astype(np.int64), name)
                             for s, c in zip(sums, scales)])
        # Choose common units before any narrowing. The bound covers each
        # addend and their sum, so ADD itself does not silently saturate.
        if residual is None:
            exponent = storage_exponent(np.max(np.abs(logical), axis=1))
        else:
            old, old_exp = residual
            old_logical = old * (2.0 ** old_exp[:, None] / 256)
            exponent = storage_exponent(np.max(np.abs(logical) + np.abs(old_logical), axis=1))
        outputs = []
        for index, exp in enumerate(exponent):
            invunit = 256 / 2.0 ** int(exp)
            branch = self.affine(sums[index], scales[index] * invunit,
                                 np.rint(bias * invunit).astype(np.int64), name + '.scaled')
            if residual is not None:
                previous = self.affine(old[index], np.full(old.shape[1], 2.0 ** int(old_exp[index] - exp)),
                                       np.zeros(old.shape[1], dtype=np.int64), name + '.align')
                branch = self.narrow(previous.astype(np.int64) + branch, name + '.residual')
            outputs.append(branch)
            self.stats[name + '.exponent_' + str(exp)] += 1
        return np.stack(outputs), exponent

    def forward(self, tokens, cache=None, all_logits=False, capture=False):
        tokens = np.asarray(tokens)
        if tokens.ndim != 1 or not tokens.size or not np.issubdtype(tokens.dtype, np.integer) or np.any(tokens < 0) or np.any(tokens >= 50257):
            raise ValueError('nonempty batch-one token vector required')
        if cache is not None and len(cache) != 12:
            raise ValueError('cache must have twelve layers')
        past = 0 if cache is None else cache[0][0].shape[1]
        if past + len(tokens) > 1024:
            raise ValueError('position limit exceeded')
        x = self.narrow(self.embedding[tokens].astype(np.int64) + self.position[past:past + len(tokens)], 'embedding')
        exponent = np.zeros(len(tokens), dtype=np.int32)
        trace = {'embedding': x.astype(np.float64) / 256} if capture else {}
        next_cache = []
        for layer in range(12):
            prefix = f'h.{layer}'
            n1 = self.norm(x, exponent, prefix + '.ln_1')
            qkv = self.project(n1, prefix + '.attn.c_attn')
            q, k, v = (part.reshape(-1, 12, 64).transpose(1, 0, 2) for part in np.split(qkv, 3, axis=-1))
            if cache is not None:
                pk, pv = cache[layer]
                if pk.shape != (12, past, 64) or pv.shape != pk.shape:
                    raise ValueError('inconsistent cache shape')
                k, v = np.concatenate((pk, k), axis=1), np.concatenate((pv, v), axis=1)
            next_cache.append((k.copy(), v.copy()))
            context = np.empty((len(tokens), 12, 64), dtype=np.int16)
            for head in range(12):
                k8, sk = dynamic_columns(k[head].T, 1 / 256)
                for row in range(len(tokens)):
                    length = past + row + 1
                    q8, sq = dynamic_columns(q[head, row, :, None], 1 / 256)
                    sums = q8[:, 0].astype(np.int64) @ k8[:, :length].astype(np.int64)
                    scores = self.scores(sums, sq[0] * sk[:length] * 32, prefix + '.scores')
                    prob = sf.softmax_int(scores, np.ones(length, dtype=bool))
                    p8, sp = dynamic_columns(prob[:, None], 1 / 32768)
                    v8, sv = dynamic_columns(v[head, :length], 1 / 256)
                    value = p8[:, 0].astype(np.int64) @ v8.astype(np.int64)
                    context[row, head] = self.affine(value, sp[0] * sv * 256, np.zeros(64, dtype=np.int64), prefix + '.context')
            context = context.reshape(-1, 768)
            residual, rexp = self.project(self.smooth(context, prefix + '.attn.c_proj'), prefix + '.attn.c_proj', (x, exponent))
            n2 = self.norm(residual, rexp, prefix + '.ln_2')
            up = self.project(n2, prefix + '.mlp.c_fc')
            gelu = np.stack([sf.gelu_int(row) for row in up])
            x, exponent = self.project(self.smooth(gelu, prefix + '.mlp.c_proj'), prefix + '.mlp.c_proj', (residual, rexp))
            if capture:
                for name, value in (('ln1', n1 * self.smoothing[prefix + '.attn.c_attn']),
                                    ('qkv', qkv), ('context', context),
                                    ('residual', residual * 2.0 ** rexp[:, None]),
                                    ('ln2', n2 * self.smoothing[prefix + '.mlp.c_fc']),
                                    ('up', up), ('gelu', gelu), ('output', x * 2.0 ** exponent[:, None])):
                    trace[f'{prefix}.{name}'] = value.astype(np.float64) / 256
        n = self.norm(x, exponent, 'ln_f')
        if capture:
            trace['ln_f'] = n * self.smoothing['lm_head'] / 256
        logits, lexp = self.project(n if all_logits else n[-1:], 'lm_head')
        # Returned float64 values are exact power-of-two representations of
        # integer payloads, NOT an extra floating projection or recomputation.
        return logits * (2.0 ** lexp[:, None] / 256), next_cache, trace
