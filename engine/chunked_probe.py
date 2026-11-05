"""Private bounded native-probe chunks;experimental,not runtime-selected.

Same positive finite Gaussian/native world/height interpolation as the original
mapped profile. Sparse survey queries do not allocate a dense FOV rectangle.
Only immutable intrinsic fields/responses are cached;no acquired state is cached.
The caller supplies measured host cache admission and owns the GPU1 lease.
"""
from collections import OrderedDict,defaultdict
import math
import os
from pathlib import Path
import time
import numpy as np
from .human_episode_types import EpisodeGeometry,EpisodeSettings,exact
from .human_specimen_map import NativeWorldMap,available_memory_bytes,canonical,digest
from .prepared_specimen_map import PreparedWorldMap
from .hierarchical_native_map import HierarchicalNativeMap
from .human_mapped_probe import (HumanMappedProfile,MappedProbeBank,effective_settings,
    emitted_and_collected,_positive_kernel,HEIGHT_STEP_M)
from .beam_profile import HEIGHT_BOUND_M

CHUNK_CELLS=32
GPU_UUID = os.environ.get('VSEM_GPU_UUID', 'UNCONFIGURED')
# Pinned Torch2.3.1 actual two-plane large-halo peaks measured96.03 bytes
# per group FFT cell (6144/9216 axes).160 retains66% implementation headroom;
# source fields are prepared/admitted separately before convolution allocations.
FFT_BYTES_PER_GROUP_CELL=160


def _bucket(radius):
    return 1<<(max(1,radius)-1).bit_length()


def _groups(keys):
    """Coalesce dense neighbouring atomic chunks;split sparse bounding boxes.

    Grouping affects work only. Cached atomic outputs retain fixed coordinates.
    Every rectangle contains at least one requested key. No empty distant area
    can cause a millimetre native allocation through this partition.
    """
    keys=tuple(keys)
    if not keys:return
    lowx=min(k[0] for k in keys);highx=max(k[0] for k in keys)
    lowy=min(k[1] for k in keys);highy=max(k[1] for k in keys)
    area=(highx-lowx+1)*(highy-lowy+1)
    if len(keys)==1 or len(keys)*2>=area:
        yield (lowx,lowy,highx,highy,keys);return
    axis=0 if highx-lowx>=highy-lowy else 1
    ordered=sorted(keys,key=lambda k:(k[axis],k[1-axis]))
    middle=len(ordered)//2
    yield from _groups(ordered[:middle]);yield from _groups(ordered[middle:])


def _probe_groups(keys,rx,ry):
    """Choose rectangles by padded FFT work,including real halo duplication.

    Sparse raster centres within a small FOV can be cheaper as one dense scene
    than thousands of overlapping probe halos. Distant survey points still split.
    This never changes the atomic output lattice or a physical kernel.
    """
    from scipy.fft import next_fast_len
    def plan(keys):
        lowx=min(k[0] for k in keys);highx=max(k[0] for k in keys)
        lowy=min(k[1] for k in keys);highy=max(k[1] for k in keys)
        nx=(highx-lowx+1)*CHUNK_CELLS+1;ny=(highy-lowy+1)*CHUNK_CELLS+1
        group=(lowx,lowy,highx,highy,keys)
        cost=next_fast_len(nx+4*rx)*next_fast_len(ny+4*ry)
        if len(keys)==1 or len(keys)*2>=(highx-lowx+1)*(highy-lowy+1):return cost,(group,)
        axis=0 if nx>=ny else 1;ordered=sorted(keys,key=lambda k:(k[axis],k[1-axis]))
        middle=len(ordered)//2;a,left=plan(tuple(ordered[:middle]));b,right=plan(tuple(ordered[middle:]))
        return (cost,(group,)) if cost<=a+b else (a+b,left+right)
    keys=tuple(keys)
    return () if not keys else plan(keys)[1]


def _fit_groups(groups,rx,ry,max_fft_cells):
    """Split work rectangles to an actual measured FFT allowance,not a quota."""
    from scipy.fft import next_fast_len
    for group in groups:
        nx=(group[2]-group[0]+1)*CHUNK_CELLS+1
        ny=(group[3]-group[1]+1)*CHUNK_CELLS+1
        cells=next_fast_len(nx+4*rx)*next_fast_len(ny+4*ry)
        if cells<=max_fft_cells:
            yield group;continue
        if len(group[4])==1:raise MemoryError('actual resources cannot admit one physical probe chunk')
        axis=0 if nx>=ny else 1
        ordered=sorted(group[4],key=lambda k:(k[axis],k[1-axis]));middle=len(ordered)//2
        parts=(*_groups(ordered[:middle]),*_groups(ordered[middle:]))
        yield from _fit_groups(parts,rx,ry,max_fft_cells)


