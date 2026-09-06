# M5 goal — autonomous GPT-2 on the RISC-V fabric

Status: **CLOSED — lean acceptance PASS**, 2026-09-06 UTC.
Baseline: pushed M4 closure `114bcc58bba8a32e9b683c639072f2b690582d2f`.
The user explicitly selected **>=1 token/s as a stretch target**, not a hard
closure gate. On 2026-09-06 the user also selected a **lean side-project
closure**: retain real autonomy, exactness, safety, timing and useful physical
performance evidence, but remove duplicate and marathon acceptance runs. M4 is
complete; M5 now passes its final physical model, safety, timing and performance
campaign. See [verification](M5_VERIFICATION.md), [performance](M5_PERFORMANCE.md)
and the machine-readable [closure evidence](m5_closure_evidence.json).

Authorization update: the user explicitly approved loading the temporary DMA
helper and requested removal of subsequent approval gates. Necessary M5
implementation, deployment, board testing and recovery are preauthorized;
continue without routine confirmation prompts. Preserve the scope and safe
memory-ownership rules below.

## Outcome and non-negotiable scope

Run the same actual GPT-2-small/124M adaptive-v3 model autonomously under
bare-metal Ibex firmware. The two-hart system owns the complete model loop,
prefill, incremental decode, scale metadata, accelerator/transfer scheduling,
KV cache and greedy token selection. Define and test each hart's role rather
than claiming two-core inference from an idle second core.

A9 may program the overlay, load/verify firmware and immutable model assets,
allocate/provision owned memory, submit prompt token IDs, start/stop a request,
and receive output token IDs/status. After START it must not compute or pack
tensors, decide layer/operator descriptors, serve weight/tensor transfers,
maintain KV, choose scales or select output tokens. A polling/status/token
transport is not a tensor-service worker. Independent post-run tensor checking
is permitted, mandatory for qualification, and excluded from performance timing.

- Preserve the M4 checkpoint/tokenizer/calibration/prompts, frozen adaptive-v3
  reference and independent quality evidence. Full 12 layers, 12 heads, width
  768, 3072-wide MLP and all 50,257 vocabulary outputs.
- Preserve W8A8 GEMM with int16 activation/KV storage, exact int32 reductions,
  K=3072, unsigned softmax probability 32768, M3 rounding/bias/saturation order,
  model scales and LayerNorm epsilon compensation. No quiet numeric rewrite.
- Batch one, learned absolute positions and causal attention through **1024
  positions**. Original lowest-ID greedy ties and fixed-20/EOS policy. No
  200-token eviction window or int8-only KV substitution.
- DDR holds the full model and KV. The existing 64-KiB scratchpad is bounded
  working/firmware storage, not multi-MiB whole-model KV storage.
- Integer, portable, DSP-free fabric at **91 MHz**. +0.250 ns WNS is the hard
  setup gate; 95 MHz, +0.500 ns and 100 MHz remain stretch only. Two complete
  95-MHz implementation strategies reached -0.002 ns and -0.028 ns WNS, and
  the first 92-MHz implementation reached +0.203 ns. The lean side-project
  policy does not justify more seed/strategy hunting for this small clock-rate
  difference.
- Preserve M1–M4 artifacts, historical measurements, ABIs, dependency pins,
  numerical/error budgets and unrelated `NA/`. Prefer M5-specific modules and
  build configurations; review/retest any necessary shared-source change.
- SSH only, no credentials in files/commands/logs. Necessary M5 kernel/board
  work is authorized by the user; prefer temporary changes and avoid needless
  boot changes. No unowned physical memory or pagemap-only pseudo-pinning for DMA.
- Scoped local commits; no remote push until requested. No unrequested agents.
  M6/ASIC/PPA work is outside this goal. Report major gates and real blockers.

## Gates

