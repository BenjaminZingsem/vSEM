"""Approved disposable GitHub CPU experiment. Refuses private/local execution.

Only exact public inputs enter containers. All child output is bounded and
encoded before emission. No owner credentials, repository .git or runner control
files are mounted. No payload code runs in this host script.
"""
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import sys
import tempfile
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifacts import (build_preflight, manifest, read_regular, require,
                       sha256, source_inventory, wheel_inventory)
from built_wheels import admit_wheel
from confinement import entry_command, verify_container
from fetch import fetch_inputs
from processes import run_logged, write_json

BRANCH = 'refs/heads/qualification/fibsemos-m05b1-20261119'
BASE = '20f87901566b3be070fc05f7ab4d8c64b5b0fa4a'
PRODUCT = 'ca6825fb0cdcaa8aa1c4fa176965720757c195ef'


def emit(value):
    print(json.dumps(value, ensure_ascii=True, sort_keys=True), flush=True)


def evidence_file(path, label):
    raw = read_regular(path, limit=32 * 1024**2)
    parts = [base64.b64encode(raw[i:i+12288]).decode('ascii') for i in range(0, len(raw), 12288)]
    emit({'evidence_file': label, 'bytes': len(raw), 'sha256': sha256(raw), 'chunks': len(parts)})
    for index, part in enumerate(parts):
        emit({'evidence_chunk': label, 'index': index, 'base64': part})


def verify_host():
    require(sys.platform == 'linux' and os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and os.environ.get('GITHUB_REPOSITORY') == 'BenjaminZingsem/vSEM'
            and os.environ.get('GITHUB_EVENT_NAME') == 'push'
            and os.environ.get('GITHUB_REF') == BRANCH, 'approved disposable public qualification runner required')
    release = Path('/etc/os-release').read_text()
    require('VERSION_ID="22.04"' in release, 'unexpected hosted runner OS')
    require(re.fullmatch('[0-9a-f]{40}', os.environ.get('GITHUB_SHA', '')) is not None, 'invalid job source SHA')
    require(not any(Path('/dev').glob('nvidia*')), 'unexpected GPU device')
    return {'source_sha': os.environ['GITHUB_SHA'], 'runner_image': os.environ.get('ImageVersion'),
            'image_os': os.environ.get('ImageOS'), 'kernel': platform.release(),
            'cpu_count': os.cpu_count(), 'python': sys.version, 'os_release': release}


