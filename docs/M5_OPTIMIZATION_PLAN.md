# M5 optimization goal — measured performance, bounded effort

Status: **CLOSED — QUALIFIED**, 2026-09-06 UTC. Baseline: pushed M5 closure
`d0398d39a0d6252a8c0148be06a2075b8c937049`. M5 remains closed; this is a separate
optimization pass, not M6 and not retroactive alteration of M5's results.

All six points have qualified outcomes or explicit evidence-backed dispositions;
see [results](M5_OPTIMIZATION_RESULTS.md) and [machine evidence](m5_opt_evidence.json).
The retained exact firmware improves matched cached START-through-delivery
throughput 1.565x. New cache/queue RTL is deferred, the simple W4A8 candidate is
rejected, and W4A4 is deferred. Final physical 2/1/1 requests, full logits/KV,
selected traces, rejection/recovery, zero retained pages, normal unload,
reproducible firmware and both original/new evidence audits pass. No M6 or push.

The user authorized the six points from the first-principles review, with no
exhaustive hours-long experiment campaigns. Necessary scoped board work,
temporary helper load/unload and safe recovery are preauthorized. No routine
approval prompts, stored credentials, unrequested agents or automatic push.
Preserve unrelated `NA/`. The diagnosis workflow uses a short exact feedback
loop, ranked hypotheses and one-variable comparisons before adopting changes.

## Outcome and boundaries

Improve real physical latency of the autonomous GPT-2-small/124M system. Preserve
12 layers, 12 heads, all 50,257 logits, learned positions, full 1024-capacity KV,
the exact accepted W8A8/int16 path and safe ownership/drain/reset/free ordering.
A9 still only provisions and handles tokens/status; no in-run tensor worker.
>=1 token/s remains stretch. Do not manufacture a speedup or silently weaken
numerics, model size, context, output checks or safety.

Keep frozen baseline source/artifact pins unchanged. New harnesses, firmware,
representations and reports get separate identities; baseline copies or
explicitly hashed derivations must remain available. A change to common source
invalidates the corresponding old-source audit, not historical measurements;
prefer isolated optimization sources so the original auditor remains runnable.

## Six points and gates

| Gate | Required work | Acceptance |
|---|---|---|
| P0 | Freeze scope, test costs, fixtures and performance boundaries | This plan and `tests/m5_opt/performance_policy.json` before measurement |
| P1 | Profile a representative cached token; distinguish CPU metadata, operator service and engine work | Exact physical baseline, bounded 64-bit counters, explicit exclusive/inclusive accounting and ranked bottleneck evidence |
| P2 | Remove redundant metadata work, invariant divisions, duplicate scans and conversions | Exact reference comparisons and matched physical timing; retain only useful changes |
| P3 | Improve hot-data locality with BRAM buffers or a cache | Profile-justified implementation, or quantified reason to defer; genuine accelerator access/coherence and bounded ownership |
| P4 | Improve job granularity, activation reuse, queuing/overlap or fusion | Correct dependencies/rounding/error lifecycle and measured improvement, or evidence-backed deferment |
| P5 | Improve the remaining arithmetic bottleneck | Focused portable CPU/SFPU/decode datapath change with qualification, or evidence-backed rejection |
| P6 | Bounded W4A8 quality/storage/cost experiment; conditional W4A4 | Independent quality evidence and realistic packing/scaling cost; adopt only if justified; negative result valid |
| P7 | Final short exact physical checks, performance, cleanup and documentation | All six points accounted for, source/artifact pins, read-only audit and scoped local commit |

An evidence-backed deferment is allowed when a point is not worthwhile within
the lean pass. It must state the measured evidence, engineering cost, rejected
alternative and next concrete experiment. Merely calling a task difficult or
omitting it is not acceptance. Do not pursue diminishing returns indefinitely.

## Cost policy

- Default local tests and physical diagnostic requests: <=120 seconds each.
- One bounded quantization-quality candidate: <=10 minutes. Freeze a small
  candidate/sample set and its quality criteria before evaluating outputs.
- Final physical acceptance: <=20 minutes total watchdog, including model
  execution and checks. Prefer a short complete request and reusable resident
  allocation; do not repeat expensive provisioning unnecessarily.
- No empty-cache 1024-position marathon, 3x20 generation matrix, endurance/tail
  study, exhaustive calibration sweep or duplicate implementation build.
- An inherently long FPGA implementation is not an endurance experiment:
  permit one necessary final candidate after focused simulation. Do not launch
  speculative seed/strategy sweeps. Any reroute needs a documented relevant
  source/timing invalidation or a concrete correction to the failed candidate.
- Reuse unaffected native/ISA/component evidence. Run affected fast regressions
  before board work; retain failed samples instead of selectively reporting.

## P1 — reproducible short diagnosis

