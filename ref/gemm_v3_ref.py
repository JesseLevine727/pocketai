"""M3 wide GEMM contract v1; legacy M2 reference stays unchanged."""
from dataclasses import dataclass
import numpy as np
from ref.gemm_ref import Descriptor

WIDE_RESULT_V1 = 0x100
MAX_WIDE_K = 3072


@dataclass(frozen=True)
class M3GemmDescriptor(Descriptor):
    def validate(self):
        if self.flags == 0:
            super().validate()
        elif self.flags == WIDE_RESULT_V1:
            if not 1 <= self.m <= 16 or not 1 <= self.n <= 16 or not 1 <= self.k <= MAX_WIDE_K:
                raise ValueError("wide GEMM dimensions out of range")
        else:
            raise ValueError("unsupported GEMM flags")

    @property
    def output_words(self):
        return self.m * (16 if self.flags == WIDE_RESULT_V1 else 8)


def gemm_wide_int32(a, b):
    a, b = np.asarray(a), np.asarray(b)
    if a.ndim != 2 or b.ndim != 2 or a.shape[1] != b.shape[0]:
        raise ValueError("GEMM matrix shapes do not match")
    M3GemmDescriptor(a.shape[0], b.shape[1], a.shape[1], flags=WIDE_RESULT_V1).validate()
    for x in (a, b):
        if not np.issubdtype(x.dtype, np.signedinteger):
            raise TypeError("signed integer operands required")
        if np.any(x < -128) or np.any(x > 127):
            raise ValueError("GEMM operands must fit signed int8")
    return (a.astype(np.int64) @ b.astype(np.int64)).astype(np.int32)
