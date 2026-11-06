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
import struct
import sys
import zlib

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


def screenshot_manifest(root):
    """Only declared, reviewed documentation screenshots may be binary assets."""
    path=root/'docs/screenshots/captures.json'
    if not path.exists():return {}
    data=json.loads(path.read_text(encoding='utf-8'))
    assets={}
    for item in data['captures']:
        name=item['file']
        if not re.fullmatch(r'[a-z0-9-]+\.png',name):
            raise ValueError('invalid screenshot name')
        rel='docs/screenshots/'+name
        if rel in assets:raise ValueError('duplicate screenshot')
        if not re.fullmatch(r'[0-9a-f]{64}',item['sha256']):
            raise ValueError('invalid screenshot digest')
        if any(type(item[key]) is not int or not 1<=item[key]<=4096 for key in ('width','height')):
            raise ValueError('invalid screenshot dimensions')
        assets[rel]=item
    return assets


def validate_screenshot(raw,item):
    """Check hashes and PNG structure; reject embedded text and trailing data.

    This is a content guard, not a substitute for visually reviewing screenshots.
    Only Chrome's image/color chunks are allowed, with no arbitrary metadata.
    """
    if len(raw)>2*1024*1024:raise ValueError('oversized screenshot')
    if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('screenshot digest mismatch')
    if not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('invalid PNG signature')
    offset=8;seen=[];payload=[]
    while offset<len(raw):
        if len(raw)-offset<12:raise ValueError('truncated PNG chunk')
        length=struct.unpack('>I',raw[offset:offset+4])[0]
        kind=raw[offset+4:offset+8];end=offset+12+length
        if end>len(raw):raise ValueError('truncated PNG payload')
        content=raw[offset+8:end-4]
        crc=struct.unpack('>I',raw[end-4:end])[0]
        if zlib.crc32(kind+content)&0xffffffff!=crc:raise ValueError('PNG CRC mismatch')
        if kind not in (b'IHDR',b'IDAT',b'IEND',b'sRGB'):raise ValueError('unapproved PNG metadata')
        if not seen and kind!=b'IHDR':raise ValueError('missing PNG header')
        if kind==b'IHDR':
            if seen or length!=13:raise ValueError('invalid PNG header')
            width,height,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',content)
            if (width,height)!=(item['width'],item['height']):raise ValueError('PNG dimensions mismatch')
            if depth!=8 or color not in (2,6) or compression or filtering or interlace:
                raise ValueError('unexpected PNG encoding')
        elif kind==b'sRGB':
            if b'sRGB' in seen or b'IDAT' in seen or length!=1 or content[0]>3:
                raise ValueError('invalid PNG color intent')
        elif kind==b'IDAT':
            if b'IDAT' in seen and seen[-1]!=b'IDAT':raise ValueError('noncontiguous PNG data')
            payload.append(content)
        elif kind==b'IEND':
            if length or end!=len(raw) or not payload:raise ValueError('invalid PNG end')
        seen.append(kind);offset=end
    if not seen or seen[-1]!=b'IEND':raise ValueError('missing PNG end')
    expected=item['height']*(1+item['width']*(3 if color==2 else 4))
    decoder=zlib.decompressobj()
    pixels=decoder.decompress(b''.join(payload),expected+1)
    if len(pixels)!=expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError('invalid PNG raster length')


def files():
    for directory,folders,names in os.walk(ROOT):
        folders[:]=sorted(n for n in folders if n not in EXCLUDED and not n.endswith('.egg-info'))
        for name in sorted(names):
            path=Path(directory)/name
            yield path


def main():
    failures=[];manifest={};total=0
    try:assets=screenshot_manifest(ROOT)
    except (ValueError,KeyError,TypeError):
        assets={};failures.append(['docs/screenshots/captures.json','invalid_screenshot_manifest'])
    for path in files():
        rel=path.relative_to(ROOT).as_posix()
        if path.is_symlink():failures.append([rel,'symlink']);continue
        size=path.stat().st_size
        if size>(2 if rel in assets else 1)*1024*1024:failures.append([rel,'unexpected_large_source']);continue
        if path.name in ('connection.json','private-launch.json') or path.name.startswith('.env'):
            failures.append([rel,'private_runtime_file']);continue
        raw=path.read_bytes();total+=len(raw)
        manifest[rel]=hashlib.sha256(raw).hexdigest()
        if rel in assets:
            try:validate_screenshot(raw,assets[rel])
            except (ValueError,zlib.error):failures.append([rel,'invalid_screenshot'])
            continue
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
    for name in assets:
        if name not in manifest:failures.append([name,'missing_screenshot'])
    print(json.dumps({'status':'FAIL' if failures else 'PASS','files':len(manifest),
        'bytes':total,'failures':failures,
        'source_set_sha256':hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()},indent=2))
    return bool(failures)


if __name__=='__main__':sys.exit(main())
