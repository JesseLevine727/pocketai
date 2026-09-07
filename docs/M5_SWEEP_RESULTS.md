# M5 frozen-release characterization — CLOSED / PASS

All **31 predeclared experiments passed** in **2304.296 seconds (38 min 24 s)**,
including staging, provisioning, cache restoration, checking and normal release.
The physical-board cap was 60 minutes with a two-minute cleanup reserve.
No experiment was skipped, failed, or exceeded its per-case conservative bound.
Independent reference preparation took **116.598 seconds**, under its separate
10-minute guard. No optimization, new FPGA build, precision change or M6 work
was part of this goal.

## What performance can we fairly claim?

For the tested 16-token requests, **prompt-inclusive resident delivery is
0.07829 new tokens/s for story and about 0.09046 for science/computing**.
The two story repetitions average **204.364545 seconds** delivered; their internal
15-token continuation rate is **0.10780 tokens/s**, excluding prompt processing
and host return. These are finite runs, not sustained-generation guarantees.

The matched injected-cache past-13 result is **0.10024 tokens/s** over three
samples, but one takes **10.019182 seconds**. Mean latency is 9.975859 seconds,
range 9.953339–10.019182 seconds, population standard deviation 0.030642 seconds.
The previous 0.1-token/s result remains valid for its own recorded samples;
this independent sweep shows why its narrow margin was not a per-request promise.

Context matters: cached delivered throughput falls to **0.06390 tokens/s at
past 128**, **0.02899 at 512**, and **0.01671 at 1023**. The longest-context cache
was independently prepared on the native host and injected. It does **not**
measure physical-board prefill from an empty 1023-token prompt.

Prefill matters too: the 64-token synthetic prompt takes **397.947 seconds**
of on-FPGA prefill and **399.075 seconds** through delivery of one new token.
Model first-token timestamps are not streamed host TTFT: the host receives
the output batch only after safe ownership return.

## Coverage, correctness and accounting

The matrix contains 13 full requests, 15 unprofiled injected-cache requests and
three phase profiles. Full requests process **210 prompt tokens** and emit
**77 new tokens**. Four uninterrupted 16-token requests cover story twice and
science/computing once. Prompt lengths are 1/8/13/16/32/64, output lengths
1/2/4/16, and cached past lengths 1/8/13/32/128/512/1023. Profiles cover
past 13/128/1023. The 32-output extension was omitted before measurement because
the frozen independent generation oracle contains 20 steps; no long oracle
extension or extra board endurance run was needed.

Every trial checks every generated token ID, all 50,257 final logits and every
valid K/V position in all twelve layers against the independent qualified M4
reference. The original 2/1/1 requests, five selected story-prefill traces,
overflow non-mutation and accepted recovery pass. The past-1023 cases check
all 1024 valid positions after the forward. This is exact agreement with the
qualified quantized model, not a claim of universal floating-GPT-2 token identity
or a new language-quality evaluation. Historical model quality remains in
[M4 verification](M4_VERIFICATION.md).

One observed overlay/arena/model/firmware provisioning takes **19.365524 seconds**;
it is not a power-on cold start. Across this deliberately mixed full-request
matrix, 77 output tokens divided by summed resident delivery time is
**0.04425 tokens/s**. Charging those same 77 tokens the entire board campaign,
including all unrelated-to-delivery diagnostics, staging, checks and cleanup,
gives **0.03342 tokens/s**. Neither aggregate is a universal application rate;
the workload-specific table below is the useful performance description.

All observations remain in [samples](m5_sweep_samples.csv), including the
above-10-second anchor. [Continuation intervals](m5_sweep_continuation.csv) retain
all 64 additional-token model intervals. Machine evidence embeds the complete
raw campaign, references, phase records and statistics:
[m5_sweep_evidence.json](m5_sweep_evidence.json). Means, medians, extrema,
population standard deviations and sample IDs are retained for identical
workload/profiling groups; profiled timings are never pooled with plain timings.

## Bottleneck and resources

At past 13, CPU/control/scalar-memory remainder is **84.59%** of model time.
At past 1023 it is **96.63%**. Attention alone grows from **1.288 seconds**
to **51.150 seconds**, including **50.504 seconds** of remainder at the endpoint.
The complete long-context profile spends only **0.102 seconds in GEMM compute**
and **0.588 seconds in SFPU compute**, nested within **1.984 seconds of service**.
Increasing GEMM peak throughput alone therefore cannot address the dominant
observed cost. Scalar attention preparation/reduction and its memory/control
work are the clearest long-context investigation target; this sweep does not
separate arithmetic instructions from scalar-memory stalls.

The 16/32/64-token prompt cases all peak at **2,371,652 bytes** of scratch;
chunking keeps that peak bounded rather than allocating for the full prompt.
The fixed allocation remains **266,289,152 bytes (253.953 MiB)** in a 256-MiB
virtual arena: model 205,340,672 bytes, full K/V 36 MiB, auxiliary K data
10.125 MiB, work region 4 MiB and trace region 8 MiB. The reopened DMA descriptor
has **owner=0, allocated_pages=0, pte_dma=0**, and the helper unloads normally.

The reused qualified 91-MHz overlay has **29,003 LUTs, 21,724 registers,
95.5 BRAM36, zero DSPs and 9,605 occupied slices (72.22%)**. Setup/hold slack
remains the previously qualified **+0.263/+0.018 ns**, with TNS/THS zero.
These are reused implementation results, not a new synthesis/timing run.
Both pipelined RV32MFast harts and the complete W8A8/int16 GPT-2 configuration
are unchanged. The source release is `e5883bcc99ad61bba381714781febb873a1101e3`.

