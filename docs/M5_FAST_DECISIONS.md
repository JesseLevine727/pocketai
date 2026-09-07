# Bounded follow-up decisions

These decisions limit optional work; they do not weaken the required fast-core,
exactness, 91-MHz margin, physical qualification or evidence gates.

## Retained candidate set

1. Exact projection preparation: reuse the same rounded channel scale across
   the range and finalization passes, perform eligible normal binary64
   power-of-two scaling by exponent adjustment, and avoid the mathematically
   redundant exponent-zero LayerNorm correction. The short slow-overlay
   physical diagnostic improves about 24.52 → 18.08 seconds with exact final
   logits/KV. No representation, workspace-capacity or model-pack changes.
2. Optional existing REQUANT8 conversion, including expansion, max scan,
   multiplier/unit calculation, DMA, result packing and workspace rewind.
   This improves the complete conversion on both overlays. The fast-overlay
   three-sample model comparison improves 17.763754 → 17.400193 seconds with
   complete exact results, so retain it. The original CPU path remains
   available for an honest ablation.

No further software candidates will be added to this pass unless a correctness
failure requires correction. Both production-style variants pass the original
complete native model/trace/generation tests and numerical edge checks.

## Persistent immutable metadata — defer the extra cache

The measured improvement comes from exact reuse within a projection and
cheaper arithmetic, without a cache identity or invalidation contract. A
model-lifetime smoothing cache was considered but is not necessary to deliver
this improvement or the fast-core goal:

- The relevant complete smoothing calls account for about 1.89 seconds in
  the slow diagnostic; that is an upper bound, not the time a reciprocal
  cache would remove. Overflow probing, expansion, transfers and output
  conversion would remain.
- The fixed-context qualification boots the firmware for each request. A
  cache built inside that request cannot avoid its first-use preparation.
  Moving that work outside START without changing/reporting the lifecycle
  would give a misleading benchmark.
- Multi-token requests could amortize preparation. Caching the reciprocals
  and multipliers for the 24 actual attention-projection/MLP-down smoothing
  arrays would require 12×(768+3072)×(8+4) = **552,960 bytes**, plus descriptors,
  alignment and any norm/bias cache. It needs a reserved owned-memory region,
  lifetime/version validation and explicit invalidation across restarts or
  model replacement; the old workspace rewind cannot own persistent data.

Do not claim that such caching is ineffective. It is deferred on integration
cost and the limited per-request reuse of this bounded pass. Next small
experiment: measure one array's prepare-versus-reuse cost with explicit owned
storage over two decode calls, charging setup to the first call. Do not launch
that extra experiment now; qualify the two retained candidates first.

## Read-only locality and broader fusion — bounded deferment

No extra cache, scratchpad or fused RTL is in the current hardware candidate.
The required fast multiplier already needed a functional timing correction;
adding a new DMA-visible local-memory path now would expand the timing and
coherence qualification substantially. The accepted board has only 44.5 spare
BRAM36 equivalents (about 178 KiB ordinary data), while one 50,257-element
binary64 head-scale array is 402,056 bytes. A whole-array cache does not fit;
a line/burst buffer must earn its benefit under the actual access order.
The new software already removes one repeated scale calculation/pass.

Broader fusion is not dismissed by the backend-only 5.7% Amdahl ceiling: it can
remove CPU work. Candidates include max reduction, requantization/packing and
projection finalization. They still must preserve global scale/exponent
dependencies, wide intermediates, exact rounding and complete logits. The
existing REQUANT8 investigation is the bounded operation-offload experiment
for this pass; a new wider engine is not required to obtain the demonstrated
software gain.

The final production-style profiled fast run takes 17.428641 seconds, of which
16.051092 seconds (92.10%) are CPU plus scalar-memory/loop remainder and
1.377548 seconds are backend service. Head projection remains the largest
single phase at 4.129353 seconds (3.751637 outside service); the twelve
attention phases total 2.809790 seconds, 2.773781 outside service. Increasing
only current backend throughput has an idealized 1.086× ceiling now; an
operation that removes CPU work is not subject to that ceiling.

The final fine binary confirms 4.124006 seconds inside head project, including
0.745577 seconds affine finalization and its nested 0.398687 seconds metadata.
LayerNorm metadata is 2.118446 seconds; smoothing including backend is
1.814856 seconds. These intervals overlap their parents and are not added.
Read-loop probes remain about 24.02 cycles/word in SRAM versus 61.30 in DDR.
Those demonstrate a locality penalty but do not separate the model's actual
memory stalls from software floating-point arithmetic.

Next bounded experiment, outside this goal: one representative head-output
tile, with identical exact scalar arithmetic, compare existing DDR metadata
against an explicitly owned SRAM staging tile and charge the staging copy.
If locality is insufficient, prototype exact max/range and affine preparation
fusion for that same tile, retaining the global exponent/tie dependencies.
Do not build a full cache or new engine before that small falsifiable test.
The context-growing V-cache scan remains a separate long-context risk; no new
endurance campaign is needed to note it. W4/W4A4 and M6 stay out of scope.
