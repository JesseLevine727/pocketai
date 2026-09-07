"""Reproducible derivation, charged setup and native full-product instructions."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import m5_search_sources as source


class Sources(unittest.TestCase):
    def test_release_derivation_and_unchanged_timing(self):
        with tempfile.TemporaryDirectory() as temporary:
            generated = Path(temporary)/'generated'
            source.generate(generated, 'product')
            for path in generated.glob('*.c'):
                self.assertEqual(path.read_bytes(), (source.ROOT/'build/m5_search_product_v1/generated'/path.name).read_bytes())
            for name in ('runtime.c', 'profile.c', 'hardware.c', 'numerics.c', 'requant.c'):
                self.assertEqual((generated/name).read_bytes(), (source.ROOT/'build/m5_scalar_affine_v1/generated'/name).read_bytes())

    def test_changed_parent_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(source, 'BASE_GENERATOR', '0'*64):
                with self.assertRaises(RuntimeError):
                    source.generate(Path(temporary)/'generated', 'product')

    def test_rv32_full_width_native_products(self):
        with tempfile.TemporaryDirectory() as temporary:
            obj = Path(temporary)/'multiply.o'
            subprocess.run(['riscv64-unknown-elf-gcc', '-O2', '-fno-fast-math',
                '-march=rv32imc_zicsr', '-mabi=ilp32', '-Iruntime/m5_search',
                '-c', 'tests/m5_search/mul_host.c', '-o', str(obj)], check=True)
            assembly = subprocess.check_output(['riscv64-unknown-elf-objdump', '-d',
                '--disassemble=pa_search_mul_candidate', str(obj)], text=True)
            self.assertEqual(len(re.findall(r'\bmul\b', assembly)), 2)
            self.assertEqual(len(re.findall(r'\bmulhu\b', assembly)), 2)
            self.assertNotIn('__muldi3', assembly)


if __name__ == '__main__':
    unittest.main()
