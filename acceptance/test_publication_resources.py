"""Independent startup/ownership checks; no real GPU required."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from runtime.gpu_resources import PreparedGpuLease, selected_gpu

UUID = 'GPU-00000000-0000-0000-0000-000000000001'


class SelectionTests(unittest.TestCase):
    def test_missing_or_index_selection_never_chooses_a_device(self):
        for value in ('','0','1','cuda:0','GPU-invalid'):
            with self.subTest(value=value), patch.dict(os.environ,{'VSEM_GPU_UUID':value}):
                with self.assertRaises(ValueError): selected_gpu()


@unittest.skipUnless(sys.platform=='linux','Linux flock semantics')
class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'VSEM_GPU_UUID':UUID,
            'VSEM_GPU_LOCK_DIRECTORY':self.directory.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()

    def test_another_clone_cannot_take_active_lease_and_release_reuses_inode(self):
        with PreparedGpuLease('/clone-a') as first:
            inode = first.path.stat().st_ino
            with self.assertRaises(BlockingIOError):
                with PreparedGpuLease('/clone-b'): pass
        with PreparedGpuLease('/clone-b') as second:
            self.assertEqual(second.path.stat().st_ino,inode)

    def test_no_admission_without_lease(self):
        with self.assertRaises(ValueError): PreparedGpuLease().admit_device()

    def test_busy_or_unreadable_gpu_never_changes_visibility_or_kills(self):
        for used,pids in [('321',''),('0','123'),('unknown','')]:
            with self.subTest(used=used,pids=pids), PreparedGpuLease() as lease:
                values=[subprocess.CompletedProcess([],0,used),subprocess.CompletedProcess([],0,pids)]
                with patch('runtime.gpu_resources.subprocess.run',side_effect=values) as run:
                    with patch.dict(os.environ,{'CUDA_VISIBLE_DEVICES':'untouched'}):
                        with self.assertRaises(RuntimeError): lease.admit_device()
                        self.assertEqual(os.environ['CUDA_VISIBLE_DEVICES'],'untouched')
                    self.assertEqual(run.call_count,2)
                    self.assertTrue(all(call.args[0][0]=='nvidia-smi' for call in run.call_args_list))

    def test_explicit_admitted_device_is_the_only_visible_gpu(self):
        with PreparedGpuLease() as lease:
            values=[subprocess.CompletedProcess([],0,'0'),subprocess.CompletedProcess([],0,'')]
            with patch('runtime.gpu_resources.subprocess.run',side_effect=values), patch.dict(os.environ):
                lease.admit_device()
                self.assertEqual(os.environ['CUDA_VISIBLE_DEVICES'],UUID)

    def test_symlink_and_hardlink_lease_rejected(self):
        lease = PreparedGpuLease()
        target = Path(self.directory.name)/'foreign'
        target.write_text('preserve')
        lease.path.symlink_to(target)
        with self.assertRaises(OSError): lease.__enter__()
        lease.path.unlink()
        os.link(target,lease.path)
        with self.assertRaises(ValueError): lease.__enter__()
        self.assertEqual(target.read_text(),'preserve')
