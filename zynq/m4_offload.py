"""Bounded-memory M4 scheduler, independent of the frozen GPT-2 references.

NumPy and packet backends only: no Torch/Transformers/safetensors or floating
GEMM. A9 owns scale metadata, scheduling and preallocated int16 DDR KV cache.
All planned GEMM/SFPU arithmetic goes through the selected packet backend.
"""
import math
from collections import Counter
import numpy as np
from ref.sfpu_stream import SfpuDescriptor, Op
from ref.m4_cpu import CpuGemm
from ref.m4_cpu_sfpu import CpuSfpu
from ref.m4_model_pack import ModelPack, file_sha256, tile_weights

CANDIDATE_SHA = 'a8d80d03c1aacc8a40f0f84962acd4033f0a1afb1343fd9e1ab0e9c50d0c397d'
PACK_SHA = 'd2aafeffd3e4b8a134b8e48796a1b0cf8f296a3bd150b79f07e2de037fae8fd6'


def affine_parameters(coefficients):
    c = np.asarray(coefficients, dtype=np.float64)
    if not np.all(np.isfinite(c)) or np.any(c < 0):
        raise ValueError('invalid affine coefficients')
    shift = 31
    while shift and np.any(np.rint(c * 2.0 ** shift) >= 2 ** 31):
        shift -= 1
    mult = np.rint(c * 2.0 ** shift).astype(np.int64)
    if np.any(mult >= 2 ** 31) or np.any((mult == 0) & (c != 0)):
        raise ValueError('unrepresentable affine scale')
    return mult.astype(np.int32), shift


def rounded_product(x, mult, shift):
    """Host range/score metadata, exact signed RNE before hardware narrowing."""
    product = np.asarray(x, dtype=np.int64) * np.asarray(mult, dtype=np.int64)
    quotient, remainder = np.divmod(np.abs(product), 1 << shift)
    quotient += ((remainder * 2 > (1 << shift)) |
                 ((remainder * 2 == (1 << shift)) & ((quotient % 2) == 1)))
    return np.where(product < 0, -quotient, quotient)


def exponent_for_range(maximum):
    value = np.asarray(maximum, dtype=np.float64)
    if np.any(~np.isfinite(value)) or np.any(value < 0):
        raise ValueError('invalid storage range')
    return np.ceil(np.log2(np.maximum(value * 256 / 32700, 1))).astype(np.int32)


def packet_words(op, planes):
    if op == Op.SOFTMAX:
        score, valid = planes
        return (np.asarray(score, dtype=np.int32).view(np.uint32) & 65535) | (np.asarray(valid, dtype=np.uint32) << 16)
    return np.ascontiguousarray(np.concatenate(planes), dtype=np.int32).view(np.uint32)


class CpuBackend:
    """Native exact operators; same packet scheduling boundary as the FPGA."""
    def __init__(self, gemm_library, sfpu_library):
        self.native_gemm = CpuGemm(gemm_library)
        self.native_sfpu = CpuSfpu(sfpu_library)
        self.counts = Counter()

    def gemm(self, a, tiles, n):
        self.counts['gemm_macs'] += a.shape[0] * a.shape[1] * n
        self.counts['gemm_logical_calls'] += 1
        self.counts['gemm_equivalent_packets'] += (n + 15) // 16
        return self.native_gemm(np.ascontiguousarray(a, dtype=np.int8), tiles, n)

    def sfpu(self, descriptor, words):
        self.counts['sfpu_' + str(int(descriptor.op))] += 1
        self.counts['sfpu_elements'] += descriptor.length
        return self.native_sfpu(descriptor, words)


