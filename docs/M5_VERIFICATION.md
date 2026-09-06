# M5 verification — development evidence

Status: **IN PROGRESS / NOT QUALIFIED**. The 91-MHz overlay has passed final
implementation checks. Physical autonomous model execution and performance
remain unmeasured; the temporary kernel helper has not been loaded.
This document records component evidence without promoting it to whole-goal
closure. M4's accepted evidence and sources remain unchanged.

## 2026-09-06: isolated memory primitives

Commands (fresh temporary build directory on every invocation):

```sh
bash sim/run_m5_translation.sh
bash sim/run_m5_axi_burst.sh
```

Both use the repository's `env.sh` Verilator 5.020 tool, `--assert -Wall`, with
warnings fatal and no blanket warning suppression. The initial translation
testbench had two lint-only warnings (clock blocking assignment and an
over-wide task argument); those were corrected before simulation acceptance.

| Component | Accepted local result | Evidence directory |
|---|---|---|
| Page translator | 1,059 cases, 1,039 PTE walks, terminal exit 0 | `build/m5_translation.cEnBxL/` |
| Buffered AXI master | 546 cases, 32,955 W beats and 33,012 R beats, terminal exit 0 | `build/m5_axi_burst.3NlUS7/` |

Translation tests cover dispersed/noncontiguous page mappings, cache collisions
and hits, read-only permission checks including hits, invalid/reserved PTEs,
bus-address zero, 32-bit/page/arena boundaries, malformed configurations/counts,
missing responses, both request/response backpressure, delayed idle-only flush,
remapping and quiescent-reset invalidation.

AXI tests cover every burst length 1..256 in both directions, buffered payload
values/strobes/last beats, address/write/output/completion stalls, normal slave
errors, no usable errored-read output, no early AW, and the final legal 32-bit
word. Aborts cover validation, partial input, stalled AW/AR/W, absent B,
in-flight reads and stalled buffered output. Missing bus responses remain busy.
Malformed IDs and early/missing RLAST remain poisoned despite abort; the test
then models a coordinated reset of **both** master and downstream bus before
checking subsequent operation. AXI VALID/payload stability is also asserted.

These tests do not prove translated AXI integration, arbitration, Linux page
ownership, a physically safe whole-system reset or firmware autonomy. Their
reset model must not be cited as permission to reset/free a live board mapping.

### Source and log identities

| File | SHA-256 |
|---|---|
| `rtl/m5/pa_m5_page_translate.sv` | `6c783e95fb02f4d48da16c7f45b3a83f38123b9276b5f1e501aa783cc7000142` |
| `tests/m5/pa_m5_page_translate_tb.sv` | `b2567b7a78b23e606ff7ad27a984811ad1067c837c1874dd1d97855fadefb55b` |
| `sim/run_m5_translation.sh` | `83bbd44d34ea3a722769752ef1c540aa9d48beb7f081d7c17493c7d9a0d2d340` |
| `build/m5_translation.cEnBxL/build.log` | `7c43a549e00787305d883abe9f04a3ce3d2cc15b33642295d65bc5939cae04c7` |
| `build/m5_translation.cEnBxL/test.log` | `5f2d289b3dcb9e1b17844452d29f68110b6e4b2aa15f0312fac140a54161353c` |
| `rtl/m5/pa_m5_axi_burst.sv` | `d94e902d742be7e84fbf6310713794392de4810950864cffb5b6c2c937013023` |
| `tests/m5/pa_m5_axi_burst_tb.sv` | `cf3a089ed536279dc4f65eebd10944162aabbd7242315428e4069d7c3183f2ee` |
| `sim/run_m5_axi_burst.sh` | `c712105d75413dda0e3f5c8f496195b3e34ab1a49cb3bc331fe6d77cbb252a70` |
| `build/m5_axi_burst.3NlUS7/build.log` | `369827b37c290e1df7a73b820a6fb89e9661eff82a58a2556218b05d5241f71a` |
| `build/m5_axi_burst.3NlUS7/test.log` | `6f59bc9f38fd46b940cc6ad81fcf22eebc4d1f9ec43b234fbe60a0ca63e80d10` |

## 2026-09-06: translated AXI composition

