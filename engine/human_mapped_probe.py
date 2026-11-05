"""New private map/probe response candidate;never refocus a recorded image.

Positive native-grid Gaussian quadrature + fixed world material fields produce
expected SE response BEFORE exposure. This is a new numerical/profile variant,
not a renamed B0/B1 result. Actual native detector/count/timing gates still apply.
"""
from dataclasses import dataclass,field
import hashlib
import json
import math
from pathlib import Path
import time
import numpy as np
from .beam_profile import BeamProfile,BeamSettings,HEIGHT_BOUND_M
from .human_episode_types import EpisodeGeometry,EpisodeSettings,exact,integer
from .human_specimen_map import NativeWorldMap,available_memory_bytes

HEIGHT_STEP_M=50e-9
SUPPORT_SIGMA=9.0
PROTOCOL='vsem.private.mapped-se-probe.v1'

@dataclass(frozen=True)
class HumanMappedProfile(BeamProfile):
    profile_id:str=field(default='generic-fe-sem-human-mapped-v1',init=False)
    optics_id:str=field(default='vsem.human-mapped-gaussian.v1',init=False)
    # Normalized controls have no named-instrument calibration. A larger
    # explicit generic focal-plane span provides discernible alignment effects.
    astigmatic_plane_scale_m:float=field(default=15e-6,init=False)

def effective_settings(settings,geometry):
    exact(settings,EpisodeSettings);exact(geometry,EpisodeGeometry)
    focus=settings.focus_offset_m if geometry.stage_z_m==0. else settings.focus_offset_m+geometry.stage_z_m
    return BeamSettings(settings.current_pA/10**12,focus,settings.stigmator_x,settings.stigmator_y)

def emitted_and_collected(fields):
    _,sx,sy,yield_se=fields
    normal=np.sqrt(1+sx*sx+sy*sy)
    emitted=yield_se*normal
    return emitted,emitted*.35*(1-.2*sx/normal)

def _positive_kernel(covariance,spacing):
    rx=math.ceil(SUPPORT_SIGMA*math.sqrt(covariance.xx_m2)/spacing)
    ry=math.ceil(SUPPORT_SIGMA*math.sqrt(covariance.yy_m2)/spacing)
    x,y=np.meshgrid(np.arange(-rx,rx+1)*spacing,np.arange(-ry,ry+1)*spacing)
    det=covariance.xx_m2*covariance.yy_m2-covariance.xy_m2**2
    kernel=np.exp(-.5*(covariance.yy_m2*x*x-2*covariance.xy_m2*x*y+covariance.xx_m2*y*y)/det)
    kernel/=np.sum(kernel,dtype=np.float64)
    return kernel,rx,ry

def _sample(plane,ix,iy,fx,fy):
    return ((1-fx)*(1-fy)*plane[iy,ix]+fx*(1-fy)*plane[iy,ix+1]+
            (1-fx)*fy*plane[iy+1,ix]+fx*fy*plane[iy+1,ix+1])

@dataclass(frozen=True)
class MappedProbeBank:
    geometry:EpisodeGeometry
    settings:EpisodeSettings
    source_identity:str
    se_emitted_per_incident:object=field(repr=False)
    se_collected_per_incident:object=field(repr=False)
    surface_height_m:object=field(repr=False)
    construction_s:float
    native_spacing_m:float
    height_layers:int
    protocol:str=field(default=PROTOCOL,init=False)

    def __post_init__(self):
        exact(self.geometry,EpisodeGeometry);exact(self.settings,EpisodeSettings)
        for values in (self.se_emitted_per_incident,self.se_collected_per_incident):
            if (type(values) is not np.ndarray or values.shape!=(self.geometry.pixel_count,)
                    or values.dtype!=np.dtype('float64') or not np.isfinite(values).all()
                    or np.any(values<0) or np.any(values>4)):
                raise ValueError('Complete finite native mapped response plane required')
            values.setflags(write=False)
        if np.any(self.se_collected_per_incident>self.se_emitted_per_incident):
            raise ValueError('Collected SE response exceeds emitted response')
        values=self.surface_height_m
        if (type(values) is not np.ndarray or values.shape!=(self.geometry.pixel_count,)
                or values.dtype!=np.dtype('float64') or not np.isfinite(values).all()
                or np.any(np.abs(values)>.55e-6)):
            raise ValueError('Complete immutable native surface heights required')
        values.setflags(write=False)

    def coefficient(self,index):
        integer(index,0,self.geometry.pixel_count-1)
        return float(self.se_collected_per_incident[index])

