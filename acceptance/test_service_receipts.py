"""Independent lifecycle/admission checks, without a GPU or running service."""
import queue
import threading
from types import SimpleNamespace
import unittest

from engine import human_episode_types as t
from engine.episode_credits import EpisodeCapacity
from engine.human_verified_episode import GroundedEpisode
from runtime.core_human_service import API
from runtime.finite_human_service import FiniteHumanService
from runtime.live_operation_receipts import LiveOperationReceipts


def fixture(normal=256, safety=64):
    service = FiniteHumanService.__new__(FiniteHumanService)
    service.normal, service.safety = queue.Queue(normal), queue.Queue(safety)
    service.operations = {}
    service.live_receipts = LiveOperationReceipts()
    service.lock, service.stop_event = threading.Lock(), threading.Event()
    service.failure = None
    service.kernel = SimpleNamespace(causal_error=None)
    return service


def configuration(pixels=64, width=2e-6):
    return t.ScanRequest(pixels, pixels, width, 0., 0., 20000).bind(0., 0., 0.)


class LiveReceiptTests(unittest.TestCase):
    def setUp(self):
        self.service = fixture()
        self.at = 0
        self.config = configuration()
        self.add('live')
        self.event('GEOMETRY', ('live', 1, self.config))
        self.event('DISPOSITION', ('live', 'ACCEPTED', 'OK', 'StartCapture'))
        self.start(self.config)

    def add(self, operation):
        self.service.operations[operation] = dict(operation_id=operation,
            status='RECEIVED', reason=None, observed_at_ns=None)

    def event(self, kind, body):
        self.at += 1
        self.service._event(SimpleNamespace(kind=kind, body=body, event_at_ns=self.at))

    def start(self, config):
        self.event('RASTER_START', ('raster', 1, 0, 'LIVE', 'live', 'view', config, None, 'initial'))

    def configure(self, op, config):
        self.add(op)
        self.event('GEOMETRY', (op, self.at, config))
        self.event('DISPOSITION', (op, 'ACCEPTED', 'OK', 'ConfigureLive'))

    def status(self, op):
        return self.service.operation(op)['status']

    def test_request_is_not_application_and_matching_raster_resolves_receipt(self):
        changed = configuration(128)
        self.configure('configure', changed)
        self.assertEqual(self.status('configure'), 'ACCEPTED')
        self.start(self.config)
        self.assertEqual(self.status('configure'), 'ACCEPTED')
        self.event('RASTER_END', ('raster', 0, 0, 0, 'GEOMETRY_CHANGED'))
        self.start(changed)
        self.assertEqual(self.status('configure'), 'COMPLETED')
        self.assertEqual(self.status('live'), 'RUNNING')
        self.assertEqual(self.service.operation('configure')['observed_at_ns'], self.at)

    def test_same_active_grid_finishes_only_after_accepted_disposition(self):
        self.add('same')
        self.event('GEOMETRY', ('same', 2, self.config))
        self.assertEqual(self.status('same'), 'RECEIVED')
        self.event('DISPOSITION', ('same', 'ACCEPTED', 'OK', 'ConfigureLive'))
        self.assertEqual(self.status('same'), 'COMPLETED')
        self.event('DISPOSITION', ('same', 'ACCEPTED', 'OK', 'ConfigureLive'))
        self.assertEqual(self.status('same'), 'COMPLETED')

    def test_superseded_configure_cannot_be_completed_by_a_later_match(self):
        first, second = configuration(128), configuration(256)
        self.configure('first', first)
        self.configure('second', second)
        self.assertEqual(self.status('first'), 'CANCELLED')
        self.assertEqual(self.service.operation('first')['reason'], 'SUPERSEDED')
        self.start(first)
        self.assertEqual(self.status('first'), 'CANCELLED')
        self.assertEqual(self.status('second'), 'ACCEPTED')
        self.start(second)
        self.assertEqual(self.status('second'), 'COMPLETED')

    def test_freeze_resolves_separately_and_late_acceptance_cannot_downgrade_it(self):
        self.add('freeze')
        self.event('SESSION_ENDED', ('live', 'COMPLETED', 'freeze'))
        self.assertEqual(self.status('live'), 'COMPLETED')
        self.assertEqual(self.status('freeze'), 'COMPLETED')
        self.event('DISPOSITION', ('freeze', 'ACCEPTED', 'OK', 'FreezeLive'))
        self.assertEqual(self.status('freeze'), 'COMPLETED')
        self.assertIsNone(self.service.live_receipts.freeze)

    def test_pending_freeze_and_configure_cancel_on_stop(self):
        self.configure('configure', configuration(128))
        self.add('freeze')
        self.event('DISPOSITION', ('freeze', 'ACCEPTED', 'OK', 'FreezeLive'))
        self.event('SESSION_ENDED', ('live', 'STOP', 'freeze'))
        for op in ('live', 'configure', 'freeze'):
            self.assertEqual(self.status(op), 'CANCELLED')
            self.assertEqual(self.service.operation(op)['reason'], 'STOP')

    def test_second_freeze_supersedes_first_without_rewriting_first_terminal(self):
        for op in ('first', 'second'):
            self.add(op)
            self.event('DISPOSITION', (op, 'ACCEPTED', 'OK', 'FreezeLive'))
        self.assertEqual(self.status('first'), 'CANCELLED')
        self.event('SESSION_ENDED', ('live', 'COMPLETED', 'second'))
        self.assertEqual(self.status('first'), 'CANCELLED')
        self.assertEqual(self.status('second'), 'COMPLETED')

    def test_never_applied_configuration_is_not_success_on_completed_session(self):
        self.configure('configure', configuration(128))
        self.event('SESSION_ENDED', ('live', 'COMPLETED', None))
        self.assertEqual(self.status('configure'), 'CANCELLED')
        self.assertEqual(self.service.operation('configure')['reason'], 'NOT_APPLIED')

    def test_unrelated_motion_terminal_does_not_cancel_live_configuration(self):
        self.configure('configure', configuration(128))
        self.event('SESSION_ENDED', ('stage', 'COMPLETED', None))
        self.assertEqual(self.status('configure'), 'ACCEPTED')
        self.start(configuration(128))
        self.assertEqual(self.status('configure'), 'COMPLETED')

    def test_authority_loss_and_fault_cancel_pending_commands(self):
        for kind, body in [('LEASE', (None, 'EXPIRED')), ('INTERLOCK', ('BANK_FAILED',))]:
            with self.subTest(kind=kind):
                self.setUp()
                self.configure('configure', configuration(128))
                self.add('freeze')
                self.event('DISPOSITION', ('freeze', 'ACCEPTED', 'OK', 'FreezeLive'))
                self.event(kind, body)
                self.assertEqual(self.status('configure'), 'CANCELLED')
                self.assertEqual(self.status('freeze'), 'CANCELLED')

    def test_rejected_configure_preserves_an_earlier_admitted_request(self):
        self.configure('valid', configuration(128))
        self.add('rejected')
        self.event('DISPOSITION', ('rejected', 'REJECTED', 'UNAUTHORIZED', 'ConfigureLive'))
        self.start(configuration(128))
        self.assertEqual(self.status('valid'), 'COMPLETED')
        self.assertEqual(self.status('rejected'), 'REJECTED')


