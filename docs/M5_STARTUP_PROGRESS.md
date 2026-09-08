# Pre-M6 startup optimization — closed experiment record

**The required goal is now CLOSED / PASS; M6 is not started.** See
`M5_STARTUP_RESULTS.md` and the chained startup evidence audit. The entries below
are chronological checkpoints: their then-open work and rejected hypotheses
are preserved, not current blockers. Final hardware is the newly qualified
91-MHz DSP0, two-fast-Ibex data/instruction-mirror overlay. The optional
5-second preparation stretch is unmet, and the measured short-request margin
is only 3.1 ms. Requirements remain in `M5_STARTUP_PLAN.md`.

## Initial physical experiments

Each row below is one short **diagnostic** campaign: independently seeded story
past-1022 cold forward, its actual greedy warm past-1023 continuation, then the
original eight-token science prompt and one generated output. Every listed
campaign passed exact token, all 50,257 logical logits, complete valid KV and
normal release checks. These are not three-repeat final performance claims.

| Candidate | Cold initialization (s) | Cold delivered (s) | Warm delivered (s) | Actual science prompt delivered (s) |
|---|---:|---:|---:|---:|
| New diagnostic baseline | 35.0171 | 44.8788 | 9.0412 | 31.0487 |
| Parallel cold phases / packed transpose | 16.3507 | 26.2036 | 9.0488 | 31.0439 |
| Cold absolute-value LUT — rejected slowdown | 17.455 | 27.3200 | 9.0533 | 31.0744 |
| Local integer affine + LUT | 17.3176 | 27.2033 | 9.0733 | 31.2092 |
| Maximum-bounded quantization / register scan | 13.1410 | 23.0110 | 9.0440 | 31.0520 |
| Certified fused projection | 13.1582 | 21.8541 | 7.8811 | 25.7542 |
| Register-held signed cold conversion | 11.0455 | 19.7364 | 7.8558 | 24.9454 |
| Interval-certified product | 10.9804 | 19.6833 | 7.8294 | 24.5646 |
| Packed scalar I/O / direct attention output | 11.0080 | 19.4567 | 7.5712 | 22.3416 |
| Signed-extrema cold scan | 10.4133 | 18.8648 | 7.5603 | 22.3436 |
| Three-product high-word interval — rejected slowdown | ~10.6 | 18.9842 | 7.7238 | 23.4079 |
| Reuse smoothing's exact prospective outputs | 10.6153 | 18.8795 | 7.3866 | 20.9282 |
| Parallel direct projection quantization | 10.4143 | 18.5412 | 7.2461 | 19.8531 |
| Word-based affine RNE | 10.6243 | 18.7169 | 7.2182 | 19.5397 |
| Feature-partitioned cold conversion — no clear gain | 10.5359 | 18.6188 | 7.2062 | 19.5383 |
| Certified exponent hint | ~10.4 | ~18.5 | ~7.2 | 18.4389 |
| Reuse projection weights/biases across prompt rows | ~10.412 | 18.4616 | 7.1426 | 16.8035 |
| Implicit-significand product enclosure | 10.6284† | 18.6654 | 7.0876 | 16.5999 |
| Exact demand-materialized V (batch-project ancestor) | 7.0321‡ | 14.9784 | 7.3428 | 16.8091 |
| Parallel first-use metadata / packed batched smoothing | 7.0146‡ | 14.4025 | 7.1137 | 15.3375 |
| Final-branch enclosure — rejected slowdown | 7.0163‡ | 14.4153 | 7.1335 | 15.8545 |
| Packed append / bounded attention quantization | 7.0102‡ | 14.2339 | 6.9618 | 14.6623 |
| Reusable exact-certified projection constants | 7.0287‡ | 14.2397 | 6.9498 | 14.2117 |
| Separate same-source ready/trace images | 7.0204‡ | 14.2362 | 6.9578 | 14.2106 |

† Complete prepare-call counter, rather than the earlier head-interval sum.
‡ Complete prepare calls **plus first-demand V materialization**: deferred
first-use work has not been excluded from the initialization number. For the
first lazy trial this is 6.1053 + 0.9268 = 7.0321 seconds. Later new demands remain
inside each forward, including the measured warm continuation. Intermediate
rows with `~` are rounded checkpoints, not final timing claims; raw JSON wins.

The separate leaf-retirement diagnostic measured projection-leaf CPI around
7.16 on both harts for the science prompt. That excludes outer setup and
handoff, and is not a complete attribution of stalls to DDR. Row reuse produced
a measured gain; the final-result interval variant did not and is not inherited
by the subsequent packed-cache experiment.

Raw reports remain under fresh `build/m5_startup_*_diag_v1/campaign.json`
directories; binaries, generated sources and logs also use fresh startup paths.
Slower variants are retained. Campaign elapsed includes the recorded board clock
before staging/queueing. Final machine evidence must pin all retained trials.

