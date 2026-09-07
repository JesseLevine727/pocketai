# Frozen-release characterization: 60-minute board cap

Characterize `e5883bc`, without optimization or changes to the full GPT-2 model,
precision, FPGA hardware, 91-MHz clock, two fast Ibex harts, runtime or DMA driver.
The 60 minutes includes board preparation, provisioning, correctness checks,
seed restoration, measurement and normal release; it is a cap, not a target.
Independent reference preparation has a separate 10-minute guard. No M6.

The exact non-Cartesian order, per-case conservative admission bounds and hashes
are frozen by `python3 -m scripts.m5_sweep_policy` before reference/board work.
Each completed case checkpoints its raw result. Two minutes remain reserved for
cleanup; an alarm cancels/drains through the qualified driver, never force-unloads
the helper or frees undrained pages. Missing references and insufficient remaining
budget produce explicit skips. Failed and slow observations remain in evidence.

Coverage: prompt lengths 1/8/13/16/32/64; 1/4/16 generated tokens; original
story/science/computing streams; repeated 16-token uninterrupted requests;
cached decode at past 1/8/13/32/128/512/1023, repeated short anchor and selected
short/long phase profiles. The synthetic prompt curve repeats/truncates the
frozen story tokens; it is length control, not a language-quality benchmark.
No full Cartesian product or 32-output extension of the existing 20-step oracle.

All generated token IDs, all final logits and all valid K/V are checked against
independent qualified M4 references. Preserve the original 2/1/1 requests,
five selected story-prefill traces, overflow non-mutation and accepted recovery.
Long cached contexts are independently prefilled on the native host and injected:
they do not establish physical-board long-prompt prefill performance.

Report provisioning (not power-on cold start), on-board prefill, model first-token
time (not streamed delivered TTFT), continuation intervals, resident request
delivery, prompt-inclusive generated-token rates, injected-cache decode, and the
fully charged campaign rate separately. Service contains GEMM/SFPU engine time;
its complement is CPU/control/scalar-memory remainder, not measured arithmetic.
Mixed engine work is not GMACs. Include all samples and descriptive statistics,
sample counts, traffic/workspace, reused hardware timing/resources, and limits.
No power, thermal, endurance, QoS-tail or universal 0.1-token/s claims.

Deliver new policy/reference/raw/CSV evidence, report, read-only chained audit,
mock/negative safety tests and a scoped local commit. Preserve every old audited
artifact and unrelated `NA/`. No push requested for this goal.
