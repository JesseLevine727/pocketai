# M4 runtime preparation — not physically qualified

## Frozen handoff

The selected host arithmetic is `ref/gpt2_scaled.py`, pinned by
`tests/m4/scaled_candidate.json` (SHA-256
`ffebd8cd032bfcc92fb248c596a70082e15b3e7f858b15d8ff90eb1a2637b3ee`).
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
OPENBLAS_NUM_THREADS=4 build/m4_venv/bin/python -m scripts.export_m4_pack
```

Export `build/m4_pack_v2` contains 248 arrays, **205,271,824 payload bytes =
195.7625 MiB**. Pack manifest SHA-256:
`87ca19ae6557d071db4a79664bd7ced53dbef78b62ad936f065b063be4e004a8`.
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

`zynq/m4_offload.py` is not implemented yet. It must independently schedule
the frozen model through the M3 GEMM/SFPU interface, preserving common
per-row affine shifts across tiles, all heads, unsigned probabilities, causal
prefix scale selection, exact residual alignment, epsilon correction and the
full-vocabulary output scale. Scalar REQUANT8 scales may require separate
packets; metadata computation is not free. A practical native A9 integer GEMM
baseline is also still required.

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

Reuse the accepted M3 qual3 overlay and hash-check it. Preserve single-owner
DMA, route interlocks, completion/errors/timeouts, cache synchronization, buffer
lifetime and recovery. No M4 overlay programming, board inference, measured
speedup, tokens/s or peak runtime memory is claimed by this pack export.
