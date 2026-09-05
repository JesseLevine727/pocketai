# M4 goal — real GPT-2 hybrid inference and honest system performance

Status: **IN PROGRESS / NOT PHYSICALLY QUALIFIED**, 2026-09-05. The scaled W8A8
adaptive v3 candidate passes frozen held-out quality, 3x20 generation/cache
checks and the 1024-token functional/range stress. Compact model packing and
native A9 operator kernels and the bounded offload runtime are implemented.
Physical CPU and FPGA both pass all three 20-token generation cases and full
tensor/logit/KV checks. The complete resident benchmark passes exact checks:
FPGA full-generation throughput is 0.04619 tokens/s versus 0.17624 on CPU,
including prefill; no speedup was required. Full-context board and supplemental
process-cold qualification are in progress. See
`M4_VERIFICATION.md`. M3 is closed/pushed through `68da8f8`;
M5/M6 are outside this goal.

## Outcome and invariants

Run the actual GPT-2-small/124M model on physical PYNQ-Z1 with Cortex-A9
software controlling GEMM/SFPU offload. Generate **20 new tokens for each of
at least three frozen prompts**, matching an independent CPU implementation of
the same quantized contract token for token. Separately pass a frozen model-
quality gate against the pinned floating-point model. Measure real prefill,
decode and CPU-relative performance; a speedup is not assumed or required.

- Preserve M1–M3 ABIs, dependency pins, frozen operator numerics/error budgets,
  historical measurements and accepted artifacts. No silent threshold changes.
- W8A8 GEMM arithmetic with int16 activation storage; wide int32 reductions.
  This is not weight-only W8A16 and not a floating-point fabric.
- Start with the exact accepted M3 qual3 overlay at **95 MHz**, DSP=0.
  Do not presume a new RTL design is needed. M3's synthetic chains are not
  full-model performance estimates.
- Use SSH, not JTAG. Do not store credentials or silently tune board-global
  settings. Leave `NA/` and unrelated user work untouched.
- A9 owns model scheduling, scale metadata and the DDR KV cache in M4.
  Autonomous RISC-V inference is M5; ASIC/PPA is M6. Neither starts here.
- Scoped local milestone commits; additional remote pushes require a request.
  Report major gates and meaningful blockers. No unrequested sub-agent work.

## Gates

| Gate | Required outcome | Status |
|---|---|---|
| G0 | Coherent acceptance plan and scope recorded | Recorded |
| G1 | Pinned checkpoint/tokenizer and independent full-model references | Host references PASS — float oracle and exact integer cache through 1024 positions |
| G2 | Full-model quantization and frozen quality criteria qualified | Host PASS — adaptive v3 quality/generation and full-context range checks; G4/G5 physical checks remain |
| G3 | Bounded-memory A9 hybrid runtime, prefill and cached decode | Implemented; full-context physical memory/boundary qualification remains |
| G4 | Real-checkpoint tensor/layer tests and affected regressions | PASS for tensor/operators, lifecycle, clean local/ISA and exact-overlay physical compatibility; context boundary tracked in G3/G5 |
| G5 | Exact-overlay physical model correctness and 3×20-token acceptance | Physical A9 CPU and FPGA both pass 3×20 plus all tensor/logit/KV cases; physical 1024-context check still required |
| G6 | Repeated physical performance, matching CPU baseline, measured improvements | Resident benchmark PASS: all 794 raw observations exact/audited; results and slowdowns in SPEEDUP.md. Supplemental process-start boundary frozen in 61a08b1 remains pending until the context sequence finishes |
| G7 | Evidence audit, closure documentation and scoped local milestone commit | Pending |

## G1 — model identity and independent references

Pin checkpoint, configuration, tokenizer/vocabulary/merges, source revisions,
licenses, hashes and runtime versions. Preserve M3's pinned OpenAI GPT-2
operator semantics. Build a reproducible floating-point CPU reference and a
separately executable bit-exact quantized full-model reference.

Cover all 12 layers, learned token/absolute-position embeddings, pre-LayerNorm
with learned affine and epsilon=1e-5, causal scaled attention, tanh GELU,
residuals, final LayerNorm and tied vocabulary/logit projection. Validate tensor
orientation, Q/K/V packing, bias order, tokenization, position indexing,
vocabulary-tail tiling, greedy tie-breaking and EOS handling.

Freeze at least three deterministic prompts before hardware generation tests;
require 20 new-token steps per prompt under an explicit EOS policy. Do not
choose replacement prompts after observing mismatches. Define supported batch,
prompt/context lengths and boundary tests within the model's 1024-position limit.

## G2 — model quality is not hardware self-consistency

Use symmetric per-output-channel weight scales, effective dynamic activation/
probability scales, signed int32 wide results, and the frozen M3 rounding and
saturation order. Preserve unsigned probability 32768, K=3072 down-projection,
full-length attention-value reduction and explicit rescaling/bias boundaries.

