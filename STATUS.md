# Current project status

**Latest qualified system:** [M5 scalar preparation](docs/M5_SCALAR_RESULTS.md),
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