`bash sim/run_m5_memory_bridge.sh` passes 225 cases with 12 actual PTE reads,
112 data-read bursts and 103 write bursts in an independent noncontiguous-page
memory model. Evidence: `build/m5_memory_bridge.FiaG7R/`, terminal exit 0.
The first run stopped at a testbench watchdog shorter than a legal stalled
256-beat write; the bound was corrected to include the specified maximum burst
and stalls. No RTL change was needed for that failure; the failed run remains
separate from accepted evidence.

Coverage includes byte-strobed write/readback, cached and uncached translation,
read-only/invalid/reserved PTE denial, PTE/data errors, no raw-physical escape,
arena/page boundaries, disabled mappings, remapping/flush, abort before a walk,
abort during missing PTE/data/B responses, buffered write drain without client
service, delayed flush and child poison propagation. The slave checks that no
physical transaction leaves its independently bounded owned-page/table model,
and that bridge quiescence never overlaps outstanding slave state. Subsequent
operations succeed after ordinary drained aborts and after a separately modeled
coordinated master/slave reset for a poisoned case.

| File | SHA-256 |
|---|---|
| `rtl/m5/pa_m5_memory_bridge.sv` | `9f44830684ee682f02a6397415cf9fecf651101af84ef114e47c78055dbc5ba8` |
| `tests/m5/pa_m5_memory_bridge_tb.sv` | `38f6de212fc2d3ed64621b2252d8de63f6ea009864b8951a7d44388d41a10bfe` |
| `sim/run_m5_memory_bridge.sh` | `719baf311fa36f09c37ab26eae7a024c4735264ae9977be792ddb4ac933bc39c` |
| `build/m5_memory_bridge.FiaG7R/build.log` | `256c151557d3ac2fec1b98e9cfc0adb900cea2169a906b9ca78ff657f7f087ee` |
| `build/m5_memory_bridge.FiaG7R/test.log` | `745a6bf4836aead3c52afa80a41ec728ce977ead77be1591a97d87a53b6e0a9f` |

This is still local component integration, not Ibex/accelerator integration or
physical Linux ownership/timing/autonomous inference acceptance.

## 2026-09-06: frozen model serialization and arena fit

`bash sim/run_m5_arena.sh` passes nine host layout/ABI/rejection tests, then
exports and separately reopens/rechecks all 248 accepted M4 arrays. Exactly
205,271,824 raw payload bytes match, with no changed precision or metadata.
Export and independent recheck reports are byte-identical. Evidence is
`build/m5_arena.1Org4t/`, terminal exit 0.

| Allocation class | Bytes |
|---|---:|
| Read-only binary header, aligned model and padding | 205,340,672 |
| Complete K/V/K8/K-unit caches | 48,365,568 |
| Reserved runtime work | 4,194,304 |
| Reserved qualification trace storage | 8,388,608 |
| Total mapped payload regions | 266,289,152 (253.953125 MiB) |
| Unmapped guards and unused tail | 2,146,304 (2.046875 MiB) |
| Device-virtual arena | 268,435,456 |

This proves a static layout fits; kernel mapping metadata/page table, host
provisioning memory and board OS overhead are outside the device-virtual arena
and still need physical accounting. The runtime's actual work/trace liveness
must stay within the reserved regions. No board allocation or runtime fit is
inferred solely from this table.

| File | SHA-256 |
|---|---|
| `ref/m5_arena.py` | `12f520207cf58df085bd054caee7953d301d9a0d1dd9ed45f1c0067753b46b4d` |
| `scripts/export_m5_model.py` | `9c151899a20fe0bd84f9a4b49b0bba78a6eb43c7f99d73b5ddf2aba155e37e10` |
| `tests/m5/test_arena.py` | `809451872660788e56f6291db5ffc9303bb6c8fc43f7c19f035dbf1d32d74492` |
| `sim/run_m5_arena.sh` | `155e9ce3276b59b0c3452c4bc61bf3bd5385a12491338a12b69ec0d695487d79` |
| `build/m5_arena.1Org4t/unit.log` | `371141081a92101751ec918e6fbb243c09a47f50043850ad8c8e266d06a2e687` |
| `build/m5_arena.1Org4t/export.log` | `09b9e23d33f52b9a6191dc1ec8b882f65bbae5412183764e0eee0887cc01f0ff` |
| `build/m5_arena.1Org4t/recheck.log` | `09b9e23d33f52b9a6191dc1ec8b882f65bbae5412183764e0eee0887cc01f0ff` |
| `build/m5_arena.1Org4t/model/model.bin` | `4a8743dce2f9dd9b32087ef30e45131ec2e02488789c6a949e36ee2959ad5a78` |
| `build/m5_arena.1Org4t/model/layout.json` | `f782820638969163e0dd975a6fcfc87076bc6cd47dc841f6fb0ae6d2b52729d8` |

