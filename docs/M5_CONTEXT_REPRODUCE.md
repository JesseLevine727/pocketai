# Reproducing maximum-context qualification

This is an M5 performance extension, not the M6 ASIC/PPA milestone or its report.
Read-only verification of the frozen engineering evidence:

```sh
python3 -m scripts.audit_m5_context
```

The audit checks the complete candidate history, preserved failed qualification,
matched original baseline, six final unprofiled last-slot samples, exact tokens/
all logits/full valid K/V, cold initialization accounting, bounded campaigns,
normal DMA release, source/artifact hashes and byte-identical firmware rebuild.
It then runs the entire previous qualification chain and new evidence/measurement
negative tests. Large ignored `build/` assets must be present, as for prior audits;
the repository contains embedded raw reports and hashes, not GPT-2 model blobs
or FPGA bitstreams. The audit does not contact or program the board.

## Fresh firmware and independent references

Use fresh paths. Do not overwrite a qualified build, reference or board stage.
The build requires the existing RISC-V toolchain, M4/M5 fixtures, native baseline
libraries and `build/m4_venv` described by the earlier reproduction documents.

```sh
M5_CONTEXT_BUILD=build/m5_context_masked_repeat_v1 M5_CONTEXT_VARIANT=masked \
  bash scripts/build_m5_context.sh

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 build/m4_venv/bin/python \
  -m scripts.export_m5_context --output build/m5_context_story_repeat_ref_v1 \
  --case story

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 build/m4_venv/bin/python \
  -m scripts.export_m5_context --output build/m5_context_science_repeat_ref_v1 \
  --case science
```

The exporter uses the independently qualified M4 CPU implementation. It repeats
the selected fixture prompt to 1022 tokens, exports raw cache arrays, and computes
two real greedy continuations. Each export has a ten-minute alarm; recorded
story/science preparation took about 79 seconds each. This is test-oracle work,
not host inference in the measured FPGA implementation.

The build checks all three zero-padded 64-KiB firmware images, unresolved symbols,
ISA attributes and linker regions. It runs legacy attention/numerical tests,
bound consumer-cache tests through 1024, threaded full-model checks, and targeted
score-product/metadata/local-score/combined-score tests. Fresh final and
reproduction `.bin` files must compare byte-for-byte. Generated C is derived
from hash-pinned prior sources; none of the qualified earlier sources is edited.

## Prepare and stage short board campaigns

```sh
python3 -m scripts.prepare_m5_context_ready \
  --stage build/m5_context_story_repeat_v1 \
  --build build/m5_context_masked_repeat_v1 \
  --references build/m5_context_story_repeat_ref_v1 \
  --repetitions 3 --full-checks

python3 -m scripts.stage_m5_context \
  --stage build/m5_context_story_repeat_v1 --upload-seed
```

Prepare science analogously with its reference, three repetitions and no
`--full-checks`. `--upload-seed` ensures each repeat uses its own exported prefix.
The recorded story campaigns reused the byte-identical original story seed;
science explicitly uploaded its own. Staging reuses immutable large assets from
`/home/xilinx/pocketai_m5_context_ready_diag_v1` on `xilinx@10.0.0.223`. If this
baseline stage is absent, provision its verified model/layout/fixtures/qualified
overlay and frozen harness first; do not substitute another model or overlay.

Staging prints `CAMPAIGN_START` from the board's monotonic clock **before** any
copies and saves it in local `staging.json`. Queuing time is not subtracted.
Run only one board campaign at a time. Do not take over an existing helper or
another process's arena. In an interactive root SSH shell, with no stored
credentials:

```sh
cd /home/xilinx/pocketai_m5_context_story_repeat_v1
/usr/local/share/pynq-venv/bin/python3 m5_context_ready_run.py \
  --stage . --campaign-start BOARD_MONOTONIC_TIMESTAMP
```

The unchanged sweep harness enforces a 3600-second campaign cap including
staging, setup, checks and cleanup, with 120 seconds reserved for normal drain.
Cold cases allow 240 seconds, warm cases 120 seconds, full requests 180 seconds.
It checks overflow before accepted requests and verifies each result against its
policy-bound independent oracle. All final cases must run; no skip is a pass.
The final JSON must show PASS, `within_budget`, normal module unload and reopened
owner/allocated-pages/PTE all zero. Never force-unload or free undrained pages.
Retrieve `campaign.json` after completion. A rerun is new evidence, not a silent
replacement for this closure's fixed campaign paths.

Use `--diagnostic` only for phase exploration: it stages `m5_detail.bin` and
enables instrumentation. Primary qualification stages `m5_profile.bin` with
profiling **disabled**. Full application requests use `m5_runtime.bin`.
`--baseline` accepts only a plain cached pair with the frozen original firmware;
it retains the actual preceding FPGA-produced KV but has no derived-cache checks.

## Timing and cache boundary

Each pair restores only the independent raw past-1022 seed. A9 invalidates the
derived-cache marker, but does no transposition, maxima, quantization or smoothing
preparation. The first FPGA forward performs and pays for all of that work.
The next forward retains its real KV/derived DDR state, uses its actual greedy
token, and appends the final position. It is not a replay with future state.
Every new repetition starts from the original independent seed again.

`host_request_through_delivery_seconds` measures START through safe DMA ownership
return and token copy. It includes control/return overhead, not model provisioning,
seed restoration, firmware loading or correctness hashing. Those costs stay in
campaign time. `model_seconds` is the nested FPGA execution interval. The console
`SWEEP EXACT PASS ... seconds` value is case elapsed time including checks, **not**
delivered token latency. Full-request latency additionally includes its actual
short prompt prefill; it is not interchangeable with resident last-slot decode.

The final-slot test reaches 1024 valid KV positions. It does not establish a
cheap 1022-token cold start, sustained throughput beyond capacity, arbitrary-
content worst-case latency, Linux tail latency, energy, or a power-on guarantee.
The original traffic/engine counter limitations in `M5_SWEEP_REPRODUCE.md` still
apply. No speed claim is derived from profiling overhead subtraction.
