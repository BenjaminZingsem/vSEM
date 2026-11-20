"""Host-side static comparison of stopped-builder wheels to exact source bytes."""
import ast
import email.parser
import email.policy
from pathlib import Path
import re

from artifacts import (compare_source_members, normalized_name, require, sha256,
                       wheel_inventory)


def literal_value(raw, section, key):
    text = raw.decode('utf-8')
    match = re.search(r'(?ms)^\[' + re.escape(section) + r'\]\s*\n(.*?)(?=^\[|\Z)', text)
    require(match is not None, 'missing frozen TOML section')
    value = re.search(r'(?m)^' + re.escape(key) + r'\s*=\s*(.*)', match.group(1))
    require(value is not None, 'missing frozen TOML value')
    lines = match.group(1)[value.start(1):].splitlines()
    for count in range(1, len(lines) + 1):
        try:
            return ast.literal_eval('\n'.join(lines[:count]))
        except (ValueError, SyntaxError):
            continue
    raise ValueError('unsupported frozen TOML literal')


def literal_table(raw, section):
    text = raw.decode('utf-8')
    match = re.search(r'(?ms)^\[' + re.escape(section) + r'\]\s*\n(.*?)(?=^\[|\Z)', text)
    if match is None:
        return {}
    keys = re.findall(r'(?m)^([A-Za-z0-9_-]+)\s*=', match.group(1))
    require(len(keys) == len(set(keys)), 'duplicate frozen TOML key')
    return {key: literal_value(raw, section, key) for key in keys}


def canonical_requirement(raw):
    name_part, separator, marker = raw.partition(';')
    match = re.fullmatch(r'\s*([A-Za-z0-9_.-]+)(.*)', name_part)
    require(match is not None, 'invalid requirement identity')
    suffix = re.sub(r'\s+', '', match[2])
    extras = ''
    if suffix.startswith('['):
        extra_match = re.match(r'\[([A-Za-z0-9_.,-]+)\]', suffix)
        require(extra_match is not None, 'invalid requirement extras')
        extras = '[' + ','.join(sorted(normalized_name(e) for e in extra_match[1].split(','))) + ']'
        suffix = suffix[extra_match.end():]
    if suffix.startswith('(') and suffix.endswith(')'):
        suffix = suffix[1:-1]
    parts = suffix.split(',') if suffix else []
    require(all(re.fullmatch(r'(?:===|==|!=|~=|<=|>=|<|>)[A-Za-z0-9.*+!_-]+', p) for p in parts),
            'unexpected requirement constraint or direct URL')
    # Constraint conjunctions and extra sets have no ordering semantics.
    name = normalized_name(match[1]) + extras + ','.join(sorted(parts))
    if not separator:
        return (name, '')
    tree = ast.parse(marker.strip(), mode='eval')
    allowed = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.Compare, ast.Name,
               ast.Load, ast.Constant, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt,
               ast.GtE, ast.In, ast.NotIn)
    require(all(isinstance(node, allowed) for node in ast.walk(tree)), 'unexpected dependency marker syntax')
    # Parse only as data; no marker string is evaluated on the host.
    return name, ast.dump(tree, include_attributes=False)


def expected_requirements(pyproject):
    base = literal_value(pyproject, 'project', 'dependencies')
    extras = literal_table(pyproject, 'project.optional-dependencies')
    result = list(base)
    for extra, values in extras.items():
        for value in values:
            requirement, separator, marker = value.partition(';')
            condition = '(' + marker.strip() + ') and ' if separator else ''
            result.append(requirement + '; ' + condition + 'extra == ' + repr(normalized_name(extra)))
    return sorted(canonical_requirement(r) for r in result), sorted(normalized_name(e) for e in extras)


