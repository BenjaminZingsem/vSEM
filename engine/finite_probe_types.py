"""Immutable finite numerical descriptors;no GPU or generation imports."""
from dataclasses import dataclass,field
import numpy as np
from .human_mapped_probe import MappedProbeBank,HumanMappedProfile


@dataclass(frozen=True)
class FiniteProfile(HumanMappedProfile):
    profile_id:str=field(default='generic-fe-sem-human-finite-v1',init=False)
    optics_id:str=field(default='vsem.finite-stored-gaussian.v1',init=False)


@dataclass(frozen=True)
class FiniteProbeBank(MappedProbeBank):
    absorbed_probability:object=field(default=None,repr=False)
    escaped_probability:object=field(default=None,repr=False)
    protocol:str=field(default='vsem.private.finite-stored-probe.v1',init=False)

    def __post_init__(self):
        super().__post_init__()
        for values in (self.absorbed_probability,self.escaped_probability):
            if (type(values) is not np.ndarray or values.shape!=(self.geometry.pixel_count,) or
                    values.dtype!=np.dtype('float64') or not np.isfinite(values).all() or np.any(values<0.) or np.any(values>1.)):
                raise ValueError('complete immutable interception/escape planes required')
            values.setflags(write=False)
        if np.any(np.abs(self.absorbed_probability+self.escaped_probability-1.)>8*np.spacing(1.)):
            raise ValueError('finite incident interception/escape probability closure')
        vacuum=self.absorbed_probability==0.
        if np.any(self.se_emitted_per_incident[vacuum]!=0.) or np.any(self.se_collected_per_incident[vacuum]!=0.):
            raise ValueError('vacuum cannot emit or collect specimen electrons')

