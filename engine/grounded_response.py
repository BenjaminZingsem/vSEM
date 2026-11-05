"""Pure private grounded SE/BSE response and one-interval exposure algebra.

No actor, sampler, mutable history, public projection or enabled capability.
The qualified B0 specimen and Gaussian model are immutable dependencies.
"""
from dataclasses import dataclass, field
import math
import numpy as np
from .beam_profile import (BeamProfile, BeamSettings, Covariance2D,
                           ELEMENTARY_CHARGE_C, gaussian_quadrature)
from .fine_specimen import FineSpecimen
from .primary_fluence import (PrimaryFluence, primary_fluence,
                              _coordinate, _real)


@dataclass(frozen=True)
class GroundedResponse:
    profile_id: str
    calibration_status: str
    settings: BeamSettings
    center_x_m: float
    center_y_m: float
    surface_height_m: float
    primary_covariance: Covariance2D
    se_emitted_per_incident: float
    bse_emitted_per_incident: float
    se_collected_per_incident: float
    bse_collected_per_incident: float
    fluence: PrimaryFluence
    protocol: str = field(default='vsem.grounded-response.v1',init=False)
    solver_id: str = field(default='vsem.grounded-shared-exposure.v1',init=False)

    def __post_init__(self):
        if self.profile_id != 'generic-fe-sem-grounded-v2' or self.calibration_status != 'generic_uncalibrated':
            raise ValueError('exact grounded profile required')
        if type(self.settings) is not BeamSettings or type(self.primary_covariance) is not Covariance2D:
            raise ValueError('exact settings/covariance required')
        _coordinate(self.center_x_m); _coordinate(self.center_y_m)
        _real(self.surface_height_m,-.552e-6,.552e-6,'height')
        if type(self.fluence) is not PrimaryFluence or (self.fluence.center_x_m,
                self.fluence.center_y_m,self.fluence.covariance) != (
                self.center_x_m,self.center_y_m,self.primary_covariance):
            raise ValueError('fluence must describe the original primary')
        for name,limit in (('se_emitted_per_incident',4.0),
                           ('bse_emitted_per_incident',.6)):
            _real(getattr(self,name),0.0,limit,name)
        _real(self.se_collected_per_incident,0.0,self.se_emitted_per_incident,'SE collection')
        _real(self.bse_collected_per_incident,0.0,self.bse_emitted_per_incident,'BSE collection')


def _coefficients(specimen,kernel,cx,cy,channel,vectorized):
    if vectorized:
        samples = np.asarray(kernel,dtype=np.float64)
        _,dx,dy,se,bse = specimen.surface_arrays(cx+samples[:,0],cy+samples[:,1])
        if channel == 'SE':
            norm = np.sqrt(1+dx*dx+dy*dy)
            emitted = se*norm
            collected = emitted*.35*(1-.2*dx/norm)
        else:
            emitted,collected = bse,.20*bse
        return (math.fsum(float(w*v) for w,v in zip(samples[:,2],emitted)),
                math.fsum(float(w*v) for w,v in zip(samples[:,2],collected)))
    emitted, collected = [], []
    for x,y,weight in kernel:
        _,dx,dy,se,bse = specimen.surface(cx+x,cy+y)
        if channel == 'SE':
            norm = math.sqrt(1+dx*dx+dy*dy)
            signal = se*norm
            efficiency = .35*(1-.2*dx/norm)
        else:
            signal,efficiency = bse,.20
        emitted.append(weight*signal); collected.append(weight*signal*efficiency)
    return math.fsum(emitted),math.fsum(collected)


