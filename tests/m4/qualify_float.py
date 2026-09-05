"""Qualify independent full-model equations against pinned Transformers."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import torch
import transformers
from transformers import GPT2LMHeadModel, GPT2TokenizerFast, GPT2Tokenizer
from ref.gpt2_float import FloatGPT2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, default=Path('build/m4_model'))
    parser.add_argument('--output', type=Path, default=Path('build/m4_float_qualification.json'))
    args = parser.parse_args()
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    fast = GPT2TokenizerFast.from_pretrained(args.model, local_files_only=True)
    slow = GPT2Tokenizer.from_pretrained(args.model, local_files_only=True)
    prompts_file = Path('tests/m4/prompts.json')
    prompts = json.loads(prompts_file.read_text())
    strings = [p['text'] for p in prompts['prompts']] + [
        '', ' leading space', 'café naïve — 日本語', 'a\n\n b\tC', '<|endoftext|>']
    for string in strings:
        ids = fast.encode(string, add_special_tokens=False)
        assert ids == slow.encode(string, add_special_tokens=False)
        assert fast.decode(ids, clean_up_tokenization_spaces=False) == string
    model = FloatGPT2(args.model)
    oracle = GPT2LMHeadModel.from_pretrained(args.model, local_files_only=True,
                                            use_safetensors=True, attn_implementation='eager').eval()
    assert sum(p.numel() for p in oracle.parameters()) == 124439808
    report = {'status': 'RUNNING', 'torch': torch.__version__,
              'transformers': transformers.__version__, 'threads': torch.get_num_threads(),
              'prompt_sha256': hashlib.sha256(prompts_file.read_bytes()).hexdigest(),
              'tokenizer_cases': len(strings), 'cases': [], 'generation': []}
    with torch.inference_mode():
        for text in [p['text'] for p in prompts['prompts']]:
            ids = fast.encode(text, add_special_tokens=False)
            actual, cache, _ = model.forward(ids, all_logits=True)
            expected = oracle(torch.tensor([ids]), use_cache=False).logits[0]
            error = float((actual - expected).abs().max())
            assert error <= 0.001, (text, error)
            assert torch.equal(actual.argmax(-1), expected.argmax(-1))
            # Every token's cached forward agrees with complete causal prefill.
            incremental, pcache = [], None
            for token in ids:
                output, pcache, _ = model.forward([token], pcache)
                incremental.append(output[0])
            cache_error = float((torch.stack(incremental) - actual).abs().max())
            assert cache_error <= 0.001, cache_error
            for (a, b), (c, d) in zip(cache, pcache):
                assert torch.allclose(a, c, atol=0.0001, rtol=0.0001)
                assert torch.allclose(b, d, atol=0.0001, rtol=0.0001)
            got = model.generate(ids, prompts['new_tokens'])
            tokens, past = torch.tensor([ids]), None
            want = []
            for _ in range(prompts['new_tokens']):
                result = oracle(tokens, past_key_values=past, use_cache=True)
                token = int(result.logits[0, -1].argmax())
                want.append(token)
                tokens, past = torch.tensor([[token]]), result.past_key_values
            assert got == want, (text, got, want)
            report['cases'].append({'input_tokens': ids, 'logit_max_abs': error,
                                    'cached_max_abs': cache_error})
            report['generation'].append({'prompt': text, 'new_token_ids': got,
                                         'text': fast.decode(ids + got, clean_up_tokenization_spaces=False)})
            print(f'M4 FLOAT PROMPT PASS tokens={len(ids)} logit_error={error:.9g} cached_error={cache_error:.9g}', flush=True)
        # Exercise the final legal position and reject one beyond it.
        ids = np.random.default_rng(0x4d344650).integers(0, 50257, 1024).tolist()
        actual, cache, _ = model.forward(ids)
        expected = oracle(torch.tensor([ids]), use_cache=False).logits[0, -1:]
        edge_error = float((actual - expected).abs().max())
        assert edge_error <= 0.001, edge_error
        try:
            model.forward([0], cache)
        except ValueError:
            pass
        else:
            raise AssertionError('accepted position 1024')
        report['context_1024_logit_max_abs'] = edge_error
    report['status'] = 'PASS'
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f'M4 FLOAT REFERENCE PASS output={args.output}', flush=True)


if __name__ == '__main__':
    main()