def admit_wheel(path, source_files, plugin_files, vsem_license):
    wheel_path = Path(path)
    contents, report = wheel_inventory(path)
    info = report['dist_info']
    require(report['name'] in ('fibsem', 'vsem-fibsemos'), 'unexpected built distribution')
    upstream = report['name'] == 'fibsem'
    project = source_files['pyproject.toml'][1] if upstream else plugin_files['pyproject.toml']
    name = literal_value(project, 'project', 'name')
    version = literal_value(project, 'project', 'version')
    require(report['name'] == normalized_name(name) and report['version'] == version,
            'built package identity differs from source')
    expected, extras = expected_requirements(project)
    require(sorted(canonical_requirement(r) for r in report['requires_dist']) == expected,
            'built dependency metadata differs from frozen source')
    metadata = email.parser.BytesParser(policy=email.policy.default).parsebytes(contents[info + 'METADATA'])
    require(metadata.get_all('Requires-Python') == [literal_value(project, 'project', 'requires-python')],
            'built Python requirement differs from frozen source')
    require(sorted(normalized_name(str(v)) for v in metadata.get_all('Provides-Extra', [])) == extras,
            'built extras differ from frozen source')
    scripts = literal_table(project, 'project.scripts')
    entry_points = {'console_scripts': scripts} if scripts else {}
    gui_scripts = literal_table(project, 'project.gui-scripts')
    if gui_scripts:
        entry_points['gui_scripts'] = gui_scripts
    drivers = literal_table(project, 'project.entry-points."fibsem.drivers"')
    if drivers:
        entry_points['fibsem.drivers'] = drivers
    require(report['entry_points'] == entry_points, 'built entry points differ from frozen source')
    require(report['license'] in ('MIT', 'MIT License'), 'unexpected license declaration')
    wheel = email.parser.BytesParser(policy=email.policy.default).parsebytes(contents[info + 'WHEEL'])
    require(str(wheel['Wheel-Version']) == '1.0' and str(wheel['Root-Is-Purelib']) == 'true'
            and wheel.get_all('Tag') == ['py3-none-any'], 'unexpected built wheel type/tag')
    generated = {'METADATA', 'WHEEL', 'RECORD', 'top_level.txt', 'entry_points.txt'}
    license_bytes = source_files['LICENSE'][1] if upstream else vsem_license
    license_members = []
    for member in contents:
        if not member.startswith(info):
            continue
        relative = member[len(info):]
        if relative in ('licenses/LICENSE', 'LICENSE'):
            require(contents[member] == license_bytes, 'built license bytes changed')
            license_members.append(member)
        else:
            require(relative in generated, 'unexpected generated wheel metadata/startup member')
    if upstream:
        require(bool(license_members), 'upstream wheel lacks expected license material')
        mapping = {path: data for path, (_, data) in source_files.items() if path.startswith('fibsem/')}
        required = {path for path in mapping if path.endswith(('.py', '.yaml'))}
        required.update(path for path in mapping if path.startswith('fibsem/server/ui/assets/'))
        required.update(path for path in mapping if path.startswith('fibsem/server/ui/') and path.endswith('.html'))
        required.add('fibsem/correlation/data/zeta_lut.npz')
        for path, (_, data) in source_files.items():
            if any(path.startswith('.claude/' + kind + '/') for kind in ('skills', 'agents', 'fibsem-agent')):
                if '__pycache__' in path.split('/') or path.endswith('.pyc'):
                    continue
                target = 'fibsem/ai/agent/shipped/' + path
                mapping[target] = data
                required.add(target)
    else:
        mapping = {path[4:]: data for path, data in plugin_files.items() if path.startswith('src/')}
        required = set(mapping)
    report['source_comparison'] = compare_source_members(contents, mapping, required)
    report['generated_members'] = sorted(member for member in contents if member.startswith(info))
    report['license_evidence'] = {'declaration': report['license'], 'source_notice_sha256': sha256(license_bytes),
                                  'wheel_notice_members': license_members,
                                  'binary_redistribution_authorized': False}
    report['filename'] = wheel_path.name
    report['status'] = 'STATIC_ADMISSION_PASS'
    return report
