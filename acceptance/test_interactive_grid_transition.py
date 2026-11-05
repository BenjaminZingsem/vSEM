"""Independent scalar grid-switch/Stop/dose certificates;not a SEM frame gate."""
from dataclasses import replace
import unittest
from engine import human_episode_types as t
from engine.episode_credits import EpisodeCapacity
from engine.interactive_paced_episode import GroundedEpisode
from runtime.interactive_paced_verifier import PacedCausalVerifier
from runtime.human_live_records import LiveTickBegin,SweepDelivery
from runtime.human_realtime_records import TickEnd

SCIENCE=t.ScienceIdentity('interactive-grid-fixture','a'*64,'b'*64,'VECTOR','c'*64,'count-fixture')
CAP=EpisodeCapacity(4096,256,128,4096,1024,4096)
INITIAL=t.EpisodeSettings(100,1.2e-6,.18,-.12)
OLD=t.ScanRequest(16,16,2e-6,0.,0.,1_000_000)
NEW=t.ScanRequest(8,8,1e-6,0.,0.,1_000_000)


class Probe:
    def __init__(self,expiry=10**12):
        self.owner=GroundedEpisode(SCIENCE,INITIAL,episode_namespace='fixture',capacity=CAP)
        self.verifier=PacedCausalVerifier(SCIENCE,INITIAL,episode_namespace='fixture',capacity=CAP)
        self.events=[]
        self.tick(0,t.EpisodeInputs(authority=t.GrantAuthority('grant','human',expiry)))
        self.authority=self.owner.snapshot().lease.authority

    def tick(self,at,inputs=t.EpisodeInputs(),delivery=None):
        inputs=replace(inputs,verified_ack=t.VerifiedAcknowledgement('fixture',self.verifier.cut.last_ordinal if self.verifier.cut else 0))
        result=self.owner.tick(at,inputs,delivery)
        begin=LiveTickBegin(len(self.events)+1,at,inputs,delivery)
        end=TickEnd(begin.tick_id,result.state,result.bank_dispatch,result.started_raster_ids,result.ended_raster_ids)
        if delivery:self.verifier.register_delivery(delivery)
        self.verifier.verify(begin,result.facts,end)
        self.events.append((begin,result.facts,end))
        return result

    def ready(self,ticket):
        return t.BankReady(ticket,t.ScalarBankHandle('scalar-'+ticket.job_id,1,'d'*64,
            SCIENCE.solver_source_digest,ticket.configuration.geometry,ticket.settings))

    def start(self):
        result=self.tick(0,t.EpisodeInputs(normal=t.StartCapture('scan',self.authority,'LIVE',OLD,0)))
        self.tick(1,t.EpisodeInputs(bank_result=self.ready(result.bank_dispatch)))
        return self.tick(50_000_000)

    def configure(self,at=120_000_000,request=NEW,authority=None):
        return self.tick(at,t.EpisodeInputs(normal=t.ConfigureLive('configure',authority or self.authority,request,0)))