class AdmissionAccountingTests(unittest.TestCase):
    def test_normal_capacity_refusal_retains_only_admitted_receipts_and_stop_reserve(self):
        service = fixture()
        admitted = []
        for _ in range(256):admitted.append(service.request(API, 'lease')['operation_id'])
        for _ in range(1792):
            with self.assertRaisesRegex(BufferError, 'ingress_capacity'):service.request(API, 'lease')
        self.assertEqual(service.normal.qsize(), 256)
        self.assertEqual(set(service.operations), set(admitted))
        stop = {'action':'stop', 'parameters':{}, 'expected_stop_generation':0}
        stops = [service.request(API, 'command', stop)['operation_id'] for _ in range(64)]
        for _ in range(50):
            with self.assertRaisesRegex(BufferError, 'ingress_capacity'):service.request(API, 'command', stop)
        self.assertEqual(set(service.operations), set(admitted+stops))
        self.assertEqual(service.safety.qsize(), 64)

    def test_record_exists_before_consumer_and_is_not_overwritten_by_request_return(self):
        service = fixture()
        class ImmediateQueue(queue.Queue):
            def put_nowait(self, item):
                operation = item[-1]
                with service.lock:
                    self.assert_visible = operation in service.operations
                    service.operations[operation]['status'] = 'COMPLETED'
                return super().put_nowait(item)
        service.normal = ImmediateQueue(1)
        receipt = service.request(API, 'lease')
        self.assertTrue(service.normal.assert_visible)
        self.assertEqual(service.operation(receipt['operation_id'])['status'], 'COMPLETED')

    def test_concurrent_producers_and_consumer_keep_every_admitted_receipt(self):
        service = fixture(normal=8)
        receipts, errors = [], []
        result_lock = threading.Lock()
        done = threading.Event()
        def consume():
            while not done.is_set() or not service.normal.empty():
                try:item = service.normal.get(timeout=.02)
                except queue.Empty:continue
                with service.lock:
                    if item[-1] not in service.operations:errors.append('missing receipt')
                    else:service.operations[item[-1]]['status'] = 'COMPLETED'
        def produce():
            for _ in range(100):
                try:record = service.request(API, 'lease')
                except BufferError:continue
                with result_lock:receipts.append(record['operation_id'])
        consumer = threading.Thread(target=consume)
        producers = [threading.Thread(target=produce) for _ in range(4)]
        consumer.start()
        for thread in producers:thread.start()
        for thread in producers:thread.join(5);self.assertFalse(thread.is_alive())
        done.set();consumer.join(5);self.assertFalse(consumer.is_alive())
        self.assertFalse(errors)
        self.assertEqual(set(service.operations), set(receipts))
        self.assertTrue(all(v['status']=='COMPLETED' for v in service.operations.values()))


