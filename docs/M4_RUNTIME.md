# M4 runtime — physical qualification in progress

## Frozen handoff

The selected host arithmetic is `ref/gpt2_adaptive.py` extending the immutable
scaled v2, pinned by `tests/m4/adaptive_candidate.json` (SHA-256
`a8d80d03c1aacc8a40f0f84962acd4033f0a1afb1343fd9e1ab0e9c50d0c397d`).
See `M4_NUMERICS.md` for every activation/weight/epsilon boundary and A9 cost.
Model quality and generation evidence are in `M4_VERIFICATION.md`.

`scripts/export_m4_pack.py` emits a compact serialization, independently reloads
every array with hashes, and compares **every weight byte and metadata element**
against the frozen reference. `ref/m4_model_pack.py` is a NumPy-only read-only
mmap reader: no Torch, Transformers, safetensors or PYNQ import on the board.
Its operation inventory is exactly 49 linear maps and 25 normalizations.

Weights use `[ceil(N/16), K, 16]` signed-int8 tiles, with zero column-tail
padding; tests compare the complete B byte layout with the independent M3
packet packer, including K=3072 and N=50257. Input A row padding must still be
handled per the M3 descriptor. Scales/biases/smoothing metadata are float64;
GEMM payloads remain int8. Embeddings and positions are int16.

```bash
OPENBLAS_NUM_THREADS=4 build/m4_venv/bin/python -m scripts.export_m4_pack --adaptive-v3
```

Export `build/m4_pack_v3` contains 248 arrays, **205,271,824 payload bytes =
195.7625 MiB**. Pack manifest SHA-256:
`d2aafeffd3e4b8a134b8e48796a1b0cf8f296a3bd150b79f07e2de037fae8fd6`.
All array contents match the preserved v2 pack; only identity/export provenance
changes. V3's adaptive units belong to the runtime, not different weights.
Output directories cannot be overwritten. The eventual board staging manifest
must pin this manifest and the exact overlay/code too; a candidate-ID field
alone is not proof that arbitrary incoming pack contents are authentic.

## Memory budget, not a peak-memory measurement

The board inventory reported 491 MiB RAM, approximately 387 MiB then available,
and only about 16.6 MiB free CMA. The 195.8-MiB pack is ordinary file-backed
DDR, **not** a CMA allocation. A full 1024-token, 12-layer int16 K/V cache needs
37,748,736 bytes = **36 MiB**. Both still leave room on paper for bounded
working buffers, but actual PYNQ/runtime peak RSS, faults, CMA and swap behavior
must be measured. File payload size is not measured peak residency.

Use bounded prefill blocks and reusable tile/SFPU buffers. A maximum M3 GEMM
packet is 16x3072 A bytes plus 3072x16 B bytes = 98,304 bytes. Maximum SFPU
input is 3x3072 32-bit words = 36,864 bytes; maximum output is 12,288 bytes.
The full model does not require a hundreds-of-MiB prepacked CMA allocation.
Precomputed tiled weights are immutable ordinary DDR; required copies, A9
metadata, DMA/cache maintenance and result assembly belong inside delivery
timing. Initialization/packing and cold page-in costs must be reported separately.

## Remaining integration

`zynq/m4_offload.py` now independently schedules
the frozen model through the M3 GEMM/SFPU interface, preserving common
per-row affine shifts across tiles, all heads, unsigned probabilities, causal
prefix scale selection, exact residual alignment, epsilon correction and the
full-vocabulary output scale. Scalar REQUANT8 scales may require separate
packets; metadata computation is not free. The matching CPU baseline uses
native A9 integer kernels. Host checks match all 196 layer-boundary
comparisons across 13-token prefill plus four cached tokens, all logits/KV,
and all 60 frozen generated tokens. The physical CPU runtime now passes all
four tensor cases and all three 20-token generations. The FPGA passes the same
four cases and all 60 generated-token/logit/KV checks. Driver controls and
physical M1/M2/M3/M1 compatibility pass. Full-context board checks remain.

The runtime preallocates K/V, stable per-token K8 and K scale metadata, totaling
**48,365,568 bytes (46.125 MiB)** at capacity 1024. Int16 K/V alone is the
36-MiB budget above; the extra derived cache is explicitly counted. Token blocks
are at most 16, model weights stay mmap int8, and all planned arithmetic is
dispatched through the chosen GEMM/SFPU backend. There is no floating GEMM or
model-reference import in the scheduler. A9 still performs declared metadata
range scans and epsilon correction.

