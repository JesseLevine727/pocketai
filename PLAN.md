# PocketAI-T — RISC-V + GEMM Transformer Inference on PYNQ Z1 → Sky130 ASIC

## Mission
Design a fabric-resident AI inference SoC (2× RISC-V cores + int8 GEMM unit +
special-function unit) on the PYNQ Z1 (Zynq-7020, ~212K LUT, 3.6 MB BRAM,
100 MHz fabric). Run GPT-2 124M (int8 weights, int16 activations) with
weight-streaming from DDR3. Then port the *identical* RTL to Sky130 via
OpenLane and deliver a **PPA report** (fabric vs silicon: area, timing,
power, bandwidth) as a first-class deliverable.

## Architecture (target state)

```
 DDR3 ◄─ A9 ─┬─ AXI Stream (weight tiles) ─► ┌──────────────┐
              │                               │  GEMM 16×16  │ int8×int8→int16
              │  AXI slave (control/UART)     │  SFPU: exp/LUT│ (softmax, SiLU,
              └─────────────────────────────► │  RMSNorm dot  │  RoPE, recip)
              │                               │  KV r/w port  │
              │                               └──────┬───────┘
              │        scratchpad ◄──── simple bus ─┤
              │        (activations,   ┌─────┬─────┴─────┐
              │         KV cache)      │Core0│  Core1     │
              │                        │Ibex │  Ibex      │  RV32IMC, in-order
              │                        └─────┴───────────┘
              └─ tokens/UART out
```

Design rules (non-negotiable):
- No Zynq DSP48 in datapath RTL → soft multipliers only (ASIC portability).
- int8/int16 datapath only. No FP anywhere in fabric logic.
- Cores own control flow; units are descriptor-driven (ptr, M, N, K, flags).
- Every unit has a Python reference in `ref/` and a tile-level test vector.

## Repository layout
```
pocketai/
  PLAN.md
  rtl/            # all Verilog (fabric-only, no Zynq primitives)
  ref/            # Python golden models (numpy/torch), shared by sim+board
  sim/            # Verilator testbenches, C smoke tests
  zynq/           # PYNQ overlay .xsa/.bof, Python board code
  asic/           # OpenLane configs, reports, PPA artifacts
  docs/           # PPA_REPORT.md, notes
  tests/          # unit test vectors (hex/csv)
```

## Milestones
Format: Deliverable / Verification (PASS = concrete evidence) / Risks / Agent plan.
Each milestone ends with a `reviewer` PASS against the written criteria before the next starts.

### M1 — Cluster on fabric: bus + Ibex + scratchpad  [~1 wk]
**Status (2026-09-03): M1a + M1b SIM PASS.** (Board bring-up still open: needs the fabric bitstream — Vivado XSA version mismatch with the pre-built board image, PC has Vivado 2025.1; `zynq/m1_boot.py` to be added once the bitstream is built.)
- Core gate DONE: Ibex `small` config (RV32IMC), Verilator, riscv-compliance pinned @844c6660 (upstream CI commit): rv32imc 25/25, rv32im 8/8, rv32i 44/48 (4 fails = upstream expected-fail whitelist), Zicsr 6/6, Zifencei 1/1. C hello_test PASS. Ibex repo: `rtl/ibex-orig` (ignore `rtl/ibex` = CVE2 fork). Compliance runner: `/home/elfo/pocketai/riscv-compliance` @844c6660 (patched for gcc16/binutils 2.47: `_zicsr` in -march, mbadaddr→0x41). Toolchain env: `env.sh` (needs `srecord` at ~/tools/srecord on PATH/LD_LIBRARY_PATH, `VERILATOR_ROOT` bin symlink).
- M1a smoke DONE: `rtl/soc/pa_smoke_top.sv` + `sim/run_smoke.sh` → `PA M1 BOOT`, exit 0.
- M1b cluster DONE (sim): `rtl/soc/pa_cluster_top.sv` (2× `pa_ibex_wrapper` hart0/hart1 over lowRISC `bus` demo arbiter, shared 64 KB RAM, `pa_axi_lite_bridge` AXI4-Lite slave port, mailbox regs @0x12000-0x12008, UART @0x40400). `bash sim/run_cluster.sh` → **PASS**: firmware dual-hart boot + mailbox ping-pong (`P0`, `H1 BOOT`, `P1: PONG OK` in UART log) AND AXI4-Lite self-test through the slave port (3 writes + 3 reads incl. pre-read, all correct → `AXI OK`) while both cores boot and run; sim exits 0 via halt register.
  - TB: `sim/pa_cluster/pa_cluster.cc` (Verilator cc + MemUtil; manual clocking; AXI master in C++).
  - Debug log (M1b postmortem), keep for future TBs:
    1. Arbiter: lowRISC demo `bus` is strictly priority, host 0 first. AxI (AXI bridge) is host 0 on purpose — its transfers are short; if M2+ GEMM/SFPU hosts need fairness, replace with round-robin.
    2. TB clocking: `clock()` must be a FULL cycle (clk=1 eval, clk=0 eval), one eval per edge; a single-toggle clock makes handshake "accept" edges phase-dependent (AW accepted on a falling toggle = silent no-op). Verilator FFs only update on the rising edge.
    3. AXI master in C++: check ready *before* the clock, then clock once to complete the handshake (handshake completes on the edge where valid&&ready are both high); deassert valid after; `axi_idle` (clear all valids + 2 cycles) between transactions; bready/rready held high.
    4. Reset: `IO_RST_N` must be released from cycle 0 in this build; a reset asserted before the first clock edge corrupted core CSR init ("Illegal instruction" on `csrr`). Short SoC reset after 2 idle cycles is safe.
