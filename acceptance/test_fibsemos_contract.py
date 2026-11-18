"""Independent M05A CPU contracts; locally authored real HTTP fixture only.

No upstream import or engine import. These tests do not establish physical image
response or genuine fibsemOS compatibility; those need separately approved gates.
"""
import ast
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'integrations/fibsemos/src'
sys.path.insert(0, str(SOURCE))
from vsem_fibsemos.client import Client
from vsem_fibsemos.errors import (AdmissionUnknown, AuthorityError, HTTPFailure,
                                  OperationFailure, PendingOutcome, ProtocolError,
                                  QualificationRequired)
from vsem_fibsemos import plugin, units
from vsem_fibsemos.records import RawFrame, MAGIC, MAX_METADATA


def metadata(**changes):
    return {'protocol': 'vsem.core-native-image.v2', 'image_id': 'image-42',
            'source_id': 'raster-7', 'mode': 'SINGLE', 'outcome': 'COMPLETED',
            'terminal_reason': 'COMPLETED', 'origin_ns': 500, 'cut_elapsed_ns': 90_000_000,
            'numerical_verified_ordinal': 42, 'causal_verified_ordinal': 42,
            'width_px': 64, 'height_px': 64, 'completed_pixels': 4096,
            'active_dwell_ns': 0, 'dwell_ns': 20000, 'field_width_m': 2e-6,
            'pixel_pitch_m': 2e-6 / 64, 'magnification': .1 / 2e-6,
            'magnification_reference_width_m': .1,
            'stage': {'x_m': .001, 'y_m': -.002, 'z_m': 1e-6, 'working_distance_m': .009999},
            'offset_x_m': 0., 'offset_y_m': 0., 'incident_pA_ns': 8192000000,
            'parameter_segments': [
                {'start_elapsed_ns': 0, 'end_elapsed_ns': 40_000_000, 'current_pA': 100,
                 'focus_offset_m': 0., 'stigmator_x': .1, 'stigmator_y': -.2,
                 'stage': {'x_m': .001, 'y_m': -.002, 'z_m': 1e-6, 'working_distance_m': .009999}},
                {'start_elapsed_ns': 40_000_000, 'end_elapsed_ns': 90_000_000, 'current_pA': 200,
                 'focus_offset_m': 5e-6, 'stigmator_x': -.1, 'stigmator_y': .2,
                 'stage': {'x_m': .0011, 'y_m': -.002, 'z_m': 1e-6, 'working_distance_m': .009999}}],
            'blank_holds': [{'start_elapsed_ns': 30_000_000, 'end_elapsed_ns': 31_000_000}],
            'raw_format': 'uint32_little_endian', 'calibration_status': 'generic_uncalibrated',
            'detector': 'SE', **changes}


