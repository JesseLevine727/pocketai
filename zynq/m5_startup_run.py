"""Bounded exact cold-cache and real multirow-prefill profiling; no host inference."""
import hashlib
import json
import struct
import time
import numpy as np
import m5_run as m
import m5_opt_profile as profiler
import m5_context_ready_run as ready
import m5_context_run as context
import m5_sweep
original_full_case = m.run_case


def full_case(arena, fixture_dir, case, fixture, count, capture, ordinal, timeout):
    trace_firmware = fixture_dir.parent/'m5_trace.bin'
    firmware = fixture_dir.parent/'m5_runtime.bin'
    if capture and trace_firmware.exists():
        # Sweep has already PREPAREd and loaded the primary image. Select the
        # same-source full-trace image before this non-primary request starts.
        from pynq import MMIO
        policy = json.loads((fixture_dir.parent/'policy.json').read_text())
        if m.sha256_file(trace_firmware) != policy['pinned']['m5_trace.bin']:
            raise ValueError('trace firmware identity mismatch')
        m.load_firmware(MMIO(m.CLUSTER_BASE, m.CLUSTER_BYTES), trace_firmware)
        firmware = trace_firmware
    result = original_full_case(arena, fixture_dir, case, fixture, count, capture, ordinal, timeout)
    result.update(execution_image=firmware.name, firmware_sha256=m.sha256_file(firmware))
    return result

NAMES = ('cold_head_initialization', 'key_transpose', 'value_maximum_scan', 'value_units',
         'value_conversion', 'projection_quantize', 'projection_gemm_and_copy',
         'projection_scale_and_range', 'projection_affine', 'projection_residual',
         'smoothing_setup', 'smoothing_probe', 'smoothing_rows', 'complete_cache_preparation',
         'initial_demand_materialization', 'all_demand_materialization')


def details(trace, rows, phases):
    header = struct.unpack_from('<4I', trace, 0x2a000)
    # The original 13-counter experiments remain readable. Counter 14 measures
    # the entire cache-prepare call, including reset and validity bookkeeping.
    if header[:2] != (0x37545350, 1) or header[2] not in (13, 14, 16) or header[3]:
        raise ValueError('startup detail header')
    result = []
    for index, name in enumerate(NAMES[:header[2]]):
        cycles, calls, reserved = struct.unpack_from('<QII', trace, 0x2a010+index*16)
        if reserved or (calls == 0 and cycles): raise ValueError('startup detail record')
        result.append(dict(name=name, cycles=cycles, calls=calls, seconds=cycles/m.FABRIC_HZ))
    if sum(x['cycles'] for x in result[1:5]) > result[0]['cycles']:
        raise ValueError('initialization subintervals exceed parent')
    if len(result) >= 14 and result[13]['calls']:
        if result[13]['calls'] != 12 or result[0]['cycles'] > result[13]['cycles']:
            raise ValueError('complete cache preparation coverage')
    words = struct.unpack_from('<30I', trace, 0x28000)
    if words[:3] != (0x36585443, 1, 9): raise ValueError('attention detail header')
    attention = []
    for index, name in enumerate(context.NAMES):
        calls, low, high = words[3+index*3:6+index*3]
        if calls != (12 if index == 0 else 144*rows): raise ValueError('attention detail coverage')
        cycles = low | high << 32
        attention.append(dict(name=name, calls=calls, cycles=cycles, seconds=cycles/m.FABRIC_HZ))
    total = sum(x['cycles'] for x in phases if x['name'] == 'attention')
    if sum(x['cycles'] for x in attention) > total: raise ValueError('attention subintervals exceed parent')
    parsed = dict(startup_detail=result, attention_detail=attention,
                  attention_unassigned_cycles=total-sum(x['cycles'] for x in attention))
    if len(result) == 16:
        initial, all_demands = result[14:16]
        if initial['cycles'] > all_demands['cycles'] or initial['calls'] > all_demands['calls']:
            raise ValueError('initial demand materialization coverage')
        if all_demands['calls'] and (all_demands['calls'] != 144*rows or initial['calls'] not in (0, 144)):
            raise ValueError('demand materialization coverage')
        # Deferred first-use work is INCLUDED, not renamed out of initialization.
        parsed['initial_required_derived_seconds'] = result[13]['seconds']+initial['seconds']
    if len(trace) >= 0x2b040 and struct.unpack_from('<I', trace, 0x2b000)[0] == 0x3746504c:
        if struct.unpack_from('<4I', trace, 0x2b000) != (0x3746504c, 1, 2, 0):
            raise ValueError('leaf detail header')
        leaves = []
        for worker in range(2):
            cycles, instructions, calls, reserved = struct.unpack_from('<QQII', trace, 0x2b010+worker*24)
            if reserved or (not calls and (cycles or instructions)) or (calls and not instructions):
                raise ValueError('leaf detail coverage')
            leaves.append(dict(worker=worker, cycles=cycles, retired_instructions=instructions,
                calls=calls, cycles_per_instruction=cycles/instructions if instructions else None))
        if any(x['calls'] for x in leaves): parsed['projection_leaf_diagnostic'] = leaves
    return parsed


