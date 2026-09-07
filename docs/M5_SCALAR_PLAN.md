# M5 scalar preparation — bounded acceleration

Status: CLOSED / PASS. Baseline: pushed `1825659a419e98a53b0916dba8a187a45bbd1a0b`.
All four candidates were retained and final physical qualification/reproduction
passed. See [results](M5_SCALAR_RESULTS.md) and [evidence](m5_scalar_evidence.json).
The preserved bounded contract follows.

Optimize this project's autonomous FPGA-led GPT-2, not a replacement running
the model on the ARM. Preserve exact W8A8/int16, full vocabulary, 12 layers and
heads, 1024 KV capacity, both pipelined RV32MFast harts and the qualified 91-MHz
DSP0 overlay. No accuracy, clock or timing-margin relaxation. One token/s is
stretch, not a reason to change the architecture or hide setup time.

At most four main measured candidates, with correctness corrections allowed:

1. Exact 32-bit quantizer division and inlined fixed-shift quantization.
2. Exact bounded-domain lookup/reuse versus arithmetic, including setup cost.
3. Fresh fine-profile-guided metadata reuse and memory-pass reduction.
4. A final justified refinement, only if the preceding evidence supports it.

Keep the fastest exact measured combination; negative candidates are retained
as evidence, not deployed. Preserve original hash-pinned source/evidence using
an isolated generator. Do not modify `NA/`, add agents/tracker scaffolding, or
push without another request. No new RTL or long-context endurance campaign.

Lookup/prepared data must have explicit ownership, bounds and invalidation.
Prefer call-scoped reuse; mandatory preparation remains inside measured work,
or is explicitly reported as provisioning rather than an apparent speedup.
Preserve operation ordering, global exponent reductions and DMA ownership.

Reuse existing exact native tests and independent past-13 board seed. Each
candidate gets a short profiled/unprofiled diagnostic with complete logits and
valid KV comparisons. The final version gets one diagnostic, one warmup and
three unprofiled observations, plus one original full 2/1/1 campaign with
traces/error recovery. Report model and START-through-delivery separately.
Require byte-identical clean rebuild, previous audits, concise new evidence
checks, owner0/pages0/pte_dma0 cleanup, normal helper unload and a scoped commit.
No hours-long sweeps; no claim of a global optimum or sustained throughput.
