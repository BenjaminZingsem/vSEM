"""Run only the verified pip wheel, in an isolated/no-site base interpreter."""
import hashlib
import json
from pathlib import Path
import runpy
import sys


def main():
    if not sys.flags.isolated or not sys.flags.no_site or sys.version_info[:3] != (3, 12, 16):
        raise RuntimeError('isolated pinned base interpreter required')
    source = Path('/scratch/pip-bootstrap')
    expected = json.loads(Path('/inputs/bootstrap-pip.json').read_text())
    module = source / 'pip/__init__.py'
    if hashlib.sha256(module.read_bytes()).hexdigest() != expected['module_sha256']:
        raise RuntimeError('bootstrap pip source changed')
    sys.path.insert(0, str(source))
    import pip
    if pip.__version__ != '26.3' or Path(pip.__file__) != module:
        raise RuntimeError('unexpected installer origin/version')
    print(json.dumps({'bootstrap_pip': pip.__version__, 'origin': str(module),
                      'base_site_disabled': True}), flush=True)
    sys.argv = ['pip', *sys.argv[1:]]
    runpy.run_module('pip', run_name='__main__', alter_sys=True)


if __name__ == '__main__':
    main()
