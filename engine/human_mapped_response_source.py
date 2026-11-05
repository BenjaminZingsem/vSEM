"""Actual off-actor mapped banks + unchanged primary-fluence charge mathematics.

New explicitly generic human SE source. No graph/rate plane/seed is a public
observation or actor input. Stored expected signals become counts only when the
ordered follower receives original physical exposure records.
"""
from dataclasses import dataclass,field
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np
from .beam_profile import BeamSettings,Covariance2D,HEIGHT_BOUND_M
from .human_mapped_probe import HumanMappedProfile,MappedProbeBank,build_probe_bank,effective_settings
from .human_specimen_map import NativeWorldMap
from .primary_fluence import PrimaryFluence,primary_fluence,CELL_SIZES_M
from .human_episode_types import (ScienceIdentity,EpisodeSettings,ScalarBankHandle,
    BankTicket,BankReady,exact,integer)
from .episode_detector_counts import PROTOCOL as COUNT_PROTOCOL

SOURCE_NAMES=('beam_profile.py','human_mapped_probe.py','human_specimen_map.py',
    'fine_practice_specimen.py','procedural_specimen.py','primary_fluence.py',
    'human_episode_types.py','episode_detector_counts.py','human_mapped_response_source.py',
    'human_mapped_charge_projection.py')

def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def source_identity():
    folder=Path(__file__).resolve().parent
    sources={name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in SOURCE_NAMES}
    sources['packages/specimens/bounds_index.py']=hashlib.sha256((folder.parent/'packages/specimens/bounds_index.py').read_bytes()).hexdigest()
    return {'source':sources,'python':sys.version,'numpy':np.__version__,'byteorder':sys.byteorder}

@dataclass(frozen=True)
class MappedResponse:
    profile_id:str
    calibration_status:str
    settings:BeamSettings
    center_x_m:float
    center_y_m:float
    surface_height_m:float
    primary_covariance:Covariance2D
    se_emitted_per_incident:float
    bse_emitted_per_incident:float
    se_collected_per_incident:float
    bse_collected_per_incident:float
    fluence:PrimaryFluence=field(repr=False)
    protocol:str=field(default='vsem.human-mapped-grounded-response.v1',init=False)
    solver_id:str=field(default='vsem.human-mapped-shared-exposure.v1',init=False)

    def __post_init__(self):
        if self.profile_id!='generic-fe-sem-human-mapped-v1' or self.calibration_status!='generic_uncalibrated':
            raise ValueError('Exact new generic human mapped profile required')
        if type(self.settings) is not BeamSettings or type(self.primary_covariance) is not Covariance2D or type(self.fluence) is not PrimaryFluence:
            raise ValueError('Exact beam/fluence source fields required')
        for value in (self.center_x_m,self.center_y_m):
            if type(value) is not float or not math.isfinite(value) or abs(value)>.055:
                raise ValueError('Finite source-coordinate envelope required')
        if type(self.surface_height_m) is not float or not math.isfinite(self.surface_height_m) or abs(self.surface_height_m)>HEIGHT_BOUND_M:
            raise ValueError('Finite source height required')
        if (self.fluence.center_x_m,self.fluence.center_y_m,self.fluence.covariance)!=(self.center_x_m,self.center_y_m,self.primary_covariance):
            raise ValueError('Primary fluence belongs to another ray')
        for emitted,collected,limit in ((self.se_emitted_per_incident,self.se_collected_per_incident,4.),
                                         (self.bse_emitted_per_incident,self.bse_collected_per_incident,.6)):
            if any(type(v) is not float or not math.isfinite(v) for v in (emitted,collected)) or not 0<=collected<=emitted<=limit:
                raise ValueError('Bounded emitted/collected response required')

@dataclass(frozen=True)
class ResolvedMappedSource:
    handle:ScalarBankHandle
    bank:MappedProbeBank=field(repr=False)
    cell_size_m:float
    def response(self,index):
        integer(index,0,self.handle.geometry.pixel_count-1)
        profile=HumanMappedProfile();settings=effective_settings(self.handle.settings,self.handle.geometry)
        x,y=self.handle.geometry.pixel_center(index)
        height=float(self.bank.surface_height_m[index])
        covariance=profile.covariance(settings,height)
        fluence=primary_fluence(covariance,x,y,cell_size_m=self.cell_size_m)
        # The first human profile enables SE. The shared-charge reference keeps
        # a fixed generic .22 backscatter yield/.20 collection for its uniform
        # conductive material. No composition-resolving BSE control is advertised.
        return MappedResponse(profile.profile_id,profile.calibration_status,settings,x,y,height,covariance,
            float(self.bank.se_emitted_per_incident[index]),.22,
            float(self.bank.se_collected_per_incident[index]),.044,fluence)

class MappedResponseRegistry:
    def __init__(self,*,world=None,cell_size_m=25e-9,generation=1,binding_capacity=4096):
        world=NativeWorldMap() if world is None else world
        if type(world) is not NativeWorldMap or type(cell_size_m) is not float or cell_size_m not in CELL_SIZES_M:
            raise ValueError('Exact native world/qualified primary grid required')
        integer(generation,1);integer(binding_capacity,1)
        self.world,self.cell_size_m,self.generation,self.capacity=world,cell_size_m,generation,binding_capacity
        self.pins=source_identity()
        self.science=ScienceIdentity(HumanMappedProfile().profile_id,_digest(world.identity),
            _digest({'primary_cell_size_hex':cell_size_m.hex(),'native_spacing_hex':world.spacing.hex(),
                     'frame':'stage-xyz-raster-y-up-v1'}),'VECTOR',_digest(self.pins),COUNT_PROTOCOL)
        self._bindings={};self._tickets={}
    def prepare(self,ticket):
        exact(ticket,BankTicket)
        if ticket.science!=self.science or ticket.custodian_generation!=self.generation or source_identity()!=self.pins:
            raise ValueError('Foreign/changed mapped source or custodian generation')
        old=self._tickets.get(ticket.job_id)
        if old is not None:
            if old[0]!=ticket:raise ValueError('Owned mapped job identity rebound')
            return BankReady(ticket,old[1])
        if len(self._bindings)>=self.capacity:raise ValueError('Trusted measured mapped binding allowance exhausted')
        bank=build_probe_bank(self.world,ticket.configuration.geometry,ticket.settings)
        descriptor=_digest({'bank':bank.source_identity,'science':self.science.solver_source_digest,
                            'dwell_ns':ticket.configuration.dwell_ns})
        handle=ScalarBankHandle('mapped-'+str(len(self._bindings)+1),self.generation,descriptor,
            self.science.solver_source_digest,ticket.configuration.geometry,ticket.settings)
        self._bindings[handle.handle_id]=ResolvedMappedSource(handle,bank,self.cell_size_m)
        self._tickets[ticket.job_id]=(ticket,handle)
        return BankReady(ticket,handle)
    def resolve(self,handle):
        exact(handle,ScalarBankHandle);source=self._bindings.get(handle.handle_id)
        if source is None or source.handle!=handle or handle.source_binding_digest!=self.science.solver_source_digest:
            raise ValueError('Unregistered/rebound mapped handle')
        return source
