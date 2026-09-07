"""Derivation identity and generated-machine-code/charged-setup checks."""
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import m5_scalar_sources as source
from scripts.m5_iterate_sources import function


class Sources(unittest.TestCase):
    def test_generated_release_reproduces(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/'generated'
            source.generate(output, 'affine')
            for path in output.glob('*.c'):
                self.assertEqual(path.read_bytes(),
                    (source.ROOT/'build/m5_scalar_affine_v1/generated'/path.name).read_bytes(), path.name)

    def test_changed_parent_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(source.PINS, {'scripts/m5_iterate_sources.py': '0'*64}):
                with self.assertRaises(RuntimeError):
                    source.generate(Path(temporary)/'generated', 'affine')

    def test_one_native_division_uses_fast_multiply_remainder(self):
        text = subprocess.check_output(['riscv64-unknown-elf-objdump', '-d',
            '--disassemble=pa_m5_dynamic_multiplier', 'build/m5_scalar_affine_v1/m5_runtime.elf'], text=True)
        self.assertEqual(len(re.findall(r'\bdivu\b', text)), 1)
        self.assertEqual(len(re.findall(r'\bmul\b', text)), 1)
        self.assertNotRegex(text, r'\bremu\b|__udivdi3|__umoddi3')

    def test_table_is_inside_forward_and_invalidated_before_rewind(self):
        runtime = (source.ROOT/'build/m5_scalar_affine_v1/generated/runtime.c').read_text()
        body = function(runtime, 'pa_m5_forward_chunk')
        markers = ['pa_scalar_cache_begin(work)', 'pa_scalar_inner_forward_chunk(runtime',
                   'pa_scalar_cache_end()', 'pa_m5_workspace_rewind(work, mark)']
        self.assertEqual([body.index(m) for m in markers], sorted(body.index(m) for m in markers))
        # Both firmware entry points are the old timed callers, not new setup
        # wrappers inserted before their clocks.
        profile = source.ROOT/'build/m5_scalar_affine_v1/generated/profile.c'
        self.assertEqual(hashlib.sha256(profile.read_bytes()).hexdigest(), source.GENERATED['profile.c'])


if __name__ == '__main__':
    unittest.main()
