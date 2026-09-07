# Current project status

**Latest qualified system:** [M5 fast-controller pass](docs/M5_FAST_RESULTS.md),
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
