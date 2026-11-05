"""Closed trusted administrative option;never an operator-agent command.

Creating this descriptor only validates the small immutable header. The private
numerical child verifies every data file before it announces ScienceIdentity.
Missing/corrupt data cannot trigger a generator,download or provider fallback.
"""
from dataclasses import dataclass,field
import hashlib
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class FrozenFiniteLaunch:
    directory:str
    manifest_sha256:str
    world_generation_allowed:bool=field(default=False,init=False)
    protocol:str=field(default='vsem.private.finite-stored-launch.v1',init=False)

    def __post_init__(self):
        if type(self.directory) is not str or type(self.manifest_sha256) is not str or not re.fullmatch('[0-9a-f]{64}',self.manifest_sha256):
            raise ValueError('explicit trusted absolute catalogue path and SHA256 required')
        path=Path(self.directory)
        if not path.is_absolute() or path.resolve()!=path or path.is_symlink():
            raise ValueError('existing canonical owned finite catalogue required')
        manifest=path/'manifest.json'
        if not path.is_dir() or not manifest.is_file() or manifest.is_symlink() or manifest.stat().st_size>128*1024:
            raise ValueError('existing bounded frozen finite manifest required;generation forbidden')
        if hashlib.sha256(manifest.read_bytes()).hexdigest()!=self.manifest_sha256:
            raise ValueError('finite manifest changed;generation forbidden')


def finite_launch_option(*,no_world_generation,catalogue_directory,manifest_sha256):
    if type(no_world_generation) is not bool:raise ValueError('explicit boolean no-generation option required')
    if not no_world_generation:
        if catalogue_directory is not None or manifest_sha256 is not None:
            raise ValueError('finite assets require explicit --no-world-generation')
        return None
    if catalogue_directory is None or manifest_sha256 is None:raise ValueError('no-generation mode requires both existing asset path and hash')
    return FrozenFiniteLaunch(catalogue_directory,manifest_sha256)
