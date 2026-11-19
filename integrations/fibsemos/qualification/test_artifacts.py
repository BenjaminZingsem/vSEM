"""Negative admission tests using only maintainer-authored synthetic data."""
import base64
import csv
import hashlib
import io
from pathlib import Path
import stat
import sys
import tempfile
import unittest
import warnings
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifacts import (AdmissionError, build_preflight, build_requirements,
                       compare_source_members, git_object, git_tree, read_regular,
                       safe_path, wheel_inventory, zip_inventory)


def archive_bytes(entries):
    output = io.BytesIO()
    with warnings.catch_warnings(), zipfile.ZipFile(output, 'w') as archive:
        warnings.simplefilter('ignore', UserWarning)
        for name, raw in entries:
            archive.writestr(name, raw)
    return output.getvalue()


def wheel_bytes(extra=None, change_record=None):
    prefix = 'sample-1.0.dist-info/'
    contents = {
        'sample/__init__.py': b'raise RuntimeError("synthetic payload must never execute")\n',
        prefix + 'METADATA': b'Metadata-Version: 2.4\nName: sample\nVersion: 1.0\nLicense-Expression: MIT\n',
        prefix + 'WHEEL': b'Wheel-Version: 1.0\nGenerator: fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n',
        prefix + 'entry_points.txt': b'[fibsem.drivers]\nsample = sample:driver\n',
    }
    contents.update(extra or {})
    record = prefix + 'RECORD'
    rows = [[name, 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('='),
             str(len(raw))] for name, raw in contents.items()]
    rows.append([record, '', ''])
    if change_record:
        change_record(rows)
    output = io.StringIO(newline='')
    csv.writer(output, lineterminator='\n').writerows(rows)
    contents[record] = output.getvalue().encode()
    return archive_bytes(contents.items())


class ArchiveTests(unittest.TestCase):
    def inventory(self, entries):
        with zipfile.ZipFile(io.BytesIO(archive_bytes(entries))) as archive:
            return zip_inventory(archive)

    def test_unsafe_names(self):
        for name in ('', '/absolute', '../escape', 'a/../b', 'a//b', './a',
                     'C:/escape', 'a\\b', 'a\nb', 'a\x00b', 'a\x7fb'):
            with self.subTest(name=name), self.assertRaises(AdmissionError):
                safe_path(name)

    def test_duplicate_files(self):
        with self.assertRaisesRegex(AdmissionError, 'duplicate'):
            self.inventory([('a', b'x'), ('a', b'x')])

    def test_file_directory_alias(self):
        for entries in ([('a', b'x'), ('a/b', b'x')], [('a/', b''), ('a', b'x')]):
            with self.subTest(entries=entries), self.assertRaises(AdmissionError):
                self.inventory(entries)

    def test_symlink_refused(self):
        item = zipfile.ZipInfo('link')
        item.create_system = 3
        item.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaisesRegex(AdmissionError, 'symbolic link'):
            self.inventory([(item, b'/private')])

    def test_valid_directory_and_regular_file(self):
        self.assertEqual(set(self.inventory([('a/', b''), ('a/b', b'data')])), {'a/b'})

    def test_expansion_limit_before_decompression(self):
        with zipfile.ZipFile(io.BytesIO(archive_bytes([('a', b'data')]))) as archive:
            archive.infolist()[0].file_size = 129 * 1024**2
            with self.assertRaisesRegex(AdmissionError, 'oversized'):
                zip_inventory(archive)

    def test_git_known_objects_and_ordering(self):
        self.assertEqual(git_object(b'blob', b'hello\n').hex(),
                         'ce013625030ba8dba906f756967f9e9ca394464a')
        self.assertEqual(git_tree({}), '4b825dc642cb6eb9a060e54bf8d69288fbee4904')
        first = {'a.c': ('100644', b'x'), 'a/z': ('100644', b'y')}
        self.assertEqual(git_tree(first), git_tree(dict(reversed(list(first.items())))))
        self.assertNotEqual(git_tree(first), git_tree({**first, 'a.c': ('100755', b'x')}))


