"""Independent command/image attribution and failure-order acceptance, CPU only."""
import copy
import queue
import threading
from types import SimpleNamespace
import unittest

from engine import human_episode_types as t
from engine.episode_credits import EpisodeCapacity
from engine.human_verified_episode import GroundedEpisode
from runtime.core_human_service import API, GUI
from runtime.finite_human_service import FiniteHumanService
from runtime.live_operation_receipts import LiveOperationReceipts


def service_fixture():
    service = FiniteHumanService.__new__(FiniteHumanService)
    service.lock, service.stop_event = threading.Lock(), threading.Event()
    service.normal, service.safety = queue.Queue(256), queue.Queue(64)
    service.operations, service.image_records = {}, {}
    service.live_receipts = LiveOperationReceipts()
    service.kernel = SimpleNamespace(causal_error=None)
    service.failure = None
    return service


def parameters(pixels=64, width=2e-6):
    return dict(width_px=pixels, height_px=pixels, field_width_m=width,
        offset_x_m=0., offset_y_m=0., dwell_ns=20000)


class AssociationTests(unittest.TestCase):
    def setUp(self):
        self.service = service_fixture()
        self.ordinal = 0

    def command(self, action='scan_single', params=None, owner=API):
        return self.service.request(owner, 'command', dict(action=action,
            parameters=parameters() if params is None else params,
            expected_stop_generation=0))['operation_id']

    def event(self, kind, body):
        self.ordinal += 1
        fact = SimpleNamespace(ordinal=self.ordinal, kind=kind, body=body,
            event_at_ns=self.ordinal * 100)
        self.service._event(fact)
        return fact

    def accepted(self, operation, command):
        return self.event('DISPOSITION', (operation, 'ACCEPTED', 'OK', command))

    def start(self, operation, raster='r1', view=None, params=None):
        configuration = t.ScanRequest(**(parameters() if params is None else params)).bind(0., 0., 0.)
        return self.event('RASTER_START', (raster, 1, 0, 'LIVE' if view else 'SINGLE',
            operation, view, configuration, None, 'initial'))

    def end(self, raster='r1', elapsed=500, reason='COMPLETED'):
        return self.event('RASTER_END', (raster, elapsed, elapsed, 100, reason))

    def publish(self, image='i1', raster='r1', source=None, elapsed=500,
                outcome='COMPLETED', ordinal=None):
        ready = SimpleNamespace(image_id=image, causal_raster_id=raster,
            numerical_ordinal=self.ordinal if ordinal is None else ordinal)
        observation = dict(image_id=image, source_id=source or raster,
            cut_elapsed_ns=elapsed, outcome=outcome)
        with self.service.lock:
            self.service.image_records[image] = (ready, observation)
            self.service._acquisitions_locked().publish(ready, observation)

    def project(self, operation, owner=API):
        return self.service.operation_acquisitions(owner, operation)

    def live(self):
        operation = self.command('scan_live')
        self.accepted(operation, 'StartCapture')
        self.start(operation, view='v1')
        return operation

    def configure(self, params):
        operation = self.command('configure_live', params)
        configuration = t.ScanRequest(**params).bind(0., 0., 0.)
        self.event('GEOMETRY', (operation, 1, configuration))
        self.accepted(operation, 'ConfigureLive')
        return operation

    def test_received_accepted_and_unstarted_commands_cannot_claim_existing_image(self):
        operation = self.command()
        self.publish('older', 'old', ordinal=1)
        self.accepted(operation, 'StartCapture')
        value = self.project(operation)
        self.assertEqual(value['receipt']['status'], 'ACCEPTED')
        for key in ('association', 'latest_cut', 'final_cut'):
            self.assertIsNone(value[key])
        self.event('SESSION_ENDED', (operation, 'STOP', None))
        self.assertIsNone(self.project(operation)['association'])

    def test_single_uses_actual_start_and_terminal_publication_not_receipt_or_latest(self):
        operation = self.command()
        fact = self.start(operation)
        self.accepted(operation, 'StartCapture')
        self.assertEqual(self.project(operation)['association'], dict(relation='started_single',
            source_id='r1', raster_id='r1', applied_at_ns=fact.event_at_ns))
        self.publish('partial', elapsed=200, outcome='ACQUIRING', ordinal=2)
        self.end()
        self.event('SESSION_ENDED', (operation, 'COMPLETED', None))
        value = self.project(operation)
        self.assertEqual(value['receipt']['status'], 'COMPLETED')
        self.assertEqual(value['latest_cut']['image_id'], 'partial')
        self.assertIsNone(value['final_cut'])
        self.publish('unrelated', 'r2', ordinal=100)
        self.publish('wrong-elapsed', elapsed=499, ordinal=3)
        self.assertIsNone(self.project(operation)['final_cut'])
        self.publish('terminal', ordinal=4)
        self.assertEqual(self.project(operation)['final_cut']['image_id'], 'terminal')

    def test_live_latest_explicitly_identifies_older_raster_and_final_waits_for_session_end(self):
        live = self.live()
        self.end()
        self.publish(source='v1')
        self.assertIsNone(self.project(live)['final_cut'])
        self.start(live, 'r2', 'v1')
        value = self.project(live)
        self.assertEqual(value['association']['raster_id'], 'r2')
        self.assertEqual(value['latest_cut']['raster_id'], 'r1')
        self.end('r2', 600)
        self.event('SESSION_ENDED', (live, 'COMPLETED', None))
        self.assertIsNone(self.project(live)['final_cut'])
        self.publish('final', 'r2', 'v1', 600)
        self.assertEqual(self.project(live)['final_cut']['raster_id'], 'r2')

    def test_configure_first_application_is_immutable_and_old_raster_cuts_do_not_match(self):
        live = self.live()
        changed = parameters(128)
        configure = self.configure(changed)
        self.assertIsNone(self.project(configure)['association'])
        self.end(reason='GEOMETRY_CHANGED')
        applied = self.start(live, 'r2', 'v1', changed)
        expected = dict(relation='configuration_applied', source_id='v1',
            raster_id='r2', applied_at_ns=applied.event_at_ns)
        self.assertEqual(self.project(configure)['association'], expected)
        self.publish('old', 'r1', 'v1', ordinal=2)
        self.assertIsNone(self.project(configure)['latest_cut'])
        self.end('r2', 900)
        self.publish('config-final', 'r2', 'v1', 900)
        self.start(live, 'r3', 'v1', changed)
        self.publish('later', 'r3', 'v1', 100, 'ACQUIRING')
        self.assertEqual(self.project(configure)['association'], expected)
        self.assertEqual(self.project(configure)['final_cut']['image_id'], 'config-final')

    def test_already_active_is_labelled_and_does_not_create_exposure(self):
        live = self.live()
        self.publish('partial', source='v1', elapsed=200, outcome='ACQUIRING')
        before = self.ordinal
        same = self.configure(parameters())
        value = self.project(same)
        self.assertEqual(value['association']['relation'], 'already_active')
        self.assertEqual(value['association']['raster_id'], 'r1')
        self.assertEqual(value['association']['applied_at_ns'], self.ordinal * 100)
        self.assertEqual(value['latest_cut']['image_id'], 'partial')
        self.assertEqual(self.ordinal, before + 2)
        self.assertEqual(self.project(live)['association']['raster_id'], 'r1')

    def test_superseded_cancelled_rejected_and_never_applied_configs_stay_unassociated(self):
        live = self.live()
        first = self.configure(parameters(128))
        second = self.configure(parameters(256))
        rejected = self.command('configure_live', parameters(128))
        self.event('DISPOSITION', (rejected, 'REJECTED', 'UNAUTHORIZED', 'ConfigureLive'))
        self.end()
        self.start(live, 'r2', 'v1', parameters(128))
        self.event('SESSION_ENDED', (live, 'STOP', None))
        for operation in (first, second, rejected):
            self.assertIsNone(self.project(operation)['association'])
        self.assertEqual(self.project(first)['receipt']['reason'], 'SUPERSEDED')

    def test_freeze_same_tick_before_admission_preserves_exact_final_raster(self):
        live = self.live()
        self.end()
        self.publish('previous', source='v1')
        self.start(live, 'r2', 'v1')
        freeze = self.command('freeze', {'source_id': 'v1'})
        self.end('r2', 700)
        self.event('SESSION_ENDED', (live, 'COMPLETED', freeze))
        self.accepted(freeze, 'FreezeLive')
        value = self.project(freeze)
        self.assertEqual(value['receipt']['status'], 'COMPLETED')
        self.assertEqual(value['association']['relation'], 'freeze_of')
        self.assertEqual(value['association']['raster_id'], 'r2')
        self.assertEqual(value['latest_cut']['raster_id'], 'r1')
        self.assertIsNone(value['final_cut'])
        self.publish('frozen', 'r2', 'v1', 700)
        self.assertEqual(self.project(freeze)['final_cut'], self.project(live)['final_cut'])

    def test_freeze_between_sweeps_reuses_already_published_terminal(self):
        live = self.live()
        self.end()
        self.publish(source='v1')
        freeze = self.command('freeze', {'source_id': 'v1'})
        self.event('SESSION_ENDED', (live, 'COMPLETED', freeze))
        self.assertEqual(self.project(freeze)['final_cut']['image_id'], 'i1')

    def test_interruption_retains_cancelled_outcome_instead_of_success(self):
        for reason in ('STOP', 'AUTHORITY_EXPIRED', 'BANK_FAILED'):
            with self.subTest(reason=reason):
                self.setUp()
                live = self.live()
                config = self.configure(parameters(128))
                freeze = self.command('freeze', {'source_id': 'v1'})
                self.accepted(freeze, 'FreezeLive')
                self.end(reason=reason)
                self.event('SESSION_ENDED', (live, reason, freeze))
                self.publish(source='v1', outcome='CANCELLED')
                for operation in (live, freeze):
                    value = self.project(operation)
                    self.assertEqual(value['receipt']['status'], 'CANCELLED')
                    self.assertEqual(value['final_cut']['outcome'], 'CANCELLED')
                self.assertIsNone(self.project(config)['association'])

    def test_lease_loss_and_interlock_do_not_allow_later_configuration_match(self):
        for kind, body in (('LEASE', (None, 'EXPIRED')), ('INTERLOCK', ('BANK_FAILED',))):
            with self.subTest(kind=kind):
                self.setUp()
                live = self.live()
                config = self.configure(parameters(128))
                self.event(kind, body)
                self.start(live, 'r2', 'v1', parameters(128))
                self.assertIsNone(self.project(config)['association'])

    def test_duplicate_late_facts_and_out_of_order_images_cannot_rebind_results(self):
        operation = self.command()
        old = self.start(operation)
        self.end()
        self.event('SESSION_ENDED', (operation, 'COMPLETED', None))
        expected = self.project(operation)['association']
        self.service._event(old)
        self.publish('terminal', ordinal=3)
        self.publish('late-partial', elapsed=200, outcome='ACQUIRING', ordinal=2)
        self.assertEqual(self.project(operation)['association'], expected)
        self.assertEqual(self.project(operation)['latest_cut']['image_id'], 'terminal')
        self.assertEqual(self.project(operation)['final_cut']['image_id'], 'terminal')

    def test_unknown_removed_unavailable_and_foreign_operations_do_not_fall_back(self):
        operation = self.command()
        gui = self.command(owner=GUI)
        for identity in ('unknown', gui):
            with self.assertRaises(KeyError):
                self.project(identity)
        del self.service.operations[operation]
        with self.assertRaises(KeyError):
            self.project(operation)
        own = self.command()
        self.service.failure = 'private_failure_details'
        with self.assertRaisesRegex(BufferError, 'service_unavailable'):
            self.project(own)

    def test_missing_image_is_null_and_no_other_image_can_replace_it(self):
        operation = self.command()
        self.start(operation)
        self.end()
        self.publish('terminal')
        self.publish('other', 'other-raster', ordinal=999)
        del self.service.image_records['terminal']
        value = self.project(operation)
        self.assertIsNone(value['latest_cut'])
        self.assertIsNone(value['final_cut'])

    def test_exact_closed_projection_copy_and_get_has_no_mutations_or_artifact_io(self):
        operation = self.command()
        self.start(operation)
        self.end()
        self.publish()
        tracker = self.service._operation_acquisitions
        before = copy.deepcopy(tracker.__dict__)
        value = self.project(operation)
        self.assertEqual(set(value), {'protocol', 'operation_id', 'command', 'receipt',
            'association', 'latest_cut', 'final_cut'})
        self.assertEqual(set(value['receipt']), {'operation_id', 'status', 'reason', 'observed_at_ns'})
        self.assertEqual(set(value['association']), {'relation', 'source_id', 'raster_id', 'applied_at_ns'})
        self.assertEqual(set(value['final_cut']), {'image_id', 'source_id', 'raster_id', 'cut_elapsed_ns', 'outcome'})
        self.assertEqual(value['protocol'], 'vsem.operation-acquisitions.v1')
        value['receipt']['reason'] = 'tampered'
        value['association']['source_id'] = 'tampered'
        value['final_cut']['image_id'] = 'tampered'
        self.assertEqual(tracker.__dict__, before)
        self.assertEqual(self.project(operation)['association']['source_id'], 'r1')

    def test_non_acquisition_operations_have_null_references_and_capacity_has_no_orphans(self):
        lease = self.service.request(API, 'lease')['operation_id']
        stop = self.command('stop', {})
        for operation, command in ((lease, 'lease'), (stop, 'stop')):
            value = self.project(operation)
            self.assertEqual(value['command'], command)
            self.assertTrue(all(value[k] is None for k in ('association', 'latest_cut', 'final_cut')))
        self.service.normal = queue.Queue(1)
        self.command()
        before = set(self.service._operation_acquisitions.entries)
        with self.assertRaisesRegex(BufferError, 'ingress_capacity'):
            self.command()
        self.assertEqual(set(self.service._operation_acquisitions.entries), before)
        self.assertEqual(set(self.service.operations), before)