`zynq/m4_driver.py` allocates **110,592 CMA bytes** (98,304 TX + 12,288 RX),
reuses length-specific views, preserves padding/unsigned probabilities, checks
descriptor acceptance, DMA byte counts and completion tags/counts, and prevents
buffer rewrites after a failed operation. Reset/restart is bounded by deadlines;
failed DMA reset retains allocations. Route changes require idle engines.
The physical driver control test now passes both busy-route directions,
descriptor rejection, a real missing-producer DMA timeout, refusal to rewrite
failed-transfer buffers, reset/restart, and K=3072/N=13 wide GEMM after recovery.
`build/m4_driver_board_control.json` records the exact driver source and checks.

`tests/m4/export_runtime_fixtures.py` exports from the **frozen independent
reference**, not this runtime: four tensor cases, all 60 generation logit/KV
hashes, and the full 1024-token stress. `zynq/m4_run.py` checks those delivered
tensors and hashes. Diagnostic operator cross-checking is optional and outside
any performance claim. Its elapsed time includes checking and must not be
reported as model performance.

Initial source/pack/fixture/overlay bundle: `build/m4_runtime_stage.le05p1bc`,
manifest SHA-256 `cfff45881ba6ff1937bf809ac865a27647ba8432f95e318c3dfa43eb9c5b41e1`.
Physical staging uses the fresh owned directory
`/home/xilinx/pocketai_m4_runtime.ptyLjY`. Every staged file is hash-checked before
programming; the runtime independently checks the accepted pack and overlay.

The initial scalar-bridge board run passes **all four tensor cases** (single,
story, science, computing) with exact layer/logit/KV checks. Its generation
phase was intentionally interrupted after a verified batching improvement;
the old log and partial JSON remain in `build/m4_runtime_board_cpu.log` and
`build/m4_runtime_board_cpu_partial.json`. The latter retains its original
`RUNNING` status because that old runner did not catch KeyboardInterrupt. It
is **not** a completed generation/performance PASS. The process was explicitly
sent SIGINT, its traceback/output preserved, and its terminal SSH handle polled.

The replacement batches dynamically scaled columns through equivalent M3
AFFINE packets, as proved in `M4_NUMERICS.md`. It passes 24 host unit tests,
all 196 full-model tensor boundaries, logits/KV and 60 frozen generated tokens.
This avoids spending most A9 time dispatching thousands of tiny column calls.
Short-context physical model qualification of this replacement passes; full-
context checks are still required. No inference
speedup is claimed from the dispatch-count reduction alone.

Current bundle: `build/m4_runtime_stage.l3_ox1tq`, manifest SHA-256
`99897c20ad4c7cfa1a47507a94b34c1f0a72c85091435f7628ef54916e307fe7`,
staged at `/home/xilinx/pocketai_m4_runtime.LrxYKW`. The accepted model pack,
reference fixtures, C kernels and M3 overlay are unchanged.

The same runtime also passes a host-native 64x16-block full-context run:
all 1024 positions, exact final logits and every KV value, followed by an
overlength rejection without mutation. Evidence:
`build/m4_runtime_host_boundary.json`. Host output uses the shared runner's
`M4 BOARD` log prefix, but its backend explicitly says portable C: this is
**host evidence**, not a physical ARM/FPGA pass.

Performance/boundary bundle: `build/m4_runtime_stage.mug8tsv8`, manifest
`e711e00ecac9cb7756b116fe8b41517224b2286afad8d13e9b13ad61c3a91cfa`,
remote `/home/xilinx/pocketai_m4_bench.lkETvP`. The model scheduler, driver,
ARM binaries, pack and overlay are identical to the correctness bundle; only
the benchmark helper and frozen sampling policy are added. The sequenced
physical workflow runs the paired benchmark, then separate CPU and FPGA
1024-context checks. It stops on any failure; it never reuses another active
process's DMA ownership or overwrites old result files.

The native host libraries required by the runtime/benchmark unit tests can be
built before `unittest` discovery:

```bash
gcc -O3 -Wall -Wextra -Werror -shared -fPIC zynq/m4_cpu_gemm.c -o build/m4_cpu_gemm_host.so
gcc -O3 -Wall -Wextra -Werror -shared -fPIC zynq/m4_cpu_sfpu.c -lm -o build/m4_cpu_sfpu_host.so
OPENBLAS_NUM_THREADS=4 build/m4_venv/bin/python -m unittest discover -s tests/m4 -v
```

