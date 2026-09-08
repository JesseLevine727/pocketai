# M5 startup and prompt-inclusive performance

**CLOSED / PASS.** This is a pre-M6 engineering extension, not the M6 report.
All required original short-request repetitions, both cold-initialization
diagnostics and both-prefix maximum-context repetitions pass. The read-only
chained audit binds the complete evidence. No sustained or arbitrary-content
latency guarantee is claimed; the short-request timing margin is only 3.1 ms.

## What changed

The design still runs the complete GPT-2 W8A8/int16 model on two autonomous
fast-multiply Ibex harts and the existing GEMM/SFPU engines. The A9 provisions,
controls and checks; it does not perform inference. All 12 layers and heads,
50,257 logits and the complete valid raw KV remain checked exactly.

Cold preparation now uses packed key transpose, parallel extrema/unit setup,
maximum-bounded exact integer conversion and consumer-ready layouts. Derived
V rows materialize on demand only when the exact integer attention probability
requires them. A validity bit certifies all 64 features at the current maxima;
maximum changes invalidate the head. Complete preparation and first-demand
work are included in initialization accounting. No numerical work was moved
before START, and no future or repeated-prompt state is memoized.

Prompt processing reuses exact projection and smoothing metadata across rows,
parallelizes quantization and first-use scalar setup, and uses packed I/O.
Integer enclosures certify the original final rounding or the original exponent
choice; uncertainty executes the complete old path. A call-local residual
metadata cache is tagged by the last accepted exponent and rebuilt after a
change or fallback. Narrow cached biases are stored only when the already
rounded integer fits exactly; wider values retain full generic computation.

Projection borrows the existing 4-KiB score BRAM after attention has finished.
Tentative outputs use it up to 2,048 columns; exact cached int16 biases can share
it up to 1,024 columns. The halves are disjoint and worker calls join before
publication or reuse. Larger vectors retain DDR scratch. There is no new
workspace allocation or reduced stack/score capacity. Ready and trace images
contain the same numerical operators with their respective execution paths.

The measured instruction-fetch bottleneck also required qualified RTL changes:
a coherent 64-KiB instruction mirror, registered sequential lookahead, direct
instruction responses, a second coherent 64-KiB data-read mirror, and direct
data responses with registered shared-bus fallback. Every accepted original
RAM write updates both copies with the original byte enables. All new BRAM
controls are synchronous. DDR/peripheral routes, ownership, abort and drain
semantics remain unchanged. No instruction cache or slow multiplier is enabled.

## Timing and resources

Selected hardware is `build/m5_startup_data_finish_v1`, synthesized from
`build/m5_startup_data_direct_pynq_v2` and simulated by
`build/m5_startup_data_direct_autonomous_v2`.

| Routed hardware check | Result |
|---|---:|
| Clock | 91 MHz |
| Setup WNS / required minimum | +0.269 / +0.250 ns |
| Hold slack | +0.008 ns |
| Total setup / hold violations | 0 / 0 |
| DSPs | 0 |
| LUTs / registers | 29,229 / 21,833 |
| BRAM36-equivalent tiles | 127.5 / 140 |
| Occupied slices | 9,752 |
| Routable nets routed | 45,626 / 45,626 |

The mirrors explicitly cost 32 additional BRAM36s: 16 for instructions and
16 for data reads. This is a resource tradeoff, not an unchanged-overlay claim.
Routed DRC retains only the reviewed RTSTAT-10 warning. Seven existing
reset-LUT methodology warnings have individually checked truth tables and the
same seven registered reset/control sources; no new data-dependent reset is
waived. Rejected timing, asynchronous-BRAM-control and capacity candidates were
not deployed. The final clock uncertainty and every acceptance limit remain
unchanged after post-route optimization.

## Measurement boundary

Delivered latency starts before START/ownership transfer and ends after safe
DMA RETURN and token copy. It includes actual prompt prefill, first-use
preparation, inference and token selection. Output tokens alone form the
throughput numerator. Provisioning, firmware/overlay loading and post-delivery
verification are recorded separately and are not called inference time.

