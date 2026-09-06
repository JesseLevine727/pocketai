#!/usr/bin/env python3
"""Independent Python checks for the portable M5 RV32 metadata foundation."""
import argparse
import ctypes
import hashlib
import json
import math
import mmap
from pathlib import Path
import struct
import numpy as np

from ref.gpt2_quantized import affine_metadata, dynamic_columns, rne_shift
from ref.gpt2_scaled import storage_exponent
from ref import sfpu_ref as sf
from ref.sfpu_ref import rne_div


def bits(value):
    return struct.pack('<d', float(value))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--library', required=True)
    args = parser.parse_args()
    lib = ctypes.CDLL(str(Path(args.library).resolve()))
    lib.pa_m5_rne_u64.argtypes = [ctypes.c_uint64, ctypes.c_uint64]
    lib.pa_m5_rne_u64.restype = ctypes.c_uint64
    lib.pa_m5_rne_i64.argtypes = [ctypes.c_int64, ctypes.c_uint64]
    lib.pa_m5_rne_i64.restype = ctypes.c_int64
    lib.pa_m5_rne_f64.argtypes = [ctypes.c_double]
    lib.pa_m5_rne_f64.restype = ctypes.c_uint64
    lib.pa_m5_rne_f64_signed.argtypes = [ctypes.c_double]
    lib.pa_m5_rne_f64_signed.restype = ctypes.c_int64
    lib.pa_m5_sqrt_f64.argtypes = [ctypes.c_double]
    lib.pa_m5_sqrt_f64.restype = ctypes.c_double
    lib.pa_m5_dynamic_multiplier.argtypes = [ctypes.c_uint32]
    lib.pa_m5_dynamic_multiplier.restype = ctypes.c_uint32
    lib.pa_m5_dynamic_unit.argtypes = [ctypes.c_uint32, ctypes.c_double]
    lib.pa_m5_dynamic_unit.restype = ctypes.c_double
    lib.pa_m5_affine_metadata.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]
    lib.pa_m5_affine_metadata.restype = ctypes.c_int
    lib.pa_m5_storage_exponent.argtypes = [ctypes.c_double]
    lib.pa_m5_storage_exponent.restype = ctypes.c_uint32
    lib.pa_m5_layernorm_metadata.argtypes = [ctypes.POINTER(ctypes.c_int16), ctypes.c_uint32,
        ctypes.c_uint32, ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_int16), ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_uint32)]
    lib.pa_m5_layernorm_metadata.restype = ctypes.c_int
    lib.pa_m5_arena_open.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32]
    lib.pa_m5_arena_open.restype = ctypes.c_int
    lib.pa_m5_arena_array.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
    lib.pa_m5_arena_array.restype = ctypes.c_void_p
    lib.pa_m5_model_open.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32]
    lib.pa_m5_model_open.restype = ctypes.c_int
    class Workspace(ctypes.Structure):
        _fields_ = [('base', ctypes.c_void_p), ('capacity', ctypes.c_uint32),
                    ('used', ctypes.c_uint32), ('high_water', ctypes.c_uint32)]
    lib.pa_m5_workspace_open.argtypes = [ctypes.POINTER(Workspace), ctypes.c_void_p, ctypes.c_uint32]
    lib.pa_m5_workspace_allocate.argtypes = [ctypes.POINTER(Workspace), ctypes.c_uint32, ctypes.c_uint32]
    lib.pa_m5_workspace_allocate.restype = ctypes.c_void_p
    lib.pa_m5_workspace_rewind.argtypes = [ctypes.POINTER(Workspace), ctypes.c_uint32]
    int16p = ctypes.POINTER(ctypes.c_int16); int8p = ctypes.POINTER(ctypes.c_int8)
    uint32p = ctypes.POINTER(ctypes.c_uint32); doublep = ctypes.POINTER(ctypes.c_double)
    lib.pa_m5_host_project.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
        ctypes.c_uint32, int16p, uint32p, ctypes.c_uint32, ctypes.c_int,
        int16p, uint32p, int16p, uint32p, uint32p]
    lib.pa_m5_host_project.restype = ctypes.c_int
    lib.pa_m5_host_smooth.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
        ctypes.c_uint32, int16p, ctypes.c_uint32, int16p, uint32p, uint32p]
    lib.pa_m5_host_smooth.restype = ctypes.c_int
    lib.pa_m5_host_tables.argtypes = [int16p, uint32p]
    lib.pa_m5_host_norm.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
        ctypes.c_uint32, int16p, uint32p, ctypes.c_uint32, int16p, uint32p]
    lib.pa_m5_host_norm.restype = ctypes.c_int
    lib.pa_m5_host_gelu.argtypes = [ctypes.c_void_p, ctypes.c_uint32, int16p,
        ctypes.c_uint32, int16p, uint32p]
    lib.pa_m5_host_gelu.restype = ctypes.c_int
    lib.pa_m5_host_attention.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
        int16p, int16p, int8p, doublep, ctypes.c_uint32, int16p,
        ctypes.c_uint32, ctypes.c_uint32, int16p, uint32p]
    lib.pa_m5_host_attention.restype = ctypes.c_int
    lib.pa_m5_host_forward.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
        int16p, int16p, int8p, doublep, uint32p, ctypes.c_uint32, ctypes.c_uint32,
        int16p, uint32p, uint32p]
    lib.pa_m5_host_forward.restype = ctypes.c_int
    trace_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32,
        ctypes.c_uint32, int16p, uint32p, ctypes.c_uint32, ctypes.c_uint32, doublep)
    lib.pa_m5_host_forward_trace.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_uint32, int16p, int16p, int8p, doublep, uint32p, ctypes.c_uint32,
        ctypes.c_uint32, int16p, uint32p, uint32p, trace_type, ctypes.c_void_p]
    lib.pa_m5_host_forward_trace.restype = ctypes.c_int
    lib.pa_m5_host_generate.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_uint32, int16p, int16p, int8p, doublep, uint32p, ctypes.c_uint32,
        ctypes.c_uint32, uint32p, int16p, uint32p, uint32p, uint32p]
    lib.pa_m5_host_generate.restype = ctypes.c_int
    gelu_table = np.asarray([int(x, 16) for x in Path('rtl/sfpu/gelu_q8.mem').read_text().split()], dtype=np.uint16).view(np.int16)
    exp_table = np.asarray([int(x, 16) for x in Path('rtl/sfpu/exp_q24.mem').read_text().split()], dtype=np.uint32)
    np.testing.assert_array_equal(gelu_table, np.asarray(sf.GELU_TABLE, dtype=np.int16))
    np.testing.assert_array_equal(exp_table, np.asarray(sf.EXP_TABLE, dtype=np.uint32))
    lib.pa_m5_host_tables(gelu_table.ctypes.data_as(int16p), exp_table.ctypes.data_as(uint32p))

    rng = np.random.default_rng(0x4D354E55)
    integer_cases = 0
    for denominator in list(range(1, 300)) + [2**s for s in range(1, 32)]:
        values = [0, 1, denominator // 2, denominator, 2**63 - 1]
        values += rng.integers(0, 2**63, 40, dtype=np.uint64).tolist()
        for value in values:
            assert lib.pa_m5_rne_u64(value, denominator) == rne_div(value, denominator)
            signed = -value if integer_cases & 1 else value
            if signed >= -(2**63) + 1 and signed <= 2**63 - 1:
                assert lib.pa_m5_rne_i64(signed, denominator) == rne_div(signed, denominator)
            integer_cases += 1

    float_values = [0.0, -0.0, 0.5, 1.5, 2.5, 2**31 - .5, 2**31 + .5]
    float_values += rng.uniform(0, 2**40, 50000).tolist()
    for value in float_values:
        assert lib.pa_m5_rne_f64(value) == int(np.rint(value))
        signed = -value if int(value) & 1 else value
        assert lib.pa_m5_rne_f64_signed(signed) == int(np.rint(signed))
    sqrt_values = [1.0, 2.0, 4.0, np.nextafter(1.0, 0.0), np.nextafter(1.0, 2.0)]
    sqrt_values += np.exp2(rng.uniform(-900, 900, 20000)).tolist()
    for value in sqrt_values:
        assert bits(lib.pa_m5_sqrt_f64(value)) == bits(math.sqrt(value))

    dynamic_cases = 0
    for maximum in list(range(0, 32769)) + rng.integers(1, 2**31, 10000).tolist():
        expected = 0 if maximum == 0 else rne_div(127 << 24, maximum)
        actual = lib.pa_m5_dynamic_multiplier(maximum)
        if expected >= 2**31:
            assert actual == 2**32 - 1
        else:
            assert actual == expected
            for unit in (1/256, 1/32768, 2.0**rng.integers(-20, 10)):
                reference = 1.0 if not expected else (1 << 24) / expected * unit
                assert bits(lib.pa_m5_dynamic_unit(actual, unit)) == bits(reference)
        dynamic_cases += 1

    pack = Path('build/m4_pack_v3')
    manifest = json.loads((pack / 'manifest.json').read_text())
    affine_sets = []
    for name, entry in manifest['arrays'].items():
        if name.endswith(('.scale', '.smooth')):
            array = np.load(pack / entry['file'], allow_pickle=False).astype(np.float64)
            affine_sets.append(array if name.endswith('.scale') else 1 / array)
    affine_sets += [10.0 ** rng.uniform(-8, 2, rng.integers(1, 4000)) for _ in range(120)]
    affine_values = 0
    for scales in affine_sets:
        source = np.ascontiguousarray(scales, dtype=np.float64)
        output = np.zeros(len(source), dtype=np.uint32)
        shift = ctypes.c_uint32()
        status = lib.pa_m5_affine_metadata(source.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), len(source),
            output.ctypes.data_as(ctypes.POINTER(ctypes.c_uint32)), ctypes.byref(shift))
        try:
            expected_mult, expected_shift = affine_metadata(scales)
        except ValueError:
            assert status == -2
            continue
        assert status == 0 and shift.value == expected_shift
        np.testing.assert_array_equal(output, expected_mult.astype(np.uint32))
        affine_values += len(source)

    storage_values = [0.0, 32700/256, 2*(32700/256), np.nextafter(32700/256, math.inf)]
    storage_values += (10.0 ** rng.uniform(-10, 7, 10000)).tolist()
    for value in storage_values:
        assert lib.pa_m5_storage_exponent(value) == int(storage_exponent([value])[0])

    metadata_cases = 0
    norm_names = sorted(manifest['norms'])
    for case in range(200):
        count = [1, 2, 64, 768, 3072][case % 5]
        values = rng.integers(-32768, 32768, count, dtype=np.int16)
        if case < len(norm_names):
            name = norm_names[case]
            gain = np.load(pack / manifest['arrays'][name+'.gain']['file'], allow_pickle=False)
            bias = np.load(pack / manifest['arrays'][name+'.bias']['file'], allow_pickle=False)
            values = rng.integers(-32768, 32768, 768, dtype=np.int16); count = 768
        else:
            gain = rng.normal(1, 5, count).astype(np.float64)
            bias = rng.normal(0, 3, count).astype(np.float64)
        exponent = case % 9
        raw = values.astype(np.int64)
        variance = count * int(raw @ raw) - int(raw.sum()) ** 2
        epsilon = 1e-5 * 256**2 * count**2
        correction = math.sqrt((variance + epsilon) / (variance + epsilon / 2.0**(2*exponent)))
        corrected = gain * correction
        factor = 1
        while np.max(np.abs(corrected / factor)) > 32767 / 4096:
            factor *= 2
        expected_g = np.rint(corrected * 4096 / factor).astype(np.int16)
        expected_b = np.rint(bias * 256).astype(np.int32)
        actual_g = np.zeros(count, dtype=np.int16); actual_b = np.zeros(count, dtype=np.int32)
        actual_factor = ctypes.c_uint32()
        status = lib.pa_m5_layernorm_metadata(
            values.ctypes.data_as(ctypes.POINTER(ctypes.c_int16)), count, exponent,
            np.ascontiguousarray(gain).ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            np.ascontiguousarray(bias).ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            actual_g.ctypes.data_as(ctypes.POINTER(ctypes.c_int16)),
            actual_b.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)), ctypes.byref(actual_factor))
        assert status == 0 and actual_factor.value == factor
        np.testing.assert_array_equal(actual_g, expected_g); np.testing.assert_array_equal(actual_b, expected_b)
        metadata_cases += 1

    model = Path('build/m5_arena.1Org4t/model/model.bin')
    with model.open('rb') as source, mmap.mmap(-1, 256*1024*1024) as image:
        image[:65536] = source.read(65536)
        backing = (ctypes.c_ubyte * len(image)).from_buffer(image)
        arena = (ctypes.c_uint64 * 3)() # pointer, uint32 bytes/pad, pointer
        assert lib.pa_m5_arena_open(arena, backing, len(image)) == 0
        model_storage = (ctypes.c_uint64 * 512)()
        assert lib.pa_m5_model_open(model_storage, backing, len(image)) == 0
        size = ctypes.c_uint32()
        first = lib.pa_m5_arena_array(arena, 0, ctypes.byref(size))
        assert first == ctypes.addressof(backing) + 65536 and size.value == 50257*768*2
        header = bytearray(image[:65536])
        corruptions = [0, 4, 8, 12, 16, 24, 40, 44, 48, 52, 56, 60, 64, 96,
                       128, 132, 136, 140, 144, 148, 8192, 8196, 8200, 8204]
        for offset in corruptions:
            image[offset] ^= 1
            assert lib.pa_m5_arena_open(arena, backing, len(image)) != 0
            image[:65536] = header
        work_bytes = (ctypes.c_ubyte * 4096)()
        workspace = Workspace()
        lib.pa_m5_workspace_open(ctypes.byref(workspace), work_bytes, len(work_bytes))
        first_alloc = lib.pa_m5_workspace_allocate(ctypes.byref(workspace), 13, 64)
        second_alloc = lib.pa_m5_workspace_allocate(ctypes.byref(workspace), 4000, 128)
        assert first_alloc == ctypes.addressof(work_bytes) and second_alloc is None
        assert workspace.used == 13 and workspace.high_water == 13
        third_alloc = lib.pa_m5_workspace_allocate(ctypes.byref(workspace), 128, 128)
        assert third_alloc == ctypes.addressof(work_bytes) + 128 and workspace.used == 256
        lib.pa_m5_workspace_rewind(ctypes.byref(workspace), 13)
        assert workspace.used == 13 and workspace.high_water == 256
        del backing, arena

    def affine(raw, scale, bias):
        mult, shift = affine_metadata(scale)
        return np.clip(rne_shift(raw.astype(np.int64) * mult, shift) + bias,
                       -32768, 32767).astype(np.int16)

    linear_names = ['h.0.attn.c_attn', 'h.0.attn.c_proj', 'h.0.mlp.c_fc',
                    'h.0.mlp.c_proj', 'lm_head']
    work = (ctypes.c_ubyte * (4*1024*1024))()
    model_file = Path('build/m5_arena.1Org4t/model/model.bin')
    operation_words = 0; operation_cases = 0; maximum_workspace = 0
    with model_file.open('rb') as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_COPY) as arena_image:
        arena_buffer = (ctypes.c_ubyte * len(arena_image)).from_buffer(arena_image)

        for selector, rows in ((0, 3), (2, 1)):
            name = linear_names[selector]; entry = manifest['linears'][name]; k, n = entry
            data = rng.integers(-20000, 20001, (rows, k), dtype=np.int16)
            input_exp = np.zeros(rows, dtype=np.uint32)
            output = np.zeros((rows, n), dtype=np.int16); output_exp = np.zeros(rows, dtype=np.uint32)
            high = ctypes.c_uint32()
            status = lib.pa_m5_host_project(arena_buffer, work, len(work), selector,
                data.ctypes.data_as(int16p), input_exp.ctypes.data_as(uint32p), rows, 0,
                None, None, output.ctypes.data_as(int16p), output_exp.ctypes.data_as(uint32p), ctypes.byref(high))
            assert status == 0
            tiles = np.load(pack / manifest['arrays'][name+'.tiles']['file'], allow_pickle=False)
            weights = tiles.transpose(1, 0, 2).reshape(k, -1)[:, :n]
            scales = np.load(pack / manifest['arrays'][name+'.scale']['file'], allow_pickle=False)
            biases = np.load(pack / manifest['arrays'][name+'.bias']['file'], allow_pickle=False)
            q, units = dynamic_columns(data.T, 1/256)
            sums = q.T.astype(np.int64) @ weights.astype(np.int64)
            expected = np.stack([affine(row, unit*scales*256, np.rint(biases*256).astype(np.int64))
                                 for row, unit in zip(sums, units)])
            np.testing.assert_array_equal(output, expected); np.testing.assert_array_equal(output_exp, 0)
            maximum_workspace = max(maximum_workspace, high.value); operation_words += output.size; operation_cases += 1

        for selector in (0, 3):
            name = linear_names[selector]; k, _ = manifest['linears'][name]
            data = rng.integers(-32768, 32768, (3, k), dtype=np.int16)
            output = np.zeros_like(data); exponents = np.zeros(3, dtype=np.uint32); high = ctypes.c_uint32()
            status = lib.pa_m5_host_smooth(arena_buffer, work, len(work), selector,
                data.ctypes.data_as(int16p), 3, output.ctypes.data_as(int16p),
                exponents.ctypes.data_as(uint32p), ctypes.byref(high))
            assert status == 0
            smoothing = np.load(pack / manifest['arrays'][name+'.smooth']['file'], allow_pickle=False)
            smooth_scales = 1 / smoothing
            mult, shift = affine_metadata(smooth_scales)
            prospective = rne_shift(data.astype(np.int64) * mult, shift)
            any_overflow = np.any((prospective < -32768) | (prospective > 32767), axis=1).any()
            expected_exp = np.zeros(3, dtype=np.uint32)
            if any_overflow:
                expected_exp = storage_exponent(np.max(np.abs(data.astype(np.float64)*smooth_scales), axis=1)/256).astype(np.uint32)
                expected = np.stack([affine(row, smooth_scales/2.0**int(exp), np.zeros(k, dtype=np.int64))
                                     for row, exp in zip(data, expected_exp)])
            else:
                expected = np.stack([affine(row, smooth_scales, np.zeros(k, dtype=np.int64)) for row in data])
            np.testing.assert_array_equal(output, expected); np.testing.assert_array_equal(exponents, expected_exp)
            maximum_workspace = max(maximum_workspace, high.value); operation_words += output.size; operation_cases += 1

        for selector, rows, residual_used in ((1, 2, True), (3, 1, True), (4, 1, False)):
            name = linear_names[selector]; k, n = manifest['linears'][name]
            data = rng.integers(-20000, 20001, (rows, k), dtype=np.int16)
            input_exp = np.arange(rows, dtype=np.uint32) + selector % 3
            residual = rng.integers(-20000, 20001, (rows, n), dtype=np.int16) if residual_used else None
            residual_exp = np.arange(rows, dtype=np.uint32) + 1 if residual_used else None
            output = np.zeros((rows, n), dtype=np.int16); output_exp = np.zeros(rows, dtype=np.uint32)
            high = ctypes.c_uint32()
            status = lib.pa_m5_host_project(arena_buffer, work, len(work), selector,
                data.ctypes.data_as(int16p), input_exp.ctypes.data_as(uint32p), rows, 1,
                None if residual is None else residual.ctypes.data_as(int16p),
                None if residual_exp is None else residual_exp.ctypes.data_as(uint32p),
                output.ctypes.data_as(int16p), output_exp.ctypes.data_as(uint32p), ctypes.byref(high))
            assert status == 0
            tiles = np.load(pack / manifest['arrays'][name+'.tiles']['file'], allow_pickle=False)
            weights = tiles.transpose(1, 0, 2).reshape(k, -1)[:, :n]
            static_scale = np.load(pack / manifest['arrays'][name+'.scale']['file'], allow_pickle=False)
            static_bias = np.load(pack / manifest['arrays'][name+'.bias']['file'], allow_pickle=False)
            q, units = dynamic_columns(data.T, 1/256)
            sums = q.T.astype(np.int64) @ weights.astype(np.int64)
            channels = units[:, None] * static_scale[None, :]
            channels = channels * (2.0 ** input_exp[:, None])
            logical = sums * channels + static_bias
            if residual is None:
                expected_exp = storage_exponent(np.max(np.abs(logical), axis=1)).astype(np.uint32)
            else:
                old_logical = residual * (2.0 ** residual_exp[:, None] / 256)
                expected_exp = storage_exponent(np.max(np.abs(logical)+np.abs(old_logical), axis=1)).astype(np.uint32)
            expected = []
            for row, exponent in enumerate(expected_exp):
                inverse = 256 / 2.0**int(exponent)
                branch = affine(sums[row], channels[row]*inverse,
                                np.rint(static_bias*inverse).astype(np.int64))
                if residual is not None:
                    aligned = affine(residual[row], np.full(n, 2.0**(int(residual_exp[row])-int(exponent))),
                                     np.zeros(n, dtype=np.int64))
                    branch = np.clip(branch.astype(np.int64)+aligned, -32768, 32767).astype(np.int16)
                expected.append(branch)
            np.testing.assert_array_equal(output, np.stack(expected)); np.testing.assert_array_equal(output_exp, expected_exp)
            maximum_workspace = max(maximum_workspace, high.value); operation_words += output.size; operation_cases += 1

        def norm_reference(data, exponents, name):
            gains = np.load(pack / manifest['arrays'][name+'.gain']['file'], allow_pickle=False)
            biases = np.load(pack / manifest['arrays'][name+'.bias']['file'], allow_pickle=False)
            result = []
            for row, exponent in zip(data, exponents):
                values = [int(x) for x in row]; length = len(values)
                variance = length * sum(x*x for x in values) - sum(values)**2
                epsilon = sf.EPSILON * 256**2 * length**2
                correction = math.sqrt((variance+epsilon)/(variance+epsilon/2.0**(2*int(exponent))))
                corrected = gains * correction; factor = 1
                while np.max(np.abs(corrected/factor)) > 32767/4096: factor *= 2
                gain_q = np.rint(corrected*4096/factor).astype(np.int16)
                bias_q = np.rint(biases*256).astype(np.int64)
                denominator = math.isqrt((variance << 24) + sf.rne_div(length*length*(1 << 40), 100000))
                unbounded = np.asarray([sf.rne_div((length*x-sum(values))*int(g)*256, denominator)
                                        for x, g in zip(values, gain_q)], dtype=np.int64)
                if factor == 1: row_out = np.clip(unbounded+bias_q, -32768, 32767)
                else: row_out = np.clip(np.clip(unbounded, -32768, 32767)*factor+bias_q, -32768, 32767)
                result.append(row_out.astype(np.int16))
            return np.stack(result)

        for selector, name in ((0, 'h.0.ln_1'), (1, 'h.0.ln_2'), (2, 'ln_f')):
            data = rng.integers(-32768, 32768, (3, 768), dtype=np.int16)
            exponents = np.asarray([0, 3, 8], dtype=np.uint32)
            output = np.zeros_like(data); high = ctypes.c_uint32()
            status = lib.pa_m5_host_norm(arena_buffer, work, len(work), selector,
                data.ctypes.data_as(int16p), exponents.ctypes.data_as(uint32p), 3,
                output.ctypes.data_as(int16p), ctypes.byref(high))
            assert status == 0
            np.testing.assert_array_equal(output, norm_reference(data, exponents, name))
            maximum_workspace = max(maximum_workspace, high.value); operation_words += output.size; operation_cases += 1

        gelu_input = rng.integers(-32768, 32768, 7000, dtype=np.int16)
        gelu_output = np.zeros_like(gelu_input); high = ctypes.c_uint32()
        assert lib.pa_m5_host_gelu(work, len(work), gelu_input.ctypes.data_as(int16p), len(gelu_input),
                                   gelu_output.ctypes.data_as(int16p), ctypes.byref(high)) == 0
        gelu_expected = np.concatenate([sf.gelu_int(gelu_input[i:i+3072])
                                        for i in range(0, len(gelu_input), 3072)])
        np.testing.assert_array_equal(gelu_output, gelu_expected)
        maximum_workspace = max(maximum_workspace, high.value); operation_words += len(gelu_input); operation_cases += 1
        del arena_buffer

    cache_k = np.zeros((12, 1024, 64), dtype=np.int16)
    cache_v = np.zeros_like(cache_k)
    cache_k8 = np.zeros_like(cache_k, dtype=np.int8)
    cache_units = np.zeros((12, 1024), dtype=np.float64)
    reference_k = np.zeros_like(cache_k); reference_v = np.zeros_like(cache_k)
    reference_k8 = np.zeros_like(cache_k8); reference_units = np.zeros_like(cache_units)

    def attention_reference(qkv, past):
        rows = len(qkv)
        q, new_k, new_v = (part.reshape(rows, 12, 64).transpose(1, 0, 2)
                           for part in np.split(qkv, 3, axis=-1))
        reference_k[:, past:past+rows] = new_k; reference_v[:, past:past+rows] = new_v
        result = np.empty((rows, 12, 64), dtype=np.int16)
        for head in range(12):
            for row in range(rows):
                code, unit = dynamic_columns(reference_k[head, past+row, :, None], 1/256)
                reference_k8[head, past+row] = code[:, 0]; reference_units[head, past+row] = unit[0]
            for row in range(rows):
                length = past + row + 1
                q8, qunit = dynamic_columns(q[head, row, :, None], 1/256)
                sums = q8[:, 0].astype(np.int64) @ reference_k8[head, :length].T.astype(np.int64)
                score_scale = qunit[0] * reference_units[head, :length] * 32
                mult, shift = affine_metadata(score_scale)
                raw = rne_shift(sums*mult, shift)
                scores = np.clip(raw-int(raw.max()), -32768, 0).astype(np.int16)
                probability = sf.softmax_int(scores, np.ones(length, dtype=bool))
                p8, punit = dynamic_columns(probability[:, None], 1/32768)
                v8, vunits = dynamic_columns(reference_v[head, :length], 1/256)
                value = p8[:, 0].astype(np.int64) @ v8.astype(np.int64)
                result[row, head] = affine(value, punit[0]*vunits*256, np.zeros(64, dtype=np.int64))
        return result.reshape(rows, 768)

    attention_words = 0
    for rows, past in ((5, 0), (2, 5)):
        qkv = rng.integers(-32768, 32768, (rows, 2304), dtype=np.int16)
        expected = attention_reference(qkv, past)
        actual = np.zeros((rows, 768), dtype=np.int16); high = ctypes.c_uint32()
        status = lib.pa_m5_host_attention(work, len(work), cache_k.ctypes.data_as(int16p),
            cache_v.ctypes.data_as(int16p), cache_k8.ctypes.data_as(int8p),
            cache_units.ctypes.data_as(doublep), 0, qkv.ctypes.data_as(int16p), rows, past,
            actual.ctypes.data_as(int16p), ctypes.byref(high))
        assert status == 0
        np.testing.assert_array_equal(actual, expected)
        np.testing.assert_array_equal(cache_k[:, :past+rows], reference_k[:, :past+rows])
        np.testing.assert_array_equal(cache_v[:, :past+rows], reference_v[:, :past+rows])
        np.testing.assert_array_equal(cache_k8[:, :past+rows], reference_k8[:, :past+rows])
        assert cache_units[:, :past+rows].tobytes() == reference_units[:, :past+rows].tobytes()
        maximum_workspace = max(maximum_workspace, high.value); attention_words += actual.size
    operation_cases += 2; operation_words += attention_words

    fixture_directory = Path('build/m4_runtime_fixtures')
    runtime_manifest = json.loads((fixture_directory / 'manifest.json').read_text())
    full_k = np.zeros((12, 12, 1024, 64), dtype=np.int16)
    full_v = np.zeros_like(full_k); full_k8 = np.zeros_like(full_k, dtype=np.int8)
    full_units = np.zeros((12, 12, 1024), dtype=np.float64)
    full_logits = np.zeros(50257, dtype=np.int16); full_exponent = np.zeros(1, dtype=np.uint32)
    model_high = ctypes.c_uint32()

    def cache_digest(length):
        digest = hashlib.sha256()
        for layer in range(12):
            keys = np.ascontiguousarray(full_k[layer, :, :length], dtype='<i2')
            values = np.ascontiguousarray(full_v[layer, :, :length], dtype='<i2')
            digest.update(f'{layer}:{keys.shape}:<i2'.encode())
            digest.update(keys.tobytes()); digest.update(values.tobytes())
        return digest.hexdigest()

    trace_names = {1: 'embedding', 2: 'ln1', 3: 'qkv', 4: 'context',
                   5: 'residual', 6: 'ln2', 7: 'up', 8: 'gelu',
                   9: 'output', 10: 'ln_f', 11: 'logits'}
    fixture_trace_checks = 0
    fixture_trace_words = 0
    full_model_input_tokens = 0
    with model_file.open('rb') as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_COPY) as arena_image:
        arena_buffer = (ctypes.c_ubyte * len(arena_image)).from_buffer(arena_image)

        for case in runtime_manifest['cases']:
            full_k.fill(0); full_v.fill(0); full_k8.fill(0); full_units.fill(0)
            tokens = np.asarray(case['input_tokens'], dtype=np.uint32)
            callback_errors = []
            seen = []

            def compare_trace(_context, kind, layer, values, exponents, rows, columns,
                              channel_scale, *, fixture=case):
                try:
                    base = trace_names[kind]
                    name = base if kind in (1, 10, 11) else f'h.{layer}.{base}'
                    actual = np.ctypeslib.as_array(values, shape=(rows*columns,)).reshape(rows, columns).astype(np.float64)
                    if exponents:
                        row_exponents = np.ctypeslib.as_array(exponents, shape=(rows,))
                        actual *= np.exp2(row_exponents.astype(np.float64))[:, None]
                    if channel_scale:
                        scales = np.ctypeslib.as_array(channel_scale, shape=(columns,))
                        actual *= scales[None, :]
                    actual /= 256.0
                    expected = np.load(fixture_directory / fixture['tensors'][name]['file'],
                                       allow_pickle=False)
                    np.testing.assert_array_equal(actual, expected, err_msg=name)
                    seen.append(name)
                    return 0
                except BaseException as error:
                    callback_errors.append(error)
                    return 1

            callback = trace_type(compare_trace)
            status = lib.pa_m5_host_forward_trace(arena_buffer, work, len(work),
                full_k.ctypes.data_as(int16p), full_v.ctypes.data_as(int16p),
                full_k8.ctypes.data_as(int8p), full_units.ctypes.data_as(doublep),
                tokens.ctypes.data_as(uint32p), len(tokens), 0,
                full_logits.ctypes.data_as(int16p), full_exponent.ctypes.data_as(uint32p),
                ctypes.byref(model_high), callback, None)
            if callback_errors:
                raise callback_errors[0]
            assert status == 0 and seen == list(case['tensors']), (case['id'], status,
                model_high.value, len(seen), seen[-3:],
                list(case['tensors'])[len(seen):len(seen)+3])
            assert cache_digest(len(tokens)) == case['cache_sha256']
            fixture_trace_checks += len(seen)
            fixture_trace_words += sum(np.prod(np.load(
                fixture_directory / entry['file'], mmap_mode='r', allow_pickle=False).shape)
                for entry in case['tensors'].values())
            full_model_input_tokens += len(tokens)

        generation_tokens = 0
        generation_steps = 0
        for case in runtime_manifest['generation']:
            full_k.fill(0); full_v.fill(0); full_k8.fill(0); full_units.fill(0)
            input_tokens = np.asarray(case['input_tokens'], dtype=np.uint32)
            for step, expected in enumerate(case['steps']):
                step_tokens = input_tokens if step == 0 else np.asarray(
                    [case['steps'][step-1]['token']], dtype=np.uint32)
                past = 0 if step == 0 else len(input_tokens) + step - 1
                status = lib.pa_m5_host_forward(arena_buffer, work, len(work),
                    full_k.ctypes.data_as(int16p), full_v.ctypes.data_as(int16p),
                    full_k8.ctypes.data_as(int8p), full_units.ctypes.data_as(doublep),
                    step_tokens.ctypes.data_as(uint32p), len(step_tokens), past,
                    full_logits.ctypes.data_as(int16p), full_exponent.ctypes.data_as(uint32p),
                    ctypes.byref(model_high))
                assert status == 0
                logical = full_logits.astype(np.float64) * (2.0**int(full_exponent[0]) / 256)
                assert hashlib.sha256(logical.astype('<f8').tobytes()).hexdigest() == expected['logits_sha256']
                assert int(np.argmax(full_logits)) == expected['token']
                assert cache_digest(len(input_tokens)+step) == expected['cache_sha256']
                generation_tokens += 1
                generation_steps += len(step_tokens)

        smoke = runtime_manifest['generation'][0]
        full_k.fill(0); full_v.fill(0); full_k8.fill(0); full_units.fill(0)
        prompt = np.asarray(smoke['input_tokens'], dtype=np.uint32)
        generated = np.zeros(3, dtype=np.uint32)
        cache_valid = np.zeros(1, dtype=np.uint32)
        status = lib.pa_m5_host_generate(arena_buffer, work, len(work),
            full_k.ctypes.data_as(int16p), full_v.ctypes.data_as(int16p),
            full_k8.ctypes.data_as(int8p), full_units.ctypes.data_as(doublep),
            prompt.ctypes.data_as(uint32p), len(prompt), len(generated),
            generated.ctypes.data_as(uint32p), full_logits.ctypes.data_as(int16p),
            full_exponent.ctypes.data_as(uint32p), cache_valid.ctypes.data_as(uint32p),
            ctypes.byref(model_high))
        assert status == 0
        np.testing.assert_array_equal(generated,
            np.asarray([step['token'] for step in smoke['steps'][:3]], dtype=np.uint32))
        assert cache_valid[0] == len(prompt) + 2
        final_logical = full_logits.astype(np.float64) * (2.0**int(full_exponent[0]) / 256)
        assert hashlib.sha256(final_logical.astype('<f8').tobytes()).hexdigest() == smoke['steps'][2]['logits_sha256']
        assert cache_digest(int(cache_valid[0])) == smoke['steps'][2]['cache_sha256']
        del arena_buffer
    operation_cases += len(runtime_manifest['cases']) + generation_tokens + 1
    operation_words += fixture_trace_words + generation_tokens*50257
    maximum_workspace = max(maximum_workspace, model_high.value)

    print('M5 NUMERICAL FOUNDATION PASS', json.dumps({
        'integer_rne_cases': integer_cases, 'float_rne_cases': len(float_values),
        'sqrt_cases': len(sqrt_values),
        'dynamic_cases': dynamic_cases, 'affine_values': affine_values,
        'storage_cases': len(storage_values), 'layernorm_metadata_cases': metadata_cases,
        'arena_arrays': 248, 'arena_regions': 15, 'arena_corruptions_rejected': len(corruptions),
        'workspace_cases': 4, 'model_operation_cases': operation_cases,
        'model_operation_words': int(operation_words), 'attention_words': attention_words,
        'maximum_workspace_bytes': maximum_workspace,
        'full_model_fixture_cases': len(runtime_manifest['cases']),
        'full_model_input_tokens': full_model_input_tokens,
        'full_model_trace_tensors': fixture_trace_checks,
        'full_model_trace_values': int(fixture_trace_words),
        'generation_cases': len(runtime_manifest['generation']),
        'generation_tokens': generation_tokens, 'generation_forward_tokens': generation_steps,
        'generate_api_smoke_tokens': len(generated), 'full_model_logits': 50257
    }, sort_keys=True))


if __name__ == '__main__':
    main()