The benchmark boundary is pre-tokenized IDs through greedy ID delivery, not
a text/network service. Tokenizer assets and host tokenization are independently
qualified in G1; text conversion is not included in resident model timing.
`prefill` supports up to the remaining 1024-position context; `generate`
conservatively requires prompt length plus requested output count <= capacity.
Generation is batch one, lowest-ID greedy ties, with EOS treated as an ordinary
token under the frozen fixed-20 policy.

### Deployment source and license preflight

`scripts/verify_m4_deployment.py` now rechecks the **actual bytes** of all ten
pinned model assets (checkpoint, configuration, tokenizer/vocabulary/merges,
license and semantic source), all 248 packed arrays, all 396 independent tensor
files, frozen source/calibration/selection identities, and exact bit/HWH.
Checking a manifest's identity alone does not prove that its asset files still
match it. The verifier is read-only and does not download, repair, evaluate
models, program hardware or alter quality thresholds.

```bash
OPENBLAS_NUM_THREADS=4 build/m4_venv/bin/python -m scripts.verify_m4_deployment --output build/m4_deployment_preflight.json
```

The staging helper invokes this preflight before creating a future bundle and
copies the small model/tokenizer/configuration/license assets plus the receipt
into `model_identity/`. It does not copy the 548-MB original checkpoint to the
board or expand its weights: inference still loads only the accepted compact
pack. A newly tested host bundle, `build/m4_runtime_stage.ryasqcbb`, passes all
676 staged-file hashes and has manifest
`730b67083e2898e485c895519823ea34b1b792ef6b5994ee253e9d4941afc8ac`.
It has **not** replaced the active board bundle. Runtime, driver, model arrays,
native libraries, fixtures and overlay are unchanged, so the ongoing physical
measurements are not restarted or relabelled as using this later staging helper.

### Native CPU kernel preparation

`zynq/m4_cpu_gemm.c` and `ref/m4_cpu.py` implement exact tiled int8 GEMM with
int32 outputs. Portable C passes 20 host cases; the **actual physical A9 NEON
backend** also passes all 20, including full-range positive/negative/cancellation,
K=3072, N=50257 and row/column tails. The NumPy int64 oracle converts B in
128-column chunks to bound reference memory on the board. This is a native
kernel check, **not a complete CPU model or an inference performance result**.

Board GCC 11.2.0, NumPy 1.21.5; build flags:
`-O3 -Wall -Wextra -Werror -shared -fPIC -mcpu=cortex-a9 -mfpu=neon`.
The test ran over SSH without sudo in the newly created owned temporary
directory `/tmp/pocketai_m4_cpu.xh9AfQ`; no FPGA programming or board-global
changes were made. Evidence is `build/m4_cpu_gemm_arm.json`, SHA-256
`b5b1bec44d945f1db4fc535ccc4e2f58a6e6f8ef8d5fc34afe8c7057885756eb`.

`zynq/m4_cpu_sfpu.c` and `ref/m4_cpu_sfpu.py` provide the exact M3 SFPU
packet arithmetic for the CPU baseline. Both host and physical A9 pass 140
adversarial cases covering all seven operations and the full **3,472 immutable
accepted M3 SFPU packets**. Host undefined-behavior sanitizer replay also
passes all 3,472 packets. The integer LayerNorm square root uses an FP seed
followed by exact emulated 80-bit comparisons; final results do not depend on
seed rounding or unavailable ARM `__int128`. CPU use of an FP seed is not a
floating-point fabric or a change to the quantized result.

Physical full-corpus evidence: `build/m4_cpu_sfpu_arm_m3vectors.json`, SHA-256
`d66b7511fd697da8b7a4b537a9b16dd130fa334325cfe4eca8ec01e82827396b`.
GCC flags are as above with `-lm`; this is operator correctness, not a measured
model speedup. Subsequent physical model checks use the exact M3 overlay.

Reuse the accepted M3 qual3 overlay and hash-check it. Preserve single-owner
DMA, route interlocks, completion/errors/timeouts, cache synchronization, buffer
lifetime and recovery. Pack export alone does not prove board inference or
memory fit. Initial short-context physical measurements and their precise
scope are now recorded in `M4_VERIFICATION.md`; full-context peak-memory
qualification and fair repeated performance remain required.