def check_initial_coverage(result, role, rows):
    """Version-2 first-use accounting must match the actual request boundary."""
    if result['derived_cache']['version'] != 2: return
    records = result['startup_detail']
    if len(records) != 16: raise ValueError('lazy cache requires full first-use counters')
    cold = role in ('cold_initialization_in_model', 'actual_prompt_prefill')
    if role not in ('cold_initialization_in_model', 'actual_prompt_prefill', 'warm_last_slot'):
        raise ValueError('unknown initialization boundary')
    expected = {0: 144 if cold else 0, 13: 12, 14: 144 if cold else 0, 15: 144*rows}
    if any(records[index]['calls'] != count for index, count in expected.items()):
        raise ValueError('first-use accounting does not match cold/warm request')


def run_one(arena, cluster, stage, seed, enabled, ordinal, timeout):
    tokens = seed.get('prefill_tokens', [seed.get('input_token')])
    if not 1 <= len(tokens) <= 16 or any(not isinstance(t, int) or not 0 <= t < 50257 for t in tokens):
        raise ValueError('invalid independent input tokens')
    if not 0 <= seed['past'] <= 1024-len(tokens): raise ValueError('invalid cache prefix')
    arena.ioctl(m.IOC_PREPARE)
    firmware_hash = m.load_firmware(cluster, stage/'m5_profile.bin')
    if seed['context_role'] == 'actual_prompt_prefill':
        if seed['past'] != 0: raise ValueError('prefill must start empty')
        ready.previous = None
        # No numerical host preparation; FPGA past=0 initializes its own cache.
    else:
        ready.restore_or_continue(arena, stage/'seed', seed)
    work, trace = arena.maps['work'], arena.maps['trace']
    work[:0x3000] = bytes(0x3000); trace[:256] = bytes(256)
    words = [profiler.CONTROL_MAGIC, 1, ordinal, 2, len(tokens), 1, int(enabled), 100_000_000]
    words += [0]*(25-len(words)); words[10] = seed['past']
    struct.pack_into('<25I', work, 0, *words)
    struct.pack_into('<'+str(len(tokens))+'I', work, m.WORK_PROMPT, *tokens)
    begin = time.monotonic()
    arena.ioctl(m.IOC_START)
    while True:
        info = arena.info()
        if info['status'] & (1 << 5): break
        if info['status'] & ((1 << 3) | (1 << 4)): raise RuntimeError('fabric fault: '+repr(info))
        if time.monotonic()-begin > timeout: raise TimeoutError('startup case watchdog')
        time.sleep(.01)
    arena.ioctl(m.IOC_RETURN)
    token = struct.unpack_from('<I', work, m.WORK_GENERATED)[0]
    delivered = time.monotonic()
    words = struct.unpack_from('<25I', work)
    if words[8:12] != (4, 0, seed['past']+len(tokens), 1) or words[23:25] != (3, 0):
        raise ValueError('firmware completion mismatch: '+repr(words))
    header = struct.unpack_from('<64I', trace)
    result = profiler.parse_profile(header,
        bytes(trace[profiler.RECORD_OFFSET:profiler.RECORD_OFFSET+header[5]*profiler.RECORD.size]), enabled, m.FABRIC_HZ)
    logits = np.frombuffer(trace, dtype='<i2', count=50257, offset=profiler.LOGITS_OFFSET).copy()
    logical = np.ldexp(logits.astype(np.float64), int(header[4]))/256
    logits_hash = hashlib.sha256(logical.astype('<f8').tobytes()).hexdigest()
    kv_hash = m.cache_digest(arena, words[10]); expected = seed['expected']
    if token != expected['token'] or int(np.argmax(logits)) != token or logits_hash != expected['logits_sha256'] or kv_hash != expected['cache_sha256']:
        raise ValueError('startup result differs from independent token/logits/full KV')
    if struct.unpack_from('<144I', trace, 0x60008) != (words[10],)*144:
        raise ValueError('derived cache validity mismatch')
    counters = struct.unpack_from('<4I', trace, 0x60000+130760)
    if counters[0] != 144 or counters[3]: raise ValueError('cold-head metadata mismatch')
    result.update(status='PASS', ordinal=ordinal, token=token, firmware_sha256=firmware_hash,
        logits_sha256=logits_hash, kv_sha256=kv_hash, cache_valid=words[10],
        input_tokens=tokens, initial_past=seed['past'], context_role=seed['context_role'],
        derived_cache=dict(version=struct.unpack_from('<I', trace, 0x60004)[0],
            cold_heads=counters[0], updated_columns=counters[1], appended_vectors=counters[2]),
        host_request_through_delivery_seconds=delivered-begin)
    if enabled:
        result.update(details(trace, len(tokens), result['phases']))
        check_initial_coverage(result, seed['context_role'], len(tokens))
    ready.previous = result
    return result


if __name__ == '__main__':
    profiler.run_one = run_one
    m.run_case = full_case
    m5_sweep.main()
