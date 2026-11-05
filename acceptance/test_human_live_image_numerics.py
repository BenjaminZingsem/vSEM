"""Genuine response/count/charge integration;no numerical solver mocks."""
from dataclasses import replace
import math
import struct
import unittest

from engine.human_live_mapped_source import LiveMappedResponseRegistry as MappedResponseRegistry
from engine.human_live_image_ledger import EpisodeExposureLedger
from engine.human_grounded_episode import GroundedEpisode
from engine.episode_credits import EpisodeCapacity
from engine.human_episode_types import (EpisodeSettings, EpisodeInputs, GrantAuthority,
    StartCapture, ScanRequest, VerifiedAcknowledgement, SafetyStop, SetOptics,
    ConfigureLive, ScalarBankHandle)
from engine.detector_count_prefix import CountProcess as OriginalCounts
from engine.episode_detector_counts import CountProcess as WiderCounts
from engine.human_photon_prefix import CountProcess as HumanCounts
from engine.human_mapped_charge_projection import exposure_for_charge

SEED = b'acceptance-private-count-seed-001'
SEED = SEED.ljust(32, b'!')[:32]


class RealNumericalProbe:
    def __init__(self, settings=None):
        self.registry = MappedResponseRegistry()
        initial = settings or EpisodeSettings(10, 1.2e-6, .18, -.12)
        self.engine = GroundedEpisode(self.registry.science, initial, episode_namespace='actual1',
            capacity=EpisodeCapacity(4096, 128, 128, 4096, 512, 512))
        self.ledger = EpisodeExposureLedger(self.registry.science, initial, episode_namespace='actual1',
            seed=SEED, bank_resolver=self.registry.resolve)
        self.all_facts = []
        result = self.tick(0, EpisodeInputs(authority=GrantAuthority('grant', 'human', 10**12)))
        self.authority = result.state.lease.authority

    def tick(self, at, inputs=None):
        inputs = inputs or EpisodeInputs()
        # Every acknowledgement comes from actually committed original facts.
        inputs = replace(inputs, verified_ack=VerifiedAcknowledgement('actual1', self.ledger.last))
        result = self.engine.tick(at, inputs)
        receipt = self.ledger.ingest(result.facts)
        if receipt.status != 'COMMITTED':
            raise AssertionError((receipt, [(f.kind, f.body) for f in result.facts]))
        self.all_facts.extend(result.facts)
        return result

    def start(self, request, op='start', at=0, mode='SINGLE', generation=0):
        result = self.tick(at, EpisodeInputs(normal=StartCapture(op, self.authority, mode, request, generation)))
        if result.bank_dispatch is not None:
            ready = self.registry.prepare(result.bank_dispatch)
            self.tick(at+1, EpisodeInputs(bank_result=ready))
        return self.tick(at+50_000_000)


