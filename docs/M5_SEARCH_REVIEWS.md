# Three first-principles reviews

## Cycle 1 — visibility is not automatically speed

**Reject LTO for the release.** Strict-math LTO passes the complete native
model suite and the physical all-logit/KV decode. Runtime text decreases
34,624 → 31,548 bytes, but its unprofiled diagnostic takes **12.228432 s**
against the qualified scalar mean **12.211767 s**. The ~0.14% difference is
small and not a distribution claim; there is no demonstrated speed benefit.
No compiler-flag sweep is justified. Continue with original `-O2` strict math.

The head remains dominated by scalar work around its ~0.38-s backend service.
Compiler visibility alone did not remove the algorithm's extra array passes.
Next: keep the global exponent decision, but directly construct affine integer
planes from the original channel scales and biases, avoiding intermediate
scaled-double stores/reloads. Preserve fallback, errors and backend chunking.
No model-lifetime cache, numerical approximation or new accelerator is needed.

## Cycle 2 — avoid materialization after the global decision

**Retain fused projection preparation.** The complete native model passes;
2,916 plane/fallback/error/workspace comparisons match the qualified affine
implementation, including 3,073/50,257-element chunking and special values.
The physical diagnostic matches every logit and valid KV word. Unprofiled
decode decreases to **11.771209 s**, 3.61% below the prior release mean. The
profiled head falls from 3.505035 to **3.279272 s**; QKV/up also improve.

Global range/exponent reduction still precedes quantization. Normal finite
scales produce the exact final integer planes directly; exceptional scales
and invalid fast-path integer parameters take the original affine fallback.
Keep legacy scratch reservations to preserve allocation/error behavior;
workspace remains 2,026,052 bytes on this decode. The gain is fewer scalar
array passes and double stores/reloads, not a smaller model or hidden cache.

The head is still the largest phase; 10.421567 of 11.799583 profiled seconds
remain outside backend service. Range evaluation currently pays for a generic
int32-to-double conversion and generic double multiplication at every output.
Next: exploit the exact integer operand, retaining the full significand product
and one binary64 ties-to-even rounding. Apply the same primitive to smoothing's
int16 overflow-range scan. Nonzero bias addition, residual order and global
reductions remain unchanged; special/subnormal scales retain original math.

Build note: fusion_v1 was compiled with LTO but never board measured. Following
cycle 1's rejection, measured fusion_v2 uses the original non-LTO flags.

## Cycle 3 — specialize the operand, not the numerical precision

**Retain exact integer/binary64 multiplication.** The int32 conversion is
exact, so the normal-scale path directly multiplies the 53-bit significand by
the unsigned integer magnitude. It retains every product bit and rounds once
to binary64 nearest/even. Signed zero, carry, overflow and INT32_MIN are
handled explicitly; subnormal, zero, infinity and NaN scales use the original
arithmetic. No float/double precision reduction, early truncation or bias
reordering is involved. The RV32 compiler emits two MUL and two MULHU
instructions for the two full-width products, using the existing fast harts.

1,033,040 bitwise product cases cover all binary64 exponent classes and signed
integer endpoints. The complete native model and physical all-logit/KV decode
pass. Unprofiled diagnostic: **11.045137 s**, 6.17% below fused preparation
alone and 9.55% below the prior release mean. Profiled head: **2.747785 s**
(previous release 3.505035 s); smoothing/projection residual phases also gain.
Keep the combination of cycles 2 and 3, with original non-LTO compiler flags.
Three configurations were board measured; no fourth search is needed.

### Renewed first-principles assessment

The diagnostic's **9.695285 / 11.073193 s (87.56%)** remains outside backend
service. This includes scalar instructions, memory stalls and control, not
just arithmetic. Head outside-service cost is 2.369885 s; down is 1.897677 s,
up 1.366329 s, attention 1.262125 s and QKV 1.026485 s. These are non-overlapping
phase remainders; 0.087228 s GEMM and 0.291977 s SFPU engine time are nested
inside 1.377908 s backend service, not additional latency.

The remaining design opportunity is still the scalar-to-accelerator interface:
reuse exact preparation metadata where its actual dependencies permit it,
reduce repeated reads/conversions and integer-plane construction, and inspect
attention's remaining fixed-context scalar loops. The global output exponent
prevents blindly quantizing independently per tile. A new prepared-metadata
format or scalar helper instruction would be a separate, larger design pass;
its setup, storage, invalidation and hardware timing would all need charging
and qualification. These are hypotheses for a next pass, not measured gains.

Even hypothetical elimination of **all** measured backend service leaves
9.695285 s of this profile (only about 1.14× speedup if the remainder stayed
fixed). Therefore more MAC throughput or weight bandwidth alone is not the
first target. W4A4 would also change numerical behavior and the datapath; it
does not directly remove the surviving preparation dependency chain. This is
an Amdahl estimate for the current profile, not a hard architectural limit.

The three-cycle search is finished. Final repeated samples and the original
short complete-request campaign qualify this retained combination separately;
no fourth cycle, new hardware, precision change or M6 is started.
