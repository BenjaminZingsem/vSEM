"""Actual image projection can advance before exact spatial cache construction."""
import unittest
from dataclasses import replace
from acceptance.test_human_live_image_numerics import RealNumericalProbe
from engine.human_episode_types import ScanRequest

class LazyDoseTests(unittest.TestCase):
    def test_actual_images_keep_exact_history_without_waiting_for_cell_projection(self):
        p=RealNumericalProbe();calls=[];actual_resolve=p.registry.resolve
        class ObservedRealSource:
            def __init__(self,source):self.source=source;self.handle=source.handle;self.bank=source.bank
            def response(self,index):
                calls.append(index)
                return self.source.response(index)  # Actual qualified function,never a solver mock.
        p.ledger.resolve=lambda handle:ObservedRealSource(actual_resolve(handle))
        opened=p.start(ScanRequest(4,3,2e-6,0.,0.,1000))
        identifier=opened.started_raster_ids[0]
        p.tick(50_000_000+p.engine.capture.plan.program_end_ns)
        self.assertEqual(calls,[])
        prefix=p.ledger.capture_prefix(identifier)
        self.assertEqual(prefix.outcome,'COMPLETED')
        self.assertGreater(sum(prefix.se_means),0)
        self.assertEqual(p.ledger.total,12*1000*10)
        dose=p.ledger.dose_snapshot()
        self.assertEqual(len(calls),12)
        self.assertTrue(dose.cells)
        self.assertEqual(dose.incident_total_pA_ns,p.ledger.total)

if __name__=='__main__':unittest.main()
