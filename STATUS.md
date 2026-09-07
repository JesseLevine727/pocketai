# Current project status

**Latest qualified system:** [maximum-context M5 extension](docs/M5_CONTEXT_RESULTS.md),
**CLOSED / PASS — >=0.1 delivered token/s at the measured maximum cached context.**
All six final unprofiled past-1023 forwards reach 1024 valid K/V positions in
<=9.469 s. Story averages **8.974859 s / 0.111422 token/s**; the harder science
prefix averages **9.467926 s / 0.105620 token/s**. Worst observed margin is 531 ms.
The matched original story baseline is 60.730311 s: **6.7667x delivered speedup**.
Exact consumer-ready caches, selective updates and two-hart preparation retain
the full W8A8/int16 model, both fast multipliers and the same 91-MHz DSP0 overlay.
Cold derived preparation stays timed on FPGA (~45 s); this is last-slot resident
decode, not long-prompt prefill, sustained generation or arbitrary-content/tail
latency assurance. All logits/KV, original full 2/1/1 requests/story traces,
overflow/recovery, threaded/edge tests, byte-identical rebuild and normal
zero-resource release pass. Prior audits remain intact; intermediate misses and
the trace-fixture checker failure are preserved. Audit with
`python3 -m scripts.audit_m5_context`; see [evidence](docs/m5_context_evidence.json)
and [reproduction](docs/M5_CONTEXT_REPRODUCE.md).
**M6, ASIC/PPA and its report have not started.** The speed prerequisite is now
met; the bounded optimization ends here. Older measurements below are historical.

**Latest characterization:** [bounded M5 experiment sweep](docs/M5_SWEEP_RESULTS.md),
**CLOSED / PASS**. All 31 predeclared experiments pass in **38 min 24 s** of the
60-minute board cap, with no skips and normal zero-resource DMA release.
The design remains the qualified `e5883bc` release below; this pass changes no
firmware, hardware, precision or clock. Full 16-token requests deliver
**0.07829 token/s (story)** and **~0.09046 (science/computing)** including prompts.
Matched past-13 cached decode averages **0.10024 token/s**, but one sample takes
10.019 s; past-1023 cached delivery is **0.01671 token/s**. Context and prefill
cost are now measured explicitly. Long-context CPU/control/scalar-memory
remainder reaches **96.63%**, dominated by attention. Full logits/KV, original
traces and overflow recovery pass; all previous audits remain intact.
See [machine evidence](docs/m5_sweep_evidence.json), [samples](docs/m5_sweep_samples.csv)
and [reproduction](docs/M5_SWEEP_REPRODUCE.md). Audit with
`python3 -m scripts.audit_m5_sweep`. M6 is the next requested goal, not part of
this characterization closure.

**Latest qualified system:** [M5 0.1-token/s pursuit](docs/M5_TENTH_RESULTS.md),
**CLOSED / PASS — target achieved on the matched cached decode**.
Mean resident START-through-delivery is **9.958322 s / 0.10041853 token/s**,
up **21.53% throughput** from 12.102234 s / 0.08263 token/s. All three measured
samples are below 10 s, but margin is only 41.68 ms: not a sustained, tail,
long-context or prompt-prefill-inclusive guarantee. Model time is 8.896736 s.
Exact signed rounding, full-width channel multiplication and certified exact
reciprocals retain the same full W8A8 model and both fast harts / 91-MHz DSP0
overlay. Native/full-logit/KV/traces, original full 2/1/1 requests, rejection/
recovery, byte-identical rebuild and normal zero-resource DMA release pass.
Full campaign ~3 min 26 s; no marathon tests. Scalar/control/memory remainder
is still 84.59%; one token/s remains stretch. No M6 or new hardware.
See [evidence](docs/m5_tenth_evidence.json); audit with
`python3 -m scripts.audit_m5_tenth`.

**Previous qualified system:** [three more M5 search cycles](docs/M5_SEARCH_RESULTS.md),
**CLOSED / PASS**. Reject LTO; retain fused projection preparation and exact
integer/binary64 scaling. Matched cached-token delivery falls **13.27 → 12.10 s**
(**1.0962× throughput, 0.08263 token/s**); model time **12.21 → 11.04 s**.
Full-logit/KV/native checks, original 2/1/1 board requests and traces, overflow
recovery, byte-identical firmware reproduction and zero-resource normal DMA
release pass. Full requests take 91.33 / 51.09 / 51.12 s delivered; campaign
~4 min 2 s, no marathon tests. Both fast harts, exact W8A8, timed preparation
and the qualified 91-MHz DSP0 overlay are unchanged. The CPU/control/scalar-
memory remainder is still 87.55%; >=1 token/s remains stretch. No M6.
See [three reviews](docs/M5_SEARCH_REVIEWS.md), [evidence](docs/m5_search_evidence.json);
audit with `python3 -m scripts.audit_m5_search`.

