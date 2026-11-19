"""Container-only bootstrap/build/test controller. Never run on the private host."""
import json
import os
from pathlib import Path
import shutil
import sys
import venv
import zipfile

sys.path.insert(0, '/tests')
from artifacts import SOURCE_PREFIX, read_regular, require, sha256, zip_inventory
from processes import run_logged, write_json

PYTHON = '/scratch/venv/bin/python'


def command(args, label, *, cwd=None):
    result = run_logged(args, Path('/out') / (label + '.log'), env=dict(os.environ), cwd=cwd)
    write_json(Path('/out') / (label + '-process.json'), result)
    require(result['exit_code'] == 0, label + ' failed; see bounded evidence log')


def extract_regular(archive_path, destination, prefix=''):
    """Extraction is restricted to fresh scratch INSIDE the networkless container."""
    destination.mkdir()
    with zipfile.ZipFile(archive_path) as archive:
        for name, item in zip_inventory(archive).items():
            require(name.startswith(prefix), 'archive member outside expected root')
            relative = name[len(prefix):]
            target = destination / relative
            require(target.is_relative_to(destination), 'extraction escape')
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as output:
                output.write(archive.read(item))
            target.chmod(0o755 if (item.external_attr >> 16) & 0o111 else 0o644)


def bootstrap():
    require(os.name == 'posix' and os.getuid() == 10001 and
            Path('/inputs/manifest.json').is_file() and sys.flags.no_site and sys.flags.isolated,
            'approved isolated container entry required')
    require(sys.version_info[:3] == (3, 12, 16), 'base Python version mismatch')
    os.umask(0o022)
    Path('/scratch/home').mkdir()
    Path('/scratch/tmp').mkdir()
    Path('/scratch/mpl').mkdir()
    approved = json.loads(Path('/inputs/manifest.json').read_text())
    pip = next(r for r in approved['records'] if r['name'] == 'pip')['wheel']
    path = Path('/inputs/wheels') / pip['filename']
    read_regular(path, expected_sha=pip['sha256'], expected_size=pip['size'])
    extract_regular(path, Path('/scratch/pip-bootstrap'))
    venv.EnvBuilder(with_pip=False, system_site_packages=False).create('/scratch/venv')
    command(['/usr/local/bin/python', '-I', '-S', '-B', '/tests/pip_bootstrap.py',
             '--isolated', '--disable-pip-version-check', '--no-input', '--python', PYTHON,
             'install', '--no-index', '--no-cache-dir', '--no-deps', '--require-hashes',
             '--only-binary=:all:', '-r', '/inputs/requirements-closed.txt'], 'installer')
    command([PYTHON, '-I', '-B', '/tests/environment.py', '/out/environment.json'], 'environment')


def build():
    bootstrap()
    Path('/out/wheels').mkdir()
    extract_regular(Path('/inputs/upstream.zip'), Path('/scratch/upstream'), SOURCE_PREFIX)
    shutil.copytree('/inputs/plugin', '/scratch/plugin')
    for label, project in [('upstream', '/scratch/upstream'), ('plugin', '/scratch/plugin')]:
        command([PYTHON, '-I', '-B', '/tests/backend_build.py', project, '/out/wheels',
                 '/out/build-' + label + '.json'], 'build-' + label)


def runtime():
    bootstrap()
    admission = json.loads(Path('/admitted/admission.json').read_text())
    for record in admission['wheels']:
        read_regular(Path('/admitted/wheels') / record['filename'],
                     expected_sha=record['sha256'], expected_size=record['size'])
    command([PYTHON, '-I', '-B', '-m', 'pip', '--isolated', '--disable-pip-version-check',
             '--no-input', 'install', '--no-index', '--no-deps', '--no-cache-dir', '--require-hashes',
             '--only-binary=:all:', '-r', '/admitted/requirements-built.txt'], 'install-built')
    command([PYTHON, '-I', '-B', '/tests/environment.py', '/out/runtime-environment.json', '--built'],
            'runtime-environment')
    # The original source-only suite has its own interpreter and remains unchanged.
    legacy = run_logged([PYTHON, '-I', '-B', '-m', 'unittest', 'discover', '-s',
                         '/inputs/legacy/acceptance', '-p', 'test_fibsemos_*.py', '-v'],
                        '/out/original-acceptance.log', env=dict(os.environ))
    write_json('/out/original-acceptance-process.json', legacy)
    genuine = run_logged([PYTHON, '-I', '-B', '/tests/genuine.py'],
                         '/out/genuine.log', env=dict(os.environ))
    write_json('/out/genuine-process.json', genuine)
    require(legacy['exit_code'] == 0 and genuine['exit_code'] == 0, 'CPU acceptance failed')


if __name__ == '__main__':
    {'build': build, 'runtime': runtime}[sys.argv[1]]()
