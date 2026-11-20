"""Real PEP 517 backend hooks with independently checked closed build requirements."""
import importlib
import json
import os
from pathlib import Path
import sys
import tomllib

sys.path.insert(0, '/tests')
from artifacts import require, sha256
from environment import inspect_environment, requirements_satisfied
from processes import write_json


def main():
    project, destination, report = map(Path, sys.argv[1:])
    environment = inspect_environment()
    configuration = tomllib.loads((project / 'pyproject.toml').read_text())['build-system']
    require(set(configuration) == {'requires', 'build-backend'} and
            configuration['build-backend'] == 'setuptools.build_meta', 'unexpected build backend')
    declared = requirements_satisfied(configuration['requires'], environment['distributions'])
    os.chdir(project)
    backend = importlib.import_module(configuration['build-backend'])
    require(Path(backend.__file__).is_relative_to(Path(sys.prefix)), 'backend outside venv')
    dynamic = backend.get_requires_for_build_wheel({})
    require(type(dynamic) is list and all(type(x) is str for x in dynamic), 'invalid dynamic build requirements')
    checked = requirements_satisfied(dynamic, environment['distributions'])
    # Record requirements before executing the build; no implicit installer runs.
    write_json(report.with_name(report.stem + '-requirements.json'),
               {'declared': declared, 'dynamic': checked, 'backend_origin': backend.__file__})
    filename = backend.build_wheel(str(destination), config_settings={})
    require(type(filename) is str and Path(filename).name == filename and filename.endswith('.whl'),
            'backend returned invalid wheel name')
    path = destination / filename
    require(path.is_file() and not path.is_symlink(), 'backend did not produce regular wheel')
    write_json(report, {'filename': filename, 'size': path.stat().st_size,
                        'sha256': sha256(path.read_bytes()), 'status': 'BUILT_NOT_ADMITTED'})


if __name__ == '__main__':
    main()
