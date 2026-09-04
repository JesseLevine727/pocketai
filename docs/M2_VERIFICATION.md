# M2 verification record — COMPLETE / PASS

M2 is **closed — PASS (2026-09-04)**. Numerical/protocol simulation, active
two-hart integration, M1 regression and ISA suites, two clean 95 MHz FPGA builds,
and the exact-overlay physical-board acceptance workload all passed. The board
run used `m2_qual2`; the reported bitstream/HWH hashes match the accepted build.
README.md and PLAN.md now record M2 closure. M3 has not started.

## Acceptance status

| Gate | Evidence | Status |
|---|---|---|
| Numerical contract | `NUMERICS.md`, int64 NumPy reference, five unit tests | PASS |
| Randomized RTL/reference comparison | 1000 random + 7 directed tiles; seed `0x50414d32` | PASS |
| Protocol and lifecycle | Descriptor bounds/byte enables, queue overflow, bad keep/TLAST, reset and abort during load/compute/output, output stalls, IRQ assertion/clear | PASS |
| Integrated GEMM | AXI descriptor, signed partial tile, output/padding, counters, scratchpad write/read while both harts execute | PASS |
| M1 local regression | Bus/mailbox, boot, 10000-round two-hart workload, fatal-warning lint | PASS |
| Pinned ISA suites | 84 passing tests + four named expected failures | PASS |
| Final 95 MHz implementation | +0.499 / +0.486 ns WNS, TNS 0, hold +0.018 ns, fully routed, DSP 0, DRC errors 0 | PASS |
| Clean reproducibility | `m2_qual1` and `m2_qual2`, identical resolved source trees | PASS |
| Physical-board test | `m2_qual2`: M1 workload + 16x768x768 projection; 12288 int16 results and 6144 shared words exact | PASS |
| Warning review and artifact hashes | Final reports reviewed; DDR/DMA/reset/console checks passed; exact board artifact hashes matched | PASS |

## Qualified design

See `M2_ARCHITECTURE.md` for the register/descriptor ABI, buffering, error
recovery, stream layout, shared-memory layout, and counter semantics.

The engine accepts logical tiles up to 16x16 with K up to 768. A 4x16 physical
array contains 64 portable soft signed-int8 multipliers with 25-bit accumulators.
It processes rows in groups of four and saturates once to int16. Two independent
tile slots overlap input, computation, and output. No vendor primitive is
instantiated in the accelerator RTL.

The board overlay retains the two M1 Ibex harts and shared-bus memory map,
adds accelerator registers at `0x43c13000`, and connects 32-bit payload streams
to AXI DMA at `0x40400000`. DMA accesses DDR3 through PS HP0; A9 publishes
results to the existing shared scratchpad at `0x43c04000..0x43c09fff`.

The qualified clock target is exactly 95 MHz. +0.500 ns setup margin and
100 MHz are stretch targets. A preliminary revision reported +0.266 ns setup,
0 TNS, +0.024 ns hold, zero DSP, and complete routing. That revision is not
final qualification evidence: review subsequently corrected descriptor
truncation, associated counters with the completed slot, and removed a
duplicate primary-clock constraint by configuring Clocking Wizard for an
internally driven input (`PRIM_SOURCE=No_buffer`). The final design must retain
the PS-generated clock's vendor-specified 0.300 ns input jitter.

The first clean build with the corrected clock model (`build/m2_clean1`)
finished fully routed at +0.035 ns setup WNS, zero TNS, and +0.013 ns hold;
it failed the required +0.250 ns setup margin. It used 23508 LUTs, 18090 FFs,
42 BRAM tiles, and zero DSPs. The critical path chained the two multiplies in
`M*N*K` from a staging register to the slot's MAC-count register. The next
revision captures M*N on submission and calculates (M*N)*K in the next cycle,
during input loading. This changes no numerical result or compute cycle count.