The original initialization counter sums 144 cold-head intervals, excluding small
outer validity/reset bookkeeping. The added complete-prepare counter includes
that bookkeeping and validates 12-layer coverage. Fused-row
work is charged to `projection_affine`, including scale/range certification and
residual finalization. Immutable-weight min/max scanning is inside model timing
but outside these nested counters; full phase totals are authoritative.

## Exactness, not reduced precision

- Maximum-derived int16/Q15 quantization proves the complete product below 2^31.
  Absolute and branchless signed versions retain original ties-to-even rounding;
  462,147 contract cases passed. Cold conversion holds four multipliers in
  registers and writes full words. Nothing moves onto the A9 or outside START.
- Fused projection tries the incoming residual exponent (zero without residual).
  Integer error bounds certify that the ordered binary64 range calculation would
  select exactly that exponent. Uncertain rows take the old complete path, without
  publishing scratch. Tests passed 1,526 accepted and 1,936 non-mutating fallback
  rows, including threshold cases.
- The interval-product candidate encloses the full-significand product using
  top-32 significands, widened for binary64 rounding. It accepts only when both
  endpoints round to the same integer multiplier. Otherwise it computes the full
  106-bit product. This is not a reduced-precision mode.
- Native full-model tests still check 396 tensors / 4,670,788 values, 60 generated
  outputs, every final logit and valid KV, alongside threaded/full-1024 operator
  edge cases and overflow non-mutation.
- Lazy V retains full-prefix maxima and units. One published bitmap bit certifies
  all 64 features at the current maxima; any maximum change invalidates the head.
  Only exact integer-zero attention probabilities permit absent V8 rows. Native
  tests poison absent rows, check every present row, compare all original
  outputs/raw KV, and exercise dense/sparse/zero demands and max-change invalidation.
  There is no approximate attention pruning. Cache version is explicitly 2.
- The bitmap uses trace `0x2b200..0x2f9ff`, with 144 first-demand flags at
  `0x2b080`; both fit below the existing smoothing area at `0x30000`. Demand lists
  borrow local-score BRAM only after softmax has consumed the scores. Neither
  existing hart stack nor local-score capacity was reduced.
- Parallel exact reciprocal setup joins before H0 publishes the smoothing cache.
  Batched smoothing reuses multipliers, writes complete words, and retains the
  original complete overflow fallback. Layer-normalization metadata retains
  ordered binary64 operations. Generic tests cover 96 threaded shape/alignment
  pairs, including odd widths, workspace failures and guard preservation.
- Final-branch enclosure passed 500,000 native cases (118,316 accepted), but its
  physical slowdown is preserved as a rejected hypothesis. Compilation failures
  included an include-order inlining regression and a four-byte memory overlap;
  no memory assertion was relaxed. Native test improvements and seam-header
  corrections are recorded in subsequent fresh builds.
- Reusable normalized projection constants certify the *final* RNE result with
  an explicit four-unit multiplier enclosure; ambiguous cases retain the full
  original calculation. 500,000 native cases passed (126,400 certified), plus
  20 batched accepted and 120 non-mutating rejected operator cases.
- Packed append writes whole transposed key words and preserves the 2-byte-
  unaligned QKV path. Fixed-branch builds passed native full-model/threaded and
  layout tests. The subsequent split image removes only mutually exclusive
  legacy/ready attention code: capture requests select a separately pinned
  same-source trace image. Existing memory/stack reservations are unchanged.
- The split campaign passed the original physical story trace and plain story,
  science and computing requests, all exact logits/raw KV and normal release.
  Plain delivered times: story two outputs 23.6167 s; science one 14.1055 s;
  computing one 14.1068 s. These are first diagnostic observations, not final
  three-repeat passes. Trace delivery (35.8621 s) is not headline throughput.

## Open work

Cold initialization and delivery now have diagnostic passes on one prefix, not
final qualification. The science request is still over 10 seconds. No target is
waived. The fixed-branch diagnostic science model time is 13.1541 seconds,
with approximately 1.0576 additional seconds through safe delivery. Plain
split-image science is 14.1055 seconds delivered. The current short-request
targets remain unmet.

An instruction-cache hypothesis is isolated under startup paths. The actual
two harts share a staged local instruction/data bus; instruction caching is
disabled in the qualified overlay. An ICache-enabled Verilator model built, but
the full original cache-off numerical suite exceeded its 120-second experiment
bound before completion. This timeout is retained, not a correctness pass.
A smaller matched two-hart soft-f64/integer probe passed exact host-oracle hashes
and cache CSR readback, including off/on/off/on firmware reloads under core-only
reset. Hart 0: 1,262,914 cycles off / 558,081 on; hart 1: 1,310,368 / 580,887,
with identical retired-instruction counts. Approximately 2.26x microbenchmark
speedup is **not a model throughput claim**. Probe setup failures (Verilator
include path; sticky console-done latch across core-only reset) are retained.

