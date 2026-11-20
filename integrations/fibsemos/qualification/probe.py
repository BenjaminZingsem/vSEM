"""Separate trusted base-Python probe, before any package installer/import/build."""
import json
import os
from pathlib import Path
import socket
import sys


def main():
    checks = {'uid': os.getuid(), 'gid': os.getgid(), 'python': sys.version,
              'environment_keys': sorted(os.environ), 'mounts': Path('/proc/self/mountinfo').read_text()}
    if checks['uid'] != 10001 or checks['gid'] != 10001:
        raise RuntimeError('explicit nonroot identity missing')
    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    checks['restrictions'] = {key: status[key].strip() for key in ('CapEff', 'CapPrm', 'CapBnd', 'NoNewPrivs', 'Seccomp')}
    if any(int(status[key].strip(), 16) for key in ('CapEff', 'CapPrm', 'CapBnd')):
        raise RuntimeError('capabilities remain')
    if status['NoNewPrivs'].strip() != '1' or status['Seccomp'].strip() != '2':
        raise RuntimeError('no-new-privileges/default seccomp not active')
    allowed = {'PATH', 'HOME', 'LANG', 'TMPDIR', 'PIP_CONFIG_FILE', 'MPLCONFIGDIR'}
    if set(os.environ) != allowed or os.environ['HOME'] != '/scratch/home':
        raise RuntimeError('unexpected process environment')
    checks['forbidden_paths'] = {}
    for name in ('/var/run/docker.sock', '/root/.gitconfig', '/inputs/.git', '/github', '/workspace'):
        try:
            exists = Path(name).exists()
        except PermissionError:
            checks['forbidden_paths'][name] = 'inaccessible'
        else:
            if exists:
                raise RuntimeError('unexpected host/credential mount')
            checks['forbidden_paths'][name] = 'absent'
    checks['readonly'] = {}
    for mount in ('/', '/inputs', '/tests'):
        # Test the actual mount flags, not merely file permissions for this UID.
        flags = os.statvfs(mount).f_flag
        if not flags & os.ST_RDONLY:
            raise RuntimeError('required filesystem is not mounted read-only')
        path = Path(mount) / 'm05b1-negative-write'
        try:
            path.open('xb').close()
        except OSError as error:
            checks['readonly'][mount] = error.errno
        else:
            raise RuntimeError('write succeeded on a protected mount')
    checks['network_interfaces'] = sorted(p.name for p in Path('/sys/class/net').iterdir())
    if checks['network_interfaces'] != ['lo']:
        raise RuntimeError('external network interface present')
    with socket.socket() as stream:
        stream.settimeout(2.)
        try:
            stream.connect(('1.1.1.1', 443))
        except OSError as error:
            checks['external_connect_errno'] = error.errno
        else:
            raise RuntimeError('external connection succeeded')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        checks['loopback_bind'] = True
    checks['status'] = 'PASS'
    print(json.dumps(checks, sort_keys=True))


if __name__ == '__main__':
    main()
