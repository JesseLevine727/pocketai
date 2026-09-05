"""Scoped physical M4 driver interlock/timeout/recovery checks on M3 qual3."""
import argparse
import json
from pathlib import Path
import numpy as np
from zynq.m4_driver import FpgaBackend
from zynq.m4_offload import packet_words
from ref.sfpu_stream import Op, SfpuDescriptor
from ref.m4_model_pack import file_sha256, tile_weights


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bitstream', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('refusing to overwrite driver evidence')
    backend = FpgaBackend(args.bitstream)
    checks = []
    try:
        # Both directions of the physical route interlock, with no DMA pending.
        for route in (0, 1):
            backend.select(route)
            engine = backend.engines[route]
            params = (1, 1, 1, 0x100) if route == 0 else (7, 1, 0, 0)
            for i, value in enumerate(params): engine.write(8 + 4 * i, value)
            engine.write(0x1c, 1)
            backend.engines[1].write(0x50, 1 - route)
            if backend.engines[1].read(0x50) != route or backend.engines[1].read(0x38) != 9:
                raise AssertionError('physical busy route interlock failed')
            backend.recover()
            checks.append('busy_route_' + str(route))
        # Invalid descriptor must poison the backend until deliberate recovery.
        try:
            backend.execute(1, (0, 1, 0, 0), 1, 1)
        except RuntimeError:
            if not backend.failed:
                raise AssertionError('descriptor failure did not poison backend')
        else:
            raise AssertionError('invalid descriptor accepted')
        backend.recover()
        checks.append('descriptor_rejection_and_recovery')
        descriptor = SfpuDescriptor(Op.ADD, 3)
        words = packet_words(Op.ADD, (np.array([17, -32768, 32767]), np.array([25, -1, 1])))
        np.testing.assert_array_equal(backend.sfpu(descriptor, words), [42, -32768, 32767])
        # Controlled missing-producer fault: real S2MM/engine wait for data,
        # while the test suppresses only the MM2S submission. No bad address,
        # overwritten buffer or unbounded DMA access is introduced.
        original_transfer = backend.dma.sendchannel.transfer
        backend.dma.sendchannel.transfer = lambda *args, **kwargs: None
        backend.timeout = .1
        try:
            try:
                backend.sfpu(descriptor, words)
            except TimeoutError:
                if not backend.failed:
                    raise AssertionError('timeout did not poison backend')
            else:
                raise AssertionError('missing producer did not time out')
            saved = backend.tx_array.copy()
            try:
                backend.sfpu(descriptor, words + 1)
            except RuntimeError:
                pass
            else:
                raise AssertionError('failed backend accepted a retry')
            np.testing.assert_array_equal(backend.tx_array, saved)
        finally:
            backend.dma.sendchannel.transfer = original_transfer
            backend.timeout = 10
        backend.recover()
        np.testing.assert_array_equal(backend.sfpu(descriptor, words), [42, -32768, 32767])
        checks.append('actual_dma_timeout_buffer_retention_restart')
        # Maximum wide reduction and non-16 column tail after all recoveries.
        a = np.full((16, 3072), -128, dtype=np.int8)
        b = np.full((3072, 13), -128, dtype=np.int8)
        np.testing.assert_array_equal(backend.gemm(a, tile_weights(b), 13), a.astype(np.int64) @ b.astype(np.int64))
        checks.append('wide_3072_tail_after_recovery')
        backend.close()
        if not backend.closed:
            raise AssertionError('close did not mark the backend closed')
        report = {'status': 'PASS', 'checks': checks, 'cma_payload_bytes': 110592,
                  'driver_sha256': file_sha256(Path(__file__).with_name('m4_driver.py')),
                  'runner_sha256': file_sha256(__file__), 'counts': dict(backend.counts),
                  'limitation': 'Driver controls only; full-model and performance gates are separate.'}
        args.output.write_text(json.dumps(report, indent=2) + '\n')
        print('M4 PHYSICAL DRIVER CONTROL PASS', json.dumps(report), flush=True)
    finally:
        backend.close()


if __name__ == '__main__':
    main()