Pin separate calibration/development and held-out quality data. Measure
activation/gain/bias/scale representability, clipping, scale underflow and
accumulated layer/logit error against the floating model. Establish justified,
explicit numerical acceptance thresholds before FPGA integration, including
held-out perplexity or negative log-likelihood, logit/top-token agreement and
deterministic generation comparisons. Record the thresholds and freeze them;
they were not yet selected at initialization. They are now frozen in
`tests/m4/quality_policy.json`; see `M4_VERIFICATION.md` for the exact data split,
limits and finite-sample interpretation. The selected v3 passes these host
quality limits; physical qualification remains separate.

Exact FPGA-versus-quantized-CPU agreement alone does not prove useful GPT-2
quality. Do not silently relax thresholds, calibrate on held-out tests, hide
clipping, or label degraded text accurate. Quantized output need not universally
match floating-point greedy output; those are separate comparisons. A necessary
numeric/ABI revision requires a versioned rationale and affected M3/M4
requalification. Material scope/quality tradeoffs require user direction.

## G3 — full hybrid runtime with bounded memory

Implement `zynq/m4_offload.py` and suitable packing/reference/support modules.
Keep embeddings, scheduling, scale metadata and required glue on A9. Offload
the planned linear/GEMM and LayerNorm/softmax/GELU/scale operations; explicitly
account for any host fallback. Execute all heads and the full vocabulary output,
not just M3's single-head/16-column fixture.

Support prompt prefill and incremental cached decode. Check cached decode
against full recomputation, masks/positions, prompt reset/reuse and context
boundaries. Inventory actual RAM/CMA availability and peak allocations before
choosing weight packing/residency. Use bounded tile/cache buffers, reuse tied
weights and allocations, and avoid unbounded expanded weight-packet storage.

Maintain explicit tensor scales, DMA completion/cache maintenance, buffer
lifetime, route interlocks, timeouts/errors and recovery. Optimize measured
overhead without changing numerical or result-delivery semantics. No autonomous
core-driven inference or implicit direct fabric forwarding is required.

## G4 — progressive correctness and hardware provenance

Test real-checkpoint packing, individual operations, complete MLP and multi-head
attention, a full transformer layer, then all 12 layers and final logits.
Compare delivered tensors to independent exact quantized references at defined
boundaries, with floating-model quality checked separately. Diagnose the first
divergence; never repair tests by copying faulty hardware outputs into goldens.

Require host, cache/mask/tail/scale adversarial and descriptor/counter/error
tests, plus all affected M1/M2/M3 local and ISA regressions. Preserve only the
four already documented ISA expected failures.

If RTL, clocks or physical implementation change, require two independent
clean full-overlay builds at 95 MHz: WNS >= +0.250 ns, TNS=0, positive hold,
DSP=0, fully routed, no unconstrained endpoints, no final DRC/methodology errors
or critical warnings, and every remaining warning reviewed. +0.500 ns and
100 MHz remain stretch only. If hardware is unchanged, verify exact accepted
M3 bit/HWH hashes; do not fabricate a new implementation result.

## G5 — physical acceptance

Verify the final checkpoint/tokenizer/model-pack and overlay hashes before
SSH programming/testing. Run M1/M2/M3 regressions on that exact overlay.
Require all three frozen prompts to generate 20 new tokens matching the
independent quantized CPU implementation greedily, token for token.

Include tensor/layer/logit checks that detect coincidental token agreement,
complete multi-head/full-vocabulary execution, prefill/cached-decode equivalence,
prompt reset/reuse, supported context boundaries and clean error recovery.
The separate frozen floating-model quality gate must also pass. Record normal
quantization-induced differences honestly; no full-precision identity or M5
claim is inferred from matching the integer reference.

## G6 — real performance and CPU comparison

Produce `docs/SPEEDUP.md` with physical time to first token, prefill latency/
throughput, per-token decode latency/tokens per second, median/p95/variability,
context lengths, peak memory and transfer bytes. Separate model download/load/
packing and cold start from warm resident inference.

Predetermine sampling before timing: target at least three warmups and 20
measured trials per headline workload, or document a justified practical
sampling decision in advance. Exclude reference validation from timing but
include required packing, dispatch, dynamic scaling, DMA/cache operations,
KV work, logits/greedy selection and result delivery within a common boundary.

Compare with a practical same-board A9 CPU implementation of the same
quantized arithmetic/workload. Disclose compiler, libraries, threads, residency
and boundary choices; distinguish any original-floating-model baseline.
Report per-operation and integrated baseline/offload ratios, including
slowdowns. Profile without summing overlapping counters, improve justified
bottlenecks and retain controlled before/after data. No invented speedup or
token-rate target; 5.793 kernel GMAC/s is not a full-model prediction.

## G7 — closure

Record commands, hashes, model/data/tool pins, frozen thresholds and measured
quality, test counts, board logs, overlay/timing/resource provenance, performance
boundaries and limitations in `docs/M4_VERIFICATION.md`, `docs/SPEEDUP.md` and
supporting model/numerical records. Audit every original gate. Mark README/PLAN
and the goal complete only after all mandatory work passes, with a scoped local
M4 closure commit. Preserve M1–M3 evidence; leave M5/M6 unstarted.
