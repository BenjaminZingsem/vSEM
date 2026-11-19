"""Independent negative tests, authored data only; never import external payloads."""
import base64
from copy import deepcopy
import csv
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifacts import AdmissionError
from built_wheels import admit_wheel, canonical_requirement
from confinement import entry_command, verify_container
from processes import run_logged
from run_cpu import verify_host


class ConfinementTests(unittest.TestCase):
    def setUp(self):
        self.mounts = {p: (str(Path('synthetic-inputs', p[1:]).resolve()), p == '/out')
                       for p in ('/inputs', '/tests', '/out')}
        self.arguments = dict(image_id='sha256:fixture', image_env=['LANG=C.UTF-8'],
                              mounts=self.mounts, memory=1024, scratch=512,
                              phase='build', owner='synthetic-owner')
        self.value = {
            'Image': 'sha256:fixture',
            'Config': {'Image': 'sha256:fixture', 'User': '10001:10001',
                       'Entrypoint': ['/usr/bin/env'], 'Cmd': entry_command('build'),
                       'Env': ['LANG=C.UTF-8'], 'Labels': {'vsem.m05b1.owner': 'synthetic-owner'}},
            'HostConfig': {'NetworkMode': 'none', 'PidMode': '', 'IpcMode': 'private',
                           'CgroupnsMode': 'private', 'ReadonlyRootfs': True, 'Privileged': False,
                           'CapDrop': ['ALL'], 'SecurityOpt': ['no-new-privileges:true'],
                           'Memory': 1024, 'MemorySwap': 1024,
                           'Tmpfs': {'/scratch': 'rw,exec,nosuid,nodev,size=512,mode=1777'}},
            'Mounts': [{'Type': 'bind', 'Destination': key, 'Source': value[0],
                        'RW': value[1], 'Propagation': 'rprivate'} for key, value in self.mounts.items()],
            'State': {'Status': 'created', 'Running': False},
        }

    def test_valid_before_start(self):
        self.assertEqual(verify_container(self.value, **self.arguments)['status'], 'PASS')

    def test_privilege_namespace_device_and_resource_changes_refused(self):
        changes = {'NetworkMode': 'host', 'PidMode': 'host', 'IpcMode': 'host',
                   'CgroupnsMode': 'host', 'ReadonlyRootfs': False, 'Privileged': True,
                   'CapDrop': [], 'CapAdd': ['SYS_ADMIN'], 'SecurityOpt': ['seccomp=unconfined'],
                   'Devices': ['device'], 'DeviceRequests': ['gpu'], 'DeviceCgroupRules': ['a'],
                   'PortBindings': {'80/tcp': []}, 'Links': ['other'], 'ExtraHosts': ['host'],
                   'VolumesFrom': ['other'], 'Binds': ['/private:/private'], 'PublishAllPorts': True,
                   'Memory': 0, 'MemorySwap': -1, 'NanoCpus': 1, 'CpuQuota': 1000,
                   'CpusetCpus': '0', 'Tmpfs': {'/scratch': 'rw'}}
        for key, value in changes.items():
            with self.subTest(key=key), self.assertRaises(AdmissionError):
                changed = deepcopy(self.value)
                changed['HostConfig'][key] = value
                verify_container(changed, **self.arguments)

    def test_process_identity_environment_and_early_execution_refused(self):
        changes = {'Image': 'different', 'User': '0:0', 'Entrypoint': ['sh'],
                   'Cmd': ['-c', 'payload'], 'Env': ['TOKEN=not-allowed'],
                   'Healthcheck': {'Test': ['CMD', 'payload']}, 'ExposedPorts': {'80/tcp': {}},
                   'Labels': {'vsem.m05b1.owner': 'unrelated'}}
        for key, value in changes.items():
            with self.subTest(key=key), self.assertRaises(AdmissionError):
                changed = deepcopy(self.value)
                changed['Config'][key] = value
                verify_container(changed, **self.arguments)
        self.value['State'] = {'Status': 'running', 'Running': True}
        with self.assertRaises(AdmissionError):
            verify_container(self.value, **self.arguments)

    def test_mount_injection_write_and_propagation_refused(self):
        variants = []
        for key, value in [('RW', True), ('Propagation', 'rshared'), ('Type', 'volume'),
                           ('Source', str(Path('unapproved').resolve())), ('Destination', '/private')]:
            changed = deepcopy(self.value)
            changed['Mounts'][0][key] = value
            variants.append(changed)
        changed = deepcopy(self.value)
        changed['Mounts'].append(deepcopy(changed['Mounts'][0]))
        variants.append(changed)
        for changed in variants:
            with self.subTest(mounts=changed['Mounts']), self.assertRaises(AdmissionError):
                verify_container(changed, **self.arguments)

    def test_private_host_guard_before_side_effects(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(AdmissionError, 'public qualification'):
            verify_host()


PROJECT = b'''[project]
name = "vsem-fibsemos"
version = "0.0.0.dev1"
requires-python = ">=3.10"
dependencies = []
[project.entry-points."fibsem.drivers"]
vsem = "vsem_fibsemos.plugin:driver_entry"
'''
PAYLOAD = b'raise RuntimeError("synthetic wheel must NEVER execute")\n'
PREFIX = 'vsem_fibsemos-0.0.0.dev1.dist-info/'
METADATA = (b'Metadata-Version: 2.4\nName: vsem-fibsemos\nVersion: 0.0.0.dev1\n'
            b'License-Expression: MIT\nRequires-Python: >=3.10\n')


def synthetic_wheel(changes=None, omitted=()):
    contents = {'vsem_fibsemos/plugin.py': PAYLOAD,
                PREFIX + 'METADATA': METADATA,
                PREFIX + 'WHEEL': b'Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n',
                PREFIX + 'entry_points.txt': b'[fibsem.drivers]\nvsem = vsem_fibsemos.plugin:driver_entry\n'}
    contents.update(changes or {})
    for key in omitted:
        del contents[key]
    rows = [[name, 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('='),
             str(len(raw))] for name, raw in contents.items()]
    rows.append([PREFIX + 'RECORD', '', ''])
    record = io.StringIO(newline='')
    csv.writer(record, lineterminator='\n').writerows(rows)
    contents[PREFIX + 'RECORD'] = record.getvalue().encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, raw in contents.items():
            archive.writestr(name, raw)
    return stream.getvalue()


class BuiltAdmissionTests(unittest.TestCase):
    def admit(self, changes=None, omitted=()):
        with tempfile.TemporaryDirectory(prefix='vsem-synthetic-admission-') as directory:
            path = Path(directory) / 'vsem_fibsemos-0.0.0.dev1-py3-none-any.whl'
            path.write_bytes(synthetic_wheel(changes, omitted))
            return admit_wheel(path, {}, {'pyproject.toml': PROJECT, 'src/vsem_fibsemos/plugin.py': PAYLOAD}, b'MIT fixture')

    def test_source_bytes_admitted_without_import(self):
        self.assertEqual(self.admit()['status'], 'STATIC_ADMISSION_PASS')

    def test_changed_or_missing_product_member_refused_despite_valid_record(self):
        with self.assertRaises(AdmissionError):
            self.admit({'vsem_fibsemos/plugin.py': b'changed'})
        with self.assertRaises(AdmissionError):
            self.admit(omitted=('vsem_fibsemos/plugin.py',))

    def test_added_executable_or_generated_member_refused(self):
        for member in ('startup.pth', 'new_module.py', PREFIX + 'unexpected.py'):
            with self.subTest(member=member), self.assertRaises(AdmissionError):
                self.admit({member: PAYLOAD})

    def test_dependency_and_python_constraint_changes_refused(self):
        for metadata in (METADATA + b'Requires-Dist: unapproved>=1\n',
                         METADATA.replace(b'>=3.10', b'>=3.13'),
                         METADATA + b'Provides-Extra: surprise\n'):
            with self.subTest(metadata=metadata), self.assertRaises(AdmissionError):
                self.admit({PREFIX + 'METADATA': metadata})

    def test_entrypoint_license_and_native_tag_changes_refused(self):
        for changes in ({PREFIX + 'entry_points.txt': b'[console_scripts]\nx = bad:run\n'},
                        {PREFIX + 'METADATA': METADATA.replace(b'MIT', b'Proprietary')},
                        {PREFIX + 'licenses/LICENSE': b'changed notice'},
                        {PREFIX + 'WHEEL': b'Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: cp312-linux_x86_64\n'}):
            with self.subTest(changes=changes), self.assertRaises(AdmissionError):
                self.admit(changes)

    def test_markers_are_parsed_as_data_not_executed(self):
        self.assertEqual(canonical_requirement('demo; extra == "one"'),
                         canonical_requirement("demo; extra == 'one'"))
        with self.assertRaises(AdmissionError):
            canonical_requirement('demo; __import__("os").system("payload")')


@unittest.skipUnless(os.name == 'posix', 'POSIX process-group supervisor; exercised on public CPU runner')
class ProcessTests(unittest.TestCase):
    def test_bounded_capture_does_not_forward_workflow_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'output.log'
            result = run_logged([sys.executable, '-I', '-S', '-c', 'print("::warning::synthetic")'],
                                log, env=dict(os.environ), timeout=10)
            self.assertEqual(result['exit_code'], 0)
            self.assertEqual(log.read_bytes(), b'::warning::synthetic\n')

    def test_excess_log_and_timeout_fail_and_reap_child(self):
        with tempfile.TemporaryDirectory() as directory:
            for label, body, expected, settings in (
                ('limit', 'print("x"*4096)', RuntimeError, {'limit': 64, 'timeout': 10}),
                ('timeout', 'import time; time.sleep(10)', TimeoutError, {'timeout': .1}),
            ):
                with self.subTest(label=label), self.assertRaises(expected):
                    run_logged([sys.executable, '-I', '-S', '-c', body], Path(directory) / (label + '.log'),
                               env=dict(os.environ), **settings)


if __name__ == '__main__':
    unittest.main(verbosity=2)
