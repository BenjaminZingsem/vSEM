"""Private lazy native-world specimen tiles for the human imaging candidate.

Intrinsic height/slopes/yield only,no acquisition,clock,noise or public route.
This is a NEW interpolated numerical variant. Analytic reference,beam-response,
whole-frame and visual qualification must precede activation.
"""
from collections import OrderedDict
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import uuid
import numpy as np
from .fine_practice_specimen import FinePracticeSpecimen
from .human_alignment_specimen import HumanAlignmentSpecimen

PROTOCOL='vsem.private.native-world-fields.v1'
TILE_CELLS=128
SPACINGS=(1.25e-9,2.5e-9,5e-9,10e-9)
COORDINATE_BOUND_M=.055
SOURCE_NAMES=('fine_practice_specimen.py','procedural_specimen.py','human_specimen_map.py','human_alignment_specimen.py')

def available_memory_bytes():
    if os.name=='nt':
        class MemoryStatus(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[
                (name,ctypes.c_ulonglong) for name in ('total','available','page_total',
                    'page_available','virtual_total','virtual_available','extended')]
        status=MemoryStatus();status.length=ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise RuntimeError('Cannot measure actual available host memory')
        return int(status.available)
    return int(os.sysconf('SC_AVPHYS_PAGES')*os.sysconf('SC_PAGE_SIZE'))

def digest(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')
def strict_record(path):
    if path.is_symlink():raise ValueError('Map metadata symlink forbidden')
    def pairs(items):
        value={}
        for key,item in items:
            if key in value:raise ValueError('Duplicate map metadata key')
            value[key]=item
        return value
    def bad_constant(value):raise ValueError('Nonfinite map metadata')
    return json.loads(path.read_bytes(),object_pairs_hook=pairs,parse_constant=bad_constant)

class NativeWorldMap:
    def __init__(self,*,specimen=None,spacing_m=5e-9,cache_bytes=None,directory=None):
        specimen=FinePracticeSpecimen() if specimen is None else specimen
        if type(specimen) not in (FinePracticeSpecimen,HumanAlignmentSpecimen):
            raise ValueError('Exact immutable fine procedural specimen required')
        if type(spacing_m) is not float or spacing_m not in SPACINGS:
            raise ValueError('Declared native map spacing required')
        budget=available_memory_bytes()*3//4 if cache_bytes is None else cache_bytes
        self.tile_bytes=4*(TILE_CELLS+1)**2*8
        if type(budget) is not int or budget<self.tile_bytes:
            raise ValueError('Measured/trusted cache allowance must fit at least one tile')
        self.specimen,self.spacing,self.budget=specimen,spacing_m,budget
        self.cache=OrderedDict();self.resident_bytes=0;self.generated_tiles=0;self.loaded_tiles=0
        self.max_grid_index=math.floor(math.nextafter(COORDINATE_BOUND_M,0.)/spacing_m)
        self.map_bound_m=self.max_grid_index*spacing_m
        folder=Path(__file__).resolve().parent
        pins={name:digest((folder/name).read_bytes()) for name in SOURCE_NAMES}
        helper=folder.parent/'packages/specimens/bounds_index.py'
        pins['packages/specimens/bounds_index.py']=digest(helper.read_bytes())
        self.identity={'protocol':PROTOCOL,'native_spacing_hex':spacing_m.hex(),
            'specimen_kind':type(specimen).__name__,
            'tile_cells':TILE_CELLS,'field_order':['height_m','slope_x','slope_y','SE_intrinsic_yield'],
            'private_seed_sha256':digest(specimen.seed),'source':pins,
            'numpy':np.__version__,'python':sys.version,'byteorder':sys.byteorder,
            'interpolation':'positive-bilinear-v1','coordinate_frame':'fixed-specimen-metres-y-up'}
        self.identity_digest=digest(canonical(self.identity))
        self.directory=None if directory is None else Path(directory).resolve()
        if self.directory is not None:
            self.directory.mkdir(parents=True,exist_ok=True)
            manifest=self.directory/'identity.json'
            if manifest.exists():
                if strict_record(manifest)!=self.identity:raise ValueError('Persistent map identity differs')
            else:
                with manifest.open('xb') as stream:stream.write(canonical(self.identity)+b'\n')

    def _paths(self,key):
        stem='tile_'+str(key[0])+'_'+str(key[1])
        return self.directory/(stem+'.npy'),self.directory/(stem+'.json')

    def _validate_tile(self,tile):
        if (type(tile) is not np.ndarray or tile.shape!=(4,TILE_CELLS+1,TILE_CELLS+1)
                or tile.dtype!=np.dtype('float64') or not np.isfinite(tile).all()
                or np.any(np.abs(tile[0])>.55e-6) or np.any(tile[3]<.12) or np.any(tile[3]>.32)):
            raise ValueError('Native world tile shape/type/physical field bounds differ')
        tile.setflags(write=False)
        return tile

    def _read_tile(self,key,data,record):
        if data.is_symlink() or not data.is_file() or not record.is_file():
            raise ValueError('Incomplete/substituted persistent map tile')
        if not self.tile_bytes<=data.stat().st_size<=self.tile_bytes+4096:
            raise ValueError('Persistent tile file outside fixed native byte envelope')
        metadata=strict_record(record)
        expected={'protocol':PROTOCOL,'identity_digest':self.identity_digest,
                  'tile_x':key[0],'tile_y':key[1],'data_sha256':digest(data.read_bytes())}
        if metadata!=expected:raise ValueError('Persistent map tile hash/identity differs')
        tile=self._validate_tile(np.load(data,allow_pickle=False))
        self.loaded_tiles+=1
        return tile

    def _generate_tile(self,key):
        # Only the full map's OUTER incomplete lattice tile needs edge fill.
        # Query admission requires both interpolation neighbors in the real
        # source domain. Filled outer nodes are therefore never sampled.
        ix=np.arange(TILE_CELLS+1,dtype=np.int64)+key[0]*TILE_CELLS
        iy=np.arange(TILE_CELLS+1,dtype=np.int64)+key[1]*TILE_CELLS
        ix=np.clip(ix,-self.max_grid_index,self.max_grid_index)
        iy=np.clip(iy,-self.max_grid_index,self.max_grid_index)
        x,y=np.meshgrid(ix*self.spacing,iy*self.spacing)
        result=np.stack(self.specimen.surface_arrays(x,y))
        self.generated_tiles+=1
        return self._validate_tile(result)

    def _persist_tile(self,key,tile,data,record):
        if data.exists() or record.exists():raise ValueError('Never overwrite a persistent map tile')
        temp=self.directory/('.tile-'+uuid.uuid4().hex+'.tmp')
        try:
            with temp.open('xb') as stream:np.save(stream,tile,allow_pickle=False)
            metadata={'protocol':PROTOCOL,'identity_digest':self.identity_digest,
                      'tile_x':key[0],'tile_y':key[1],'data_sha256':digest(temp.read_bytes())}
            # The cache has one trusted owner. An interrupted two-file commit is
            # rejected on return;it never silently becomes another specimen.
            os.replace(temp,data)
            with record.open('xb') as stream:stream.write(canonical(metadata)+b'\n')
        finally:
            if temp.exists():temp.unlink()

    def _tile(self,key):
        if key in self.cache:
            tile=self.cache.pop(key);self.cache[key]=tile;return tile
        if available_memory_bytes()<self.tile_bytes*3:
            raise MemoryError('Insufficient actual memory for native tile construction')
        if self.directory is not None:
            data,record=self._paths(key)
            if data.exists() or record.exists():tile=self._read_tile(key,data,record)
            else:
                tile=self._generate_tile(key);self._persist_tile(key,tile,data,record)
        else:tile=self._generate_tile(key)
        while self.resident_bytes+self.tile_bytes>self.budget:
            self.cache.popitem(last=False);self.resident_bytes-=self.tile_bytes
        self.cache[key]=tile;self.resident_bytes+=self.tile_bytes
        return tile

    def surface_arrays(self,x_m,y_m):
        def inputs(value):
            def contains_boolean(item):
                return isinstance(item,(bool,np.bool_)) or isinstance(item,(tuple,list)) and any(contains_boolean(v) for v in item)
            if contains_boolean(value):raise ValueError('Boolean map coordinates forbidden')
            original=np.asarray(value)
            if original.dtype.kind not in 'fiu':raise ValueError('Exact real map coordinates required')
            result=np.asarray(original,dtype=np.float64)
            if not np.isfinite(result).all():raise ValueError('Finite native map coordinates required')
            return result
        x,y=np.broadcast_arrays(inputs(x_m),inputs(y_m))
        gx,gy=x/self.spacing,y/self.spacing
        ix,iy=np.floor(gx),np.floor(gy)
        # Two actual native neighbors are required. No query,probe footprint or
        # extrapolation is clipped to manufacture edge signal.
        if np.any(ix<-self.max_grid_index) or np.any(iy<-self.max_grid_index) or np.any(ix+1>self.max_grid_index) or np.any(iy+1>self.max_grid_index):
            raise ValueError('Native map interpolation support outside source domain')
        ix,iy=ix.astype(np.int64),iy.astype(np.int64)
        tx,ty=ix//TILE_CELLS,iy//TILE_CELLS
        fx,fy=(gx-ix).reshape(-1),(gy-iy).reshape(-1)
        local_x,local_y=(ix%TILE_CELLS).reshape(-1),(iy%TILE_CELLS).reshape(-1)
        keys=np.stack([tx.reshape(-1),ty.reshape(-1)],axis=1)
        result=np.empty((4,x.size),dtype=np.float64)
        unique,inverse=np.unique(keys,axis=0,return_inverse=True)
        for number,key in enumerate(unique):
            mask=inverse==number;tile=self._tile((int(key[0]),int(key[1])))
            a,b=local_x[mask],local_y[mask];u,v=fx[mask],fy[mask]
            result[:,mask]=((1-u)*(1-v)*tile[:,b,a]+u*(1-v)*tile[:,b,a+1]+
                           (1-u)*v*tile[:,b+1,a]+u*v*tile[:,b+1,a+1])
        return tuple(result[i].reshape(x.shape) for i in range(4))

    def surface(self,x_m,y_m):
        if type(x_m) not in (int,float) or type(y_m) not in (int,float):
            raise ValueError('Builtin finite scalar map coordinates required')
        return tuple(float(value) for value in self.surface_arrays(x_m,y_m))
