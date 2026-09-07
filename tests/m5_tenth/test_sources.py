"""Frozen parent, unchanged timed setup and actual native full-product code."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import m5_tenth_sources as source


class Sources(unittest.TestCase):
    def test_derivation_and_timed_setup(self):
        with tempfile.TemporaryDirectory() as temporary:
            generated = Path(temporary)/'generated'
            source.generate(generated, 'reciprocal')
            for path in generated.glob('*.c'):
                self.assertEqual(path.read_bytes(), (source.ROOT/'build/m5_tenth_reciprocal_v1/generated'/path.name).read_bytes())
            for name in ('runtime.c', 'profile.c', 'hardware.c', 'requant.c'):
                self.assertEqual((generated/name).read_bytes(), (source.ROOT/'build/m5_search_product_v1/generated'/name).read_bytes())

    def test_reject_changed_parent(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(source, 'PARENT', '0'*64):
                with self.assertRaises(RuntimeError): source.generate(Path(temporary)/'generated', 'reciprocal')

    def test_native_full_products(self):
        with tempfile.TemporaryDirectory() as temporary:
            obj = Path(temporary)/'factor.o'
            subprocess.run(['riscv64-unknown-elf-gcc', '-O2', '-fno-fast-math',
                '-march=rv32imc_zicsr', '-mabi=ilp32', '-Iruntime/m5_tenth',
                '-c', 'tests/m5_tenth/mul_host.c', '-o', str(obj)], check=True)
            assembly = subprocess.check_output(['riscv64-unknown-elf-objdump', '-d',
                '--disassemble=pa_tenth_candidate', str(obj)], text=True)
            self.assertEqual(len(re.findall(r'\bmul\b', assembly)), 4)
            self.assertEqual(len(re.findall(r'\bmulhu\b', assembly)), 4)


if __name__ == '__main__': unittest.main()
