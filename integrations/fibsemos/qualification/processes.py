"""Owned subprocess/log handling; never forward raw child output to Actions."""
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def run_logged(arguments, log_path, *, env, cwd=None, timeout=10500, limit=16 * 1024**2):
    """POSIX supervisor: bounded capture and process-group cleanup on failure."""
    started = time.monotonic()
    with Path(log_path).open('xb') as output:
        child = subprocess.Popen(arguments, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        try:
            total = 0
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    if time.monotonic() - started > timeout:
                        raise TimeoutError('owned process exceeded its finite envelope')
                    for key, _ in selector.select(.25):
                        block = os.read(key.fd, 65536)
                        if not block:
                            selector.unregister(key.fileobj)
                            continue
                        total += len(block)
                        if total > limit:
                            raise RuntimeError('child log exceeded evidence limit; qualification incomplete')
                        output.write(block)
            code = child.wait(timeout=max(1, timeout - (time.monotonic() - started)))
            return {'exit_code': code, 'log_bytes': total, 'elapsed_s': time.monotonic() - started}
        except BaseException:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait(timeout=30)
            raise
        finally:
            child.stdout.close()
