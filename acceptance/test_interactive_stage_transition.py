"""Independent integer/certificate gates;scalar banks are NOT image evidence."""
from dataclasses import replace
import random
import unittest
from engine import human_episode_types as t
from engine.episode_credits import EpisodeCapacity
from engine.interactive_stage_episode import GroundedEpisode
from runtime.interactive_stage_verifier import PacedCausalVerifier
from runtime.human_live_records import LiveTickBegin
from runtime.human_realtime_records import TickEnd
from acceptance.test_interactive_grid_transition import Probe as GridProbe,SCIENCE,CAP,INITIAL,NEW


class Probe(GridProbe):
    def __init__(self,expiry=10**12,capacity=CAP):
        self.owner=GroundedEpisode(SCIENCE,INITIAL,episode_namespace='fixture',capacity=capacity)
        self.verifier=PacedCausalVerifier(SCIENCE,INITIAL,episode_namespace='fixture',capacity=capacity)
        self.events=[]
        self.tick(0,t.EpisodeInputs(authority=t.GrantAuthority('grant','human',expiry)))
        self.authority=self.owner.snapshot().lease.authority

    def tick(self,*args,**kwargs):
        result=super().tick(*args,**kwargs)
        if len(result.facts)+2>34:raise AssertionError('frozen per-tick34 fact envelope including witnesses exceeded')
        return result

    def move(self,at=120_000_000,op='stage',x=2e-6,y=0.,z=.5e-6,authority=None,generation=0):
        return self.tick(at,t.EpisodeInputs(normal=t.MoveStageXYZ(op,authority or self.authority,x,y,z,generation)))