The cache-enabled ISA suite passed 84 expected passes and the same four frozen
waivers across 88 tests; every test enables and reads back the cache CSR. The
autonomous RTL configuration additionally passed the original accelerator
regression with normal and seven-cycle-delayed AXI: 9,633 independently checked
words per complete run, two completed boots plus packet-abort/remap and 14
component-lifecycle cases. Both-hart memory/M-extension tests passed, including
656 integer arithmetic pairs per hart, instruction-port DDR execution, explicit
FENCE.I self-modifying-code checks, unaligned accesses, protection faults and
abort/drain/remap. These are bounded tests, not model endurance runs.

Harness setup misses are retained: the first accelerator attempt linked the
non-autonomous numerical model and correctly rejected exposed development
ports. A fresh autonomous model was built. The inherited non-autonomous memory
harness then needed the already-qualified supervisor START/reset/flush sequence
and correct initial falling reset edge for the two-state simulator. All original
memory assertions remain; the corrected autonomous run passed.

The first clean physical cache candidate passed synthesis/structural checks but
failed final timing at **-0.903 ns WNS**. It was **not deployed**. Routed paths
identified instruction/decode-to-LUT-tag-memory feedback. A second isolated
candidate forced those synchronous tag memories into block RAM, retaining their
one-cycle behavior; synthesis confirmed two tag BRAMs per hart. It also failed
final timing, at **-1.943 ns WNS**, now limited by tag-output-to-instruction paths.
Both rejected hardware builds are retained; neither was deployed.

The next bounded alternative is a coherent 64-KiB instruction-memory mirror
with one dedicated read port per hart. Every original local-RAM write, including
byte masks and stack writes, updates the copy. Writes take priority over both
reads to prevent dual-port collision ambiguity. Only local instruction addresses
below 64 KiB bypass the shared bus; the existing routers still track accepted
requests, responses and drain, and all other accesses retain their old route.
It uses the original no-I-cache, pipelined-fast-M CPU configuration, not the
rejected cache-enabled cores. The memory cost is one additional 64-KiB BRAM bank.

The mirror's bounded probe passed exact hashes twice: hart 0 908,779 cycles,
hart 1 943,776. The matched qualified no-cache/pipelined-M model takes 1,263,133
and 1,310,671 cycles for the identical instructions/hashes (about 1.39x). Both
normal/delayed autonomous accelerator tests and the original memory/M-extension
tests passed; extra full-word/byte-store instruction-coherence tests cover six
spare local-memory offsets per hart. Two initial compile attempts exposed the
assertion's mixed reset classification; aligning its asynchronous sensitivity
with the mirrored valid registers passed without adding a lint waiver.

An isolated follow-up removes the extra instruction-response holding cycle and
allows the single owned instruction-request slot to turn over on its response
edge. Data-port routers remain in the original mode. New admission still requires
no stop/abort; old requests still drain. Simulation asserts one outstanding
request, no unowned responses and no admission under stop. The independent router
scoreboard passed 1,000 transactions in each mode, including 854 same-cycle
response/request handovers in the new mode, randomized backpressure, errors and
stop/drain. The direct-return matched probe passed twice at 618,600 / 643,509
cycles (about 2.04x versus the qualified baseline, not GPT-2 throughput).
Both-hart memory and normal/delayed accelerator integration passed again. Memory
checks additionally cover an instruction-port protection fault with exact trap
resume, without removing the original data-fault checks.

The first mirror synthesis unexpectedly inferred two banks (32 BRAM36s), caught
by the resource guard before placement. Explicitly sharing Port A's read/write
address corrected the inference. A fresh Verilator model repeated the same
probe cycles and passed all memory/accelerator tests. Fresh synthesis confirmed
one 64-KiB mirror (16 BRAM36s), both original fast pipelined harts, and DSP0.
The first completed mirror implementation missed timing at -0.010 ns. A bounded
high-fanout replication/reroute improved this to +0.124 ns, still below +0.250 ns.
One final post-route physical optimization reached +0.149 ns, still a miss.
The worst remaining path ran from the **original shared RAM**, through the
non-RAM instruction fallback mux, into hart 1's instruction register. This is
not the intended mirror data path. A separate variant registers the rare
non-RAM local response while retaining direct mirrored RAM instruction delivery.
There is no false-path exception and no change to the main fetch cycle count.
Fresh simulation again passed the exact probe (618,600 / 643,509 cycles), both-
hart memory tests, normal/delayed accelerator tests, and abort/drain/remap.
Directed tests now execute RET from each hart's mailbox register (real fallback
data), and check exact trap/resume for both unmapped-local and invalid-DDR
instruction fetches. This variant passed its fresh FPGA build at **91 MHz,
WNS +0.308 ns, hold +0.010 ns, TNS/THS zero, DSP0**, fully routed. Utilization:
29,090 LUTs, 21,747 registers, 111.5 BRAM36 tiles, 9,657 slices. The final netlist's
nine LUTAR warnings were individually reviewed: eight replicas of the original
two-input IO-reset NAND and the original core-reset/cancellation function.
All startpoints are the existing registered reset/control/cancel sources; there
is no newly introduced data-dependent reset. The single RTSTAT-10 is the same
no-routable-load class; no DRC errors/critical warnings. The extra reset replicas
are explicitly pinned by the new audit, not silently treated as the previous
six-warning result. No timing exception, clock or acceptance threshold changed.
The first bounded physical diagnostic passed all exact outputs, the original
story trace, overflow/recovery and normal zero-owner/pages/PTE release in
170.72 seconds including staging. Cold required initialization is 5.5473 s;
cold delivered forward 11.1476 s, warm last-slot delivery 5.4755 s. Original
plain requests: story two outputs 18.3806 s, science one output 10.9795 s,
computing one output 10.9896 s. This is a successful correctness campaign, **not
final performance closure**: science/computing miss by about one second.