## 2026-09-06: core-port routing and memory ownership

`bash sim/run_m5_core_memory.sh` passes 340 synthetic core-port requests plus
40 bulk-client requests. The exact accounting is 170 local-bus grants and 210
memory-arbiter grants/completions. Evidence: `build/m5_core_memory.fcwDbH/`,
terminal exit 0. Four independent OBI port drivers exercise the two-hart
instruction/data-port topology; **this is not yet executing Ibex instructions**.

The tests mix local/DDR reads and byte-strobed writes, change upstream pins
after grant to check captured ownership, stall bulk input/output/completion,
check round-robin non-starvation, and verify no lost/duplicated transaction.
Ten local operations complete while another port has an indefinitely withheld
DDR response. Aborts cover pre-bridge issue, a live memory operation and pending
requests on the other ports. Already accepted requests retire with errors while
core stop blocks new admission; ordinary operation succeeds after drain/reuse.
This qualifies the router/adapter/arbiter against a variable-latency memory
interface model, not their final combined physical overlay.

Development failures were preserved and resolved before acceptance:

- A generated timed-fork C++ function had no return/co-return, produced a
  compiler diagnostic and segfaulted (`build/m5_core_memory.gSSHic/`; ASan
  reproduction in `build/m5_core_asan.5NQ4s2/`). The runner now keeps generated
  test coroutines unsplit and treats return-type diagnostics as fatal. It does
  not suppress RTL warnings or alter hardware to satisfy that compiler issue.
- Mixed structural/procedural drivers on unpacked testbench arrays produced
  stale generated port copies (including a zero burst count and a duplicated
  input beat). The bulk driver now drives scalar signals connected structurally
  to the arrays, matching the intended hardware wiring. Ready handshakes are
  sampled before the active clock edge to remove scheduling ambiguity.
- One over-wide boolean expression in the testbench was corrected at lint.

| File | SHA-256 |
|---|---|
| `rtl/m5/pa_m5_obi_router.sv` | `73e114d4902ed1ef4bce5bf5df108cd3c02caf402e84d7f5de49836419bdbbdb` |
| `rtl/m5/pa_m5_obi_ddr.sv` | `e5fce18b506840ca5c85d6d6e0524ee7c0cef7e104bb78f28cf99eee07e975bd` |
| `rtl/m5/pa_m5_memory_arbiter.sv` | `8852993d778637ea80165e91ee6dfbaab31bcf964bf6cd5449955e1e52596803` |
| `tests/m5/pa_m5_core_memory_tb.sv` | `6bbabe7bc57b4a5d0a5f7504e29e5ccf5c028ab44aa9b54999fa7f804474b253` |
| `sim/run_m5_core_memory.sh` | `91c2769f0b633f9c24488eaf9ce6faf9b69f1eeb6209875f3ba0ffb2cadfe4d9` |
| `build/m5_core_memory.fcwDbH/build.log` | `dacf5e3d4bbb2a740521fcaa111d22cfbfd269db791e5f1945bc10f69fdb1d59` |
| `build/m5_core_memory.fcwDbH/test.log` | `2a2e71e2c72f8488a37f50fe8f57e9b5240a5bb7904dca10355e28e8aa7925e5` |

The same final local checkpoint also reran translation, AXI burst and translated
bridge tests from fresh directories `build/m5_translation.WBQRn5/`,
`build/m5_axi_burst.aaTtpH/` and `build/m5_memory_bridge.mpZMS4/`. All passed
with result logs byte-identical to the corresponding accepted logs above.
All four fresh build logs contain no RTL or C++ warning/error diagnostic.

## 2026-09-06: actual dual-Ibex memory integration and core corrections

The real cores now execute firmware through the M5 routers, local bus, memory
arbiter, translator and buffered AXI master. Commands and accepted directories:

