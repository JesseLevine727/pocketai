# Maximum-context M5 performance extension

**CLOSED / PASS.** All six final unprofiled maximum-context observations deliver
within ten seconds, with exact full-model results and normal zero-resource
cleanup. M6, ASIC/PPA work and its report remain unstarted. This document records
the bounded engineering optimization, not M6.

## What is being measured

The endpoint is one genuine greedy forward with **past = 1023**, producing a
token and **1024 valid K/V positions**. The full W8A8/int16 GPT-2 still has twelve
layers, twelve heads, a 50,257-token output vocabulary and both fast-multiply
Ibex harts. A9 provisions, controls and checks; it performs no measured inference.

Delivered latency means START through safe DMA ownership return and token copy.
It includes host control/return overhead. It excludes model provisioning, raw
prefix restoration, firmware loading and correctness hashing, which remain
charged to campaign time. FPGA model time is a smaller nested interval. This is
**resident last-slot cached decode**, not a prompt-inclusive or sustained
generation claim beyond the fixed context capacity.

For each repetition an independent CPU oracle supplies only the raw past-1022
prefix. The FPGA performs a cold forward, including all new derived-cache
initialization inside model timing. Its actual greedy token and actual KV/
derived state feed the next forward at past 1023. The warm trial neither restores
future state nor repeats an already-computed query with its result cached.
Every repetition starts over from the independent seed. Both cold and warm costs
are reported. Story and science use repeated fixture prompts, not a representative
natural-language corpus or an arbitrary-content worst-case construction.

## Why the original design was slow

The historical full-context sweep measured 59.841 s delivered / 58.787 s model.
A separate detailed diagnostic spent 51.150 s in attention, dominated by scalar
packing and repeated quantization work: 14.582 s in QK packing/GEMM, 9.560 s in
value maximum scanning, 20.190 s in value quantization/packing/GEMM and 5.906 s
in score preparation/affine. Accelerator arithmetic was not the main cost.

This pass did not change W8A8 to W4A4, truncate attention, offload inference to
A9, increase the clock or alter Ibex multiplication. It stopped repeatedly
rebuilding data that the next consumer could reuse exactly, then parallelized
independent scalar preparation on the two existing harts.

## Retained implementation

1. **Consumer-ready keys and values.** K8 uses its existing nine-MiB allocation
   in block-16 consumer order. A persistent nine-MiB V8 cache uses otherwise
   unused work/trace space. Exact per-feature maxima, quantization multipliers,
   units and validity accompany it. If a maximum changes, every affected old
   value is requantized with the new multiplier; no stale scale is accepted.
2. **Exact metadata reuse.** Immutable model smoothing multipliers are cached
   by vector identity. Key-unit score metadata uses exact-key, per-query-epoch
   lookups. Overflow and unsupported arithmetic domains retain the qualified
   generic computation. All preparation and maintenance execute on FPGA.
3. **Preserved rounding.** The score product retains the intermediate binary64
   round-to-nearest-even operation before integer rounding; it does not replace
   two roundings with one. Integer scaled scores and their maximum are kept in
   a four-KiB BRAM scratch array before the original saturation/tagging rule.
4. **Two-hart preparation.** Projection scaling/range, output affine work and
   score preparation run over disjoint ranges. Value updates split by position
   so even one changed group uses both harts. Workers are pure leaf operations:
   no nested accelerator submission, shared workspace allocation or lazy-cache
   mutation. Join/fences precede dependent accelerator work.
5. **Direct destinations and changed-feature masks.** GEMM writes directly into
   the consumer's output span where strides permit. A 64-bit change mask avoids
   requantizing unchanged lanes in a partly changed four-byte value group.
   Workers write disjoint complete words. Old unchanged bytes are retained;
   every feature of the new tail position is always initialized.

The selected variant is `masked`, built in `build/m5_context_masked_v2` and
reproduced in `build/m5_context_masked_repro_v1`. Its three 65,536-byte binaries:

| Image | SHA-256 |
|---|---|
| Runtime | `4500c0731eed2201d6bce50a678953ecc881866eb0bc6a4af354721dd1307826` |
| Unprofiled-capable profile entry | `f6c5fec9547f9d10fa8ec3365fabd7fe169fe0ac4646daff2e48f51f91f544e1` |
| Diagnostic detail | `b8cb77c35fb5bc50b7bcc89bff737d22ff5a6b1d0590fa8ef2e8989146281c1d` |

