"""Exact grounded image/dose tape with deferred spatial-dose reconstruction.

The fixed ideal grounded material has no dose-dependent signal feedback. The
complete verified physical trace is its authoritative exposure history. Image
counts need only the actual incident charge and immutable response coefficients;
expensive spatial cell projections may be reconstructed exactly from that same
retained trace on demand. This variant cannot enable charging/damage feedback.
"""
import math
from .beam_profile import ELEMENTARY_CHARGE_C
from .human_mapped_probe import MappedProbeBank
from .human_fast_mapped_ledger import EpisodeExposureLedger as FullLedger,DyadicAccumulator
from .episode_raster import incident_charge_C

class EpisodeExposureLedger(FullLedger):
    def __init__(self,science,initial_settings,*,episode_namespace,seed,bank_resolver):
        super().__init__(science,initial_settings,episode_namespace=episode_namespace,
            seed=seed,bank_resolver=bank_resolver)
        self._initial_settings=initial_settings

    def _project(self,capture,index,start,end,transaction):
        handle=capture.binding
        key=(capture.identity,index,capture.label,handle.descriptor_digest)
        old=self.open_fragment
        if old is None or old['key']!=key or old['end']!=start:
            self._seal_fragment(transaction);origin=start
        else:origin=old['start']
        source=self._source(handle,capture.config,capture.settings)
        if type(source.bank) is not MappedProbeBank:
            raise ValueError('Only fixed dose-independent mapped grounded banks may defer spatial projection')
        current=capture.settings.current_pA
        q=incident_charge_C((end-origin)*current);electrons=q/ELEMENTARY_CHARGE_C
        se_mean=electrons*float(source.bank.se_collected_per_incident[index])
        bse_mean=electrons*.044
        se_emitted=q*float(source.bank.se_emitted_per_incident[index]);bse_emitted=q*.22
        ground=math.fsum((q,-se_emitted,-bse_emitted))
        for table in (capture.se,capture.bse):
            if index not in table:transaction.item(table,index,DyadicAccumulator())
        for accumulator,value in ((capture.se[index],se_mean),(capture.bse[index],bse_mean),
            (self.ground,ground),(self.se_emitted,se_emitted),(self.bse_emitted,bse_emitted)):
            transaction.attr(accumulator,'open',DyadicAccumulator.units(value))
        # No empty spatial table is presented as computed truth. Original facts
        # retain every interval/setting/geometry;dose_snapshot performs full
        # reconstruction,including observer-fragment and positive-hold rules.
        transaction.attr(self,'open_fragment',{'key':key,'raster':capture.identity,
            'pixel':index,'start':origin,'end':end,'cells':()})
        transaction.item(capture.incident,index,capture.incident.get(index,0)+(end-start)*current)

    def dose_snapshot(self):
        replay=FullLedger(self.science,self._initial_settings,episode_namespace=self.episode,
            seed=self.seed,bank_resolver=self.resolve)
        receipt=replay.ingest(tuple(self.facts[i] for i in range(1,self.last+1)))
        if receipt.status!='COMMITTED' or replay.total!=self.total:
            raise ValueError('Exact retained spatial-dose reconstruction failed')
        return replay.dose_snapshot()