| Command | Evidence | Terminal result |
|---|---|---|
| `bash sim/run_m5_cluster_memory.sh` | `build/m5_cluster_memory.NrkNB2/` | 2 successful dual-hart boots, 1 aborted boot, exit 0 |
| `bash sim/run_m5_compliance.sh` | `build/m5_compliance.VUHOaN/` | 84 passes, exactly 4 known xfails, exit 0 |
| `bash sim/run_m5_ibex_patch.sh` | `build/m5_ibex_patch.Qjd4Qa/` | normal/idempotent derivation, 3 unsafe-input refusals, unchanged frozen dependencies, exit 0 |

Exact source, firmware, derived RTL and log hashes are recorded in
[`m5_core_memory_evidence.json`](m5_core_memory_evidence.json). The integrated
firmware uses 1,412 bytes of text, 128 bytes of results and no BSS, with separate
4-KiB hart stacks; the complete 64-KiB zero-padded image is loaded and read back
through AXI-Lite before release. This small test's fit does not establish the
future model runtime's fit.

Both actual harts fill and independently check full writable pages, exercise
byte/halfword strobes and signed/unsigned loads, and execute a function from a
read-only DDR page. Each hart checks RO-store, invalid-PTE-load and arena-range
load traps. Word/halfword offsets 1..3 include page crossings and untouched-byte
checks; a direct DDR-store/taken-branch sequence covers delayed memory response.
The independent physical-page model rejects escaped/unauthorized accesses and
checks final contents, not just firmware's success word.

The abort test stops both cores during an issued write, withholds B for 32
cycles, verifies that buffered W drains without core assistance and that
quiescence remains false, then releases B and drains. A new mapping is flushed
in the disabled/quiescent state; both cores pass a fresh firmware run without
resetting the memory system. Accounting across all three starts is 11 PTE reads,
4,576 data-read bursts and 4,249 writes, over 1,051,894 simulation clocks.
These are diagnostic counts, not board throughput estimates.

Two inherited core bugs were reproduced at actual instruction boundaries and
fixed **only in exported M5 build copies**: prematurely selecting the second
word's byte mask, and allowing a speculative branch decision to outrun the
target-calculation state behind pending memory. See `M5_LSU_REVIEW.md` for the
failed evidence, competing explanations, boundary probes and exact derivation.
The final sources contain no temporary debug probes. Original dependency
checkouts still match the historical pinned patches. M5's new derived identities
require independent timing and physical qualification.

Other harness/build findings were resolved without weakening the RTL gate:

- Verilator needs command-line initialization before HDL plusarg use, and an
  explicit falling reset edge for initially gated core registers. The simulator
  now supplies both; the early failing builds remain separate.
- Verilator's process-level dependency analysis reported false combinational
  feedback through the upstream controller's large combinational block.
  M5 simulation configuration isolates assignments to `controller_run_o`,
  `halt_if`, `retain_id` and `flush_id`; this partitions simulation scheduling,
  not hardware, and **does not suppress UNOPTFLAT**. The sole RTL lint exception
  remains the existing unused upstream FPGA-register-file parameter.
- The final full-cluster build has no RTL, firmware or C++ warning/error.
  FuseSoC emits its known backend-deprecation notice. The independent ISA build
  additionally reports an upstream Verilator FST-library `varDir` enum-switch
  maybe-uninitialized warning. Reviewed: all defined directions are covered,
  FST tracing remains disabled during these runs, and no tool source was changed
  or warning suppressed. This does not affect the non-tracing cluster build.
- An initial ISA harness used `WORK`, but the pinned test makefiles require
  `work_dir`. It refreshed the disposable `riscv-compliance/work/rv32imc`
  outputs, then failed its own missing-private-output check. Those working
  outputs are not retained as M1 provenance or accepted M5 evidence. Historical
  closure reports/binaries and source pins were not altered. The final runner
  uses a fresh private `work_dir`, no clean step and no instruction trace files
  in legacy directories; all five suites then pass against original references.

This closes an actual-core memory **development subgate**, not all of G2/G4.
Autonomous accelerator transfer/control, complete model firmware, physical
owned-memory lifecycle, full-overlay timing and final model/context/performance
acceptance remain outstanding. No M5 kernel helper has been loaded.

