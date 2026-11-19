"""Installed-environment evidence, executed only inside the approved container."""
from importlib import metadata
import json
from pathlib import Path
import sys

sys.path.insert(0, '/tests')
from artifacts import normalized_name, require
from processes import write_json


def requirements_satisfied(requirements, installed, extras=('',)):
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    result = []
    for value in requirements:
        requirement = Requirement(value)
        require(requirement.url is None, 'direct dependency URL is outside closed graph')
        active = any(requirement.marker is None or requirement.marker.evaluate(
                     {**default_environment(), 'extra': extra}) for extra in extras)
        name = normalized_name(requirement.name)
        if active:
            require(name in installed and requirement.specifier.contains(installed[name], prereleases=True),
                    'unsatisfied closed requirement: ' + value)
        result.append({'requirement': value, 'active': active})
    return result


def inspect_environment(include_built=False):
    import pip
    require(sys.prefix == '/scratch/venv' and sys.base_prefix == '/usr/local', 'unexpected venv prefix')
    require(sys.flags.isolated and not sys.flags.no_site, 'runtime must use isolated venv with its site')
    require('/usr/local/lib/python3.12/site-packages' not in sys.path, 'base site-packages leaked')
    require(pip.__version__ == '26.3' and Path(pip.__file__).is_relative_to(Path(sys.prefix)),
            'wrong installed pip origin')
    config = Path(sys.prefix, 'pyvenv.cfg').read_text()
    require('include-system-site-packages = false' in config, 'system packages enabled')
    manifest = json.loads(Path('/inputs/manifest.json').read_text())
    expected = {r['name']: r['version'] for r in manifest['records']}
    if include_built:
        expected.update({'fibsem': '0.7.0.dev0', 'vsem-fibsemos': '0.0.0.dev1'})
    distributions = list(metadata.distributions())
    names = [normalized_name(d.metadata['Name']) for d in distributions]
    require(len(names) == len(set(names)), 'duplicate installed distribution')
    installed = {normalized_name(d.metadata['Name']): d.version for d in distributions}
    require(installed == expected, 'installed distribution set differs from closed graph')
    extras = {r['name']: ('', *r['enabled_extras']) for r in manifest['records']}
    entries, requirements, origins = [], {}, {}
    for distribution in distributions:
        name = normalized_name(distribution.metadata['Name'])
        origin = Path(distribution.locate_file('')).resolve()
        require(origin.is_relative_to(Path(sys.prefix)), 'distribution outside fresh venv')
        origins[name] = str(origin)
        requirements[name] = requirements_satisfied(distribution.requires or [], installed, extras.get(name, ('',)))
        entries.extend({'distribution': name, 'group': e.group, 'name': e.name, 'value': e.value}
                       for e in distribution.entry_points)
    discovery = [e for e in entries if e['group'].startswith('fibsem.')]
    allowed = [{'distribution': 'vsem-fibsemos', 'group': 'fibsem.drivers', 'name': 'vsem',
                'value': 'vsem_fibsemos.plugin:driver_entry'}] if include_built else []
    require(discovery == allowed, 'unexpected upstream plugin entry point')
    return {'distributions': installed, 'origins': origins, 'requirements': requirements,
            'entry_points': sorted(entries, key=lambda e: (e['group'], e['name'], e['distribution'])),
            'pip_origin': pip.__file__, 'prefix': sys.prefix, 'base_prefix': sys.base_prefix,
            'sys_path': sys.path, 'status': 'PASS'}


if __name__ == '__main__':
    write_json(sys.argv[1], inspect_environment(include_built='--built' in sys.argv))
