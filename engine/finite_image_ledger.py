"""Ordered finite grounded exposure with primary escape kept separate.

The existing stage,held-raster,transactional count and immutable-prefix machinery
is inherited unchanged. This explicit variant changes physical interception and
ground accounting. Spatial dose is reconstructed from the original retained
facts on demand;an empty deferred table is never presented as computed dose.
"""
from dataclasses import dataclass,field
import math
from .beam_profile import ELEMENTARY_CHARGE_C
from .episode_raster import incident_charge_C
from .human_fast_mapped_ledger import EpisodeExposureLedger as FullLedger,DyadicAccumulator
from .interactive_stage_ledger import StageBindingMixin
from .human_mapped_charge_projection import ElapsedCellCharge
from .finite_absorption import bounds_rectangle,split_probability_charge
from .finite_probe_types import FiniteProbeBank


@dataclass(frozen=True)
class FiniteChargeSnapshot:
    incident_charge_C:float
    absorbed_charge_C:float
    escaped_primary_charge_C:float
    se_emitted_charge_C:float
    bse_emitted_charge_C:float
    ground_charge_C:float
    incident_pA_ns:int
    numerical_ordinal:int
    physical_sequence:int
    protocol:str=field(default='vsem.private.finite-grounded-charge.v1',init=False)

    def __post_init__(self):
        q=incident_charge_C(self.incident_pA_ns)
        if self.incident_charge_C!=q:raise ValueError('canonical incident charge required')
        for v in (self.incident_charge_C,self.absorbed_charge_C,self.escaped_primary_charge_C,self.se_emitted_charge_C,self.bse_emitted_charge_C):
            if type(v) is not float or not math.isfinite(v) or v<0.:raise ValueError('finite nonnegative canonical charge required')
        if type(self.ground_charge_C) is not float or not math.isfinite(self.ground_charge_C):raise ValueError('finite signed ground charge required')
        if (abs(math.fsum((self.absorbed_charge_C,self.escaped_primary_charge_C,-q)))>8*math.ulp(q) or
                abs(math.fsum((self.se_emitted_charge_C,self.bse_emitted_charge_C,self.ground_charge_C,-self.absorbed_charge_C)))>8*math.ulp(q)):
            raise ValueError('canonical incident/escape/emission/ground closure failed')


@dataclass(frozen=True)
class FiniteDoseSnapshot:
    cells:tuple
    unresolved_specimen_charge_C:float
    bounds_m:tuple
    cell_size_m:float
    charge:FiniteChargeSnapshot
    protocol:str=field(default='vsem.private.finite-grounded-dose.v1',init=False)

    def __post_init__(self):
        bounds_rectangle(self.bounds_m)
        if type(self.charge) is not FiniteChargeSnapshot or type(self.cells) is not tuple or any(type(c) is not ElapsedCellCharge for c in self.cells):
            raise ValueError('exact private finite dose partition required')
        q=self.charge.incident_charge_C
        if type(self.unresolved_specimen_charge_C) is not float or not math.isfinite(self.unresolved_specimen_charge_C) or self.unresolved_specimen_charge_C<0.:
            raise ValueError('positive unresolved specimen tail required')
        deposited=math.fsum([c.charge_C for c in self.cells]+[self.unresolved_specimen_charge_C])
        if abs(math.fsum((deposited,-self.charge.absorbed_charge_C)))>8*math.ulp(q):
            raise ValueError('intercepted specimen-dose closure failed')
        x0,x1,y0,y1=self.bounds_m;s=self.cell_size_m
        for c in self.cells:
            if c.index_x*s>=x1 or (c.index_x+1)*s<=x0 or c.index_y*s>=y1 or (c.index_y+1)*s<=y0:
                raise ValueError('no specimen dose cell may lie wholly in vacuum')