With that change, the original routing directive reached +0.214 ns, still below
the gate. Comparing routing on the same placed checkpoint showed +0.359 ns
setup / +0.012 ns hold using `route_design -directive Explore`, versus
+0.254 / +0.022 ns using targeted pre-route replication. Both were fully routed
and DSP-free. The build now uses the `Explore` routing directive, followed by
the existing Explore/AggressiveExplore physical optimization. These are timing
experiments, not final board qualification; the final clean builds also include
the subsequent abort/drain recovery fix.

Those two clean builds (`m2_final1`, `m2_final2`) reached +0.069 and +0.349 ns
respectively; only the second passed. Both identified the BRAM-to-multiplier
path as critical, so this pair does not establish repeatable closure. The next
revision registers the selected A/B operands before the soft multiplier,
separating BRAM/mux delay from arithmetic. It adds one cycle per row group
(four per full tile) without changing numerical results or steady-state MAC
throughput. Final qualification uses this operand-pipelined revision.

## Final implementation evidence — 2026-09-04

Both commands completed successfully with Vivado 2025.1 and `PA_CLEAN=1`:

```bash
export PYNQ_BOARD_REPO=/home/elfo/Documents/MASc/pynq-z1-llm-accel/external/board_files
M2_VIVADO_BUILD_DIR="$PWD/build/m2_qual1" PA_CLEAN=1 bash zynq/build_m2.sh
M2_VIVADO_BUILD_DIR="$PWD/build/m2_qual2" PA_CLEAN=1 bash zynq/build_m2.sh
```

| Final routed metric | `m2_qual1` | `m2_qual2` |
|---|---:|---:|
| Fabric clock | 95 MHz | 95 MHz |
| Setup WNS | +0.499 ns | +0.486 ns |
| Setup TNS / failing endpoints | 0 / 0 | 0 / 0 |
| Hold WNS | +0.018 ns | +0.018 ns |
| Hold TNS / failing endpoints | 0 / 0 | 0 / 0 |
| LUTs | 23272 (43.74%) | 23263 (43.73%) |
| Registers | 20157 (18.94%) | 20157 (18.94%) |
| BRAM tiles | 42 (30%) | 42 (30%) |
| DSPs | 0 | 0 |
| Routable / fully routed nets | 37961 / 37961 | 37945 / 37945 |
| Routing errors | 0 | 0 |
| DRC errors / critical warnings | 0 / 0 | 0 / 0 |
| Methodology errors / critical warnings | 0 / 0 | 0 / 0 |

Both final timing summaries report zero for all twelve `check_timing` checks,
including missing clocks, unconstrained endpoints, missing I/O delays, multiple
clocks, generated-clock errors, and loops. The PS clock is 100 MHz and the MMCM
output is 95 MHz; the vendor PS input jitter remains 0.300 ns. The artificial
implementation uncertainty is removed only for the final actual-clock reports.
Neither build meets the optional +0.500 ns stretch target; neither claims
100 MHz qualification.

The two builds used separate projects, source exports, and logs, with no
incremental reuse. Their resolved source trees compare byte-for-byte equal.
Implementation results need not be bit-identical: both independently satisfy
the same acceptance limits. Reports are in each build's `reports/` directory;
complete logs are `build/m2_qual1_console.log` and
`build/m2_qual2_console.log`.

## Artifact hashes

SHA-256 values below identify the accepted artifacts. `m2_qual2` passed the
physical-board test; its bitstream and HWH hashes appear in that test's log.
`m2_qual1` independently passed the clean implementation gate but was not
separately programmed for M2 board acceptance.

