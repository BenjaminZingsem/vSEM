"""Explicit administrator-selected GPU; shared leases across source checkouts."""
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


def selected_gpu():
    value = os.environ.get('VSEM_GPU_UUID', '')
    if not re.fullmatch(r'GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', value):
        raise ValueError('Set VSEM_GPU_UUID to an explicit physical NVIDIA GPU UUID')
    return value


class PreparedGpuLease:
    def __init__(self, project=None):
        if sys.platform != 'linux':
            raise ValueError('The numerical runtime requires Linux or WSL2')
        self.gpu_uuid = selected_gpu()
        # All clones share this per-user lock. An administrator can explicitly
        # share the directory with other trusted GPU schedulers on this host.
        directory = Path(os.environ.get('VSEM_GPU_LOCK_DIRECTORY',
            str(Path.home()/'.cache/vsem/gpu-locks'))).expanduser()
        if not directory.is_absolute() or directory.is_symlink():
            raise ValueError('Canonical absolute GPU lock directory required')
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if directory.resolve() != directory:
            raise ValueError('GPU lock directory may not contain symlink components')
        self.path = directory/(self.gpu_uuid+'.lock')
        self.stream = None

    def __enter__(self):
        import fcntl
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        stream = os.fdopen(fd, 'r+', encoding='ascii')
        try:
            state = os.fstat(stream.fileno())
            if not stat.S_ISREG(state.st_mode) or state.st_nlink != 1:
                raise ValueError('Regular single-link GPU lease required')
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            stream.seek(0)
            stream.truncate()
            stream.write(self.gpu_uuid+'\n')
            stream.flush()
            self.stream = stream
            return self
        except BaseException:
            stream.close()
            raise

    def admit_device(self):
        if self.stream is None or self.stream.closed:
            raise ValueError('Actual exclusive GPU lease required')
        def query(field):
            return subprocess.run(['nvidia-smi', '--id='+self.gpu_uuid, field,
                '--format=csv,noheader,nounits'], check=True, capture_output=True,
                text=True, timeout=30).stdout.strip()
        used = query('--query-gpu=memory.used')
        processes = query('--query-compute-apps=pid')
        if not used.isdigit() or int(used)>320 or processes:
            raise RuntimeError('Selected GPU occupied; no foreign kill or device/provider fallback')
        os.environ['CUDA_VISIBLE_DEVICES'] = self.gpu_uuid
        os.environ['CUDA_DEVICE_ORDER'] = 'PCI_BUS_ID'
        return {'gpu_uuid':self.gpu_uuid,'used_mib_before_CUDA':int(used),'shared_lock':str(self.path)}

    def __exit__(self, *_):
        if self.stream is not None:
            self.stream.close()
            self.stream = None
