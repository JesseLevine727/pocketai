# M5 verification — development evidence

Status: **IN PROGRESS / NOT QUALIFIED**. No M5 physical overlay, autonomous
model runtime, final-context proof or performance result is accepted yet.
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

## Outstanding mandatory gates

All of `M5_PLAN.md` G1–G8 remain open. In particular, local component simulation
is not a timing report or a substitute for the final autonomous empty-cache
1024-position physical test. Kernel-helper loading still requires explicit
approval; no helper has been loaded and no boot setting changed.
