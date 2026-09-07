"""Capture block-level attention counters using the frozen safe sweep wrapper."""
import struct
import m5_opt_profile as profiler
import m5_sweep

NAMES = ('append_cache', 'query_quantize', 'qk_pack_and_gemm', 'score_preparation_and_affine',
         'softmax_and_probability', 'value_maximum_scan', 'value_unit_preparation',
         'value_quantize_pack_and_gemm', 'output_affine')
original = profiler.run_one


def detailed(*args, **kwargs):
    result = original(*args, **kwargs)
    arena = args[0]
    words = struct.unpack_from('<30I', arena.maps['trace'], 0x28000)
    if words[:3] != (0x36585443, 1, 9):
        raise ValueError('attention detail header mismatch')
    rows = []
    for i, name in enumerate(NAMES):
        count, low, high = words[3+i*3:6+i*3]
        if count != (12 if i == 0 else 144):
            raise ValueError('attention detail call count mismatch')
        cycles = low | high << 32
        rows.append(dict(name=name, calls=count, cycles=cycles, seconds=cycles/91000000))
    attention_cycles = sum(p['cycles'] for p in result['phases'] if p['name'] == 'attention')
    if sum(r['cycles'] for r in rows) > attention_cycles:
        raise ValueError('attention detail exceeds parent interval')
    result['attention_detail'] = rows
    result['attention_unassigned_cycles'] = attention_cycles-sum(r['cycles'] for r in rows)
    return result


if __name__ == '__main__':
    profiler.run_one = detailed
    m5_sweep.main()
