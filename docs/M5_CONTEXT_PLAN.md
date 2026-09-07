# Goal: 0.1 delivered token/s at maximum cached context

**Closed / PASS:** six final unprofiled observations are <=9.469 s delivered.
See [results and scope limits](M5_CONTEXT_RESULTS.md) and
[read-only reproduction](M5_CONTEXT_REPRODUCE.md).

M6, ASIC/PPA work and its report are on hold by user instruction. The frozen
characterization is closed at `72c625a`; no M6 implementation was started.

Required endpoint: past 1023, one forward, all 1024 valid K/V positions. Each
of at least three final unprofiled START-through-safe-return/token-copy samples
must be <=10 seconds. Prefer margin and check additional representative cache
contents. This is cached last-slot decode, not 1023-token physical prefill,
streamed TTFT, or generation beyond the model's context capacity.

Keep full autonomous on-FPGA W8A8/int16 GPT-2, twelve layers/heads, full 50,257
logits, two fast-multiply Ibex harts and A9 provisioning/control/checking only.
No approximation, truncated attention, CPU inference, slow multiply, discarded
outliers or hidden preparation. Start on the qualified 91-MHz DSP0 overlay.

The measured baseline is 59.841 seconds delivered / 58.787 seconds model.
The diagnostic attention phase is 51.150 seconds, including 50.504 seconds of
CPU/control/scalar-memory remainder. The first experiment separates key packing,
score preparation, softmax/probability work, V-maximum scanning, V quantization/
packing and value reduction. Timers bracket blocks, never individual elements.

Bounded implementation sequence:

1. Pin/derive baseline sources, build detailed attention instrumentation and
   verify it natively and on the physical endpoint with full logits/KV.
2. Use the measured dominant costs to select exact packed-access and/or
   consumer-layout optimizations. Avoid speculative broad rewrites.
3. Investigate persistent derived V quantization state only with exact evolving
   per-channel maxima and requantization on changes. Real prefix initialization
   and maintenance must execute on FPGA and be accounted for; no stale maxima,
   host-inference substitution, or silently excluding first-use work. Any changed
   cache state/measurement assumptions must be explicit and tested.
4. Re-profile and address the next measured bottleneck. RTL is a fallback only
   if needed, with full simulation, timing/resource and board requalification;
   no silent timing-margin relaxation.
5. Qualify final exact short/long contexts, original 2/1/1 requests/traces,
   overflow non-mutation/recovery, arithmetic/layout edge cases, reproducible
   binaries, repeated maximum-context delivery and safe normal release.

Every physical campaign has a <=60-minute aggregate cap, including preparation,
checks and cleanup, a two-minute cleanup reserve and conservative admission.
Use short hypothesis-driven cases, not a full-context prefill marathon or
exhaustive multi-hour experiment. Preserve failed and slower trials. Never force
unload or free undrained pages. Finish with new machine evidence and an audit
that preserves the entire previous qualification chain. Use new paths, preserve
unrelated `NA/`, and do not start M6 or write its report until this target passes.

Necessary engineering notes/results for this performance goal are in scope.
No agents or tracker scaffolding. Commits are scoped; the requested combined
push remains associated with the later M6/report workflow unless requested sooner.

## Gates reached during implementation

The instrumented baseline passed physical full-logit/full-KV checks and normal
zero-resource cleanup. Its attention blocks were: QK packing/GEMM 14.582 s,
V maximum scan 9.560 s, V quantization/packing/GEMM 20.190 s, score preparation
and affine 5.906 s. This is diagnostic instrumentation, not an updated speed claim.

The first consumer-ready candidate uses the existing K8 allocation in block16
layout and maintains exact per-feature V maxima, multipliers and quantized V.
When any maximum changes, every affected four-feature group is requantized for
the entire valid prefix. It reserves 1.5 MiB at work+0x280000 and 7.5 MiB at
trace+0x80000; metadata occupies trace+0x60000..0x7fed7. No arena/driver/RTL
change is needed. Optional full-tensor traced requests retain the legacy path
and its original workspace/trace capacity. Untraced/profiled requests retain
2,609,152 bytes of workspace, above the measured 2,371,652-byte requirement.

