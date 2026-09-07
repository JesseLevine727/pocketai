"""All sixteen changed-byte masks, both V regions, and the final cache slot."""
import ctypes as c
import unittest
import numpy as np
from ref.gpt2_quantized import dynamic_columns
from scripts.audit_m5_context import FINAL
from tests.m5_context.test_ready import configure, bind, LIMIT, WORK_START


class ChangedFeatures(unittest.TestCase):
    def test_all_masks_and_new_tail(self):
        base = configure('build/m5_tenth_reciprocal_v1/native.so')
        ready = configure(FINAL+'/native.so')
        shape = (12, 12, 1024, 64)
        for layer, initial in ((0, 31), (11, 1022)):
            with self.subTest(layer=layer, initial=initial):
                source = [np.full(shape, 512, np.int16), np.full(shape, 512, np.int16),
                          np.full(shape, 127, np.int8), np.full(shape[:-1], 1/256, np.float64)]
                arrays = [source, [a.copy() for a in source]]
                works = [c.create_string_buffer(4*1024*1024) for _ in range(2)]
                trace = c.create_string_buffer(8*1024*1024)
                bind(ready, arrays[1], works[1], trace)
                for step in range(2):
                    past = initial+step
                    qkv = np.full((1, 2304), 512, np.int16)
                    for head in range(12):
                        for group in range(16):
                            for lane in range(4):
                                if group & (1 << lane):
                                    qkv[0, 1536+head*64+group*4+lane] = -32768 if step else 1024
                    outputs = []
                    for lib, cache, work in zip((base, ready), arrays, works):
                        output = np.zeros((1, 768), np.int16); high = c.c_uint32()
                        status = lib.pa_m5_host_attention(c.addressof(work)+WORK_START,
                            LIMIT-WORK_START, *[a.ctypes.data for a in cache], layer,
                            qkv.ctypes.data, 1, past, output.ctypes.data, c.byref(high))
                        self.assertEqual(status, 0)
                        outputs.append(output)
                    np.testing.assert_array_equal(*outputs)
                    for i in (0, 1, 3): np.testing.assert_array_equal(arrays[0][i], arrays[1][i])
                    logical = arrays[1][2][layer].reshape(12, 64, 64, 16).transpose(0, 1, 3, 2).reshape(12, 1024, 64)
                    np.testing.assert_array_equal(logical[:, :past+1], arrays[0][2][layer, :, :past+1])
                    for head in range(12):
                        index = layer*12+head
                        address = (c.addressof(works[1])+LIMIT+index*65536 if index < 24 else
                                   c.addressof(trace)+0x80000+(index-24)*65536)
                        raw = np.ctypeslib.as_array((c.c_int8*65536).from_address(address))
                        values = raw.reshape(4, 1024, 16).transpose(1, 0, 2).reshape(1024, 64)
                        expected, _ = dynamic_columns(arrays[0][1][layer, head, :past+1], 1/256)
                        np.testing.assert_array_equal(values[:past+1], expected)


if __name__ == '__main__': unittest.main()
