"""Native SFPU packet backend; packet layout remains independently specified."""
import ctypes
from pathlib import Path
import numpy as np
from ref import sfpu_ref as sf
from ref.sfpu_stream import SfpuDescriptor


class CpuSfpu:
    def __init__(self, library):
        self.library = ctypes.CDLL(str(Path(library).resolve()))
        self.function = self.library.pa_m4_sfpu
        self.function.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint32,
                                  np.ctypeslib.ndpointer(dtype=np.int32, flags='C_CONTIGUOUS'),
                                  np.ctypeslib.ndpointer(dtype=np.int32, flags=('C_CONTIGUOUS', 'WRITEABLE')),
                                  np.ctypeslib.ndpointer(dtype=np.int16, flags='C_CONTIGUOUS'),
                                  np.ctypeslib.ndpointer(dtype=np.uint32, flags='C_CONTIGUOUS')]
        self.function.restype = ctypes.c_int
        self.gelu = np.asarray(sf.GELU_TABLE, dtype=np.int16)
        self.exp = np.asarray(sf.EXP_TABLE, dtype=np.uint32)

    def __call__(self, descriptor, words, output=None):
        if not isinstance(descriptor, SfpuDescriptor):
            raise ValueError('M3 SFPU descriptor required')
        descriptor.validate()
        words = np.asarray(words)
        if words.dtype not in (np.dtype('<u4'), np.dtype('<i4')) or words.shape != (descriptor.input_words,) or not words.flags.c_contiguous:
            raise ValueError('contiguous M3 32-bit packet words required')
        if output is None:
            output = np.empty(descriptor.length, dtype=np.int32)
        if output.dtype != np.int32 or output.shape != (descriptor.length,) or not output.flags.c_contiguous or not output.flags.writeable:
            raise ValueError('invalid SFPU output storage')
        if np.shares_memory(output, words):
            raise ValueError('SFPU output may not alias inputs')
        status = self.function(descriptor.op, descriptor.length, descriptor.shift, descriptor.multiplier,
                               words.view(np.int32), output, self.gelu, self.exp)
        if status:
            raise ValueError('native SFPU rejected packet: ' + str(status))
        return output