| Artifact | SHA-256 |
|---|---|
| `m2_qual1/m2_pynq.bit` | `2d53bfe13fa5577ab70c28b98d323dc5928ce98d1e0107a422f464826835ec7f` |
| `m2_qual2/m2_pynq.bit` | `f196e92c4509ebad977521bf40a8cd30b0f3f131fbfe199515d6e0ff6600fa03` |
| Both builds' `m2_pynq.hwh` | `f77dfe909dd8a3d7d0266d4326c05ceb1eb97a0182bbd4d67acf25a96833c390` |
| `m2_qual1/m2_pynq.xsa` | `10dd7a16f4f472f4a63d8f5d80cd26605307a76863a7ef72dc99583101e0db74` |
| `m2_qual2/m2_pynq.xsa` | `66ed4d98e84cf2b45af59dd4e494e9d23693445cd5b376fe1060f9da76510934` |
| `m2_qual1/m2_pynq_final.dcp` | `be63516ef22683a91d39ad306ed2990da9c0dd69b8b77a0d886b4c2eef7d89d7` |
| `m2_qual2/m2_pynq_final.dcp` | `4e04af946be0d78a1d8e618efe772a768e97ce0a8df70f707cff056aca412a0d` |
| `m2_qual1/reports/m2_timing_summary.rpt` | `5c3f61c9433e43060f16fa86a57fe0bcca589325c279473fa50709e65a3eddbe` |
| `m2_qual2/reports/m2_timing_summary.rpt` | `064d4695f6117d58b5b40533335c09db1e36b4ad11d406d40e86fd9828b2f486` |
| `m2_qual1/reports/m2_drc.rpt` | `f6e2d783ae882f1fd7eae688221cb771aaa8d1645e221b5a87b4113581b7570b` |
| `m2_qual2/reports/m2_drc.rpt` | `b446f13d26418ce1e2a5ccb0b514cccd5f9ef74937d7ad7784efd7e1da80c129` |
| `pa_cluster/cluster.bin` | `1c877c4ccf82060ae3dd71645fe5e1892215b03d95fad1edb2e020ca6f85dcc0` |
| `m2_local_operand.log` | `6e5293cef1ade4826612cc4274561cbdbf1cf07331ce5888f8b70cb5f709b10d` |
| `m2_compliance_final.log` | `5817c84e5fc0e1ed53c24bd431967c41289900ca2f88a73a48c49299f2656378` |
| `m2_qual2_board.log` | `fb3e16f7a10bb33f743da6842a819c6bb7741d248f9fc47c4fc6d397d48840e7` |

Artifact paths in the table are relative to `build/`. The source-level anchors
are `rtl/gemm/pa_gemm.sv` SHA-256
`61d2ae67b5664657fbfb6d51a4b699011bfd479b1ba3ccfdc51ca174c8215b31`,
`zynq/build_m2.tcl`
`645f51f6affaa383f523167a72f82115b8a0c6f4fe2e18ec1e9e8af3a524149f`,
and `zynq/build_m2.sh`
`be3690006bb2293c33a9efcb29b1e90aa8dfa14c6202d76e83a6ab68006f42b4`.
The board runner sources are `zynq/m2_run.py`
`10141df9e95ed52fd4768da3093b07d327874ec851e767f4be5ebe54092a7bd6`
and `zynq/run_m2_board.sh`
`9a10aba1e1008fc176839ff281a5585b43f9e7a3955808a1cefbb34f10a8a8f1`.
For either build, running
`rg --files -0 | sort -z | xargs -0 sha256sum | sha256sum` inside
`resolved_sources/src` gives
`9ef7f81cbdb4a020ac9ef51474a7afb21da6b500eb30f0a0b7ed63b9a71a02ec`.

## Local verification

Commands from the repository root:

```bash
PA_CLEAN=1 bash sim/run_m2.sh
PA_CLEAN=1 bash scripts/run_compliance.sh
```

Recorded local output for the operand-pipelined revision
(`build/m2_local_operand.log`):

```text
M2 GEMM RTL PASS cases=1007 random=1000 seed=0x50414d32 cycles=2313002
M2 CLUSTER GEMM PASS
M1 RESULTS OK count0=10000 count1=10000 msg0=468aad43 msg1=85558c0a work0=29c4c2c2 work1=a3e316ec
M1 LINT PASS
M1 LOCAL PASS
M2 LOCAL PASS
```

Recorded compliance output (`build/m2_compliance_final.log`):

```text
M1 COMPLIANCE PASS rv32imc=25/25 rv32im=8/8 rv32i=44/48+4-xfail rv32Zicsr=6/6 rv32Zifencei=1/1
```

The four expected failures remain the explicit M1 upstream exceptions:
`I-EBREAK-01`, `I-ECALL-01`, `I-MISALIGN_JMP-01`, `I-MISALIGN_LDST-01`.
Dependency revision/patch integrity is checked by `scripts/check_deps.sh`.

