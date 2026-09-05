# M3 goal — GPT-2-correct SFPU and honest measured performance

Status: **ACTIVE / NOT QUALIFIED**, started 2026-09-04. M1 and M2 remain closed.
This is the implementation and acceptance plan, not a claim that its gates have
passed. The active goal must stay open until all required evidence is recorded.

## Scope and invariants

Implement the operator and numerical interfaces needed by GPT-2-small/124M:
masked softmax, LayerNorm, the original tanh-approximate GELU, and scale,
conversion and vector support. Learned absolute position embeddings are part
of the GPT-2 reference semantics; they require lookup/addition, not a RoPE unit.
RMSNorm, SiLU, RoPE, autonomous KV management, full-model hardware offload (M4),
and autonomous inference (M5) are outside this goal.

Preserve the M1 two-hart ABI, bus fairness, dependency pins, and M2 flag-zero
descriptor/stream behavior. Preserve all historical M1/M2 evidence and accepted
artifacts. Fabric RTL remains portable integer logic with no DSPs or vendor
primitives. New work uses separate build directories and a scoped local commit;
no remote push or edits to unrelated user-owned `NA/` files.

Report completed major gates and meaningful blockers. Never call an unchecked
gate complete, silently relax a numerical bound, or substitute simulated results
for physical-board acceptance.

## Ordered gates

| Gate | Required outcome | Current status |
|---|---|---|
| G0 | Coherent scope, ordering, and acceptance criteria recorded | Recorded |
| G1 | Fair physical M2 baseline, CPU comparison, measured host/dataflow improvement | PASS — [evidence](M3_PERFORMANCE.md) |
| G2 | Pinned GPT-2 semantics, validated/frozen numerics and interface contract | PASS — v1 frozen; [evidence](M3_VERIFICATION.md) |
| G3 | GEMM extensions and portable SFPU pass local numerical/protocol/integration tests | In progress — wide GEMM and shared ALU pass standalone; operator controller/integration remain |
| G4 | Two clean full-overlay implementations pass timing/resource/DRC checks | Pending |
| G5 | Exact accepted overlay passes physical M1/M2/M3 tests and performance measurement | Pending |
| G6 | Evidence audit, coherent closure documentation, scoped local commit | Pending |

G1 and reference exploration for G2 may proceed independently. G2 must pass
before modifying arithmetic RTL. A future implementation change invalidates any
affected downstream qualification: final G4/G5 evidence must refer to the same
source configuration. No unrequested multi-agent delegation is implied by this
plan.

## G1 — fair baseline and practical dataflow

Use `build/m2_qual2/m2_pynq.bit`, SHA-256
`f196e92c4509ebad977521bf40a8cd30b0f3f131fbfe199515d6e0ff6600fa03`, and its HWH
`f77dfe909dd8a3d7d0266d4326c05ceb1eb97a0182bbd4d67acf25a96833c390`.
Program and run on the physical PYNQ-Z1 over SSH, with M1 regression on the same
overlay. Do not benchmark the old exploratory `build/m2_pynq` artifact by mistake.

The historical M2 result is immutable: 9,437,184 MACs, 154,752 compute/pack
cycles at 95 MHz, 5.793 GMAC/s while computing, and 110.649 ms / 0.085 GMAC/s
for the acceptance harness including DMA, validation and publication. This is
not a full-model result or a tuned application runtime.

New measurements must:

- Exercise at least M=1 (decode-like) and M=16 (prefill-like), K=N=768.
- Generate deterministic inputs and reference outputs before timing; compare
  every result after the timed region. Required transfers, cache maintenance,
  runtime dispatch, copies and delivery to the stated destination remain timed.
- Specify whether operands are logical row-major arrays or prepacked packets,
  ordinary DDR or DMA-ready buffers. Account for any packing/staging excluded
  from a resident-data measurement in a separate cold/staging measurement.
- Warm up, repeat at least 20 trials, retain raw samples, and report median,
  p95, min/max and variation. State CPU, software, clock and artifact versions.
- Report useful MACs, cycles, bytes, compute-only and delivered throughput.
  Attribute sequential host phases without double counting concurrent hardware
  work. Hardware cycles are a nested/overlapping measurement, not an additive
  wall-time phase. Profiling overhead must be disclosed.
- Include a practical native CPU implementation of the same signed-int8 dot
  product and one final int16 saturation. Match logical operands and result
  delivery for an end-to-end comparison; disclose implementation/compiler,
  thread count, cache state and exclusions. Do not claim a best-possible CPU.
- Preserve an initial driver policy and compare any justified polling,
  descriptor or buffer-residency improvements on the identical workload.
  Report only measured gains and any tradeoffs (CPU spin, extra memory, reuse).

The current full M=16 input format sends 1,179,648 bytes for 9,437,184 MACs
(8 MAC/input byte). A 32-bit stream at 95 MHz has an *ideal calculated* input
ceiling of 380 MB/s, therefore 3.04 GMAC/s for this format even with perfect
overlap. This is not measured DDR bandwidth. Repeated A traffic, dispatch and
lane utilization matter; removing Python validation cannot by itself establish
5.793 GMAC/s delivered throughput or a decode token rate.

Record methodology, phase timings, CPU comparison and limitations in
`docs/M3_PERFORMANCE.md`, with board logs and machine-readable raw results in
the build output. Necessary host/dataflow improvements precede claims of gain.

## G2 — freeze semantics, numerics, and interfaces