The remaining science profile has 9.9860 s model time, 1.9420 s nested service
time and 8.0439 s scalar/control/memory remainder. Original START/RETURN safety
and cache synchronization still contribute about 1.05 s to delivery; none is
excluded or moved outside the request. A bounded next RTL hypothesis allows a
local RAM instruction read to issue at admission instead of spending another
cycle in the router's Send state. Admission is granted only when the mirror
actually accepts that read; write-priority stalls, one owned request, stop/drain,
DDR and non-RAM fallback behavior remain intact. It is a separate source-marked
experiment and must pass simulation and fresh hardware timing before deployment.
Its independent 1,000-transaction scoreboard passes in all three modes, including
334 early RAM admissions, same-cycle handovers, backpressure and stop coverage.
The exact CPU probe passes twice at 483,415 / 503,272 cycles, roughly 22% fewer
than the board-tested mirror and 2.61x the matched original probe. Both-hart
memory and normal/delayed accelerator integration also pass. A fresh FPGA build
failed final timing at **-2.947 ns** and was not deployed. Its live CPU branch
address fed through admission/fallback/grant logic into another cycle-critical
path; removing the Send stage indiscriminately was not timing-safe.

The next isolated alternative keeps the router address registered and reads
one sequential lookahead word on each instruction response. A coherent hit can
complete in Send; a miss keeps the qualified request/response path. Writes
conservatively invalidate both lookahead words, and prediction never crosses
64 KiB. It uses the same one extra 64-KiB bank, not an additional cache bank.
The independent three-mode scoreboard passes with 172 same-cycle local replies,
backpressure and stop/drain. The exact two-repeat probe takes 499,276 / 519,460
cycles (about 19% fewer than the board-tested mirror); the expanded memory and
normal/delayed accelerator tests pass. Fresh implementation reached +0.134 ns
WNS; bounded replication/post-route variants reached +0.143, +0.185 and +0.048 ns.
Every result misses the unchanged +0.250-ns gate. Further inspection also found
REQP-1839 asynchronous-control warnings on the lookahead BRAM address cone,
including the prediction tags and registered fallback-valid bits. These are
**not** the previously reviewed reset-LUT warnings and are not waived. None of
these implementations is safe to select, regardless of its timing result.

