"""Observable-only prototype transport, with independent lease and Stop paths.

One trusted plugin writer per API principal is required. The public API does not
offer compare-and-swap optics or unique client principals. Image return requires
the explicit verified operation/image projection and a fixed count-window policy.
"""
import http.client
import json
import threading
import time
from urllib.parse import urlsplit

from .errors import (AdmissionUnknown, AuthorityError, HTTPFailure, OperationFailure,
                     PendingOutcome, ProtocolError, QualificationRequired)
from .protocol import acquisitions, decode, identity, integer, keys, optics, raster, real, receipt, stage
from .records import RawFrame, MAX_METADATA, MAX_RAW, validate_metadata
from .image_result import AcquisitionResult

TERMINAL = ('COMPLETED', 'REJECTED', 'CANCELLED', 'UNKNOWN')
STATE_FIELDS = ('protocol', 'availability', 'clock_mode', 'retention', 'calibration_status',
                'observed_at_ns', 'delivery_age_ns', 'causal_verified_ordinal',
                'numerical_verified_ordinal', 'phase', 'beam_blank', 'interlock_reason',
                'stage', 'applied', 'requested', 'current_scan', 'requested_scan',
                'stop_generation', 'live_source_id', 'progress', 'episode_incident_pA_ns',
                'control', 'capabilities', 'control_owned', 'latest_image', 'recorded_images')


