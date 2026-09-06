# Temporary M5 Linux DMA owner

`pa_m5_dma` exposes `/dev/pocketai_m5` to root only. It owns individual ordinary
DDR pages, their DMA mappings, a coherent 256-KiB page table, and the four
protected supervisor GPIO blocks. It does not modify boot settings or reserve
arbitrary physical memory. The user has explicitly authorized helper loading
and subsequent necessary M5 board work without further routine approval prompts.

The staged target is PYNQ-Z1 Linux
`6.6.10-xilinx-v2024.1-g916a1f7c7222`. Its private build preparation uses the
actual board `Module.symvers` (SHA-256
`691f689a91121517e257d47421dbc9aa3f41575629306b512f820f7eafb5ab58`) and
generated release header. The board's packaged build tree lacked generated
ARM headers, so preparation occurred in a user-home copy. GCC 12.0.1 from a
user-home toolchain compiled the helper; the original kernel used GCC 12.2.0.
Matching vermagic/symbol versions are checked and normal loading now passes;
an exact compiler match is not claimed.

Rebuild on the prepared board (unprivileged):

```sh
cp /lib/modules/6.6.10-xilinx-v2024.1-g916a1f7c7222/build/include/generated/utsrelease.h \
  /home/xilinx/pocketai_m5_kernel_build/include/generated/utsrelease.h
make -C /home/xilinx/pocketai_m5_kernel_build \
  M=/home/xilinx/pocketai_m5_helper_build \
  KERNELRELEASE=6.6.10-xilinx-v2024.1-g916a1f7c7222 \
  CC=/home/xilinx/pocketai_m5_toolchain/root/usr/bin/gcc-12 modules
modinfo /home/xilinx/pocketai_m5_helper_build/pa_m5_dma.ko
```

No module force-load or force-unload is permitted. The authorized physical
commands are:

```sh
sudo insmod /home/xilinx/pocketai_m5_final/pa_m5_dma.ko
# Run from the board's login shell so XILINX_XRT=/usr is set; preserve it.
sudo -E /usr/local/share/pynq-venv/bin/python3 \
  /home/xilinx/pocketai_m5_final/m5_run.py \
  --stage /home/xilinx/pocketai_m5_final \
  --output /home/xilinx/pocketai_m5_final/m5_physical.json
sudo rmmod pa_m5_dma
```

The runner programs the separately staged bit/HWH, provisions the full model
and caches, verifies firmware before every boot, checks a rejected overflow
request, then runs the fixed short model matrix. During START..DONE it polls
only supervisor status; every tensor/operator/transfer decision is in firmware.

Physical allocation regression (with an M5 overlay already programmed):

```sh
sudo -E /usr/local/share/pynq-venv/bin/python3 \
  /home/xilinx/pocketai_m5_final/m5_dma_check.py \
  --stage /home/xilinx/pocketai_m5_final \
  --output /home/xilinx/pocketai_m5_final/m5_allocation.json
```

All 65,012 pages / 266,289,152 bytes allocate in 3.029 seconds on the board;
bounds/guard/exclusive-open/mmap/close-reopen checks pass. The allocation uses
`__GFP_RETRY_MAYFAIL` for bounded reclaim without directly invoking the OOM
killer. `__GFP_NORETRY` previously failed around 15 MiB despite reclaimable
file cache. No CMA resizing, cache dropping or boot change is needed.

The final three-prompt inference campaign passes with safe ownership return.
A subsequent full allocation/bounds/close-reopen check passes in 2.043 seconds,
then normal `rmmod pa_m5_dma` succeeds: both `/sys/module/pa_m5_dma` and
`/dev/pocketai_m5` are absent. No force operation or persistent boot change was
used. See `docs/m5_closure_evidence.json` for the exact loaded module and reports.

IOCTL allocation/mapping occurs only while CPU-owned. START syncs every mapped
page for the device, clears sticky cancellation using a drained IO reset,
flushes mappings with cores held, then releases the harts. RETURN_CPU holds
cores and asserts cancellation, requires quiesced/not-busy/not-poisoned, disables
mapping and syncs pages back to the CPU. Existing userspace mappings are not
revoked during device ownership: the controlled root runner obeys that phase
contract and performs no tensor accesses until RETURN_CPU succeeds.

If drain fails, close retains pages, DMA mappings and a module reference;
reopening is rejected. A failed drain is a terminal ownership problem to
investigate, not permission to unload/reset/reprogram the fabric or free pages.
The process reports cleanup failures as FAIL and preserves the error report.
