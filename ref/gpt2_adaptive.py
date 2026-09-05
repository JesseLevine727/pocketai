"""M4 v3 development candidate: range-safe post-nonlinearity balancing.

Preserves frozen v2 unchanged. The only change is an explicit per-row exponent
when context/post-GELU balancing would overflow int16. Weights, calibration,
quality thresholds, M3 operators and every non-overflow output remain unchanged.
"""
import numpy as np
from ref.gpt2_scaled import ScaledGPT2, storage_exponent
from ref.gpt2_quantized import affine_metadata, rne_shift


class AdaptiveGPT2(ScaledGPT2):
    def __init__(self, directory, calibration, alpha=0.5):
        super().__init__(directory, calibration, alpha)
        self.identity['version'] = 'm4-adaptive-v3-development'

    def smooth(self, x, name):
        scales = 1 / self.smoothing[name]
        mult, shift = affine_metadata(scales)
        prospective = rne_shift(x.astype(np.int64) * mult, shift)
        overflow = np.any((prospective < -32768) | (prospective > 32767), axis=1)
        exponent = np.zeros(len(x), dtype=np.int32)
        if not np.any(overflow):
            # Exact frozen v2 path, including its common affine shift.
            return super().smooth(x, name), exponent
        ranges = np.max(np.abs(x.astype(np.float64) * scales), axis=1) / 256
        exponent[overflow] = storage_exponent(ranges[overflow])
        result = np.stack([self.affine(row, scales / 2.0 ** int(exp),
                                      np.zeros(len(row), dtype=np.int64), name + '.smooth')
                           for row, exp in zip(x, exponent)])
        for exp in exponent:
            self.stats[name + '.balance_exponent_' + str(exp)] += 1
        return result, exponent

    def wide_linear(self, x, name):
        if not isinstance(x, tuple):
            return super().wide_linear(x, name)
        payload, exponent = x
        sums, scales, bias = super().wide_linear(payload, name)
        return sums, scales * 2.0 ** exponent[:, None], bias
