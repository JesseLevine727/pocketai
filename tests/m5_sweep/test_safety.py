"""No board imports or mutations: exercise admission and ownership failures."""
import json
from pathlib import Path
import tempfile
import unittest

from zynq.m5_sweep import admitted, checkpoint, expired, safe_close


class Arena:
    def __init__(self, owner, fails=False, stuck=False):
        self.owner, self.fails, self.stuck = owner, fails, stuck
        self.events = []

    def info(self):
        return dict(owner=self.owner)

    def ioctl(self, request):
        self.events.append('drain')
        if self.fails:
            raise TimeoutError('not drained')
        if not self.stuck:
            self.owner = 0

    def close(self):
        self.events.append('close')


class Safety(unittest.TestCase):
    def test_admission_reserves_cleanup(self):
        policy = dict(board_budget_seconds=3600, cleanup_reserve_seconds=120)
        self.assertTrue(admitted(3400, 80, policy))
        self.assertFalse(admitted(3400, 81, policy))
        self.assertFalse(admitted(3500, 1, policy))
        self.assertFalse(admitted(1, -1, policy))
        self.assertFalse(admitted(-1, 1, policy))

    def test_drain_precedes_close(self):
        arena = Arena(1)
        self.assertEqual(safe_close(arena, 7)['owner'], 0)
        self.assertEqual(arena.events, ['drain', 'close'])

    def test_failed_drain_never_closes(self):
        for arena in (Arena(1, fails=True), Arena(1, stuck=True)):
            with self.assertRaises((TimeoutError, RuntimeError)):
                safe_close(arena, 7)
            self.assertEqual(arena.events, ['drain'])

    def test_cpu_owned_close(self):
        arena = Arena(0)
        safe_close(arena, 7)
        self.assertEqual(arena.events, ['close'])

    def test_watchdog_requests_exception_not_force_exit(self):
        with self.assertRaises(TimeoutError):
            expired()

    def test_checkpoint_preserves_failed_sample(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'report.json'
            checkpoint(path, dict(trials=[dict(status='FAIL', seconds=100)]))
            self.assertEqual(json.loads(path.read_text())['trials'][0]['status'], 'FAIL')
            self.assertFalse(path.with_suffix('.tmp').exists())


if __name__ == '__main__':
    unittest.main()