The older approximately 45-second cold-forward figure included inference: the
initial diagnostic separately measured 35.0171 seconds of cold-head preparation
and 44.8788 seconds through delivery. Later accounting is stricter: complete
prepare calls plus first-demand materialization. Raw-prefix availability is an
explicit condition of cold maximum-context tests, not a claim of full-1024
prompt prefill. Short-request tests begin with the actual original prompts and
no prefix cache.

The final three plain repetitions of each original request all pass individually:

| Original request | Output tokens | Delivered range (s) | Mean delivery (s) | Output token/s |
|---|---:|---:|---:|---:|
| Science, 8-token prompt | 1 | 9.990257–9.996906 | 9.993854 | 0.100061 |
| Computing, 8-token prompt | 1 | 9.994261–9.995312 | 9.994739 | 0.100053 |
| Story, 13-token prompt | 2 | 16.601940–16.605436 | 16.603659 | 0.120455 |

Throughput is total output tokens divided by total delivered time; the mean
does not conceal a failing sample. Firmware execution averages about 8.94 s for
the one-token requests and 15.55 s for story; approximately 1.05 s of safe
ownership/control/delivery overhead remains included in the headline latency.
The prior matched plain deliveries were 30.826094 s, 30.866358 s and 52.559107 s,
respectively: approximately **3.1x faster prompt-inclusive delivery**.

The worst final short-request margin is **3.094 ms**. The first screen also
passed, with only 6–11 ms margin. These measurements barely clear the specified
gate; they do **not** establish robust tail latency, sustained throughput or
performance for arbitrary prompt content. Provisioning-inclusive startup from
an unloaded board is also not a 0.1-token/s claim.

Required cold derived initialization measures **5.2726 s story / 5.4222 s
science**, with **10.4909 / 10.5961 s** delivered cold forwards from independent
raw past-1022 prefixes. Both required <=10-s initialization / <=20-s cold
delivery gates pass. The preferred <=5-s initialization stretch is **not met**;
the <=15-s cold-delivery stretch is met. The three final story cold forwards
take 10.4546–10.4573 s and their genuine warm last-slot continuations take
5.0842–5.0905 s. The three final science cold forwards take 10.5578–10.5672 s;
their warm continuations take 5.3365–5.3383 s. All six warm continuations reach
1024 valid KV positions and meet the <=10-s delivered maximum-context gate.

## Verification and evidence

The candidate and fresh reproduction pass the full native suite, including
396 full-model tensors / 4,670,788 values, 60 generation outputs, all final
logits and full valid KV; threaded attention/layout/first-use checks through
1024 positions; arithmetic ties/extrema; workspace/overflow non-mutation; and
metadata fallback/tag/buffer-boundary cases. All four firmware binaries are
byte-identical. Conservative per-hart stack bounds are 3,136 bytes runtime/trace,
3,040 profile and 3,056 detail, below the unchanged 4,096-byte limits.

RTL checks include exact two-hart repeated probes, original and expanded
memory/code-coherence tests, normal and delayed accelerator tests, and router
scoreboards for ordinary, direct-response and lookahead modes. Physical checks
compare tokens, every final logical logit, complete valid raw KV and the original
story traces, plus overflow/recovery and normal zero-owner/pages/PTE release.

Each campaign has a 3,600-second bound including staging, queueing, checks and
cleanup, with a 120-second cleanup reserve. No full-1024 physical prefill,
endurance or sustained-generation experiment is required. Slower/failed trials,
actual deployed runners and their identities are retained across all **38**
physical campaigns. The selected story diagnostic/final campaigns take
174.14/325.08 s including staging, and the science diagnostic/final campaigns
159.38/157.91 s. Earlier M5 audits remain intact. The complete machine-readable
record is [startup evidence](m5_startup_evidence.json); validate it with
`python3 -m scripts.audit_m5_startup`. All 27 measurement/runner/audit unit tests
pass, including rejection of individual latency misses and unsafe cleanup.

See [reproduction](M5_STARTUP_REPRODUCE.md), [requirements](M5_STARTUP_PLAN.md)
and the [chronological experiment record](M5_STARTUP_PROGRESS.md). M6 and pushing
remain separately gated.
