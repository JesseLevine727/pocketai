"""Two genuine consecutive forwards; derived-cache initialization stays timed on FPGA."""
import struct
import m5_opt_profile as profiler
import m5_context_run as diagnostic
import m5_sweep

restore = profiler.restore_seed
run = profiler.run_one
previous = None


def restore_or_continue(arena, folder, seed):
    global previous
    trace = arena.maps['trace']
    if seed['context_role'] == 'cold_initialization_in_model':
        previous = None
        restore(arena, folder, seed)
        # Invalidate only. All layout conversion, maxima and V quantization are
        # performed by Ibex after START, never numerically prepared by A9.
        trace[0x60000:0x60008] = bytes(8)
    elif seed['context_role'] == 'warm_last_slot':
        if (previous is None or previous['cache_valid'] != seed['past'] or
                previous['token'] != seed['input_token'] or
                previous['kv_sha256'] != seed['prefill_kv_sha256']):
            raise ValueError('warm forward must follow its exact preceding FPGA forward')
        if profiler.m.cache_digest(arena, seed['past']) != seed['prefill_kv_sha256']:
            raise ValueError('retained full KV differs from independent prefix')
        if not seed.get('context_baseline') and struct.unpack_from('<144I', trace, 0x60008) != (seed['past'],)*144:
            raise ValueError('derived cache does not cover the exact prefix')
    else:
        raise ValueError('unknown context boundary')


def ready_run(*args, **kwargs):
    global previous
    seed, enabled = args[3:5]
    if seed.get('context_baseline') and enabled:
        raise ValueError('matched original baseline uses unprofiled firmware mode')
    # Detail instrumentation is used only by explicitly diagnostic policies.
    result = diagnostic.detailed(*args, **kwargs) if enabled else run(*args, **kwargs)
    if seed.get('context_baseline'):
        result.update(context_role=seed['context_role'], matched_original_baseline=True)
        previous = result
        return result
    trace = args[0].maps['trace']
    if struct.unpack_from('<144I', trace, 0x60008) != (seed['past']+1,)*144:
        raise ValueError('derived cache append validity mismatch')
    counters = struct.unpack_from('<4I', trace, 0x60000+130760)
    if counters[0] != 144 or counters[3] != 0:
        raise ValueError('derived-cache initialization count mismatch')
    result['derived_cache'] = dict(cold_heads=counters[0], updated_columns=counters[1],
                                   appended_vectors=counters[2])
    result['context_role'] = seed['context_role']
    previous = result
    return result


if __name__ == '__main__':
    profiler.restore_seed = restore_or_continue
    profiler.run_one = ready_run
    m5_sweep.main()
