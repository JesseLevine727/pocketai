"""Split trace-image selection is pinned and happens before request timing."""
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'zynq'))
runner = importlib.import_module('m5_startup_run')


class SplitRunner(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='m5_startup_runner_')
        self.stage = Path(self.temp.name); (self.stage/'fixtures').mkdir()
        (self.stage/'m5_runtime.bin').write_bytes(b'primary')
        (self.stage/'m5_trace.bin').write_bytes(b'trace')
        self.digest = hashlib.sha256(b'trace').hexdigest()
        (self.stage/'policy.json').write_text(json.dumps({'pinned': {'m5_trace.bin': self.digest}}))
        self.events = []
        def request(*args): self.events.append('START_AND_DELIVER'); return {'status': 'PASS'}
        def load(mmio, path): self.events.append(('LOAD', path.name)); return self.digest
        self.original = patch.object(runner, 'original_full_case', side_effect=request)
        self.loader = patch.object(runner.m, 'load_firmware', side_effect=load)
        self.pynq = patch.dict(sys.modules, {'pynq': types.SimpleNamespace(MMIO=lambda *a: object())})
        self.original.start(); self.load_mock = self.loader.start(); self.pynq.start()

    def tearDown(self):
        self.pynq.stop(); self.loader.stop(); self.original.stop(); self.temp.cleanup()

    def call(self, capture):
        return runner.full_case(None, self.stage/'fixtures', {}, {}, 2, capture, 1, 60)

    def test_trace_image_loaded_before_request(self):
        result = self.call(True)
        self.assertEqual(self.events, [('LOAD', 'm5_trace.bin'), 'START_AND_DELIVER'])
        self.assertEqual(result['execution_image'], 'm5_trace.bin')
        self.assertEqual(result['firmware_sha256'], self.digest)

    def test_plain_request_keeps_primary_image(self):
        result = self.call(False)
        self.assertEqual(self.events, ['START_AND_DELIVER'])
        self.assertEqual(result['execution_image'], 'm5_runtime.bin')

    def test_bad_trace_digest_prevents_load_and_execution(self):
        (self.stage/'m5_trace.bin').write_bytes(b'changed')
        with self.assertRaises(ValueError): self.call(True)
        self.assertEqual(self.events, [])

    def test_failed_trace_load_prevents_execution(self):
        self.load_mock.side_effect = RuntimeError('load verification failed')
        with self.assertRaises(RuntimeError): self.call(True)
        self.assertEqual(self.events, [])


if __name__ == '__main__': unittest.main()
