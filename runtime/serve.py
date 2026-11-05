"""Foreground, loopback-only development launcher. Ctrl+C closes owned children."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import sys
import threading


def check_environment():
    if sys.platform != 'linux' or sys.version_info[:2] != (3, 10):
        raise RuntimeError('Use Linux/WSL2 and Python 3.10 (qualified on 3.10.12)')
    for name, version in {'numpy':'1.26.4','scipy':'1.15.3','torch':'2.3.1','triton':'2.3.1'}.items():
        if importlib.metadata.version(name).split('+')[0] != version:
            raise RuntimeError('Pinned dependency required: '+name+'=='+version)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalogue-directory', required=True)
    parser.add_argument('--catalogue-manifest-sha256', required=True)
    parser.add_argument('--no-world-generation', action='store_true', required=True)
    parser.add_argument('--run-directory', required=True, help='New private directory; never reused')
    parser.add_argument('--ui-port', type=int, default=8122)
    parser.add_argument('--api-port', type=int, default=8123)
    args = parser.parse_args()
    check_environment()
    from .gpu_resources import selected_gpu
    selected_gpu()
    from .finite_launch_spec import finite_launch_option
    from .finite_human_service import FiniteHumanService
    from .hierarchical_http import HierarchicalHTTP
    finite = finite_launch_option(no_world_generation=args.no_world_generation,
        catalogue_directory=str(Path(args.catalogue_directory).resolve()),
        manifest_sha256=args.catalogue_manifest_sha256)
    directory = Path(args.run_directory).absolute()
    if directory.exists() or directory.is_symlink():
        raise ValueError('Run directory must be new; existing records are never overwritten')
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.umask(0o077)
    stopped = threading.Event()
    def stop(signum, frame):
        stopped.set()
    signal.signal(signal.SIGTERM, stop)
    service = http = None
    try:
        service = FiniteHumanService(directory/'episode', finite_catalogue=finite)
        http = HierarchicalHTTP(service, args.ui_port, args.api_port)
        connection = {'api_origin':http.api.origin,'api_token':http.api.token,
                      'human_url':http.human_url}
        path = directory/'connection.json'
        with path.open('x', encoding='utf-8') as stream:
            json.dump(connection, stream, indent=2)
            stream.write('\n')
        print('vSEM research runtime: generic uncalibrated, ideal grounded specimen.', flush=True)
        print('Open '+http.human_url, flush=True)
        print('Private API connection: '+str(path), flush=True)
        print('Ctrl+C stops this instance and its owned numerical/physical children.', flush=True)
        while not stopped.wait(.1):
            if service.failure:
                raise RuntimeError('Instrument quarantined; preserve the private run records')
    except KeyboardInterrupt:
        pass
    finally:
        if http is not None: http.close()
        if service is not None:
            service.close()
            if service.kernel.numeric.is_alive() or (service.kernel.owner and service.kernel.owner.is_alive()):
                raise RuntimeError('Owned child cleanup incomplete')
        print('vSEM closed.', flush=True)


if __name__ == '__main__':
    main()