def prepare_response(profile,specimen,settings,x_m,y_m,*,cell_size_m=25e-9,vectorized=True):
    if type(profile) is not BeamProfile or type(specimen) is not FineSpecimen or type(settings) is not BeamSettings:
        raise ValueError('exact B0 profile/specimen/settings required')
    if type(vectorized) is not bool:
        raise ValueError('exact vectorized bool required')
    cx,cy = _coordinate(x_m),_coordinate(y_m)
    bound = specimen.bounds()
    if .36*math.sqrt(1+bound.slope_magnitude**2) > 4.0:
        raise ValueError('specimen slope/emission envelope unsupported')
    height = specimen.surface(cx,cy)[0]
    primary = profile.covariance(settings,height)
    se_kernel = gaussian_quadrature(primary,'SE')
    bse_kernel = gaussian_quadrature(profile.channel_covariance(settings,height,'BSE'),'BSE')
    # Check every actual evaluated sample; no kernel clipping near domain edges.
    for kernel in (se_kernel,bse_kernel):
        for x,y,_ in kernel:
            _coordinate(cx+x); _coordinate(cy+y)
    fluence = primary_fluence(primary,cx,cy,cell_size_m=cell_size_m)
    se_emit,se_collect = _coefficients(specimen,se_kernel,cx,cy,'SE',vectorized)
    bse_emit,bse_collect = _coefficients(specimen,bse_kernel,cx,cy,'BSE',vectorized)
    return GroundedResponse(profile.profile_id,profile.calibration_status,settings,
        cx,cy,height,primary,se_emit,bse_emit,se_collect,bse_collect,fluence)


@dataclass(frozen=True)
class CellCharge:
    index_x: int
    index_y: int
    charge_C: float

    def __post_init__(self):
        if type(self.index_x) is not int or type(self.index_y) is not int:
            raise ValueError('exact cell indices required')
        _real(self.charge_C,0.0,float('inf'),'cell charge')


@dataclass(frozen=True)
class GroundedExposure:
    start_s: float
    end_s: float
    incident_charge_C: float
    incident_electrons: float
    se_mean: float
    bse_mean: float
    se_emitted_charge_C: float
    bse_emitted_charge_C: float
    ground_charge_C: float
    cell_charges: tuple
    tail_charge_C: float
    protocol: str = field(default='vsem.grounded-exposure.v1',init=False)

    def __post_init__(self):
        _real(self.start_s,0.0,float('inf'),'start')
        _real(self.end_s,self.start_s,float('inf'),'end')
        for name in ('incident_charge_C','incident_electrons','se_mean','bse_mean',
                     'se_emitted_charge_C','bse_emitted_charge_C','tail_charge_C'):
            _real(getattr(self,name),0.0,float('inf'),name)
        _real(self.ground_charge_C,-float('inf'),float('inf'),'ground charge')
        if type(self.cell_charges) is not tuple or any(type(c) is not CellCharge for c in self.cell_charges):
            raise ValueError('immutable cell charges required')
        indices = tuple((c.index_y,c.index_x) for c in self.cell_charges)
        if indices != tuple(sorted(set(indices))):
            raise ValueError('unique row-major charges required')
        tolerance = 8*math.ulp(self.incident_charge_C)+1e-30
        deposited = math.fsum(c.charge_C for c in self.cell_charges)+self.tail_charge_C
        imbalance = math.fsum((-self.incident_charge_C,self.se_emitted_charge_C,
                               self.bse_emitted_charge_C,self.ground_charge_C))
        if abs(deposited-self.incident_charge_C) > tolerance or abs(imbalance) > tolerance:
            raise ValueError('grounded interval charge closure failed')


def exposure_for_interval(response,start_s,end_s):
    if type(response) is not GroundedResponse:
        raise ValueError('exact GroundedResponse required')
    start = _real(start_s,0.0,float('inf'),'start')
    end = _real(end_s,start,float('inf'),'end')
    charge = response.settings.current_A*(end-start)
    electrons = charge/ELEMENTARY_CHARGE_C
    se_emit,bse_emit = (charge*response.se_emitted_per_incident,
                       charge*response.bse_emitted_per_incident)
    return GroundedExposure(start,end,charge,electrons,
        electrons*response.se_collected_per_incident,
        electrons*response.bse_collected_per_incident,se_emit,bse_emit,
        charge-se_emit-bse_emit,
        tuple(CellCharge(c.index_x,c.index_y,charge*c.probability) for c in response.fluence.cells),
        charge*response.fluence.tail_probability)
