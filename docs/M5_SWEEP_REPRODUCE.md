# Reproducing the characterization

Read-only verification of the recorded run (requires existing ignored build
artifacts, like the earlier closure audits):

```sh
python3 -m scripts.audit_m5_sweep
python3 -m unittest discover -s tests/m5_sweep -v
```

The machine evidence embeds the policy, independent reference manifest, complete
raw campaign and computed summary. Large model/seed/bitstream files remain under
ignored `build/`; hashes cover them without adding model blobs to Git. All previous
qualification audits run through the chained audit. CSV regeneration is optional:

```sh
python3 -m scripts.analyze_m5_sweep --stage build/m5_sweep_v1
```

Convenient version-controlled copies of the full sample and per-token tables are
`docs/m5_sweep_samples.csv` and `docs/m5_sweep_continuation.csv`. The audit verifies
they match the generated data, including every observation, rather than a
hand-selected subset. The machine evidence preserves the richer raw records.

## Fresh execution

Use a new stage, never overwrite `build/m5_sweep_v1` or its physical-board stage.
This example deliberately stops before board access:

```sh
python3 -m scripts.m5_sweep_policy --stage build/m5_sweep_repeat_v1
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 build/m4_venv/bin/python \
  -m scripts.export_m5_sweep --stage build/m5_sweep_repeat_v1
```

Check the reference manifest is PASS and inspect any preparation-budget skips.
The qualified M4 pack/native libraries and original 20-step fixture manifests
must already exist. The exporter never substitutes the optimized runtime for
its independent oracle. It writes all four complete seed arrays, including zero
unused tails; past 13 imports the previously qualified independent cache.

At first board contact, record `python3 -c 'import time; print(time.monotonic())'`
on the board. This timestamp starts the aggregate 3600-second budget, before
staging. Verify the helper is absent and the new remote stage does not exist.
Copy `policy.json`, `references/`, the frozen runtime/profile binaries, and
`zynq/{m5_sweep,m5_run,m5_opt_profile,m5_opt_release_check}.py` to the new stage.
Use the same qualified `layout.json`, `model.bin`, `fixtures/`, `m5_pynq.bit` and
`m5_pynq.hwh`; large assets can be symlinked from existing immutable stages.
Each `references/pN/m5_profile.bin` must point to the stage's qualified profile
binary. The recorded sweep used `/home/xilinx/pocketai_m5_sweep_v1` and reused
large assets from `/home/xilinx/pocketai_m5_scalar_final_v1`.

Through an interactive, tty-allocated root SSH shell, run:

```sh
cd /home/xilinx/pocketai_m5_sweep_repeat_v1
/usr/local/share/pynq-venv/bin/python3 m5_sweep.py \
  --stage /home/xilinx/pocketai_m5_sweep_repeat_v1 \
  --campaign-start BOARD_MONOTONIC_TIMESTAMP
```

Do not store credentials. The runner loads its own helper, programs the frozen
overlay, allocates/provisions once, checks overflow, and executes the frozen
matrix in order. It refuses an already loaded helper. Cache restoration, firmware
readback, result verification and staging are charged to campaign time but not
misrepresented as model compute. Per-case bounds cover setup/checking and request
work; exceeding a bound remains recorded, and the global measurement alarm always
leaves 120 seconds for normal cancellation/drain and cleanup. No hard-kill timeout.

The final `campaign.json` must have PASS, `within_budget: true`, normal unload,
and reopened owner/pages/PTE all zero. A failed drain must be investigated without
forced unload/free. Copy the report back only after completion. Analyze it with
`scripts.analyze_m5_sweep --stage NEW_LOCAL_STAGE`. The fixed audit intentionally
targets the recorded v1 snapshot; a repeat is separate evidence, never a silent
replacement. This wrapper does not authorize follow-up optimization or M6.

## Reading the samples

All per-token continuation intervals remain in `campaign.json`. `samples.csv`
has one row per declared trial, including skips/failures; `summary.json` groups
only identical workload/profiling conditions. Population standard deviations
are descriptive for these tiny samples, not inferential confidence intervals.
Profile runs are never pooled with unprofiled timing. A single provisioning
observation is neither a cold-start distribution nor a power-on boot measurement.

Traffic counters measure tensor-mover packets, not all DDR accesses: CPU loads,
stores and host cache synchronization are outside them. Full-request byte counters
are 32-bit; profile word counters are 32-bit before multiplication by four. Treat
them as raw modulo counters, not independently overflow-certified traffic totals.
Full-request engine cycles are also modulo 2^32, whereas model timing uses the
64-bit cycle timestamps. No aggregate GMAC claim is derived from the firmware's
mixed MAC/SFPU-element work counter.

The prompt curve is not perfectly content-matched: length 8 uses the original
science/computing prompts, while 1/13/16/32/64 use story or repeated/truncated
story tokens. The cached curve likewise changes both context length and selected
next-token values. It describes these representative inputs, not a causal fit
or a universally guaranteed context-cost formula.

The recorded campaign ran under the board's normal Linux/SSH environment, not
an isolated real-time benchmark configuration. Occasional read-only copies of
the checkpoint JSON were retrieved over SSH while the campaign ran; no inference
tensor was read under device ownership. These monitoring operations and ordinary
OS activity can contribute contention. No outlier is removed or attributed to
a specific cause without evidence. The result does not establish unloaded-host
tail latency or guarantee a 10-second deadline.
