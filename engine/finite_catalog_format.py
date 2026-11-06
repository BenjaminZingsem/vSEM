"""Private finite specimen file format;never generates missing world elements.

Only the numerical/preparation side imports this module. Arrays remain
provisional until their complete byte stream passes its content hash. A future
GPU loader must admit its frozen snapshot only after every stream completes.
Format acceptance alone does not qualify optical/edge/charge physics or biomes.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

PROTOCOL='vsem.private.finite-feature-catalog.v1'


def _keys(value,keys):
    if type(value) is not dict or set(value)!=set(keys):raise ValueError('closed catalogue fields required')


def _integer(value,low,high):
    if type(value) is not int or not low<=value<=high:raise ValueError('exact bounded catalogue integer required')
    return value


def _hex_real(value,low,high):
    if type(value) is not str:raise ValueError('exact hexadecimal physical scalar required')
    try:number=float.fromhex(value)
    except ValueError as exc:raise ValueError('invalid physical scalar') from exc
    if not math.isfinite(number) or not low<=number<=high or number.hex()!=value:
        raise ValueError('canonical bounded hexadecimal scalar required')
    return number


def _digest(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}',value):raise ValueError('exact content hash required')
    return value


def _pairs(items):
    result={}
    for key,value in items:
        if key in result:raise ValueError('duplicate catalogue JSON key')
        result[key]=value
    return result


def _regular(path):
    state=path.lstat()
    if not stat.S_ISREG(state.st_mode) or state.st_nlink!=1:raise ValueError('regular unlinked catalogue file required')
    return state


@dataclass(frozen=True)
class ArraySpec:
    name:str
    dtype:str
    shape:tuple
    sha256:str

    def __post_init__(self):
        if (type(self.name) is not str or not re.fullmatch(r'(?:level-[0-5]\.int32|anchor\.float64|regions\.uint8)',self.name) or
            self.dtype not in ('<i4','<f8','|u1') or type(self.shape) is not tuple or not self.shape):
            raise ValueError('closed immutable array descriptor required')
        for n in self.shape:_integer(n,1,2**31-1)
        _digest(self.sha256)
        if self.byte_count>2**63-1:raise ValueError('array byte count overflows file offsets')

    @property
    def byte_count(self):return math.prod(self.shape)*{'<i4':4,'<f8':8,'|u1':1}[self.dtype]


@dataclass(frozen=True)
class LevelSpec:
    origin:tuple
    pitch_m:float
    height_m:float
    contrast:float
    table:ArraySpec


@dataclass(frozen=True)
class CatalogHeader:
    directory:Path
    manifest_sha256:str
    bounds_m:tuple
    levels:tuple
    anchor:ArraySpec
    region_origin:tuple
    region_pitch_m:float
    regions:ArraySpec
    background_phase:float
    source:tuple

    @property
    def arrays(self):return tuple(level.table for level in self.levels)+(self.anchor,self.regions)

    @property
    def byte_count(self):return sum(array.byte_count for array in self.arrays)


def _array(value,name,dtype,rank,first_axis=None):
    _keys(value,('file','dtype','shape','sha256'))
    if value['file']!=name or value['dtype']!=dtype:raise ValueError('exact catalogue array name/type required')
    shape=value['shape']
    if type(shape) is not list or len(shape)!=rank:raise ValueError('exact array rank required')
    shape=tuple(_integer(n,1,2**31-1) for n in shape)
    if first_axis is not None and shape[0]!=first_axis:raise ValueError('exact catalogue plane count required')
    result=ArraySpec(name,dtype,shape,_digest(value['sha256']))
    if result.byte_count>2**63-1:raise ValueError('array byte count overflows file offsets')
    return result


def _origin(value):
    if type(value) is not list or len(value)!=2:raise ValueError('exact integer grid origin required')
    return tuple(_integer(n,-2**40,2**40) for n in value)


def load_header(directory,expected_manifest_sha256):
    """Validate the complete closed format/bounds/layout without allocating arrays.

    The trusted launcher supplies the expected manifest digest. No directory
    search,seed fallback,download or source regeneration occurs on any failure.
    Content hashes of array files are checked separately while loading them.
    """
    expected_manifest_sha256=_digest(expected_manifest_sha256)
    directory=Path(directory)
    if not stat.S_ISDIR(directory.lstat().st_mode):raise ValueError('regular catalogue directory required')
    directory=directory.resolve();manifest=directory/'manifest.json'
    state=_regular(manifest)
    if state.st_size>131072:raise ValueError('bounded catalogue manifest required')
    raw=manifest.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_manifest_sha256:raise ValueError('catalogue manifest content changed')
    def invalid_constant(_):raise ValueError('nonfinite JSON scalar')
    value=json.loads(raw,object_pairs_hook=_pairs,parse_constant=invalid_constant)
    _keys(value,('protocol','bounds_m','levels','anchor','regions','background_phase','source'))
    if value['protocol']!=PROTOCOL:raise ValueError('exact finite catalogue protocol required')
    b=value['bounds_m']
    if type(b) is not list or len(b)!=4:raise ValueError('physical rectangle required')
    bounds=tuple(_hex_real(n,-.055,.055) for n in b)
    if bounds[0]>=bounds[1] or bounds[2]>=bounds[3]:raise ValueError('positive specimen rectangle required')
    if type(value['levels']) is not list or len(value['levels'])!=6:raise ValueError('six immutable morphology scales required')
    levels=[]
    for index,item in enumerate(value['levels']):
        _keys(item,('origin','pitch_m','height_m','contrast','table'))
        table=_array(item['table'],'level-'+str(index)+'.int32','<i4',3,9)
        origin=_origin(item['origin']);pitch=_hex_real(item['pitch_m'],1e-9,.02)
        level=LevelSpec(origin,pitch,_hex_real(item['height_m'],0.,.55e-6),_hex_real(item['contrast'],0.,4.),table)
        # Every feature cell touched by any in-sample point and its3x3 neighbours
        # must already exist;queries may not generate missing boundary cells.
        for low,high,start,extent in ((bounds[0],bounds[1],origin[0],table.shape[2]),
                                      (bounds[2],bounds[3],origin[1],table.shape[1])):
            if start>math.floor(low/pitch)-1 or start+extent-1<math.floor(high/pitch)+1:
                raise ValueError('catalogue omits required existing feature neighbours')
        levels.append(level)
    anchor=_array(value['anchor'],'anchor.float64','<f8',2)
    if anchor.shape[1]!=11:raise ValueError('exact finite-feature coefficient width required')
    region=value['regions'];_keys(region,('origin','pitch_m','table'))
    regions=_array(region['table'],'regions.uint8','|u1',3,3)
    source=value['source'];_keys(source,('generator_sha256','integer_kernel_sha256','profile'))
    if source['profile']!='generic-finite-low-relief-v1':raise ValueError('explicit uncalibrated finite profile required')
    header=CatalogHeader(directory,expected_manifest_sha256,bounds,tuple(levels),anchor,
        _origin(region['origin']),_hex_real(region['pitch_m'],1e-9,.02),regions,
        _hex_real(value['background_phase'],0.,1.),
        (_digest(source['generator_sha256']),_digest(source['integer_kernel_sha256']),source['profile']))
    for low,high,start,extent in ((bounds[0],bounds[1],header.region_origin[0],regions.shape[2]),
                                  (bounds[2],bounds[3],header.region_origin[1],regions.shape[1])):
        if start>math.floor(low/header.region_pitch_m) or start+extent-1<math.floor(high/header.region_pitch_m):
            raise ValueError('catalogue omits existing material regions')
    allowed={'manifest.json'}|{array.name for array in header.arrays}
    if {p.name for p in directory.iterdir()}!=allowed:raise ValueError('unexpected or missing catalogue members')
    for array in header.arrays:
        if _regular(directory/array.name).st_size!=array.byte_count:raise ValueError('exact catalogue array byte count required')
    return header


def array_chunks(header,array,chunk_bytes=8*1024*1024):
    """Yield provisional bytes;final exhaustion verifies this exact input stream.

    Consumers must finish all streams before admitting any frozen numerical
    source. chunk_bytes is an IO grain,not an asset/memory/compute budget.
    """
    if type(header) is not CatalogHeader or type(array) is not ArraySpec or array not in header.arrays:
        raise ValueError('array must belong to this validated catalogue')
    _integer(chunk_bytes,1,2**31-1)
    path=header.directory/array.name;before=_regular(path);digest=hashlib.sha256();total=0
    # Do not prefetch later chunks: a concurrent write to not-yet-yielded bytes
    # must reach the digest even when filesystem timestamps have not advanced.
    with path.open('rb',buffering=0) as stream:
        opened=os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink!=1 or
            (opened.st_dev,opened.st_ino,opened.st_size,opened.st_mtime_ns)!=
            (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)):
            raise ValueError('catalogue member replaced before byte loading')
        while True:
            raw=stream.read(chunk_bytes)
            if not raw:break
            # Raw IO may return short reads. Preserve the caller's chunk grain
            # (and numeric element alignment) until actual EOF.
            if len(raw)<chunk_bytes:
                parts=[raw];remaining=chunk_bytes-len(raw)
                while remaining:
                    part=stream.read(remaining)
                    if not part:break
                    parts.append(part);remaining-=len(part)
                raw=b''.join(parts)
            total+=len(raw)
            if total>array.byte_count:raise ValueError('array changed while loading')
            digest.update(raw);yield raw
    after=_regular(path)
    if ((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=
        (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns) or total!=array.byte_count or
        digest.hexdigest()!=array.sha256):raise ValueError('array content changed;frozen source not admitted')