class EpisodeNumericalTests(unittest.TestCase):
    def test_wider_constructor_preserves_original_counts_on_old_indices(self):
        for index in (0, 17, 65535):
            for channel in ('SE', 'BSE'):
                for mean in (0., .25, 7.5, 1000., 100000.):
                    self.assertEqual(OriginalCounts(SEED, 'same-causal-id', index, channel).count(mean),
                                     WiderCounts(SEED, 'same-causal-id', index, channel).count(mean))
        self.assertIs(type(WiderCounts(SEED, 'large-causal-id', 131071, 'SE').count(4.)), int)
        with self.assertRaises(ValueError):
            WiderCounts(SEED, 'large-causal-id', 16777216, 'SE')

    def test_complete_capture_matches_actual_independent_charge_and_count_calls(self):
        probe = RealNumericalProbe()
        result = probe.start(ScanRequest(4, 3, 2e-6, 0., 0., 1000))
        identifier = result.started_raster_ids[0]
        opened = next(f for f in result.facts if f.kind == 'RASTER_START')
        configuration, handle = opened.body[6], opened.body[7]
        source = probe.registry.resolve(handle)
        end = 50_000_000+probe.engine.capture.plan.program_end_ns
        probe.tick(end)
        prefix = probe.ledger.capture_prefix(identifier)
        self.assertEqual(prefix.outcome, 'COMPLETED')
        se, bse = prefix.counts.read(0, configuration.geometry.pixel_count)
        for index in range(configuration.geometry.pixel_count):
            direct = exposure_for_charge(source.response(index), current_pA=10, incident_pA_ns=10000)
            self.assertEqual(prefix.se_means[index].hex(), direct.se_mean.hex())
            self.assertEqual(prefix.bse_means[index].hex(), direct.bse_mean.hex())
            self.assertEqual(struct.unpack_from('<I', se, 4*index)[0],
                HumanCounts(SEED, 'actual1:'+identifier, index, 'SE').count(direct.se_mean))
            self.assertEqual(struct.unpack_from('<I', bse, 4*index)[0],
                HumanCounts(SEED, 'actual1:'+identifier, index, 'BSE').count(direct.bse_mean))
        dose = probe.ledger.dose_snapshot()
        self.assertEqual(dose.incident_total_pA_ns, 4*3*1000*10)
        self.assertAlmostEqual(math.fsum(c.charge_C for c in dose.cells)+dose.tail_charge_C,
            dose.incident_total_pA_ns/10**21, delta=8*math.ulp(dose.incident_total_pA_ns/10**21))

    def test_observer_cuts_preserve_bitwise_counts_means_and_cell_dose(self):
        request = ScanRequest(2, 2, 1e-6, 0., 0., 1000)
        coarse, fine = RealNumericalProbe(), RealNumericalProbe()
        first = coarse.start(request).started_raster_ids[0]
        second = fine.start(request).started_raster_ids[0]
        end = 50_000_000+coarse.engine.capture.plan.program_end_ns
        for at in (70_000_001, 70_000_017, 70_000_333, 70_000_999, 70_001_001, 70_001_741):
            fine.tick(at)
        coarse.tick(end); fine.tick(end)
        a, b = coarse.ledger.capture_prefix(first), fine.ledger.capture_prefix(second)
        self.assertEqual(a.counts.read(0, 4), b.counts.read(0, 4))
        self.assertEqual(tuple(v.hex() for v in a.se_means), tuple(v.hex() for v in b.se_means))
        self.assertEqual(tuple(v.hex() for v in a.bse_means), tuple(v.hex() for v in b.bse_means))
        da, db = coarse.ledger.dose_snapshot(), fine.ledger.dose_snapshot()
        self.assertEqual(da.cells, db.cells)
        self.assertEqual((da.tail_charge_C.hex(), da.ground_charge_C.hex()),
                         (db.tail_charge_C.hex(), db.ground_charge_C.hex()))

    def test_zoom_and_offsets_keep_old_geometry_and_one_accumulated_ledger(self):
        probe = RealNumericalProbe()
        opened = probe.start(ScanRequest(4, 2, 2e-6, 0., 0., 1000), mode='LIVE')
        old_id = opened.started_raster_ids[0]
        old_configuration = opened.state.current_configuration
        probe.tick(51_000_000, EpisodeInputs(normal=ConfigureLive('zoom', probe.authority,
            ScanRequest(3, 2, 4e-6, .2e-6, -.1e-6, 2000), 0)))
        boundary = probe.tick(100_000_000)
        old = probe.ledger.capture_prefix(old_id)
        self.assertEqual(old.configuration, old_configuration)
        self.assertEqual(old.incident_total_pA_ns, 8*1000*10)
        new = probe.tick(100_000_001, EpisodeInputs(bank_result=probe.registry.prepare(boundary.bank_dispatch)))
        new_id = new.started_raster_ids[0]
        probe.tick(150_000_000, EpisodeInputs(stop=SafetyStop('stop', probe.authority)))
        current = probe.ledger.capture_prefix(new_id)
        self.assertEqual(current.configuration.geometry.width_px, 3)
        self.assertEqual(current.configuration.geometry.field_width_m, 4e-6)
        self.assertEqual(probe.ledger.total, old.incident_total_pA_ns+current.incident_total_pA_ns)
        self.assertEqual(probe.ledger.dose_snapshot().incident_total_pA_ns, probe.engine.snapshot().episode_incident_pA_ns)

    def test_real_512_axis_partial_capture_preserves_native_storage_and_mask_numerator(self):
        probe = RealNumericalProbe()
        result = probe.start(ScanRequest(512, 256, 2e-6, 0., 0., 1000))
        identifier = result.started_raster_ids[0]
        probe.tick(70_002_500, EpisodeInputs(stop=SafetyStop('stop', probe.authority)))
        prefix = probe.ledger.capture_prefix(identifier)
        self.assertEqual(prefix.counts.pixel_count, 512*256)
        self.assertEqual(prefix.incident_pA_ns[:4], (10000, 10000, 5000, 0))
        self.assertTrue(all(q == 0 for q in prefix.incident_pA_ns[3:]))
        self.assertEqual(prefix.incident_total_pA_ns, 25000)
        self.assertEqual(prefix.outcome, 'CANCELLED')
        self.assertEqual(prefix.counts.read(3, 4), (bytes(16), bytes(16)))
        probe.ledger.dose_snapshot()

    def test_positive_optics_hold_split_current_and_blanked_application_preserve_capture(self):
        probe = RealNumericalProbe()
        identifier = probe.start(ScanRequest(1, 16, 1e-6, 0., 0., 10_000_000)).started_raster_ids[0]
        target = probe.tick(70_500_000, EpisodeInputs(normal=SetOptics('focus', probe.authority,
            EpisodeSettings(20, 4.2e-6, .18, -.12))))
        probe.tick(121_000_000)
        ready = probe.registry.prepare(target.bank_dispatch)
        probe.tick(121_000_000, EpisodeInputs(bank_result=ready))
        probe.tick(124_000_000, EpisodeInputs(stop=SafetyStop('stop', probe.authority)))
        prefix = probe.ledger.capture_prefix(identifier)
        self.assertEqual(len(prefix.prefix.blank_holds), 1)
        self.assertEqual(prefix.prefix.blank_holds[0].end_elapsed_ns-prefix.prefix.blank_holds[0].start_elapsed_ns, 500000)
        self.assertEqual(prefix.incident_total_pA_ns, probe.engine.snapshot().episode_incident_pA_ns)
        self.assertEqual(prefix.settings.current_pA, 20)
        probe.ledger.dose_snapshot()

    def test_duplicate_missing_conflicting_and_foreign_facts_fail_without_new_dose(self):
        probe = RealNumericalProbe()
        probe.start(ScanRequest(2, 1, 1e-6, 0., 0., 1000))
        result = probe.tick(70_001_500)
        before = probe.ledger.dose_snapshot()
        self.assertEqual(probe.ledger.ingest(result.facts).status, 'COMMITTED')
        future = replace(result.facts[-1], ordinal=probe.ledger.last+2, predecessor=probe.ledger.last+1)
        self.assertEqual(probe.ledger.ingest((future,)).status, 'BLOCKED')
        self.assertEqual(probe.ledger.dose_snapshot(), before)
        conflicting = replace(result.facts[-1], episode_namespace='foreign')
        self.assertEqual(probe.ledger.ingest((conflicting,)).status, 'POISONED')
        self.assertEqual(probe.ledger.dose_snapshot(), before)

    def test_resolver_rejects_rebound_handle_before_response_or_count(self):
        probe = RealNumericalProbe()
        result = probe.start(ScanRequest(2, 1, 1e-6, 0., 0., 1000))
        handle = next(f for f in result.facts if f.kind == 'RASTER_START').body[7]
        with self.assertRaises(ValueError):
            probe.registry.resolve(replace(handle, descriptor_digest='0'*64))
        with self.assertRaises(ValueError):
            probe.registry.resolve(replace(handle, source_binding_digest='0'*64))


if __name__ == '__main__':
    unittest.main()