## Limits and reproduction

The matrix is representative, not Cartesian, randomized or exhaustive. Length-8
full prompts use science/computing; other lengths use story or repeated/truncated
story tokens. The cached stream also changes selected token values with context.
Repetitions are small and contiguous. There is no QoS-tail, long endurance,
thermal, power/energy or universal 0.1-token/s claim.

Normal Linux/SSH activity and occasional read-only checkpoint copies were
present. Global swap occupancy changed during the campaign; no isolated-host or
no-swap claim is made, and the slower anchor is not attributed to a specific
cause. Device-owned inference tensors were not inspected. Traffic counters are
raw mover counters with the documented 32-bit limits, not total DDR traffic.
The mixed MAC/SFPU work counter is not converted into a GMAC headline.

See the [predeclared plan](M5_SWEEP_PLAN.md) and
[reproduction/accounting instructions](M5_SWEEP_REPRODUCE.md). The audit checks
hashes, every expected result, timing boundaries, all samples, safe release and
the earlier qualification chain, and runs the negative/mocked safety tests:

```sh
python3 -m scripts.audit_m5_sweep
```

## Recorded sweep tables

Generated from every passing observation; raw skips/failures remain in the CSV and campaign.

### Full requests: on-board prompt processing included

| Prompt | Input tokens | New tokens | Repeats | Mean model, s | Mean delivered, s | Aggregate new tokens/s |
|---|---:|---:|---:|---:|---:|---:|
| story | 13 | 2 | 1 | 73.163 | 74.222 | 0.02695 |
| science | 8 | 1 | 1 | 40.375 | 41.430 | 0.02414 |
| computing | 8 | 1 | 1 | 40.399 | 41.455 | 0.02412 |
| story_length_1 | 1 | 1 | 1 | 8.557 | 9.612 | 0.10403 |
| story_length_16 | 16 | 1 | 1 | 79.672 | 80.724 | 0.01239 |
| story_length_32 | 32 | 1 | 1 | 172.843 | 173.904 | 0.00575 |
| story_length_64 | 64 | 1 | 1 | 398.019 | 399.075 | 0.00251 |
| story | 13 | 1 | 1 | 64.162 | 65.215 | 0.01533 |
| story | 13 | 4 | 1 | 90.947 | 91.999 | 0.04348 |
| story | 13 | 16 | 2 | 203.311 | 204.365 | 0.07829 |
| science | 8 | 16 | 1 | 175.835 | 176.890 | 0.09045 |
| computing | 8 | 16 | 1 | 175.805 | 176.858 | 0.09047 |

### Prefill and internal continuation

First-token time is a model timestamp, **not streamed delivered TTFT**. Continuation
excludes prefill and host return; tokens are delivered together after the request.

| Request | Mean prefill, s | Prefill input tokens/s | Model first token, s | Mean finite continuation tokens/s |
|---|---:|---:|---:|---:|
| story:g2 | 64.198 | 0.20250 | 64.271 | 0.11245 |
| science:g1 | 40.302 | 0.19850 | 40.375 | — |
| computing:g1 | 40.328 | 0.19837 | 40.399 | — |
| story_length_1:g1 | 8.485 | 0.11786 | 8.557 | — |
| story_length_16:g1 | 79.600 | 0.20101 | 79.672 | — |
| story_length_32:g1 | 172.770 | 0.18522 | 172.843 | — |
| story_length_64:g1 | 397.947 | 0.16083 | 398.019 | — |
| story:g1 | 64.090 | 0.20284 | 64.162 | — |
| story:g4 | 64.093 | 0.20283 | 64.165 | 0.11202 |
| story:g16 | 64.090 | 0.20284 | 64.162 | 0.10780 |
| science:g16 | 40.302 | 0.19850 | 40.375 | 0.11073 |
| computing:g16 | 40.328 | 0.19837 | 40.399 | 0.11078 |

### Injected valid-cache decode, profiling disabled

Independent native prefill and seed restoration are outside this request boundary.

| Past | n | Mean model, s | Mean delivered, s | Delivered min–max, s | Population σ, s | Aggregate tokens/s |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2 | 8.427 | 9.479 | 9.478–9.481 | 0.00112 | 0.10549 |
| 8 | 2 | 8.688 | 9.746 | 9.746–9.746 | 0.00009 | 0.10260 |
| 13 | 3 | 8.898 | 9.976 | 9.953–10.019 | 0.03064 | 0.10024 |
| 32 | 2 | 9.932 | 10.988 | 10.986–10.990 | 0.00206 | 0.09101 |
| 128 | 2 | 14.596 | 15.649 | 15.648–15.651 | 0.00106 | 0.06390 |
| 512 | 2 | 33.432 | 34.489 | 34.486–34.493 | 0.00371 | 0.02899 |
| 1023 | 2 | 58.787 | 59.841 | 59.841–59.842 | 0.00078 | 0.01671 |

### Diagnostic phase totals

GEMM and SFPU are **inside** service, not additional time. The remainder includes
CPU work, control and scalar-memory latency; it is not an arithmetic-only counter.

| Past | Model, s | Remainder, s (%) | Service, s | GEMM, s | SFPU, s |
|---:|---:|---:|---:|---:|---:|
| 13 | 8.925 | 7.549 (84.59%) | 1.375 | 0.087 | 0.292 |
| 128 | 14.627 | 13.175 (90.08%) | 1.451 | 0.089 | 0.330 |
| 1023 | 58.839 | 56.854 (96.63%) | 1.984 | 0.102 | 0.588 |

All samples, per-token continuation intervals, phase counters, traffic and workspace
are preserved in the embedded machine evidence and ignored build CSV/JSON artifacts.
