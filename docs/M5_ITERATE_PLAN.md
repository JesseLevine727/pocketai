# M5 — three bounded optimization/reassessment cycles

Status: **CLOSED / PASS**. Baseline: pushed `bf4ec02043ad8759d0c4bbe60e781055e224fd87`.
All three cycles and final bounded qualification are complete; see
[results](M5_ITERATE_RESULTS.md), [reviews](M5_ITERATE_REVIEWS.md) and
[auditable evidence](m5_iterate_evidence.json). This contract is preserved below.
This goal comprises **three total cycles**, each implementing or genuinely
testing a bounded tweak, measuring exact results, and reassessing the remaining
system bottleneck before selecting the next cycle. Planning or three repeats
of one benchmark are not completion.

## Preserved contract

Full autonomous GPT-2 W8A8/int16: 12 layers/heads, all 50,257 logits, 1024 KV
capacity, exact rounding/bias/epsilon/ties and A9 provisioning-only role.
Both harts retain the qualified pipelined RV32MFast (9/12 execute cycles).
Reuse the exact 91-MHz fast overlay by default: +0.263-ns setup, +0.018-ns hold,
zero TNS/THS, DSP0. No slow fallback, F/D/DSP substitution, W4/W4A4, clock or
margin relaxation, M6, agents, tracker scaffolding or unrequested push.
Preserve `NA/` and every previous closure audit/source/artifact identity.
Derive isolated sources from hash-pinned inputs; never relabel old evidence.

Scoped local edits/builds/SSH tests and the normal DMA helper lifecycle are
authorized. Never store credentials, access tensors while host/device ownership
is wrong, free undrained DMA pages or force-unload an active helper.

## Cycles and decision rule

1. Start with duplicate attention affine metadata and repeated LayerNorm
   preparation. Test exact reuse/specialization, not altered model numerics.
   Inspect idle polling and shared instruction/local-bus contention.
2. Use cycle 1's measured profile to choose the next bounded tweak. Candidates
   include safe interrupt wait, useful two-hart scalar work or further exact
   preparation. Blind WFI is forbidden: prove wakeup/ack/lost-event behavior
   and compatibility with the runtime's fatal-trap handler first.
3. Reassess again and target the largest justified remaining cost. Consider
   head preparation/locality, explicitly owned persistent metadata, unnecessary
   prefill work or a small operation extension only when evidence supports it.

At most two measured implementation candidates per cycle, excluding corrections
of actual correctness defects. Each cycle ends with an explicit retain/reject
decision, complete timing samples, exactness evidence, remaining dominant costs
and next experiment. A negative investigation is valid, but cannot replace
trying a concrete useful tweak. Global exponents, operation ordering, descriptor
ownership and cache lifetime/version/bounds/invalidation are not optional.
All necessary precomputation is charged to startup/request or separately
reported model provisioning, never silently moved out of a benchmark.

New RTL is conditional, not required. If justified, coalesce into at most one
new implementation after affected simulation; require the unchanged +0.250-ns
setup floor, positive hold, TNS/THS0, DSP0, complete route/constraints, no final
DRC/methodology errors/critical warnings and review remaining warnings. No
speculative seed sweep or rebuild for each software candidate.

## Bounded evidence and closure

Frozen policy: `tests/m5_iterate/performance_policy.json`.
Default focused diagnostics <=120 seconds each; no 1024 endurance, 3x20-token
campaign or broad architecture/precision sweep. Use the independent past-13
seed, input 257, expected 582, valid14; every board sample must match complete
logits and valid KV. Per-cycle profiled/disabled pairs are diagnostics, not
three-sample primary claims. Fine counters remain nested/inclusive.

Final production-style firmware: one diagnostic, one warmup, three measured
unprofiled decodes with all descriptive statistics and separate model/resident
START-through-delivery boundaries, compared to bf4ec02. Original complete
2/1/1 requests, affected traces, overflow non-mutation/recovery, unchanged full
arena, safe return/close/reopen owner0/pages0/pte_dma0 and normal helper unload
run once at the end under a cleanup-safe <=20-minute campaign watchdog.
Reuse unaffected historical evidence; require affected native regressions and
byte-identical fresh firmware reproduction. >=1 token/s remains stretch.

Finish three written first-principles reviews, final results and independently
checkable source/artifact evidence, a read-only audit with negative tests,
preserved prior audits and a scoped local commit. No push until requested.
Only major gates or material issues warrant user updates.
