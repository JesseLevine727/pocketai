"""Fail-closed derivation tests; all negative inputs are temporary fixtures."""
import contextlib
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml
from scripts import m5_fast_sources as fast


class Sources(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name).resolve()
        mapping = {
            fast.WRAPPER: 'rtl/soc/pa_ibex_wrapper.sv',
            'src/pocketai_pa_pa_m5_rtl_0.1/pa_m5_cluster_top.sv': 'rtl/m5/pa_m5_cluster_top.sv',
        }
        for name in ('ibex_multdiv_fast.sv', 'ibex_load_store_unit.sv', 'ibex_id_stage.sv'):
            mapping['src/lowrisc_ibex_ibex_core_0.1/rtl/' + name] = 'rtl/ibex-orig/rtl/' + name
        for dest, source in mapping.items():
            target = self.work / dest
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(fast.ROOT / source, target)
        for name in ('staged_misaligned', 'branch_stall'):
            shutil.copyfile(fast.ROOT / f'rtl/m5/lsu_patch/{name}.patch', self.work / f'm5_{name}.patch')
        subprocess.run(['bash', str(fast.ROOT / 'rtl/m5/lsu_patch/apply.sh')],
                       cwd=self.work, check=True, capture_output=True)
        self.manifest = self.work / 'test.eda.yml'
        self.manifest.write_text(yaml.safe_dump({'files': [dict(name=p) for p in mapping]}))

    def prepare(self):
        (self.work / 'M5_FAST_TARGET').touch()
        fast.prepare(self.work)

    def check(self):
        with contextlib.redirect_stdout(io.StringIO()):
            fast.check(self.work)

    def test_slow_refused(self):
        with self.assertRaises(RuntimeError): self.check()

    def test_marker_required(self):
        with self.assertRaises(RuntimeError): fast.prepare(self.work)

    def test_idempotent(self):
        self.prepare(); self.check()
        fast.prepare(self.work); self.check()

    def test_unknown_wrapper_refused(self):
        (self.work / fast.WRAPPER).write_text('unknown\n')
        with self.assertRaises(RuntimeError): self.prepare()

    def test_symlink_refused(self):
        target = self.work / fast.WRAPPER
        target.unlink(); target.symlink_to(fast.ROOT / 'rtl/soc/pa_ibex_wrapper.sv')
        with self.assertRaises(RuntimeError): self.prepare()

    def test_wrong_compiler_source_refused(self):
        self.prepare()
        value = yaml.safe_load(self.manifest.read_text())
        value['files'][0]['name'] = str(fast.ROOT / 'rtl/soc/pa_ibex_wrapper.sv')
        self.manifest.write_text(yaml.safe_dump(value))
        with self.assertRaises(RuntimeError): self.check()

    def test_duplicate_source_refused(self):
        self.prepare()
        value = yaml.safe_load(self.manifest.read_text())
        value['files'].append(dict(value['files'][0]))
        self.manifest.write_text(yaml.safe_dump(value))
        with self.assertRaises(RuntimeError): self.check()

    def test_second_hart_change_refused(self):
        self.prepare()
        target = self.work / 'src/pocketai_pa_pa_m5_rtl_0.1/pa_m5_cluster_top.sv'
        target.write_text(target.read_text().replace(') u_core1 (', ') wrong_core1 ('))
        with self.assertRaises(RuntimeError): self.check()

    def test_lsu_change_refused(self):
        self.prepare()
        (self.work / 'src/lowrisc_ibex_ibex_core_0.1/rtl/ibex_load_store_unit.sv').write_text('wrong\n')
        with self.assertRaises(RuntimeError): self.check()

    def test_pipeline_opt_in(self):
        (self.work / 'M5_FAST_PIPELINED').touch()
        self.prepare(); self.check()
        fast.prepare(self.work); self.check()
        (self.work / 'M5_FAST_PIPELINED').unlink()
        with self.assertRaises(RuntimeError): self.check()


if __name__ == '__main__':
    unittest.main()
