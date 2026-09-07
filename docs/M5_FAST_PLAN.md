# M5 fast-controller goal — fast multiply and less scalar preparation

Status: **CLOSED — qualified fast hardware and exact faster software**.
Results: [M5_FAST_RESULTS.md](M5_FAST_RESULTS.md); reproducible evidence:
[m5_fast_evidence.json](m5_fast_evidence.json). Starting point: pushed optimization closure
`c40d7cd7effd3e03dfc0d42232f8c4ebb61d4f9c`. This is another bounded M5
performance pass, not M6. The user explicitly requires fast multiplication;
it is no longer an optional, low-priority candidate.

Frozen measurement contract:
[`tests/m5_fast/performance_policy.json`](../tests/m5_fast/performance_policy.json).

## Outcome

Qualify an autonomous full GPT-2 system with **fast multiplication on both
Ibex harts**, exact retained W8A8/int16 results, and measured real performance.
Start with the existing `ibex_pkg::RV32MFast` implementation. Do not substitute
`RV32MSingleCycle`, DSP primitives or a floating-point ISA without a separate
decision. Do not leave one hart on slow multiply as an unannounced compromise.
Historical M1–M5 builds may retain their original slow multiplier; the new
accepted overlay must actually instantiate the fast implementation.

Follow the measured bottleneck: the current profiled model spends 23.353 of
24.675 seconds outside accelerator service. Unprofiled fixed-context model
time is 24.648010 seconds; resident START-through-delivery is 25.704113 seconds.
Optional software changes must earn their place through exactness and measured
benefit. Fast multiplication is a required hardware deliverable even though
its whole-model speedup is not yet known. >=1 token/s remains stretch; do not
promise a particular speedup from an instruction-latency change.

## Scope and authority

- Preserve full GPT-2: 12 layers/heads, all 50,257 logits, learned positions,
  exact rounding/bias/saturation/epsilon/tie behavior and 1024-capacity KV.
- Keep A9 provisioning/token/status roles; no in-run A9 tensor worker.
- Keep zero DSPs, no F/D ISA and the 91-MHz qualification gate. Clock lowering,
  approximate numerics, a different model or a DSP-specific backend requires
  a material direction decision, not routine implementation approval.
- Scoped local edits, necessary builds and SSH board tests/helper load, safe
  recovery and unload are authorized. Never store credentials or bypass
  ownership, drain, reset or free ordering. Do not use JTAG.
- Preserve unrelated `NA/`. No agents, unrequested remote push or M6 work.
- Preserve prior source/artifact identities and runnable closure audits. Use
  isolated source targets or fail-closed, hashed derivations; historical
  measurements are not re-labelled as fast-core results. The old README/PLAN
  and milestone reports are audited artifacts; update the separate STATUS.

## Gates

| Gate | Deliverable | Required evidence |
|---|---|---|
| F0 | Scope, baseline and bounded measurement policy | This plan, dedicated policy, original M5 and optimization audits pass |
| F1 | Fast multiplier on both harts in the new target | Actual exported/elaborated configuration; focused arithmetic, stalls, interrupts and affected ISA/integration tests |
| F2 | Fine-grained preparation profile | Head preparation, dynamic quantization, LayerNorm and smoothing costs; distinguish CPU/service and explain unmeasured memory/arithmetic split |
| F3 | Two priority software investigations | Existing SFPU REQUANT8 offload and persistent/exact prepared metadata/head specialization; qualify useful implementations or record bounded negative results |
| F4 | Locality/fusion decision | Evaluate a targeted read-only buffer/scratchpad or wider operation against remaining scalar cost; implement only if a bounded justified extension fits this pass |
| F5 | One final fast-core FPGA implementation | Source-pinned clean build, 91 MHz, timing/resources/routing/DRC/methodology gates below |
| F6 | Physical fast-only and final qualification | Matched exact cached decode, complete 2/1/1 requests, affected traces, rejection/recovery and safe cleanup |
| F7 | Close honestly | All outcomes, ablations, remaining bottleneck, source/artifact pins, read-only audit and scoped local commit |

Fast multiply (F1/F5/F6) **cannot be deferred or reverted to slow and still
close this goal**. If the fast configuration cannot meet the preserved timing
and resource requirements, diagnose and correct it within scope; if a material
constraint change becomes necessary, report the conflict rather than silently
weakening a gate. Planning, synthesis alone or a build still running is not
completion.

## F1 — hardware configuration and correctness

Use the fast multi-cycle integer multiplier on both cores. RV32M instruction
semantics stay unchanged; the divider remains the existing iterative divider.
Preserve the accepted M5 LSU request and branch-stall corrections, register
file and other pipeline settings unless a specific failure justifies a scoped
change. In particular, do not revive the earlier source-export mistake.

The new source checker must verify **the multiplier configuration as well as
the patched LSU/ID source hashes**, including the actual resolved sources used
by Vivado and simulation. Check that both elaborated core instances use fast
multiply and that synthesis has not inferred DSP blocks. Source comments or a
parameter in an unused file are not evidence.

Before routing, run bounded directed/random signed and unsigned MUL/MULH/
MULHSU/MULHU checks, the affected divide corner cases, dependency/stall and
interrupt behavior, both-hart execution, patched LSU/branch regression and the
existing applicable RV32IMC ISA suite. Retain known historical expected failures
explicitly; do not broaden waivers to mask a new regression. Reuse unaffected
GEMM/SFPU numerical evidence, but test changed-core integrated transfers and
safe error/return behavior.

## F2–F3 — remove work before merely doing it faster