Native checks exercise the bound optimized path: eleven incremental attention
calls cover zero/extreme values, changed maxima, partial tiles, full1024 and both
V allocation segments; sixty full-model generation outputs match all logits and
complete valid K/V. Existing legacy-path numerical/layout tests also pass.

Physical candidates use an independently prepared past1022 prefix. A cold
forward runs all derived-cache initialization on FPGA inside model timing. Its
actual output becomes the input to a second forward at past1023, retaining only
the previous FPGA-produced KV and derived state. No future cache state is reused
to accelerate repeated identical queries. Both timings and aggregate campaign
cost are reported; this does not claim inexpensive long-prompt prefill.

Successive exact physical diagnostics reached 17.539 s (consumer layout),
13.970 s (fused score metadata), 12.991 s (persistent smoothing multipliers),
12.748 s (exact two-rounding score product), 12.503 s (local scaled scores),
and 10.841 s (parallel projection preparation). These are not final unprofiled
samples; the original sweep uses a different synthetic prefix at the same
context length, so a matched-reference baseline is still required.

Smoothing multipliers use trace+0x30000..0x5cfff, with their pointer-keyed
immutable-model metadata at trace+0x5d000. Cold invalidation and preparation
remain inside FPGA model execution. Overflow cases retain exact reciprocal
and exponent preparation. Local score scratch uses previously reserved BRAM
0xc000..0xcfff; the exact-key score lookup uses 0xd080..0xd87f. The unchanged
128-byte result ABI stays at 0xd000, and both 4-KiB stacks remain untouched.
The new linker asserts each boundary; no RTL, clock or arena changes were made.

Both harts now share independent projection preparation via a software mailbox
job. Hart 0 and hart 1 write disjoint ranges and join before any dependent
accelerator job. Max reductions use separate exact per-hart results; leaf work
does not allocate workspace, issue backend work or mutate the lazy quantizer.
Native threaded full-logit/KV tests and physical diagnostics pass.

Two-hart score/value preparation and direct consumer GEMM destinations reduced
the story diagnostic to 9.700 s. Three unprofiled story repetitions also passed,
but a different science prefix took 10.728 s. The gate was not closed on the
easier prefix: science caused 396 new V-feature maxima versus story's 171.
Partitioning changed-value work by position balanced the two harts and reached
10.412 s; fusing exact score metadata, integer scaling and local maximum
reduction reached 10.098 s. Finally, maintaining a 64-bit changed-feature mask
avoided requantizing unchanged features within an affected four-byte group.
The science diagnostic reached 9.522 s, with all logits and valid K/V exact.
Each worker writes disjoint complete words; unchanged bytes are retained only
for old positions, while the newly appended position always initializes all
features. Native threaded and independent NumPy cache checks pass.

The retained `masked` variant uses `memory_packed.ld`: literals occupy the
previously reserved 0xd880..0xdb53 gap, below the unchanged hart-1 stack at
0xe000. The first masked detail build correctly failed its link-time overlap
assertion; this relocation fits all three firmware images without changing RAM,
RTL, the result ABI or either stack. Runtime, unprofiled-capable profile and
detail binaries reproduce byte-for-byte in a fresh build.

Final qualification uses three independent cold/warm pairs for each of story
and science, all primary samples unprofiled, plus original full 2/1/1 requests,
story traces and the optimized story request. A matched original-firmware pair
uses exactly the same story oracle and actual preceding FPGA state: its last
slot takes 60.730 s delivered and 58.884 s model time. Historical sweep and
diagnostic observations remain separate; no profiling data is pooled into the
primary performance gate. Final outcomes belong in `M5_CONTEXT_RESULTS.md`.

An earlier qualification campaign failed after three passing story samples
because the checker requested an unstaged science trace fixture. The failed
campaign and its exact partial inference result are preserved, including safe
cleanup. The corrected matrix checks the original story trace and all logits/
KV for science and computing; it does not suppress an inference mismatch.