class Runtime:
    def __init__(self, pack, backend, capacity=1024):
        if not 1 <= capacity <= 1024:
            raise ValueError('invalid KV capacity')
        if file_sha256(str(pack) + '/manifest.json') != PACK_SHA:
            raise ValueError('not the accepted v3 model-pack manifest')
        self.pack = ModelPack(pack, CANDIDATE_SHA)
        self.backend, self.capacity = backend, capacity
        # Persistent storage is bounded by model context, never grown by append.
        self.k = np.empty((12, 12, capacity, 64), dtype=np.int16)
        self.v = np.empty_like(self.k)
        self.k8 = np.empty(self.k.shape, dtype=np.int8)
        self.kunits = np.empty((12, 12, capacity), dtype=np.float64)
        self.length, self.failed = 0, False
        self.metadata_counts = Counter()

    def reset(self):
        # Stale values are inaccessible beyond logical length, then overwritten.
        self.length, self.failed = 0, False

    @property
    def cache_bytes(self):
        return self.k.nbytes + self.v.nbytes + self.k8.nbytes + self.kunits.nbytes

    def operator(self, op, planes, shift=0, multiplier=0):
        length = len(planes[0])
        if any(len(p) != length for p in planes):
            raise ValueError('operator plane lengths disagree')
        # A common affine shift/multiplier was chosen over the FULL row before
        # splitting. Vocabulary tiles must not silently choose different shifts.
        limit = 1024 if op == Op.SOFTMAX else 3072
        if op in (Op.SOFTMAX, Op.LAYERNORM) and length > limit:
            raise ValueError('normalization cannot be split')
        result = np.empty(length, dtype=np.int32)
        for start in range(0, length, limit):
            chunk = tuple(np.asarray(p)[start:start + limit] for p in planes)
            d = SfpuDescriptor(op, len(chunk[0]), shift, multiplier)
            result[start:start + limit] = self.backend.sfpu(d, packet_words(op, chunk))
        return result

    def affine(self, raw, coefficients, bias):
        mult, shift = affine_parameters(coefficients)
        bias = np.asarray(bias, dtype=np.int64)
        if np.any(bias < -(1 << 31)) or np.any(bias >= 1 << 31):
            raise ValueError('affine bias exceeds int32')
        return self.operator(Op.AFFINE, (raw, mult, bias), shift=shift).astype(np.int16)

    def requant(self, raw, unit):
        raw = np.asarray(raw, dtype=np.int32)
        if raw.ndim != 1 or np.any(raw < -32768) or np.any(raw > 32768):
            raise ValueError('invalid represented requantization input')
        maximum = int(np.max(np.abs(raw)))
        if maximum:
            m, remainder = divmod(127 << 24, maximum)
            m += int(2 * remainder > maximum or (2 * remainder == maximum and m % 2))
            effective = (1 << 24) / m * unit
        else:
            m, effective = 0, 1.0
        return self.operator(Op.REQUANT8, (raw,), shift=24, multiplier=m).astype(np.int8), effective

    def norm(self, rows, exponents, name):
        gain, bias = self.pack.norms[name]
        result = np.empty_like(rows)
        for index, row in enumerate(rows):
            e = int(exponents[index])
            r = row.astype(np.int64)
            variance = int(len(row) * (r @ r) - int(r.sum()) ** 2)
            eps = 1e-5 * 256 ** 2 * len(row) ** 2
            corrected = gain * math.sqrt((variance + eps) / (variance + eps / 2.0 ** (2 * e)))
            factor = 1
            while np.max(np.abs(corrected / factor)) > 32767 / 4096:
                factor *= 2
            g = np.rint(corrected * 4096 / factor).astype(np.int16)
            b = np.rint(bias * 256).astype(np.int64)
            if np.any(b < -32768) or np.any(b > 32767):
                raise ValueError('normalization bias exceeds M3 representation')
            if factor == 1:
                result[index] = self.operator(Op.LAYERNORM, (row, g, b))
            else:
                core = self.operator(Op.LAYERNORM, (row, g, np.zeros(len(row), dtype=np.int32)))
                result[index] = self.affine(core, np.full(len(row), factor, dtype=np.float64), b)
            self.metadata_counts['ln_epsilon_rows'] += 1
        return result

    def smooth(self, x, name):
        coefficients = 1 / self.pack.smoothing[name]
        mult, shift = affine_parameters(coefficients)
        prospective = rounded_product(x, mult, shift)
        overflow = np.any((prospective < -32768) | (prospective > 32767), axis=1)
        exponent = np.zeros(len(x), dtype=np.int32)
        if np.any(overflow):
            ranges = np.max(np.abs(x.astype(np.float64) * coefficients), axis=1) / 256
            exponent[overflow] = exponent_for_range(ranges[overflow])
        output = np.empty_like(x)
        for i, row in enumerate(x):
            output[i] = self.affine(row, coefficients / 2.0 ** int(exponent[i]), np.zeros(len(row), dtype=np.int32))
        return output, exponent

    def project(self, x, name, residual=None):
        if isinstance(x, tuple):
            x, balance_exp = x
        else:
            balance_exp = np.zeros(len(x), dtype=np.int32)
        tiles, static_scales, bias, (k, n) = self.pack.linears[name]
        q = np.empty(x.shape, dtype=np.int8)
        units = np.empty(len(x), dtype=np.float64)
        for i, row in enumerate(x):
            q[i], units[i] = self.requant(row, 1 / 256)
        sums = self.backend.gemm(q, tiles, n)
        scales = (units[:, None] * static_scales[None, :]) * 2.0 ** balance_exp[:, None]
        logical = sums * scales + bias
        if residual is None and name != 'lm_head':
            output = np.empty((len(x), n), dtype=np.int16)
            b = np.rint(bias * 256).astype(np.int64)
            for i in range(len(x)):
                output[i] = self.affine(sums[i], scales[i] * 256, b)
            return output
        if residual is None:
            exponents = exponent_for_range(np.max(np.abs(logical), axis=1))
        else:
            old, old_exp = residual
            previous = old * (2.0 ** old_exp[:, None] / 256)
            exponents = exponent_for_range(np.max(np.abs(logical) + np.abs(previous), axis=1))
        output = np.empty((len(x), n), dtype=np.int16)
        for i, exponent in enumerate(exponents):
            invunit = 256 / 2.0 ** int(exponent)
            branch = self.affine(sums[i], scales[i] * invunit, np.rint(bias * invunit).astype(np.int64))
            if residual is not None:
                aligned = self.affine(old[i], np.full(n, 2.0 ** int(old_exp[i] - exponent)), np.zeros(n, dtype=np.int32))
                branch = self.operator(Op.ADD, (aligned, branch)).astype(np.int16)
            output[i] = branch
        return output, exponents

    def attention(self, qkv, layer, past):
        batch = len(qkv)
        q, new_k, new_v = (x.reshape(batch, 12, 64).transpose(1, 0, 2) for x in np.split(qkv, 3, axis=1))
        end = past + batch
        self.k[layer, :, past:end] = new_k
        self.v[layer, :, past:end] = new_v
        context = np.empty((batch, 12, 64), dtype=np.int16)
        for head in range(12):
            for i in range(batch):
                self.k8[layer, head, past + i], self.kunits[layer, head, past + i] = self.requant(new_k[head, i], 1 / 256)
            queries, qunits = np.empty((batch, 64), dtype=np.int8), np.empty(batch)
            for i in range(batch):
                queries[i], qunits[i] = self.requant(q[head, i], 1 / 256)
            kt = tile_weights(self.k8[layer, head, :end].T)
            scores_wide = self.backend.gemm(queries, kt, end)
            for i in range(batch):
                length = past + i + 1
                raw = scores_wide[i, :length]
                coefficients = qunits[i] * self.kunits[layer, head, :length] * 32
                mult, shift = affine_parameters(coefficients)
                maximum = int(rounded_product(raw, mult, shift).max())
                centered = self.affine(raw, coefficients, np.full(length, -maximum, dtype=np.int64))
                probability = self.operator(Op.SOFTMAX, (centered, np.ones(length, dtype=bool)))
                p8, punit = self.requant(probability, 1 / 32768)
                value8 = np.empty((length, 64), dtype=np.int8)
                vunits = np.empty(64, dtype=np.float64)
                for channel in range(64):
                    value8[:, channel], vunits[channel] = self.requant(self.v[layer, head, :length, channel], 1 / 256)
                reduced = self.backend.gemm(p8.reshape(1, length), tile_weights(value8), 64)[0]
                context[i, head] = self.affine(reduced, punit * vunits * 256, np.zeros(64, dtype=np.int32))
        return context.reshape(batch, 768)

    def step(self, tokens, all_logits=False, emit_logits=True, capture=None):
        tokens = np.asarray(tokens)
        if (tokens.ndim != 1 or not 1 <= len(tokens) <= 16 or not np.issubdtype(tokens.dtype, np.integer)
                or np.any(tokens < 0) or np.any(tokens >= 50257) or self.length + len(tokens) > self.capacity):
            raise ValueError('invalid batch-one token block or context boundary')
        if self.failed:
            raise RuntimeError('failed runtime must be reset before reuse')
        past = self.length

        def trace(name, raw, unit=1 / 256):
            if capture is not None:
                capture(name, np.asarray(raw, dtype=np.float64) * unit)

        try:
            # Embedding addition is also routed through the selected SFPU.
            x = np.stack([self.operator(Op.ADD, (self.pack.embedding[token], self.pack.position[past + i])).astype(np.int16)
                          for i, token in enumerate(tokens)])
            exponent = np.zeros(len(tokens), dtype=np.int32)
            trace('embedding', x)
            for layer in range(12):
                p = f'h.{layer}'
                n1 = self.norm(x, exponent, p + '.ln_1')
                trace(p + '.ln1', n1 * self.pack.smoothing[p + '.attn.c_attn'])
                qkv = self.project(n1, p + '.attn.c_attn')
                trace(p + '.qkv', qkv)
                context = self.attention(qkv, layer, past)
                trace(p + '.context', context)
                residual, rexp = self.project(self.smooth(context, p + '.attn.c_proj'), p + '.attn.c_proj', (x, exponent))
                trace(p + '.residual', residual, 2.0 ** rexp[:, None] / 256)
                n2 = self.norm(residual, rexp, p + '.ln_2')
                trace(p + '.ln2', n2 * self.pack.smoothing[p + '.mlp.c_fc'])
                up = self.project(n2, p + '.mlp.c_fc')
                trace(p + '.up', up)
                gelu = np.stack([self.operator(Op.GELU, (row,)).astype(np.int16) for row in up])
                trace(p + '.gelu', gelu)
                x, exponent = self.project(self.smooth(gelu, p + '.mlp.c_proj'), p + '.mlp.c_proj', (residual, rexp))
                trace(p + '.output', x, 2.0 ** exponent[:, None] / 256)
            result = None
            if emit_logits:
                normed = self.norm(x, exponent, 'ln_f')
                trace('ln_f', normed * self.pack.smoothing['lm_head'])
                payload, le = self.project(normed if all_logits else normed[-1:], 'lm_head')
                result = payload * (2.0 ** le[:, None] / 256)
            self.length += len(tokens)
            return result
        except Exception:
            self.failed = True
            raise

    def prefill(self, tokens, block=16, capture=None):
        tokens = np.asarray(tokens)
        if (tokens.ndim != 1 or not len(tokens) or not np.issubdtype(tokens.dtype, np.integer)
                or np.any(tokens < 0) or np.any(tokens >= 50257) or not 1 <= block <= 16
                or self.length + len(tokens) > self.capacity):
            raise ValueError('invalid prefill/context request')
        result = None
        for start in range(0, len(tokens), block):
            result = self.step(tokens[start:start + block], emit_logits=start + block >= len(tokens), capture=capture)
        return result

    def generate(self, tokens, count=20):
        if count < 1 or len(tokens) + count > self.capacity:
            raise ValueError('invalid generation length')
        self.reset()
        logits = self.prefill(tokens)
        result = []
        for i in range(count):
            result.append(int(logits[-1].argmax()))
            if i + 1 < count:
                logits = self.step([result[-1]])
        return result
