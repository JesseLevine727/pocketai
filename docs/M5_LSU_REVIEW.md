# M5 Ibex memory-latency corrections

Status: local actual-core and ISA regressions pass; physical qualification is
still pending. This is not a new M1–M4
closure claim. Their repository sources, binaries and historical evidence stay
unchanged. M5 must qualify its derived source, including fresh physical timing.

## Reproduction and competing explanations

The actual dual-Ibex memory firmware, loaded and read back through AXI-Lite,
writes `0x89abcdef` at virtual `0x40000ffd`, spanning two noncontiguous pages.
The initial integrated run in `build/m5_cluster_memory.Znfv0T/` reproducibly
reports hart-0 error bits `0x00000c00`: the loaded word and first physical word
are wrong, while the second physical word is correct. Aligned, byte, halfword,
permission-fault and instruction-fetch checks had reached completion.

Ranked predictions before boundary instrumentation:

1. The inherited request-staging change sets `handle_misaligned_q` before the
   first request is granted. Both core and AXI first-word byte masks will be
   `1`, where `e` is required; the second-word mask will correctly be `1`.
2. The new router/adapter corrupts a correct core mask. The core will show `e`,
   but AXI will show a different mask.
3. The independent memory model or load assembly is wrong. Both boundaries
   will show the correct first mask/data, but the checked result will differ.

Targeted probes in `build/m5_cluster_memory.vLPRUH/` confirmed prediction 1: first core address `40000ffc` and AXI
address `10003ffc` both carry `be=1,data=abcdef89`; second core address
`40001000` and AXI address `10000000` also carry `be=1,data=abcdef89`.
The bridge preserves exactly the incorrect mask supplied by the core.

## Minimal correction and isolation

During the LSU's IDLE staging cycle, no external request is issued or granted.
Keep `handle_misaligned_d=0` there. The existing WAIT_GNT_MIS logic already sets
it to one when the first word is granted, selecting the second mask at the
correct point. The staged request timing, rotation, response ordering and
unaligned-load assembly are otherwise unchanged.

`rtl/m5/lsu_patch/` contains the reviewed LSU/ID corrections and a
fail-closed FuseSoC pre-build hook. It modifies only the exported M5 work-root
copy, refuses symlink/path escapes and unknown source hashes, and verifies the
complete derived file's hash. Repeating the hook is idempotent. It does not
edit `rtl/ibex-orig/`, alter an old core definition, or depend on a globally
installed override. M5 build scripts must retain this hook; direct compilation
of the frozen LSU is not the qualified M5 hardware identity.

- Original LSU SHA-256:
  `e85e87c1eb3c77c5c78db67793383cd23480afdfedd79b39fedc3eff2cc6945d`.
- Derived LSU SHA-256:
  `7fe4d5c261420f9862783978c9d9370a65dae6f360b5780f7afca19b090a8791`.

## Required regression

Retain the original real-core failure as a regression. Expand coverage to
word/halfword offsets and page crossings, byte effects and signed/unsigned
loads, both harts, plus drain/restart. Run affected ISA and legacy integration
tests. The four legacy exception-policy xfails are not permission to ignore
incorrect data in supported unaligned accesses. Final M5 implementation/timing
and physical memory/model gates remain mandatory.

## Speculative branch while memory is outstanding

The expanded real-core offset test exposed a second inherited bug, separately
from byte strobes. In `build/m5_cluster_memory.oHFM6f/`, the branch at PC `c8`
(`beqz a3,1ca`) redirected with target **zero**, while its target should have
been `1ca`. Execution entered the vector jump as ordinary code: the first
handler therefore read reset-valued mcause/mepc/mtval, and MRET then caused
secondary privilege faults. This was not a CSR encoding or initial-reset bug.

The competing causes were a premature branch decision, a bad instruction
fetch/response pairing, or simulation-only controller scheduling. Boundary
instrumentation distinguished them: the incorrect target was already present
at the core's PC redirect, before any fetch or router response. The ID source
itself contained a matching unresolved upstream bug comment.

`branch_set_raw_q` advanced from the speculative comparison even while
`id_fsm_q` remained in FIRST_CYCLE behind a pending memory response. Thus the
redirect could use compare operands instead of second-cycle PC+immediate.
M5 captures `branch_set_raw_d & instr_executing`, so the decision cannot advance
before the ID state machine can enter target calculation. It is cleared, not
held stale, when actual execution is disallowed. With this single assignment
changed, the same failing branch redirects to `1ca` and the entire expanded
test passes (`build/m5_cluster_memory.llupuO/`, diagnostic probes retained only
in that historical build). All temporary probes were removed before acceptance.

- Original ID-stage SHA-256:
  `eb14d2cd21b6dae9432cd1e40ab7d512828de44f32c0a1fff86e725ed1cb8fe6`.
- Derived ID-stage SHA-256:
  `1e9d382752cf9f13477f279ddc3f73a2b3d7bbd8e5cf8e4a7a9d755f6162c5f1`.

The final no-probe actual-core test (`build/m5_cluster_memory.NrkNB2/`) adds an
explicit DDR-store-followed-immediately-by-taken-branch probe on both harts.
Both boots pass all word/halfword offsets, signed/unsigned loads, byte effects,
page crossings, permission traps, full-page verification and abort/remap reuse.
The independently built M5-derived ISA runner (`build/m5_compliance.VUHOaN/`)
passes 84 tests with exactly the four historical exception-policy xfails.

What prevented earlier detection was insufficient stress on the actual core's
multi-cycle memory boundary: synthetic routers cannot expose an internal LSU
mask or speculative branch error. Keep the actual-core and independent ISA
tests alongside the lower-level bus/translation tests; do not replace either
with the other. Frozen M1 timing does not qualify these M5 changes.
