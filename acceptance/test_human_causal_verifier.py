"""Independent admission/physics predicates,corrupt certificates,and real tapes.

Opaque READY helpers below are explicitly scalar scheduling fixtures only.
Actual saved OS-process and native1024 tapes are a separate genuine criterion.
"""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import unittest

from engine import human_episode_types as t
from engine.episode_credits import EpisodeCapacity
from engine.human_verified_episode import GroundedEpisode
from runtime.human_realtime_records import TickBegin, TickEnd
from runtime.human_realtime_codec import decode_cell
from runtime.human_causal_verifier import HumanCausalVerifier

ROOT = Path(__file__).resolve().parents[1]
SCIENCE = t.ScienceIdentity('generic-fixture', 'a'*64, 'b'*64, 'VECTOR', 'c'*64, 'count-fixture')
CAP = EpisodeCapacity(4096, 256, 128, 4096, 1024, 4096)
INITIAL = t.EpisodeSettings(100, 1.2e-6, .18, -.12)


class Probe:
    def __init__(self, capacity=CAP, initial=INITIAL, expiry=10**12, ack=True):
        self.owner = GroundedEpisode(SCIENCE, initial, episode_namespace='fixture', capacity=capacity)
        self.verifier = HumanCausalVerifier(SCIENCE, initial, episode_namespace='fixture', capacity=capacity)
        self.services = []; self.ack = ack; self.now = 0
        self.tick(0, t.EpisodeInputs(authority=t.GrantAuthority('grant', 'human', expiry)))
        self.authority = self.owner.snapshot().lease.authority

    def tick(self, at, inputs=t.EpisodeInputs()):
        if self.ack:
            inputs = replace(inputs, verified_ack=t.VerifiedAcknowledgement('fixture', self.verifier.cut.last_ordinal if self.verifier.cut else 0))
        result = self.owner.tick(at, inputs); self.now = at
        begin = TickBegin(len(self.services)+1, at, inputs)
        end = TickEnd(begin.tick_id, result.state, result.bank_dispatch, result.started_raster_ids, result.ended_raster_ids)
        self.verifier.verify(begin, result.facts, end)
        self.services.append((begin, result.facts, end))
        return result

    def ready(self, ticket):
        return t.BankReady(ticket, t.ScalarBankHandle('scalar-'+ticket.job_id, 1, 'd'*64,
            SCIENCE.solver_source_digest, ticket.configuration.geometry, ticket.settings))

    def start(self, mode='SINGLE', request=None, op='scan', at=0):
        request = request or t.ScanRequest(64, 64, 2e-6, 0., 0., 1_000_000)
        submitted = self.tick(at, t.EpisodeInputs(normal=t.StartCapture(op, self.authority, mode, request, self.owner.stop_generation)))
        if submitted.bank_dispatch is not None:
            self.tick(at+1, t.EpisodeInputs(bank_result=self.ready(submitted.bank_dispatch)))
        return self.tick(at+50_000_000)


def replay(services, capacity=CAP, initial=INITIAL, science=SCIENCE, namespace='fixture'):
    verifier = HumanCausalVerifier(science, initial, episode_namespace=namespace, capacity=capacity)
    for begin, facts, end in services: verifier.verify(begin, facts, end)
    return verifier


