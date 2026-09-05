"""M4 single-owner bounded DMA backend for the exact accepted M3 overlay.

No numerical reference evaluation occurs here. Payloads are built from actual
runtime operands and delivered int32 results. PYNQ is imported only on board.
"""
from collections import Counter
from pathlib import Path
import time
import numpy as np
from ref.m4_model_pack import file_sha256

BIT_SHA = '78fc22f0e9263759ed2ac6417345ce8c6ef7815438febd9c6a4332532790be5b'
HWH_SHA = '20a2f3caa860b3dd644b9f4b5e7fa9bb8e7a70dc6a51dbd280e7e9347a3eafd6'
_RETAINED_UNSAFE_BUFFERS = []


def pack_gemm_into(target, a, weight_tile):
    a, weight_tile = np.asarray(a), np.asarray(weight_tile)
    if a.ndim != 2 or a.dtype != np.int8 or weight_tile.dtype != np.int8:
        raise ValueError('signed int8 GEMM operands required')
    m, k = a.shape
    if not 1 <= m <= 16 or not 1 <= k <= 3072 or weight_tile.shape != (k, 16):
        raise ValueError('GEMM dimensions out of range')
    stride = ((k + 3) // 4) * 4
    words = (m * stride + 16 * k) // 4
    if target.dtype != np.uint32 or target.ndim != 1 or len(target) < words:
        raise ValueError('GEMM packet buffer too small')
    byte_target = target[:words].view(np.int8)
    first = byte_target[:m * stride].reshape(m, stride)
    first.fill(0)
    first[:, :k] = a
    byte_target[m * stride:].reshape(k, 16)[:] = weight_tile
    return words


class FpgaBackend:
    def __init__(self, bitstream, timeout=10.0):
        bitstream = Path(bitstream)
        if file_sha256(bitstream) != BIT_SHA or file_sha256(bitstream.with_suffix('.hwh')) != HWH_SHA:
            raise ValueError('not the accepted M3 qual3 overlay')
        if not np.isfinite(timeout) or timeout <= 0:
            raise ValueError('positive finite DMA timeout required')
        from pynq import Overlay, MMIO, allocate
        self.overlay = Overlay(str(bitstream.resolve()), download=True)
        reset = MMIO(0x43c20000, 0x10000)
        reset.write(4, 0); reset.write(0, 0)  # harts held reset; A9 owns M4
        self.dma = self.overlay.axi_dma_0
        self.engines = [MMIO(0x43c13000, 0x1000), MMIO(0x43c14000, 0x400)]
        self.timeout, self.failed, self.closed = timeout, False, False
        self.tag, self.counts = 0, Counter()
        self.route = self.engines[1].read(0x50)
        self.completed = [engine.read(0x34) for engine in self.engines]
        self.check_capabilities()
        self.tx = allocate((24576,), dtype=np.uint32)  # 98,304 bytes
        try:
            self.rx = allocate((3072,), dtype=np.uint32)  # 12,288 bytes
        except Exception:
            self.tx.freebuffer()  # no transfers have been submitted
            raise
        self.tx_array, self.rx_array = np.asarray(self.tx), np.asarray(self.rx)
        self.tx_views, self.rx_views = {}, {}

    @property
    def cma_bytes(self):
        return self.tx.nbytes + self.rx.nbytes

    def check_capabilities(self):
        gemm, sfpu = self.engines
        if (gemm.read(0), gemm.read(0x3c), gemm.read(0x44), gemm.read(0x48), gemm.read(0x4c)) != (0x50414732, 0x03001010, 1, 3072, 0x30001):
            raise RuntimeError('M3 GEMM capability mismatch')
        if (sfpu.read(0), sfpu.read(0x3c), sfpu.read(0x44), sfpu.read(0x48), sfpu.read(0x4c)) != (0x50415333, 0x01000c00, 0xfe, 0x30001, 1024):
            raise RuntimeError('M3 SFPU capability mismatch')
        if any(e.read(0x38) or e.read(4) & 2 for e in self.engines):
            raise RuntimeError('engine starts busy or with an error')

    def wait(self, channel):
        deadline = time.monotonic() + self.timeout
        while not channel.idle:
            if channel.error:
                raise RuntimeError('M4 DMA channel error')
            if time.monotonic() >= deadline:
                raise TimeoutError('M4 DMA completion timeout')
        channel.wait()  # includes S2MM invalidation; MM2S transfer flushes inputs

    def select(self, route):
        if route != self.route:
            if any(engine.read(4) & 2 for engine in self.engines):
                raise RuntimeError('route change attempted while an engine is busy')
            self.engines[1].write(0x50, route)
            if self.engines[1].read(0x50) != route or self.engines[1].read(0x38):
                raise RuntimeError('route interlock rejected request')
            self.route = route

    def execute(self, route, parameters, ni, no):
        self.require_ready()
        if not 1 <= ni <= len(self.tx_array) or not 1 <= no <= len(self.rx_array):
            raise ValueError('transfer exceeds bounded buffers')
        if ni not in self.tx_views: self.tx_views[ni] = self.tx[:ni]
        if no not in self.rx_views: self.rx_views[no] = self.rx[:no]
        try:
            self.select(route)
            engine = self.engines[route]
            self.tag = (self.tag + 1) & 0xffffffff
            for i, value in enumerate(parameters):
                engine.write(8 + 4 * i, int(value))
            engine.write(0x18, self.tag)
            engine.write(0x1c, 1)
            if engine.read(0x38):
                raise RuntimeError('M4 descriptor rejected')
            self.dma.recvchannel.transfer(self.rx_views[no])
            self.dma.sendchannel.transfer(self.tx_views[ni])
            self.wait(self.dma.sendchannel)
            self.wait(self.dma.recvchannel)
            if self.dma.sendchannel.transferred != 4 * ni or self.dma.recvchannel.transferred != 4 * no:
                raise RuntimeError('DMA delivered an unexpected byte count')
            self.completed[route] = (self.completed[route] + 1) & 0xffffffff
            if (engine.read(0x38) or engine.read(0x20) != self.tag or
                    engine.read(0x34) != self.completed[route]):
                raise RuntimeError('M4 completion/tag/count mismatch')
            self.counts['dma_input_bytes'] += 4 * ni
            self.counts['dma_output_bytes'] += 4 * no
            self.counts['packets_' + str(route)] += 1
            self.counts['compute_cycles_' + str(route)] += engine.read(0x24)
            # Copy before the next request can reuse the receive allocation.
            return self.rx_array[:no].view(np.int32).copy()
        except Exception:
            self.failed = True
            raise

    def gemm(self, a, tiles, n):
        self.require_ready()  # never rewrite an active/failed DMA's input buffer
        a, tiles = np.asarray(a), np.asarray(tiles)
        if a.ndim != 2 or a.dtype != np.int8 or not 1 <= n <= 50257:
            raise ValueError('invalid GEMM operands')
        m, k = a.shape
        if tiles.shape != ((n + 15) // 16, k, 16) or tiles.dtype != np.int8:
            raise ValueError('invalid packed weight dimensions')
        result = np.empty((m, n), dtype=np.int32)
        for t in range(len(tiles)):
            width = min(16, n - t * 16)
            ni = pack_gemm_into(self.tx_array, a, tiles[t])
            words = self.execute(0, (m, width, k, 0x100), ni, m * 16)
            delivered = words.reshape(m, 16)
            if width < 16 and np.any(delivered[:, width:]):
                self.failed = True
                raise RuntimeError('nonzero GEMM output padding')
            result[:, t * 16:t * 16 + width] = delivered[:, :width]
        self.counts['gemm_macs'] += m * k * n
        return result

    def sfpu(self, descriptor, words):
        self.require_ready()
        descriptor.validate()
        if words.dtype not in (np.dtype('uint32'), np.dtype('int32')) or words.shape != (descriptor.input_words,):
            raise ValueError('invalid SFPU packet')
        self.tx_array[:len(words)] = words
        result = self.execute(1, (descriptor.op, descriptor.length, descriptor.shift, descriptor.multiplier),
                              len(words), descriptor.length)
        self.counts['sfpu_' + str(int(descriptor.op))] += 1
        return result

    def require_ready(self):
        if self.closed or self.failed:
            raise RuntimeError('DMA backend is closed/failed; recovery required')

    def reset_dma(self):
        self.dma.mmio.write(0, 4)
        deadline = time.monotonic() + self.timeout
        while self.dma.mmio.read(0) & 4:
            if time.monotonic() >= deadline:
                raise TimeoutError('DMA reset failed; CMA buffers must be retained')

    def recover(self):
        if self.closed:
            raise RuntimeError('closed backend cannot recover')
        self.failed = True
        self.reset_dma()
        for engine in self.engines:
            engine.write(0x1c, 4)
            engine.write(0x1c, 2)
        # PYNQ 3.1.1 start() spins without a deadline. Use its verified simple
        # DMA start sequence with a timeout, then restore first-transfer state.
        for offset, channel in ((0, self.dma.sendchannel), (0x30, self.dma.recvchannel)):
            self.dma.mmio.write(offset, 1)
            deadline = time.monotonic() + self.timeout
            while not channel.running:
                if time.monotonic() >= deadline:
                    raise TimeoutError('DMA restart did not finish')
            channel._first_transfer = True
        self.completed = [engine.read(0x34) for engine in self.engines]
        self.route = self.engines[1].read(0x50)
        self.check_capabilities()
        self.failed = False

    def close(self):
        if self.closed:
            return
        try:
            self.reset_dma()
        except Exception:
            self.failed = True
            _RETAINED_UNSAFE_BUFFERS.extend((self.tx, self.rx))
            raise
        self.tx_views.clear(); self.rx_views.clear()
        self.rx.freebuffer(); self.tx.freebuffer()
        self.closed = True