Random tests cover M/N=1..16 and K choices from 1 through 768, including
packing and memory-boundary sizes. Directed tests include -128 times -128 at
full 16x16x768, both saturation signs, zero inputs, and a large partial sum
that later cancels to zero. Input padding is deliberately poisoned, and every
output word including padded columns is compared exactly. Input gaps and
output backpressure are deterministic; the source holds valid data when
stalled. Prolonged output stalls check stable data, keep, valid, and last.
Two queued descriptors with different dimensions verify counter/tag association.
The standalone portion of the aggregate run also holds input valid
for 32 cycles before submission, verifies that ready remains low without a
descriptor, and checks that the held first word is accepted exactly once.

The generated vector file's SHA-256 is
`8e11618ae6c4eb14dfbc315f0a18134d0c77c12c65b7591368d2f4b9a0ec72ec`.

## Tools and dependencies

| Dependency/tool | Version |
|---|---|
| Ibex | `34b0705760ef3dfa00e99637432473d2be8f22f3` + tracked M1 patch |
| riscv-compliance | `844c6660ef3f0d9b96957991109dfd80cc4938e2` + tracked local patch |
| Vivado | 2025.1, build 6140274 |
| Verilator | 5.020 |
| FuseSoC / Edalize | 2.4.6 / 0.6.8 |
| RISC-V GCC | 16.1.0 (`g6afcc4f6d`) |
| Host Python / NumPy | 3.12.3 / 2.4.3 |
| Board Python / NumPy / PYNQ | 3.10.4 / 1.21.5 / 3.1.1 |

## Implementation and board reproduction

```bash
export PYNQ_BOARD_REPO=/path/to/board_files
PA_CLEAN=1 bash zynq/build_m2.sh
bash zynq/run_m2_board.sh
```

`M2_VIVADO_BUILD_DIR` selects an independent project/output directory.
`PYNQ_HOST` defaults to `xilinx@10.0.0.223`; `PYNQ_M2_DIR` selects the remote
staging directory. Board programming uses SSH and the PYNQ Python environment
with sudo, without JTAG. `M2_BOARD_LOG` selects a separate acceptance log.
The board runner first loads the M1 firmware on the M2 overlay, then reloads
the identical overlay for the projection. It prints bitstream and HWH hashes.

To repeat acceptance of the already-built overlay above, run from the repository root in
an interactive terminal and enter the board's sudo password when prompted:

```bash
M2_VIVADO_BUILD_DIR="$PWD/build/m2_qual2" \
M2_BOARD_LOG="$PWD/build/m2_qual2_board.log" \
bash zynq/run_m2_board.sh
```

Do not substitute an older exploratory overlay in `build/m2_pynq`. The board
log must contain both M1 and M2 PASS markers and match the accepted hashes.

The authenticated run exited successfully. Remote SHA-256 checks for the
bitstream, HWH, and firmware matched the values above. An earlier attempt had
stopped before programming because sudo authentication was unavailable; the
recorded board log now contains the successful authenticated rerun.

The projection uses 48 descriptors, M=16, N=16, K=768, in pairs occupying both
slots. Expected totals are 9437184 MACs, 154752 compute/pack cycles,
1179648 input bytes, 24576 output bytes, and 6144 exact output/shared words.
The runner records observed transfer time, A9 publication time, end-to-end
latency, and accelerator and end-to-end GMAC/s separately.

## Physical-board evidence and measured performance

Recorded output from `build/m2_qual2_board.log` (terminal control characters
and the authentication prompt omitted here):

