"""Frozen primary-cell CDF integrated only over material already present.

The eight-sigma lattice is a numerical partition,not the boundary of the beam.
Any intercepted mass outside it is a positive unresolved specimen tail. Primary
escape is separate and never deposited in the specimen. No cell is generated
for a vacuum ray. This is an explicit finite variant of the B1a partition.
"""
from dataclasses import dataclass
import math
from .finite_absorption import FiniteAbsorption
from .primary_fluence import CELL_SIZES_M,FluenceCell,rectangle_probability,NumericalConvergenceError


@dataclass(frozen=True)
class FiniteFluence:
    absorption:FiniteAbsorption
    cell_size_m:float
    cells:tuple
    box_edges_m:tuple
    unresolved_specimen_probability:float
    normalization_correction:float

    def __post_init__(self):
        if type(self.absorption) is not FiniteAbsorption or type(self.cell_size_m) is not float or self.cell_size_m not in CELL_SIZES_M:
            raise ValueError('exact finite absorption and frozen primary grid required')
        if type(self.cells) is not tuple or any(type(c) is not FluenceCell for c in self.cells):
            raise ValueError('immutable finite cell partition required')
        indices=tuple((c.index_y,c.index_x) for c in self.cells)
        if indices!=tuple(sorted(set(indices))):raise ValueError('unique row-major cells required')
        if (type(self.unresolved_specimen_probability) is not float or not math.isfinite(self.unresolved_specimen_probability) or
                not 0<=self.unresolved_specimen_probability<=self.absorption.absorbed_probability or
                type(self.normalization_correction) is not float or not math.isfinite(self.normalization_correction) or
                abs(self.normalization_correction)>5e-11):raise ValueError('finite positive partition and frozen correction required')
        if abs(math.fsum([c.probability for c in self.cells]+[self.unresolved_specimen_probability,
                -self.absorption.absorbed_probability]))>8*math.ulp(self.absorption.absorbed_probability):
            raise NumericalConvergenceError('finite specimen probability closure failed')

    def cell_rectangle(self,cell):
        if type(cell) is not FluenceCell:raise ValueError('exact primary cell required')
        x0,x1,y0,y1=self.absorption.bounds_m;s=self.cell_size_m
        return (max(x0,cell.index_x*s),min(x1,(cell.index_x+1)*s),
            max(y0,cell.index_y*s),min(y1,(cell.index_y+1)*s))


def finite_fluence(absorption,*,cell_size_m=25e-9):
    if type(absorption) is not FiniteAbsorption or type(cell_size_m) is not float or cell_size_m not in CELL_SIZES_M:
        raise ValueError('exact finite absorption and frozen primary grid required')
    a=absorption;cov=a.covariance;cx,cy=a.center_x_m,a.center_y_m;s=cell_size_m
    if a.absorbed_probability==0.:
        return FiniteFluence(a,s,(),(),0.,0.)
    sx,sy=math.sqrt(cov.xx_m2),math.sqrt(cov.yy_m2)
    ix0,ix1=math.floor((cx-8*sx)/s),math.ceil((cx+8*sx)/s)
    iy0,iy1=math.floor((cy-8*sy)/s),math.ceil((cy+8*sy)/s)
    x0,x1,y0,y1=a.bounds_m
    left,right=max(x0,ix0*s),min(x1,ix1*s)
    bottom,top=max(y0,iy0*s),min(y1,iy1*s)
    if left>=right or bottom>=top:
        return FiniteFluence(a,s,(),(),a.absorbed_probability,0.)
    def mass(rect):return rectangle_probability(cov,cx,cy,*rect)
    inside=mass((left,right,bottom,top))
    pieces=((x0,left,y0,y1),(right,x1,y0,y1),(left,right,y0,bottom),(left,right,top,y1))
    tail=math.fsum(mass(rect) for rect in pieces)
    if abs(math.fsum((inside,tail,-a.absorbed_probability)))>8e-15:
        raise NumericalConvergenceError('finite box/positive specimen tail closure failed')
    # Preserve the positively integrated smaller part. This only closes the
    # frozen numerical partition to intercepted mass;never normalize to one.
    if inside<=tail:tail=math.fsum((a.absorbed_probability,-inside))
    else:inside=math.fsum((a.absorbed_probability,-tail))
    rows=[]
    for iy in range(max(iy0,math.floor(y0/s)),min(iy1,math.ceil(y1/s))):
        for ix in range(max(ix0,math.floor(x0/s)),min(ix1,math.ceil(x1/s))):
            rect=(max(x0,ix*s),min(x1,(ix+1)*s),max(y0,iy*s),min(y1,(iy+1)*s))
            p=mass(rect)
            if p:rows.append((ix,iy,p))
    total=math.fsum(p for _,_,p in rows)
    if total==0.:
        if inside!=0.:raise NumericalConvergenceError('nonzero intercepted box has no positive cells')
        scale=1.
    else:scale=inside/total
    if not math.isfinite(scale) or abs(scale-1.)>5e-11:
        raise NumericalConvergenceError('finite-cell normalization correction exceeded frozen budget')
    cells=tuple(FluenceCell(ix,iy,p*scale) for ix,iy,p in rows)
    return FiniteFluence(a,s,cells,(left,right,bottom,top),float(tail),float(scale-1.))
