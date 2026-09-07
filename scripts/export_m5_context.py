"""Independent two-forward oracle: real FPGA-derived state precedes the last slot."""
import argparse
import json
from pathlib import Path
import signal
import time
import numpy as np
from scripts.export_m5_sweep import snapshot, expired
from scripts.m5_sweep_policy import sha
from zynq.m4_offload import CpuBackend, Runtime


def main():
    p = argparse.ArgumentParser(__doc__); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--case', choices=('story', 'science', 'computing'), default='story')
    args = p.parse_args(); args.output.mkdir(exist_ok=False)
    started = time.monotonic(); signal.signal(signal.SIGALRM, expired); signal.alarm(600)
    fixtures = json.loads(Path('build/m4_runtime_fixtures/manifest.json').read_text())
    prompt = next(c for c in fixtures['generation'] if c['id'] == args.case)['input_tokens']
    tokens = (prompt*((1022+len(prompt)-1)//len(prompt)))[:1022]
    runtime = Runtime('build/m4_pack_v3', CpuBackend('build/m4_cpu_gemm_host.so', 'build/m4_cpu_sfpu_host.so'))
    arrays = dict(k=runtime.k, v=runtime.v, k8=runtime.k8, kunits=runtime.kunits)
    runtime.reset()
    for a in arrays.values(): a.fill(0)
    prefix = snapshot(runtime, runtime.prefill(tokens))
    folder = args.output/'seed'; folder.mkdir()
    entries = {}
    for name, array in arrays.items():
        path = folder/f'{name}.bin'
        path.write_bytes(np.ascontiguousarray(array, dtype=array.dtype.newbyteorder('<')).tobytes())
        entries[name] = dict(file=path.name, bytes=path.stat().st_size, sha256=sha(path))
    cold = dict(schema=1, status='PASS', past=1022, input_token=prefix['token'], arrays=entries,
        prefill_kv_sha256=prefix['cache_sha256'], prefill_logits_sha256=prefix['logits_sha256'],
        input_tokens=tokens, context_role='cold_initialization_in_model')
    cold['expected'] = snapshot(runtime, runtime.step([cold['input_token']]))
    warm = dict(schema=1, status='PASS', past=1023, input_token=cold['expected']['token'], arrays={},
        prefill_kv_sha256=cold['expected']['cache_sha256'],
        prefill_logits_sha256=cold['expected']['logits_sha256'], context_role='warm_last_slot')
    warm['expected'] = snapshot(runtime, runtime.step([warm['input_token']]))
    (folder/'manifest.json').write_text(json.dumps(cold, indent=2)+'\n')
    result = dict(schema=1, status='PASS', case=args.case, seeds={'1022': cold, '1023': warm},
        elapsed_seconds=time.monotonic()-started,
        boundary='Independent prefill1022, then two actual greedy forwards; no future state reused',
        sources={name: sha(name) for name in ('scripts/export_m5_context.py', 'zynq/m4_offload.py',
            'zynq/m4_run.py', 'build/m4_pack_v3/manifest.json', 'build/m4_cpu_gemm_host.so',
            'build/m4_cpu_sfpu_host.so', 'build/m4_runtime_fixtures/manifest.json')})
    (args.output/'manifest.json').write_text(json.dumps(result, indent=2)+'\n')
    signal.alarm(0)
    print('CONTEXT INDEPENDENT TWO-FORWARD REFERENCE PASS', result['elapsed_seconds'], flush=True)


if __name__ == '__main__': main()