class InteractiveStageGates(unittest.TestCase):
    def test_same_raster_pauses_exposure_then_binds_actual_settled_XYZ(self):
        p=Probe();start=p.start();move=p.move()
        self.assertEqual(move.state.causal_raster_id,start.state.causal_raster_id)
        self.assertEqual(move.state.episode_incident_pA_ns,4_970_000_000)
        self.assertTrue(move.state.beam_blank);self.assertEqual(move.state.phase,'MOVING')
        ready=p.tick(121_000_000,t.EpisodeInputs(bank_result=p.ready(move.bank_dispatch)))
        self.assertFalse(any(f.kind=='SETTINGS_APPLIED' for f in ready.facts))
        self.assertEqual(ready.state.episode_incident_pA_ns,move.state.episode_incident_pA_ns)
        before=p.tick(224_999_999)
        self.assertTrue(before.state.beam_blank)
        settled=p.tick(225_000_000)
        self.assertEqual(settled.state.causal_raster_id,start.state.causal_raster_id)
        self.assertEqual(settled.state.episode_incident_pA_ns,move.state.episode_incident_pA_ns)
        applied=next(f for f in settled.facts if f.kind=='SETTINGS_APPLIED')
        self.assertEqual(applied.body[1],applied.body[2])
        self.assertEqual((applied.body[4].geometry.stage_x_m,applied.body[4].geometry.stage_z_m),(2e-6,.5e-6))
        after=p.tick(245_000_000)
        self.assertEqual(after.state.causal_raster_id,start.state.causal_raster_id)
        self.assertGreater(after.state.episode_incident_pA_ns,settled.state.episode_incident_pA_ns)
        prefix=next(f for f in after.facts if f.kind=='PREFIX')
        self.assertEqual(prefix.body[6].geometry.stage_x_m,2e-6)

    def test_delayed_source_keeps_same_raster_blank_after_settlement(self):
        p=Probe();start=p.start();move=p.move();held=p.tick(500_000_000)
        self.assertEqual(held.state.causal_raster_id,start.state.causal_raster_id)
        self.assertTrue(held.state.beam_blank)
        self.assertEqual(held.state.episode_incident_pA_ns,move.state.episode_incident_pA_ns)
        applied=p.tick(600_000_000,t.EpisodeInputs(bank_result=p.ready(move.bank_dispatch)))
        self.assertIsNone(applied.state.interlock_reason)
        self.assertEqual(applied.state.causal_raster_id,start.state.causal_raster_id)
        self.assertEqual(applied.state.episode_incident_pA_ns,move.state.episode_incident_pA_ns)

    def test_Stop_mid_motion_closes_both_terminals_and_retires_unreached_source(self):
        p=Probe();p.start();move=p.move()
        stopped=p.tick(130_000_000,t.EpisodeInputs(stop=t.SafetyStop('stop',p.authority),bank_result=p.ready(move.bank_dispatch)))
        self.assertEqual(stopped.state.phase,'STOPPED');self.assertTrue(stopped.state.beam_blank)
        self.assertAlmostEqual(stopped.state.stage_x_m,.8e-6,places=18)
        self.assertAlmostEqual(stopped.state.stage_z_m,.2e-6,places=18)
        self.assertEqual(sum(f.kind=='SESSION_ENDED' for f in stopped.facts),2)
        self.assertFalse(any(f.kind=='SETTINGS_APPLIED' for f in stopped.facts))
        self.assertIsNone(p.owner.pending)
        late=p.tick(300_000_000)
        self.assertFalse(late.started_raster_ids);self.assertIsNone(late.state.requested_settings)

    def test_expiry_ends_both_motion_and_capture_at_exact_deadline(self):
        p=Probe(expiry=130_000_000);p.start();move=p.move()
        expired=p.tick(400_000_000,t.EpisodeInputs(bank_result=p.ready(move.bank_dispatch)))
        self.assertIsNone(expired.state.lease);self.assertEqual(expired.state.phase,'STOPPED')
        ends=[f for f in expired.facts if f.kind in ('RASTER_END','MOTION_XYZ_END')]
        self.assertEqual(len(ends),2)
        self.assertTrue(all(f.event_at_ns==130_000_000 and f.body[-1]=='EXPIRED' for f in ends))
        self.assertEqual(expired.state.episode_incident_pA_ns,move.state.episode_incident_pA_ns)

    def test_revoke_while_moving_never_applies_prepared_target(self):
        p=Probe();p.start();move=p.move()
        result=p.tick(130_000_000,t.EpisodeInputs(authority=t.RevokeAuthority('revoke',p.authority),bank_result=p.ready(move.bank_dispatch)))
        self.assertIsNone(result.state.lease);self.assertIsNone(result.state.requested_settings)
        self.assertFalse(any(f.kind=='SETTINGS_APPLIED' for f in result.facts))
        self.assertEqual(sum(f.kind=='SESSION_ENDED' for f in result.facts),2)

    def test_numeric_fault_closes_concurrent_terminals_in_original_emergency_budget(self):
        p=Probe();p.start();p.move()
        result=p.tick(130_000_000,t.EpisodeInputs(fault=t.EpisodeFault('fixture','CAUSAL_FAILURE')))
        self.assertEqual(result.state.interlock_reason,'CAUSAL_FAILURE')
        self.assertTrue(result.state.beam_blank);self.assertIsNone(result.state.lease)
        self.assertLessEqual(sum(f.lane=='C' and f.emergency for f in result.facts),8)

    def test_pending_lens_survives_stage_and_stale_old_pose_reply_is_fenced(self):
        p=Probe();p.start();desired=t.EpisodeSettings(50,3e-6,.2,-.3)
        lens=p.tick(80_000_000,t.EpisodeInputs(normal=t.SetOptics('lens',p.authority,desired)))
        p.move();stale=p.tick(121_000_000,t.EpisodeInputs(bank_result=p.ready(lens.bank_dispatch)))
        self.assertEqual(stale.state.settings,INITIAL)
        self.assertEqual(stale.bank_dispatch.request_id,'lens')
        self.assertEqual(stale.bank_dispatch.configuration.geometry.stage_z_m,.5e-6)
        self.assertEqual(stale.bank_dispatch.settings,desired)
        result=p.tick(225_000_000,t.EpisodeInputs(bank_result=p.ready(stale.bank_dispatch)))
        self.assertEqual(result.state.settings,desired);self.assertIsNone(result.state.interlock_reason)

    def test_equal_optics_during_motion_cannot_unblank_raster(self):
        p=Probe();p.start();move=p.move()
        same=p.tick(130_000_000,t.EpisodeInputs(normal=t.SetOptics('same',p.authority,INITIAL)))
        self.assertTrue(same.state.beam_blank)
        self.assertEqual(same.state.episode_incident_pA_ns,move.state.episode_incident_pA_ns)
        still=p.tick(140_000_000,t.EpisodeInputs(bank_result=p.ready(move.bank_dispatch)))
        self.assertTrue(still.state.beam_blank)
        self.assertEqual(still.state.episode_incident_pA_ns,move.state.episode_incident_pA_ns)

    def test_configure_during_motion_ends_partial_and_rebinds_new_grid_at_destination(self):
        p=Probe();old=p.start();move=p.move();changed=p.configure(at=130_000_000)
        self.assertEqual(next(f.body[-1] for f in changed.facts if f.kind=='RASTER_END'),'GEOMETRY_CHANGED')
        self.assertIsNone(changed.state.causal_raster_id)
        stale=p.tick(131_000_000,t.EpisodeInputs(bank_result=p.ready(move.bank_dispatch)))
        self.assertEqual(stale.bank_dispatch.configuration.geometry.width_px,8)
        self.assertEqual(stale.bank_dispatch.configuration.geometry.stage_x_m,2e-6)
        self.assertEqual(stale.state.live_view_id,old.state.live_view_id)

    def test_unauthorised_or_stale_generation_move_does_not_hold_exposure(self):
        for authority,generation,reason in ((t.AuthorityRef('foreign',1),0,'UNAUTHORIZED'),(None,9,'STOPPED_BEFORE_ADMISSION')):
            p=Probe();p.start();result=p.move(authority=authority,generation=generation)
            self.assertEqual(next(f.body[2] for f in result.facts if f.kind=='DISPOSITION'),reason)
            self.assertFalse(any(f.kind in ('MOTION_XYZ_START','HOLD_START') for f in result.facts))
            advanced=p.tick(130_000_000)
            self.assertGreater(advanced.state.episode_incident_pA_ns,result.state.episode_incident_pA_ns)

    def test_combined_Z_and_pending_lens_domain_is_checked_before_movement(self):
        p=Probe();p.start()
        p.tick(80_000_000,t.EpisodeInputs(normal=t.SetOptics('lens',p.authority,t.EpisodeSettings(100,24e-6))))
        result=p.move(z=2e-6)
        self.assertEqual(next(f.body[2] for f in result.facts if f.kind=='DISPOSITION'),'SOURCE_DOMAIN')
        self.assertFalse(any(f.kind=='MOTION_XYZ_START' for f in result.facts))

    def test_concurrent_second_terminal_must_be_reserved_or_fail_closed(self):
        capacity=EpisodeCapacity(4096,7,128,4096,1024,4096)
        p=Probe(capacity=capacity);p.start();result=p.move()
        self.assertEqual(result.state.interlock_reason,'NUMERIC_BACKLOG_CAPACITY')
        self.assertFalse(any(f.kind=='MOTION_XYZ_START' for f in result.facts))
        self.assertIsNone(result.state.causal_raster_id);self.assertTrue(result.state.beam_blank)

    def test_corrupt_settled_pose_application_quarantines_independent_certificate(self):
        p=Probe();p.start();move=p.move()
        p.tick(225_000_000,t.EpisodeInputs(bank_result=p.ready(move.bank_dispatch)))
        verifier=PacedCausalVerifier(SCIENCE,INITIAL,episode_namespace='fixture',capacity=CAP)
        for begin,facts,end in p.events[:-1]:verifier.verify(begin,facts,end)
        begin,facts,end=p.events[-1]
        changed=[]
        for f in facts:
            if f.kind=='SETTINGS_APPLIED':
                body=list(f.body);handle=body[4]
                body[4]=replace(handle,geometry=replace(handle.geometry,stage_x_m=3e-6));f=replace(f,body=tuple(body))
            changed.append(f)
        previous=verifier.cut.last_ordinal
        with self.assertRaises(ValueError):verifier.verify(begin,tuple(changed),end)
        self.assertEqual(verifier.cut.last_ordinal,previous);self.assertIsNotNone(verifier.poison)

    def test_seeded_combined_intent_reply_and_terminal_races_preserve_certificate_and_reservations(self):
        rng=random.Random(191026)
        for scenario in range(128):
            with self.subTest(scenario=scenario):
                p=Probe();started=p.start();at=50_000_000;queued=[]
                for step in range(64):
                    at+=rng.randint(1,40_000_000);op='s'+str(scenario)+'-n'+str(step)
                    normal=stop=fault=None
                    choice=rng.randrange(10)
                    if choice<3:
                        normal=t.MoveStageXYZ(op,p.authority,rng.randint(-4,4)*1e-6,rng.randint(-4,4)*1e-6,
                            rng.randint(-4,4)*.5e-6,p.owner.stop_generation)
                    elif choice<6:
                        normal=t.SetOptics(op,p.authority,t.EpisodeSettings(rng.choice((10,100,1000)),
                            rng.choice((0.,1.2e-6,24e-6,-24e-6)),rng.choice((-.4,0.,.4)),rng.choice((-.4,0.,.4))))
                    elif choice<8:normal=t.ConfigureLive(op,p.authority,rng.choice((NEW,t.ScanRequest(16,16,2e-6,0.,0.,1_000_000))),p.owner.stop_generation)
                    elif choice==8:normal=t.StartCapture(op,p.authority,'LIVE',NEW,p.owner.stop_generation)
                    if rng.randrange(30)==0:stop=t.SafetyStop('stop-'+op,p.authority)
                    if step>20 and rng.randrange(120)==0:fault=t.EpisodeFault('fixture','PROCESS_FAILURE')
                    reply=queued.pop(0) if queued and rng.randrange(3)==0 else None
                    result=p.tick(at,t.EpisodeInputs(normal=normal,stop=stop,fault=fault,bank_result=reply))
                    if result.bank_dispatch is not None:queued.append(p.ready(result.bank_dispatch))


if __name__=='__main__':unittest.main()
