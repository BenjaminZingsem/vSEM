"""Private trusted episode boundary; never an operator transport or readback.

Generic uncalibrated proxies. Grounded stable is an ideal practice reference,
not a claim of measured sample conductivity or radiation-damage resistance.
"""
from dataclasses import dataclass
import math
from typing import Optional


@dataclass(frozen=True)
class SpecimenMaterial:
    grounded: bool = False
    damage_charge_scale_C: Optional[float] = 2e-12

    def __post_init__(self):
        if type(self.grounded) is not bool:
            raise ValueError('trusted material grounding must be boolean')
        value=self.damage_charge_scale_C
        if value is not None:
            if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
                raise ValueError('trusted damage scale must be finite positive or absent')
            object.__setattr__(self,'damage_charge_scale_C',float(value))


LEGACY_HISTORY_PROXY=SpecimenMaterial()
GROUNDED_STABLE_REFERENCE=SpecimenMaterial(grounded=True,damage_charge_scale_C=None)