Pin the reference to OpenAI GPT-2 commit
[`9b63575ef42771a015060c964af2c3da4cf7c8ab`](https://github.com/openai/gpt-2/blob/9b63575ef42771a015060c964af2c3da4cf7c8ab/src/model.py).
Document the 12 layers, width 768, 12 heads of width 64, context up to 1024,
learned token/position embeddings, pre-LayerNorm residual structure, scaled
causal attention and 768→3072→768 MLP. Pin checkpoint/configuration and input
normalization used for any empirical range exploration; no full-model hardware
runtime is required in this gate.

Before arithmetic RTL, extend `docs/NUMERICS.md` and add
`docs/M3_ARCHITECTURE.md` with:

- Exact supported tensor shapes, domains, scales, signedness and widths.
- LayerNorm mean/variance definition, epsilon=1e-5, reciprocal square root,
  learned gain/bias, and zero/near-zero variance behavior.
- GELU `0.5*x*(1+tanh(sqrt(2/pi)*(x+0.044715*x^3)))`, not SiLU or a silently
  substituted erf-based GELU.
- Stable softmax, attention scale/mask ordering, supported masks/lengths,
  max subtraction, underflow, rounding and explicitly defined all-masked output.
- Wide product/reduction bounds, bias and scale ordering, rounding ties,
  saturation and exceptional inputs for each path. No post-clipping repair.
- An honest int16-storage→int8-GEMM policy and quantization label. GPT-2 weight
  layouts/transposes and scale metadata are explicit, not inferred by the RTL.
- A legacy-compatible/versioned GEMM path supporting the down-projection's
  K=3072. Direct widened reduction or wide partial sums are acceptable; adding
  already saturated int16 chunks is not. Signed-int8 K=3072 sums need at least
  27 signed bits (maximum positive sum 50,331,648).
- Register/descriptor/stream formats; tensor residency and byte counts;
  buffer ownership, ordering, backpressure, bounds, IRQ/completion/error codes,
  reset and abort semantics. Shared staging needs a single owner or lock.
- **Numeric accuracy thresholds with numbers**, both exact agreement with the
  fixed-point reference and absolute/relative/probability-mass error against a
  high-precision reference. Relative error alone near zero is invalid. Select
  and test budgets in reference exploration, then freeze them before RTL;
  the obsolete RMSNorm threshold is not a LayerNorm contract.

Do not mark G2 passed with unspecified scales or error budgets. A necessary
contract change later requires an explicit versioned rationale, rerun tests and
requalification; never silently widen a limit to make failing RTL pass.

## G3 — portable implementation and local proof

Provide integer references, high-precision references, reproducible LUT/table
generation and versioned vectors. Implement scaling/conversion and GEMM width/
reduction extensions with backward compatibility, then the SFPU operators and
cluster/overlay integration. Favor resource-conscious sequential/shared
arithmetic when it meets the measured need. Avoid unnecessary A9/DDR round
trips where feasible, and measure rather than assume the benefit.

Required tests include:

- Exhaustive scalar domains where feasible; substantial deterministic random
  and adversarial vectors, with seeds and worst-case errors recorded.
- Exact fixed-point/RTL agreement; all frozen high-precision accuracy budgets.
- Extremes, equal inputs, near-zero mean/variance/denominators, masked and
  all-masked cases, rounding ties, clipping, partial/max lengths and padding.
- K=3072 extremes, cancellation across K chunks, and the overflow/saturation
  cases that invalidate the old int16 partial-sum approach.
- Invalid descriptors/stream framing, arbitrary stalls, IRQ behavior, ordered
  completion, reset/abort at all execution stages and safe recovery.
- Representative GEMM→scale→GELU→GEMM, LayerNorm/affine and attention
  scale/mask/softmax chains, including shapes relevant to GPT-2.
- M1/M2 standalone and cluster regressions, fatal-warning lint, and the pinned
  ISA suites (preserving only the four documented upstream expected failures).

No vendor/DSP primitives, hidden floating-point fabric math, premature
accumulator clipping, unspecified overflow or protocol dependence on no stalls.

## G4 — independent implementation closure

Two separately clean full-design builds at **95 MHz** must each have:

- Setup WNS >= +0.250 ns and TNS=0; positive hold slack.
- All paths routed; clean clock/endpoint checks with no unconstrained endpoints.
- DSP count zero; DRC errors and critical warnings zero.
- Every remaining tool/DRC/methodology warning reviewed with a specific reason,
  not a blanket waiver. Preserve proper clocks/jitter; no timing exceptions
  added simply to hide failing paths.

+0.500 ns and 100 MHz are stretch only, not reasons to weaken the required
gates or substantially distort the M3 design. Archive source snapshots,
commands, reports, build pins and hashes for both clean implementations.

## G5/G6 — physical acceptance and closure

Use SSH, not JTAG. Check the exact accepted bit/HWH hashes before programming;
record board/runtime versions and clock configuration. Run M1 and M2 regression,
every M3 operation and representative integrated chains on the physical board.
Compare actual delivered outputs with the frozen reference. Benchmark operator
and integrated wall latency with the G1 discipline and disclose residency and
CPU participation. No full-model accuracy/speedup or token-rate claims.

Populate `docs/M3_VERIFICATION.md` with commands, dependency/source/artifact
hashes, numerical/protocol counts and errors, timing/resource/DRC/warning
evidence, board logs, performance results and known limitations. Audit all gates
against actual evidence, update README/PLAN to COMPLETE only after all pass,
and make a scoped local milestone commit. Leave M4 and M5 unstarted.