Deliverables:
- `rtl/bus/`: simple 32-bit shared bus (1 arbiter, 2 core masters + A9-side AXI-slave bridge).
- 2× Ibex (PULP), 128 KB scratchpad each side in BRAM, mailbox + interrupt between cores.
- PYNQ overlay: A9 can write scratchpad, reset cores, read results; UART for core console.
- Bare-metal C (riscv-gnu) on cores: hello world, ping-pong across cores via mailbox.

Verification (PASS =):
- Verilator: cores boot a C `coremark-lite`-style test binary; both cores alive; mailbox ping-pong count correct over 10k iterations.
- Board: `python3 zynq/m1_boot.py` prints the same ping-pong result from UART + reads ping count from scratchpad via PYNQ.

Risks: Ibex config flags (pipelined, writeback) vs Verilator — pin exact `ibex.yaml` early.
Bus protocol: keep it 1-cycle req/ack, no outstanding transactions (simplicity > speed).

Prior-art on board (READ-ONLY, do not modify): RV32IM soft core + Q-format Softmax/LayerNorm/GELU split-IP blocks already ran at 100 MHz (`/home/xilinx/tcas_*`); established bring-up pattern = sysfs bitstream + /dev/mem MMIO (see `tcas_*/run_*_board.py`). Board `import pynq` requires login shell (venv auto-activate: `ssh ... 'bash -lc ...'`). Vivado 2025.1 proven on this board — build our own BD, do NOT use PYNQ repo base.tcl (2024.1-only).

Agents:
- `explorer`: locate Ibex build/config options + PYNQ overlay packaging gotchas (read-only, returns file:line notes). [DONE 2026-09-03]
- `implementer`: one run per file-group (bus, then SoC top, then overlay, then bare-metal tests). No two agents on same file.
- `reviewer`: runs the Verilator sim + board script; PASS only on printed evidence.

### M2 — GEMM unit + weight streaming  [~1 wk]
Deliverables:
- `rtl/gemm/`: 16×16 int8 MAC array, int16 acc, double-buffered tile I/O via descriptor FIFO.
- Weight-streaming channel: A9 → AXI Stream → GEMM (tile 64×64), DMA of results to scratchpad.
- `ref/gemm_ref.py` + tile test vectors (incl. negative/edge values).

Verification:
- Verilator: 1000 random int8 tiles match numpy int8 GEMM exactly; timing: measure cycles → report achieved GMAC/s at 100 MHz (expect ≥ ~25).
- Board: `m2_gemm_stream.py` streams a 768×768 projection weight matrix from DDR3, matches NumPy on A9; report tokens/s of pure weight streaming (bandwidth check).

Risks: MAC-array pipeline bubbles — design the feed logic before the multiplier; int8 overflow tests (saturation semantics must match ref exactly — define in docs).

Agents: same trio; implementer splits: (a) MAC array + sim, (b) streaming/AXI side, (c) board script — (a) and (b) touch disjoint files.

### M3 — SFPU: exp/LUT, RMSNorm, RoPE, SiLU  [~1.5 wk — numerics are the grind]
Deliverables:
- `rtl/sfpu/`: exp via piecewise-linear LUT (int16 in/out, document error bound),
  reciprocal approx, dot-reduce for RMSNorm, RoPE sin/cos LUT + MAC, SiLU approx, KV gather/scatter port with head/seq offsets.