class Fixture:
    """Controllable public endpoint, with no physical simulation or private truth."""
    def __init__(self):
        self.commands = []
        self.paths = []
        self.records = {}
        self.status = 'COMPLETED'
        self.command_reply = None
        self.operation_reply = None
        self.drop_admission = False
        self.confirm_stop = True
        self.lease_count = 0
        self.change_epoch_on_lease = False
        self.block_operation = threading.Event()
        self.release_operation = threading.Event()
        self.state_reads = 0
        self.change_base = False
        self.meta = metadata()
        self.raw = struct.pack('<4096I', *range(4096))
        self.state = {'protocol': 'vsem.core-human.v3', 'availability': 'AVAILABLE',
                      'observed_at_ns': 100, 'delivery_age_ns': 10,
                      'interlock_reason': None, 'stop_generation': 8,
                      'control_owned': True, 'control': {'holder': 'operator-api', 'epoch': 3,
                                                       'expires_ns': 30_000_000_000},
                      'applied': {'current_pA': 100, 'focus_offset_m': 0.,
                                  'stigmator_x': .1, 'stigmator_y': -.2},
                      'requested': None, 'stage': {'x_m': 0., 'y_m': 0., 'z_m': 0.},
                      'live_source_id': 'view-3'}
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self, code, value, raw=False):
                payload = value if raw else json.dumps(value).encode()
                self.send_response(code)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                try:
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def authenticated(self):
                fixture.paths.append(self.path)
                return (self.headers.get('Authorization') == 'Bearer fixture-only' and
                        self.headers.get('Cookie') is None and self.headers.get('Origin') is None)

            def do_GET(self):
                if not self.authenticated():
                    return self.respond(401, {})
                if self.path == '/state':
                    fixture.state_reads += 1
                    if fixture.change_base and fixture.state_reads >= 2:
                        fixture.state['applied']['stigmator_y'] = .9
                    return self.respond(200, deepcopy(fixture.state))
                if self.path.startswith('/operation/'):
                    operation = self.path.rsplit('/', 1)[1]
                    if operation == 'op-wait':
                        fixture.block_operation.set()
                        fixture.release_operation.wait(3.)
                    value = fixture.records.get(operation, {'operation_id': operation,
                        'status': fixture.status, 'reason': 'OK', 'observed_at_ns': 120})
                    return self.respond(200, fixture.operation_reply or value)
                if self.path.endswith('/SE'):
                    return self.respond(200, fixture.raw, raw=True)
                if self.path.startswith('/image/'):
                    return self.respond(200, fixture.meta)
                return self.respond(404, {})

            def do_POST(self):
                if not self.authenticated():
                    return self.respond(401, {})
                value = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path == '/command':
                    fixture.commands.append(value)
                    if fixture.drop_admission:
                        self.connection.shutdown(socket.SHUT_RDWR)
                        self.connection.close()
                        return
                    if fixture.command_reply is not None:
                        code, reply = fixture.command_reply
                        return self.respond(code, reply)
                    if value['action'] == 'stop' and fixture.confirm_stop:
                        fixture.state['stop_generation'] += 1
                elif self.path != '/lease':
                    return self.respond(404, {})
                else:
                    fixture.lease_count += 1
                    if fixture.change_epoch_on_lease:
                        fixture.state['control']['epoch'] += 1
                operation = 'op-' + str(len(fixture.records) + 1)
                fixture.records[operation] = {'operation_id': operation, 'status': fixture.status,
                                             'reason': 'OK', 'observed_at_ns': 120}
                self.respond(202, {'operation_id': operation, 'status': 'RECEIVED',
                                   'reason': None, 'observed_at_ns': None})

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=.01))
        self.thread.start()
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port)

    def close(self):
        self.release_operation.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3.)
        assert not self.thread.is_alive()


SETTINGS = {'width_px': 64, 'height_px': 64, 'hfw_m': 2e-6, 'dwell_s': 20e-6}


class MappingTests(unittest.TestCase):
    def test_every_current_roundtrip_including_endpoints(self):
        for current in range(1, 1001):
            self.assertEqual(units.current_to_pa(units.pa_to_current(current)), current)

    def test_rounding_tolerance_does_not_admit_adjacent_currents(self):
        self.assertEqual(units.current_to_pa((100 + 5e-10) * 1e-12), 100)
        for value in (100.01e-12, 99.5e-12, (1 - 2e-9) * 1e-12, (1000 + 2e-9) * 1e-12):
            with self.subTest(value=value), self.assertRaises(ValueError):
                units.current_to_pa(value)

    def test_no_coercion_nonfinite_or_overflow(self):
        class Float(float):
            pass
        for value in (True, False, '1e-10', None, float('nan'), float('inf'), 10**10000, Float(1e-10)):
            for function in (units.current_to_pa, units.dwell_to_ns, units.hfw, units.pa_to_current, units.ns_to_dwell):
                with self.subTest(function=function.__name__, type=type(value)), self.assertRaises(ValueError):
                    function(value)

    def test_supported_rasters_dwells_and_hfw(self):
        for size in (64, 128, 256, 512, 1024):
            self.assertEqual(units.resolution(size, size), (size, size))
        for ns in (20000, 100000, 1000000):
            self.assertEqual(units.dwell_to_ns(units.ns_to_dwell(ns)), ns)
        self.assertEqual(units.hfw(1e-7), 1e-7)
        self.assertEqual(units.hfw(.005), .005)

    def test_unsupported_raster_dwell_and_hfw(self):
        for args in ((64, 128), (2048, 2048), (64., 64), (True, True)):
            with self.assertRaises(ValueError):
                units.resolution(*args)
        for value in (19e-6, 21e-6, .1, -.1, 0):
            with self.assertRaises(ValueError):
                units.dwell_to_ns(value)
        for value in (1e-8, .005001, 0, -1):
            with self.assertRaises(ValueError):
                units.hfw(value)


