import hashlib
from pathlib import Path
import tempfile
import unittest
from scripts.verify_m4_deployment import verify_files, verify_deployment


class DeploymentPreflightTests(unittest.TestCase):
    def test_manifest_identity_does_not_hide_changed_asset_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tokenizer.json'
            path.write_bytes(b'original')
            entries = {path.name: {'size': 8, 'sha256': hashlib.sha256(b'original').hexdigest()}}
            self.assertEqual(verify_files(directory, entries)[path.name], entries[path.name]['sha256'])
            path.write_bytes(b'changed!')  # same length and unchanged manifest
            with self.assertRaises(ValueError):
                verify_files(directory, entries)
            self.assertEqual(path.read_bytes(), b'changed!')  # verifier never repairs/overwrites

    def test_path_escape_and_missing_actual_asset_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                verify_files(directory, {'../outside': {'sha256': '0' * 64}})
            with self.assertRaises(FileNotFoundError):
                verify_files(directory, {'missing': {'sha256': '0' * 64}})

    def test_real_frozen_checkpoint_tokenizer_pack_and_fixture_bytes(self):
        result = verify_deployment(Path(__file__).resolve().parents[2])
        self.assertEqual(result['status'], 'DEPLOYMENT_SOURCE_IDENTITY_PASS_NOT_RUNTIME_ACCEPTANCE')
        self.assertEqual(result['pack_arrays_checked'], 248)
        self.assertEqual(result['pack_payload_bytes'], 205271824)
        self.assertEqual(result['independent_tensor_files_checked'], 396)
        self.assertEqual(len(result['model_actual_file_sha256']), 10)
        self.assertIn('OPENAI_LICENSE', result['model_actual_file_sha256'])


if __name__ == '__main__':
    unittest.main()
