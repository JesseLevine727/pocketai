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

## Outstanding mandatory gates

All of `M5_PLAN.md` G1–G8 remain open. In particular, local component simulation
is not a timing report or a substitute for the final autonomous empty-cache
1024-position physical test. Kernel-helper loading still requires explicit
approval; no helper has been loaded and no boot setting changed.