class RecordTests(unittest.TestCase):
    def test_raw_roundtrip_keeps_counts_above_uint16_and_partial_history(self):
        raw = struct.pack('<4096I', *([0, 65536, 2**32 - 1, 7] * 1024))
        frame = RawFrame.from_observation(raw, metadata(outcome='CANCELLED', completed_pixels=17,
                                                       terminal_reason='STOPPED', incident_pA_ns=None))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'raw.vsem'
            frame.save(path)
            again = RawFrame.load(path)
            self.assertEqual(again.raw, raw)
            self.assertEqual(again.metadata, frame.metadata)
            self.assertIsNone(again.metadata['incident_pA_ns'])
            with self.assertRaises(FileExistsError):
                frame.save(path)

    def test_metadata_defensive_copy_and_unknown_fields_refused(self):
        frame = RawFrame.from_observation(bytes(64 * 64 * 4), metadata())
        other = frame.metadata
        other['parameter_segments'][0]['focus_offset_m'] = 9e-6
        self.assertEqual(frame.metadata['parameter_segments'][0]['focus_offset_m'], 0.)
        with self.assertRaises(ValueError):
            RawFrame.from_observation(frame.raw, metadata(seed=42))

    def test_truncation_digest_trailing_bytes_and_declared_size(self):
        frame = RawFrame.from_observation(bytes(64 * 64 * 4), metadata())
        with tempfile.TemporaryDirectory() as directory:
            good = Path(directory) / 'good'
            bad = Path(directory) / 'bad'
            frame.save(good)
            source = good.read_bytes()
            self.assertIn(b'"completed_pixels":4096', source)
            for changed in (source[:-1], source + b'x', source[:-1] + b'\x01',
                            source.replace(b'"completed_pixels":4096', b'"completed_pixels":4095'),
                            MAGIC + struct.pack('<Q', MAX_METADATA + 1), b'wrong'):
                bad.write_bytes(changed)
                with self.assertRaises((ValueError, ProtocolError)):
                    RawFrame.load(bad)

    def test_fixed_view_known_rounding_clipping_orientation_and_companion(self):
        frame = RawFrame.from_observation(struct.pack('<4096I', *([0, 10, 15, 20, 30, 65536, 2**32-1, 0] * 512)), metadata())
        view, provenance = frame.view(10, 20, 8)
        self.assertEqual(list(view[:8]), [0, 0, 128, 255, 255, 255, 255, 0])
        self.assertEqual(provenance['source_raw_sha256'], frame.digest)
        self.assertTrue(provenance['raw_companion_required'])
        self.assertFalse(provenance['lossless_counts'])
        self.assertEqual(provenance['orientation'], 'columns_positive_x_rows_negative_y')
        view16, _ = frame.view(10, 20, 16)
        self.assertEqual(struct.unpack('<8H', view16[:16]), (0, 0, 32768, 65535, 65535, 65535, 65535, 0))

    def test_vacuum_zero_counts_distinct_from_unacquired_zeros(self):
        raw = bytes(64 * 64 * 4)
        complete = RawFrame.from_observation(raw, metadata())
        partial = RawFrame.from_observation(raw, metadata(completed_pixels=12, outcome='ACQUIRING', terminal_reason=None))
        self.assertEqual(complete.raw, partial.raw)
        self.assertNotEqual(complete.metadata, partial.metadata)
        for args in ((5, 5), (0, 10, 32), (False, 10), (-1, 10)):
            with self.assertRaises(ValueError):
                complete.view(*args)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()
        self.client = Client(self.fixture.origin, 'fixture-only', timeout_s=.5, poll_s=.005)

    def tearDown(self):
        self.client.close()
        self.fixture.close()

    def test_loopback_origin_credentials_and_no_ambient_proxy(self):
        for origin in ('https://127.0.0.1:1', 'http://localhost:1', 'http://example.org:1',
                       'http://user@127.0.0.1:1', 'http://127.0.0.1', self.fixture.origin + '/',
                       self.fixture.origin + '?secret', 'http://127.0.0.1:001'):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                Client(origin, 'fixture-only')
        for token in ('', 'token\r\nInjected: value', True):
            with self.assertRaises(ValueError):
                Client(self.fixture.origin, token)
        with patch.dict('os.environ', {'HTTP_PROXY': 'http://127.0.0.1:1', 'http_proxy': 'http://127.0.0.1:1', 'NO_PROXY': ''}):
            self.assertEqual(self.client.state()['stop_generation'], 8)

    def test_applied_readback_is_not_locally_changed_by_intent(self):
        self.client.set_optics({'current_a': 200e-12})
        self.assertEqual(self.client.state()['applied']['current_pA'], 100)
        command = self.fixture.commands[-1]
        self.assertEqual(command['expected_stop_generation'], 8)
        self.assertEqual(command['parameters'], {'current_pA': 200, 'focus_offset_m': 0.,
                                                'stigmator_x': .1, 'stigmator_y': -.2})

    def test_mixed_unsupported_requests_have_no_side_effects(self):
        for action in (lambda: self.client.set_optics({'current_a': 200e-12, 'voltage_v': 5000}),
                       lambda: self.client.set_optics({'working_distance_m': .01}),
                       lambda: self.client.submit_scan({**SETTINGS, 'rotation': .1}),
                       lambda: self.client.submit_scan({**SETTINGS, 'offset_x_m': .006}),
                       lambda: self.client.move_stage({'x_m': 0., 'y_m': 0., 'z_m': 0., 'frame': 'vendor'}),
                       lambda: self.client.move_stage({'x_m': 0., 'y_m': 0., 'z_m': 0., 'frame': 'vsem_specimen_xyz_m', 'tilt': 0})):
            with self.assertRaises(ValueError):
                action()
        self.assertEqual(self.fixture.paths, [])
        self.assertEqual(self.fixture.commands, [])

    def test_invalid_timeouts_rejected_before_any_network_or_admission(self):
        for timeout in (0, -1, True, float('nan'), float('inf'), '20'):
            for call in (lambda: self.client.acquire_control(timeout),
                         lambda: self.client.set_optics({'current_a': 200e-12}, timeout),
                         lambda: self.client.move_stage({'x_m': 0., 'y_m': 0., 'z_m': 0., 'frame': 'vsem_specimen_xyz_m'}, timeout),
                         lambda: self.client.stop(timeout)):
                with self.assertRaises(ValueError):
                    call()
        self.assertEqual(self.fixture.paths, [])
        self.assertEqual(self.fixture.commands, [])

    def test_combined_focus_z_bound_and_stale_base_rejected(self):
        self.fixture.state['stage']['z_m'] = 20e-6
        with self.assertRaises(ValueError):
            self.client.set_optics({'focus_offset_m': 10e-6})
        self.fixture.state['stage']['z_m'] = 0.
        self.fixture.state_reads = 0
        self.fixture.change_base = True
        with self.assertRaises(AuthorityError):
            self.client.set_optics({'current_a': 200e-12})
        self.assertEqual(self.fixture.commands, [])

    def test_stage_exact_absolute_frame_and_signs_no_transform(self):
        self.client.move_stage({'x_m': .002, 'y_m': -.003, 'z_m': 2e-6, 'frame': 'vsem_specimen_xyz_m'})
        self.assertEqual(self.fixture.commands[-1]['parameters'], {'x_m': .002, 'y_m': -.003, 'z_m': 2e-6})

    def test_scan_roi_configure_and_freeze_are_distinct(self):
        self.client.submit_scan(SETTINGS, mode='LIVE')
        self.client.submit_scan({**SETTINGS, 'offset_y_m': -1e-6}, mode='CONFIGURE_LIVE')
        self.client.freeze('view-3')
        self.assertEqual([c['action'] for c in self.fixture.commands], ['scan_live', 'configure_live', 'freeze'])
        with self.assertRaises(ValueError):
            self.client.freeze('old-view')
        self.assertEqual(self.client.state()['stop_generation'], 8)

    def test_optics_remains_available_during_scan_and_duplicate_scan_refused(self):
        scan = self.client.submit_scan(SETTINGS)
        self.client.set_optics({'focus_offset_m': 2e-6})
        with self.assertRaises(PendingOutcome):
            self.client.submit_scan(SETTINGS)
        self.client.operation(scan['operation_id'])
        self.client.submit_scan(SETTINGS)

    def test_lost_admission_response_halts_workflow_without_replay(self):
        self.fixture.drop_admission = True
        with self.assertRaises(AdmissionUnknown):
            self.client.submit_scan(SETTINGS)
        self.fixture.drop_admission = False
        with self.assertRaises(AdmissionUnknown):
            self.client.submit_scan(SETTINGS)
        self.client.stop()
        self.assertEqual([c['action'] for c in self.fixture.commands], ['scan_single', 'stop'])
        with self.assertRaises(AdmissionUnknown):
            self.client.submit_scan(SETTINGS)

    def test_explicit_capacity_refusal_has_no_unknown_admission(self):
        self.fixture.command_reply = (429, {'error': 'ingress_capacity'})
        with self.assertRaises(HTTPFailure) as caught:
            self.client.submit_scan(SETTINGS)
        self.assertEqual(caught.exception.status, 429)
        self.fixture.command_reply = None
        self.client.submit_scan(SETTINGS)

    def test_known_timeout_requires_reconciliation(self):
        self.fixture.status = 'RUNNING'
        operation = self.client.submit_scan(SETTINGS)['operation_id']
        with self.assertRaises(PendingOutcome) as caught:
            self.client.wait_operation(operation, .02)
        self.assertEqual(caught.exception.operation_id, operation)
        with self.assertRaises(PendingOutcome):
            self.client.set_optics({'current_a': 200e-12})
        self.fixture.records[operation]['status'] = 'CANCELLED'
        self.assertEqual(self.client.operation(operation)['status'], 'CANCELLED')
        self.fixture.status = 'COMPLETED'
        self.client.set_optics({'current_a': 200e-12})
        self.assertEqual(len(self.fixture.commands), 2)

    def test_rejection_cancellation_unknown_are_not_success(self):
        for status in ('REJECTED', 'CANCELLED', 'UNKNOWN'):
            self.fixture.operation_reply = {'operation_id': 'op-test', 'status': status,
                                            'reason': 'fixture', 'observed_at_ns': 120}
            with self.assertRaises(OperationFailure) as caught:
                self.client.wait_operation('op-test', .02)
            self.assertEqual(caught.exception.receipt['status'], status)

    def test_operation_identity_mismatch_refused(self):
        self.fixture.operation_reply = {'operation_id': 'op-other', 'status': 'COMPLETED',
                                        'reason': 'OK', 'observed_at_ns': 120}
        with self.assertRaises(ProtocolError):
            self.client.operation('op-test')

    def test_hidden_or_future_fields_not_forwarded(self):
        self.fixture.state['seed'] = 42
        with self.assertRaises(ProtocolError):
            self.client.state()
        del self.fixture.state['seed']
        self.fixture.state['stage']['ideal_focus'] = 1e-6
        with self.assertRaises(ProtocolError):
            self.client.state()
        del self.fixture.state['stage']['ideal_focus']
        for field, value in (('capabilities', {'specimen_response': {'seed': 42}}),
                             ('applied', {'current_pA': {'seed': 42}, 'focus_offset_m': 0., 'stigmator_x': 0., 'stigmator_y': 0.}),
                             ('phase', {'seed': 42}), ('control_owned', {'seed': 42})):
            original = deepcopy(self.fixture.state)
            self.fixture.state[field] = value
            with self.assertRaises(ProtocolError):
                self.client.state()
            self.fixture.state = original

    def test_uncertain_post_receipt_is_not_a_refusal_or_success(self):
        for response in ((503, {'error': 'service_unavailable'}),
                         (202, {'operation_id': 'wrong/identifier', 'status': 'RECEIVED', 'reason': None, 'observed_at_ns': None})):
            client = Client(self.fixture.origin, 'fixture-only', timeout_s=.5)
            try:
                self.fixture.command_reply = response
                with self.assertRaises(AdmissionUnknown):
                    client.submit_scan(SETTINGS)
                with self.assertRaises(AdmissionUnknown):
                    client.submit_scan(SETTINGS)
            finally:
                client.close()

    def test_stop_needs_new_observed_generation(self):
        self.fixture.confirm_stop = False
        with self.assertRaises(AuthorityError):
            self.client.stop(.025)

    def test_renewal_epoch_change_halts_and_cannot_silently_reacquire(self):
        self.fixture.change_epoch_on_lease = True
        # Exercise the real renewal control path without waiting five seconds.
        # Existing test separately covers the actual periodic renewal thread.
        with patch.object(self.client._halt, 'wait', return_value=False):
            self.client._renew()
        self.assertIsInstance(self.client._renew_error, AuthorityError)
        self.assertEqual(self.fixture.lease_count, 1)
        with self.assertRaises(AuthorityError):
            self.client.acquire_control()
        with self.assertRaises(AuthorityError):
            self.client.set_optics({'current_a': 200e-12})
        self.assertEqual(self.fixture.lease_count, 1)
        self.assertEqual(self.fixture.commands, [])

    def test_stop_works_while_operation_http_is_blocked(self):
        errors = []
        def wait():
            try:
                self.client.wait_operation('op-wait', .1)
            except PendingOutcome:
                pass
            except Exception as error:
                errors.append(error)
        thread = threading.Thread(target=wait)
        thread.start()
        self.assertTrue(self.fixture.block_operation.wait(1.))
        try:
            self.client.stop()
            self.assertFalse(self.fixture.release_operation.is_set())
            self.assertEqual(self.client.state()['stop_generation'], 9)
        finally:
            self.fixture.release_operation.set()
            thread.join(2.)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])

    def test_lease_loss_expiry_competition_and_interlock_fail_honestly(self):
        for changes in ({'control': None}, {'control_owned': False},
                        {'availability': 'QUARANTINED', 'interlock_reason': 'BANK_FAILED'},
                        {'control': {'holder': 'operator-api', 'epoch': 3, 'expires_ns': 110}}):
            original = deepcopy(self.fixture.state)
            self.fixture.state.update(changes)
            with self.assertRaises(AuthorityError):
                self.client.stop()
            self.fixture.state = original
        self.assertEqual(self.fixture.commands, [])

    def test_explicit_lease_acquisition_and_owned_thread_cleanup(self):
        self.client.acquire_control()
        thread = self.client._renew_thread
        self.assertTrue(thread.is_alive())
        self.client.close()
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.fixture.commands, [])

    def test_actual_lease_renewal_during_blocked_normal_write(self):
        self.client.acquire_control()
        self.fixture.status = 'RUNNING'
        result = []
        def write():
            try:
                self.client.set_optics({'focus_offset_m': 2e-6}, timeout_s=7.)
            except (AuthorityError, PendingOutcome):
                pass
            except Exception as error:
                result.append(error)
        thread = threading.Thread(target=write)
        thread.start()
        try:
            deadline = time.monotonic() + 6.5
            while self.fixture.lease_count < 2 and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertGreaterEqual(self.fixture.lease_count, 2)
            self.assertTrue(thread.is_alive())
        finally:
            for record in self.fixture.records.values():
                record['status'] = 'COMPLETED'
            thread.join(2.)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, [])

    def test_image_source_cut_and_raw_identity(self):
        frame = self.client.image('image-42', source_id='raster-7', min_cut_elapsed_ns=90_000_000)
        self.assertEqual(frame.raw, self.fixture.raw)
        for image_id, source_id, cut in (('image-old', 'raster-7', 0),
                                         ('image-42', 'raster-old', 0),
                                         ('image-42', 'raster-7', 90_000_001)):
            with self.assertRaises(ProtocolError):
                self.client.image(image_id, source_id=source_id, min_cut_elapsed_ns=cut)

    def test_no_automatic_newest_image_or_invented_operation_source_link(self):
        with self.assertRaises(QualificationRequired):
            self.client.acquire_image(SETTINGS)
        self.assertEqual(self.fixture.paths, [])
        self.assertEqual(self.fixture.commands, [])


class BoundaryTests(unittest.TestCase):
    def test_core_private_imports_absent_and_no_upstream_execution(self):
        for path in (SOURCE / 'vsem_fibsemos').glob('*.py'):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [item.name for item in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or '']
                else:
                    continue
                self.assertFalse(any(m.split('.')[0] in ('engine', 'runtime', 'evaluator') for m in modules), path)
        self.assertNotIn('fibsem', sys.modules)

    def test_registry_is_lazy_and_bindings_are_not_executed_in_m05a(self):
        self.assertEqual(plugin.QUALIFICATION, 'M05A_source_only')
        self.assertNotIn('vsem_fibsemos.bindings', sys.modules)
        tree = ast.parse((SOURCE / 'vsem_fibsemos/bindings.py').read_text())
        classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
        for name, base in (('VsemMicroscope', 'FibsemMicroscope'),
                           ('VsemBeam', 'Beam'), ('VsemStage', 'Stage')):
            self.assertEqual([ast.unparse(b) for b in classes[name].bases], [base])
        # This is a source-boundary check, not simulated upstream compatibility.
        self.assertNotIn('fibsem', sys.modules)


if __name__ == '__main__':
    unittest.main()
