"""Check the publishable source set without reading ignored runtime credentials.

This deterministic guard supplements maintainer review; it is not a claim that
pattern matching proves the absence of all secrets or third-party rights issues.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={'.git','.venv','__pycache__','.pytest_cache','.bootstrap-tmp','runs','data','build','dist'}
PATTERNS={
    'github_token':r'gh[pousr]_[A-Za-z0-9]{30,}',
    'fine_grained_token':r'github_pat_[A-Za-z0-9_]{40,}',
    'private_key':r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'provider_key':r'sk-(?:proj-|ant-)?[A-Za-z0-9_-]{32,}',
    'personal_path':r'(?:/mnt/g/ownCloud|G:[\\/]ownCloud|C:[\\/]Users[\\/]Benja)',
    'original_device':r'GPU-3593cfc0-6056-580c-a2d5-efaf237f94f8',
}


def files():
    for directory,folders,names in os.walk(ROOT):
        folders[:]=sorted(n for n in folders if n not in EXCLUDED and not n.endswith('.egg-info'))
        for name in sorted(names):
            path=Path(directory)/name
            yield path


def main():
    failures=[];manifest={};total=0
    for path in files():
        rel=path.relative_to(ROOT).as_posix()
        if path.is_symlink():failures.append([rel,'symlink']);continue
        size=path.stat().st_size
        if size>1024*1024:failures.append([rel,'unexpected_large_source']);continue
        if path.name in ('connection.json','private-launch.json') or path.name.startswith('.env'):
            failures.append([rel,'private_runtime_file']);continue
        raw=path.read_bytes();total+=len(raw)
        manifest[rel]=hashlib.sha256(raw).hexdigest()
        try:text=raw.decode('utf-8')
        except UnicodeDecodeError:failures.append([rel,'unexpected_binary']);continue
        # This checker contains its own detection expressions, not credentials.
        if rel!='scripts/audit_publication.py':
            for name,pattern in PATTERNS.items():
                if re.search(pattern,text):failures.append([rel,name])
        if path.suffix=='.py':
            try:ast.parse(raw)
            except SyntaxError:failures.append([rel,'invalid_python'])
    required=['README.md','LICENSE','AGENTS.md','requirements.txt','requirements-gpu.txt',
        'runtime/serve.py','examples/agent_client.py','docs/HUMAN_REVIEW.md',
        'docs/SCIENCE.md','docs/API.md','docs/PROVENANCE.md','docs/VALIDATION.md',
        '.github/workflows/ci.yml','SECURITY.md','CONTRIBUTING.md']
    for name in required:
        if name not in manifest:failures.append([name,'missing_required_file'])
    print(json.dumps({'status':'FAIL' if failures else 'PASS','files':len(manifest),
        'bytes':total,'failures':failures,
        'source_set_sha256':hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()},indent=2))
    return bool(failures)


if __name__=='__main__':sys.exit(main())