class ScalarLifecycleTests(unittest.TestCase):
    def test_receipts_follow_genuine_scalar_configuration_and_freeze_facts(self):
        science = t.ScienceIdentity('generic','a'*64,'b'*64,'VECTOR','c'*64,'count')
        owner = GroundedEpisode(science,t.EpisodeSettings(10),episode_namespace='actual-facts',
            capacity=EpisodeCapacity(4096,256,128,4096,65536,65536))
        service = fixture()
        def tick(at, inputs=t.EpisodeInputs()):
            result=owner.tick(at,inputs)
            for fact in result.facts:service._event(fact)
            return result
        def ready(work):
            return t.BankReady(work,t.ScalarBankHandle('bank-'+work.job_id,1,'d'*64,
                science.solver_source_digest,work.configuration.geometry,work.settings))
        auth=tick(0,t.EpisodeInputs(authority=t.GrantAuthority('grant','human',10**12))).state.lease.authority
        for op in ('live','configure','freeze','stop'):
            service.operations[op]=dict(operation_id=op,status='RECEIVED',reason=None,observed_at_ns=None)
        started=tick(0,t.EpisodeInputs(normal=t.StartCapture('live',auth,'LIVE',
            t.ScanRequest(64,64,2e-6,0.,0.,1000000),0)))
        tick(1,t.EpisodeInputs(bank_result=ready(started.bank_dispatch)))
        tick(50000000)
        tick(71000000,t.EpisodeInputs(normal=t.ConfigureLive('configure',auth,
            t.ScanRequest(128,128,2e-6,0.,0.,100000),0)))
        self.assertEqual(service.operation('configure')['status'],'ACCEPTED')
        boundary=tick(5000000000)
        tick(5000000001,t.EpisodeInputs(bank_result=ready(boundary.bank_dispatch)))
        self.assertEqual(service.operation('configure')['status'],'COMPLETED')
        tick(5000000002,t.EpisodeInputs(normal=t.FreezeLive('freeze',auth,owner.snapshot().live_view_id,0)))
        ended=tick(7000000000)
        self.assertEqual(service.operation('freeze')['status'],'COMPLETED')
        self.assertEqual(service.operation('live')['status'],'COMPLETED')
        self.assertEqual(ended.state.stop_generation,0)
        stopped=tick(7000000001,t.EpisodeInputs(stop=t.SafetyStop('stop',auth)))
        self.assertEqual(service.operation('stop')['status'],'COMPLETED')
        self.assertEqual(stopped.state.stop_generation,1)

    def test_genuine_bank_failure_is_terminal_without_fabricating_a_stop(self):
        science = t.ScienceIdentity('generic', 'a'*64, 'b'*64, 'VECTOR', 'c'*64, 'count')
        owner = GroundedEpisode(science, t.EpisodeSettings(10), episode_namespace='receipt-test',
            capacity=EpisodeCapacity(4096,256,128,4096,65536,65536))
        service = fixture()
        def tick(at, inputs=t.EpisodeInputs()):
            result = owner.tick(at, inputs)
            for fact in result.facts:service._event(fact)
            return result
        grant = tick(0, t.EpisodeInputs(authority=t.GrantAuthority('grant', 'human', 10**12)))
        auth = grant.state.lease.authority
        for op in ('live', 'optics'):
            service.operations[op] = dict(operation_id=op, status='RECEIVED', reason=None, observed_at_ns=None)
        start = tick(0, t.EpisodeInputs(normal=t.StartCapture('live', auth, 'LIVE',
            t.ScanRequest(64,64,2e-6,0.,0.,20000),0)))
        initial = start.bank_dispatch
        handle = t.ScalarBankHandle('initial-bank',1,'d'*64,science.solver_source_digest,
            initial.configuration.geometry,initial.settings)
        tick(1,t.EpisodeInputs(bank_result=t.BankReady(initial,handle)))
        tick(50000000)
        exposed=tick(75000000)
        self.assertGreater(exposed.state.episode_incident_pA_ns,0)
        changed=tick(76000000,t.EpisodeInputs(normal=t.SetOptics('optics',auth,t.EpisodeSettings(10,4e-6))))
        failed = tick(77000000, t.EpisodeInputs(bank_result=t.BankFailed(changed.bank_dispatch)))
        self.assertEqual(failed.state.phase, 'INTERLOCKED')
        self.assertTrue(failed.state.beam_blank)
        self.assertIsNone(failed.state.lease)
        self.assertEqual(failed.state.stop_generation, 0)
        self.assertEqual(service.operation('live')['status'], 'CANCELLED')
        self.assertEqual(service.operation('optics')['status'], 'CANCELLED')
        self.assertEqual(service.operation('optics')['reason'], 'BANK_FAILED')
        total = failed.state.episode_incident_pA_ns
        later = tick(10**9, t.EpisodeInputs(stop=t.SafetyStop('after-fault', auth)))
        self.assertEqual(later.state.episode_incident_pA_ns, total)
        self.assertEqual(later.state.stop_generation, 0)
        self.assertEqual(later.facts, ())


if __name__ == '__main__':unittest.main()