class GenuineScalarAssociationTests(unittest.TestCase):
    def test_actual_owner_fact_identities_determine_configure_and_freeze_association(self):
        service = service_fixture()
        science = t.ScienceIdentity('generic', 'a'*64, 'b'*64, 'VECTOR', 'c'*64, 'count')
        owner = GroundedEpisode(science, t.EpisodeSettings(10), episode_namespace='association-facts',
            capacity=EpisodeCapacity(4096,256,128,4096,65536,65536))
        def tick(at, inputs=t.EpisodeInputs()):
            result = owner.tick(at, inputs)
            for fact in result.facts:
                service._event(fact)
            return result
        def ready(ticket):
            return t.BankReady(ticket, t.ScalarBankHandle('bank-'+ticket.job_id, 1, 'd'*64,
                science.solver_source_digest, ticket.configuration.geometry, ticket.settings))
        def register(action, params):
            return service.request(API, 'command', dict(action=action, parameters=params,
                expected_stop_generation=0))['operation_id']
        auth = tick(0, t.EpisodeInputs(authority=t.GrantAuthority('grant', API.holder, 10**12))).state.lease.authority
        initial = dict(parameters(), dwell_ns=1000000)
        live = register('scan_live', initial)
        first = tick(0, t.EpisodeInputs(normal=t.StartCapture(live, auth, 'LIVE', t.ScanRequest(**initial), 0)))
        tick(1, t.EpisodeInputs(bank_result=ready(first.bank_dispatch)))
        started = tick(50000000)
        actual_start = next(f for f in started.facts if f.kind == 'RASTER_START')
        value = service.operation_acquisitions(API, live)
        self.assertEqual(value['association']['raster_id'], actual_start.body[0])
        self.assertEqual(value['association']['source_id'], actual_start.body[5])
        changed = dict(parameters(128), dwell_ns=100000)
        configure = register('configure_live', changed)
        tick(71000000, t.EpisodeInputs(normal=t.ConfigureLive(configure, auth, t.ScanRequest(**changed), 0)))
        self.assertIsNone(service.operation_acquisitions(API, configure)['association'])
        boundary = tick(5000000000)
        applied = tick(5000000001, t.EpisodeInputs(bank_result=ready(boundary.bank_dispatch)))
        actual_applied = next(f for f in applied.facts if f.kind == 'RASTER_START')
        value = service.operation_acquisitions(API, configure)
        self.assertEqual(value['association']['raster_id'], actual_applied.body[0])
        self.assertEqual(value['association']['applied_at_ns'], actual_applied.event_at_ns)
        freeze = register('freeze', {'source_id': owner.snapshot().live_view_id})
        tick(5000000002, t.EpisodeInputs(normal=t.FreezeLive(freeze, auth, owner.snapshot().live_view_id, 0)))
        tick(7000000000)
        value = service.operation_acquisitions(API, freeze)
        self.assertEqual(value['receipt']['status'], 'COMPLETED')
        self.assertEqual(value['association']['raster_id'], actual_applied.body[0])
        self.assertEqual(value['association']['relation'], 'freeze_of')
        self.assertIsNone(value['final_cut'])  # Scalar completion is not numerical delivery.


if __name__ == '__main__':
    unittest.main()
