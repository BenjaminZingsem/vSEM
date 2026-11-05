"""Frontier-owned single-writer reference actor. Public projections are explicit.

This class has no network listener. The runtime owns it in one dedicated process;
all mutation and physical integration happen on that process's actor loop.
"""
import copy
from dataclasses import replace
import datetime
import hashlib
import math
import secrets
import struct
from .timebase import SimulationClock
from .raster_timing import RasterTiming
from .delivery_pacing import delivery_timing
from .reference_physics import AppliedSettings, SpecimenHistory, CURRENT_A, detector_count
from .live_scan import validate_live_envelope, acquired_geometry, MIN_LIVE_WALL_DWELL_S
from packages.contracts.public_support import validate_public, validate_arguments
from packages.contracts.public_schema_data import REGISTRY
from packages.contracts.ui_observable import project_readbacks as ui_projection
from packages.contracts.instrument_observable import project_readbacks as api_projection


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')


class Rejected(ValueError):
    pass


class InstrumentActor:
    def __init__(self, clock=None, seed=None, specimen=None, material=None):
        self.clock = clock or SimulationClock()
        self._seed = secrets.token_bytes(32) if seed is None else seed
        self._settings = AppliedSettings()
        self._history = SpecimenHistory(specimen=specimen,material=material)
        self._revision = 0
        self._now = self.clock.stamp().simulation_s
        self._lease = None
        self._lease_generation = 0
        self._idempotency = {}
        self._operations = {}
        self._pending = []
        self._motion = None
        self._capture = None
        self._captures = 0
        self._images = {}
        self._image_order = []
        self._displayed = None
        self._jobs = []
        self._next_publication = 0.0
        self._last_generation = {}
        self._delivery = {}
        self._live = None
        self._live_ids = set()
        self._freeze_records = {}
        self._completed_live = None

    def lease(self, channel, identity):
        self.advance()
        if channel not in ('ui', 'instrument') or not identity:
            raise Rejected('unauthorized')
        if self._lease and self._lease['expires'] > self._now:
            if (channel, identity) != (self._lease['channel'], self._lease['identity']):
                raise Rejected('control_held')
            self._lease['expires'] = self._now+300
        else:
            self._lease_generation += 1
            self._lease = {'channel': channel, 'identity': identity, 'expires': self._now+300,
                           'token': secrets.token_urlsafe(24), 'generation': self._lease_generation}
        return {'lease_token': self._lease['token'], 'expires_simulation_s': self._lease['expires']}

    def _authorized(self, channel, identity, token, generation=None):
        lease = self._lease
        return (lease is not None and lease['expires'] > self._now
                and lease['channel'] == channel and lease['identity'] == identity
                and secrets.compare_digest(lease['token'], token)
                and (generation is None or lease['generation'] == generation))

    def command(self, channel, identity, envelope):
        self.advance()
        kind = 'ui_intent' if channel == 'ui' else 'instrument_command'
        if channel not in ('ui', 'instrument'):
            raise Rejected('unauthorized')
        value = validate_public(envelope, kind)
        command = value['intent'] if channel == 'ui' else value['command']
        arguments = validate_arguments(command, value['arguments'])
        if not self._authorized(channel, identity, value['lease_token']):
            raise Rejected('lease_required')
        key = (channel, identity, value['intent_id'] if channel=='ui' else value['idempotency_key'])
        if key in self._idempotency:
            old, opid = self._idempotency[key]
            if old != value:
                raise Rejected('idempotency_conflict')
            return copy.deepcopy(self._operations[opid])
        if value['expected_revision'] != self._revision:
            raise Rejected('stale_revision')
        if len(self._operations) >= 4096:
            raise Rejected('session_capacity')
        if command == 'acquire':
            if (arguments['mode'] != 'single' or any(type(arguments[n]) is not int
                    or arguments[n] > 256 for n in ('width_px', 'height_px'))):
                raise Rejected('unsupported_acquisition')
            if self._capture or self._motion:
                raise Rejected('busy')
        if command == 'move_stage_xy' and (self._capture or self._motion):
            raise Rejected('busy')
        if command == 'set_beam_blanked' and not arguments['blanked']:
            raise Rejected('parked_beam_unavailable')
        if command=='set_focus_offset' and abs(arguments['offset_m'])>5e-6:
            raise Rejected('focus_envelope')
        opid = 'operation-'+str(len(self._operations)+1)
        op = {'operation_id': opid, 'command': command, 'state': 'RUNNING',
              'received_simulation_s': self._now, 'completed_simulation_s': None,
              'error': None, 'image_id': None}
        self._operations[opid] = op
        self._idempotency[key] = (copy.deepcopy(value), opid)
        self._revision += 1
        if command == 'acquire':
            self._start_capture(arguments, op)
        elif command in ('stop_scan', 'set_beam_blanked'):
            if self._capture:
                self._finish_capture(self._now, cancelled=True)
            self._complete(op, self._now)
        elif command == 'move_stage_xy':
            distance = math.hypot(arguments['x_m']-self._settings.x_m,
                                  arguments['y_m']-self._settings.y_m)
            self._motion = {'start': self._now, 'end': self._now+distance/0.001,
                            'settled': self._now+distance/0.001+0.08,
                            'initial': self._settings, 'arguments': arguments, 'operation': op,
                            'channel': channel, 'identity': identity, 'token': value['lease_token'],
                            'lease_generation': self._lease['generation']}
        else:
            op['state'] = 'QUEUED'
            self._pending.append({'at': self._now+0.05, 'command': command, 'arguments': arguments,
                                  'operation': op, 'channel': channel, 'identity': identity,
                                  'token': value['lease_token'], 'lease_generation': self._lease['generation']})
        return copy.deepcopy(op)

    def _complete(self, operation, at, state='COMPLETED', error=None):
        operation.update(state=state, completed_simulation_s=at, error=error)
        self._revision += 1

    def live_command(self, channel, identity, envelope):
        try:
            value, command, key_field = validate_live_envelope(channel, envelope)
        except ValueError as exc:
            raise Rejected(str(exc)) from exc
        if command in ('start_live', 'configure_live'):
            stamp = self.clock.stamp()
            if (stamp.mode != 'decision_stepped' and
                    value['arguments']['dwell_s']/stamp.rate < MIN_LIVE_WALL_DWELL_S):
                raise Rejected('unsupported_live_rate')
        self.advance()
        if not self._authorized(channel, identity, value['lease_token']):
            raise Rejected('lease_required')
        key = ('live', channel, identity, value[key_field])
        if key in self._idempotency:
            old, opid = self._idempotency[key]
            if old != value:
                raise Rejected('idempotency_conflict')
            return copy.deepcopy(self._operations[opid])
        if value['expected_revision'] != self._revision:
            raise Rejected('stale_revision')
        if len(self._operations) >= 4096:
            raise Rejected('session_capacity')
        if command == 'start_live':
            if self._capture or self._motion or (self._live and self._live['active']):
                raise Rejected('busy')
        elif not self._live or not self._live['active']:
            raise Rejected('live_not_running')
        if command == 'capture_live' and self._live['id'] not in self._images:
            raise Rejected('live_image_not_ready')
        if command in ('configure_live', 'freeze_live') and self._live and self._live['freeze']:
            raise Rejected('freeze_pending')
        opid = 'operation-'+str(len(self._operations)+1)
        op = {'operation_id': opid, 'command': command, 'state': 'RUNNING',
              'received_simulation_s': self._now, 'completed_simulation_s': None,
              'error': None, 'image_id': None}
        self._operations[opid] = op
        self._idempotency[key] = (copy.deepcopy(value), opid)
        self._revision += 1
        if command == 'start_live':
            self._completed_live = None
            self._captures += 1
            imageid = 'frame-'+str(self._captures)
            self._live_ids.add(imageid)
            op['image_id'] = imageid
            self._live = {'id': imageid, 'operation': op, 'active': True, 'sweep_index': 0,
                          'arguments': copy.deepcopy(value['arguments']),
                          'requested': copy.deepcopy(value['arguments']), 'configurations': [], 'freeze': None}
            self._start_capture(value['arguments'], op, live=self._live, at=self._now)
        elif command == 'configure_live':
            op['state'] = 'QUEUED'
            self._live['requested'] = copy.deepcopy(value['arguments'])
            self._live['configurations'].append((copy.deepcopy(value['arguments']), op))
        elif command == 'capture_live':
            imageid = self._record_live_image(self._images[self._live['id']])
            op['image_id'] = imageid
            self._complete(op, self._now)
        else:
            # Freeze stops at this sweep's physical end, then records its exact
            # final generation when rendering is ready, without extra exposure.
            self._captures += 1
            op['image_id'] = 'frame-'+str(self._captures)
            self._live['freeze'] = op
        return copy.deepcopy(op)

    def _record_live_image(self, source, imageid=None):
        if imageid is None:
            self._captures += 1
            imageid = 'frame-'+str(self._captures)
        image = copy.deepcopy(source)
        image['metadata']['image_id'] = imageid
        self._images[imageid] = image
        self._image_order.append(imageid)
        self._image_order.sort(key=lambda name:int(name.removeprefix('frame-')))
        self._delivery[imageid] = self._delivery.get(source['metadata']['image_id'], 0.0)
        return imageid

    def _start_capture(self, arguments, op, live=None, at=None):
        if live is None:
            self._captures += 1
        start = self._now if at is None else at
        timing = RasterTiming(arguments['width_px'], arguments['height_px'], arguments['dwell_s'],
                              line_flyback_s=0.0001, settling_s=0.02, frame_overhead_s=0.01)
        stamp = self.clock.stamp()
        imageid = 'frame-'+str(self._captures) if live is None else live['id']
        size = timing.width_px*timing.height_px
        wall_start = (stamp.wall_elapsed_s if stamp.mode=='decision_stepped' else
                      stamp.wall_elapsed_s-(stamp.simulation_s-start)/stamp.rate)
        self._capture = {'id': imageid, 'start': start, 'wall_start': wall_start,
                         'timing': timing, 'field': arguments['field_width_m'], 'operation': op,
                         'elapsed': 0.0, 'expectations': [0.0]*size, 'exposures': [0.0]*size,
                         'responses': [None]*size,
                         'settings': self._settings, 'segments': [], 'segment_start': start,
                         'charge': 0.0, 'live': live,
                         'offset_x_m': arguments.get('offset_x_m', 0.0),
                         'offset_y_m': arguments.get('offset_y_m', 0.0),
                         'sweep_index': live['sweep_index'] if live else None}
        op['image_id'] = imageid
        self._next_publication = start+0.2

    def _integrate(self, end):
        capture = self._capture
        if not capture:
            return
        t = capture['timing']
        a, b = capture['elapsed'], min(t.duration_s, max(0.0, end-capture['start']))
        if b <= a:
            return
        settings = capture['settings']
        pixel_m = capture['field']/t.width_px
        for row in range(t.height_px):
            row_start = t.row_start_s(row)
            if row_start >= b or row_start+t.row_exposure_s <= a:
                continue
            for col in range(t.width_px):
                start = max(a, row_start+col*t.dwell_s)
                stop = min(b, row_start+(col+1)*t.dwell_s)
                if stop <= start:
                    continue
                index = row*t.width_px+col
                x = settings.x_m + capture['offset_x_m'] + (col+0.5-t.width_px/2)*pixel_m
                y = settings.y_m + capture['offset_y_m'] - (row+0.5-t.height_px/2)*pixel_m
                if capture['responses'][index] is None:
                    capture['responses'][index] = self._history.response(settings,x,y,capture['start']+start)
                capture['expectations'][index] += self._history.expectation(
                    capture['responses'][index], capture['start']+start, capture['start']+stop)
                capture['exposures'][index] += stop-start
        capture['charge'] += t.charge_C(a, b, CURRENT_A)
        capture['elapsed'] = b

    def _segment(self, end):
        c = self._capture
        if not c or end <= c['segment_start']:
            return
        s = c['settings']
        c['segments'].append({'start_simulation_s': c['segment_start'], 'end_simulation_s': end,
            'focus_offset_m': s.focus_m, 'stigmator_x': s.stig_x, 'stigmator_y': s.stig_y,
            'stage_x_m': s.x_m, 'stage_y_m': s.y_m, 'dwell_s': c['timing'].dwell_s,
            'beam_current_A': CURRENT_A})
        c['segment_start'] = end

    def _publish_job(self, end, final=False):
        c = self._capture
        if not c:
            return
        # Copy actual segments through this endpoint without closing the live one.
        start, segments = c['segment_start'], copy.deepcopy(c['segments'])
        self._segment(end)
        published_segments = copy.deepcopy(c['segments'])
        c['segment_start'], c['segments'] = start, segments
        if not published_segments:  # Cancellation before any elapsed time.
            s = c['settings']
            published_segments = [{'start_simulation_s': end, 'end_simulation_s': end,
                'focus_offset_m': s.focus_m, 'stigmator_x': s.stig_x, 'stigmator_y': s.stig_y,
                'stage_x_m': s.x_m, 'stage_y_m': s.y_m, 'dwell_s': c['timing'].dwell_s,
                'beam_current_A': CURRENT_A}]
        t = c['timing']
        generation = self._last_generation.get(c['id'], -1)+1
        self._last_generation[c['id']] = generation
        rows = t.completed_rows(c['elapsed'])
        scan_id = c['id'] if c['live'] is None else c['id']+'-sweep-'+str(c['sweep_index'])
        meta = {'image_id': c['id'], 'scan_id': scan_id, 'generation': generation,
                'profile_version': REGISTRY['profile'], 'detector': 'SE',
                'raw_unit': 'arbitrary_detector_signal', 'width_px': t.width_px, 'height_px': t.height_px,
                'completed_rows': rows, 'partial': rows < t.height_px,
                'capture_start_simulation_s': c['start'], 'capture_end_simulation_s': end,
                'delivered_at': utc(), 'field_width_m': c['field'],
                'coordinate_transform_id': 'stage-xy-raster-y-up-v1',
                'parameter_segments': published_segments, 'exposure_charge_C': c['charge'],
                'raw_sha256': '0'*64, 'display_lut_id': 'counts-per-second-fixed-1e7-v1',
                'save_status': 'unsaved'}
        validate_public(meta, 'image')
        job = (copy.deepcopy(meta), tuple(c['expectations']), tuple(c['exposures']),
               self._seed, c['wall_start'], final)
        if c['live'] is not None:
            job += (acquired_geometry(c, generation),)
            # Bounded final/periodic lanes preserve completed sweeps independently
            # of newer partial presentation. A terminal partial is a final job.
            self._jobs = [queued for queued in self._jobs
                          if queued[0]['image_id'] != c['id'] or queued[5] != final]
        self._jobs.append(job)
        return generation

    def _finish_capture(self, end, cancelled=False):
        c = self._capture
        if not c:
            return
        actual_end = min(end, c['start']+c['timing'].duration_s)
        self._integrate(actual_end)
        generation = self._publish_job(actual_end, final=True)
        self._capture = None
        live = c['live']
        if live is None:
            self._complete(c['operation'], actual_end, 'CANCELLED' if cancelled else 'COMPLETED')
            return
        if cancelled or live['freeze']:
            live['active'] = False
            self._complete(live['operation'], actual_end, 'CANCELLED' if cancelled else 'COMPLETED')
            for arguments, operation in live['configurations']:
                self._complete(operation, actual_end, 'REJECTED', 'live_stopped')
            live['configurations'] = []
            if live['freeze']:
                operation = live['freeze']
                if cancelled:
                    self._complete(operation, actual_end, 'CANCELLED', 'live_stopped')
                else:
                    operation['state'] = 'SETTLING'
                    self._freeze_records[(c['id'], generation)] = operation
            return
        for arguments, operation in live['configurations']:
            live['arguments'] = arguments
            self._complete(operation, actual_end)
        live['configurations'] = []
        live['sweep_index'] += 1
        self._start_capture(live['arguments'], live['operation'], live=live, at=actual_end)

    def _advance_capture_to(self, endpoint, publish=False):
        while self._capture:
            capture_end = self._capture['start']+self._capture['timing'].duration_s
            if capture_end <= endpoint:
                self._finish_capture(capture_end)
                continue
            self._integrate(endpoint)
            if publish and endpoint >= self._next_publication:
                self._publish_job(endpoint)
                self._next_publication = endpoint+0.2
            break

    def advance(self):
        target = self.clock.stamp().simulation_s
        if target < self._now:
            raise RuntimeError('actor time cannot rewind')
        # Integrate intervals in actual application-time order, even after a long
        # pause. A renderer or observer never determines these boundaries.
        events = [e for e in self._pending if e['at'] <= target]
        if self._lease and self._now < self._lease['expires'] <= target:
            events.append({'at':self._lease['expires'],'expiry':True})
        for event in sorted(events, key=lambda e:e['at']):
            endpoint = event['at']
            self._advance_capture_to(endpoint)
            self._now = endpoint
            if event.get('expiry'):
                if self._capture:
                    operation=self._capture['operation']
                    self._finish_capture(endpoint,cancelled=True)
                    operation['error']='lease_expired'
                if self._motion:
                    m=self._motion
                    fraction=1.0 if m['end']==m['start'] else min(1.0,(endpoint-m['start'])/(m['end']-m['start']))
                    self._settings=replace(self._settings,
                        x_m=m['initial'].x_m+(m['arguments']['x_m']-m['initial'].x_m)*fraction,
                        y_m=m['initial'].y_m+(m['arguments']['y_m']-m['initial'].y_m)*fraction)
                    self._complete(m['operation'],endpoint,'CANCELLED','lease_expired')
                    self._motion=None
                continue
            if not self._authorized(event['channel'], event['identity'], event['token'], event['lease_generation']):
                self._complete(event['operation'], endpoint, 'REJECTED', 'lease_revoked')
            else:
                self._segment(endpoint)
                a = event['arguments']
                self._settings = (replace(self._settings, focus_m=a['offset_m']) if event['command']=='set_focus_offset'
                                  else replace(self._settings, stig_x=a['x'], stig_y=a['y']))
                if self._capture:
                    self._capture['settings'] = self._settings
                    self._capture['responses'] = [None]*len(self._capture['responses'])
                self._complete(event['operation'], endpoint)
            self._pending.remove(event)
        self._now = target
        if self._motion:
            m = self._motion
            fraction = 1.0 if m['end']==m['start'] else min(1.0,(target-m['start'])/(m['end']-m['start']))
            self._settings = replace(self._settings,
                x_m=m['initial'].x_m+(m['arguments']['x_m']-m['initial'].x_m)*fraction,
                y_m=m['initial'].y_m+(m['arguments']['y_m']-m['initial'].y_m)*fraction)
            m['operation']['state'] = 'SETTLING' if target >= m['end'] else 'RUNNING'
            if target >= m['settled']:
                self._complete(m['operation'], m['settled'])
                self._motion = None
        self._advance_capture_to(target, publish=True)

    def take_render_jobs(self):
        jobs, self._jobs = self._jobs, []
        return jobs

    def accept_render(self, result):
        meta, pixels, raw, ready_wall, wall_start = result[:5]
        geometry = result[5] if len(result) == 6 else None
        stamp = self.clock.stamp()
        gate = delivery_timing(mode=stamp.mode,clock_rate=stamp.rate,
            capture_start_simulation_s=meta['capture_start_simulation_s'],
            capture_end_simulation_s=meta['capture_end_simulation_s'],
            capture_start_wall_elapsed_s=wall_start,now_wall_elapsed_s=stamp.wall_elapsed_s,
            now_simulation_s=stamp.simulation_s,render_ready_wall_elapsed_s=ready_wall)
        if not gate.eligible:
            return False
        imageid = meta['image_id']
        meta = copy.deepcopy(meta)
        meta['delivered_at'] = utc()
        validate_public(meta, 'image')
        image = {'metadata': meta, 'pixels': pixels, 'raw': raw}
        if geometry is not None:
            image['geometry'] = copy.deepcopy(geometry)
        reference = self._completed_live
        complete = (self._live and imageid == self._live['id'] and geometry is not None
                    and not meta['partial'] and (reference is None or
                    meta['generation'] > reference['metadata']['generation']))
        if complete:
            self._completed_live = image
        old = self._images.get(imageid)
        if old and old['metadata']['generation'] >= meta['generation']:
            if complete:
                self._revision += 1
            return True
        self._images[imageid] = image
        self._delivery[imageid] = max(0.0, stamp.simulation_s-meta['capture_end_simulation_s'])
        if imageid not in self._image_order and imageid not in self._live_ids:
            self._image_order.append(imageid)
        self._image_order.sort(key=lambda name:int(name.removeprefix('frame-')))
        if self._live and imageid == self._live['id']:
            self._displayed = imageid
        elif self._image_order and (not self._live or not self._live['active']):
            self._displayed = self._image_order[-1]
        freeze = self._freeze_records.pop((imageid, meta['generation']), None)
        if freeze:
            self._record_live_image(self._images[imageid], freeze['image_id'])
            self._complete(freeze, stamp.simulation_s)
            self._displayed = freeze['image_id']
        self._revision += 1
        return True

    def render_failed(self, image_id, generation):
        """Fixed public failure outcome; never retry or restart physical scanning."""
        self.advance()
        if self._capture and self._capture['id'] == image_id:
            operation = self._capture['operation']
            self._finish_capture(self._now, cancelled=True)
            self._complete(operation, self._now, 'FAILED', 'render_failed')
        for key, operation in list(self._freeze_records.items()):
            if key[0] == image_id:
                self._complete(operation, self._now, 'FAILED', 'render_failed')
                del self._freeze_records[key]
        for operation in self._operations.values():
            if operation['image_id'] == image_id and operation['command'] in ('acquire', 'start_live'):
                self._complete(operation, self._now, 'FAILED', 'render_failed')

    def snapshot(self, channel):
        if channel not in ('ui', 'instrument'):
            raise Rejected('unauthorized')
        s = self._settings
        beam_on = (self._capture is not None and any(
            self._capture['timing'].row_start_s(row) <= self._capture['elapsed'] <
            self._capture['timing'].row_start_s(row)+self._capture['timing'].row_exposure_s
            for row in range(self._capture['timing'].height_px)))
        values = {'stage.x_m': s.x_m, 'stage.y_m': s.y_m, 'optics.focus_offset_m': s.focus_m,
                  'optics.stigmator_x': s.stig_x, 'optics.stigmator_y': s.stig_y,
                  'beam.blanked': not beam_on, 'scan.field_width_m': None,
                  'scan.dwell_s': None, 'scan.live': bool(self._live and self._live['active']), 'detector.selected': 'SE'}
        if self._capture:
            values['scan.field_width_m'] = self._capture['field']
            values['scan.dwell_s'] = self._capture['timing'].dwell_s
        elif self._displayed and self._displayed in self._images:
            image = self._images[self._displayed]['metadata']
            values['scan.field_width_m'] = image['field_width_m']
            values['scan.dwell_s'] = image['parameter_segments'][-1]['dwell_s']
        records = [{'field': d['field'], 'value': values[d['field']], 'unit': d['unit'],
                    'observed_at_simulation_s': self._now, 'quality': 'reported' if values[d['field']] is not None else 'unavailable',
                    'reason': None if values[d['field']] is not None else 'sensor_unavailable', 'uncertainty': None}
                   for d in REGISTRY['fields']]
        projection = ui_projection if channel=='ui' else api_projection
        observation = validate_public({'protocol': channel+'.observation.v1', 'instrument_id': 'vSEM-local',
            'episode_id': 'human-reference', 'revision': self._revision, 'simulation_time_s': self._now,
            'time_mode': {'accelerated':'accelerated_continuous'}.get(self.clock.stamp().mode,self.clock.stamp().mode),
            'profile_version': REGISTRY['profile'], 'published_at': utc(), 'displayed_image_id': self._displayed,
            'readbacks': projection(records, REGISTRY)}, channel+'_observation')
        result = {'observation': observation,
                'images': [copy.deepcopy(self._images[i]['metadata']) for i in self._image_order[-100:]],
                'operations': [copy.deepcopy(o) for o in list(self._operations.values())[-32:]],
                'rendering_latency_simulation_s': dict(self._delivery),
                'control': {'holder': self._lease['channel'] if self._lease and self._lease['expires']>self._now else None},
                'capabilities': {'max_raster_px': 256, 'detectors': ['SE'], 'acquisition_modes': ['single','live'],
                                 'stage_axes': ['X','Y'], 'profile_calibrated': False}}
        live = self._live
        image = self._images.get(live['id']) if live else None
        if live is not None:
            result['live_scan'] = {'protocol':'vsem.live-scan.v1', 'active':live['active'],
                'image_id':live['id'], 'sweep_index':live['sweep_index'],
                'geometry':copy.deepcopy(image['geometry']) if image else None,
                'requested_geometry':copy.deepcopy(live['requested']),
                'pending_geometry':copy.deepcopy(live['configurations'][-1][0]) if live['configurations'] else None,
                'scan_operation_id':live['operation']['operation_id']}
        return result

    def image(self, imageid):
        if imageid not in self._images:
            raise Rejected('image_not_found')
        return self._public_image(self._images[imageid])

    def completed_reference(self):
        """Latest delivery-qualified complete live view; no record or exposure."""
        if self._completed_live is None:
            raise Rejected('image_not_found')
        return self._public_image(self._completed_live)

    @staticmethod
    def _public_image(image):
        result = {'metadata': copy.deepcopy(image['metadata']), 'pixels': list(image['pixels']),
                'raw_counts': [item[0] for item in struct.iter_unpack('>I',image['raw'])]}
        if 'geometry' in image:
            result['geometry'] = copy.deepcopy(image['geometry'])
        return result


def render_capture(job, wall_elapsed):
    """Immutable expectations only; no live specimen, clock mutation or dose."""
    meta, expected, exposed, seed, wall_start, final = job[:6]
    counts = tuple(detector_count(seed, meta['scan_id'], i, mean) for i, mean in enumerate(expected))
    raw = b''.join(struct.pack('>I', min(0xffffffff,c)) for c in counts)
    pixels = tuple(min(255, round(count/(duration*1e7)*255)) if duration>0 else 0
                   for count,duration in zip(counts,exposed))
    meta = copy.deepcopy(meta)
    meta['raw_sha256'] = hashlib.sha256(raw).hexdigest()
    result = meta, pixels, raw, wall_elapsed(), wall_start
    return result+(copy.deepcopy(job[6]),) if len(job) == 7 else result
