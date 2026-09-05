#!/usr/bin/env python3
"""Full-shape MLP and causal-attention operator chains, not model inference.

Each packet identifies which earlier HARDWARE result must replace its input.
Consumers must apply those patches, not simply replay independent golden inputs.
The same binary can drive cluster simulation and physical-board qualification.
"""
import argparse
import json
from pathlib import Path
import struct
import numpy as np
from ref.gemm_v3_ref import M3GemmDescriptor, gemm_wide_int32, pack_input_v3, pack_output_v3
from ref.sfpu_stream import Op, SfpuDescriptor, evaluate_and_pack, expected_compute_cycles
from ref.sfpu_ref import dynamic_int8_parameters, rne_div

SEED = 0x43484e33


def build_chains():
    rng = np.random.default_rng(SEED)
    steps, tensors = [], {}

    def append(kind, parameters, inputs, outputs, cycles, source, mode, count,
               destination, offset, scenario):
        tag = len(steps) + 1
        metadata = [kind, *parameters, tag, len(inputs), len(outputs), cycles,
                    source, mode, count, destination, offset, len(outputs), scenario]
        assert len(metadata) == 16
        steps.append((metadata, inputs, outputs))
        if destination not in tensors:
            tensors[destination] = []
        values = outputs.view("<i4").tolist()
        if len(tensors[destination]) < offset + len(values):
            tensors[destination].extend([0] * (offset + len(values) - len(tensors[destination])))
        tensors[destination][offset:offset + len(values)] = values

    def sfpu(op, planes, dest, source=0, mode=1, shift=0, multiplier=0, scenario=0):
        d = SfpuDescriptor(op, len(planes[0]), shift, multiplier)
        inputs, outputs = evaluate_and_pack(d, planes)
        append(1, [d.op, d.length, d.shift, d.multiplier], inputs, outputs,
               expected_compute_cycles(d, planes), source, mode if source else 0,
               d.length if source else 0, dest, 0, scenario)
        return outputs.view("<i4").copy()

    def projection(a, weights, dest, source=0, scenario=0):
        k, n = weights.shape
        for col in range(0, n, 16):
            d = M3GemmDescriptor(1, 16, k, flags=0x100)
            tile = weights[:, col:col + 16]
            inputs = pack_input_v3(d, a.reshape(1, k), tile)
            outputs = pack_output_v3(d, gemm_wide_int32(a.reshape(1, k), tile))
            append(0, [1, 16, k, 0x100], inputs, outputs, k + 6 + 16,
                   source, 2 if source else 0, k if source else 0, dest, col, scenario)
        return np.asarray(tensors[dest], dtype=np.int32)

    # One pre-LayerNorm MLP sub-block, width 768 and full expansion 3072.
    x = rng.integers(-512, 513, 768, dtype=np.int32)
    gain = rng.integers(3584, 4609, 768, dtype=np.int32)
    bias = rng.integers(-64, 65, 768, dtype=np.int32)
    normalized = sfpu(Op.LAYERNORM, (x, gain, bias), 2)
    mult, shift = dynamic_int8_parameters(normalized)
    a = sfpu(Op.REQUANT8, (normalized,), 3, source=2, shift=shift, multiplier=mult)
    w_up = rng.integers(-8, 9, (768, 3072), dtype=np.int16).astype(np.int8)
    up = projection(a, w_up, 4, source=3)
    up_scales = rng.integers(1536, 2561, 3072, dtype=np.int32)
    up_bias = rng.integers(-128, 129, 3072, dtype=np.int32)
    activated = sfpu(Op.AFFINE_GELU, (up, up_scales, up_bias), 5, source=4, shift=16)
    mult, shift = dynamic_int8_parameters(activated)
    hidden = sfpu(Op.REQUANT8, (activated,), 6, source=5, shift=shift, multiplier=mult)
    w_down = rng.integers(-8, 9, (3072, 768), dtype=np.int16).astype(np.int8)
    down = projection(hidden, w_down, 7, source=6)
    projected = sfpu(Op.AFFINE, (down, np.full(768, 4096, dtype=np.int32), bias),
                     8, source=7, shift=16)
    sfpu(Op.ADD, (projected, x), 9, source=8)

    # One 64-wide attention head, context 1024, causal valid prefix length768.
    q = rng.integers(-16, 17, 64, dtype=np.int32)
    keys = rng.integers(-16, 17, (64, 1024), dtype=np.int16).astype(np.int8)
    qk = projection(q, keys, 20, scenario=1)
    scores = sfpu(Op.AFFINE, (qk, np.ones(1024, dtype=np.int32),
                             np.zeros(1024, dtype=np.int32)),
                  21, source=20, shift=3, scenario=1)
    mask = np.arange(1024) < 768
    probability = sfpu(Op.SOFTMAX, (scores, mask), 22, source=21, mode=3, scenario=1)
    mult, shift = dynamic_int8_parameters(probability)
    p8 = sfpu(Op.REQUANT8, (probability,), 23, source=22,
              shift=shift, multiplier=mult, scenario=1)
    values = rng.integers(-16, 17, (1024, 16), dtype=np.int16).astype(np.int8)
    av = projection(p8, values, 24, source=23, scenario=1)
    # Q/K/V code scales are 1/16. Restore the effective probability conversion
    # scale and V's scale into activation raw units; nearest fixed coefficient.
    final_multiplier = rne_div(8192 << 24, mult)
    sfpu(Op.AFFINE, (av, np.full(16, final_multiplier, dtype=np.int32),
                     np.zeros(16, dtype=np.int32)), 25, source=24, shift=24, scenario=1)
    return steps, tensors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    steps, tensors = build_chains()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("wb") as stream:
        stream.write(struct.pack("<3I", 0x334e4843, len(steps), SEED))
        for metadata, inputs, outputs in steps:
            stream.write(struct.pack("<16I", *metadata))
            stream.write(inputs.tobytes())
            stream.write(outputs.tobytes())
    summary = {"seed": SEED, "steps": len(steps),
               "gemm_steps": sum(m[0] == 0 for m, _, _ in steps),
               "sfpu_steps": sum(m[0] == 1 for m, _, _ in steps),
               "actual_result_patch_steps": sum(m[9] != 0 for m, _, _ in steps),
               "mlp_shape": [1, 768, 3072, 768], "attention_shape": [1, 64, 1024, 16],
               "attention_valid_prefix": 768,
               "final_mlp_elements": len(tensors[9]), "final_attention_elements": len(tensors[25])}
    args.output.with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n")
    print("M3 CHAIN VECTORS PASS " + json.dumps(summary))


if __name__ == "__main__":
    main()
