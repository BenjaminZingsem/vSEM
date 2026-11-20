"""Pure host-side container configuration checks, independent of package reports."""
from pathlib import Path
from artifacts import require

PROCESS_ENV = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/scratch/home', 'LANG': 'C.UTF-8',
               'TMPDIR': '/scratch/tmp', 'PIP_CONFIG_FILE': '/dev/null', 'MPLCONFIGDIR': '/scratch/mpl'}


def entry_command(phase):
    script = ['/tests/probe.py'] if phase == 'probe' else ['/tests/container_main.py', phase]
    return ['-i', *(key + '=' + value for key, value in PROCESS_ENV.items()),
            '/usr/local/bin/python', '-I', '-S', '-B', *script]


def verify_container(value, *, image_id, image_env, mounts, memory, scratch, phase, owner):
    host, config = value['HostConfig'], value['Config']
    require(value['Image'] == image_id and config['Image'] == image_id, 'container image ID mismatch')
    require(config['User'] == '10001:10001' and config['Entrypoint'] == ['/usr/bin/env']
            and config['Cmd'] == entry_command(phase), 'container process identity/entry mismatch')
    require(config.get('Env') == image_env and not config.get('Healthcheck'), 'unexpected image environment/healthcheck')
    require(config.get('Labels', {}).get('vsem.m05b1.owner') == owner, 'wrong container ownership label')
    require(host['NetworkMode'] == 'none' and host.get('PidMode', '') == '' and host['IpcMode'] == 'private'
            and host['CgroupnsMode'] == 'private', 'shared host namespace')
    require(host['ReadonlyRootfs'] is True and host['Privileged'] is False,
            'writable root or privileged container')
    require(host.get('CapDrop') == ['ALL'] and not host.get('CapAdd'), 'unexpected capabilities')
    require(host.get('SecurityOpt') in (['no-new-privileges'], ['no-new-privileges:true']),
            'security profile differs from default seccomp/no-new-privileges')
    for key in ('Devices', 'DeviceRequests', 'DeviceCgroupRules', 'PortBindings', 'Links', 'ExtraHosts',
                'VolumesFrom', 'Binds'):
        require(not host.get(key), 'unapproved device/host/network access: ' + key)
    require(not host.get('PublishAllPorts') and not config.get('ExposedPorts'), 'published port')
    require(host['Memory'] == memory and host['MemorySwap'] == memory, 'resource memory envelope mismatch')
    require(not host.get('NanoCpus') and not host.get('CpuQuota') and not host.get('CpusetCpus'),
            'CPU capacity restricted')
    require(host['Tmpfs'] == {'/scratch': 'rw,exec,nosuid,nodev,size=' + str(scratch) + ',mode=1777'},
            'unexpected scratch mount')
    actual = {}
    for mount in value['Mounts']:
        if mount['Type'] == 'tmpfs' and mount['Destination'] == '/scratch':
            continue
        require(mount['Type'] == 'bind' and mount.get('Propagation') == 'rprivate', 'unexpected mount type/propagation')
        require(mount['Destination'] not in actual, 'duplicate container mount')
        actual[mount['Destination']] = (str(Path(mount['Source']).resolve()), mount['RW'])
    require(actual == mounts, 'container mount allowlist mismatch')
    require(value['State']['Status'] == 'created' and not value['State']['Running'],
            'container executed before independent inspection')
    return {'status': 'PASS', 'image_id': image_id, 'phase': phase, 'mounts': actual,
            'memory_bytes': memory, 'scratch_bytes': scratch, 'cpu_limit': 'all available CPUs',
            'read_only_root': True, 'uid': 10001, 'network': 'none', 'caps': [],
            'seccomp': 'engine builtin, runtime probe required', 'owner': owner}