class ChunkedProbeBuilder:
    def __init__(self,world,*,cache_bytes,device='cpu'):
        if type(world) not in (NativeWorldMap,PreparedWorldMap,HierarchicalNativeMap):raise ValueError('known immutable world map required')
        if type(cache_bytes) is not int or cache_bytes<1:raise ValueError('explicit measured positive cache allowance required')
        if device not in ('cpu','cuda:0'):raise ValueError('explicit CPU or qualified GPU1 device required')
        import torch
        if torch.__version__!='2.3.1+cu121':raise ValueError('pinned qualified Torch required')
        if device=='cuda:0':
            if os.environ.get('CUDA_VISIBLE_DEVICES')!=GPU_UUID or torch.cuda.device_count()!=1:
                raise ValueError('exclusive qualified physical GPU1 visibility required')
        self.torch,self.device,self.world=torch,device,world
        self.budget=cache_bytes;self.resident=0;self.cache=OrderedDict()
        self.hits=self.misses=self.scene_hits=self.scene_builds=self.convolutions=0
        self.maximum_scene_cells=0;self.total_scene_cells=0
        self.pins=self._pins();self.map_identity=world.identity_digest

    @staticmethod
    def _pins():
        folder=Path(__file__).resolve().parent
        result={n:digest((folder/n).read_bytes()) for n in ('chunked_probe.py','beam_profile.py','human_mapped_probe.py')}
        result['batched_valid_convolution.py']=digest((folder.parent/'packages/numerics/batched_valid_convolution.py').read_bytes())
        return result

    def _get(self,key):
        if key not in self.cache:return None
        value,size=self.cache.pop(key);self.cache[key]=(value,size);return value

    def _put(self,key,value):
        size=sum(v.nbytes for v in value)
        if size>self.budget:return
        while self.resident+size>self.budget:
            _,(_,removed)=self.cache.popitem(last=False);self.resident-=removed
        for v in value:v.setflags(write=False)
        self.cache[key]=(value,size);self.resident+=size

    def _evict_for_work(self,needed):
        # Evict only this builder's immutable copies,never foreign allocations.
        while needed>available_memory_bytes()*4//5 and self.cache:
            _,(_,size)=self.cache.popitem(last=False);self.resident-=size
        if needed>available_memory_bytes()*4//5:raise MemoryError('actual RAM cannot admit native response work')

    def _scene(self,group,rx,ry):
        x0,y0,x1,y1,_=group;n=CHUNK_CELLS
        nx=(x1-x0+1)*n+1;ny=(y1-y0+1)*n+1
        sx,sy=nx+2*rx,ny+2*ry
        key=('fields',x0,y0,x1,y1,rx,ry,self.map_identity)
        cached=self._get(key)
        if cached is not None:self.scene_hits+=1;return cached
        self._evict_for_work(sx*sy*256)
        spacing=self.world.spacing
        x=(np.arange(sx,dtype=np.int64)+x0*n-rx)*spacing
        y=(np.arange(sy,dtype=np.int64)+y0*n-ry)*spacing
        xx,yy=np.meshgrid(x,y)
        fields=self.world.surface_arrays(xx,yy)
        emitted,collected=emitted_and_collected(fields)
        if (not np.isfinite(emitted).all() or not np.isfinite(collected).all() or
            np.any(emitted>4) or np.any(collected<0)):raise ValueError('physical emission envelope exceeded')
        values=(np.ascontiguousarray(emitted),np.ascontiguousarray(collected))
        self.scene_builds+=1;self.total_scene_cells+=sx*sy
        self.maximum_scene_cells=max(self.maximum_scene_cells,sx*sy)
        self._put(key,values);return values

    def _convolve(self,groups,kernel,rx,ry):
        from packages.numerics.batched_valid_convolution import valid_convolve2d
        from scipy.fft import next_fast_len
        torch=self.torch;n=CHUNK_CELLS
        host=available_memory_bytes()
        free=host if self.device=='cpu' else torch.cuda.mem_get_info()[0]
        groups=_fit_groups(groups,rx,ry,int(min(host,free)*.65//FFT_BYTES_PER_GROUP_CELL))
        shapes=defaultdict(list)
        for g in groups:shapes[((g[2]-g[0]+1)*n+1,(g[3]-g[1]+1)*n+1)].append(g)
        for (nx,ny),pending in shapes.items():
            fft_shape=(next_fast_len(ny+4*ry),next_fast_len(nx+4*rx))
            cells=fft_shape[0]*fft_shape[1]
            # Conservative scene/input/output/complex FFT/workspace admission.
            # This sizes the batch from actual availability,not a task-count cap.
            peak_per_group=cells*FFT_BYTES_PER_GROUP_CELL
            host=available_memory_bytes()
            free=host if self.device=='cpu' else torch.cuda.mem_get_info()[0]
            batch=max(1,min(len(pending),int(min(host,free)*.65//peak_per_group)))
            if peak_per_group>min(host,free)*.8:raise MemoryError('actual device/RAM cannot admit one native chunk group')
            for start in range(0,len(pending),batch):
                group_batch=pending[start:start+batch]
                scenes=np.stack([v for g in group_batch for v in self._scene(g,rx,ry)])
                s=torch.as_tensor(scenes,dtype=torch.float64,device=self.device)
                k=torch.as_tensor(kernel[None],dtype=torch.float64,device=self.device)
                answer=valid_convolve2d(s,k,fft_shape).cpu().numpy()
                self.convolutions+=1
                for index,g in enumerate(group_batch):
                    planes=answer[2*index:2*index+2]
                    for tx,ty in g[4]:
                        x=(tx-g[0])*n;y=(ty-g[1])*n
                        # Owning atomic copies do not retain the large group.
                        yield (tx,ty),tuple(np.array(p[y:y+n+1,x:x+n+1],copy=True) for p in planes)
                del s,k,answer,scenes

    def build(self,geometry,settings):
        exact(geometry,EpisodeGeometry);exact(settings,EpisodeSettings)
        if self._pins()!=self.pins or self.world.identity_digest!=self.map_identity:
            raise ValueError('changed immutable chunked response source')
        started=time.perf_counter();world=self.world;spacing=world.spacing;n=CHUNK_CELLS
        if geometry.pixel_count*2048>available_memory_bytes()*4//5:
            raise MemoryError('actual RAM cannot admit declared native raster indexing')
        px=geometry.center_x_m+(np.arange(geometry.width_px)+.5-geometry.width_px/2)*geometry.pixel_size_m
        py=geometry.center_y_m+(geometry.height_px/2-np.arange(geometry.height_px)-.5)*geometry.pixel_size_m
        x,y=np.meshgrid(px,py);x=x.ravel();y=y.ravel()
        heights=world.surface_arrays(x,y)[0]
        lower=np.floor(heights/HEIGHT_STEP_M).astype(np.int64);fraction=heights/HEIGHT_STEP_M-lower
        gx,gy=x/spacing,y/spacing
        ix,iy=np.floor(gx).astype(np.int64),np.floor(gy).astype(np.int64)
        fx,fy=gx-ix,gy-iy;tx,ty=ix//n,iy//n
        # Index once rather than mask the complete raster for each atomic chunk.
        positions=defaultdict(list)
        for i,key in enumerate(zip(tx.tolist(),ty.tolist())):positions[key].append(i)
        positions={key:np.asarray(value,dtype=np.int64) for key,value in positions.items()}
        profile=HumanMappedProfile();beam=effective_settings(settings,geometry)
        result=[np.zeros(geometry.pixel_count,dtype=np.float64) for _ in range(2)];used=0
        for level in sorted(set(lower.tolist())|set((lower+1).tolist())):
            height=level*HEIGHT_STEP_M
            if abs(height)>HEIGHT_BOUND_M:raise ValueError('height interpolation outside optical envelope')
            weights=np.where(lower==level,1-fraction,np.where(lower+1==level,fraction,0.))
            if not np.any(weights):continue
            used+=1;covariance=profile.covariance(beam,height)
            covariance_key=tuple(v.hex() for v in (covariance.xx_m2,covariance.xy_m2,covariance.yy_m2))
            def sample(key,planes):
                indices=positions[key];indices=indices[weights[indices]!=0]
                a=ix[indices]-key[0]*n;b=iy[indices]-key[1]*n;u=fx[indices];v=fy[indices]
                for target,plane in zip(result,planes):
                    values=(1-u)*(1-v)*plane[b,a]+u*(1-v)*plane[b,a+1]+(1-u)*v*plane[b+1,a]+u*v*plane[b+1,a+1]
                    target[indices]+=values*weights[indices]
            pending={}
            for key,indices in positions.items():
                active=indices[weights[indices]!=0]
                if not len(active):continue
                cache_key=('response',key,covariance_key,self.map_identity)
                cached=self._get(cache_key)
                if cached is None:self.misses+=1;pending[key]=cache_key
                else:self.hits+=1;sample(key,cached)
            if pending:
                kernel,actual_rx,actual_ry=_positive_kernel(covariance,spacing)
                rx,ry=_bucket(actual_rx),_bucket(actual_ry)
                padded=np.pad(kernel,((ry-actual_ry,ry-actual_ry),(rx-actual_rx,rx-actual_rx)))
                for key,planes in self._convolve(_probe_groups(pending,rx,ry),padded,rx,ry):
                    self._put(pending[key],planes);sample(key,planes)
        if self.device!='cpu':self.torch.cuda.synchronize()
        identity=digest(canonical({'map':self.map_identity,'source':self.pins,'geometry':list(geometry._key()),
            'settings':list(settings._key()),'chunk_cells':n,'height_step_hex':HEIGHT_STEP_M.hex(),
            'intrinsic_planes_sha256':[digest(v.tobytes()) for v in result],
            'variant':'positive-native-chunks-v1','torch':self.torch.__version__,'device':self.device}))
        return MappedProbeBank(geometry,settings,identity,result[0],result[1],heights,
            time.perf_counter()-started,spacing,used)

    def close(self):
        self.cache.clear();self.resident=0
        if self.device!='cpu':self.torch.cuda.empty_cache()