## 2026-09-06: autonomous packet-mover component

`bash sim/run_m5_stream_transfer.sh` passes **392 cases**, 2,967 memory-client
commands, 383,344 input words and 205,240 output words over 961,106 simulation
cycles. Accepted evidence: `build/m5_stream_transfer.Oov4MB/`, terminal exit 0.
RTL and C++ builds use strict warnings and contain no warning/error diagnostic.

The mover captures up to three source segments and one destination, preserving
the M3 packet layout without firmware copying static weight tiles into a second
contiguous packet. Tests check each burst length 1..256, page-end splits,
deterministic randomized three-segment packets, 65,535-word maximum input/output,
full-size GEMM and SFPU packet shapes, final legal addresses, and all data,
strobes, packet TLAST and captured-tag/count fields under independent stalls.

Sixteen malformed descriptors are rejected without memory/stream side effects.
Memory faults cover initial/later reads and initial/later destination writes;
stream keep/early-last/missing-last and internal missing/extra/early-completion
faults request global cancellation. Nine external-abort placements cover
unoffered/offered commands, both payload directions, both final memory
completions and a stalled normal completion. Tests withhold completion after
abort/timeout and require busy to stay asserted. Input stalls and accelerator
compute/output absence are included in deadline tests. Recovery happens only
after the modeled memory command drains and a deliberate reset.

This test uses independent **memory-client and accelerator stream models**, not
the real AXI translator or numerical M3 operators. Their composition, the MMIO
publication queue, route/IRQ ownership and actual-hart scheduling remain new
work. No physical bandwidth or model-autonomy result is inferred from it.
The first test watchdog was too short to reach a missing-last error at the end
of a stalled 600-word input/300-word output; it was corrected to cover the whole
scenario. The mover's deadline and drain requirements were not weakened.

| File | SHA-256 |
|---|---|
| `rtl/m5/pa_m5_stream_transfer.sv` | `e86fe7dd89bd170534128df5ddaa10f0b3442f7e2d122679cc38382206330224` |
| `tests/m5/stream_transfer.cc` | `cf455375b0a6fb83d1d6a4ea181252df747e41958568e06b2c6950697a5105f0` |
| `sim/run_m5_stream_transfer.sh` | `a1023c718ace2448d1e1e5394220d0aea9faaab3202cf52d96ad7b7025db9862` |
| `build/m5_stream_transfer.Oov4MB/build.log` | `9ae6819775080083f4a4cb413809e31b8046629acb46419ab23b684dfa445bdc` |
| `build/m5_stream_transfer.Oov4MB/test.log` | `af1598422980a04c853674a3d141fd4390d8521b1316d87b55e1c9273b2d9d7b` |

## 2026-09-06: transfer MMIO publication and completion credit

`bash sim/run_m5_transfer_control.sh` passes 8,187 MMIO accesses, 200 atomic
command publications/completions and 429 rejected accesses, including 160
staging-byte-enable cases. Evidence: `build/m5_transfer_control.kgBaF5/`, terminal
exit 0, with no RTL/C++ warning or error. The single-credit ABI and hart-1
ownership policy were recorded in `M5_TRANSFER_ABI.md` before this controller.

Tests cover every staging field and byte-enable mask, changes to staging while
a command is owned, full-credit rejection, completion backpressure, exact tag/
fault/word-count observability, ACK without completion, partial/multi-action
doorbells, unknown/unaligned/read-only MMIO errors, IRQ enable/reserved bits,
level IRQ acknowledgement, and independent rejection versus completion/fatal
IRQ sources. Accepted/completed/rejected counters are independently checked
throughout 200 credit-reuse cycles; holding DONE cannot duplicate completion
events. External abort blocks START; neither rejection-clear nor ACK can release
the control's sticky abort or the mover's fatal stopped state.

The mover side is a **register-level handshake model** here. This qualifies the
publication boundary, not end-to-end numerical execution or hart ownership in
running firmware. Connect and qualify the real mover, memory arbiter, M3
operators, route lock, interrupts and supervisor before claiming all G2 gates.

