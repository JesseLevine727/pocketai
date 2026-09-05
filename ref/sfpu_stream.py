"""M3 v1 descriptor and packet reference; arithmetic lives in sfpu_ref."""
from dataclasses import dataclass
from enum import IntEnum
import numpy as np
from ref.sfpu_ref import (add_int, affine_int, gelu_int, layernorm_int,
                         requantize_int8, softmax_int)


class Op(IntEnum):
    GELU = 1
    LAYERNORM = 2
    SOFTMAX = 3
    AFFINE = 4
    REQUANT8 = 5
    AFFINE_GELU = 6
    ADD = 7


@dataclass(frozen=True)
class SfpuDescriptor:
    op: int
    length: int
    shift: int = 0
    multiplier: int = 0
    tag: int = 0

    def validate(self):
        if self.op not in tuple(Op):
            raise ValueError("unsupported SFPU operation")
        if not 1 <= self.length <= (1024 if self.op == Op.SOFTMAX else 3072):
            raise ValueError("invalid SFPU length")
        if self.op in (Op.AFFINE, Op.AFFINE_GELU):
            if not 0 <= self.shift <= 31 or self.multiplier != 0:
                raise ValueError("invalid affine parameters")
        elif self.op == Op.REQUANT8:
            if not 0 <= self.shift <= 31 or not 0 <= self.multiplier < (1 << 31):
                raise ValueError("invalid requantization parameters")
        elif self.shift or self.multiplier:
            raise ValueError("unused parameters must be zero")
        if not 0 <= self.tag <= 0xffffffff:
            raise ValueError("tag must fit uint32")

    @property
    def planes(self):
        return 3 if self.op in (2, 4, 6) else 2 if self.op == 7 else 1

    @property
    def input_words(self):
        return self.planes * self.length


def evaluate_and_pack(d, planes):
    d.validate()
    arrays = tuple(np.asarray(p) for p in planes)
    expected_planes = 2 if d.op == Op.SOFTMAX else d.planes
    if len(arrays) != expected_planes or any(p.shape != (d.length,) for p in arrays):
        raise ValueError("SFPU input planes do not match descriptor")
    if d.op == Op.GELU:
        result = gelu_int(arrays[0])
    elif d.op == Op.LAYERNORM:
        result = layernorm_int(*arrays)
    elif d.op == Op.SOFTMAX:
        result = softmax_int(*arrays)
    elif d.op in (Op.AFFINE, Op.AFFINE_GELU):
        result = affine_int(*arrays, d.shift)
        if d.op == Op.AFFINE_GELU:
            result = gelu_int(result)
    elif d.op == Op.REQUANT8:
        result = requantize_int8(arrays[0], d.multiplier, d.shift)
    else:
        result = add_int(*arrays)
    if d.op == Op.SOFTMAX:
        inputs = (arrays[0].astype("<i4").view("<u4") & 0xffff) | (arrays[1].astype("<u4") << 16)
    else:
        inputs = np.concatenate(arrays).astype("<i4").view("<u4")
    outputs = result.astype("<i4").view("<u4")
    return inputs.copy(), outputs.copy()


def expected_compute_cycles(d, planes):
    """Independent accounting of v1 controller states, excluding DMA/output.

    A 64-cycle ALU request costs start + 65 wait observations + return = 67.
    A square-root request costs 43. Changes to microarchitecture must update
    this explicitly; it is not a throughput promise or arithmetic error budget.
    """
    if d.op == Op.GELU:
        return 6 * d.length
    if d.op == Op.LAYERNORM:
        return 281 * d.length + 313
    if d.op == Op.SOFTMAX:
        x, valid = (np.asarray(p) for p in planes)
        positive = int(np.count_nonzero(valid & (int(x[valid].max()) - x < 4096))) if valid.any() else 0
        return 15 * d.length + 137 * positive
    if d.op == Op.AFFINE_GELU:
        return 77 * d.length
    if d.op == Op.ADD:
        return 4 * d.length
    return 75 * d.length
