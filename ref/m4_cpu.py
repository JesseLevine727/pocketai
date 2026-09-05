"""Checked NumPy/ctypes interface for the M4 native tiled integer GEMM."""
import ctypes
from pathlib import Path
import numpy as np


class CpuGemm:
    def __init__(self, library):
        self.library = ctypes.CDLL(str(Path(library).resolve()))
        self.function = self.library.pa_m4_gemm
        self.function.argtypes = [np.ctypeslib.ndpointer(dtype=np.int8, flags='C_CONTIGUOUS'),
                                  np.ctypeslib.ndpointer(dtype=np.int8, flags='C_CONTIGUOUS'),
                                  np.ctypeslib.ndpointer(dtype=np.int32, flags=('C_CONTIGUOUS', 'WRITEABLE')),
                                  ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self.function.restype = ctypes.c_int
        self.library.pa_m4_cpu_backend.restype = ctypes.c_char_p
        self.backend = self.library.pa_m4_cpu_backend().decode()

    def __call__(self, a, tiles, n, output=None):
        a, tiles = np.asarray(a), np.asarray(tiles)
        if a.dtype != np.int8 or a.ndim != 2 or not a.flags.c_contiguous:
            raise ValueError('A must be contiguous int8 [M,K]')
        m, k = a.shape
        if not 1 <= m <= 16 or not 1 <= k <= 3072 or not 1 <= n <= 50257:
            raise ValueError('GEMM dimensions outside M4 native contract')
        if tiles.dtype != np.int8 or tiles.shape != ((n + 15) // 16, k, 16) or not tiles.flags.c_contiguous:
            raise ValueError('B must be contiguous int8 [N16,K,16]')
        if output is None:
            output = np.empty((m, n), dtype=np.int32)
        if output.shape != (m, n) or output.dtype != np.int32 or not output.flags.c_contiguous or not output.flags.writeable:
            raise ValueError('output must be writable contiguous int32 [M,N]')
        if np.shares_memory(output, a) or np.shares_memory(output, tiles):
            raise ValueError('GEMM output may not alias its inputs')
        if self.function(a, tiles, output, m, k, n):
            raise RuntimeError('native GEMM rejected dimensions')
        return output