| File | SHA-256 |
|---|---|
| `rtl/m5/pa_m5_transfer_control.sv` | `158faf881bbb27b91b349531e1270658c522c9badf38c93d7956f868557f6b7c` |
| `tests/m5/transfer_control.cc` | `d7dfdd801961cb5ebd0d49117bb3f5853344c56ed61f2e0534bc11ab144df0c4` |
| `sim/run_m5_transfer_control.sh` | `dbb1f9ef0a17815447ddfb4a1b6df03d7340cf4d19445b4c38443d4ce85bb8f8` |
| `build/m5_transfer_control.kgBaF5/build.log` | `6bb1de46f836c03752a7626c71ef617dc138084b5ae8a8dc5a122d0986c183be` |
| `build/m5_transfer_control.kgBaF5/test.log` | `3a93d2bad25669ea01fb6e72ac3d4a28d5e1b925eda1cb03cd67b0cf10290ee0` |

## 2026-09-06: real operators, dual-Ibex scheduling and cancellation

The production `EnableTransfer=1` composition connects the qualified packet
mover to the original M3 wide GEMM and SFPU and makes it the only bulk-memory
client and stream owner. The external development payload/bulk ports are tied
off. Hart 0 receives only mailbox IRQs; hart 1 receives mailbox, GEMM, SFPU and
transfer IRQs. A route change is rejected while the mover owns its completion.

`bash sim/run_m5_cluster_accelerators.sh` builds actual RV32IMC firmware and the
complete two-Ibex/translated-memory/real-operator system with strict compiler and
Verilator warnings. The accepted fresh run is
`build/m5_cluster_accelerators.yKAk3l/`:

- two successful boots separated by an issued packet-write abort, full drain,
  noncontiguous physical-page remap, complete firmware reload and restart;
- hart 0 prepares and independently checks 9 jobs/9,633 result words while
  issuing competing translated DDR traffic; hart 1 is the sole descriptor,
  route and transfer owner;
- five signed-int8 wide GEMMs cover K=1,3,7,768,3072, partial bytes, M=1/3/16
  and N=13, with explicit padded output lanes;
- SFPU ADD, three-plane AFFINE, REQUANTIZE8 and unsigned-probability SOFTMAX
  cover 3,072-word planes and the 32,768 probability endpoint;
- each boot observes exactly nine mailbox IRQs on each hart, nine DMA completion
  IRQs, five GEMM IRQs and four SFPU IRQs on hart 1, with no unexpected IRQs;
- no AXI-Lite request is permitted while firmware runs, and continuously driven
  external development interfaces never handshake in autonomous mode;
- a separate host-driven lifecycle phase covers accelerator-MMIO cancellation
  overlap, local descriptor rejection/no memory effects, source permission
  failure, late destination protection/partial-result invalidation, deadline
  with a missing B response, external abort with a missing R response and the
  transfer ABORT doorbell: 14 cases pass.

The run retires 418 page-table reads, 20,272 data-read bursts and 132,655 write
bursts in 31,208,155 simulated cycles. These counts include test preparation,
checking and fault injection and are **not** a performance result. Firmware is
2,786 text bytes plus the fixed 128-byte result ABI, with no BSS.

`bash sim/run_m5_mmio_cancel.sh` independently checks the response shell over
10,000 randomized cycles: 7,569 accepted requests, 1,932 cancellation-overlap
responses and 5,637 engine responses. Every accepted request still produces
one response; cancelled accesses return explicit error and never reach the
reset engine. Accepted evidence is `build/m5_mmio_cancel.nu6iJn/`.

The unchanged development-mode cluster was rebuilt from the same current M5 RTL
with `bash sim/run_m5_cluster_memory.sh`; `build/m5_cluster_memory.dHa6HY/`
repeats both successful dual-hart boots and the issued-write abort/remap test.
This proves the optional integration did not replace the previously qualified
core-memory path. It does not replace later legacy M1-M4 regression.

Exact source and evidence hashes are in `docs/m5_accelerator_evidence.json`.
This gate proves real operator transport/control and component lifecycle, not
full GPT-2 firmware, a protected physical supervisor, owned Linux DMA pages,
timing closure, physical correctness or physical performance.

## 2026-09-06: portable full-model and actual-Ibex numerical foundation

