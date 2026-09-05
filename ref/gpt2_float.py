"""Independent batch-one GPT-2 equations, using CPU Torch tensor primitives.

No Transformers model code is used here. The qualification harness compares
this implementation with a separately instantiated pinned Transformers model.
Weights retain the original [input,output] Conv1D layout. Cache is [head,T,64].
"""
import math
from pathlib import Path
import torch
from safetensors.torch import load_file


class FloatGPT2:
    def __init__(self, directory, dtype=torch.float32):
        raw = load_file(str(Path(directory) / "model.safetensors"), device="cpu")
        self.weights = {k: v.to(dtype) for k, v in raw.items()
                        if not k.endswith(".attn.bias")}
        self.dtype = dtype
        if sum(v.numel() for v in self.weights.values()) != 124439808:
            raise ValueError("unexpected GPT-2 parameter count")
        if self.weights['wte.weight'].shape != (50257, 768):
            raise ValueError("unexpected vocabulary/hidden size")

    def norm(self, x, prefix):
        centered = x - x.mean(dim=-1, keepdim=True)
        variance = (centered * centered).mean(dim=-1, keepdim=True)
        return centered * torch.rsqrt(variance + 1e-5) * self.weights[prefix + '.weight'] + self.weights[prefix + '.bias']

    def linear(self, x, prefix):
        return x @ self.weights[prefix + '.weight'] + self.weights[prefix + '.bias']

    @torch.inference_mode()
    def forward(self, tokens, cache=None, all_logits=False, capture=False):
        tokens = torch.as_tensor(tokens, dtype=torch.int64)
        if tokens.ndim != 1 or tokens.numel() == 0 or torch.any(tokens < 0) or torch.any(tokens >= 50257):
            raise ValueError("nonempty batch-one token vector required")
        if cache is not None and len(cache) != 12:
            raise ValueError("cache must contain twelve layers")
        past = 0 if cache is None else cache[0][0].shape[1]
        if past + len(tokens) > 1024:
            raise ValueError("position limit exceeded")
        x = self.weights['wte.weight'][tokens] + self.weights['wpe.weight'][past:past + len(tokens)]
        trace = {'embedding': x.clone()} if capture else {}
        next_cache = []
        for layer in range(12):
            prefix = f'h.{layer}'
            n1 = self.norm(x, prefix + '.ln_1')
            qkv = self.linear(n1, prefix + '.attn.c_attn')
            q, k, v = (part.reshape(-1, 12, 64).transpose(0, 1) for part in qkv.chunk(3, dim=-1))
            if cache is not None:
                pk, pv = cache[layer]
                if pk.shape != (12, past, 64) or pv.shape != pk.shape:
                    raise ValueError("inconsistent cache shape")
                k, v = torch.cat((pk, k), dim=1), torch.cat((pv, v), dim=1)
            next_cache.append((k.contiguous(), v.contiguous()))
            scores = q @ k.transpose(1, 2) / 8
            mask = torch.arange(k.shape[1])[None, :] <= (past + torch.arange(len(tokens)))[:, None]
            probs = torch.softmax(scores.masked_fill(~mask[None], -torch.inf), dim=-1)
            context = (probs @ v).transpose(0, 1).reshape(-1, 768)
            attn = self.linear(context, prefix + '.attn.c_proj')
            residual = x + attn
            n2 = self.norm(residual, prefix + '.ln_2')
            up = self.linear(n2, prefix + '.mlp.c_fc')
            gelu = 0.5 * up * (1 + torch.tanh(math.sqrt(2 / math.pi) * (up + 0.044715 * up ** 3)))
            down = self.linear(gelu, prefix + '.mlp.c_proj')
            x = residual + down
            if capture:
                for name, value in (('ln1', n1), ('qkv', qkv), ('scores', scores),
                                    ('probs', probs), ('context', context), ('attn', attn),
                                    ('residual', residual), ('ln2', n2), ('up', up),
                                    ('gelu', gelu), ('down', down), ('output', x)):
                    trace[f'{prefix}.{name}'] = value.clone()
        x = self.norm(x, 'ln_f')
        if capture:
            trace['ln_f'] = x.clone()
        logits = (x if all_logits else x[-1:]) @ self.weights['wte.weight'].T
        return logits, next_cache, trace

    def generate(self, tokens, count=20):
        if count < 1 or len(tokens) + count > 1024:
            raise ValueError("invalid generation length")
        logits, cache, _ = self.forward(tokens)
        result = []
        for step in range(count):
            # torch.argmax returns the first/lowest token ID on exact ties.
            token = int(logits[-1].argmax())
            result.append(token)
            if step + 1 < count:
                logits, cache, _ = self.forward([token], cache)
        return result
