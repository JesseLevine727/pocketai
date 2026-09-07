# Three bounded first-principles reviews

## Cycle 1 — remove repeated work before adding hardware

**Retain.** The full native exact suite passes (all 50,257 logits, 396 traced
tensors / 4,670,788 values, 60 generated tokens, original error checks).
The independent seeded board decode also matches every logit and valid KV word.
Profiled / disabled model intervals: **16.764289 / 16.738668 s**; corresponding
resident delivered intervals: **17.825668 / 17.792590 s**. These are two diagnostic
samples, not a sustained-throughput or statistical claim. Baseline production
three-sample means were 17.400193 model / 18.458464 delivered seconds.

We now reuse already prepared attention score multipliers and construct their
common integer bias directly. LayerNorm's factor search scans absolute gain
once, then evaluates only its maximum with the original multiply/divide order.
Monotone correctly rounded positive scaling preserves the maximizing magnitude;
nonfinite gains retain the original function. No persistent cache or uncharged
preparation was introduced. Jobs (9,701), mover bytes, engine compute cycles and
workspace high-water (1,632,708 bytes) are unchanged.

First principles: 15.386746 of 16.764289 seconds (91.80%) remain outside backend
service, versus 1.377543 seconds inside it. This remainder includes instruction
and scalar-memory stalls, not just arithmetic. Head 4.122319 s, smoothed MLP-down
3.083792 s and attention 2.741798 s dominate. More GEMM lanes cannot remove these
costs; its nested compute time is only 0.087228 s.

**Next bounded experiment:** stop the otherwise idle service hart's repeated
instruction/MMIO polling while hart 0 does scalar work. Both harts share a local
instruction/data bus and RAM. Check the actual interrupt wiring and Ibex WFI
implementation; prove the level-pending / acknowledge / wakeup race semantics
on both real simulated cores before board deployment. Keep global interrupts
disabled (the runtime trap handler is fatal), enable only the local external
wakeup mask, and always recheck the mailbox predicate. No scheduler, overlap,
new IRQ handler or RTL modification is required. Defer two-hart tensor work,
new cache/engine and lower precision until this small contention experiment
establishes whether the idle hart is imposing a material cost.

## Cycle 2 — test contention, then reject an unconvincing optimization

**Reject both sleeping-hart variants for the release.** The first candidate
slept both waiting harts. Both-core directed simulation passed pending-before-
WFI, arrival-after-WFI, sticky pending, repeated acknowledgement, unrelated SFPU
wakeup and repeated exchanges, followed by original memory/trap/abort/remap
tests. The board reached successful firmware completion with no hart trap, but
the strict profile parser rejected nested engine/service intervals. No token
or speed result is claimed for that failed diagnostic.

Diagnosis: the real Ibex core clock is gated by WFI, including its `mcycle`
counter. Hart 0's model/service timing therefore excluded sleep while engine
counters continued. A focused two-core regression independently delays a reply
by >=20,000 active peer clocks: hart-0 WFI fails the elapsed-time assertion,
while polling passes both complete boots and reset/remap. This is not repaired
by dropping the profiler's nested-counter checks. The second candidate keeps
hart 0 awake and only sleeps idle hart 1; the same exact board loop passes.

Corrected profiled / disabled model intervals: **16.754946 / 16.727825 s**;
delivered: **17.809029 / 17.783053 s**. Disabled improvement versus cycle 1 is
only **0.010842 s (0.065%)**. The single pair does not separate such a small
effect from binary-placement and run variability. We decline additional runs
or scheduler complexity. The WFI proof/reproducer stays as diagnostic evidence,
not deployed runtime policy. No power saving was measured or claimed.

First principles: simply silencing the peer did not materially accelerate the
main hart. Shared-bus competition from this idle loop is not an established
dominant latency bottleneck. CPU+scalar-memory remainder is still 15.380923 s,
head 4.120385 s, smoothed MLP-down 3.081710 s, attention 2.738933 s; backend service
1.374023 s. This does not prove all instruction/memory stalls are unimportant.

**Next bounded experiment:** specialize the projection range scan. The full
50,257-channel head remains the largest individual phase. Preserve each
ordered channel-scale and accumulator multiply, skip bias addition only when
the actual bias is signed zero, and compare non-NaN absolute binary64 encodings
directly for the maximum. A positive finite binary64 encoding is ordered by
magnitude; infinity and NaN behavior must still match the original. Test the
range seam against the exact original operations at zero, subnormal, overflow,
NaN, signed and exponent boundaries plus full model traces. No head pruning,
approximate arithmetic, hidden cache preparation or new hardware. Start from
retained cycle 1, not either WFI candidate.

## Cycle 3 — specialize exact range preparation; stop at the bounded gate

**Retain.** The new scan preserves the original ordered channel-scale and
accumulator products, only skips actual +/-zero bias additions, and reduces
absolute binary64 encodings with the original NaN/infinity semantics. Residual
int16 scaling by its power-of-two storage unit is exact over the complete
allowed exponent range. There is no hardcoded assumption that head biases are
zero, no approximation and no persistent state. Tests pass 38,640 bitwise range
comparisons, 1,683 norm metadata cases (524 failures with original partial-output
semantics), 576 attention plane/output/error/workspace comparisons and the full
native model suite. The board independently matches every logit and valid KV.

Profiled / disabled model intervals: **15.714621 / 15.687081 s**; delivered:
**16.777364 / 16.745986 s**. Disabled model reduction versus retained cycle 1 is
1.051586 s (6.28%). Head declines from 4.122319 to 3.662262 s; smoothed MLP-down
from 3.083792 to 2.774265 s; smoothed attention projection from 1.737615 to
1.432567 s. Other phase movements are small and are not independently attributed
to the range code. No extra jobs, mover bytes or workspace were introduced.

Final first principles: 14.339380 / 15.714621 s (91.25%) remain outside backend
service. Service is 1.375241 s; nested GEMM 0.087228 s and SFPU 0.291977 s. The
largest phases are head 3.662262 s, smoothed MLP-down 2.774265 s and attention
2.746006 s. These inclusive phase totals are not all compute, and CPU remainder
does not distinguish arithmetic from instruction/data stalls.

The next *future* bounded experiment should instrument the surviving exact
preparation inside those phases, rather than assume idle polling or MAC count
is the problem. Concrete candidates: exact integer/bitwise specialization of
remaining range/affine calculations; call-scoped reuse of exponent-zero norm
metadata across prefill rows; then explicitly owned model-lifetime norm and
smoothing preparation with honest startup cost and invalidation. V-cache
requantization still needs its evolving per-feature maximum: an append-only
int8 shortcut is not automatically exact. Parallel scalar work needs a measured
partition and descriptor ownership, not merely two active cores.

Even removing 90% of today's CPU remainder while leaving service unchanged
would take about 2.81 s per model decode. One token/s will eventually require
reducing backend/mover cost as well. Lowering activation precision or adding MAC
lanes does not remove current scalar preparation. Defer W4/W4A4, new cache/RTL,
new hardware builds and long-context campaigns. This goal now proceeds only to
the promised final bounded qualification, not a fourth optimization cycle.