def build_probe_bank(world,geometry,settings):
    if type(world) is not NativeWorldMap:raise ValueError('Exact fixed native-world map required')
    beam=effective_settings(settings,geometry)
    profile=HumanMappedProfile();spacing=world.spacing
    start=time.perf_counter()
    shape=(geometry.height_px,geometry.width_px)
    columns=np.arange(geometry.width_px,dtype=np.float64)
    rows=np.arange(geometry.height_px,dtype=np.float64)
    px=geometry.center_x_m+(columns+.5-geometry.width_px/2)*geometry.pixel_size_m
    py=geometry.center_y_m+(geometry.height_px/2-rows-.5)*geometry.pixel_size_m
    x,y=np.meshgrid(px,py)
    heights=world.surface_arrays(x,y)[0].reshape(-1)
    lower=np.floor(heights/HEIGHT_STEP_M).astype(np.int64)
    fraction=heights/HEIGHT_STEP_M-lower
    first,last=int(lower.min()),int(lower.max())+1
    layer_heights=[index*HEIGHT_STEP_M for index in range(first,last+1)]
    if any(abs(height)>HEIGHT_BOUND_M for height in layer_heights):
        raise ValueError('Complete mapped height interpolation outside optical envelope')
    covariances=[profile.covariance(beam,height) for height in layer_heights]
    margin_x=max(math.ceil(SUPPORT_SIGMA*math.sqrt(c.xx_m2)/spacing) for c in covariances)+2
    margin_y=max(math.ceil(SUPPORT_SIGMA*math.sqrt(c.yy_m2)/spacing) for c in covariances)+2
    xmin=math.floor(float(px.min())/spacing)-margin_x
    xmax=math.ceil(float(px.max())/spacing)+margin_x+1
    ymin=math.floor(float(py.min())/spacing)-margin_y
    ymax=math.ceil(float(py.max())/spacing)+margin_y+1
    nx,ny=xmax-xmin+1,ymax-ymin+1
    # Admission follows CURRENT hardware availability,not a small fixed quota.
    estimated_peak=nx*ny*256+geometry.pixel_count*160
    if estimated_peak>available_memory_bytes()*4//5:
        raise MemoryError('Actual available memory cannot admit this native probe extent')
    wx,wy=np.meshgrid(np.arange(xmin,xmax+1)*spacing,np.arange(ymin,ymax+1)*spacing)
    fields=world.surface_arrays(wx,wy)
    emitted,collected=emitted_and_collected(fields)
    if np.max(emitted)>4 or np.min(collected)<0:
        raise ValueError('Mapped source emission outside declared generic envelope')
    spectra=[np.fft.rfftn(emitted),np.fft.rfftn(collected)]
    gx=x.reshape(-1)/spacing-xmin;gy=y.reshape(-1)/spacing-ymin
    ix=np.floor(gx).astype(np.int64);iy=np.floor(gy).astype(np.int64)
    fx=gx-ix;fy=gy-iy
    result=[np.zeros(geometry.pixel_count,dtype=np.float64) for _ in range(2)]
    used=0
    for index,covariance in zip(range(first,last+1),covariances):
        weights=np.where(lower==index,1-fraction,np.where(lower+1==index,fraction,0.))
        mask=weights!=0
        if not mask.any():continue
        used+=1
        kernel,rx,ry=_positive_kernel(covariance,spacing)
        # Circular convolution is used only with a real SOURCE halo exceeding
        # the full finite positive kernel support. Only interior rays are sampled.
        folded=np.zeros((ny,nx),dtype=np.float64)
        for row in range(kernel.shape[0]):
            yy=(row-ry)%ny
            folded[yy,(np.arange(kernel.shape[1])-rx)%nx]=kernel[row]
        transfer=np.fft.rfftn(folded)
        for target,spectrum in zip(result,spectra):
            plane=np.fft.irfftn(spectrum*transfer,s=(ny,nx))
            target[mask]+=_sample(plane,ix[mask],iy[mask],fx[mask],fy[mask])*weights[mask]
    folder=Path(__file__).resolve().parent
    pins={name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in ('beam_profile.py','human_mapped_probe.py')}
    identity=hashlib.sha256(json.dumps({'map':world.identity_digest,'profile':profile.profile_id,
        'geometry':list(geometry._key()),'settings':list(settings._key()),'source':pins,
        'height_step_hex':HEIGHT_STEP_M.hex(),'support_sigma':SUPPORT_SIGMA,
        'quadrature':'positive-native-world-grid-gaussian+bilinear-height-v1'},sort_keys=True).encode()).hexdigest()
    return MappedProbeBank(geometry,settings,identity,result[0],result[1],heights,
        time.perf_counter()-start,spacing,used)

def direct_analytic_coefficient(specimen,geometry,settings,index):
    """Independent unchanged B0 quadrature over this NEW fine human source.

    This is an oracle for map/probe approximation;it is not a detector count,
    acquired image or use of the original incompatible B0 specimen descriptor.
    """
    from .beam_profile import gaussian_quadrature
    beam=effective_settings(settings,geometry);x,y=geometry.pixel_center(index)
    height=specimen.surface(x,y)[0]
    covariance=HumanMappedProfile().covariance(beam,height)
    points=gaussian_quadrature(covariance,'SE')
    terms=[]
    for dx,dy,weight in points:
        _,sx,sy,yield_se=specimen.surface(x+dx,y+dy)
        normal=math.sqrt(1+sx*sx+sy*sy)
        terms.append(weight*yield_se*normal*.35*(1-.2*sx/normal))
    return math.fsum(terms)
