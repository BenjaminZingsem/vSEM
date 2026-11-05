"""Reusable private world spectra for the existing finite Gaussian response law.

Only preparation changes. The positive kernel,world material,local height
interpolation and acquired sampling stay identical. Actual resource admission
controls storage;source graphs never enter the physical owner or public routes.
"""
from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import time
import numpy as np
from .human_episode_types import EpisodeGeometry,EpisodeSettings,exact
from .human_specimen_map import NativeWorldMap,available_memory_bytes
from .human_mapped_probe import (HumanMappedProfile,MappedProbeBank,effective_settings,
    emitted_and_collected,_positive_kernel,_sample,HEIGHT_STEP_M,SUPPORT_SIGMA)
from .beam_profile import HEIGHT_BOUND_M

@dataclass(frozen=True)
class _Scene:
    xmin:int
    ymin:int
    nx:int
    ny:int
    spectra:tuple
    bytes:int

def _axis_extent(low,high):
    anchor=math.floor(((low+high)/2)/128)*128
    size=1
    while size<high-low+1:size*=2
    start=anchor-size//2
    while start>low or start+size-1<high:
        size*=2;start=anchor-size//2
    return start,size

class CachedProbeBuilder:
    def __init__(self,world,*,cache_bytes=None):
        if type(world) is not NativeWorldMap:raise ValueError('Exact fixed world map required')
        self.world=world
        budget=available_memory_bytes()//2 if cache_bytes is None else cache_bytes
        if type(budget) is not int or budget<1:raise ValueError('Positive trusted/measured spectrum allowance required')
        self.budget=budget;self.resident=0;self.scenes=OrderedDict();self.scene_builds=0;self.scene_hits=0

    def _scene(self,key):
        if key in self.scenes:
            scene=self.scenes.pop(key);self.scenes[key]=scene;self.scene_hits+=1;return scene
        xmin,ymin,nx,ny=key
        if nx*ny*256>available_memory_bytes()*4//5:
            raise MemoryError('Current available memory cannot admit the canonical native source extent')
        spacing=self.world.spacing
        x,y=np.meshgrid(np.arange(xmin,xmin+nx)*spacing,np.arange(ymin,ymin+ny)*spacing)
        fields=self.world.surface_arrays(x,y)
        emitted,collected=emitted_and_collected(fields)
        if np.any(emitted>4) or np.any(collected<0):raise ValueError('Source emission envelope exceeded')
        spectra=tuple(np.fft.rfftn(value) for value in (emitted,collected))
        for spectrum in spectra:spectrum.setflags(write=False)
        size=sum(s.nbytes for s in spectra)
        scene=_Scene(xmin,ymin,nx,ny,spectra,size);self.scene_builds+=1
        if size<=self.budget:
            while self.resident+size>self.budget:
                _,old=self.scenes.popitem(last=False);self.resident-=old.bytes
            self.scenes[key]=scene;self.resident+=size
        return scene

    def build(self,geometry,settings):
        exact(geometry,EpisodeGeometry);exact(settings,EpisodeSettings)
        start=time.perf_counter();world=self.world;spacing=world.spacing
        beam=effective_settings(settings,geometry);profile=HumanMappedProfile()
        px=geometry.center_x_m+(np.arange(geometry.width_px)+.5-geometry.width_px/2)*geometry.pixel_size_m
        py=geometry.center_y_m+(geometry.height_px/2-np.arange(geometry.height_px)-.5)*geometry.pixel_size_m
        x,y=np.meshgrid(px,py)
        heights=world.surface_arrays(x,y)[0].reshape(-1)
        lower=np.floor(heights/HEIGHT_STEP_M).astype(np.int64);fraction=heights/HEIGHT_STEP_M-lower
        first,last=int(lower.min()),int(lower.max())+1
        levels=[i*HEIGHT_STEP_M for i in range(first,last+1)]
        if any(abs(height)>HEIGHT_BOUND_M for height in levels):raise ValueError('Height interpolation outside optical envelope')
        covariances=[profile.covariance(beam,height) for height in levels]
        mx=max(math.ceil(SUPPORT_SIGMA*math.sqrt(c.xx_m2)/spacing) for c in covariances)+2
        my=max(math.ceil(SUPPORT_SIGMA*math.sqrt(c.yy_m2)/spacing) for c in covariances)+2
        xmin,nx=_axis_extent(math.floor(float(px.min())/spacing)-mx,math.ceil(float(px.max())/spacing)+mx+1)
        ymin,ny=_axis_extent(math.floor(float(py.min())/spacing)-my,math.ceil(float(py.max())/spacing)+my+1)
        scene=self._scene((xmin,ymin,nx,ny))
        gx=x.reshape(-1)/spacing-xmin;gy=y.reshape(-1)/spacing-ymin
        ix=np.floor(gx).astype(np.int64);iy=np.floor(gy).astype(np.int64);fx=gx-ix;fy=gy-iy
        result=[np.zeros(geometry.pixel_count,dtype=np.float64) for _ in range(2)];used=0
        for index,covariance in zip(range(first,last+1),covariances):
            weights=np.where(lower==index,1-fraction,np.where(lower+1==index,fraction,0.))
            mask=weights!=0
            if not mask.any():continue
            used+=1;kernel,rx,ry=_positive_kernel(covariance,spacing)
            folded=np.zeros((ny,nx),dtype=np.float64)
            for row in range(kernel.shape[0]):folded[(row-ry)%ny,(np.arange(kernel.shape[1])-rx)%nx]=kernel[row]
            transfer=np.fft.rfftn(folded)
            for target,spectrum in zip(result,scene.spectra):
                plane=np.fft.irfftn(spectrum*transfer,s=(ny,nx))
                target[mask]+=_sample(plane,ix[mask],iy[mask],fx[mask],fy[mask])*weights[mask]
        folder=Path(__file__).resolve().parent
        pins={name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in
            ('beam_profile.py','human_mapped_probe.py','human_cached_probe.py')}
        identity=hashlib.sha256(json.dumps({'map':world.identity_digest,'profile':profile.profile_id,
            'geometry':list(geometry._key()),'settings':list(settings._key()),'source':pins,
            'native_extent':[xmin,ymin,nx,ny],'height_step_hex':HEIGHT_STEP_M.hex(),
            'support_sigma':SUPPORT_SIGMA,'quadrature':'same-positive-kernel+canonical-cached-world-spectra.v1'},
            sort_keys=True).encode()).hexdigest()
        return MappedProbeBank(geometry,settings,identity,result[0],result[1],heights,
            time.perf_counter()-start,spacing,used)
