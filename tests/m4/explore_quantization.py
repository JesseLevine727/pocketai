"""Diagnostic only: no quality PASS inferred from quantized self-consistency."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from transformers import GPT2TokenizerFast
from ref.gpt2_float import FloatGPT2
from ref.gpt2_quantized import QuantizedGPT2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, default=Path('build/m4_model'))
    parser.add_argument('--output', type=Path, default=Path('build/m4_quantization_v1_diagnostic.json'))
    args = parser.parse_args()
    torch.set_num_threads(4)
    tokenizer = GPT2TokenizerFast.from_pretrained(args.model, local_files_only=True)
    float_model, quant_model = FloatGPT2(args.model), QuantizedGPT2(args.model)
    prompt = json.loads(Path('tests/m4/prompts.json').read_text())['prompts'][0]['text']
    ids = tokenizer.encode(prompt, add_special_tokens=False)
    fq, cache, qt = quant_model.forward(ids, all_logits=True, capture=True)
    fp, _, ft = float_model.forward(ids, all_logits=True, capture=True)
    fp = fp.numpy()
    report = {'status': 'DIAGNOSTIC_NOT_QUALIFIED', 'prompt': prompt, 'tokens': ids,
              'logit_max_abs': float(np.abs(fq / 256 - fp).max()),
              'top1_agreement': float(np.mean(fq.argmax(-1) == fp.argmax(-1))),
              'clipping': {k: v for k, v in quant_model.stats.items() if k.endswith('.clipped') and v},
              'preclip_maximum_raw': quant_model.maxima, 'layers': {}}
    for name in qt:
        error = qt[name].astype(np.float64) / 256 - ft[name].numpy()
        report['layers'][name] = {'rmse': float(np.sqrt(np.mean(error ** 2))),
                                  'max_abs': float(np.abs(error).max()),
                                  'float_max_abs': float(ft[name].abs().max())}
    # Integer cache equivalence must be exact even when model quality is poor.
    incremental, pcache = [], None
    for token in ids:
        output, pcache, _ = quant_model.forward([token], pcache)
        incremental.append(output[0])
    np.testing.assert_array_equal(np.stack(incremental), fq)
    for (a, b), (c, d) in zip(cache, pcache):
        np.testing.assert_array_equal(a, c)
        np.testing.assert_array_equal(b, d)
    report['quantized_cached_equivalence'] = 'PASS'
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('M4 QUANTIZATION DIAGNOSTIC', json.dumps({k: report[k] for k in ('status','top1_agreement','logit_max_abs','clipping','quantized_cached_equivalence')}), flush=True)


if __name__ == '__main__':
    main()