| Gate | Required result | Current status |
|---|---|---|
| G0 | Scope, ownership and qualification/invalidation policy recorded | PASS: lean plan, versioned ABIs and premeasurement performance policy frozen |
| G1 | Safe DDR/firmware/working-memory architecture, inventory and ABI | PASS: all 65,012 pages / 266,289,152 bytes, bounds, mmap, close/reopen and normal helper unload |
| G2 | Autonomous DDR/transfer/control RTL with lifecycle qualification | PASS: dual-Ibex operators/lifecycle simulation; physical precise fault, overflow rejection, safe return and subsequent accepted boots |
| G3 | Complete bounded bare-metal model runtime, faithful numerics | PASS: portable and actual-Ibex numerics; full autonomous GPT-2 on the board; final -O2 firmware fits 64 KiB |
| G4 | Lean progressive host/RISC-V/model and affected compatibility tests | PASS: four full-model cases, 396 traces, 60 generation steps, eight host runner tests, six ARM checker tests and affected compatibility regressions |
| G5 | One clean timing-qualified full M5 overlay build | PASS: source-checked clean build, 91 MHz, WNS +0.584 ns, TNS 0, hold +0.045 ns, DSP 0; warnings reviewed; full shell exit 0 |
| G6 | Concise physical autonomous model acceptance | PASS: story five tokens plus science/computing one each; exact final full logits/KV and five story traces; terminal exit 0 and cleanup |
| G7 | Frozen-boundary real performance and matching comparisons | PASS: resident story 0.010103 tok/s; cached decode 0.025276 tok/s; raw samples/memory/counters retained; historical-only M4 comparison, no speedup claim |
| G8 | Every-requirement audit, evidence documentation and local closure | PASS: pinned closure evidence, read-only auditor, reconciled documents and scoped local closure commit; no automatic push |

## G1 — memory, autonomy and ABI feasibility

Inventory actual board RAM/CMA, kernel/tool support and memory lifetimes before
choosing an allocation strategy. M4's pack is 205,271,824 bytes; its complete
1024-capacity K/V/K8/unit caches total 48,365,568 bytes. These payloads alone
exceed the current 128-MiB CMA pool, so moving all allocations to PYNQ CMA is
not a valid design. Account separately for code, stacks, descriptors, mappings,
temporary tensors, staging, guard regions and host-side provisioning memory.

Establish an owned, bounded DDR arena and safe device-visible mappings. CPU and
fabric addressing must be explicit, including page boundaries, permissions,
cache synchronization, DMA completion and error handling. Page addresses must
remain valid until all fabric access has stopped. Merely reading PFNs from
userspace pagemap or assuming unused DDR is safe is prohibited. If a temporary
kernel memory helper is necessary, build/review/test it first. Loading and
subsequent necessary M5 board work are now authorized; avoid boot/repartition
changes where temporary measures suffice.

Freeze a versioned architecture/ABI document before corresponding RTL/firmware:
memory map and descriptor layouts, START/DONE/ERROR states, token transport,
single-owner control, hart roles, page/buffer bounds, interrupt acknowledgement,
progress counters, deadlines and safe abort/drain/reset/free order. Model loading
and autonomous execution must have separate ownership phases. A9 validation
access is only permitted after ownership has safely returned.

The existing shared bus assumes fixed-latency device responses. A variable-
latency DDR path must explicitly handle this contract rather than wiring DDR
into a one-cycle scratchpad interface. Current AXI DMA registers are controlled
through the PS master; autonomous transfer access is new work, not an existing
capability inferred from accelerator interrupts reaching the harts.

## G2 — autonomous memory and accelerator control

Implement the selected RISC-V-visible memory/transfer path, bounded queues and
descriptor publication, routing and completion handling. Component tests qualify
interrupt-driven completion; the lean model firmware uses polling with IRQs
masked. Preserve M3
operator payloads and numerical contracts. Verify each direction under stalls,
unaligned/tail cases where supported, page/region boundaries, simultaneous hart
traffic, queue wrap/full/empty, rejected descriptors and transfer errors.