Build a pinned cache snapshot independently of the FPGA result. For the fixed
story prompt, qualify the prefill snapshot and its logits against frozen M4
hashes. Feed the first reference-generated token to one cached forward at a
fixed past length of 13; require the second reference token and exact final
logits/KV. Restore the same snapshot before each sample. This is **seeded-cache
decode-only** evidence, never an empty-cache or endurance claim.

Use the accepted overlay and numerical sources for an initial instrumented
firmware variant. Record its separate identity. Compare profiling enabled and
disabled on the same harness; do not assume instrumentation is free.
Use 64-bit cycle differences. Capture each operator's existing 32-bit engine
counter before aggregate overflow can occur, then accumulate in 64 bits.

Primary phase intervals are exclusive and sum to the model time within
explicit start/end/profiling overhead. Backend service intervals include
submission, DMA and engine completion. Engine work is nested inside service,
not additive to it. `phase - backend_service` includes firmware scalar work
and its memory stalls; it does not split those causes by itself. Short local
versus DDR and integer versus software-f64 probes distinguish those hypotheses
if the initial profile leaves that decision material.

Ranked falsifiable hypotheses from the review:

1. Scalar DDR and software metadata dominate: CPU/non-service intervals will
   dominate and locality/invariant-metadata probes will reduce them.
2. Small synchronous jobs dominate service overhead: total service will greatly
   exceed nested engine cycles; coarser jobs/reuse should reduce the gap.
3. Arithmetic throughput dominates: nested GEMM/SFPU compute will occupy a
   substantial measured fraction; optimize the responsible engine, not all.
4. Bulk bandwidth dominates: measured transfer service and a bounded contiguous
   read probe will explain most latency; only then prioritize width/W4 traffic.

## P2–P5 — implementation guardrails

Preserve reference rounding/bias/saturation/epsilon and dynamic-scale semantics.
Precomputing immutable reciprocals is different from replacing dynamic values
with constants. Do not silently approximate float64 with float32/fixed point.
Write a regression at the actual numerical or memory seam before adopting a
transformation; compare exact logits/KV for the final W8A8 path.

Budget from the actual baseline: 24,758 spare LUTs, 84,712 registers and 44.5
BRAM tiles; 71.55% of slices already occupied. Current DMA accepts only the
protected DDR arena. A local buffer requires an actual accelerator-visible
path, or correct cache synchronization—not moving a pointer and hoping DMA
can read it. Maintain protection, hazards and reset/drain behavior.

Prefer feeding existing hardware efficiently over adding idle MAC rows.
Exploit queue slots only with real asynchronous ownership and dependency
tracking. Preserve wide sums and common-scale decisions when fusing stages.
Faster multiplication, exact pipelined SFPU and a decode-oriented datapath are
candidates, not predetermined changes irrespective of the profile.

Keep portable zero-DSP/no-FPU hardware by default. A DSP-specific backend,
floating-point ISA, reduced clock gate or different model-quality contract is
a material direction change, not covered by routine approval removal.

If RTL changes: one final source-checked clean 91-MHz overlay must have
WNS >= +0.250 ns, TNS=0, positive hold, DSP=0, fully routed/constrained, zero
DRC/methodology errors or critical warnings, and reviewed remaining warnings.
+0.500 ns is preferred. Firmware-only changes do not invalidate routing.

## P6 — low-precision decision

Freeze the candidate and a small independent quality subset before testing.
Compare W4A8 to the original floating GPT-2 and accepted W8A8, not just another
quantized implementation. Report quality metrics, clipping, memory savings
and unpack/scaling costs. Keep embeddings, KV and accumulation precision
explicit: halving the GEMM weights alone saves about 30% of the current model
payload, not half the entire arena.

Use a versioned representation; do not overwrite the frozen W8 pack. Build
packed-weight hardware only if quality and expected system benefit justify it
within this pass. A bounded negative result is useful. W4A4 is conditional on
W4A8 evidence and the remaining bottleneck; defer it explicitly if activation
quality risk or implementation cost exceeds the demonstrated benefit.

## P7 — closure

Final physical checks use the original prompts, at least two generated tokens
for the representative prompt and one for each other prompt. Require exact
tokens and final complete logits/KV on the retained W8A8 path; selected traces
when affected. Test bounded overflow/non-mutation, recovery and normal cleanup.

Report paired fixed-context decode (one warmup + three samples), one short
complete resident request including safe return/delivery, provisioning
separately, resource/memory/timing, all samples and limitations. n=3 is not a
tail-latency guarantee. Historical M5/M4 results retain their different scopes.
Every point gets a measured outcome or explicit justified disposition. Finish
the source/artifact audit, concise results docs and a scoped local commit.
No automatic push or M6 work. Planning alone does not complete this goal.
