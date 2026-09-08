# Startup optimization: bounded reproduction

This is a qualified engineering extension of M5, not the M6 report. The selected
physical campaigns and `audit_m5_startup` pass; a fresh reproduction must meet
the same gates independently. Existing
`m5_context` and earlier directories are frozen; always use fresh `m5_startup_*`
outputs. Do not reuse historical stage symlinks as source snapshots. The commands
below describe the completed qualification procedure. Since the closed audit
also checks complete startup artifact coverage, run later reproduction trials
in a separate workspace/artifact collection; do not append new `m5_startup_*`
builds to this frozen collection or overwrite its evidence.

## Firmware and local checks

From the repository root, with the existing toolchain and fixture environment:

```sh
source env.sh
M5_STARTUP_BUILD=build/m5_startup_reproduce_firmware_v1 \
  M5_STARTUP_VARIANT=local_bias bash scripts/build_m5_startup.sh
python3 -m scripts.check_m5_startup_stack build/m5_startup_reproduce_firmware_v1 \
  --output build/m5_startup_reproduce_firmware_v1/stack_bound_v2.json
python3 -m unittest tests.m5_startup.test_measurement \
  tests.m5_startup.test_runner tests.m5_startup.test_audit
```

The build produces runtime, profile, detail and trace images. It runs the native
full-model/logit/KV, layout, threaded, exact-arithmetic and non-mutating fallback
checks. Repeat once into a second fresh directory and compare all four binaries;
do not enable `M5_STARTUP_ICACHE` for the coherent-mirror hardware. The original
4-KiB-per-hart stacks and local-memory reservations remain mandatory.

The selected firmware is `build/m5_startup_local_bias_v3`, reproduced
at `build/m5_startup_local_bias_repro_v3`. Both include their native logs and
`stack_bound_v2.json`. The v4 evidence selection binds these to the qualified
hardware and completed physical campaigns.
The build includes exact tagged residual-metadata reuse and shared local
projection/bias scratch. It tests both sides of the 1,024-/2,048-column capacity
boundaries, exponent changes, poisoned scratch and wide-bias rejection. The
original full generic row remains the fallback; an exact int16 fit is not a
reduction of model precision. All four builds retain the O2 default; the per-row function
is kept out-of-line to satisfy the unchanged diagnostic code/BSS boundary.

## Qualified instruction and data-path RTL

The selected synchronous-lookahead design preserves the original no-cache fast CPUs,
adding a coherent 64-KiB instruction mirror, direct instruction response/turnover, and
a registered response only for rare non-RAM local instruction accesses.
One sequential word per hart is read ahead using registered addresses; local
writes invalidate both words. The new BRAM controls are synchronous. Hardware
and repeated short-request qualification both pass.
A second coherent 64-KiB data-read mirror gives each hart a dedicated local-read
port. All accepted original RAM writes update both copies with the same byte
enables and block mirror reads for that cycle. Writes, peripheral traffic and DDR
retain the original routes. Data responses use direct-response turnover with a
registered fallback for old shared-bus responses. These two mirrors cost 32
additional BRAM36 tiles in total; this is an explicit resource tradeoff.

```sh
M5_STARTUP_SIM_BUILD=build/m5_startup_reproduce_sim_v1 \
  M5_STARTUP_DIRECT_RETURN=1 M5_STARTUP_REGISTERED_FALLBACK=1 \
  M5_STARTUP_PREFETCH=1 M5_STARTUP_SYNC_LOOKAHEAD=1 \
  M5_STARTUP_DATA_READ_MIRROR=1 M5_STARTUP_DIRECT_DATA=1 \
  bash scripts/build_m5_startup_fetch_sim.sh
python3 -m scripts.test_m5_startup_icache_probe \
  --model build/m5_startup_reproduce_sim_v1/sim \
  --output build/m5_startup_reproduce_probe_v1
python3 -m scripts.test_m5_startup_icache_integration \
  --model build/m5_startup_reproduce_sim_v1/sim \
  --output build/m5_startup_reproduce_memory_v1 --kind memory
python3 -m scripts.test_m5_startup_icache_integration \
  --model build/m5_startup_reproduce_sim_v1/sim \
  --output build/m5_startup_reproduce_accelerators_v1 --kind accelerators
python3 -m scripts.test_m5_startup_router \
  --prefetch --output build/m5_startup_reproduce_router_v1
```

The retained `icache` names are shared test runners; the model marker selects
the no-cache mirror boot and checks. The accelerator runner tests normal and
seven-cycle-delayed AXI. Memory tests include full-word/byte code coherence,
DDR execution, mailbox execution, instruction faults, and abort/drain/remap.

All six `M5_STARTUP_*` feature flags shown above are required in **both** build
commands. The asynchronous lookahead branch and live-address
early-local branch were rejected and must not be deployed. The sync flag
introduces an explicit reset-release bridge and synchronously clocked BRAM-control
state; it is not a warning waiver.

