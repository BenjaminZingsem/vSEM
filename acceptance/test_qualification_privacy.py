"""Actual wrapper creation path; no subprocess/GPU is launched."""
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

if os.name == 'posix':
    from scripts import qualify_release


class BeforeLaunch(BaseException):
    pass


@unittest.skipUnless(os.name == 'posix', 'qualification launcher supports Linux/WSL')
class QualificationPrivacyTests(unittest.TestCase):
    def invoke(self, output, launched):
        def intercept(*args, **kwargs):
            launched.append(kwargs['stdout'].name)
            kwargs['stdout'].close()
            raise BeforeLaunch()
        arguments = ['qualify_release', '--output', str(output),
            '--catalogue-directory', str(output.parent/'catalogue'),
            '--catalogue-manifest-sha256', 'a'*64]
        with patch('sys.argv', arguments), patch.object(qualify_release.subprocess, 'Popen', intercept):
            qualify_release.main()

    @unittest.skipUnless(os.name == 'posix', 'POSIX mode/umask check; Windows needs ACLs')
    def test_private_creation_under_ordinary_umask_and_no_ambient_umask_change(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'new'
            launched = []
            previous = os.umask(0o022)
            try:
                with self.assertRaises(BeforeLaunch):self.invoke(output, launched)
                observed = os.umask(0o022)
                self.assertEqual(observed, 0o022)
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE((output/'service.log').stat().st_mode), 0o600)
                self.assertEqual(len(launched), 1)
            finally:os.umask(previous)

    def test_existing_output_is_not_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'existing';output.mkdir()
            marker = output/'service.log';marker.write_bytes(b'preserved')
            launched = []
            with self.assertRaises(FileExistsError):self.invoke(output, launched)
            self.assertFalse(launched)
            self.assertEqual(marker.read_bytes(), b'preserved')

    @unittest.skipUnless(os.name == 'posix', 'POSIX symlink fixture')
    def test_dangling_output_symlink_cannot_redirect_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);target = root/'must-not-create';link = root/'link'
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(FileExistsError):self.invoke(link, [])
            self.assertFalse(target.exists())


if __name__ == '__main__':unittest.main()