Use the existing independent seeded story decode: past 13, input 257, expected
output 582, valid cache 14. Keep model and full final logits/KV exact. Add only
the fine-grained instrumentation needed to distinguish the next candidates,
and compare profiling enabled/disabled where instrumentation changes timing.
Use 64-bit intervals; engine cycles are nested inside service, not additive.

Prioritized, falsifiable investigations:

1. **Existing REQUANT8:** CPU dynamic quantization does per-element multiply,
   rounding and saturation despite an existing SFPU operation. Test real
   conversions including int16/int32 expansion, DMA, output packing and launch
   overhead. Retain only if the complete conversion or relevant model phase
   improves. Do not assume operator-only speed makes the caller faster.
2. **Prepared metadata and head specialization:** avoid reconstructing
   immutable smoothing reciprocals/multipliers and eligible bias metadata for
   every token. Reuse channel scales between projection passes. Test exact
   power-of-two and zero-bias paths. For LayerNorm, exponent-zero correction
   may be specialized exactly; dynamic epsilon-dependent values must not be
   replaced with constants without proof. Start with the measured head cost.
3. **Controller arithmetic:** compare fast and slow hardware with identical
   retained firmware. Measure useful multiply/helper latency and model/request
   time separately. If available, add a small number of wait-event counters
   to the same planned hardware candidate; do not perform an extra FPGA build
   just for broad profiling infrastructure.

Precomputation happens once per defined model/runtime lifecycle, with versioned
identity, bounded storage, explicit invalidation and errors. Its cost belongs
in provisioning or required request startup, never silently omitted. Preserve
the original model pack, or version an exact derived representation separately.
All optional transformations get exact regression tests before adoption.

## F4 — targeted locality and wider operations

Consider a small read-only metadata line buffer or explicitly owned scratchpad
if post-software evidence supports it. Current CPU DDR accesses are single-word;
DMA accepts only protected DDR addresses. A local buffer must have a real
accelerator-visible path or a defined CPU-only role. Cache synchronization,
bounds, reset and ownership remain mandatory. Spare BRAM is not proof of
correct coherence or routability.

Broader fusion can remove CPU preparation and is **not** limited to the roughly
5.7% ceiling for accelerating existing backend service with CPU work fixed.
Evaluate hardware reductions, quantization/packing and projection finalization
against the scalar work they actually eliminate. Preserve common exponent/
shift dependencies, wide intermediate sums, rounding and complete logits;
multiple passes may still be necessary. Inspect the context-growing V-cache
scan as a future cost, without launching a long-context endurance campaign.

These larger extensions are conditional. An explicit decision may defer them
with measured evidence, expected work removed, integration cost and the next
small experiment. Do not turn this fast-core goal into an unbounded accelerator
redesign. No W4/W4A4 sweep or new precision contract in this pass.

## Build and test cost policy

- Reuse the accepted model, seed, fixtures and previous exact baseline results
  when measurement boundaries remain identical. Remeasure only when necessary
  for a valid comparison; keep all samples and report harness changes.
- Default focused host/board diagnostic execution <=120 seconds. Compiling an
  existing affected test suite is not an endurance experiment.
- Freeze the software candidate set after the two priority investigations;
  avoid open-ended parameter, quantization or architecture searches.
- One necessary clean final fast-core Vivado implementation, after focused
  simulation. It may take substantial wall time; do not hide that cost or
  promise that fast multiplication is a firmware-only change. No duplicate
  clean hardware build, speculative timing-seed sweep or rebuild per software
  candidate. A failed build may be corrected and rerun with a documented cause.
- Final physical campaign <=20 minutes under a safe watchdog. No new 1024
  marathon, 3x20 generation matrix or tail-latency claim. No routine approval
  prompts; updates only at important gates or material issues.

## F5–F7 — acceptance and performance

At 91 MHz require setup WNS >= **+0.250 ns**, TNS=0, strictly positive hold,
THS=0, zero DSPs, complete routing/constraints, zero DRC/methodology errors or
critical warnings, and explicit review of remaining warnings. +0.500 ns is
preferred, not mandatory. Report LUT/register/BRAM changes and placement cost.

Separate three configurations: previous qualified system, **fast-only with
identical firmware**, and fast plus retained software improvements. These
isolate the multiplier benefit from software changes. Final fixed-context
decode uses one warmup plus three measured samples; carry any diagnostic as a
separate sample. Report all times, mean/median/min/max/population deviation,
firmware-model and resident START-through-delivery rates, and limitations.
The roughly 1.05-second single-request overhead is not automatically charged
to every token in a multi-token resident request; do not mix those boundaries.

The exact final overlay/firmware must pass the original complete prompts with
at least 2/1/1 generated tokens, complete final logits and valid KV hashes,
affected selected traces, bounded overflow/non-mutation, recovery, post-close
zero pages/ownership and normal helper unload. Preserve full arena capacity.
Report provisioning/precomputation, memory and context explicitly. Demonstrate
reproducible firmware; retain the source-pinned final hardware build and logs.

Close with an independently checkable evidence report, existing closure audits
still valid, a new read-only audit and scoped local commit. No push until asked.

## Closure disposition

All F0–F7 evidence gates pass. Both harts use the verified 9/12-cycle pipelined
RV32MFast derivative, 91 MHz / +0.263-ns setup / +0.018-ns hold / DSP0.
The measured fast-only ablation, exact preparation and REQUANT8 candidates,
full 2/1/1 physical generation and safe release are complete. Native firmware
reproduction is byte-identical; source, arithmetic and tampered-evidence tests
and all prior audits pass. Persistent-cache/new-locality/fused-RTL extensions
are bounded deferments, documented against the final profile; fast multiply
itself is delivered, not deferred. The full numerical RTL simulation timeout
is explicitly incomplete, not a new waiver or a claimed pass. No M6 or push.
