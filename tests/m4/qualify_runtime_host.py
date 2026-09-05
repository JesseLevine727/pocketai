"""Independent bounded/native scheduler vs frozen full-model reference."""
import argparse
import json
from pathlib import Path
import numpy as np
from ref.gpt2_adaptive import AdaptiveGPT2
from ref.m4_model_pack import file_sha256
from zynq.m4_offload import Runtime, CpuBackend


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('build/m4_runtime_host.json'))
    args = parser.parse_args()
    output = args.output
    if output.exists():
        raise ValueError('refusing to overwrite runtime evidence')
    backend = CpuBackend('build/m4_cpu_gemm_host.so', 'build/m4_cpu_sfpu_host.so')
    runtime = Runtime('build/m4_pack_v3', backend)
    reference = AdaptiveGPT2('build/m4_model', 'build/m4_calibration.json', .5)
    tokens = np.load('build/m4_quality_data/validation_256.npy', allow_pickle=False)[0, :17]
    cache = None
    checks = 0
    for start, length in ((0, 13), (13, 4)):
        expected, cache, trace = reference.forward(tokens[start:start + length], cache, all_logits=True, capture=True)
        def compare(name, value):
            nonlocal checks
            np.testing.assert_array_equal(value, trace[name], err_msg=name)
            checks += 1
        actual = runtime.step(tokens[start:start + length], all_logits=True, capture=compare)
        np.testing.assert_array_equal(actual, expected)
        for layer, (k, v) in enumerate(cache):
            np.testing.assert_array_equal(runtime.k[layer, :, :runtime.length], k)
            np.testing.assert_array_equal(runtime.v[layer, :, :runtime.length], v)
        print('M4 RUNTIME EXACT LAYER/LOGIT/KV PASS', runtime.length, flush=True)
    frozen = json.loads(Path('build/m4_v3_generation.json').read_text())
    for case in frozen['cases']:
        generated = runtime.generate(case['input_tokens'], 20)
        np.testing.assert_array_equal(generated, case['new_token_ids'])
        print('M4 RUNTIME GENERATION EXACT PASS', case['id'], flush=True)
    report = {'status': 'HOST_RUNTIME_PASS_NOT_PHYSICAL_CLOSURE', 'trace_comparisons': checks,
              'generation_tokens': 60, 'cache_capacity': runtime.capacity, 'cache_bytes': runtime.cache_bytes,
              'source_sha256': file_sha256('zynq/m4_offload.py'), 'runner_sha256': file_sha256(__file__),
              'counts': dict(backend.counts), 'backend': backend.native_gemm.backend}
    output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