class EpisodeExposureLedger(StageBindingMixin,FullLedger):
    def __init__(self,*args,bounds_m,cell_size_m=25e-9,spatial=False,**kwargs):
        self.bounds_m=bounds_rectangle(bounds_m)
        from .primary_fluence import CELL_SIZES_M
        if type(cell_size_m) is not float or cell_size_m not in CELL_SIZES_M or type(spatial) is not bool:
            raise ValueError('frozen primary scale and explicit projection variant required')
        self.cell_size_m,self.spatial=cell_size_m,spatial
        super().__init__(*args,**kwargs)
        self._initial_settings=self.actual;self.absorbed,self.escaped=DyadicAccumulator(),DyadicAccumulator()

    def _seal_fragment(self,transaction):
        if self.open_fragment is not None:
            self._seal(self.absorbed,transaction);self._seal(self.escaped,transaction)
        super()._seal_fragment(transaction)

    def _project(self,capture,index,start,end,transaction):
        handle=capture.binding;key=(capture.identity,index,capture.label,handle.descriptor_digest);old=self.open_fragment
        if old is None or old['key']!=key or old['end']!=start:
            self._seal_fragment(transaction);origin=start
        else:origin=old['start']
        source=self._source(handle,capture.config,capture.settings)
        if type(source.bank) is not FiniteProbeBank or source.bounds_m!=self.bounds_m or source.cell_size_m!=self.cell_size_m:
            raise ValueError('only this exact finite stored specimen may use finite accounting')
        bank=source.bank;current=capture.settings.current_pA;q=incident_charge_C((end-origin)*current)
        p,e=float(bank.absorbed_probability[index]),float(bank.escaped_probability[index])
        absorbed,escaped=split_probability_charge(q,p,e);electrons=q/ELEMENTARY_CHARGE_C
        se_mean=electrons*float(bank.se_collected_per_incident[index]);bse_mean=electrons*(.044*p)
        se=q*float(bank.se_emitted_per_incident[index]);bse=q*(.22*p);ground=math.fsum((absorbed,-se,-bse))
        for table in (capture.se,capture.bse):
            if index not in table:transaction.item(table,index,DyadicAccumulator())
        cells=();tail=0.
        if self.spatial:
            response=source.response(index);fluence=response.fluence;keys=[]
            for cell in fluence.cells:
                key_cell=(cell.index_x,cell.index_y);keys.append(key_cell)
                if key_cell not in self.cells:transaction.item(self.cells,key_cell,DyadicAccumulator())
                transaction.attr(self.cells[key_cell],'open',DyadicAccumulator.units(q*cell.probability))
            cells=tuple(keys);tail=q*fluence.unresolved_specimen_probability
        for accumulator,value in ((capture.se[index],se_mean),(capture.bse[index],bse_mean),
                (self.ground,ground),(self.se_emitted,se),(self.bse_emitted,bse),
                (self.absorbed,absorbed),(self.escaped,escaped),(self.tail,tail)):
            transaction.attr(accumulator,'open',DyadicAccumulator.units(value))
        transaction.attr(self,'open_fragment',{'key':key,'raster':capture.identity,'pixel':index,
            'start':origin,'end':end,'cells':cells})
        transaction.item(capture.incident,index,capture.incident.get(index,0)+(end-start)*current)

    def charge_snapshot(self):
        return FiniteChargeSnapshot(incident_charge_C(self.total),self.absorbed.rounded(),self.escaped.rounded(),
            self.se_emitted.rounded(),self.bse_emitted.rounded(),self.ground.rounded(),self.total,self.last,self.physical)

    def dose_snapshot(self):
        if not self.spatial:
            replay=EpisodeExposureLedger(self.science,self._initial_settings,episode_namespace=self.episode,
                seed=self.seed,bank_resolver=self.resolve,initial_stage=self.initial_stage,
                bounds_m=self.bounds_m,cell_size_m=self.cell_size_m,spatial=True)
            receipt=replay.ingest(tuple(self.facts[i] for i in range(1,self.last+1)))
            if receipt.status!='COMMITTED' or replay.total!=self.total or replay.charge_snapshot()!=self.charge_snapshot():
                raise ValueError('finite original-fact spatial replay failed or changed physical charge')
            return replay.dose_snapshot()
        cells=tuple(ElapsedCellCharge(x,y,value.rounded()) for (x,y),value in sorted(self.cells.items(),key=lambda item:(item[0][1],item[0][0])))
        return FiniteDoseSnapshot(cells,self.tail.rounded(),self.bounds_m,self.cell_size_m,self.charge_snapshot())
