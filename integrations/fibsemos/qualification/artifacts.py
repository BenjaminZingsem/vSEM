"""Maintainer-owned inert admission checks; never import or extract payloads.

This module uses only the Python standard library. It is safe to use for data
inspection on the private host. Building/installing/importing the inspected
packages still requires the separately confined disposable CPU experiment.
"""
import ast
import base64
import configparser
import csv
import email.parser
import email.policy
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import zipfile

MANIFEST_SHA256 = 'a5e705b56adefa5ba884dbab2dba6ccaf036987648bc1498a05253ebcacd75a2'
SOURCE_COMMIT = '27e72f6cc8f9c014562859450ad9260411acaa12'
SOURCE_SHA256 = 'd24472e24c6a49fc387412d01590c57b64e338cfcf3479aa80c6da10869ee9ac'
SOURCE_TREE = '0a36bb2516ad632b2fc97cc17cc15f066c35333e'
SOURCE_BYTES = 9723828
SOURCE_PREFIX = 'fibsem-os-' + SOURCE_COMMIT + '/'
MAX_ARCHIVE_BYTES = 512 * 1024**2
MAX_MEMBER_BYTES = 128 * 1024**2
MAX_EXPANDED_BYTES = 2 * 1024**3
MAX_MEMBERS = 20000


class AdmissionError(ValueError):
    """Evidence does not establish the required immutable input or output."""


def require(condition, message):
    if not condition:
        raise AdmissionError(message)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def normalized_name(value):
    require(isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', value)),
            'invalid distribution name')
    return re.sub(r'[-_.]+', '-', value).lower()


