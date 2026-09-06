"""Short host checks for physical-runner checking and restart/cleanup policy."""
import json
import mmap
import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from zynq import m5_run as runner


FIXTURES = Path('build/m4_runtime_fixtures')


class BoardRunnerTests(unittest.TestCase):
    def test_overflow_rejection_preserves_cache_and_output(self):
        arena = MagicMock()
        arena.maps = {'work': bytearray(4 << 20)}
        arena.maps.update({name: bytearray(4096) for name in ('k', 'v', 'k8', 'kunits')})
        arena.info.return_value = {'status': 1 << 5}
        def complete(request):
            if request == runner.IOC_START:
                struct.pack_into('<2I', arena.maps['work'], 32, 5, 1)
        arena.ioctl.side_effect = complete
        result = runner.run_rejection(arena, 1)
        self.assertEqual(result['cache_valid'], 17)
        self.assertEqual(len(result['cache_regions_unchanged']), 4)
        def corrupt(request):
            complete(request)
            if request == runner.IOC_START:
                arena.maps['k'][0] ^= 1
        arena.ioctl.side_effect = corrupt
        with self.assertRaisesRegex(RuntimeError, 'boundary rejection'):
            runner.run_rejection(arena, 1)

    def make_trace(self):
        manifest = json.loads((FIXTURES / 'manifest.json').read_text())
        case = next(x for x in manifest['cases'] if x['id'] == 'story')
        memory = mmap.mmap(-1, 8 << 20)
        cursor = runner.TRACE_RECORDS
        entries = [(1, 0, 'embedding'), (3, 0, 'h.0.qkv'),
                   (4, 0, 'h.0.context'), (9, 0, 'h.0.output'),
                   (9, 11, 'h.11.output')]
        for kind, layer, name in entries:
            logical = np.load(FIXTURES / case['tensors'][name]['file'])
            rows, columns = logical.shape
            maxima = np.max(np.abs(logical), axis=1) * 256
            exponents = np.maximum(0, np.ceil(np.log2(np.maximum(maxima, 1) / 32767))).astype('<u4')
            values = np.rint(np.ldexp(logical * 256, -exponents.astype(np.int64)[:, None])).astype('<i2')
            self.assertTrue(np.array_equal(np.ldexp(values.astype(np.float64),
                                                   exponents.astype(np.int64)[:, None]) / 256, logical))
            struct.pack_into('<8I', memory, cursor, kind, layer, rows, columns,
                             rows * 4, rows * columns * 2, 0, 0)
            payload = exponents.tobytes() + values.tobytes()
            memory[cursor + 32:cursor + 32 + len(payload)] = payload
            cursor = (cursor + 32 + len(payload) + 63) & ~63
        header = [runner.TRACE_MAGIC, 1, runner.TRACE_LOGITS, 50257, 0, 1,
                  runner.TRACE_RECORDS, len(entries)] + [0] * 56
        struct.pack_into('<64I', memory, 0, *header)
        return memory, case

    def test_selected_frozen_traces_are_exact(self):
        memory, case = self.make_trace()
        try:
            results = runner.check_traces(memory, FIXTURES, case)
            self.assertEqual(len(results), 5)
            self.assertEqual(results[-1]['name'], 'h.11.output')
        finally:
            memory.close()

    def test_trace_mismatch_does_not_keep_mmap_exported(self):
        memory, case = self.make_trace()
        offset = runner.TRACE_RECORDS + 32 + len(case['input_tokens']) * 4
        memory[offset] ^= 1
        try:
            with self.assertRaisesRegex(RuntimeError, 'trace mismatch: embedding'):
                runner.check_traces(memory, FIXTURES, case)
        finally:
            memory.close()

    def test_trace_reference_digest_checked(self):
        memory, case = self.make_trace()
        case['tensors']['embedding']['sha256'] = '0' * 64
        try:
            with self.assertRaisesRegex(RuntimeError, 'reference file digest'):
                runner.check_traces(memory, FIXTURES, case)
        finally:
            memory.close()

    def invoke_main(self, root, close_error=None):
        # The fake arena checks host orchestration only; it is not hardware
        # or Linux DMA qualification. Frozen numerical data above is real.
        fixtures = root / 'fixtures'
        fixtures.mkdir()
        manifest = json.loads((FIXTURES / 'manifest.json').read_text())
        (fixtures / 'manifest.json').write_text(json.dumps(manifest))
        (root / 'layout.json').write_text(json.dumps({
            'arena_bytes': runner.ARENA_BYTES, 'model_sha256': 'f' * 64}))
        (root / 'performance_policy.json').write_bytes(Path('tests/m5/performance_policy.json').read_bytes())
        arena = MagicMock()
        arena.info.return_value = {'owner': 0}
        arena.close.side_effect = close_error
        output = root / 'result.json'
        fake_pynq = types.SimpleNamespace(MMIO=MagicMock(), Overlay=MagicMock())
        with patch.dict(sys.modules, {'pynq': fake_pynq}), \
                patch('builtins.print'), \
                patch.object(sys, 'argv', ['m5_run', '--stage', str(root), '--output', str(output)]), \
                patch.object(runner, 'DmaArena', return_value=arena), \
                patch.object(runner, 'sha256_file', return_value='f' * 64), \
                patch.object(runner, 'load_model'), \
                patch.object(runner, 'load_firmware', return_value='e' * 64) as firmware, \
                patch.object(runner, 'run_rejection', return_value={'status': 'PASS'}), \
                patch.object(runner, 'run_case', return_value={'status': 'PASS'}) as cases:
            if close_error:
                with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
                    runner.main()
            else:
                runner.main()
            self.assertEqual(firmware.call_count, 4, 'each boot needs fresh shared BSS')
            self.assertEqual(cases.call_count, 3)
            for call in cases.call_args_list:
                generation, trace_case = call.args[2:4]
                self.assertIn('steps', generation)
                self.assertIn('tensors', trace_case)
                self.assertEqual(generation['input_tokens'], trace_case['input_tokens'])
            arena.close.assert_called_once()
        return json.loads(output.read_text())

    def test_campaign_restores_each_boot_and_uses_trace_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.invoke_main(Path(directory))
        self.assertEqual(result['status'], 'PASS')
        self.assertIn('cleanup', result)

    def test_cleanup_failure_is_terminal_and_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.invoke_main(Path(directory), RuntimeError('cleanup failed'))
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('cleanup failed', result['cleanup_error'])


if __name__ == '__main__':
    unittest.main()
