import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.fetch_m4_model import fetch, identity


class PinnedAssetTests(unittest.TestCase):
    def test_existing_identity_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture'
            path.write_bytes(b'known asset')
            digest = hashlib.sha256(b'known asset').hexdigest()
            git = hashlib.sha1(b'blob 11\0known asset').hexdigest()
            self.assertEqual(identity(path, 'git'), git)
            with patch('urllib.request.urlopen') as request:
                fetch('https://unused.invalid', path, 11, expected=digest)
                request.assert_not_called()
                with self.assertRaises(ValueError):
                    fetch('https://unused.invalid', path, 11, expected='0' * 64)
                with self.assertRaises(ValueError):
                    fetch('https://unused.invalid', path, 12, expected=digest)
                self.assertEqual(path.read_bytes(), b'known asset')


if __name__ == '__main__':
    unittest.main()