No request may escape owned memory, publish partially written descriptors,
reuse in-flight buffers or free memory still reachable by DMA. Test failure
poisoning, quiescence, timeout, reset during each phase, drain/recovery and
subsequent successful operation. Fail safe if memory ownership cannot be proven
returned. Neither an A9 background copier nor a host-precomputed operator replay
is autonomous model inference.

## G3 — complete bare-metal numerical runtime

Use the accepted compact arrays or an independently verified equivalent
serialization; retain exact model identity and weight tie provenance. Port
M4's range/scaling/epsilon/rounding decisions faithfully, including metadata
work previously performed with A9 float64. Ibex has no floating-point ISA;
any software arithmetic implementation and compiler rounding behavior need
independent qualification. A fixed-point replacement is not presumed exact.

Implement token/position lookup, full model layer loop, all-head causal
attention, LN/softmax/GELU, residual alignment, full vocabulary logits and
lowest-ID greedy selection. Keep the full cache in DDR and bound tile/staging
buffers. Reuse allocation and stream weights without requiring an entire
expanded packet collection in memory. Declare and test the division of work
between the harts and accelerator/transfer owner.

Validate the portable firmware logic with native-host and RISC-V execution
before long physical runs. Export reference fixtures independently from the
immutable M4 reference, never from the new firmware or faulty FPGA outputs.
If exact output cannot be preserved, record the first divergence. A necessary
numeric revision requires a versioned rationale, separate frozen float-quality
requalification and user direction for material quality/scope tradeoffs.

## G4 — progressive qualification

Progress from memory/descriptor tests to actual-checkpoint GEMM/SFPU operands,
complete MLP and multi-head attention, a layer, all layers and full logits/KV.
Check all relevant boundaries, not just coincidental greedy token matches.
Exercise alternate prefill chunkings, cached versus recomputed decode, reset
and reuse, masks/positions, maximum K, vocabulary tails, scale underflow/range
and unsigned probability. Check both hart execution and synchronization.

Run targeted affected M1–M4 local/native/ISA regressions with exactly the
existing four documented ISA expected failures. Do not repeat expensive,
unaffected milestone campaigns. Hardware changes require one regression of the
old configuration; immutable historical evidence remains historical, not a
claim that old binaries contain new RTL. Do not mutate M4's closure auditor or
source pins merely to relabel M5 as unchanged M4.

## G5 — physical implementation

One clean full-overlay build on the final M5 hardware sources:

- 91 MHz, setup WNS >= +0.250 ns, TNS=0 and positive hold slack.
- DSP=0; fully routed, no unconstrained endpoints.
- Final DRC/methodology errors and critical warnings zero; every remaining
  warning reviewed against its actual cone/condition.
- Pin build scripts, source snapshots, tools, reports and bit/HWH hashes. Check
  scripted reproducibility and rebuild only if a later hardware change
  invalidates the accepted artifact.

Do not claim reuse of M3 timing for changed M5 hardware. Firmware-only changes
need not repeat place-and-route when hardware identity remains unchanged.

## G6 — physical correctness and autonomy

On the final hardware/firmware/model identities, run all three original prompts:
one representative prompt produces at least five exact new tokens and the other
two produce at least one exact new token each, with the original EOS policy.
Every observed token and each final full-logit/KV hash must match the independent
M4 quantized reference. One representative run also exports selected
intermediate layer/head/tensor checkpoints. Keep frozen floating-model quality
separate from integer self-consistency. Longer 20-token outputs are useful only
when their elapsed time remains practical; they are not a closure gate.

Prove the ownership claim: inspect the actual host runner and firmware, record
control/transfer counters and demonstrate progress/completion without any A9
in-run tensor or operator service. Host output polling may be stopped while
firmware continues into bounded output storage. Diagnose deadlock/backpressure
without disguising host cooperation as autonomy.