```text
M1 console:
H0 READY
H1 READY
M1 results: count0=10000 count1=10000 msg0=468aad43 msg1=85558c0a work0=29c4c2c2 work1=a3e316ec
M1 BOARD PASS elapsed_s=0.048
M2 artifact bit_sha256=f196e92c4509ebad977521bf40a8cd30b0f3f131fbfe199515d6e0ff6600fa03 hwh_sha256=f77dfe909dd8a3d7d0266d4326c05ceb1eb97a0182bbd4d67acf25a96833c390
M2 transfer: input_bytes=1179648 output_bytes=24576 mm2s_s=0.039558 mm2s_MB_s=29.821 effective_MB_s=10.883
M2 shared-memory publication: A9_copy_s=0.003049 bytes=24576
M2 performance: cycles=154752 macs=9437184 workload_s=0.110649 accelerator_GMAC_s=5.793 end_to_end_GMAC_s=0.085
M2 BOARD PASS projection=16x768x768 descriptors=48 pairs=24 result_i16=12288 exact_words=6144 shared_exact_words=6144 shared_offset=0x4000
```

A separate post-test configuration readback, `from pynq import Clocks;
print(Clocks.fclk0_mhz)`, returned `100.0` MHz using the runner's login-shell
and `sudo -E` environment. This matches the implemented MMCM reference for the
95 MHz fabric clock; it is configuration readback, not an oscilloscope measurement.

| Measurement | Observed value |
|---|---:|
| Exact projection outputs | 12288 int16 values |
| Exact shared-scratchpad readback | 6144 words / 24576 bytes |
| Compute/pack cycles | 154752 total; 3224 per descriptor |
| Useful MACs | 9437184 |
| Accelerator throughput from counters at 95 MHz | 5.793 GMAC/s |
| Compute/pack duration derived from counters | 1.629 ms |
| Packed A/B MM2S transfer time | 39.558 ms |
| Packed A/B MM2S bandwidth | 29.821 MB/s |
| A9 shared-memory publication | 3.049 ms |
| End-to-end workload latency | 110.649 ms |
| End-to-end throughput | 0.085 GMAC/s |
| Effective input+output bandwidth over the whole workload | 10.883 MB/s |

MB/s uses decimal megabytes. MM2S payload includes both activation and weight
bytes, including repeated activation tiles; it is not weight-only bandwidth or
an isolated DDR peak. MM2S time includes cache flush, launch, and Python polling.
End-to-end time includes descriptor programming, buffer copies, DMA, numerical
validation, and shared-memory publication. It excludes reference/vector
generation, overlay programming, and buffer allocation. These are one-run
measurements, not a statistical performance characterization or a CPU speedup
claim. The 5.793 GMAC/s number is cycle-derived accelerator throughput, not
end-to-end application throughput or GPT-2 tokens/s.

## Warning review — complete

The following classes have been examined in the implementation logs. Both
accepted builds have one final DRC warning (`RTSTAT-10`, 20 unloaded generated
reset nets), two DRC advisories (`REQP-181`), and two methodology warnings
(`LUTAR-1`); no final error or critical warning appears in those reports.
The console logs have identical diagnostic-class counts. Earlier implementation
critical messages comprise two each of `PSU-1`, `PSU-2`, and
`Designutils 20-1280`, plus one `Timing 38-282` under artificial uncertainty.
Their dispositions are below. The exact-overlay M1 and M2 board tests passed
the required DDR/DMA, reset, console, and shared-memory checks; this qualifies
the supported workload, not an exhaustive board/environment stress campaign.
The build rejects final DRC errors/critical warnings, unexpected DRC warning
classes, and final methodology errors/critical warnings.