`bash sim/run_m5_numerics.sh` passes the complete portable C numerical/model
suite in `build/m5_numerics.Vh13uK/`, terminal exit 0. It opens the independently
serialized 248-array arena, rejects 24 header/descriptor corruptions, and checks
integer and software-binary64 metadata against independent Python calculations.
The accepted run covers 14,850 integer RNE cases, 50,007 binary64-to-integer RNE
cases (including signed zero), 20,005 bit-exact square roots, 42,769 dynamic
quantization cases, 198,481 affine-scale values, 10,004 storage-range cases and
200 LayerNorm metadata cases.

The same run executes the portable C model loop with the accepted M4 CPU operator
implementations standing in for the asynchronous hardware backend. Four frozen
full-model inputs (30 input tokens total) match **all 396 independently exported
intermediate tensors**, 4,670,788 represented values, final 50,257-way logits
and complete K/V hashes exactly. All three frozen generation cases match all 60
greedy tokens, per-step full-logit hashes and per-step cache hashes. The public
generation API separately matches a three-token smoke run. Maximum observed
workspace use is 1,909,188 bytes, below the fixed 4-MiB runtime region.

This test exposed and corrected a real portable-runtime defect: negating a zero
attention score produces IEEE negative zero, which the original conversion
helper incorrectly treated as a negative out-of-domain input. Both signed zeros
now convert identically to integer zero, with explicit host and RV32 coverage.

`bash sim/run_m5_ibex_numerics.sh` then compiles the same numerical source with
the system RV32IMC soft-float libgcc and executes it on both actual Ibex RTL
cores. Accepted evidence is `build/m5_ibex_numerics.Y6riyS/`, terminal exit 0.
Hart 0 passes 6,904 cases and hart 1 passes 6,881 cases with zero error bits;
the measured firmware intervals are 49,917,481 and 102,394,216 cycles. The
firmware contains 15,392 text bytes, a fixed 128-byte result ABI and 19,968 BSS
bytes. No F/D instruction or libm is used.

Exact source and evidence hashes are recorded in
[`m5_runtime_foundation_evidence.json`](m5_runtime_foundation_evidence.json).
This gate proves portable complete-model fidelity and the actual-core soft-f64
metadata implementation. It does not yet prove that full-model jobs use the
physical GEMM/SFPU/transfer path, safe Linux-owned model pages, timing closure,
or board performance.

## 2026-09-06: final 91-MHz implementation and firmware staging

The lean test-cost policy permits one accepted implementation. Two complete
95-MHz strategies produced WNS -0.002/-0.028 ns; a 92-MHz attempt produced
+0.203 ns. The final clean build in `build/m5_pynq_lean7/` uses **91 MHz**, a
4.21% clock-rate reduction from 95 MHz, with no model/precision/context change.

Final reports and the exported `m5_pynq_final.dcp` agree on setup WNS
**+0.433 ns**, TNS **0**, hold **+0.016 ns**, THS **0**, and no failed timing
constraint checks or unconstrained internal endpoints. All 44,589 routable nets
are routed, with zero routing errors. Utilization is 28,375 LUTs, 21,668
registers, 95.5 BRAM tiles and **zero DSPs**. Normal jitter/clock uncertainty
remains in the analysis; only the extra implementation-only user uncertainty
is removed before final timing reports and checkpoint export.

Final DRC has no errors/critical warnings. The sole RTSTAT-10 warning concerns
30 unused SmartConnect internal reset-pipeline nets with no routable loads.
Methodology has seven LUTAR-1 warnings, no errors or critical warnings. A
read-only inspection of the final checkpoint (`reset_cones.log`) verifies:

- Six warned reset LUTs are NAND combinations of the peripheral reset and
  the protected cluster-reset GPIO; neither is a data-dependent reset source.
  During ordinary operation both remain high. The helper pulses only the
  cluster control while cores are held and translated memory is drained.
- The seventh combines that reset, core-reset GPIO and cancellation. Its
  cancellation sources are the protected abort GPIO and registered sticky
  transfer fault/abort/cancel state. Assertion intentionally terminates the
  run; deassertion occurs under core reset after drain/IO reset, before core
  release. No runtime switching among opposing reset inputs is permitted.

The full build generated and checked the final bitstream/HWH, then exited
nonzero on the mistyped XSA option `-include-bit`. Packaging was repaired
without synthesis/routing changes. The final XSA is a hardware handoff without
an embedded bitstream; PYNQ uses the separately pinned bit/HWH pair. The
export-only repair has terminal exit 0 in `finish_xsa.log`; the original
failed packaging log remains preserved. `zynq/build_m5.tcl` now uses the
correct export command. This is one accepted hardware artifact with an
export-only repair, not a claim that the original full shell command exited 0.