Test reset/reuse, one representative actual control/transfer error and
successful recovery. Check the 1024-position limit, overflow rejection and
cache-length non-mutation with bounded host/firmware tests; the previously
mandatory empty-cache 1024-position physical marathon is removed. Record
physical peak memory and ownership cleanup. Require terminal reports and
successful cleanup/exit, not just progress prints.

## Test cost and evidence invalidation

| Test/evidence | Development policy | Final/invalidation policy |
|---|---|---|
| Address translation, bounds, buffers/queue wrap, IRQ, failure/reset | Fast synthetic directed/random local tests | Rerun after relevant memory/control changes; targeted physical checks on final hardware |
| Real checkpoint operators/tensors and short exact generation | Run after relevant numerical/runtime changes | Full frozen prompt/tensor acceptance on final hardware/firmware |
| Near-limit cache continuation | Use independently verified cache checkpoints to reach boundary cases quickly | Supplemental coverage only; cannot replace constructing full cache from empty |
| New autonomous full 1024 positions | Not required for lean closure | Optional future endurance evidence; bounded limit/rejection tests are mandatory |
| Old M4 CPU + FPGA 1024 marathons | Reuse accepted results and frozen reference evidence | No automatic rerun; only if a relevant component changes and the old evidence is used to qualify that change |
| Full FPGA implementations | Use simulation and initial implementation feedback first | One clean final qualified hardware build; reroute only for hardware/implementation changes |
| Statistical performance | Freeze a small boundary/order/sample count before timing | One warmup plus at least three decode samples and one complete representative run; keep every sample |

Record why any expensive qualification is invalidated before launching its
replacement. A live slow process is a wait, not a reason to restart. Preserve
failed/partial evidence; no reduced context or seeded-cache shortcut may be
relabeled as the final empty-cache full-context proof.

## G7 — honest performance

Create a versioned machine-readable policy before physical performance timing.
Use one warmup plus at least three predetermined cached-decode samples and one complete
representative generation run. Specify prompt/context, reset/residency,
ordering, token delivery, profiling and cold-start sampling before observing
results. Do not launch hour-scale campaigns solely to increase sample count.

Measure physical TTFT, prefill, cached decode, complete generation, tokens/s,
median/p95/range/variability, bytes and memory. Include required work within
the stated boundary: firmware metadata, tensor/packet preparation, transfers,
cache/KV, synchronization, logits, selection and output delivery. Exclude
independent checking. Keep hardware counters separate from overlapping wall
time; do not double-count. Distinguish startup/provisioning from residency.

Compare against the matching M4 quantized same-board baseline only with clear
hardware/workload/environment boundaries. Label historical M4 results when
not newly paired; rerun affected short baselines if required for a fair claim.
Do not repeat unchanged M4 long-context runs merely to obtain a speedup ratio.
Report regressions, failure and overhead honestly. **>=1 token/s is stretch**;
no positive speedup is necessary for functional M5 closure.

## G8 — closure

Deliver `docs/M5_ARCHITECTURE.md`, runtime/ABI material,
`docs/M5_VERIFICATION.md` and `docs/M5_PERFORMANCE.md`, with exact pins,
commands, hashes, raw test/board/build logs, coverage and limitations. Audit
every original requirement against current actual hardware/firmware/results.
Reconcile README/PLAN and make a scoped local milestone closure commit only
after all mandatory gates pass. No M6 work or automatic remote push.

## Initial read-only findings

- Original M5 sketch's int8/200-token scratchpad ring is superseded by full
  M4-equivalent DDR-backed cache. >=1 token/s is user-approved stretch only.
- Board kernel is `6.6.10-xilinx-v2024.1-g916a1f7c7222`; matching build headers
  exist under `/lib/modules/<release>/build`. No memory-helper module has been
  built/loaded for M5 and no boot setting has changed.
- Board RAM reports 503,464 KiB, with 412,968 KiB available at initial inventory.
  Availability is a snapshot, not a reservation. M4 accepted artifacts remain
  preserved and the only unrelated worktree entry is `NA/`.