def main():
    host = verify_host()  # Before any network, temp mounts, Docker or payload execution.
    root = Path(__file__).resolve().parents[3]
    work = Path(tempfile.mkdtemp(prefix='vsem-m05b1-', dir=os.environ['RUNNER_TEMP']))
    for folder in ('inputs', 'tests', 'evidence', 'logs', 'home', 'docker', 'admitted', 'outputs'):
        (work / folder).mkdir()
    evidence, inputs, tests = work / 'evidence', work / 'inputs', work / 'tests'
    environment = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': str(work / 'home'), 'LANG': 'C.UTF-8',
                   'DOCKER_CONFIG': str(work / 'docker')}
    identity = os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT']
    require(re.fullmatch(r'[0-9]+-[0-9]+', identity) is not None, 'invalid owned run identity')
    owner = 'm05b1-' + identity
    containers, counter, mounted = [], 0, False

    def execute(args, *, timeout=10500, check=True):
        nonlocal counter
        counter += 1
        path = work / 'logs' / ('command-%03d.log' % counter)
        result = run_logged(args, path, env=environment, cwd=work, timeout=timeout)
        if check:
            require(result['exit_code'] == 0, 'host command failed; see ' + path.name)
        return result, read_regular(path, limit=16 * 1024**2)

    def git(*args):
        return execute(['git', '-C', str(root), *args], timeout=60)[1]

    def inspect_container(name):
        return json.loads(execute(['docker', 'inspect', name], timeout=30)[1])[0]

    report = {'status': 'INCOMPLETE', 'host': host, 'stages': {}}
    failure = None
    try:
        require(git('rev-parse', 'HEAD').decode().strip() == host['source_sha'], 'checkout/head mismatch')
        require(not git('status', '--porcelain'), 'dirty public qualification checkout')
        # Runtime product remains exact M05A; the owner approved precisely this packaging exception.
        product_paths = git('ls-tree', '-r', '--name-only', PRODUCT, 'integrations/fibsemos/src').decode().splitlines()
        require(git('ls-files', 'integrations/fibsemos/src').decode().splitlines() == product_paths,
                'runtime plugin source file set changed')
        plugin_files = {}
        for name in [*product_paths, 'integrations/fibsemos/pyproject.toml']:
            raw = (root / name).read_bytes()
            frozen = git('show', PRODUCT + ':' + name)
            if name.endswith('pyproject.toml'):
                require(frozen.count(b'setuptools==75.8.0') == 1, 'unexpected original build pin')
                frozen = frozen.replace(b'setuptools==75.8.0', b'setuptools==84.2.1')
            require(raw == frozen, 'product exceeds approved packaging exception')
            relative = name.removeprefix('integrations/fibsemos/')
            plugin_files[relative] = raw
            target = inputs / 'plugin' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        legacy = inputs / 'legacy'
        shutil.copytree(inputs / 'plugin/src', legacy / 'integrations/fibsemos/src')
        for name in ('acceptance/test_fibsemos_contract.py', 'acceptance/test_fibsemos_preflight.py'):
            raw = (root / name).read_bytes()
            require(raw == git('show', BASE + ':' + name), 'original acceptance changed')
            target = legacy / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        for name in ('.github/workflows/ci.yml', 'requirements.txt', 'requirements-gpu.txt', 'docs/MAINTENANCE_POLICY.md'):
            require((root / name).read_bytes() == git('show', BASE + ':' + name), 'protected baseline changed')
        approved = manifest(root / 'integrations/fibsemos/review/replacement-artifact-proposal.json')
        shutil.copyfile(root / 'integrations/fibsemos/review/replacement-artifact-proposal.json', inputs / 'manifest.json')
        for path in Path(__file__).parent.glob('*.py'):
            shutil.copyfile(path, tests / path.name)
        fetch_report, config = fetch_inputs(approved, inputs)
        write_json(evidence / 'fetch.json', fetch_report)
        source_files, source_report = source_inventory(inputs / 'upstream.zip')
        write_json(evidence / 'source-inventory.json', source_report)
        preflight = build_preflight(source_files, plugin_files['pyproject.toml'], approved)
        write_json(evidence / 'build-preflight.json', preflight)
        require(preflight['status'] == 'PASS', 'build requirement conflict')
        wheels = []
        for record in approved['records']:
            path = inputs / 'wheels' / record['wheel']['filename']
            contents, inventory = wheel_inventory(path)
            require(inventory['sha256'] == record['wheel']['sha256'] and inventory['name'] == record['name']
                    and inventory['version'] == record['version'] and inventory['requires_dist'] == record['requires_dist'],
                    'frozen wheel inventory mismatch')
            wheels.append(inventory)
            if record['name'] == 'pip':
                write_json(inputs / 'bootstrap-pip.json', {'module_sha256': sha256(contents['pip/__init__.py'])})
        write_json(evidence / 'wheel-inventory.json', wheels)
        requirements = ['/' + str((inputs / 'wheels' / r['wheel']['filename']).relative_to(work)).replace('\\', '/')
                        + ' --hash=sha256:' + r['wheel']['sha256'] for r in approved['records']]
        (inputs / 'requirements-closed.txt').write_text('\n'.join(requirements) + '\n', encoding='utf-8')
        # Verify compressed bytes already checked at fetch, then their uncompressed diff IDs without untarring.
        diff_ids = []
        for layer in approved['base_environment']['layers']:
            digest, total = hashlib.sha256(), 0
            with gzip.open(inputs / 'oci' / (layer['digest'][7:] + '.tar.gz'), 'rb') as stream:
                while True:
                    block = stream.read(1024**2)
                    if not block:
                        break
                    total += len(block)
                    require(total < 2 * 1024**3, 'expanded base layer exceeds inspection envelope')
                    digest.update(block)
            diff_ids.append('sha256:' + digest.hexdigest())
        require(diff_ids == config['rootfs']['diff_ids'], 'base layer diff-ID mismatch')
        image = approved['base_environment']['image']
        execute(['docker', 'pull', '--platform', 'linux/amd64', image])
        image_data = json.loads(execute(['docker', 'image', 'inspect', image], timeout=60)[1])[0]
        image_id = approved['base_environment']['config']['digest']
        require(image_data['Id'] == image_id and image_data['RootFS']['Layers'] == diff_ids
                and image_data['Architecture'] == 'amd64' and image_data['Os'] == 'linux', 'loaded OCI identity mismatch')
        require(not image_data['Config'].get('Volumes') and not image_data['Config'].get('Healthcheck'),
                'unapproved automatic image mounts/healthcheck')
        security = json.loads(execute(['docker', 'info', '--format', '{{json .SecurityOptions}}'], timeout=60)[1])
        require('name=seccomp,profile=builtin' in security, 'Docker builtin seccomp unavailable')
        write_json(evidence / 'base-image.json', {'id': image_id, 'diff_ids': diff_ids, 'security_options': security,
                    'docker_version': execute(['docker', 'version', '--format', '{{json .Server}}'], timeout=60)[1].decode()})
        available = int(re.search(r'^MemAvailable:\s+(\d+)', Path('/proc/meminfo').read_text(), re.M)[1]) * 1024
        disk = shutil.disk_usage(work).free
        memory = available - max(1024**3, available // 8)
        require(memory > 2 * 1024**3, 'runner lacks sufficient measured memory for closed environment')
        scratch, output_size = memory * 3 // 4, min(memory // 4, disk // 4)
        write_json(evidence / 'resources.json', {'available_memory': available, 'available_disk': disk,
                    'container_memory': memory, 'scratch_limit': scratch, 'output_limit': output_size,
                    'available_cpus': os.cpu_count(), 'job_timeout_minutes': 180})
        execute(['sudo', '-n', 'mount', '-t', 'tmpfs', '-o',
                 'size=' + str(output_size) + ',mode=0755,nosuid,nodev,noexec', 'tmpfs', str(work / 'outputs')], timeout=30)
        mounted = True

        def run_container(phase, admitted=False):
            output = work / 'outputs' / phase
            execute(['sudo', '-n', 'mkdir', str(output)], timeout=30)
            execute(['sudo', '-n', 'chown', '10001:10001', str(output)], timeout=30)
            mounts = {'/inputs': (str(inputs), False), '/tests': (str(tests), False), '/out': (str(output), True)}
            if admitted:
                mounts['/admitted'] = (str(work / 'admitted'), False)
            name = owner + '-' + phase
            command = ['docker', 'create', '--name', name, '--label', 'vsem.m05b1.owner=' + owner,
                       '--platform', 'linux/amd64', '--network', 'none', '--user', '10001:10001',
                       '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                       '--ipc', 'private', '--cgroupns', 'private', '--memory', str(memory),
                       '--memory-swap', str(memory), '--tmpfs',
                       '/scratch:rw,exec,nosuid,nodev,size=' + str(scratch) + ',mode=1777',
                       '--workdir', '/scratch', '--entrypoint', '/usr/bin/env',
                       '--log-driver', 'local', '--log-opt', 'max-size=16m', '--log-opt', 'max-file=1']
            for destination, (source, writable) in mounts.items():
                command += ['--mount', 'type=bind,src=' + source + ',dst=' + destination +
                            ',bind-propagation=rprivate' + ('' if writable else ',readonly')]
            containers.append(name)  # Enables labelled cleanup even if create's stdout is lost.
            execute([*command, image_id, *entry_command(phase)], timeout=60)
            inspected = inspect_container(name)
            write_json(evidence / (phase + '-configuration.json'), inspected)
            assertion = verify_container(inspected, image_id=image_id, image_env=image_data['Config']['Env'],
                                          mounts=mounts, memory=memory, scratch=scratch, phase=phase, owner=owner)
            write_json(evidence / (phase + '-configuration-check.json'), assertion)
            result, raw = execute(['docker', 'start', '--attach', name], check=False)
            ended = inspect_container(name)
            require(not ended['State']['Running'] and ended['State']['Status'] == 'exited', 'container not terminal')
            write_json(evidence / (phase + '-terminal.json'), ended['State'])
            report['stages'][phase] = {'exit_code': ended['State']['ExitCode'], 'oom': ended['State']['OOMKilled']}
            require(result['exit_code'] == ended['State']['ExitCode'], 'attach and container exit codes disagree')
            if phase == 'probe':
                probe = json.loads(raw)
                require(result['exit_code'] == 0 and probe['status'] == 'PASS', 'independent isolation probe failed')
                write_json(evidence / 'independent-probe.json', probe)
            # Writer is terminal. Read data only; never execute anything from /out on the host.
            for path in sorted(output.iterdir()):
                if path.name == 'wheels':
                    continue
                require(re.fullmatch(r'[a-z0-9_-]+\.(json|log)', path.name) is not None,
                        'unexpected output name')
                raw_file = read_regular(path, limit=16 * 1024**2)
                (evidence / (phase + '-' + path.name)).write_bytes(raw_file)
            return output, ended['State']['ExitCode']

        emit({'milestone': 'exact inputs admitted; starting independent isolation probe', 'source': host['source_sha']})
        run_container('probe')
        emit({'milestone': 'isolation probe passed; starting real offline builds'})
        output, code = run_container('build')
        require(code == 0, 'real offline build failed')
        produced = sorted((output / 'wheels').iterdir())
        require(len(produced) == 2, 'unexpected number of built wheels')
        admissions = [admit_wheel(path, source_files, plugin_files, (root / 'LICENSE').read_bytes()) for path in produced]
        require({r['name'] for r in admissions} == {'fibsem', 'vsem-fibsemos'}, 'missing/duplicated built distribution')
        write_json(evidence / 'built-wheel-admission.json', {'wheels': admissions})
        (work / 'admitted/wheels').mkdir()
        for path, record in zip(produced, admissions):
            raw = read_regular(path, expected_sha=record['sha256'], expected_size=record['size'])
            (work / 'admitted/wheels' / record['filename']).write_bytes(raw)
        write_json(work / 'admitted/admission.json', {'wheels': admissions})
        (work / 'admitted/requirements-built.txt').write_text('\n'.join(
            '/admitted/wheels/' + r['filename'] + ' --hash=sha256:' + r['sha256'] for r in admissions) + '\n')
        emit({'milestone': 'built wheels passed independent static admission; starting genuine runtime tests'})
        _, code = run_container('runtime', admitted=True)
        require(code == 0, 'genuine runtime acceptance failed')
        report['status'] = 'CPU_EXPERIMENT_PASS_PENDING_FRONTIER_AUDIT_AND_ORDINARY_CI'
    except BaseException as error:
        failure = error
        report['status'] = 'FAIL'
        report['diagnostic'] = traceback.format_exc()
    finally:
        cleanup = []
        for name in reversed(containers):
            try:
                result, raw = execute(['docker', 'inspect', name], timeout=30, check=False)
                if result['exit_code'] != 0:
                    _, listing = execute(['docker', 'container', 'ls', '--all', '--quiet',
                                          '--filter', 'name=^/' + name + '$'], timeout=30)
                    require(not listing.strip(), 'owned container inspection failed but container still exists')
                    cleanup.append({'name': name, 'state': 'absent'})
                    continue
                existing = json.loads(raw)[0]
                require(existing['Config'].get('Labels', {}).get('vsem.m05b1.owner') == owner,
                        'refuse cleanup of a container without this run ownership label')
                execute(['docker', 'rm', '--force', name], timeout=60)
                _, listing = execute(['docker', 'container', 'ls', '--all', '--quiet',
                                      '--filter', 'name=^/' + name + '$'], timeout=30)
                require(not listing.strip(), 'owned container remains after cleanup')
                cleanup.append({'name': name, 'state': 'removed'})
            except Exception:
                cleanup.append({'name': name, 'state': 'FAILED', 'traceback': traceback.format_exc()})
        if mounted:
            try:
                execute(['sudo', '-n', 'umount', str(work / 'outputs')], timeout=60)
            except Exception:
                cleanup.append({'output_mount': 'FAILED', 'traceback': traceback.format_exc()})
        report['cleanup'] = cleanup
        if any(r.get('state') == 'FAILED' or r.get('output_mount') == 'FAILED' for r in cleanup):
            report['status'] = 'FAIL_CLEANUP'
        write_json(evidence / 'host-result.json', report)
        # Only bounded text evidence and member/hash inventories; no source, wheel or image payloads.
        for folder in (evidence, work / 'logs'):
            for path in sorted(folder.iterdir()):
                evidence_file(path, folder.name + '/' + path.name)
        emit({'qualification_status': report['status'], 'source': host['source_sha'],
              'main_merge_authorized': False, 'release_authorized': False})
    return int(failure is not None or report['status'].startswith('FAIL'))


if __name__ == '__main__':
    def terminated(signum, frame):
        raise SystemExit('qualification supervisor received termination')
    signal.signal(signal.SIGTERM, terminated)
    sys.exit(main())