**Previous qualified system:** [M5 scalar preparation](docs/M5_SCALAR_RESULTS.md),
**CLOSED / PASS**. Four exact optimizations reduce matched cached-token delivery
**16.74 → 13.27 seconds (1.2616× throughput, 0.07538 token/s)**; model time
15.68 → 12.21 s. CPU/control/scalar-memory remainder falls **24.24%**.
Native/full-logit/KV checks, original 2/1/1 board requests and traces, overflow
recovery, byte-identical firmware reproduction and normal DMA release pass.
Original full requests improve from 143.49 / 78.86 / 78.87 s delivered to
98.68 / 55.22 / 55.26 s. Full campaign ~4 min 19 s, no marathon tests.
Lazy quantizer setup stays inside model timing; no hidden persistent cache.
Both pipelined RV32MFast harts, exact W8A8 and the qualified 91-MHz DSP0 overlay
remain unchanged. Head preparation is still the largest phase; this is not
a hardware limit or global optimum. >=1 token/s remains stretch; no M6.
See [evidence](docs/m5_scalar_evidence.json); audit with
`python3 -m scripts.audit_m5_scalar`.

**Previous qualified system:** [three bounded M5 cycles](docs/M5_ITERATE_RESULTS.md),
**CLOSED / PASS**. Exact attention/LayerNorm preparation and projection range
specialization lower matched cached-token delivery **18.46 → 16.74 seconds**
(**1.1029× throughput, 0.05975 token/s**); model time 17.40 → 15.68 s.
The polling/WFI experiment is documented but not deployed: hart-0 sleep
undercounts its timer; hart-1-only sleep has no demonstrated material speedup.
Full original 2/1/1 board requests, logits/KV/traces, overflow non-mutation and
recovery, fresh binary reproduction, zero retained DMA resources and normal
helper unload pass. Full campaign ~5 min 51 s; no marathon tests or new RTL.
Both pipelined RV32MFast harts and the exact 91-MHz +0.263-ns / DSP0 overlay
remain. ~91% of model time is still scalar/control/memory remainder.

See the [three first-principles reviews](docs/M5_ITERATE_REVIEWS.md) and
[machine evidence](docs/m5_iterate_evidence.json); audit with
`python3 -m scripts.audit_m5_iterate`. No fourth cycle or M6 has started;
>=1 token/s remains stretch. Earlier results below are historical.

**Previous qualified system:** [M5 fast-controller pass](docs/M5_FAST_RESULTS.md),
closed with both Ibex harts using a pipelined RV32MFast derivative (9/12 execute
cycles), 91 MHz, +0.263-ns setup margin, positive hold and zero DSPs.
Exact preparation plus REQUANT8 lowers matched cached-token START-through-
delivery **25.70 → 18.46 seconds (1.393× throughput, 0.05418 token/s)**.
Fast-only improves model time about 2.4%; software supplies most of the gain.
Full 2/1/1 physical requests, logits/KV/traces, rejection/recovery and normal
cleanup pass. See [machine evidence](docs/m5_fast_evidence.json); audit with
`python3 -m scripts.audit_m5_fast`. No 1024 marathon. >=1 token/s remains
stretch; M6 has not started. The earlier results below remain historical.

M1–M5 are closed. The separate **M5 optimization pass is qualified**:
matched cached-token START-through-delivery improves **40.23 → 25.70 seconds
(1.565x throughput)** with exact W8A8 results and unchanged 91-MHz hardware.

See [full optimization results](docs/M5_OPTIMIZATION_RESULTS.md),
[six-point scope and dispositions](docs/M5_OPTIMIZATION_PLAN.md) and
[machine evidence](docs/m5_opt_evidence.json). Short physical 2/1/1 generation,
full logits/KV, selected traces, boundary recovery and cleanup pass. Additional
cache/queue hardware is deferred; the simple W4A8 screen is rejected and W4A4
deferred. >=1 token/s remains stretch. **M6 has not started.**

The earlier README, PLAN and milestone performance documents are frozen,
hash-audited closure artifacts; their historical numbers are intentionally
preserved. The follow-up does not replace those measurements or their scope.