def read_regular(path, *, limit=MAX_ARCHIVE_BYTES, expected_sha=None, expected_size=None):
    """Read a bounded regular file, rejecting links and concurrent replacements.

    Run only after the writer container has stopped. lstat/open/fstat agreement
    is an additional check, not a claim of safety with an active hostile writer.
    """
    path = Path(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, 'non-regular or linked input')
    require(before.st_size <= limit, 'input exceeds byte limit')
    with path.open('rb') as stream:
        import os
        opened = os.fstat(stream.fileno())
        require((before.st_dev, before.st_ino, before.st_size) ==
                (opened.st_dev, opened.st_ino, opened.st_size), 'input replaced before read')
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    require(len(raw) == before.st_size and len(raw) <= limit, 'input changed or oversized')
    require((opened.st_size, opened.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
            'input changed during read')
    if expected_size is not None:
        require(len(raw) == expected_size, 'input byte size mismatch')
    if expected_sha is not None:
        require(sha256(raw) == expected_sha, 'input SHA256 mismatch')
    return raw


def safe_path(name, *, directory=False):
    require(isinstance(name, str) and bool(name), 'empty archive path')
    require(not any(ord(c) < 32 or ord(c) == 127 for c in name), 'control character in path')
    require(not any(c in name for c in ('\\', ':')), 'non-portable archive path')
    value = name[:-1] if directory and name.endswith('/') else name
    require(bool(value) and all(part not in ('', '.', '..') for part in value.split('/')),
            'unsafe archive path')
    return value


def zip_inventory(archive):
    """Validate before decompression. Returned entries are regular files only."""
    entries = archive.infolist()
    require(len(entries) <= MAX_MEMBERS, 'too many archive members')
    seen, files, expanded = set(), {}, 0
    for item in entries:
        name = safe_path(item.filename, directory=item.is_dir())
        require(name not in seen, 'duplicate archive member')
        seen.add(name)
        kind = stat.S_IFMT(item.external_attr >> 16)
        require(kind in (0, stat.S_IFDIR if item.is_dir() else stat.S_IFREG),
                'special file or symbolic link in archive')
        require(not item.flag_bits & 1, 'encrypted archive member')
        require(item.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                'unexpected archive compression')
        require(item.file_size <= MAX_MEMBER_BYTES, 'oversized archive member')
        expanded += item.file_size
        require(expanded <= MAX_EXPANDED_BYTES, 'oversized expanded archive')
        if not item.is_dir():
            files[name] = item
    for name in seen:
        parts = name.split('/')
        require(not any('/'.join(parts[:i]) in files for i in range(1, len(parts))),
                'file/directory path collision')
    return files


def git_object(kind, raw):
    return hashlib.sha1(kind + b' ' + str(len(raw)).encode('ascii') + b'\0' + raw).digest()


def git_tree(files):
    """Reconstruct Git's tree independently from archive contents and mode bits."""
    root = {}
    for path, (mode, raw) in files.items():
        node = root
        parts = path.split('/')
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            require(isinstance(node, dict), 'tree path collision')
        require(parts[-1] not in node, 'duplicate tree member')
        node[parts[-1]] = (mode, git_object(b'blob', raw))

    def tree(node):
        records = []
        for name, value in node.items():
            is_dir = isinstance(value, dict)
            mode, digest = ('40000', tree(value)) if is_dir else value
            encoded = name.encode('utf-8')
            records.append((encoded + (b'/' if is_dir else b''),
                            mode.encode('ascii') + b' ' + encoded + b'\0' + digest))
        return git_object(b'tree', b''.join(raw for _, raw in sorted(records)))
    return tree(root).hex()


def source_inventory(path):
    raw = read_regular(path, expected_sha=SOURCE_SHA256, expected_size=SOURCE_BYTES)
    files, members = {}, []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = zip_inventory(archive)
        require(len(entries) == 2163, 'upstream source member count mismatch')
        for name, item in entries.items():
            require(name.startswith(SOURCE_PREFIX), 'source outside frozen root')
            relative = name[len(SOURCE_PREFIX):]
            data = archive.read(item)
            mode = '100755' if (item.external_attr >> 16) & 0o111 else '100644'
            files[relative] = (mode, data)
            members.append({'path': relative, 'size': len(data), 'mode': mode, 'sha256': sha256(data)})
    require(git_tree(files) == SOURCE_TREE, 'upstream Git tree mismatch')
    return files, {'sha256': SOURCE_SHA256, 'git_tree': SOURCE_TREE,
                   'members': sorted(members, key=lambda r: r['path'])}


def manifest(path):
    data = json.loads(read_regular(path, limit=1024**2, expected_sha=MANIFEST_SHA256))
    require(data['upstream_commit'] == SOURCE_COMMIT, 'manifest upstream mismatch')
    records = data['records']
    names = [normalized_name(r['name']) for r in records]
    require(len(names) == 52 and len(set(names)) == 52, 'manifest distribution inventory mismatch')
    return data


def build_requirements(raw):
    """Read the frozen inputs' literal build table without loading a build backend.

    This deliberately supports only their observed literal syntax. Unexpected
    configuration stops admission; it is not a general TOML or version resolver.
    Full requirement checks belong to the confined build interpreter.
    """
    text = raw.decode('utf-8')
    sections = re.findall(r'(?ms)^\[build-system\]\s*\n(.*?)(?=^\[|\Z)', text)
    require(len(sections) == 1, 'missing or duplicate literal build-system table')
    fields = {}
    for line in sections[0].splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        match = re.fullmatch(r'([a-z-]+)\s*=\s*(.+)', line)
        require(match is not None, 'unexpected multiline build configuration')
        key, expression = match.groups()
        require(key not in fields, 'duplicate build field')
        try:
            fields[key] = ast.literal_eval(expression)
        except (ValueError, SyntaxError):
            raise AdmissionError('nonliteral build configuration') from None
    require(set(fields) == {'requires', 'build-backend'}, 'unexpected build fields or backend path')
    require(fields['build-backend'] == 'setuptools.build_meta', 'unexpected build backend')
    require(type(fields['requires']) is list and all(type(r) is str for r in fields['requires']),
            'invalid build requirements')
    return fields['requires']


def build_preflight(source_files, plugin_pyproject, approved_manifest):
    upstream = build_requirements(source_files['pyproject.toml'][1])
    plugin = build_requirements(plugin_pyproject)
    require(upstream == ['setuptools>=45', 'wheel', 'setuptools_scm[toml]>=6.2'],
            'unexpected frozen upstream build requirements')
    versions = {normalized_name(r['name']): r['version'] for r in approved_manifest['records']}
    desired = 'setuptools==' + versions['setuptools']
    compatible = plugin == [desired]
    return {'status': 'PASS' if compatible else 'BLOCKED',
            'scope': 'static build pin consistency only; not C1-C8 qualification',
            'upstream_requires': upstream, 'plugin_requires': plugin,
            'approved_plugin_requirement': desired,
            'reason': None if compatible else 'plugin build pin is outside approved execution graph',
            'dynamic_build_requirements_checked': False, 'external_execution': False}


def wheel_inventory(path):
    """Check all RECORD hashes/coverage, names, types and basic wheel structure.

    This does not itself admit a built wheel. The caller must also compare its
    full member/metadata/entry-point inventory to the frozen source mapping.
    """
    raw = read_regular(path)
    members, contents = [], {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = zip_inventory(archive)
        records = [n for n in entries if n.count('/') == 1 and n.endswith('.dist-info/RECORD')]
        require(len(records) == 1, 'wheel must have exactly one RECORD')
        record = records[0]
        info = record.rsplit('/', 1)[0] + '/'
        require(all(not n.split('/')[0].endswith('.dist-info') or n.startswith(info) for n in entries),
                'multiple wheel metadata directories')
        rows = {}
        for row in csv.reader(io.StringIO(archive.read(record).decode('utf-8'))):
            require(len(row) == 3, 'invalid RECORD row')
            name = safe_path(row[0])
            require(name not in rows, 'duplicate RECORD row')
            rows[name] = row[1:]
        require(set(rows) == set(entries), 'RECORD member coverage mismatch')
        for name, item in entries.items():
            data = archive.read(item)
            expected_hash, expected_size = rows[name]
            if name == record:
                require((expected_hash, expected_size) == ('', ''), 'RECORD hashes itself')
            else:
                digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
                require(expected_hash == 'sha256=' + digest and expected_size == str(len(data)),
                        'RECORD hash or size mismatch')
            members.append({'path': name, 'size': len(data), 'sha256': sha256(data)})
            contents[name] = data
    require(info + 'METADATA' in contents and info + 'WHEEL' in contents, 'incomplete wheel metadata')
    metadata = email.parser.BytesParser(policy=email.policy.default).parsebytes(contents[info + 'METADATA'])
    require(not metadata.defects, 'malformed package metadata')
    for key in ('Metadata-Version', 'Name', 'Version'):
        require(len(metadata.get_all(key, [])) == 1, 'missing or duplicate package identity')
    points = {}
    if info + 'entry_points.txt' in contents:
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.optionxform = str
        parser.read_string(contents[info + 'entry_points.txt'].decode('utf-8'))
        require(not parser.defaults(), 'entry-point defaults are not allowed')
        points = {group: dict(parser.items(group)) for group in parser.sections()}
    return contents, {'sha256': sha256(raw), 'size': len(raw),
                      'name': normalized_name(str(metadata['Name'])), 'version': str(metadata['Version']),
                      'requires_dist': [str(v) for v in metadata.get_all('Requires-Dist', [])],
                      'license': str(metadata.get('License-Expression') or metadata.get('License') or ''),
                      'entry_points': points, 'dist_info': info,
                      'members': sorted(members, key=lambda r: r['path'])}


def compare_source_members(contents, source_mapping, required):
    """Byte comparison for every package member; generated metadata is separate."""
    actual = {name for name in contents if not name.split('/')[0].endswith('.dist-info')}
    require(set(required) <= actual, 'required source/assets missing from wheel')
    require(actual <= set(source_mapping), 'unexpected generated code or package member')
    for name in actual:
        require(contents[name] == source_mapping[name], 'wheel differs from frozen source')
    return {'compared_members': len(actual), 'required_members': len(required)}
