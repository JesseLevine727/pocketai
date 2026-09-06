# M5 verification — lean closure PASS

Status: **CLOSED**, 2026-09-06 UTC, under the user-selected
[lean acceptance plan](M5_PLAN.md). Final source-checked hardware, production
firmware, all three physical prompts, ownership cleanup and performance pass.
The [raw physical report](m5_physical_evidence.json),
[closure manifest](m5_closure_evidence.json) and [performance](M5_PERFORMANCE.md)
record the accepted result. M6 remains unstarted.

The dated development entries below preserve failures and intermediate scope;
their then-current "pending" statements are historical, not outstanding gates.
In particular, the earlier unpatched staged artifact remains revoked, not
silently promoted to correct hardware. M4's accepted sources/evidence remain
unchanged. The final requirement-by-requirement audit is at the end.

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

**Superseded qualification:** physical testing below discovered that this
source-only Vivado flow did not execute the CPU pre-build patch hook. The
reported implementation measurements describe that unqualified artifact only.
The simulator did contain the fixes. Do not use this build to close G5/G6.

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

## 2026-09-06: authorized physical provisioning and build-path correction

The user approved temporary helper loading and subsequent necessary M5 work
without further routine confirmations. The module loads normally on the
matching kernel release; no boot change, forced module operation or arbitrary
RAM reservation was used. PYNQ requires the login environment's
`XILINX_XRT=/usr` to survive sudo (`bash -lc` and `sudo -E`). The first runner
failure omitted that environment and stopped before overlay programming.