### Memory and hardware

The qualified 91-MHz DSP0 overlay is unchanged, byte-for-byte: setup WNS
+0.263 ns, hold +0.018 ns, zero total negative slack, 29,003 LUTs, 21,724 FFs,
95.5 BRAM36 equivalents and 9,605 occupied slices. No new synthesis/timing result
is implied; these remain the previously qualified implementation results.

The arena remains 266,289,152 mapped bytes with the original model/layout/driver.
The derived V cache reserves work+0x280000..0x3fffff for its first 24 heads and
trace+0x80000..0x7fffff for the other 120 heads. Metadata occupies
trace+0x60000..0x7fed7. Smoothing multipliers use trace+0x30000..0x5cfff and
headers at +0x5d000. Profiling storage is separate at +0x20000/+0x28000.
Untraced workspace capacity is 2,609,152 bytes, above the observed 2,371,652-byte
requirement. Optional full-tensor traced requests retain the original attention
path and full workspace/trace capacity; they are checked but not the fast path.

Local scores occupy BRAM 0xc000..0xcfff, the unchanged 128-byte result ABI stays
at 0xd000, and exact lookup entries occupy 0xd080..0xd87f. The final packed linker
places literals at 0xd880..0xdb53, below the unchanged stacks at
0xe000..0xefff and 0xf000..0xffff. Linker assertions protect each boundary.
No additional physical BRAM, DDR arena pages, clock or accelerator RTL is used.

## Measurement-guided candidates and retained misses

Each diagnostic below is one cold/warm pair, not a statistically powered sample.
Profile-enabled observations are never pooled into the final unprofiled gate.
Historical candidate binaries are retained; the byte-identical rebuild claim
applies to the selected final variant, not every intermediate source version.

| Incremental variant | Prefix | Warm delivered, s | Interpretation |
|---|---|---:|---|
| Consumer-ready layout | Story | 17.539 | Removes repeated key packing and most value rebuilding |
| Fused score metadata | Story | 13.970 | Removes repeated generic metadata work |
| Smoothing cache | Story | 12.991 | Reuses immutable model multipliers |
| Exact two-rounding product | Story | 12.748 | Specializes binary64/integer scaling exactly |
| Local scores | Story | 12.503 | Avoids redundant score passes |
| Parallel projection | Story | 10.841 | Uses both fast harts for preparation |
| Parallel score/value work | Story | 10.009 | Misses the ten-second target |
| Direct GEMM destinations | Story | 9.700 | Passes this diagnostic only |
| Direct, plain qualification | Science | 10.728 | Correct but too slow; optimization continued |
| Position-split values | Science | 10.412 | Better work balance |
| Combined score preparation | Science | 10.098 | Fuses metadata, exact scaling and maximum |
| Changed-feature values | Science | 9.522 | Retained final design; diagnostic only |

Science's last slot raises 396 per-feature V maxima, versus story's 171. This
explains why a story-only pass was insufficient and why exact selective updates
matter. The first direct candidate's three plain story samples averaged 9.674 s,
but that candidate was not retained after the science miss.

The first direct qualification also has a preserved **FAIL**: after three exact
passing story pairs and a passing story trace, the science trace checker asked
for an unstaged `science.embedding.npy`. Its partial inference had correct
token/logits/full KV and normal safe cleanup, but the campaign is not relabeled
PASS. The corrected matrix uses the original available story trace, full logits/
KV for science/computing, and a separate optimized story request. The corrected
direct campaign passed; final qualification repeats these gates for `masked`.

Local pre-board failures are retained under fresh build paths: two ready-source
derivation drafts rejected ambiguous/wrong markers; `ready_v1` rejected an
implicit unresolved `memset`; `masked_v1` rejected detail-image code/BSS overlap
with local scores. Explicit initialization fixed the former link failure;
placing literals in the reserved BRAM gap fixed the latter. None was deployed
as a successful board candidate. Failed logs/artifacts remain hash-covered.

## Final timing and verification

| Maximum-context prefix | Three delivered samples, s | Mean delivered, s | Delivered token/s | Mean model, s |
|---|---|---:|---:|---:|
| Story | 8.972453, 8.979124, 8.973000 | 8.974859 | **0.111422** | 7.919588 |
| Science | 9.467196, 9.467979, 9.468602 | 9.467926 | **0.105620** | 8.409737 |