Complete hardware-backed firmware is built by `scripts/build_m5_firmware.sh`.
The reviewed build is `build/m5_firmware_review/`: 26,536 text, 128 data and
112 BSS bytes, exact 65,536-byte load image, RV32IMC/Zicsr, no F/D requirement
or undefined symbols. Hart 0 owns all GPT-2 scheduling/metadata/KV/selection;
hart 1 executes its mailbox jobs using the real GEMM/SFPU/packet-mover MMIO.
This build is staging evidence; it has not executed a full model on hardware.

## 2026-09-06: supervisor and board-runner review

Review caught three issues before physical testing: START initially held abort
through IO-reset release, which would re-latch the mover's sticky Stopped state;
later boots did not restore shared BSS and could race hart-ready publication;
and the trace checker received generation metadata rather than the separate
tensor-fixture entry. The helper now lowers abort under drained IO reset,
releases IO with mapping flush/core reset held, then releases the cores. The
runner reloads/verifies the complete firmware before every boot and supplies
the correct independent trace fixtures.

`bash sim/run_m5_cluster_accelerators.sh` in
`build/m5_cluster_accelerators.Ud8zBu/` qualifies the revised supervisor
reset/flush signal sequence on actual dual-Ibex RTL with the real operators:
two successful boots, 9,633 independently checked words per boot, nine jobs
and exact mailbox/DMA/GEMM/SFPU IRQ counts, one issued-write abort/remap,
and all 14 component lifecycle cases pass in 31,208,171 simulated cycles.
It uses the existing component firmware, not the new complete-model firmware,
and does not execute the Linux helper in a kernel.

Six short `tests/m5/test_board_runner.py` tests pass: five real frozen selected
trace tensors, altered-output rejection, reference-file hash validation,
per-boot firmware restoration/correct manifest selection, failure-report
preservation on cleanup failure, and overflow rejection with cache/output
non-mutation. Host lifecycle tests use explicit mocks and are not physical
acceptance. Trace arrays are copied before checking so a failed check cannot
retain an exported mmap buffer and prevent cleanup.

The affected legacy `bash sim/run_cluster_m3.sh` regression passes its 315
operator-chain steps and both M1 hart/mailbox checks. The untouched portable
full-model suite also passed again in `build/m5_numerics.qgO8xw/` in about
seven seconds. No old full-context board campaign was repeated.

The temporary helper uses kernel-owned scattered pages, DMA-API addresses and
explicit CPU/device cache ownership. Initial `dma_map_page` is followed by CPU
ownership synchronization before userspace touches a page. Unsafe ownership
blocks reopening; failed drain retains page mappings and a module reference.
The final staged module is compiled against the board's actual `Module.symvers`
and matching release/vermagic `6.6.10-xilinx-v2024.1-g916a1f7c7222`.
The private prepared headers initially lost the local-version suffix on a
rebuild; restoring the original generated release header and setting
`KERNELRELEASE` corrected it before staging. The compiler is Ubuntu GCC
12.0.1 (experimental), whereas the kernel was built with GCC 12.2.0; exact
compiler identity is not claimed. Loading/allocation/cache-coherence/cleanup
still need physical verification after explicit approval. No module load or
boot change has occurred.

`tests/m5/performance_policy.json` freezes the short physical matrix and timing
boundaries before measurement. Decode intervals now include token selection
and publication; forward-only prefill, firmware token-ready time and host
request-through-delivery are reported separately. Engine cycle counters wrap
at 32 bits and the aggregate work counter mixes MACs/SFPU elements; neither is
misrepresented as end-to-end model throughput.

Exact current source, artifact and report hashes are in
[`m5_staging_evidence.json`](m5_staging_evidence.json).

## Outstanding mandatory gates

The lean closure policy in `M5_PLAN.md` supersedes the original marathon test
matrix. Physical full-model firmware execution, Linux allocation/ownership,
concise physical correctness/performance and final auditing remain open.
Kernel-helper loading still requires explicit approval;
no helper has been loaded and no boot setting changed.