- `ref/sfpu_ref.py` golden functions; per-op vector tests.

Verification:
- Verilator per op: max abs error vs numpy over full input range documented in `docs/NUMERICS.md` (target: softmax output error < 2^-8 after renormalization; RMSNorm < 2^-10 rel).
- Board: per-op offload check — A9 sends activation tile, compares unit output vs torch on DDR3.

Risks: fixed-point stability in softmax (running max–subtract), reciprocal convergence. Fix the fixed-point formats in NUMERICS.md *before* RTL — this doc is the contract reviewer checks.

Agents: implementer does ops one at a time in parallel-safe order (each op = own file); explorer mines FLOPS/EdgeLLM public code for prior art on exp/recip formats.

### M4 — Hybrid GPT-2 124M offload  [~1.5 wk]
Deliverables:
- GPT-2 124M int8 (weight-only int8, int16 act) loaded on A9 (llama.cpp or tf-converted).
- `zynq/m4_offload.py`: A9 intercepts ops → dispatch: linear→GEMM, softmax/RMSNorm/RoPE/SiLU→SFPU, glue stays on A9.
- Generate 20 tokens from a fixed prompt; verify against llama.cpp CPU reference (greedy decode, temperature 0) — must match token-for-token.

Verification: PASS = token-by-token match on 3 prompts + per-op speedup table (baseline vs offloaded, saved to `docs/SPEEDUP.md`).

Risks: glue overhead dominating at 100 MHz — instrument early, per-op dispatch table on A9 side.
Agents: implementer (board-side python) + reviewer (runs 3-prompt match). RTL bugs found here get a dedicated fix cycle, not inline edits.

### M5 — Autonomous decode on the RISC-V cores  [~2 wk]
Deliverables:
- Bare-metal runtime on cores: layer loop, descriptor submission, done-interrupt, KV cache management in scratchpad (int8, ~200-token ring).
- A9 role reduced to: feed prompt tokens, collect output tokens via UART.
- `m5_autonomous.py`: end-to-end generation with A9 never touching a tensor.

Verification:
- PASS = autonomous output matches M4 hybrid output token-for-token on 3 prompts; ≥ 1 token/s decode reported (logit: weight-stream bound); 200-token context stable (no cache wrap-around corruption — dedicated stress test).

Risks: KV ring-buffer addressing is the subtlest RTL here; mailbox/interrupt latency stalls cores (add double-buffered descriptors). This is where the project lives or dies — schedule slack here, not in M1.

Agents: parallel fan-out — (a) KV/BRAM addressing + stress tests, (b) bare-metal runtime C, (c) board harness. Strict file ownership per subagent.

### M6 — Sky130 port + PPA REPORT (headline deliverable, not a bonus)  [~1.5 wk + MPW wait]
Deliverables:
- OpenLane config: Ibex cores (published case study as sanity anchor), GEMM, SFPU, RAMs → sky130 SRAM macros.
- Chip top: UART pads, weight-in interface (SPI/QDR or preloaded micro-weights for on-chip demo).
- `docs/PPA_REPORT.md` — the flagship artifact:

| Metric | Zynq fabric (measured) | Sky130 (P&R) |
|---|---|---|
| area (K-LUT → mm²) | from .xsa | OpenLane report |
| max fmax, achieved @100 MHz timing util | measured | report |
| GEMM GMAC/s (sim-timed) | board-measured | sim-timed |
| power (DC estimate vs board watt) | A9+fabric P meas | OpenROAD power |
| bandwidth to weights | DDR3-measured | interface spec |

Plus: per-block table, screenshots, methodology section (reproducible commands).
- MPW submission decision gate at end of M6 (cost ~$200-500/person) — only after PPA table is real.

Verification: P&R converges (no DRC errors), timing met at 100 MHz, PPA table filled with *measured or simulated* numbers only — no estimates.
Agents: implementer (one OpenLane run), reviewer (checks report has evidence for every cell).

## PPA Report = ship gate
The project is "done" only when `docs/PPA_REPORT.md` exists, every number traces
to a command in the report, and `reviewer` PASSes on that evidence.

## Standing rules
- Every milestone: written acceptance criteria above *before* first RTL edit.
- No file touched by two subagents concurrently; parallel work only on disjoint paths.
- Numerical formats (int8/int16 fixed-point, saturation, LUT error bounds) live in `docs/NUMERICS.md` and are the contract between RTL and `ref/`.
- Fabric RTL purity check (no DSP/Zynq-specific primitives) is a reviewer checklist item at every milestone.