def services_from_cells(path):
    raw = path.read_bytes(); nonce = raw[16:32]
    services = []; begin = None; facts = []
    for index in range(len(raw)//4096):
        value = decode_cell(raw[index*4096:(index+1)*4096], nonce, index+1)
        if type(value) is TickBegin: begin = value; facts = []
        elif type(value) is TickEnd:
            services.append((begin, tuple(facts), value)); begin = None
        else: facts.append(value)
    if begin is not None: raise AssertionError('Incomplete actual wire witness')
    return services


class CausalVerifierTests(unittest.TestCase):
    def test_scalar_certificate_has_no_owner_or_scientific_imports(self):
        import ast
        tree = ast.parse((ROOT/'runtime/human_causal_verifier.py').read_bytes())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = [node.module] if isinstance(node, ast.ImportFrom) else [item.name for item in node.names]
                for module in modules:
                    self.assertFalse(any(word in (module or '') for word in ('grounded_episode', 'numpy', 'probe', 'response', 'exposure_ledger')))
            if isinstance(node, ast.Name): self.assertNotIn(node.id, ('GroundedEpisode', 'EpisodeCredits', 'eval', 'exec'))

    def test_every_snapshot_field_and_lifecycle_is_checked(self):
        p = Probe(); p.start(); p.tick(71_000_000)
        begin, facts, end = p.services[-1]
        changes = {'now_ns': begin.at_ns+1, 'revision': end.state.revision+1,
            'phase': 'STOPPED', 'beam_blank': True, 'settings': t.EpisodeSettings(99),
            'requested_settings': t.EpisodeSettings(10), 'lease': None,
            'stop_generation': 1, 'session_generation': 2, 'settings_generation': 1,
            'geometry_generation': 2, 'applied_generation': 1, 'current_configuration': None,
            'requested_configuration': None, 'causal_raster_id': 'forged-raster', 'live_view_id': 'forged-view',
            'sweep_index': 1, 'stage_x_m': 1e-6, 'stage_y_m': 1e-6, 'stage_z_m': 1e-6,
            'last_ordinal': end.state.last_ordinal+1, 'physical_sequence': end.state.physical_sequence+1,
            'verified_ordinal': 0, 'capture_incident_pA_ns': end.state.capture_incident_pA_ns+1,
            'episode_incident_pA_ns': end.state.episode_incident_pA_ns+1, 'interlock_reason': 'forged'}
        for field, value in changes.items():
            with self.subTest(field=field):
                verifier = replay(p.services[:-1])
                old = verifier.cut
                with self.assertRaises(ValueError): verifier.verify(begin, facts, replace(end, state=replace(end.state, **{field: value})))
                self.assertIs(verifier.cut, old)
                with self.assertRaises(ValueError): verifier.verify(begin, facts, end)
        verifier = replay(p.services[:-1])
        with self.assertRaises(ValueError): verifier.verify(begin, facts, replace(end, started=('forged-raster',)))

    def test_prefix_charge_time_handle_and_predecessor_mutations_rejected(self):
        p = Probe(); p.start(); p.tick(72_000_000)
        begin, facts, end = p.services[-1]
        original = next(f for f in facts if f.kind == 'PREFIX')
        for field in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9):
            body = list(original.body)
            if field in (0, 7): body[field] = 'forged'
            elif field == 5: body[field] = not body[field]
            elif field == 6: body[field] = replace(body[field], descriptor_digest='e'*64)
            else: body[field] += 1
            mutant = replace(original, body=tuple(body))
            forged = tuple(mutant if f is original else f for f in facts)
            with self.subTest(field=field):
                with self.assertRaises(ValueError): replay(p.services[:-1]).verify(begin, forged, end)
        with self.assertRaises(ValueError): replay(p.services[:-1]).verify(begin, (), end)
        with self.assertRaises(ValueError): replay(p.services[:-1]).verify(begin, facts+facts, end)
        with self.assertRaises(ValueError): replay(p.services[:-1]).verify(replace(begin, tick_id=begin.tick_id+1), facts, end)

    def test_complete_frame_exact_charge_and_no_early_exposure(self):
        p = Probe(); p.start(request=t.ScanRequest(3, 2, 1e-6, 0., 0., 20000))
        before = p.tick(69_999_999)
        self.assertEqual(before.state.episode_incident_pA_ns, 0)
        p.tick(80_320_000)
        self.assertEqual(p.verifier.cut.state.phase, 'STOPPED')
        self.assertEqual(p.verifier.cut.state.episode_incident_pA_ns, 3*2*20000*100)

    def test_stop_expiry_duplicate_and_stale_start_fences(self):
        p = Probe(expiry=100_000_000); p.start(mode='LIVE')
        stop = p.tick(100_000_000, t.EpisodeInputs(stop=t.SafetyStop('stop', p.authority)))
        self.assertEqual(stop.state.stop_generation, 1)
        self.assertTrue(stop.state.beam_blank)
        self.assertEqual(next(f.body[-1] for f in stop.facts if f.kind == 'RASTER_END'), 'STOP')
        p.tick(101_000_000, t.EpisodeInputs(authority=t.GrantAuthority('grant2', 'human', 10**12)))
        new = p.owner.snapshot().lease.authority
        self.assertEqual(new.epoch, 2)
        stale = p.tick(102_000_000, t.EpisodeInputs(normal=t.StartCapture('stale', new, 'LIVE', t.ScanRequest(1, 1, 1e-6, 0., 0., 1000), 0)))
        self.assertEqual(next(f.body[2] for f in stale.facts if f.kind == 'DISPOSITION'), 'STOPPED_BEFORE_ADMISSION')
        denied = p.tick(103_000_000, t.EpisodeInputs(stop=t.SafetyStop('other', p.authority)))
        self.assertEqual(next(f.body[2] for f in denied.facts if f.kind == 'DISPOSITION'), 'UNAUTHORIZED')

    def test_same_tick_stop_blocks_ready_and_normal_start(self):
        p = Probe()
        submitted = p.tick(0, t.EpisodeInputs(normal=t.StartCapture('pending', p.authority, 'LIVE', t.ScanRequest(2, 2, 1e-6, 0., 0., 1000), 0)))
        result = p.tick(50_000_000, t.EpisodeInputs(stop=t.SafetyStop('stop', p.authority),
            normal=t.StartCapture('new', p.authority, 'SINGLE', t.ScanRequest(2, 2, 1e-6, 0., 0., 1000), 0),
            bank_result=p.ready(submitted.bank_dispatch)))
        self.assertEqual(result.started_raster_ids, ())
        self.assertEqual(result.state.episode_incident_pA_ns, 0)
        self.assertEqual(next(f.body[2] for f in result.facts if f.kind == 'DISPOSITION' and f.body[0] == 'new'), 'STOP')

    def test_unauthorized_commands_are_inert_while_physics_continues(self):
        p = Probe(); p.start(mode='LIVE')
        other = t.AuthorityRef('other', 1)
        for i, command in enumerate((t.MoveStageXYZ('move', other, 1e-6, 0., 2e-6, 0),
                t.SetOptics('lens', other, t.EpisodeSettings(50)), t.RevokeAuthority('revoke', other))):
            inputs = t.EpisodeInputs(authority=command) if type(command) is t.RevokeAuthority else t.EpisodeInputs(normal=command)
            result = p.tick(71_000_000+i*1_000_000, inputs)
            self.assertEqual(result.state.phase, 'CAPTURING')
            self.assertEqual(result.state.settings, INITIAL)
            self.assertEqual(result.state.stage_z_m, 0.)
            self.assertEqual(next(f.body[2] for f in result.facts if f.kind == 'DISPOSITION'), 'UNAUTHORIZED')

    def test_lens_hold_application_exact_current_and_readiness_binding(self):
        p = Probe(); p.start(mode='LIVE')
        changed = t.EpisodeSettings(50, 3e-6, .4, -.3)
        submitted = p.tick(71_000_000, t.EpisodeInputs(normal=t.SetOptics('lens', p.authority, changed)))
        held = p.tick(122_000_000)
        self.assertTrue(held.state.beam_blank)
        self.assertEqual(next(f.event_at_ns for f in held.facts if f.kind == 'HOLD_START'), 121_000_000)
        total = held.state.episode_incident_pA_ns
        p.tick(160_000_000)
        self.assertEqual(p.owner.total, total)
        applied = p.tick(170_000_000, t.EpisodeInputs(bank_result=p.ready(submitted.bank_dispatch)))
        self.assertEqual(applied.state.settings, changed)
        self.assertEqual(applied.state.applied_generation, 1)
        self.assertEqual(p.owner.total, total)
        p.tick(171_000_000)
        self.assertEqual(p.owner.total-total, 1_000_000*50)

    def test_target_supersession_no_change_releases_positive_hold(self):
        p = Probe(); p.start(mode='LIVE')
        submitted = p.tick(71_000_000, t.EpisodeInputs(normal=t.SetOptics('first', p.authority, t.EpisodeSettings(50))))
        p.tick(122_000_000)
        result = p.tick(130_000_000, t.EpisodeInputs(normal=t.SetOptics('equal', p.authority, INITIAL),
            bank_result=p.ready(submitted.bank_dispatch)))
        self.assertIsNone(result.state.requested_settings)
        self.assertFalse(result.state.beam_blank)
        self.assertEqual(next(f.body[1] for f in result.facts if f.kind == 'DISPOSITION'), 'SATISFIED_NO_CHANGE')

    def test_live_geometry_binds_next_sweep_and_freeze_source(self):
        p = Probe(); p.start(mode='LIVE', request=t.ScanRequest(2, 2, 2e-6, 0., 0., 20000))
        update = p.tick(71_000_000, t.EpisodeInputs(normal=t.ConfigureLive('zoom', p.authority,
            t.ScanRequest(3, 2, 1e-6, .2e-6, -.1e-6, 20000), 0)))
        self.assertEqual(update.state.current_configuration.geometry.width_px, 2)
        self.assertEqual(update.state.requested_configuration.geometry.width_px, 3)
        ended = p.tick(80_180_000)
        self.assertIsNone(ended.state.current_configuration)
        self.assertIsNotNone(ended.bank_dispatch)
        begun = p.tick(81_000_000, t.EpisodeInputs(bank_result=p.ready(ended.bank_dispatch)))
        self.assertEqual(begun.state.current_configuration.geometry.width_px, 3)
        view = begun.state.live_view_id
        denied = p.tick(82_000_000, t.EpisodeInputs(normal=t.FreezeLive('bad', p.authority, 'wrong', 0)))
        self.assertEqual(next(f.body[2] for f in denied.facts if f.kind == 'DISPOSITION'), 'STALE_SOURCE')
        p.tick(83_000_000, t.EpisodeInputs(normal=t.FreezeLive('freeze', p.authority, view, 0)))
        done = p.tick(111_320_000)
        self.assertEqual(done.state.phase, 'STOPPED')
        self.assertIsNone(done.state.live_view_id)

    def test_xyz_trajectory_expiry_and_subsequent_capture_pose(self):
        p = Probe()
        result = p.tick(0, t.EpisodeInputs(normal=t.MoveStageXYZ('move', p.authority, .0001, -.0001, 10e-6, 0)))
        start = next(f for f in result.facts if f.kind == 'MOTION_XYZ_START')
        self.assertEqual(start.body[-2:], (500_000_000, 580_000_000))
        at = p.tick(250_000_000)
        self.assertEqual((at.state.stage_x_m, at.state.stage_y_m, at.state.stage_z_m), (.00005, -.00005, 5e-6))
        p.tick(580_000_000)
        begun = p.start(at=600_000_000, request=t.ScanRequest(2, 2, 1e-6, 0., 0., 1000))
        self.assertEqual(begun.state.current_configuration.geometry.stage_z_m, 10e-6)
        p = Probe(expiry=100_000_000)
        p.tick(0, t.EpisodeInputs(normal=t.MoveStageXYZ('move', p.authority, 0., 0., 10e-6, 0)))
        expired = p.tick(900_000_000)
        self.assertAlmostEqual(expired.state.stage_z_m, 2e-6, delta=1e-21)
        self.assertEqual(next(f.event_at_ns for f in expired.facts if f.kind == 'MOTION_XYZ_END'), 100_000_000)

    def test_xy_motion_is_independently_checked(self):
        p = Probe(); p.tick(0, t.EpisodeInputs(normal=t.MoveStage('move', p.authority, .0001, 0., 0)))
        state = p.tick(50_000_000).state
        self.assertEqual(state.stage_x_m, .00005)
        stopped = p.tick(60_000_000, t.EpisodeInputs(stop=t.SafetyStop('stop', p.authority)))
        self.assertEqual(stopped.state.stage_x_m, .00006)

    def test_focus_z_domain_guard_before_mutation(self):
        p = Probe(initial=t.EpisodeSettings(100, 20e-6))
        denied = p.tick(0, t.EpisodeInputs(normal=t.MoveStageXYZ('unsafe', p.authority, 0., 0., 10e-6, 0)))
        self.assertEqual(denied.state.phase, 'STOPPED')
        self.assertEqual(next(f.body[2] for f in denied.facts if f.kind == 'DISPOSITION'), 'SOURCE_DOMAIN')
        p.tick(0, t.EpisodeInputs(normal=t.MoveStageXYZ('safe', p.authority, 0., 0., -10e-6, 0)))
        denied = p.tick(1, t.EpisodeInputs(normal=t.SetOptics('unsafe-lens', p.authority, t.EpisodeSettings(100, -20e-6))))
        self.assertIsNone(denied.state.requested_settings)

    def test_dispatch_field_rebinding_is_rejected(self):
        p = Probe()
        p.tick(0, t.EpisodeInputs(normal=t.StartCapture('scan', p.authority, 'LIVE', t.ScanRequest(2, 2, 1e-6, 0., 0., 1000), 0)))
        begin, facts, end = p.services[-1]
        for field, value in (('request_id', 'forged'), ('session_generation', 2), ('settings_generation', 1),
                ('geometry_generation', 2), ('applied_generation', 1), ('custodian_generation', 2),
                ('not_before_ns', 49_000_000), ('configuration', t.ScanConfiguration(t.EpisodeGeometry(3, 2, 1e-6), 1000))):
            with self.subTest(field=field):
                with self.assertRaises(ValueError): replay(p.services[:-1]).verify(begin, facts,
                    replace(end, bank_dispatch=replace(end.bank_dispatch, **{field: value})))

    def test_foreign_bank_source_cannot_become_verified_physical_state(self):
        p = Probe()
        result = p.tick(0, t.EpisodeInputs(normal=t.StartCapture('scan', p.authority, 'SINGLE', t.ScanRequest(2, 2, 1e-6, 0., 0., 1000), 0)))
        ready = p.ready(result.bank_dispatch)
        foreign = replace(ready, handle=replace(ready.handle, source_binding_digest='e'*64))
        with self.assertRaises(ValueError): p.tick(50_000_000, t.EpisodeInputs(bank_result=foreign))
        self.assertIsNotNone(p.verifier.poison)

    def test_normal_and_mixed_capacity_emergency_batches_are_verified(self):
        capacity = EpisodeCapacity(12, 7, 1, 32, 16, 65536)
        p = Probe(capacity=capacity, ack=False); p.start()
        for at in range(71_000_000, 78_000_000, 1_000_000): result = p.tick(at)
        self.assertEqual(result.state.phase, 'INTERLOCKED')
        self.assertEqual(result.state.interlock_reason, 'NUMERIC_BACKLOG_CAPACITY')
        self.assertEqual(result.state.verified_ordinal, 0)
        p = Probe(); p.start()
        result = p.tick(71_000_000, t.EpisodeInputs(stop=t.SafetyStop('stop', p.authority),
            normal=t.MoveStageXYZ('move', p.authority, 0., 0., 1e-6, 0),
            fault=t.EpisodeFault('fixture', 'SPOOL_CAPACITY')))
        self.assertEqual(result.state.phase, 'INTERLOCKED')
        self.assertEqual(next(f.body[-1] for f in result.facts if f.kind == 'RASTER_END'), 'STOP')

    def test_authorized_renew_revoke_and_new_epoch_are_verified(self):
        p = Probe(); p.start(mode='LIVE')
        renewed = p.tick(71_000_000, t.EpisodeInputs(authority=t.RenewAuthority('renew', p.authority, 500_000_000)))
        self.assertEqual(renewed.state.lease.expires_ns, 500_000_000)
        revoked = p.tick(72_000_000, t.EpisodeInputs(authority=t.RevokeAuthority('revoke', p.authority)))
        self.assertIsNone(revoked.state.lease)
        self.assertTrue(revoked.state.beam_blank)
        self.assertEqual(next(f.body[-1] for f in revoked.facts if f.kind == 'RASTER_END'), 'REVOKED')
        new = p.tick(73_000_000, t.EpisodeInputs(authority=t.GrantAuthority('new', 'other', 10**12)))
        self.assertEqual((new.state.lease.authority.holder_id, new.state.lease.authority.epoch), ('other', 2))

    def test_xyz_motion_body_and_pose_certificate_corruption_rejected(self):
        p = Probe()
        p.tick(0, t.EpisodeInputs(normal=t.MoveStageXYZ('move', p.authority, .0001, 0., 10e-6, 0)))
        p.tick(250_000_000)
        begin, facts, end = p.services[-1]
        advance = next(f for f in facts if f.kind == 'MOTION_XYZ_ADVANCE')
        for field in range(len(advance.body)):
            body = list(advance.body)
            body[field] = 'wrong' if type(body[field]) is str else body[field]+1e-9
            mutant = tuple(replace(f, body=tuple(body)) if f is advance else f for f in facts)
            with self.assertRaises(ValueError): replay(p.services[:-1]).verify(begin, mutant, end)

    def test_failed_authority_admission_cannot_cancel_active_capture(self):
        p = Probe(capacity=EpisodeCapacity(4096, 256, 128, 4096, 3, 4096))
        p.start(mode='LIVE')  # grant and start fill ordinary admission history
        rejected = p.tick(71_000_000, t.EpisodeInputs(authority=t.RevokeAuthority('over-capacity', p.authority)))
        self.assertEqual(next(f.body[2] for f in rejected.facts if f.kind == 'DISPOSITION'), 'OPERATION_CAPACITY')
        self.assertEqual(rejected.state.phase, 'CAPTURING')
        self.assertEqual(rejected.ended_raster_ids, ())

    def test_future_ack_cannot_recycle_unverified_credits(self):
        p = Probe(); begin = TickBegin(2, 1, t.EpisodeInputs(verified_ack=t.VerifiedAcknowledgement('fixture', p.owner.credits.ordinal+1)))
        end = TickEnd(2, p.owner.snapshot(), None, (), ())
        with self.assertRaises(ValueError): p.verifier.verify(begin, (), end)

    def test_every_control_kind_requires_the_exact_admitted_input_effect(self):
        probes = []
        p = Probe(); probes.append(p.services[:])  # LEASE,DISPOSITION
        p.start(); probes.append(p.services[:])   # GEOMETRY
        first = p.tick(71_000_000, t.EpisodeInputs(normal=t.SetOptics('target', p.authority, t.EpisodeSettings(50))))
        p.tick(72_000_000, t.EpisodeInputs(normal=t.SetOptics('new-target', p.authority, t.EpisodeSettings(60))))
        probes.append(p.services[:])  # TARGET_RETIRED
        p.tick(73_000_000, t.EpisodeInputs(stop=t.SafetyStop('stop', p.authority)))
        probes.append(p.services[:])  # SESSION_ENDED
        p.tick(74_000_000, t.EpisodeInputs(fault=t.EpisodeFault('fixture', 'PROCESS_FAILURE')))
        probes.append(p.services[:])  # INTERLOCK
        checked = set()
        for services in probes:
            for index, (begin, facts, end) in enumerate(services):
                for fact in facts:
                    if fact.lane != 'C' or fact.kind in checked: continue
                    body = list(fact.body)
                    if fact.kind == 'LEASE': body[1] = 'WRONG_REASON'
                    else: body[0] = 'WRONG_ID_OR_REASON'
                    mutant = tuple(replace(item, body=tuple(body)) if item is fact else item for item in facts)
                    with self.assertRaises(ValueError): replay(services[:index]).verify(begin, mutant, end)
                    checked.add(fact.kind)
        self.assertEqual(checked, {'LEASE','DISPOSITION','GEOMETRY','TARGET_RETIRED','SESSION_ENDED','INTERLOCK'})

    def test_ack_history_can_advance_without_exhausting_live_credits(self):
        p = Probe(capacity=EpisodeCapacity(32, 14, 2, 64, 256, 4096))
        p.start(mode='LIVE', request=t.ScanRequest(1, 1, 1e-6, 0., 0., 1000))
        for index in range(1000): p.tick(51_000_000+index*1_000_000)
        self.assertIsNone(p.owner.interlock)
        self.assertGreater(p.verifier.cut.last_ordinal, 1000)
        self.assertLess(len(p.verifier.budget.events), 10)

    def test_original_scalar_assertions_hold_with_certification_on_every_tick(self):
        # Reuse protected assertions without editing their file. Only the two
        # namespace imports and the source-inspection path select this variant.
        source = (ROOT/'acceptance/test_grounded_episode_scalar.py').read_text()
        adapted = source.replace('engine.grounded_episode', 'engine.human_verified_episode').replace(
            'engine.episode_types', 'engine.human_episode_types').replace(
            'engine/grounded_episode.py', 'engine/human_verified_episode.py')
        namespace = {'__name__':'causal_scalar_conformance','__file__':str(ROOT/'acceptance/test_grounded_episode_scalar.py')}
        exec(compile(adapted, namespace['__file__'], 'exec'), namespace)
        base = namespace['GroundedEpisode']
        class CertifiedOwner(base):
            def __init__(self, science, settings, **kwargs):
                super().__init__(science, settings, **kwargs)
                self._checker = HumanCausalVerifier(science, settings, **kwargs)
                self._certificate_tick = 0
            def tick(self, at, inputs=t.EpisodeInputs()):
                result = super().tick(at, inputs)
                self._certificate_tick += 1
                begin = TickBegin(self._certificate_tick, at, inputs)
                end = TickEnd(begin.tick_id, result.state, result.bank_dispatch, result.started_raster_ids, result.ended_raster_ids)
                self._checker.verify(begin, result.facts, end)
                return result
        namespace['GroundedEpisode'] = CertifiedOwner
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(namespace['ScalarOwnerTests'])
        result = unittest.TestResult(); suite.run(result)
        self.assertEqual(result.testsRun, 22)
        self.assertFalse(result.skipped)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.failures, [])

    @unittest.skip('Private historical process tapes are not distributed; use scripts/qualify_release.py for a fresh actual-runtime gate')
    def test_actual_windows_linux_and_full_native1024_saved_process_tapes(self):
        checked = 0
        for platform in ('win32', 'linux'):
            folder = ROOT/'evidence/frontier/human-realtime-process-cpu04'/platform/'episodes'
            for witness in sorted(folder.rglob('witness.json')):
                saved = json.loads(witness.read_bytes())
                services = services_from_cells(witness.parent/'owner.cells')
                tickets = [end.bank_dispatch for _, _, end in services if end.bank_dispatch is not None]
                # Stage-only traces contain/use no science descriptor; the
                # placeholder is irrelevant to their verified physical laws.
                science = tickets[0].science if tickets else SCIENCE
                capacity = EpisodeCapacity(12, 7, 1, 32, 16, 65536) if 'no_unverified_ack' in witness.parent.name else EpisodeCapacity(2048, 256, 128, 2048, 1024, 65536)
                namespace = next(f.episode_namespace for _, facts, _ in services for f in facts)
                verifier = replay(services, capacity, INITIAL, science, namespace)
                self.assertEqual(verifier.cut.last_ordinal, saved['state']['last_ordinal'])
                self.assertEqual(verifier.cut.state.episode_incident_pA_ns, saved['state']['episode_incident_pA_ns'])
                checked += 1
        self.assertEqual(checked, 18)
        job = ROOT.parents[1]/'runs/human-realtime-pattern1024-20261014-02'
        services = services_from_cells(job/'owner.cells')
        science = next(end.bank_dispatch.science for _, _, end in services if end.bank_dispatch is not None)
        namespace = next(f.episode_namespace for _, facts, _ in services for f in facts)
        verifier = replay(services, EpisodeCapacity(32768, 1024, 1024, 32768, 8192, 8192), INITIAL, science, namespace)
        self.assertEqual(verifier.cut.state.episode_incident_pA_ns, 1024*1024*20000*100)
        self.assertEqual(verifier.cut.state.phase, 'STOPPED')


if __name__ == '__main__': unittest.main()