| Messages | Interpretation and review condition |
|---|---|
| `PSU-1`, `PSU-2` | Negative DDR DQS skews (-0.009/-0.033) originate in the Digilent board preset. Retained vendor settings; physical DDR/DMA acceptance passed. |
| `Designutils 20-1280` | Two optimized-away SmartConnect reset modules have generated board XDC files containing only a physical-constraints comment; no actual constraint is lost. |
| `IP_Flow 19-11770`, `BD 41-702` | Interface metadata lacks an initial clock frequency / retains a PS GP0 frequency property; all physical AXI clock pins connect to the common generated 95 MHz clock. Final timing shows one correctly derived fabric clock and no unconstrained endpoints. |
| `BD 41-1306` | GPIO data is explicitly wired to core reset, overriding the board automation's external GPIO interface. This is intentional; reset polarity is checked by the build. |
| `BD 41-3281` | PS has control-side and HP-side SmartConnects. GP0/HP0 enables, endpoint connections, and address assignments are explicit in the build Tcl. |
| `BD 41-2384`, `Synth 8-10507` | Generated SmartConnect internal payload adapters and repeated interface attributes. External data interfaces remain 32 bits. Integrated AXI tests and the complete board transfer passed. |
| `Synth 8-11067` | Upstream Ibex package parameters are treated as localparams, consistent with SystemVerilog package semantics. |
| `Synth 8-7071`, `8-7023`, `8-7129` | Unused vendor-IP/optional ports and CDC helper connections in the configured synchronous, simple-DMA design. Final clock/endpoint checks are clean. |
| `Synth 8-3848`, `8-3295` | Disabled scatter-gather/stream-status paths in AXI DMA and unused generated reset outputs; unused DMA status inputs are tied low. |
| `Synth 8-6014`, `8-3332`, `8-3936` | Removal/trimming of unused IP, reset-controller, and optional Ibex state. Active firmware and accelerator paths are covered by regression. |
| `Synth 8-7137`, `8-4767` | M1 console storage is unreset inside a resettable process and maps to registers. Reset clears occupancy, so stale bytes are not observable; enqueue/dequeue and board-console checks passed. |
| `Synth 8-6841` | Inferred memories use whole-word or physically banked write enables; byte-wide BRAM write-enable optimization is unavailable. Logical byte-strobe behavior is tested separately. |
| `Synth 8-3323` | Intermediate arithmetic mapping attempts DSP allocation despite the zero-DSP limit; both final mapped designs contain zero DSP primitives. This is not a waiver of the zero-DSP gate. |
| `Synth 8-7080`, `Vivado 12-7122`, deprecated `-fanout_limit` | Parallel/incremental synthesis or deprecated optimization options; the full clean synthesis flow still runs. |
| `Vivado 12-2489` | The temporary 0.526315 ns implementation margin rounds to 0.526 ns. It is removed before final timing qualification; vendor jitter remains. |
| `Route 35-39`, `Timing 38-282` | May occur under temporary extra setup uncertainty. Only the final exact-95-MHz report determines acceptance. |
| `Power 33-332` | Default reset switching activity makes power estimation unreliable; no measured power claim is made in M2. |
| `Project 1-645` | Exported hardware platform has no board-image artwork; bitstream/HWH functionality is unaffected. |
| DRC `RTSTAT-10` | Unloaded generated SmartConnect reset-pipeline nets. All routable nets are fully routed in both accepted builds. |
| DRC advisory `REQP-181` | Vendor DMA FIFO BRAMs use WRITE_FIRST; FIFO control owns read/write collision avoidance. Board DMA transfer checks passed. |
| Methodology `LUTAR-1` | M1 core/peripheral reset combines system and GPIO reset. The supported sequence holds GPIO reset low during system reset/programming and releases it only after the fabric clock and system reset stabilize. Board scripts follow this sequence. |

The earlier `TIMING-2`/`TIMING-4` critical clock warnings were fixed, not
waived. No critical methodology warning is accepted for closure.

## Closure review and limitations

Acceptance review: **PASS** against every gate in the status table, with source,
artifact, report, simulation, and board-log associations recorded above. This
is the implementation agent's evidence review, not an independent external
peer review. No mandatory M2 work remains.

- The logical tile is 16x16, but the physical array is 4x16. The original
  approximately 25 GMAC/s / 256-lane estimate was not achieved and is not a
  closure claim; the qualified design delivers 5.793 cycle-derived GMAC/s.
- Projection results reach the shared scratchpad through an A9 copy after DMA
  returns them to DDR, not through a direct DMA-to-scratchpad path.
- Both harts are held in reset during the projection board benchmark. Their
  M1 workload passes separately on the same overlay; concurrent hart/GEMM
  activity is covered by the integrated simulation, not this board benchmark.
- +0.500 ns setup margin and 100 MHz remain unachieved stretch targets. M3
  changes require their own timing closure.
- Full GPT-2 inference, autonomous core-driven inference, SFPU, ASIC results,
  power measurements, and application speedup/token-rate claims are outside M2.

M3 has not started.
