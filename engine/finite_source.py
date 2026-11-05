"""Private finite-asset registry:mandatory existing data,no generation fallback.

The scalar owner receives only its existing opaque ScienceIdentity/BankHandle
types. The catalogue,finite bounds,expected coefficients and physical accounting
stay on this trusted numerical side of the observable-state boundary.
"""
from dataclasses import dataclass,field
import hashlib
import math
from pathlib import Path
from .beam_profile import BeamSettings,Covariance2D
from .primary_fluence import CELL_SIZES_M
from .finite_absorption import FiniteAbsorption,finite_absorption
from .finite_fluence import FiniteFluence,finite_fluence
from .finite_probe_types import FiniteProfile,FiniteProbeBank
from .human_mapped_probe import effective_settings
from .human_episode_types import ScienceIdentity,BankTicket,ScalarBankHandle,BankReady,exact,integer
from .human_mapped_response_source import source_identity,_digest
from .human_fast_mapped_source import fast_pins
from .human_photon_prefix import PROTOCOL as COUNT_PROTOCOL


def finite_source_pins():
    from .finite_probe import finite_probe_pins
    root=Path(__file__).resolve().parent
    return {'finite':finite_probe_pins(),'original_numeric_types':source_identity(),'unchanged_counts':fast_pins(),
        'finite_accounting':{n:hashlib.sha256((root/n).read_bytes()).hexdigest()
            for n in ('finite_source.py','finite_image_ledger.py','interactive_stage_ledger.py')}}


@dataclass(frozen=True)
class FiniteResponse:
    settings:BeamSettings
    center_x_m:float
    center_y_m:float
    surface_height_m:float
    primary_covariance:Covariance2D
    se_emitted_per_incident:float
    bse_emitted_per_incident:float
    se_collected_per_incident:float
    bse_collected_per_incident:float
    fluence:FiniteFluence=field(repr=False)
    profile_id:str=field(default='generic-fe-sem-human-finite-v1',init=False)
    calibration_status:str=field(default='generic_uncalibrated',init=False)
    protocol:str=field(default='vsem.private.finite-grounded-response.v1',init=False)

    def __post_init__(self):
        if type(self.settings) is not BeamSettings or type(self.primary_covariance) is not Covariance2D or type(self.fluence) is not FiniteFluence:
            raise ValueError('exact finite physical response fields required')
        mass=self.fluence.absorption
        if (mass.center_x_m,mass.center_y_m,mass.covariance)!=(self.center_x_m,self.center_y_m,self.primary_covariance):
            raise ValueError('finite fluence belongs to another physical ray')
        if type(self.surface_height_m) is not float or not math.isfinite(self.surface_height_m) or abs(self.surface_height_m)>.55e-6:
            raise ValueError('bounded physical centre height required')
        for emitted,collected,limit in ((self.se_emitted_per_incident,self.se_collected_per_incident,4.),
                (self.bse_emitted_per_incident,self.bse_collected_per_incident,.6)):
            if any(type(v) is not float or not math.isfinite(v) for v in (emitted,collected)) or not 0<=collected<=emitted<=limit:
                raise ValueError('bounded emitted/collected finite response required')
        if (self.bse_emitted_per_incident,self.bse_collected_per_incident)!=(.22*mass.absorbed_probability,.044*mass.absorbed_probability):
            raise ValueError('backscatter must arise from intercepted primaries')
        if mass.absorbed_probability==0. and (self.se_emitted_per_incident!=0. or self.se_collected_per_incident!=0.):
            raise ValueError('no specimen emission in physical vacuum')


@dataclass(frozen=True)
class ResolvedFiniteSource:
    handle:ScalarBankHandle
    bank:FiniteProbeBank=field(repr=False)
    cell_size_m:float
    bounds_m:tuple

    def response(self,index):
        integer(index,0,self.handle.geometry.pixel_count-1)
        if type(self.bank) is not FiniteProbeBank:raise ValueError('explicit finite bank required')
        settings=effective_settings(self.handle.settings,self.handle.geometry)
        x,y=self.handle.geometry.pixel_center(index);height=float(self.bank.surface_height_m[index])
        covariance=FiniteProfile().covariance(settings,height)
        mass=finite_absorption(covariance,x,y,self.bounds_m)
        if (mass.absorbed_probability,mass.escaped_probability)!=(float(self.bank.absorbed_probability[index]),float(self.bank.escaped_probability[index])):
            raise ValueError('bank interception differs from its exact primary ray')
        fluence=finite_fluence(mass,cell_size_m=self.cell_size_m)
        return FiniteResponse(settings,x,y,height,covariance,float(self.bank.se_emitted_per_incident[index]),
            .22*mass.absorbed_probability,float(self.bank.se_collected_per_incident[index]),.044*mass.absorbed_probability,fluence)


class FiniteResponseRegistry:
    def __init__(self,*,catalogue_directory,manifest_sha256,cell_size_m=25e-9,generation=1,binding_capacity=4096):
        from .finite_probe import FiniteProbeBuilder
        from .finite_gpu_catalog import GpuFiniteCatalog
        from .finite_gpu_world import GpuFiniteWorld
        if type(cell_size_m) is not float or cell_size_m not in CELL_SIZES_M:raise ValueError('frozen primary-cell scale required')
        integer(generation,1);integer(binding_capacity,1)
        self.catalog=GpuFiniteCatalog(catalogue_directory,manifest_sha256)
        self.world=GpuFiniteWorld(self.catalog);self.builder=FiniteProbeBuilder(self.world)
        self.bounds_m=self.catalog.header.bounds_m;self.cell_size_m=cell_size_m
        self.generation,self.capacity=generation,binding_capacity;self.pins=finite_source_pins()
        self.science=ScienceIdentity(FiniteProfile().profile_id,self.world.identity_digest,
            _digest({'cell_size_hex':cell_size_m.hex(),'finite_builder':self.builder.identity}),
            'VECTOR',_digest(self.pins),COUNT_PROTOCOL)
        self._bindings={};self._tickets={}

    def prepare(self,ticket):
        exact(ticket,BankTicket)
        if ticket.science!=self.science or ticket.custodian_generation!=self.generation or finite_source_pins()!=self.pins:
            raise ValueError('foreign or changed finite source/custodian')
        old=self._tickets.get(ticket.job_id)
        if old is not None:
            if old[0]!=ticket:raise ValueError('finite source job rebound')
            return BankReady(ticket,old[1])
        if len(self._bindings)>=self.capacity:raise ValueError('measured finite binding capacity exhausted')
        bank=self.builder.build(ticket.configuration.geometry,ticket.settings)
        descriptor=_digest({'bank':bank.source_identity,'science':self.science.solver_source_digest,'dwell_ns':ticket.configuration.dwell_ns})
        handle=ScalarBankHandle('finite-'+str(len(self._bindings)+1),self.generation,descriptor,self.science.solver_source_digest,
            ticket.configuration.geometry,ticket.settings)
        self._bindings[handle.handle_id]=ResolvedFiniteSource(handle,bank,self.cell_size_m,self.bounds_m)
        self._tickets[ticket.job_id]=(ticket,handle)
        return BankReady(ticket,handle)

    def resolve(self,handle):
        exact(handle,ScalarBankHandle);source=self._bindings.get(handle.handle_id)
        if source is None or source.handle!=handle or handle.source_binding_digest!=self.science.solver_source_digest:
            raise ValueError('unregistered or rebound finite handle')
        return source

    def close(self):self.builder.close();self.catalog.close()