The next run programmed the overlay but returned ENOMEM during model-page
allocation. A one-page test passed, excluding coherent page-table allocation
as the cause. The full allocation reproduced failure at page 3,759 (about
15 MiB), despite about 391 MiB reported available after cleanup. The allocator
used `__GFP_NORETRY`, which permits only lightweight reclaim. Replacing it
with `__GFP_RETRY_MAYFAIL` permits bounded reclaim/page-out without directly
invoking the OOM killer, as documented in the
[Linux 6.6 allocation API](https://www.kernel.org/doc/html/v6.6/core-api/mm-api.html).
No CMA pool change or global cache drop was necessary.

`zynq/m5_dma_check.py` passes the actual Linux ioctl/mmap seam: 65,012 pages
(266,289,152 bytes) allocated in **3.02885 seconds**; exclusive-open, empty,
unaligned, overflow, overlap, unmapped-guard and START-without-pages rejection;
first/last mapped-word read/write in all seven regions; close/reopen with zero
remaining pages and CPU ownership. MemAvailable was 150,612 KiB with the full
arena allocated. This is physical allocation/ownership evidence, not a claim
of full-model numerical correctness. Raw report:
`build/m5_physical.6jgElc/m5_allocation.json`.

The third full runner successfully provisioned all model/cache regions and
passed firmware overflow rejection: all four cache-region hashes and the
output sentinel remained unchanged. The subsequent valid story request
trapped before model initialization finished: state 1, hart-0 mcause 2,
mtval 0, mepc `0xfa3c`; safe ownership return/cleanup succeeded. A 64-KiB
model-header-only hardware reproduction produced the same trap. A diagnostic
uncompressed firmware passed startup but is **not** the delivered firmware or
a substitute for correcting the hardware.

Inspecting actual exported source files identified the mismatch: the Vivado
wrapper invoked FuseSoC `--setup` then Vivado directly, bypassing the exported
`pre_build` hook. Both CPU files still had their original hashes, whereas the
accepted actual-core simulation contained the derived hashes in
`M5_LSU_REVIEW.md`. `zynq/build_m5.sh` now invokes the exported fail-closed hook
explicitly. `scripts/check_m5_sources.py` independently checks both derived
hashes in the shell and again before Vivado project creation. It rejects the
old `m5_pynq_lean7` export and accepts the corrected `m5_pynq_lean8` export.
Patch/export regression `build/m5_ibex_patch.XNYWMr/` passes, including
idempotence, unsafe-input rejection and unchanged frozen dependencies.

A short extension of the real dual-Ibex accelerator harness runs the exact
production firmware and model header, deliberately truncating workspace to
terminate at a known store fault after model binding/both-hart readiness.
Six memory-response delays (0/16/32/64/128/256 cycles) all reach state 3,
hart-ready 3 and the intended fault at `0x4f201a00` on the already qualified
derived simulation library. This is startup coverage, not full-model proof.
Historical failed reports, scratchpad dump and diagnostic builds are retained
under `build/m5_physical.6jgElc/`; the original staging JSON is a historical
snapshot and is not silently rewritten to claim corrected hardware.

## 2026-09-06: corrected clean implementation

`build/m5_pynq_lean8/` completes the full shell/Vivado flow with exit 0,
including bitstream, HWH and XSA export. Both CPU derived-source hashes are
verified before compilation. Final 91-MHz setup WNS is **+0.584 ns**, TNS 0;
hold WNS **+0.045 ns**, THS 0. All clocks/endpoints are constrained; 44,736
routable nets are fully routed with zero routing errors. Utilization:
28,442 LUTs, 21,688 registers, 95.5 BRAM tiles, **zero DSPs**.

Final DRC has zero errors/critical warnings and one RTSTAT-10 warning for
30 unloaded SmartConnect reset-pipeline nets. The seven LUTAR-1 methodology
warnings have no accompanying errors/critical warnings. A fresh read-only
checkpoint audit (`review_reset_cones.tcl`, `reset_cones.log`, exit 0) examines
all seven cells named in the actual final report: six NANDs combine the
peripheral/cluster resets, and the seventh combines that reset, core reset
and the registered/protected sticky cancellation sources. The previously
qualified drain/reset/flush sequence applies; no opposed live switching is
permitted. This replaces, rather than requalifies, the unpatched artifact.

Fresh startup simulation `build/m5_startup.hktjIS/` passes all three selected
response delays using `sim/run_m5_startup.sh`. The same fresh simulation also
passes the unchanged nine-job accelerator/two-boot/14-case lifecycle matrix
in 31,208,171 cycles; the terminal log is
`build/m5_physical.6jgElc/accelerators_regression_corrected_cwd.log`.

## 2026-09-06: physical full-model progress and ARM checker correction

The corrected overlay passes the production startup/precise-fault test on the
board with both harts ready, exactly the intended first-embedding load fault
(`mcause=5`, `mtval=0x40010000`) and safe ownership return. The unchanged `-Os`
firmware then completes the valid story request: five generated tokens,
17 valid cache positions, 64,112 completed transfers, zero firmware error,
and a 1,909,188-byte workspace high-water mark. All token, final full-logit
and KV assertions execute successfully before the trace checker fails.

That remaining failure is host-only: 32-bit ARM NumPy does not accept an
int64 exponent array in `ldexp`. The checker now validates exponent range
0..30 and uses int32. Eight host tests and six focused tests using the actual
board NumPy/frozen trace fixtures pass. A trace-checking failure now preserves
the already calculated inference/timing result explicitly as partial evidence,
without converting FAIL into PASS. The earlier report is retained as
`build/m5_physical.6jgElc/m5_physical_corrected.json`; it did not retain full
64-bit timing data, so no throughput is reconstructed from its wrapping
32-bit counters or shell observations.

To reduce remaining run time without numerical/RTL changes, the delivered
firmware build now uses `-O2` instead of `-Os`. It still fits easily: 30,916
text bytes, 128 data, 112 BSS, exact 65,536-byte image, no F/D instructions
or undefined symbols. Build: `build/m5_firmware_o2/`, image SHA-256
`39314468a20eb4b89a72f25dee99abede3aba91d07afd29ae84195a2b4a8ac1c`.
The actual-core production-startup test passes all three response delays with
this image (`build/m5_physical.6jgElc/startup_o2.log`). The complete short
physical matrix is rerun once to qualify these final firmware/checker bytes;
no extra implementation build or marathon is introduced.

## 2026-09-06: final physical acceptance and normal cleanup

The complete frozen `m5-lean-physical-v1` matrix passes on the final `-O2`
firmware and corrected overlay. The shell records `M5_O2_CAMPAIGN_EXIT=0`.
Exact physical outputs are:

| Prompt | Input / generated tokens | Generated IDs | Final valid cache | Checks |
|---|---:|---|---:|---|
| story | 13 / 5 | 257, 582, 3706, 399, 2271 | 17 | Tokens, full logits/KV and five prefill traces exact |
| science | 8 / 1 | 5004 | 8 | Token and full logits/KV exact |
| computing | 8 / 1 | 22712 | 8 | Token and full logits/KV exact |

The five story traces are embedding, layer-0 QKV, all-head attention context,
layer-0 output and layer-11 output. Their complete shapes and SHA-256 values,
and every final full-logit/KV hash, are in the committed raw report. References
come from the independently frozen M4 fixture manifest, never this firmware.
The unchanged portable foundation additionally qualifies 396 trace tensors /
4,670,788 values and 60 exact generation steps. The separate frozen M4
floating-model quality evidence is retained, not replaced by self-consistency.

Hart 0 owns the complete model loop, metadata, scale/packing/KV and greedy
selection; hart 1 executes the accelerator/transfer jobs through the bounded
mailbox. Both are active; this is not a claim of two simultaneous model loops.
The actual host runner only polls supervisor status between START and DONE.
Story completes 64,112 transfers without any A9 tensor, operator or transfer
service. All cache/model work is on the bare-metal RISC-V/accelerator system.

Before the accepted runs, prompt_count=1 / generation_count=1024 is rejected
with state 5 / error 1 in 2.353512 seconds. Cache-valid/generated-count sentinels
remain 17/19, the output sentinel remains unchanged and all four full cache
region hashes remain unchanged. Subsequent accepted boots prove recovery.
The separately accepted production-startup test deliberately faults on an
unmapped first embedding load, reports exact mcause/mtval with both harts ready,
and returns ownership before the full campaign. This is targeted physical
error/recovery evidence, not a claim of physical fault injection at every AXI phase.

Final request timing from resident START through safe RETURN_CPU and copying
output IDs is 494.913238 / 208.818166 / 208.869540 seconds. Story primary rate
is 0.010102781 tok/s. Its first cached interval is a retained warmup; the next
three have median 39.520935 seconds/token and aggregate 0.025275681 tok/s.
See `M5_PERFORMANCE.md` for all samples, boundaries, memory and limitations.
No positive speedup or >=1 tok/s claim is made.

All 65,012 pages / 266,289,152 bytes were allocated, including the full
1024-position cache capacity. Peak process RSS was 326,360 KiB; the highest
firmware workspace usage was 1,909,188 bytes. The runner reports CPU ownership
and `ownership returned and mappings/file closed`. A subsequent full allocation
and bounds regression passes again in 2.043103 seconds, with close/reopen
showing zero pages and owner 0. Normal helper unload succeeds; module and
device-node absence are explicitly checked. No force unload, CMA resize,
global cache drop or boot change was used.

Accepted identities:

- Bitstream: `b25c6058b00783df611761f0cc1edf15b6c8d666cc86011c03e051c4b24dc813`.
- HWH: `6a16da94a5a4a0738834d247b50ec4a27d2582f3678ea1787d097298c34f11c9`.
- Firmware/readback: `39314468a20eb4b89a72f25dee99abede3aba91d07afd29ae84195a2b4a8ac1c`.
- Loaded helper: `4c0f5b345c93751d3c8e9c8a26410d80ba66930cbc7e7111da72758091e2df86`.
- Model: `4a8743dce2f9dd9b32087ef30e45131ec2e02488789c6a949e36ee2959ad5a78`.
- Frozen fixtures: `7324fb3a88c9b7340e9aa65ea6dd43f77253f0ddf7e7aca9fb100f47f963c537`.

The closure manifest pins the remaining sources, 182-file resolved hardware
tree, tools, build/warning-review logs, final artifacts and physical reports.
Large build products/logs remain in the ignored local build tree; the compact
raw model report and closure manifest are committed. The auditor requires
those local artifacts and fails closed if they are missing or stale; a clone
alone is not claimed to contain every bitstream or test fixture.

Representative reproduction commands (do not rerun long work just to audit):

```sh
# Local read-only closure and focused host checks:
python3 -m scripts.audit_m5
build/m4_venv/bin/python -m unittest tests.m5.test_board_runner -v

# Optional reproduction of production-startup simulation:
bash sim/run_m5_startup.sh build/m5_firmware_o2/m5_runtime.bin \
  build/m5_arena.1Org4t/model/model.bin

# Board login shell, final bytes staged, helper loaded and XILINX_XRT preserved:
sudo -E /usr/local/share/pynq-venv/bin/python3 \
  /home/xilinx/pocketai_m5_final/m5_startup_check.py \
  --stage /home/xilinx/pocketai_m5_final \
  --output /home/xilinx/pocketai_m5_final/m5_startup_o2.json
sudo -E /usr/local/share/pynq-venv/bin/python3 \
  /home/xilinx/pocketai_m5_final/m5_run.py \
  --stage /home/xilinx/pocketai_m5_final \
  --output /home/xilinx/pocketai_m5_final/m5_physical_o2.json
sudo -E /usr/local/share/pynq-venv/bin/python3 \
  /home/xilinx/pocketai_m5_final/m5_dma_check.py \
  --stage /home/xilinx/pocketai_m5_final \
  --output /home/xilinx/pocketai_m5_final/m5_allocation_final.json
sudo rmmod pa_m5_dma
test ! -e /sys/module/pa_m5_dma
test ! -e /dev/pocketai_m5
```

## Final requirement audit

| Gate | Accepted evidence / explicit boundary |
|---|---|
| G0 scope/ownership | User-authorized lean `M5_PLAN.md`, ABI v1 and premeasurement policy; no in-run A9 tensor/transfer/operator work |
| G1 memory/safety | Kernel-owned DMA pages, full model/cache capacity, physical allocation/mmap/guards/exclusivity/close-reopen and normal unload |
| G2 autonomous control | Directed component tests; fresh dual-Ibex nine-job/two-boot/14-lifecycle simulation; physical precise fault, rejection, safe return and successful reuse |
| G3 faithful full runtime | All 12 layers/heads, full 50,257 logits, W8A8/int16/scales/greedy contract retained; actual RV32IMC software numerics and final physical exactness |
| G4 regressions | 396 native full-model traces, 60 native exact generation steps; actual-Ibex 6,904 + 6,881 numerical cases; 84 ISA passes with exactly four historical xfails; affected legacy cluster/M1 harts; eight host and six ARM checker tests |
| G5 implementation | One correct clean 91-MHz full build, +0.584 ns setup / TNS 0, +0.045 ns hold / THS 0, zero DSPs, fully constrained/routed, zero DRC/methodology errors or critical warnings; all eight remaining warnings reviewed |
| G6 physical acceptance | Final 5/1/1-token matrix, all final full-logit/KV hashes and five intermediate traces exact; overflow non-mutation, precise fault, recovery, terminal exit 0 and cleanup |
| G7 honest performance | All raw times/counters/memory, one warmup + three growing-context decode samples, full resident generation boundary; historical-only M4 comparison; slow result and unmet stretch explicit |
| G8 closure | Source/artifact/fixture pins, read-only `scripts.audit_m5`, reconciled README/PLAN/architecture/ABI/performance and scoped local closure commit |

No required gate remains open under the user-selected lean policy. A second
clean build, a new empty-cache 1024-position autonomous marathon, longer
generation/endurance tests, broad cold-start statistics and >=1 tok/s remain
outside mandatory closure. Full-capacity memory and bounded limit tests do
not pretend to establish that omitted endurance evidence. Necessary M5 board
work was authorized without subsequent routine approval prompts; M6 and a
remote push are not included.