class InteractiveGridGates(unittest.TestCase):
    def test_grid_change_closes_exact_partial_then_new_raster_waits_for_old_delivery(self):
        p=Probe();started=p.start();identifier=started.state.causal_raster_id
        changed=p.configure();end=next(f for f in changed.facts if f.kind=='RASTER_END')
        self.assertEqual(end.body,(identifier,70_000_000,70_000_000,4_970_000_000,'GEOMETRY_CHANGED'))
        self.assertIsNone(changed.state.causal_raster_id);self.assertTrue(changed.state.beam_blank)
        self.assertEqual(changed.state.live_view_id,started.state.live_view_id)
        self.assertIsNotNone(changed.bank_dispatch)
        ready=p.tick(120_000_001,t.EpisodeInputs(bank_result=p.ready(changed.bank_dispatch)))
        self.assertFalse(ready.started_raster_ids)
        delivery=SweepDelivery('fixture',identifier,end.ordinal)
        resumed=p.tick(120_000_002,delivery=delivery)
        self.assertEqual(resumed.state.current_configuration.geometry,NEW.bind(0.,0.).geometry)
        self.assertNotEqual(resumed.state.causal_raster_id,identifier)
        self.assertEqual(resumed.state.episode_incident_pA_ns,4_970_000_000)

    def test_same_grid_does_not_interrupt_or_recompute_intrinsic_response(self):
        p=Probe();started=p.start();result=p.configure(request=OLD)
        self.assertEqual(result.state.causal_raster_id,started.state.causal_raster_id)
        self.assertFalse(result.ended_raster_ids);self.assertIsNone(result.bank_dispatch)
        self.assertGreater(result.state.episode_incident_pA_ns,0)

    def test_unauthorized_grid_change_is_inert_while_clock_and_exposure_continue(self):
        p=Probe();started=p.start();result=p.configure(authority=t.AuthorityRef('other',1))
        self.assertEqual(result.state.causal_raster_id,started.state.causal_raster_id)
        self.assertFalse(result.ended_raster_ids)
        self.assertEqual(next(f.body[2] for f in result.facts if f.kind=='DISPOSITION'),'UNAUTHORIZED')
        self.assertGreater(result.state.episode_incident_pA_ns,0)

    def test_Stop_wins_over_reconfigure_and_never_starts_a_replacement(self):
        p=Probe();p.start()
        result=p.tick(120_000_000,t.EpisodeInputs(stop=t.SafetyStop('stop',p.authority),
            normal=t.ConfigureLive('configure',p.authority,NEW,0)))
        self.assertEqual(result.state.phase,'STOPPED');self.assertTrue(result.state.beam_blank)
        self.assertEqual(next(f.body[-1] for f in result.facts if f.kind=='RASTER_END'),'STOP')
        self.assertEqual(next(f.body[2] for f in result.facts if f.kind=='DISPOSITION' and f.body[0]=='configure'),'STOP')
        self.assertIsNone(result.bank_dispatch)

    def test_pending_lens_target_is_rebound_and_old_grid_reply_cannot_apply(self):
        p=Probe();p.start();settings=t.EpisodeSettings(50,3e-6,.2,-.3)
        lens=p.tick(80_000_000,t.EpisodeInputs(normal=t.SetOptics('lens',p.authority,settings)))
        switched=p.configure(at=90_000_000)
        self.assertIsNone(switched.bank_dispatch)
        stale=p.tick(91_000_000,t.EpisodeInputs(bank_result=p.ready(lens.bank_dispatch)))
        self.assertEqual(stale.state.settings,INITIAL)
        self.assertEqual(stale.bank_dispatch.configuration,NEW.bind(0.,0.))
        self.assertEqual(stale.bank_dispatch.settings,settings)
        new=p.tick(131_000_000,t.EpisodeInputs(bank_result=p.ready(stale.bank_dispatch)))
        self.assertEqual(new.state.settings,settings)
        self.assertIsNone(new.state.interlock_reason)
        self.assertEqual(new.state.episode_incident_pA_ns,switched.state.episode_incident_pA_ns)

    def test_expiry_after_partial_interruption_fences_ready_and_delivery(self):
        p=Probe(expiry=128_000_000);p.start();changed=p.configure()
        end=next(f for f in changed.facts if f.kind=='RASTER_END')
        result=p.tick(128_000_000,t.EpisodeInputs(bank_result=p.ready(changed.bank_dispatch)),
            SweepDelivery('fixture',end.body[0],end.ordinal))
        self.assertFalse(result.started_raster_ids);self.assertIsNone(result.state.lease)
        self.assertTrue(result.state.beam_blank)

    def test_independent_certificate_rejects_a_forged_partial_exposure(self):
        p=Probe();p.start();p.configure()
        verifier=PacedCausalVerifier(SCIENCE,INITIAL,episode_namespace='fixture',capacity=CAP)
        for begin,facts,end in p.events[:-1]:verifier.verify(begin,facts,end)
        begin,facts,end=p.events[-1];old=verifier.cut
        corrupt=[]
        for f in facts:
            if f.kind=='RASTER_END':
                body=list(f.body);body[3]+=1;f=replace(f,body=tuple(body))
            corrupt.append(f)
        with self.assertRaises(ValueError):verifier.verify(begin,tuple(corrupt),end)
        self.assertIs(verifier.cut,old)
        with self.assertRaises(ValueError):verifier.verify(begin,facts,end)


if __name__=='__main__':unittest.main()
