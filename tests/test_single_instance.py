"""Windows kernel integration tests using isolated names, no classroom UI."""
import os
from pathlib import Path
import subprocess
import sys
import unittest
import uuid

DESKTOP = str(Path(__file__).resolve().parents[1] / 'desktop')
sys.path.insert(0, DESKTOP)
from single_instance import SingleInstance


@unittest.skipUnless(os.name == 'nt', 'Windows named objects')
class SingleInstanceTests(unittest.TestCase):
    def setUp(self):
        self.name = 'Local\\ForestDoctor.Test.' + uuid.uuid4().hex

    def child(self, code):
        return subprocess.Popen([sys.executable, '-u', '-c',
            'import sys; sys.path.insert(0,sys.argv[1]); '
            'from single_instance import SingleInstance; '
            'g=SingleInstance(sys.argv[2]); ' + code, DESKTOP, self.name],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, creationflags=0x08000000)

    def test_concurrent_duplicates_signal_primary_without_owning_instance(self):
        first = SingleInstance(self.name)
        try:
            self.assertTrue(first.acquire())
            children = [self.child('print(g.acquire()); g.activate_existing(); g.close()') for _ in range(8)]
            for child in children:
                out, err = child.communicate(timeout=15)
                self.assertEqual(child.returncode, 0, err)
                self.assertEqual(out.strip(), 'False')
            self.assertTrue(first.activation_requested())
            self.assertFalse(first.activation_requested())
        finally:
            first.close()

    def test_crashed_process_releases_instance_without_stale_file(self):
        child = self.child('print(g.acquire(),flush=True); sys.stdin.readline()')
        try:
            self.assertEqual(child.stdout.readline().strip(), 'True')
            child.kill()
            child.communicate(timeout=10)
            replacement = SingleInstance(self.name)
            try:
                self.assertTrue(replacement.acquire())
            finally:
                replacement.close()
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=10)

    def test_duplicate_launch_does_not_touch_backend(self):
        from unittest.mock import patch
        import launcher
        first = SingleInstance(self.name)
        try:
            self.assertTrue(first.acquire())
            with patch('single_instance.INSTANCE_NAME', self.name), \
                 patch('single_instance.SingleInstance', lambda: SingleInstance(self.name)), \
                 patch.object(sys, 'argv', ['launcher.py', '--port', '19191']), \
                 patch.object(launcher, '_run_primary') as start:
                self.assertEqual(launcher.main(), 0)
                start.assert_not_called()
            self.assertTrue(first.activation_requested())
        finally:
            first.close()


if __name__ == '__main__':
    unittest.main()
