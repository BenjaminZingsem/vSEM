"""Controlled worker-boundary failures; not a numerical/GPU reproduction."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from engine import human_episode_types as t
from runtime.finite_human_numerics import _numerical_worker
from runtime.finite_launch_spec import FrozenFiniteLaunch
from runtime.preparation_diagnostics import PreparationDiagnostics


def ticket():
    science = t.ScienceIdentity('generic', 'a'*64, 'b'*64, 'VECTOR', 'c'*64, 'count')
    config = t.ScanRequest(64,64,2e-6,0.,0.,20000).bind(0.,0.,0.)
    return t.BankTicket('job-1','op-test','SETTINGS',t.AuthorityRef('human',1),
        1,1,1,1,1,science,config,t.EpisodeSettings(10),0)


class CapturedBank(BaseException):
    pass


class PreparationDiagnosticTests(unittest.TestCase):
    def test_genuine_worker_preserves_ready_and_failed_channel_records(self):
        for failed in (False, True):
            with self.subTest(failed=failed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory);manifest = root/'manifest.json';manifest.write_bytes(b'{}\n')
                launch = FrozenFiniteLaunch(str(root),hashlib.sha256(manifest.read_bytes()).hexdigest())
                work = ticket()
                handle = t.ScalarBankHandle('bank',1,'d'*64,work.science.solver_source_digest,
                    work.configuration.geometry,work.settings)
                ready = t.BankReady(work, handle)
                hostile = 'sk-' + 'x'*40 + ' /private/specimen/hidden'
                def prepare(value):
                    self.assertIs(value, work)
                    if failed:raise ValueError(hostile)
                    return ready
                registry = SimpleNamespace(science=work.science,prepare=prepare,resolve=None,
                    bounds_m=(0.,1.,0.,1.),cell_size_m=1.)
                captured = []
                class Channel:
                    def __init__(self, role):self.role=role;self.used=False
                    def put(self, value):
                        if self.role=='banks':
                            captured.append(value)
                            raise CapturedBank()
                        return True
                    def get(self):
                        if self.role=='jobs' and not self.used:
                            self.used=True;return (work,)
                        return None
                channels = tuple(Channel(role) for role in ('startup','jobs','facts','banks','cuts','images'))
                out, err = io.StringIO(), io.StringIO()
                with patch('engine.finite_source.FiniteResponseRegistry',return_value=registry), \
                     patch('engine.finite_image_ledger.EpisodeExposureLedger'), \
                     patch('runtime.hierarchical_human_kernel.Wire',side_effect=lambda link,nonce:link), \
                     patch('runtime.finite_human_numerics.time.sleep'), \
                     contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    with self.assertRaises(CapturedBank):
                        _numerical_worker(work.settings,'episode','nonce',channels,1,root,0.,
                            os.getppid(),8,1.,launch)
                self.assertEqual(len(captured),1)
                self.assertEqual(out.getvalue()+err.getvalue(),'')
                if failed:
                    self.assertEqual(captured[0],t.BankFailed(work))
                    paths = list((root/'preparation-diagnostics').glob('*.json'))
                    self.assertEqual(len(paths),1)
                    raw = paths[0].read_text()
                    self.assertNotIn(hostile,raw)
                    self.assertNotIn('/private',raw)
                    value = json.loads(raw)
                    self.assertEqual(value['category'],'VALUE_ERROR')
                    self.assertEqual(value['ticket_id'],work.job_id)
                    self.assertEqual(value['operation_id'],work.request_id)
                    self.assertRegex(value['diagnostic_id'],r'^[0-9a-f]{32}$')
                else:
                    self.assertIs(captured[0],ready)
                    self.assertFalse((root/'preparation-diagnostics').exists())

    def test_bounded_records_and_no_exception_string_or_repr_evaluation(self):
        class HostileError(Exception):
            def __str__(self):raise AssertionError('exception string evaluated')
            def __repr__(self):raise AssertionError('exception repr evaluated')
        with tempfile.TemporaryDirectory() as directory:
            diagnostics = PreparationDiagnostics(directory)
            for _ in range(40):diagnostics.record(ticket(),HostileError())
            records = list(diagnostics.directory.glob('*.json'))
            self.assertEqual(len(records),8)
            self.assertEqual(diagnostics.attempts,8)
            for path in records:
                self.assertLessEqual(path.stat().st_size,1024)
                self.assertEqual(json.loads(path.read_text())['category'],'PREPARATION_ERROR')

    @unittest.skipUnless(os.name=='posix','POSIX permissions')
    def test_private_modes_under_0022(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = os.umask(0o022)
            try:
                diagnostics=PreparationDiagnostics(directory)
                diagnostics.record(ticket(),MemoryError())
                self.assertEqual(stat.S_IMODE(diagnostics.directory.stat().st_mode),0o700)
                path=next(diagnostics.directory.iterdir())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
                self.assertEqual(json.loads(path.read_text())['category'],'MEMORY_ERROR')
            finally:os.umask(previous)

    def test_storage_failure_does_not_replace_original_prepare_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            diagnostics=PreparationDiagnostics(directory)
            original=ValueError('original')
            def fail(work):raise original
            guarded=diagnostics.guard(fail)
            with patch('runtime.preparation_diagnostics.os.open',side_effect=OSError('unavailable')):
                with self.assertRaises(ValueError) as caught:guarded(ticket())
            self.assertIs(caught.exception,original)

    @unittest.skipUnless(os.name=='posix','POSIX symlink fixture')
    def test_existing_diagnostic_directory_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);external=root/'external';external.mkdir()
            (root/'preparation-diagnostics').symlink_to(external,target_is_directory=True)
            PreparationDiagnostics(root).record(ticket(),ValueError())
            self.assertEqual(list(external.iterdir()),[])


if __name__=='__main__':unittest.main()