class WheelTests(unittest.TestCase):
    def inspect(self, raw):
        with tempfile.TemporaryDirectory(prefix='vsem-inert-wheel-') as directory:
            path = Path(directory) / 'synthetic.whl'
            path.write_bytes(raw)
            return wheel_inventory(path)

    def test_full_inventory_without_executing_payload(self):
        contents, report = self.inspect(wheel_bytes())
        self.assertEqual(report['name'], 'sample')
        self.assertEqual(report['version'], '1.0')
        self.assertEqual(report['license'], 'MIT')
        self.assertEqual(report['entry_points'], {'fibsem.drivers': {'sample': 'sample:driver'}})
        self.assertIn(b'must never execute', contents['sample/__init__.py'])
        self.assertEqual(len(report['members']), 5)

    def test_missing_record_member(self):
        with self.assertRaisesRegex(AdmissionError, 'coverage'):
            self.inspect(wheel_bytes(change_record=lambda rows: rows.pop(0)))

    def test_record_wrong_hash(self):
        with self.assertRaisesRegex(AdmissionError, 'hash or size'):
            self.inspect(wheel_bytes(change_record=lambda rows: rows[0].__setitem__(1, 'sha256=AAAA')))

    def test_record_wrong_size(self):
        with self.assertRaisesRegex(AdmissionError, 'hash or size'):
            self.inspect(wheel_bytes(change_record=lambda rows: rows[0].__setitem__(2, '0')))

    def test_record_duplicate_row(self):
        with self.assertRaisesRegex(AdmissionError, 'duplicate RECORD'):
            self.inspect(wheel_bytes(change_record=lambda rows: rows.append(rows[0])))

    def test_record_self_hash_refused(self):
        with self.assertRaisesRegex(AdmissionError, 'hashes itself'):
            self.inspect(wheel_bytes(change_record=lambda rows: rows[-1].__setitem__(1, 'sha256=AAAA')))

    def test_second_distribution_refused(self):
        with self.assertRaisesRegex(AdmissionError, 'multiple wheel'):
            self.inspect(wheel_bytes({'other-1.0.dist-info/METADATA': b'Name: other\n'}))

    def test_nested_vendor_metadata_is_data_not_second_installed_distribution(self):
        _, report = self.inspect(wheel_bytes({'sample/vendor/other-1.0.dist-info/METADATA':
                                              b'Name: other\nVersion: 1.0\n'}))
        self.assertEqual(report['name'], 'sample')
        self.assertEqual(len(report['members']), 6)

    def test_duplicated_identity_refused(self):
        raw = b'Metadata-Version: 2.4\nName: sample\nName: other\nVersion: 1.0\n'
        with self.assertRaisesRegex(AdmissionError, 'duplicate package identity'):
            self.inspect(wheel_bytes({'sample-1.0.dist-info/METADATA': raw}))

    def test_entry_point_defaults_refused(self):
        with self.assertRaisesRegex(AdmissionError, 'defaults'):
            self.inspect(wheel_bytes({'sample-1.0.dist-info/entry_points.txt':
                                      b'[DEFAULT]\nx = bad:thing\n[fibsem.drivers]\n'}))

    def test_source_comparison_refuses_added_changed_and_missing_code(self):
        approved = {'sample/__init__.py': b'approved'}
        for contents in ({}, {'sample/__init__.py': b'changed'},
                         {**approved, 'extra.pth': b'import something'},
                         {**approved, 'sample/vendor/hidden.dist-info/evil.py': b'unapproved'}):
            with self.subTest(contents=contents), self.assertRaises(AdmissionError):
                compare_source_members(contents, approved, set(approved))
        self.assertEqual(compare_source_members(approved, approved, set(approved))['compared_members'], 1)

    def test_bounded_regular_file_and_identity(self):
        with tempfile.TemporaryDirectory(prefix='vsem-inert-file-') as directory:
            path = Path(directory) / 'data'
            path.write_bytes(b'abcd')
            for kwargs in ({'limit': 3}, {'expected_size': 3}, {'expected_sha': '0' * 64}):
                with self.subTest(kwargs=kwargs), self.assertRaises(AdmissionError):
                    read_regular(path, **kwargs)
            self.assertEqual(read_regular(path, expected_size=4,
                             expected_sha=hashlib.sha256(b'abcd').hexdigest()), b'abcd')
            with self.assertRaises(AdmissionError):
                read_regular(directory)


class BuildPinTests(unittest.TestCase):
    UPSTREAM = b'[build-system]\nrequires = ["setuptools>=45", "wheel", "setuptools_scm[toml]>=6.2"]\nbuild-backend = "setuptools.build_meta"\n'
    MANIFEST = {'records': [{'name': 'setuptools', 'version': '84.2.1'}]}

    def plugin(self, version):
        return ('[build-system]\nrequires = ["setuptools==' + version +
                '"]\nbuild-backend = "setuptools.build_meta"\n').encode()

    def test_original_pin_is_blocked_replacement_pin_consistent(self):
        for version, status in [('75.8.0', 'BLOCKED'), ('84.2.1', 'PASS')]:
            report = build_preflight({'pyproject.toml': ('100644', self.UPSTREAM)},
                                     self.plugin(version), self.MANIFEST)
            self.assertEqual(report['status'], status)
            self.assertFalse(report['external_execution'])
            self.assertFalse(report['dynamic_build_requirements_checked'])

    def test_build_backend_path_refused(self):
        with self.assertRaisesRegex(AdmissionError, 'unexpected build fields'):
            build_requirements(self.plugin('84.2.1') + b'backend-path = ["."]\n')

    def test_unexpected_build_backend_and_code_refused(self):
        for raw in (self.plugin('84.2.1').replace(b'setuptools.build_meta', b'hostile.backend'),
                    self.plugin('84.2.1').replace(b'["setuptools==84.2.1"]', b'__import__("os").getcwd()')):
            with self.subTest(raw=raw), self.assertRaises(AdmissionError):
                build_requirements(raw)


if __name__ == '__main__':
    unittest.main(verbosity=2)
