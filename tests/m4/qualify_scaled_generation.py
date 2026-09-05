"""Frozen 3x20 generation comparison; no tuning or float-identity requirement."""
import json
from pathlib import Path
import numpy as np
from transformers import GPT2TokenizerFast
from ref.gpt2_scaled import ScaledGPT2
from tests.m4.qualify_scaled_quality import verify_frozen
from tests.m4.evaluate_scaled import sha


def main():
    output = Path('build/m4_v2_generation.json')
    if output.exists():
        raise ValueError('refusing to overwrite generation evidence')
    freeze = verify_frozen()
    fixture_file = Path('tests/m4/prompts.json')
    fixture = json.loads(fixture_file.read_text())
    floating_file = Path('build/m4_float_qualification.json')
    if sha(fixture_file) != '0886333492f4ff907845c7ba6aed6c914b5b7c1e5cc0595bc4665b860eb7a90c':
        raise ValueError('acceptance prompts changed')
    if sha(floating_file) != '095ad37bbb38aea4ef5e9baf3fc7e1289648423d16b649aaa547a0aef685d0b5':
        raise ValueError('floating generation evidence changed')
    floating = json.loads(floating_file.read_text())
    tokenizer = GPT2TokenizerFast.from_pretrained('build/m4_model', local_files_only=True)
    model = ScaledGPT2('build/m4_model', 'build/m4_calibration.json', freeze['alpha'])
    cases = []
    for prompt, base in zip(fixture['prompts'], floating['generation']):
        if prompt['text'] != base['prompt']:
            raise ValueError('prompt/oracle mismatch')
        tokens = tokenizer.encode(prompt['text'], add_special_tokens=False)
        generated, per_step, cache = [], [], None
        for step in range(fixture['new_tokens']):
            inputs = tokens if step == 0 else [generated[-1]]
            logits, cache, _ = model.forward(inputs, cache)
            # Full recomputation on the same actual generated prefix is an
            # independent schedule, not a different floating generation path.
            recomputed, other_cache, _ = model.forward(tokens + generated)
            np.testing.assert_array_equal(logits, recomputed)
            for (k, v), (ok, ov) in zip(cache, other_cache):
                np.testing.assert_array_equal(k, ok)
                np.testing.assert_array_equal(v, ov)
            token = int(logits[0].argmax())
            generated.append(token)
            per_step.append({'step': step, 'token': token, 'logits_sha256': __import__('hashlib').sha256(logits.astype('<f8').tobytes()).hexdigest()})
        differences = [i for i, (a, b) in enumerate(zip(generated, base['new_token_ids'])) if a != b]
        case = {'id': prompt['id'], 'prompt': prompt['text'], 'input_tokens': tokens,
                'new_token_ids': generated, 'text': tokenizer.decode(tokens + generated),
                'float_new_token_ids': base['new_token_ids'], 'float_text': base['text'],
                'float_first_divergence': differences[0] if differences else None,
                'same_step_float_matches': len(generated) - len(differences),
                'cached_vs_recomputed': 'EXACT_PASS_ALL_20_STEPS_AND_KV', 'steps': per_step}
        cases.append(case)
        print('M4 GENERATION EXACT CACHE PASS', json.dumps(case, ensure_ascii=False), flush=True)
    clipping = {k: v for k, v in model.stats.items() if k.endswith('.clipped') and v}
    report = {'status': 'GENERATION_REFERENCE_PASS_NOT_PHYSICAL_M4_CLOSURE',
              'candidate_sha256': sha('tests/m4/scaled_candidate.json'), 'runner_sha256': sha(__file__),
              'prompt_sha256': sha(fixture_file), 'cases': cases, 'unintended_clipping': clipping,
              'notes': 'Free-running float and quantized outputs can diverge after a near tie. Same-step token matches after divergence are descriptive, not teacher-forced quality. All 60 cached/recomputed steps are exact.'}
    if clipping:
        report['status'] = 'FAIL_UNINTENDED_CLIPPING'
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    if clipping:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