For a physical build, set `PYNQ_BOARD_REPO` to the existing PYNQ board repository:

```sh
M5_STARTUP_VIVADO_BUILD=build/m5_startup_reproduce_pynq_v1 \
  M5_STARTUP_DIRECT_RETURN=1 M5_STARTUP_REGISTERED_FALLBACK=1 \
  M5_STARTUP_PREFETCH=1 M5_STARTUP_SYNC_LOOKAHEAD=1 \
  M5_STARTUP_DATA_READ_MIRROR=1 M5_STARTUP_DIRECT_DATA=1 \
  bash zynq/build_m5_startup_fetch.sh
```

Only a root-level **qualified** `m5_pynq.bit` plus HWH may be staged. A bitstream
inside `m5_pynq.runs` is not acceptance: failed timing candidates retain those
intermediate files. Acceptance requires 91 MHz, WNS >= +0.250 ns, positive hold,
zero total violations, full routing, DSP0 and reviewed DRC/methodology findings.
Do not use the rejected I-cache builds or waive any gate.

Selected hardware: `build/m5_startup_data_finish_v1`, WNS +0.269 ns and hold
+0.008 ns, DSP0, 127.5 BRAM36 tiles. Its actual final checkpoint has seven
individually reviewed existing reset-LUT warnings; see
`build/m5_startup_data_reset_review_v1.log`. A fresh build must recheck its own
timing and actual warning cones, not assume a count-only waiver.
This selected build required a bounded post-route driver-replication/reroute
pass from the `build/m5_startup_data_direct_pynq_v2/m5_candidate.dcp` checkpoint.
That source build's +0.189-ns result was rejected. To reproduce the same finishing
procedure into a fresh output directory, use `zynq/finish_m5_startup_fetch.tcl`
with source build, fresh output, and the generated full guard tail as its three
arguments; an optional fourth argument selects an explicit startup checkpoint.
Generate the tail with `python3 -m scripts.m5_fast_sources <fresh-tail-path>
--emit-finish-tail`. The finisher restores the original final clock uncertainty
and runs the same complete timing/resource/DRC/routing guard before writing the
qualified root bitstream. No intermediate runs-directory bitstream is accepted.

## Physical campaigns

`prepare_m5_startup.py` freezes firmware, overlay and independent reference
identities in a fresh stage. `stage_m5_startup.py` records the board monotonic
clock **before copying**. The runner must receive that clock so copying and
queueing count against the 3,600-second campaign bound and 120-second cleanup
reserve. Use one board campaign at a time through the existing SSH connection.
Provisioning/control/checking are on A9; numerical preparation and inference
remain inside FPGA START-through-completion timing.

The initial diagnostic should include `--full-checks`. Final unprofiled story
qualification uses `--plain --full-checks --repetitions 3 --skip-prefill`; final
science-prefix qualification uses `--plain --repetitions 3 --skip-prefill` and
`--references build/m5_context_science_reference_v1`. The latter still executes
all three cold/warm pairs; it omits only redundant cached-harness short prefill.
Original science/computing/story full requests remain covered by the first
campaign. Record a separate cold diagnostic on each prefix with the detail image.

Never unload the helper or release pages until the usual RETURN/drain succeeds.
Normal cleanup must show owner, allocated pages and PTE DMA all zero. Archive
each `campaign.json`, staging clock, policy, references and actual deployed
runners (`python3 -m scripts.archive_m5_startup_trials`). Slower and failed
experiments are retained alongside selected results.

## Audit and reporting boundary

```sh
python3 -m scripts.audit_m5_startup --campaign build/m5_startup_local_bias_diag_story_v3
python3 -m scripts.audit_m5_context
```

The campaign check above is integrity-only, not a throughput pass. Final evidence
collection requires an explicit selected set of **passing** physical campaigns,
matching simulated/synthesized RTL, qualified hardware, reproducible firmware,
complete cold first-demand accounting and every individual latency gate.
All original prompts, all 50,257 final logits, and the entire valid raw KV are
checked. Initialization includes deferred first-use materialization; prompt
tokens are not counted as output throughput. Provisioning/firmware loading and
post-delivery checks stay separately reported. No full-1024 physical prefill,
endurance, sustained-throughput or arbitrary-content latency claim is made.

The qualified v4 selection is `build/m5_startup_selection_v4.json`. Its story
diagnostic is `build/m5_startup_local_bias_diag_story_v3`; completed final story,
diagnostic science and final science stages use the corresponding
`m5_startup_local_bias_{final_story,diag_science,final_science}_v3` names.
The original collection command was
`python3 -m scripts.audit_m5_startup --collect build/m5_startup_selection_v4.json`.
Do not rerun collection over the qualified evidence: the collector refuses to
overwrite it. Fresh experiments must use new paths and independent evidence.
For this closed release,
`python3 -m scripts.audit_m5_startup` is the read-only chained check; it also
revalidates earlier context evidence and the 27 measurement/runner/audit tests.