Rates are three tokens divided by the sum of the three delivered intervals,
reported separately by prefix. No sample was discarded. The slowest of all six
is **9.468602 s**, leaving **0.531398 s** below the ten-second gate. This is
observed margin, not a tail-latency guarantee.

The matched original baseline passed at 60.730311 s delivered / 58.883789 s model
for the identical story prefix and greedy input. The final story mean is
**6.7667x faster delivered** and **7.4352x faster in model time**. This is one
baseline observation; its 1.8465-s host overhead is retained, not replaced with
a cleaner estimate. The historical sweep uses a different final input and is
not used for the controlled speedup ratio.

The three charged cold forwards average **45.192452 s delivered for story** and
**45.459388 s for science**. They start with an existing raw prefix, so neither
number includes constructing that long prefix on the FPGA. These costs are not
hidden in the faster warm result.

Original short application requests also passed using the final runtime:

| Request | Model, s | Prompt-through-delivery, s | Delivered token/s |
|---|---:|---:|---:|
| Story, two tokens, full trace | 57.525583 | 58.576704 | 0.034143 |
| Science, one token, optimized | 29.770684 | 30.826094 | 0.032440 |
| Computing, one token, optimized | 29.811691 | 30.866358 | 0.032398 |
| Story, two tokens, optimized | 51.500139 | 52.559107 | 0.038052 |

These short-request rates include actual prompt prefill and are **not** the
resident cached-decode rate. The trace-enabled row also uses the legacy attention
path to preserve full tensor capture. No new sixteen-token sustained-request
measurement is claimed in this bounded pass.

Final story qualification took **432.771 s (7 min 13 s)** for ten cases; science
took **686.284 s (11 min 26 s)** for six cases, including its queue/staging time.
Both are below the 60-minute per-campaign cap, with the 120-second cleanup reserve
intact. Across the optimization there were eighteen short board campaigns, not
one sixty-minute aggregate experiment; their elapsed times include overlapping
queue time and should not be summed as hardware execution time. All have normal
zero-resource release, including the preserved checker-failure campaign. Final
owner, allocated pages and PTE state were zero after reopen, the helper unloaded
normally, and an independent final check found the helper absent.

Native regression gates pass: 15 legacy attention comparisons; the full
numerical foundation and 396 trace tensors; eleven bound-cache incremental calls
through 1024; 17 cache-preserving rejections; 60 threaded full-model generation
outputs; 115 metadata sets; 197,918 accepted exact two-rounding products and
2,082 fallback cases; 40 local-score and 84 threaded combined-score sets. An
additional test covers all sixteen changed-byte masks, both V regions and the
last slot. Cold/warm measurement tests reject hidden/future/unmatched state.
The machine audit also rejects eighteen altered-evidence cases, including slow
samples, hidden derived-state accounting, wrong logits/KV, unsafe cleanup,
profiling contamination and an incorrectly started M6. All earlier closure
audits still pass. See [machine evidence](m5_context_evidence.json) and
[reproduction](M5_CONTEXT_REPRODUCE.md).

## Remaining cost and scope limits

The retained science diagnostic spends 8.466 s in the model: 3.494 s attention,
1.270 s output head, 1.080 s smooth/down/residual, 0.824 s MLP-up and 0.620 s QKV.
Within attention, score preparation costs 1.166 s, selective value maintenance
0.848 s, and softmax/probability 0.631 s. The value maintenance block retains its
original `value_maximum_scan` label in raw counters even though it now also
updates the persistent value cache.

The nested accounting is 6.631 s CPU/control/scalar-memory remainder plus
1.835 s backend service, totaling 8.466 s. GEMM compute is 0.102 s and SFPU compute
0.467 s **inside** backend service, not extra additive time. The remainder is
78.3% of model time; these counters do not separate CPU arithmetic from DDR stalls
or give a sum of both harts' CPU utilization. More raw MAC capacity or lower
precision alone would not remove the dominant remaining measured work.

No 1022-token physical prefill marathon, extended endurance run, real-time Linux
isolation, thermal/energy sweep or arbitrary-content worst-case proof was done.
First-use derived preparation remains expensive and is explicitly charged.
The measured margin is descriptive for these inputs and runs, not a deadline
guarantee. Further optimization and M6 are separate follow-up decisions.
