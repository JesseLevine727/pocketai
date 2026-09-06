# M5 performance — measurement pending

No physical M5 GPT-2 throughput, TTFT or speedup is accepted yet. The final
overlay is implemented at 91 MHz with +0.433 ns setup margin. Clock closure and
native-host correctness do not establish physical inference performance.

The premeasurement policy is
[`tests/m5/performance_policy.json`](../tests/m5/performance_policy.json),
`m5-lean-physical-v1`. Three original prompts run in fixed order: story produces
five tokens, then science/computing one each. The first of four story decode
intervals is a retained warmup; the next three provide a small descriptive
sample. Context grows at each step, so these are not identical-context repeats.
No hour-scale context or endurance campaign is required for lean M5 closure.

The primary throughput boundary runs from resident host START through safe DMA
ownership return and copying output IDs. It includes required firmware
initialization, metadata, operators, packing, transfers, KV, full logits,
greedy selection, synchronization and delivery. Independent exact checking is
excluded. Firmware reports its own model-loop time, first token ready in DDR,
forward-only prefill and decode intervals including token selection. Since the
runner delivers tokens after DONE and ownership return, firmware token-ready
time must not be described as interactive host TTFT.

The story prefill includes five trace copies; their cost remains in that run.
Startup/provisioning is recorded once separately from resident request time.
All samples are retained. Median, interpolated p95, range and population
standard deviation from three observations describe only those observations.
Engine counters overlap wall time; their sum is not another model latency.

Any M4 comparison must label the historical workload, clock and host/runtime
differences. There is currently no M5 speedup claim. The user selected
**>=1 token/s as a stretch target**; functional closure does not require a
positive speedup. Physical correctness and measured results remain required.
