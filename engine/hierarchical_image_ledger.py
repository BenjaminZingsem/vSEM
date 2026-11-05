"""Explicit new analytic/native grounded bank admission;original ledger unchanged.

Both exact bank constructors enforce immutable intrinsic rates and height bounds.
This does not admit damage/charging banks or defer any live material response.
Only the bank-type predicate changes;the original exposure/count/ground arithmetic
and transactional stage binding remain independently compared by AST and tests.
"""
import math
from .beam_profile import ELEMENTARY_CHARGE_C
from .human_mapped_probe import MappedProbeBank
from .analytic_probe import AnalyticProbeBank
from .human_fast_mapped_ledger import DyadicAccumulator
from .episode_raster import incident_charge_C
from .interactive_stage_ledger import EpisodeExposureLedger as StageLedger


class EpisodeExposureLedger(StageLedger):
    def _project(self, capture, index, start, end, transaction):
        handle = capture.binding
        key = (capture.identity, index, capture.label, handle.descriptor_digest)
        old = self.open_fragment
        if old is None or old['key'] != key or old['end'] != start:
            self._seal_fragment(transaction)
            origin = start
        else:
            origin = old['start']
        source = self._source(handle, capture.config, capture.settings)
        if type(source.bank) not in (MappedProbeBank, AnalyticProbeBank):
            raise ValueError('Only explicit immutable dose-independent grounded banks may defer spatial projection')
        current = capture.settings.current_pA
        q = incident_charge_C((end - origin) * current)
        electrons = q / ELEMENTARY_CHARGE_C
        se_mean = electrons * float(source.bank.se_collected_per_incident[index])
        bse_mean = electrons * 0.044
        se_emitted = q * float(source.bank.se_emitted_per_incident[index])
        bse_emitted = q * 0.22
        ground = math.fsum((q, -se_emitted, -bse_emitted))
        for table in (capture.se, capture.bse):
            if index not in table:
                transaction.item(table, index, DyadicAccumulator())
        for (accumulator, value) in ((capture.se[index], se_mean), (capture.bse[index], bse_mean), (self.ground, ground), (self.se_emitted, se_emitted), (self.bse_emitted, bse_emitted)):
            transaction.attr(accumulator, 'open', DyadicAccumulator.units(value))
        transaction.attr(self, 'open_fragment', {'key': key, 'raster': capture.identity, 'pixel': index, 'start': origin, 'end': end, 'cells': ()})
        transaction.item(capture.incident, index, capture.incident.get(index, 0) + (end - start) * current)
