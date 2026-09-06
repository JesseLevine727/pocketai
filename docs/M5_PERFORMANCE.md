# M5 performance — qualified autonomous inference

The final PYNQ-Z1 campaign passes at **91 MHz**. M5 delivers real autonomous
GPT-2 inference, but it is slow: the representative resident request achieves
**0.01010 output tokens/s including prefill and delivery**, while three cached
decode intervals achieve **0.02528 tokens/s**. Neither is a kernel-only rate.
The user-selected **>=1 token/s stretch target was not met**; no speedup is claimed.

Source data: [complete physical report](m5_physical_evidence.json),
[closure/source/artifact pins](m5_closure_evidence.json), and local terminal log
`build/m5_physical.6jgElc/m5_physical_o2.log`. The campaign exits 0 and returns
DMA ownership; final allocation cleanup and normal helper unload also pass.
The final `-O2` firmware preserves the frozen adaptive-v3 model/numerics and
matches every observed token, final full-logit/KV hash and selected trace.

## Measurement boundaries

The policy was frozen before measurement in
[`tests/m5/performance_policy.json`](../tests/m5/performance_policy.json),
`m5-lean-physical-v1`. Fixed order: story produces five tokens, then science
and computing one each. Every case starts with cache-valid length zero; model,
overlay and mapped pages remain resident, with firmware reloaded and verified
before each boot. These are resident measurements, not disk-cold startup.

The primary interval is **host START through safe RETURN_CPU and copying the
generated token IDs**. It includes required ownership synchronization, firmware
initialization, metadata, operators, packing, transfers, KV, full logits,
greedy selection and delivery. Independent output checking is outside timing.
During execution the A9 only polls supervisor status; it does no tensor work,
operator scheduling, transfer service or token selection.

Firmware separately records its model loop, forward-only prefill and each
token-publication timestamp using 64-bit cycle differences. Its first-token
time means **ready in DDR**, not interactive host TTFT: this runner delivers
all tokens only after DONE and safe ownership return. Five story prefill
trace copies remain included in the measured work. No cost is subtracted to
make the result appear faster.

## Complete resident requests

| Prompt | Input / new tokens | START through delivery (s) | Primary output tok/s | First token ready in DDR (s) | Forward-only prefill (s) |
|---|---:|---:|---:|---:|---:|
| story | 13 / 5 | 494.913238 | 0.010103 | 335.995567 | 335.923020 |
| science | 8 / 1 | 208.818166 | 0.004789 | 207.755157 | 207.682618 |
| computing | 8 / 1 | 208.869540 | 0.004788 | 207.804390 | 207.733442 |

The firmware-only model-loop times are 493.854598, 207.755162 and 207.804394
seconds respectively. The primary throughput includes the larger, required
request boundary above; the faster firmware-only number is not the headline.
For the one-token cases, generation rate is dominated by prefill and should
not be interpreted as steady-state cached-decode throughput.

## Cached decode: one warmup plus three samples

All four consecutive story token-to-token intervals, in seconds:

```text
39.167862242  # retained warmup, excluded from the summary below
39.308302143
39.520934890
39.861927989
```

For the three predetermined measured samples:

- Median: **39.520935 s/token**.
- Aggregate rate, `3 / sum(intervals)`: **0.025275681 tok/s**.
- Mean: 39.563722 s; minimum/maximum: 39.308302 / 39.861928 s.
- Linearly interpolated p95: 39.827829 s; population standard deviation: 0.228033 s.

Contexts grow by one at each decode step. These are not three repeats at an
identical context, and n=3 is descriptive only: it does not establish tail
latency, statistical significance or long-run reliability. The request and
cached-decode rates measure different boundaries, not contradictory results.

## Provisioning, memory and transfer observations

One provisioning observation takes **21.650612 seconds**, excluded from the
resident request numbers. This is not a complete process-start/disk-cold or
repeated startup benchmark. The runner allocates **266,289,152 bytes** across
65,012 kernel-owned pages in a bounded 256-MiB device-virtual arena. This
includes the full 1024-position int16 K/V and derived cache capacity, not a
shortened or evicting cache. The final post-campaign allocation-only check
takes 2.043103 seconds, then close/reopen confirms zero retained pages.

Linux reports 503,464 KiB total RAM. During the model campaign:

| Observation (KiB) | Before provisioning | Provisioned | After cleanup |
|---|---:|---:|---:|
| MemAvailable | 399,140 | 155,248 | 418,744 |
| SwapFree | 461,308 | 429,052 | 427,772 |
| CmaFree | 13,284 | 14,908 | 6,480 |
| Process peak RSS | 55,820 | 326,360 | 326,360 |

Peak RSS is a high-water mark, not post-cleanup live usage, and includes mapped
arena pages; **do not add the arena size to RSS**. The process peak is about
318.71 MiB. Kernel-owned DMA pages remain resident, but Linux global swap use
changed. Process VmSwap was not sampled: no claim of a swap-free process or
system is supported. No CMA resizing, cache dropping or boot changes were used.

| Prompt | Completed transfers | Mover bytes read | Mover bytes written | Workspace high-water (bytes) |
|---|---:|---:|---:|---:|
| story | 64,112 | 768,619,260 | 24,339,028 | 1,909,188 |
| science | 18,815 | 189,965,772 | 10,863,812 | 1,793,988 |
| computing | 18,815 | 189,965,772 | 10,863,812 | 1,793,988 |

These are transfer-mover counters, not all system DDR traffic; firmware direct
loads/stores and model provisioning have different paths. Raw engine-cycle
counters are modulo 2^32, and the work counter mixes GEMM MACs with SFPU
elements. They cannot support a pure GMAC/s figure or a disjoint CPU/transfer/
engine latency decomposition. Software float64 metadata and serialized uncached
DDR/local-bus traffic are plausible overhead sources from the architecture,
**not a measured bottleneck attribution**.

## Historical M4 context and qualification limits

[M4's frozen results](SPEEDUP.md) used a 95-MHz overlay with A9 orchestration.
Its story TTFT median was 71.242 seconds (20 observations), and fixed-context
cached decode was about 18.648 seconds/token (0.05363 tok/s). The historical
20-output story generation rates were 0.04619 tok/s with FPGA offload and
0.17624 tok/s on the A9 CPU. M5 moves the orchestration and numerical metadata
onto small bare-metal Ibex cores; the present measurements do not show a
performance win.

These are **historical, unpaired comparisons**: clocks, runtime, output count,
context progression, tracing and sample counts differ. No speedup ratio is
computed from the unmatched runs, and no M4 marathon was repeated for one.
The earlier `-Os` attempt did not preserve complete timing, so no measured
`-O2` improvement is claimed either.

Lean M5 qualifies short autonomous correctness, safe ownership, full capacity,
positive timing margin and honest physical measurements. It does not claim
a new empty-cache 1024-position autonomous endurance run, interactive token
streaming, disk-cold behavior, broad statistical coverage, or the stretch rate.
