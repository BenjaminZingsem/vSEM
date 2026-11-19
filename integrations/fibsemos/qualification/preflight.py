"""Inert preflight only. Does not fetch, launch, install, build or import a payload."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifacts import (build_preflight, manifest, read_regular, source_inventory,
                       sha256, wheel_inventory, require)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-archive', required=True, type=Path)
    parser.add_argument('--wheel-dir', action='append', type=Path, default=[])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    require(not args.output.exists(), 'preserve prior evidence: choose a fresh output path')
    approved = manifest(root / 'review/replacement-artifact-proposal.json')
    source, source_report = source_inventory(args.source_archive)
    plugin = read_regular(root / 'pyproject.toml', limit=65536)
    result = {'external_execution': False, 'archive_extraction': False,
              'plugin_pyproject_sha256': sha256(plugin),
              'source': source_report,
              'build_preflight': build_preflight(source, plugin, approved),
              'wheels': [], 'artifact_errors': [], 'execution_qualification': 'NOT_RUN'}
    for record in approved['records'] if args.wheel_dir else []:
        wheel = record['wheel']
        candidates = [directory / wheel['filename'] for directory in args.wheel_dir
                      if (directory / wheel['filename']).exists()]
        try:
            require(len(candidates) == 1, 'wheel missing or ambiguous across input directories')
            path = candidates[0]
            read_regular(path, expected_sha=wheel['sha256'], expected_size=wheel['size'])
            _, report = wheel_inventory(path)
            require(report['name'] == record['name'] and report['version'] == record['version'],
                    'wheel package identity mismatch')
            require(report['requires_dist'] == record['requires_dist'], 'wheel dependency metadata mismatch')
            result['wheels'].append(report)
        except Exception as error:
            result['artifact_errors'].append({'name': record['name'], 'error': str(error)[:2000],
                                              'type': type(error).__name__})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8', newline='\n') as output:
        json.dump(result, output, indent=2, sort_keys=True)
        output.write('\n')
    print(json.dumps({'source_members': len(source), 'wheels': len(result['wheels']),
                      'build_preflight': result['build_preflight'], 'external_execution': False,
                      'artifact_errors': result['artifact_errors']}))
    if result['artifact_errors']:
        return 1
    return 0 if result['build_preflight']['status'] == 'PASS' else 2


if __name__ == '__main__':
    sys.exit(main())