class Client:
    def __init__(self, origin, token, *, timeout_s=10., poll_s=.1):
        if type(origin) is not str:
            raise ValueError("explicit numeric loopback origin required")
        try:
            url = urlsplit(origin)
            port = url.port
        except ValueError:
            raise ValueError("invalid origin") from None
        if (url.scheme != 'http' or url.hostname != '127.0.0.1' or
                type(port) is not int or not 1 <= port <= 65535 or
                url.username is not None or url.password is not None or
                url.path or url.query or url.fragment or origin != f'http://127.0.0.1:{port}'):
            raise ValueError("explicit numeric loopback origin and port required")
        if type(token) is not str or not 1 <= len(token) <= 512 or any(not 33 <= ord(c) <= 126 for c in token):
            raise ValueError("invalid bearer token")
        self._port, self._token = port, token
        self._timeout = real(timeout_s, .01, 120.)
        self._poll = real(poll_s, .001, 5.)
        self._writes = threading.Lock()
        self._safety = threading.Lock()
        self._halt = threading.Event()
        self._renew_thread = None
        self._renew_error = None
        self._uncertain = False
        self._pending = {}
        self._unresolved = set()
        self._records_lock = threading.Lock()
        self._closed = False
        self._image_window = None
        self._image_pending = {}
        self._lease_operation = None

    def _http(self, path, value=None, *, raw=False, limit=MAX_METADATA):
        if self._closed:
            raise RuntimeError("client closed")
        connection = http.client.HTTPConnection('127.0.0.1', self._port, timeout=self._timeout)
        try:
            headers = {'Authorization': 'Bearer ' + self._token}
            payload = None if value is None else json.dumps(value, allow_nan=False).encode('utf-8')
            if payload is not None:
                headers['Content-Type'] = 'application/json'
            # http.client follows no redirect, proxy or provider chain. Each call
            # owns its connection; a blocked image GET cannot hold the Stop socket.
            connection.request('GET' if value is None else 'POST', path, payload, headers)
            response = connection.getresponse()
            if response.status not in (200, 202):
                raise HTTPFailure(response.status)
            data = response.read(limit + 1)
            if len(data) > limit:
                raise ProtocolError("response exceeds documented envelope")
            return data if raw else decode(data)
        finally:
            connection.close()

    def state(self):
        value = self._http('/state')
        if type(value) is not dict or value.get('protocol') != 'vsem.core-human.v3':
            raise ProtocolError("unqualified state protocol")
        try:
            keys(value, ('protocol', 'availability'), STATE_FIELDS)
            for name in ('applied', 'requested'):
                if value.get(name) is not None:
                    keys(value[name], ('current_pA', 'focus_offset_m', 'stigmator_x', 'stigmator_y'))
            if value.get('stage') is not None:
                keys(value['stage'], ('x_m', 'y_m', 'z_m'), ('working_distance_m', 'z_supported_m'))
            if value.get('control') is not None:
                keys(value['control'], ('holder', 'epoch', 'expires_ns'))
            for name in ('current_scan', 'requested_scan'):
                if value.get(name) is not None:
                    keys(value[name], ('width_px', 'height_px', 'field_width_m', 'pixel_pitch_m',
                                      'magnification', 'magnification_reference_width_m', 'stage_x_m',
                                      'stage_y_m', 'stage_z_m', 'offset_x_m', 'offset_y_m', 'dwell_ns'))
            if value.get('progress') is not None:
                keys(value['progress'], ('completed_pixels', 'total_pixels', 'elapsed_ns', 'nominal_ns', 'source_id'))
            if value.get('capabilities') is not None:
                keys(value['capabilities'], (), ('stage_xyz', 'focus', 'stigmator', 'physical_zoom', 'live_roi',
                                                'native1024', 'detectors', 'field_width_m', 'within_raster_stage',
                                                'specimen_response'))
                for name, item in value['capabilities'].items():
                    if name == 'detectors':
                        if item != ['SE']:
                            raise ValueError("unknown detectors")
                    elif name == 'specimen_response':
                        if item != 'ideal_grounded_reference':
                            raise ValueError("unknown response mode")
                    elif name == 'field_width_m':
                        if type(item) is not list or len(item) != 2:
                            raise ValueError("invalid field limits")
                        real(item[0], 1e-7, .005)
                        real(item[1], item[0], .005)
                    elif type(item) is not bool:
                        raise ValueError("invalid capability flag")
            for name, allowed in (
                    ('availability', ('INITIALIZING', 'AVAILABLE', 'QUARANTINED')),
                    ('clock_mode', ('realtime',)),
                    ('retention', ('buffered_development_not_crash_durable',)),
                    ('calibration_status', ('generic_uncalibrated',)),
                    ('phase', ('STOPPED', 'MOVING', 'CAPTURING', 'PREPARING', 'BETWEEN_SWEEPS', 'INTERLOCKED'))):
                if name in value and value[name] not in allowed:
                    raise ValueError("unknown state mode")
            for name in ('observed_at_ns', 'delivery_age_ns', 'causal_verified_ordinal',
                         'numerical_verified_ordinal', 'stop_generation', 'episode_incident_pA_ns'):
                if name in value:
                    integer(value[name])
            for name in ('beam_blank', 'control_owned'):
                if name in value and type(value[name]) is not bool:
                    raise ValueError("invalid state flag")
            for name in ('live_source_id', 'interlock_reason'):
                if value.get(name) is not None:
                    identity(value[name])
            for name in ('applied', 'requested'):
                if value.get(name) is not None:
                    s = value[name]
                    integer(s['current_pA'], 1, 1000)
                    real(s['focus_offset_m'], -25e-6, 25e-6)
                    real(s['stigmator_x'], -1., 1.)
                    real(s['stigmator_y'], -1., 1.)
            if value.get('stage') is not None:
                s = value['stage']
                for name, limit in (('x_m', .025), ('y_m', .025), ('z_m', 20e-6)):
                    real(s[name], -limit, limit)
                if 'working_distance_m' in s:
                    real(s['working_distance_m'], 0., 1.)
                if 'z_supported_m' in s and s['z_supported_m'] != [-20e-6, 20e-6]:
                    raise ValueError("unqualified Z limits")
            if value.get('control') is not None:
                c = value['control']
                if c['holder'] not in ('human-gui', 'operator-api'):
                    raise ValueError("unknown authority")
                integer(c['epoch'])
                integer(c['expires_ns'])
            for name in ('current_scan', 'requested_scan'):
                if value.get(name) is not None:
                    s = value[name]
                    raster({'width_px': s['width_px'], 'height_px': s['height_px'],
                            'hfw_m': s['field_width_m'], 'dwell_s': s['dwell_ns'] / 1e9,
                            'offset_x_m': s['offset_x_m'], 'offset_y_m': s['offset_y_m']})
                    integer(s['dwell_ns'])
                    for field, limit in (('stage_x_m', .025), ('stage_y_m', .025), ('stage_z_m', 20e-6)):
                        real(s[field], -limit, limit)
                    for field in ('pixel_pitch_m', 'magnification', 'magnification_reference_width_m'):
                        real(s[field], 0., 1e12)
            if value.get('progress') is not None:
                p = value['progress']
                total = integer(p['total_pixels'], 0, 1024**2)
                integer(p['completed_pixels'], 0, total)
                integer(p['elapsed_ns'])
                integer(p['nominal_ns'])
                identity(p['source_id'])
            if value.get('latest_image') is not None:
                validate_metadata(value['latest_image'])
            if 'recorded_images' in value:
                if type(value['recorded_images']) is not list:
                    raise ValueError("invalid image list")
                for image in value['recorded_images']:
                    validate_metadata(image)
        except (ValueError, TypeError):
            raise ProtocolError("state contains unsupported projection fields") from None
        # This is a copy of an actual server observation; it is never updated from
        # command intent. No cached readback fallback exists on network failure.
        return value

    def _authority(self):
        value = self.state()
        control = value.get('control')
        if (value.get('availability') != 'AVAILABLE' or value.get('interlock_reason') is not None or
                value.get('control_owned') is not True or type(control) is not dict or
                control.get('holder') != 'operator-api'):
            raise AuthorityError("API control unavailable or instrument interlocked")
        try:
            integer(value['stop_generation'])
            integer(value['observed_at_ns'])
            integer(value['delivery_age_ns'])
            integer(value['control']['epoch'])
            expires = integer(value['control']['expires_ns'])
            if value['observed_at_ns'] + value['delivery_age_ns'] >= expires:
                raise ValueError("expired observation")
        except (ValueError, KeyError, TypeError):
            raise AuthorityError("no current observed authority") from None
        return value

    def operation(self, operation_id):
        identity(operation_id)
        value = receipt(self._http('/operation/' + operation_id), operation_id)
        with self._records_lock:
            if value['status'] in TERMINAL and value['status'] != 'UNKNOWN':
                self._pending.pop(operation_id, None)
                self._unresolved.discard(operation_id)
            elif value['status'] == 'UNKNOWN':
                self._unresolved.add(operation_id)
        return value

    def wait_operation(self, operation_id, timeout_s=300., *, check_renewal=True):
        identity(operation_id)
        deadline = time.monotonic() + real(timeout_s, .001, 86400.)
        while True:
            if check_renewal and self._renew_error is not None:
                raise AuthorityError("lease renewal failed; outcome requires reconciliation")
            try:
                value = self.operation(operation_id)
            except (OSError, http.client.HTTPException, ProtocolError, HTTPFailure):
                with self._records_lock:
                    self._unresolved.add(operation_id)
                raise PendingOutcome(operation_id) from None
            if value['status'] == 'COMPLETED':
                return value
            if value['status'] in TERMINAL:
                raise OperationFailure(value)
            if time.monotonic() >= deadline:
                with self._records_lock:
                    self._unresolved.add(operation_id)
                raise PendingOutcome(operation_id)
            self._halt.wait(min(self._poll, max(0., deadline - time.monotonic())))
            if self._closed or self._halt.is_set():
                raise RuntimeError("client closed with pending outcome")

    def _admit(self, path, value):
        try:
            result = receipt(self._http(path, value))
        except HTTPFailure as error:
            # These responses are refusal before admission in the qualified API.
            if error.status in (400, 401, 403, 404, 429):
                raise
            self._uncertain = True
            raise AdmissionUnknown("POST outcome unknown; workflow halted") from None
        except (OSError, http.client.HTTPException, ProtocolError, ValueError):
            self._uncertain = True
            raise AdmissionUnknown("POST outcome unknown; workflow halted") from None
        with self._records_lock:
            self._pending[result['operation_id']] = value.get('action', 'lease')
            if path == '/lease':
                self._lease_operation = result['operation_id']
        return result

    def acquire_control(self, timeout_s=20.):
        timeout_s = real(timeout_s, .001, 86400.)
        with self._writes:
            if self._uncertain:
                raise AdmissionUnknown("unreconciled admission; no automatic reacquisition")
            if self._renew_error is not None:
                raise AuthorityError("renewal failed; explicit session reconciliation required")
            if self._renew_thread is not None:
                self._authority()
                return None
            result = self._admit('/lease', {})
            self.wait_operation(result['operation_id'], timeout_s, check_renewal=False)
            self._authority()
            if self._renew_thread is not None:
                return result
            self._renew_error = None
            self._renew_thread = threading.Thread(target=self._renew, name='vsem-plugin-lease', daemon=True)
            self._renew_thread.start()
            return result

    def _renew(self):
        while not self._halt.wait(5.):
            try:
                self._renew_once()
            except Exception as error:
                self._renew_error = error
                return

    def _renew_once(self):
        # /lease is acquire-or-renew, not compare-and-swap. A grant can race an
        # expiry between these reads; detect an epoch change and halt rather than
        # silently treating a new authority as continuation of the old one.
        before = self._authority()
        result = self._admit('/lease', {})
        self.wait_operation(result['operation_id'], 20., check_renewal=False)
        after = self._authority()
        if after['control']['epoch'] != before['control']['epoch']:
            raise AuthorityError("lease epoch changed during renewal; workflow halted")

    def _ready(self):
        if self._uncertain:
            raise AdmissionUnknown("unreconciled admission; workflow halted")
        if self._renew_error is not None:
            raise AuthorityError("lease renewal failed")
        with self._records_lock:
            if self._unresolved:
                raise PendingOutcome(sorted(self._unresolved)[0])
        return self._authority()

    def _command(self, action, parameters, state):
        return self._admit('/command', {'action': action, 'parameters': parameters,
                                      'expected_stop_generation': state['stop_generation']})

    def set_optics(self, changes, timeout_s=300.):
        timeout_s = real(timeout_s, .001, 86400.)
        # Validate the WHOLE patch before state reads, lease changes or writes.
        keys(changes, (), ('current_a', 'focus_offset_m', 'stigmator_x', 'stigmator_y'))
        if not changes:
            raise ValueError("empty optics patch")
        # Validate supplied fields independent of the observed base.
        optics({'current_a': 100e-12, 'focus_offset_m': 0., 'stigmator_x': 0.,
                'stigmator_y': 0., **changes})
        with self._writes:
            base = self._ready()
            applied = base['applied']
            if base.get('requested') is not None:
                raise AuthorityError("unapplied optics request; wait for coherent base")
            merged = {'current_a': applied['current_pA'] / 1e12,
                      **{k: applied[k] for k in ('focus_offset_m', 'stigmator_x', 'stigmator_y')}, **changes}
            parameters = optics(merged)
            real(parameters['focus_offset_m'] + base['stage']['z_m'], -25e-6, 25e-6)
            current = self._authority()
            if any(current.get(k) != base.get(k) for k in ('applied', 'requested', 'stage', 'control', 'stop_generation')):
                raise AuthorityError("observed base changed; no stale overwrite")
            result = self._command('optics', parameters, current)
            return self.wait_operation(result['operation_id'], timeout_s)

    def move_stage(self, position, timeout_s=300.):
        timeout_s = real(timeout_s, .001, 86400.)
        parameters = stage(position)
        with self._writes:
            state = self._ready()
            if state.get('requested') is not None:
                raise AuthorityError("unapplied optics request")
            real(parameters['z_m'] + state['applied']['focus_offset_m'], -25e-6, 25e-6)
            result = self._command('stage_move', parameters, state)
            return self.wait_operation(result['operation_id'], timeout_s)

    def submit_scan(self, settings, mode='SINGLE'):
        parameters = raster(settings)
        if mode not in ('SINGLE', 'LIVE', 'CONFIGURE_LIVE'):
            raise ValueError("unsupported scan mode")
        with self._writes:
            state = self._ready()
            with self._records_lock:
                scans = [op for op, action in self._pending.items() if action in ('scan_single', 'scan_live')]
                scans += list(self._image_pending)
            if scans and mode != 'CONFIGURE_LIVE':
                raise PendingOutcome(scans[0])
            return self._command({'SINGLE': 'scan_single', 'LIVE': 'scan_live',
                                  'CONFIGURE_LIVE': 'configure_live'}[mode], parameters, state)

    def freeze(self, source_id):
        identity(source_id)
        # A running live session is a valid pending operation. Freeze is a separate
        # receipt and may proceed while the start receipt is still RUNNING.
        with self._writes:
            if self._uncertain or self._renew_error:
                raise AuthorityError("control outcome uncertain")
            state = self._authority()
            if state.get('live_source_id') != source_id:
                raise ValueError("source is not the observed current live session")
            return self._command('freeze', {'source_id': source_id}, state)

    def stop(self, timeout_s=20.):
        timeout_s = real(timeout_s, .001, 86400.)
        with self._safety:
            deadline = time.monotonic() + timeout_s
            before = self._authority()
            result = self._command('stop', {}, before)
            completed = self.wait_operation(result['operation_id'], timeout_s, check_renewal=False)
            while True:
                after = self.state()
                if after.get('availability') != 'AVAILABLE' or after.get('interlock_reason') is not None:
                    raise AuthorityError("Stop unconfirmed after interlock or unavailable observation")
                if type(after.get('stop_generation')) is int and after['stop_generation'] > before['stop_generation']:
                    break
                if time.monotonic() >= deadline or self._halt.wait(self._poll):
                    raise AuthorityError("Stop receipt lacks observed generation confirmation")
            # A confirmed Stop does not retroactively resolve an unknown earlier
            # admission or rewrite its receipt. Known pending IDs remain available.
            return completed

    def image(self, image_id, *, source_id, min_cut_elapsed_ns=0):
        identity(image_id)
        identity(source_id)
        integer(min_cut_elapsed_ns)
        metadata = self._http('/image/' + image_id)
        if (type(metadata) is not dict or metadata.get('image_id') != image_id or
                metadata.get('source_id') != source_id or
                type(metadata.get('cut_elapsed_ns')) is not int or metadata['cut_elapsed_ns'] < min_cut_elapsed_ns):
            raise ProtocolError("image/source/cut mismatch")
        raw = self._http('/image/' + image_id + '/SE', raw=True, limit=MAX_RAW)
        return RawFrame.from_observation(raw, metadata)

    def configure_image_return(self, black, white):
        integer(black, 0, 2**32-1)
        integer(white, black+1, 2**32-1)
        with self._writes:
            if self._image_window is not None:
                raise RuntimeError('image return policy is single-use configuration')
            self._image_window = (black, white)

    def acquisitions(self, operation_id, expected_command=None):
        identity(operation_id)
        return acquisitions(self._http('/operation/'+operation_id+'/acquisitions'),
                            operation_id, expected_command)

    def acquire_image(self, settings, timeout_s=300.):
        parameters = raster(settings)
        timeout_s = real(timeout_s, .001, 86400.)
        with self._writes:
            if self._image_window is None:
                raise QualificationRequired('Configure the fixed raw-count window explicitly before image acquisition')
            before = self._ready()
            with self._records_lock:
                pending = list(self._image_pending)
                pending += [op for op, action in self._pending.items() if action in ('scan_single', 'scan_live')]
                lease = self._lease_operation
            if pending:
                raise PendingOutcome(pending[0])
            if lease is None:
                raise AuthorityError('known lease operation required before image acquisition')
            try:
                probe = self.acquisitions(lease, 'lease')
            except HTTPFailure as error:
                if error.status == 404:
                    raise QualificationRequired('server lacks public operation/image association') from None
                raise
            if any(probe[key] is not None for key in ('association', 'latest_cut', 'final_cut')):
                raise ProtocolError('lease falsely claims an acquisition')
            current = self._authority()
            if current['control']['epoch'] != before['control']['epoch']:
                raise AuthorityError('lease epoch changed before image admission')
            result = self._command('scan_single', parameters, current)
            with self._records_lock:
                self._image_pending[result['operation_id']] = (dict(parameters), self._image_window)
        # No write/safety lock is held during image delivery or reconciliation.
        return self.reconcile_image(result['operation_id'], timeout_s)

    def reconcile_image(self, operation_id, timeout_s=300., *, settings=None):
        identity(operation_id)
        timeout_s = real(timeout_s, .001, 86400.)
        with self._records_lock:
            pending = self._image_pending.get(operation_id)
        if pending is None:
            raise ValueError('no retained image request for this operation')
        parameters, window = pending
        if settings is not None and raster(settings) != parameters:
            raise ValueError('reconciliation settings differ from the admitted request')
        deadline = time.monotonic()+timeout_s
        while True:
            if self._renew_error is not None:
                with self._records_lock:
                    self._unresolved.add(operation_id)
                raise AuthorityError('lease renewal failed; image operation pending: '+operation_id)
            try:
                self._authority()
                value = self.acquisitions(operation_id, 'scan_single')
                observed = value['receipt']
                with self._records_lock:
                    if observed['status'] in TERMINAL and observed['status'] != 'UNKNOWN':
                        self._pending.pop(operation_id, None)
                    if observed['status'] == 'UNKNOWN':
                        self._unresolved.add(operation_id)
                if observed['status'] in ('REJECTED', 'CANCELLED', 'UNKNOWN'):
                    if observed['status'] != 'UNKNOWN':
                        with self._records_lock:
                            self._image_pending.pop(operation_id, None)
                            self._unresolved.discard(operation_id)
                    raise OperationFailure(observed)
                cut = value['final_cut']
                if observed['status'] == 'COMPLETED' and cut is not None:
                    frame = self.image(cut['image_id'], source_id=cut['source_id'],
                                       min_cut_elapsed_ns=cut['cut_elapsed_ns'])
                    result = AcquisitionResult.from_acquisition(frame, value, *window, parameters)
                    with self._records_lock:
                        self._image_pending.pop(operation_id, None)
                        self._unresolved.discard(operation_id)
                    return result
            except (OSError, http.client.HTTPException, ProtocolError, HTTPFailure, ValueError, KeyError):
                with self._records_lock:
                    self._unresolved.add(operation_id)
                raise PendingOutcome(operation_id) from None
            if time.monotonic() >= deadline or self._halt.wait(self._poll):
                with self._records_lock:
                    self._unresolved.add(operation_id)
                raise PendingOutcome(operation_id)

    def close(self):
        # Disconnect is not Stop; caller must explicitly confirm Stop first.
        self._halt.set()
        if self._renew_thread is not None:
            self._renew_thread.join(2 * self._timeout + 2.)
            if self._renew_thread.is_alive():
                raise RuntimeError("lease thread still running; client not closed")
        self._closed = True
        self._token = ''