A separate synchronous-lookahead variant resets all new BRAM-control state
synchronously. A dedicated asynchronous-assert/synchronous-release bridge keeps
that reset island explicit; a clocked ready flag delays instruction admission
until it is released. Speculative local reads may harmlessly finish during
drain, so asynchronous core-reset/cancel outputs are no longer part of the
BRAM address-selection cone. There is no new external request or ownership.
The first direct mixed-reset attempt failed lint and was retained; the reset
bridge version builds without a lint waiver and repeats the exact 499,276 /
519,460-cycle probe. Both-hart memory/coherence/fault/abort tests and normal plus
seven-cycle-delayed accelerator tests pass. The fresh three-mode ownership
scoreboard also passes all 3,000 transactions, including 172 same-cycle local
responses and 821 stop-while-owned observations in lookahead mode. Fresh FPGA
requalification is running; the asynchronous-control DRC must be absent as well
as meeting the original timing gate.
The fresh synthesis confirms both fast harts, DSP0 and 16 mirror BRAM36s. A
read-only REQP-1839 screen of its synthesized checkpoint reports zero violations;
the identical screen rejects the retained asynchronous candidate as a negative
control. This is an early safety screen, not a substitute for routed DRC/timing.
The first screen invocation used an unsupported query option after producing
its report; the corrected query and fresh outputs are retained separately.
The fresh routed design now passes the full guard: **91 MHz, WNS +0.262 ns,
hold +0.016 ns, TNS/THS zero, DSP0**, all 45,385 routable nets routed. Utilization
is 29,138 LUTs, 21,783 registers, 111.5 BRAM36 tiles and 9,768 slices. Routed DRC
has only the reviewed RTSTAT-10 warning, no REQP-1839 or CHECK-3 findings. The
actual final checkpoint's seven reset warnings are six replicas of the existing
two-input IO-reset NAND (INIT 4'h7), plus the existing core-reset/cancel function
(INIT 8'hEF). Their seven startpoints are the original registered GPIO/reset and
accelerator cancel/fault sources, with no data-dependent reset. The audit pins
this selected checkpoint's actual non-replicated GPIO[0]/abort-request names.
This qualified bitstream is `build/m5_startup_fetch_sync_pynq_v2`; its matching
model and integration tests use `fetch_sync_*_v2`. Physical performance remains
to be measured on this hardware; none of the timing thresholds was lowered.
Its first physical campaign passes all seven cases, exact full outputs, original
story trace, overflow/recovery and normal zero-owner/pages/PTE cleanup in
167.26 seconds including staging. Required cold initialization is **5.3357 s**,
cold delivery **10.7162 s**, and warm last-slot delivery **5.2788 s**. Plain
story two-output delivery is **17.7015 s**; science/computing are **10.6119 s**
each. The model times are 16.6466 / 9.5524 / 9.5530 s respectively. Thus the
microbenchmark's 19% cycle reduction translates to only a roughly 3.5% gain
for these short requests. They still miss the unchanged 10-second gate, so the
prepared final repetition stages and selection v2 are **not executed/closed**.

The next bounded hypothesis targets local data loads. The original shared bus
captures, arbitrates, issues and returns each read even after instruction fetch
has been separated. A second coherent 64-KiB mirror provides one data-read port
per hart, keeping the original registered data-router response and all writes,
peripheral/DDR accesses and ownership on their existing paths. Every accepted
RAM write updates both copies; writes conservatively stall both data reads.
It uses the existing synchronous reset island and no live CPU-address bypass.
The explicit resource cost is **16 more BRAM36 tiles**, targeting **127.5/140**
total (12.5 remaining), rather than silently retaining the 111.5 claim. The
91-MHz +0.250-ns setup/positive-hold/DSP0/clean-DRC gates are unchanged. Simulation,
fresh synthesis/resource/timing and physical tests are required before selection.
The data-read-only model passes the same exact probe twice (480,815 / 499,977
cycles), both-hart memory and normal/delayed accelerator integration. This small
probe gain is not taken as a throughput claim. A separately marked follow-up
uses the already-scoreboard-tested direct response mode on data routers too,
removing one local-read/DDR-response holding cycle. Shared-bus writes/peripherals
retain their old effective latency through a synchronous fallback register,
which keeps the old shared-RAM mux out of the fast LSU response path. Ownership,
stop/drain and DDR protection are unchanged. New memory tests additionally read
back local word/halfword/byte data and execute code after a halfword modification.
An initial derivation-order mistake failed before RTL compilation and is
retained; its corrected fresh model is building. Earlier derived variants have
been rechecked against their immutable exports after the generator extension.
The corrected combined data-path model now passes its exact probe twice at
470,860 / 489,571 cycles, the expanded local word/halfword/byte and code-coherence
checks, original memory/protection/abort/remap tests, and normal plus delayed
accelerator tests. The data routers use the existing scoreboard's direct mode
(1); lookahead instruction routers still use mode 3. A fresh hardware build is
running under `build/m5_startup_data_direct_pynq_v2`. It is not yet qualified or
deployed, and no short-request speed is inferred from the probe.
Its synthesis proves exactly 16 instruction plus 16 data-read mirror BRAM36s,
both 91-cell fast-multiply harts and DSP0. The read-only synthesized BRAM-control
screen passes with zero REQP-1839 violations. Simulation/synthesis source
manifests match. Final routing, timing and all routed DRC remain pending.
The final data-path build has clean routed DRC apart from RTSTAT-10 and seven
existing reset-LUT methodology warnings, but **WNS +0.189 ns** misses +0.250 ns.
It was not deployed. The worst path is the existing hart-0 instruction/ALU decode
to an intermediate-value register, not a new BRAM-control failure. One bounded
post-route pass now targets an additional 0.500-ns optimization uncertainty;
the earlier 0.989-ns artificial target put the optimizer outside its recommended
post-route slack range. This is an implementation heuristic only: the unchanged
final guard restores the original user uncertainty and still demands the same
91-MHz +0.250-ns setup margin, positive hold, routing/resource and DRC checks.
That margin-focused post-route trial retained **+0.189 ns**, so it also remains
unqualified. The next bounded correction is the existing targeted driver-
replication/reroute procedure, selecting actual sub-+0.350-ns paths whose
startpoint register drives more than 16 sinks. It operates on a new checkpoint
copy and retains the same complete final guard. There is no threshold waiver.
The replication/reroute passes: **91 MHz, WNS +0.269 ns, hold +0.008 ns, TNS/THS
zero, DSP0**, all 45,626 routable nets routed. The selected corrected checkpoint
uses 29,229 LUTs, 21,833 registers, **127.5 BRAM36 tiles**, and 9,752 slices.
Its routed DRC has only RTSTAT-10; the actual seven reset-warning cells are six
IO-reset NAND replicas plus the same original core/cancel function, with the
same seven registered startpoints as the prior synchronous candidate. The
read-only final checkpoint review is `build/m5_startup_data_reset_review_v1.log`.
Qualified hardware is `build/m5_startup_data_finish_v1`, synthesized from
`data_direct_pynq_v2` and simulated by `data_direct_autonomous_v2`. The first
bounded physical campaign is staged; request timing has not yet been measured.
Its seven-case physical campaign passes exact outputs, original traces,
overflow/recovery and normal cleanup in **171.37 seconds** including staging.
Required initialization is **5.2735 s**; cold delivery **10.4995 s**, warm delivery
**5.1266 s**. Original plain story two-output delivery is **17.1524 s**, science
**10.2926 s**, computing **10.2910 s**. The remaining ~0.293-second short-request
miss is retained, not rounded into a pass. No final repetitions have run.

The next firmware-only candidate uses the local code space freed by split
images to inline the fixed-factor certificate and narrow saturation helpers in
the hot batch-projection leaf. Operations, proof bounds, RNE, overflow handling
and fallback are unchanged; only call placement changes. The generated header
is a separately hashed copy, leaving earlier sources/binaries intact. The
`inline_fixed` build inherits the complete split-fixed native test suite and
must pass code/local-memory/stack bounds and fresh exact physical checks.
Both fresh inline builds pass the complete native suite, and all four binaries
are byte-identical (`inline_fixed_v1` / `inline_fixed_repro_v1`). Runtime BSS ends
at 0xb614, below the unchanged 0xc000 score area; worst conservative stack bounds
remain 3,168 bytes (runtime/trace) and 3,072 (profile/detail). Linked code no longer
contains the two out-of-line helpers. The bounded physical campaign is running.
The inline-fixed campaign passes correctness/cleanup but provides no speed gain:
science **10.3095 s**, computing **10.2995 s**, story **17.1954 s**. Its 218.34-s
campaign elapsed includes staging/queueing. It is a retained rejected slowdown,
not the selected firmware. A separate `inline_product` candidate starts from
split-fixed and inlines the more widely used certified metadata-multiplier
helper instead. Its arithmetic and complete fallback are unchanged; the earlier
fixed/narrow inlining is not inherited. Both generated-header copies are hashed.
Inlining the metadata multiplier everywhere overflowed the diagnostic code/BSS
boundary by 140 bytes; the unchanged linker guard rejected it. That partial
build is retained and was not deployed. The corrected fresh variant inlines an
exact copy only in the general projection leaf, keeping the original shared
helper for cold/batch callers. No memory reservation or numerical bound changes.
The first selective generator attempt rejected a void-function extraction;
the corrected `inline_product_v3` uses a local balanced-brace extraction without
changing the frozen parent helper. It and `inline_product_repro_v3` pass all
native gates, all four byte-identical binaries, and the unchanged stack bounds.
The 179.12-second board campaign passes exactness and normal cleanup. Science
delivery is **10.2530 s**, computing **10.2389 s**, story **17.0619 s**: a small
improvement over split-fixed, still a short-request gate miss. The case-elapsed
values include postchecks and are not delivery latency. No final repetitions
are run on this miss.

The next bounded `bias_reuse` trial starts from split-fixed, without either
inlining change. Residual projections with multiple rows and equal incoming
exponents repeatedly perform the same exact bias rounding. The first accepted
row now writes those int32 values into the unused upper half of the already
allocated 8*n-byte bias scratch. Later rows may reuse them; speculative int16
outputs occupy only the disjoint first 2*n bytes. An uncertain/rejected row
invalidates this private cache **before** the original generic fallback may
overwrite the entire scratch. Different exponents and scaled/no-residual
previews retain the old per-row calculation. There is no extra allocation,
persistent memoization, changed precision/range certificate, or untimed work.
New native edge tests compare the unchanged no-cache row operator against
multirow reuse, including halfway ties, signed zeros/subnormals, invalid biases,
unequal exponents, first/middle-row rejection, poisoned fallback scratch and
unmodified public outputs on rejected rows. Full-model/threaded tests still
exercise the actual production projection.
`bias_reuse_v1` and `bias_reuse_repro_v1` both pass the complete native suite
and the new 1,024-sequence test (2,048 reused rows, 3,168 fallback rows). All four
images are byte-identical. Conservative stack bounds rise by 32 bytes to 3,200
for runtime/trace and 3,104 for profile/detail, below the original 4,096-byte
per-hart limits. No local-memory linker guard changed. Its seven-case physical
screen is running on the fully qualified data-mirror overlay.
That screen passes exactness/cleanup in **193.55 s** including staging. Delivery
is **10.2660 s** science, **10.2576 s** computing, **17.0753 s** story; cold
**10.4756 s**, warm **5.1106 s**. The tiny short-request gain does not satisfy the
gate and does not justify final repetitions yet.

`residual_fixed` extends the already validated four-integer-unit multiplier
enclosure from unscaled batch projections to these residual rows. Normalized
weight metadata occupies the existing separate `scales` scratch; the same
accepted-first-row lifetime and pre-fallback invalidation govern both caches.
The first row prepares metadata inside the leaf; later rows reuse it. Every
element still requires the complete interval to give one exact final RNE value;
uncertain or invalid fixed factors call the unchanged binary64 multiplier and
word-affine path. The original full-row exponent/range certificate, bias
rounding, residual saturation and publication rules remain unchanged.
The fresh build passes all native gates plus 1,024 randomized residual sequences
with non-power-of-two weights/units (748 reused rows and 5,912 fallback rows
matching the old operator). Code/local-memory guards pass. Conservative stack
bounds are 3,200 bytes runtime/trace, 3,104 profile and 3,120 detail. The original
4,096-byte limits remain unchanged; a fresh reproduction and board screen follow.
The reproduction passes all four byte comparisons and the same stack/native
gates. The 181.31-s board screen remains exact with normal release, but science
**10.2956 s** and computing **10.2882 s** still miss. Story is **17.1215 s**,
cold **10.5097 s**, warm **5.1306 s**. This candidate is not a performance pass.

A new **native-only** branch-coverage experiment runs the actual original
prompts and verifies every logit plus full KV. It is not FPGA timing evidence.
`projection_coverage_v1` shows only 18/192 science residual rows entering the
cache-capable path: a first-token exponent outlier disables the all-rows-equal
condition, and an early fallback disables the cache for all later rows.
The bounded `rolling_fixed` correction therefore tags the private scratch with
the **last accepted row's exponent**. Matching rows reuse it; exponent changes
or generic fallback invalidate the tag, and the next row rebuilds all metadata
before publication. This does not retain metadata between projection calls or
requests and does not change any numerical eligibility/proof bound.

`rolling_fixed_v1` and `rolling_fixed_repro_v1` pass the complete native suite,
all four byte-identical firmware images, and conservative stack bounds of 3,216
bytes runtime/trace, 3,120 profile and 3,136 detail. New edge coverage includes
1,024 tag/lifetime sequences (3,648 reuse attempts, 3,168 fallback rows), 1,024
non-power-of-two random sequences (1,399 reuse attempts, 5,912 fallback rows),
and 256 alternating/returning-exponent sequences (576 reuse attempts and 576
fallbacks). Every accepted result matches the unchanged old row operator;
rejected outputs/exponents and input guards remain unchanged. Native
`projection_coverage_v3` explicitly counts 139 actual metadata reuse attempts
on both science and computing, and 254 on story, with exact logits/KV.
`projection_coverage_v2` counted cache-capable rows, not reuse attempts; both
schemas and outputs are retained. The qualified-hardware physical screen is
running; no final repetitions or performance claim yet.
The rolling-tag board campaign passes exactness/normal cleanup in **178.42 s**.
Science delivery is **10.1325 s**, computing **10.1389 s**, story **16.8517 s**;
cold **10.5097 s**, warm **5.1301 s**. This improves the short path but still
misses the 10-second gate. The next `local_rows` change reuses the existing
4-KiB local score buffer for tentative int16 projection outputs up to 2,048
columns. Attention and projection are sequential, all worker leaves join, and
scores are dead once attention returns its context. Projection workers own
disjoint aligned portions. No local RAM or workspace reservation grows; larger
vectors retain their original DDR scratch, including the complete 50,257-logit
head. The existing exponent proof still gates publication to the caller.

`local_rows_v1` passes the complete native suite, including 48 explicit
2,047/2,048/2,049-column boundary sequences with two workers, exponent changes,
uncertain fallback and output guards. Original full-model traces and subsequent
attention calls verify the sequential shared-buffer lifetime. Reproduction,
stack checks and a fresh physical screen follow before any selection.
The reproduction is byte-identical for all four images; stack bounds are 3,232
bytes runtime/trace and 3,136 profile/detail. The board campaign passes
exactness/release in **175.56 s**: science **10.0393 s**, computing **10.0480 s**,
story **16.6854 s**, cold **10.4913 s**, warm **5.1046 s**. The remaining 39–48-ms
miss is not rounded into a pass.

`local_bias` now attempts exact int16 storage for private cached biases beside
the tentative outputs: 2*n + 2*n bytes fit the existing 4-KiB score buffer when
n<=1,024. Larger rows keep the original DDR reservation. A rounded bias outside
int16 rejects tentative publication and executes the complete original generic
row; there is no saturation, approximation or model-precision change. Tests
explicitly include large bias/branch cancellation where the old speculative
path can accept but the narrow-cache path must leave outputs untouched and
fall back. Local scratch is poisoned after failed raw-row tests to verify tag
invalidation. The first build exceeded the diagnostic code/BSS boundary by 132
bytes and was rejected, not deployed. The next fresh build size-optimizes only
the per-row setup/certification function, with unchanged ordered arithmetic and
no loop-to-libc transformation. The hot element leaf remains at O2. No memory
reservation or assertion is relaxed.
The Os attempt was rejected at link time because compiler-generated structure
copies required unavailable `memcpy`; it was not deployed. The fresh v3 keeps
O2 and only prevents inlining the per-row function into its large caller. This
fits all four images below the unchanged boundary without adding libc code.
Both `local_bias_v3` and `local_bias_repro_v3` pass the full native suite,
including 30 additional bias-capacity/large-cancellation fallback sequences.
All four images are byte-identical; stack bounds are 3,136 bytes runtime/trace,
3,040 profile and 3,056 detail. The new physical screen is running on the
unchanged qualified data-mirror overlay. This is still not final performance
closure until every required plain repetition passes.
The first local-bias board screen passes exactness/normal release in **174.14 s**.
Required cold initialization is **5.2726 s**, cold delivery **10.4909 s**, warm
**5.1148 s**. Original plain science is **9.98865 s**, computing **9.99382 s**,
story two outputs **16.60391 s**. This is the first individual short-request
gate pass, but only **6–11 ms** of one-token margin: it is not repeated closure.
The new selection v4 identifies this firmware/hardware and fresh both-prefix
diagnostic/final stages. Required three-repeat plain qualification follows;
every individual sample must still meet the original bound.
All three final plain original-request repetitions now pass on this selection.
Science is **9.990257 / 9.994399 / 9.996906 s**; computing **9.994644 / 9.994261 /
9.995312 s**; two-output story **16.605436 / 16.603601 / 16.601940 s**. All tokens,
logits, complete KV and the original story trace are exact. All three story
cold/warm pairs pass: cold **10.4546–10.4573 s**, warm **5.0842–5.0905 s**.
Normal release and the 325.08-second including-staging campaign bound pass.
The worst short-request headroom is only **3.094 ms**; this must remain explicit,
not recast as a sustained or arbitrary-request guarantee. No samples are pooled
to conceal a miss. Independent science-prefix diagnostic/final qualification
and the final chained audit remain open.
The independent science-prefix diagnostic also passes: required initialization
**5.4222 s**, cold delivery **10.5961 s**, warm last-slot delivery **5.3733 s**,
all exact and normally released in **159.38 s** including staging/queueing.
The three final plain science cold/warm pairs are now running. The preferred
<=5-second initialization stretch remains unmet; the required <=10-second
initialization and <=20-second cold-delivery gates pass on both prefixes.
All three science final pairs pass: cold **10.557780 / 10.564295 / 10.567245 s**,
warm **5.336473 / 5.338301 / 5.338002 s**. Each warm run reaches 1024 valid KV
positions exactly. Overflow/non-mutation, exact outputs and normal zero-resource
release pass; the complete campaign takes **157.91 s** including staging.
The complete closure preflight validates all 38 archived campaigns, selected
native/reproduction/stack gates, simulated/synthesized RTL identity, final
routing/timing/resources/reset review and every required per-sample latency
limit. The frozen context audit and all 27 startup unit tests also pass.
These remain microbenchmark, not GPT-2 claims.
No failed timing candidate was deployed.

All 38 completed historical board campaigns now archive their actual deployed
Python runners under `deployed/`, with every policy hash checked; current-source
symlinks are not mistaken for old snapshots. The entire frozen context audit
still passes. Conservative linked-binary stack analysis, including indirect
callbacks, libgcc and one nonreturning trap, bounds runtime/trace at 3,168 bytes
and profile/detail at 3,072 bytes per hart, below the unchanged 4,096-byte stacks.
All four cache-enabled firmware images reproduced byte-for-byte in a fresh build.
The selected **no-cache** mirror firmware also reproduced all four images
byte-for-byte (`fetch_split_v1` / `fetch_split_repro_v1`); both complete builds
passed the native numerical/operator suite and conservative stack bounds.
The first stack JSON mislabeled the ELF hash as a firmware hash; new
`stack_bound_v2.json` files distinguish ELF and deployed padded-binary hashes.
Both were rechecked, with unchanged 3,168 / 3,072-byte bounds; old metadata is
retained. There was no firmware mismatch or stack-bound change.
Twenty measurement
and trace-selection tests now cover request-specific first-use counter coverage
and rejection of changed/unloadable trace firmware before request execution.
The read-only startup campaign validator passes all 38 retained physical
campaigns. Its negative tests reject missing/reordered checks, changed original
prompts/logits/KV/traces, unsafe release, hidden first-demand initialization, and
individual latency misses even when a pooled mean would pass. Final evidence
collection passes with the final v4 selection; all repeated performance gates
are closed. Earlier provisional selections remain recorded and are not releases.

Selected-hardware timing, both-prefix three-pair cold/warm qualification and
three plain original short-request repetitions (including the selected original
story trace) are complete. Arithmetic checks, memory/stack accounting and
byte-identical firmware rebuild pass. Complete machine evidence chains the
frozen context audit. M6 and pushing remain separately gated.

Intermediate build issues are retained: wrong bounded-test argument and reference
module import (fixed); an ambiguous transformation matching both attention paths
(fixed by scoping). Packed-output builds tripped the unchanged code/local-score
overlap assertion. Sharing the product helper and size-optimizing only the legacy
trace fallback preserves that memory gate. That fallback disables loop-to-memset
conversion for the freestanding image. These were not physical test failures.
