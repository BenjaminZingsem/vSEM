"""Independent scalar transition certificates for the private human runtime.

Consumes actual ingress/time witnesses and checks ALL emitted facts/dispatch/
snapshot fields. Never imports,instantiates or replays the authoritative owner;
never advances a physical clock, computes an image, or supplies an actor input.
Normative laws are explicit integer exposure, linear XYZ motion, ordered
admission predicates and four-lane reservation accounting. Failure permanently
quarantines this verifier. Only a COMPLETE successful certificate advances its
immutable published cut; retention and trusted ingress remain launcher's duties.
"""
from collections import deque
from dataclasses import dataclass, fields, is_dataclass
import math

from engine import human_episode_types as t
from engine.human_episode_facts import EpisodeFact, EpisodeState
from engine.episode_credits import EpisodeCapacity
from .human_realtime_records import TickBegin, TickEnd

SETTLING = 20_000_000
LINE_RETURN = 100_000
FRAME_RETURN = 10_000_000
APPLICATION_DELAY = 50_000_000
RECORD_LIMIT = 131072
LANES = ('R', 'T', 'A', 'C')


def key(value):
    """Exact binary64/type comparison,including signed zero,for closed records."""
    cls = type(value)
    if cls is float: return (float, value.hex())
    if cls in (str, int, bool, type(None)): return (cls, value)
    if cls is tuple: return (tuple, tuple(key(item) for item in value))
    if is_dataclass(value):
        return (cls, tuple(key(getattr(value, item.name)) for item in fields(value)))
    raise ValueError('Non-scalar certificate value')


def same(a, b): return key(a) == key(b)


def beam_time(config, cursor):
    g = config.geometry; line = g.width_px*config.dwell_ns
    elapsed = max(0, cursor-SETTLING)
    rows, remainder = divmod(elapsed, line+LINE_RETURN)
    return min(g.pixel_count*config.dwell_ns, rows*line+min(line, remainder))


def duration(config):
    g = config.geometry
    return SETTLING+g.pixel_count*config.dwell_ns+(g.height_px-1)*LINE_RETURN+FRAME_RETURN


@dataclass(frozen=True)
class CausalCut:
    tick_id: int
    last_ordinal: int
    physical_sequence: int
    observed_at_ns: int
    state: EpisodeState


class _Budget:
    """Independent counted reservations; no owner-credit algorithm/checkpoints."""
    def __init__(self, capacity):
        self.cap = dict(zip(LANES, (capacity.regular_slots, capacity.terminal_slots,
            capacity.application_slots, capacity.control_slots)))
        self.held = dict.fromkeys(LANES, 0)
        self.outstanding = dict.fromkeys(LANES, 0)
        self.events = deque()
        self.ack = 0

    def free(self, lane): return self.cap[lane]-self.held[lane]-self.outstanding[lane]

    def take(self, lane, count):
        if self.free(lane) < count: return None
        self.held[lane] += count
        return [lane, count]

    def release(self, reservation):
        self.held[reservation[0]] -= reservation[1]
        reservation[1] = 0

    def emit(self, reservation, ordinal):
        if reservation is None or reservation[1] < 1: raise ValueError('Unreserved certificate emission')
        lane = reservation[0]
        reservation[1] -= 1; self.held[lane] -= 1; self.outstanding[lane] += 1
        self.events.append((ordinal, lane))

    def acknowledge(self, ordinal):
        if ordinal <= self.ack: return
        while self.events and self.events[0][0] <= ordinal:
            _, lane = self.events.popleft(); self.outstanding[lane] -= 1
        self.ack = ordinal


class HumanCausalVerifier:
    def __init__(self, science, initial_settings, *, episode_namespace, capacity,
                 stage_x_m=0., stage_y_m=0., stage_z_m=0., custodian_generation=1):
        t.exact(science, t.ScienceIdentity); t.exact(initial_settings, t.EpisodeSettings)
        t.exact(capacity, EpisodeCapacity); t.identity(episode_namespace)
        self.science, self.namespace, self.capacity = science, episode_namespace, capacity
        self.custodian = t.integer(custodian_generation, 1)
        self.pose = (t.real(stage_x_m, -.025, .025), t.real(stage_y_m, -.025, .025),
                     t.real(stage_z_m, -20e-6, 20e-6))
        if abs(initial_settings.focus_offset_m+self.pose[2]) > 25e-6: raise ValueError('Initial defocus envelope')
        self.budget = _Budget(capacity)
        self.emergency = self.budget.take('C', 8)
        self.tick_id = self.now = self.ordinal = self.physical = self.epoch = self.revision = 0
        self.stop_generation = self.session_generation = self.settings_generation = 0
        self.geometry_generation = self.applied_generation = self.job_generation = self.raster_generation = 0
        self.total = self.last_capture_total = 0
        self.applied = initial_settings
        self.lease = self.target = self.session = self.capture = self.motion = self.job = self.bank = None
        self.requested = self.interlock = self.poison = None
        self.operations = set()
        self.cut = None
        self.expected = []

    def _authorized(self, ref, inclusive=False):
        return self.lease is not None and same(ref, self.lease.authority) and (
            self.now <= self.lease.expires_ns if inclusive else self.now < self.lease.expires_ns)

    def _remember(self, op, safety=False):
        if op in self.operations: return 'DUPLICATE_OPERATION'
        if len(self.operations) >= self.capacity.admission_record_slots-(not safety): return 'OPERATION_CAPACITY'
        self.operations.add(op)
        return None

    def _record(self, kind, body, event, reservation, emergency=False):
        self.ordinal += 1
        physical = reservation[0] != 'C'
        if physical: self.physical += 1
        fact = EpisodeFact(self.ordinal, self.ordinal-1, self.now, event, self.namespace,
            reservation[0], emergency, self.physical if physical else None,
            self.physical-1 if physical else None, kind, body)
        self.budget.emit(reservation, self.ordinal)
        self.expected.append(fact)

    def _control(self, kind, body, event=None):
        limits = {'LEASE': 1 if self.emode else 2, 'DISPOSITION': 3, 'TARGET_RETIRED': 1,
            'SESSION_ENDED': 1, 'GEOMETRY': 0 if self.emode else 1, 'INTERLOCK': 1}
        tag = (kind, self.emode)
        self.sites[tag] = self.sites.get(tag, 0)+1
        if self.sites[tag] > limits[kind]: raise ValueError('Certificate control inventory exceeded')
        self._record(kind, body, self.now if event is None else event,
            self.emergency if self.emode else self.creserve, self.emode)

    def _disposition(self, command, reason='OK', status='ACCEPTED'):
        self._control('DISPOSITION', (command.operation_id, status, reason, type(command).__name__))

    def _lease(self, lease, reason, event=None):
        self._control('LEASE', (lease, reason), event)
        self.lease = lease; self.revision += 1

    def _retire(self, reason, keep=False):
        if self.target is None: return None
        self._control('TARGET_RETIRED', (self.target['op'], reason))
        slot = self.target['slot']; self.target = None
        if not keep: self.budget.release(slot)
        return slot

    def _end_session(self, reason):
        if self.session is None: return
        self._control('SESSION_ENDED', (self.session['op'], reason, self.session['freeze']))
        self.session = None

    def _prefix(self, event, reservation):
        c = self.capture; elapsed = event-c['origin']
        if elapsed == c['elapsed']: return
        nominal = c['nominal']+(0 if c['hold'] is not None else elapsed-c['elapsed'])
        charge = (beam_time(c['config'], nominal)-beam_time(c['config'], c['nominal']))*c['handle'].settings.current_pA
        self._record('PREFIX', (c['id'], c['elapsed'], elapsed, c['nominal'], nominal,
            c['hold'] is not None, c['handle'], c['label'], charge, c['total']+charge), event, reservation)
        c['elapsed'], c['nominal'], c['total'] = elapsed, nominal, c['total']+charge
        self.total += charge

    def _hold(self, starting, event, reservation):
        c = self.capture
        if starting:
            if c['hold'] is not None: return
            if c['records'] >= RECORD_LIMIT: raise ValueError('No reserved hold record')
            self._record('HOLD_START', (c['id'], c['elapsed'], c['nominal'], c['label']), event, reservation)
            c['hold'], c['hold_nominal'] = c['elapsed'], c['nominal']; c['records'] += 1
        elif c['hold'] is not None:
            self._record('HOLD_END', (c['id'], c['hold'], c['elapsed'], c['hold_nominal'], c['label']), event, reservation)
            if c['hold'] == c['elapsed']: c['records'] -= 1
            c['hold'] = c['hold_nominal'] = None

    def _end_capture(self, event, reason):
        c = self.capture
        self._hold(False, event, c['terminal'])
        self._record('RASTER_END', (c['id'], c['elapsed'], c['nominal'], c['total'], reason), event, c['terminal'])
        self.ended.append(c['id']); self.last_capture_total = c['total']
        self.budget.release(c['terminal']); self.capture = None
        if reason != 'COMPLETED' or self.session['mode'] == 'SINGLE' or self.session['freeze'] is not None:
            self._end_session(reason)

    def _advance(self, reason=None):
        """Known mechanical deadlines,never solver predictions or new clock ticks."""
        if self.capture is not None:
            c = self.capture
            event = self.now
            if self.lease is not None and (self.lease.expires_ns < event or
                    self.lease.expires_ns == event and reason != 'STOP'):
                event, reason = self.lease.expires_ns, 'EXPIRED'
            completion = None if c['hold'] is not None else c['origin']+c['elapsed']+duration(c['config'])-c['nominal']
            due = self.target['due'] if self.target is not None and self.lease is not None and (
                same(self.target['authority'], self.lease.authority) and self.target['due'] < self.lease.expires_ns) else None
            if completion is not None and (completion < event or completion == event and reason is None):
                if due is None or due >= completion or self.target['ready'] is not None:
                    event, reason = completion, 'COMPLETED'
            reservation = c['terminal'] if reason is not None else self.rreserve
            should_hold = (due is not None and self.target['ready'] is None and c['hold'] is None and
                (due < event or due == event and reason is None) and (completion is None or due < completion))
            if should_hold:
                boundary = max(due, c['origin']+c['elapsed'])
                if c['records'] >= RECORD_LIMIT:
                    self._prefix(boundary, c['terminal']); self._end_capture(boundary, 'CAPTURE_RECORD_LIMIT'); return
                self._prefix(boundary, reservation); self._hold(True, boundary, reservation)
                if reason == 'COMPLETED': event, reason = self.now, self.physical_reason
            self._prefix(event, reservation)
            if reason is not None: self._end_capture(event, reason)
        elif self.motion is not None:
            m = self.motion; event = self.now
            if self.lease is not None and (self.lease.expires_ns < event or
                    self.lease.expires_ns == event and reason != 'STOP'):
                event, reason = self.lease.expires_ns, 'EXPIRED'
            if m['settled'] < event or m['settled'] == event and reason is None: event, reason = m['settled'], 'COMPLETED'
            if event >= m['moving_end'] or m['moving_end'] == m['origin']: pose = m['target']
            else:
                fraction = (event-m['origin'])/(m['moving_end']-m['origin'])
                pose = tuple(a+fraction*(b-a) for a, b in zip(m['start'], m['target']))
            reservation = m['terminal'] if reason is not None else self.rreserve
            if event != m['last']:
                phase = 'SETTLING' if event >= m['moving_end'] else 'MOVING'
                body = (m['op'], *self.pose, *pose, phase) if m['xyz'] else (m['op'], *self.pose[:2], *pose[:2], phase)
                self._record('MOTION_XYZ_ADVANCE' if m['xyz'] else 'MOTION_ADVANCE', body, event, reservation)
                self.pose, m['last'] = pose, event
            if reason is not None:
                body = (m['op'], *self.pose, reason) if m['xyz'] else (m['op'], *self.pose[:2], reason)
                self._record('MOTION_XYZ_END' if m['xyz'] else 'MOTION_END', body, event, reservation)
                self.budget.release(m['terminal']); self.motion = None
                self._control('SESSION_ENDED', (m['op'], reason, None))

    def _interlock(self, reason, physical_reason=None):
        if self.interlock is not None: return
        self.emode = True; self.physical_reason = physical_reason or reason
        self._advance(self.physical_reason)
        self._end_session(reason); self._retire(reason)
        if self.lease is not None:
            expired = self.lease.expires_ns <= self.now
            self._lease(None, 'EXPIRED' if expired else reason, self.lease.expires_ns if expired else None)
        self._control('INTERLOCK', (reason,)); self.interlock = reason

    def _authority_command(self, command):
        if command is None: return
        reason = None
        if self.emode: reason = self.interlock or 'NUMERIC_BACKLOG_CAPACITY'
        elif command.operation_id in self.operations: reason = 'DUPLICATE_OPERATION'
        elif type(command) is t.GrantAuthority:
            if self.lease is not None or command.expires_ns <= self.now: reason = 'CONTROL_HELD'
        elif not self._authorized(command.authority): reason = 'UNAUTHORIZED'
        elif type(command) is t.RenewAuthority and command.expires_ns <= self.now: reason = 'EXPIRED'
        if reason is None: reason = self._remember(command.operation_id)
        if reason:
            self._disposition(command, reason, 'REJECTED'); return
        if type(command) is t.GrantAuthority:
            self.epoch += 1
            self._lease(t.LeaseState(t.AuthorityRef(command.holder_id, self.epoch), command.expires_ns), 'GRANTED')
        elif type(command) is t.RenewAuthority:
            self._lease(t.LeaseState(self.lease.authority, command.expires_ns), 'RENEWED')
        else:
            self._lease(None, 'REVOKED'); self._end_session('REVOKED'); self._retire('REVOKED')
        self._disposition(command)

    def _normal_reason(self, command, stop_valid):
        """Ordered admission predicates,with no effect until every predicate passes."""
        cls = type(command)
        predicates = (
            (self.emode or self.interlock is not None, self.interlock or 'NUMERIC_BACKLOG_CAPACITY'),
            (not self._authorized(command.authority), 'UNAUTHORIZED'),
            (stop_valid, 'STOP'),
            (getattr(command, 'expected_stop_generation', self.stop_generation) != self.stop_generation, 'STOPPED_BEFORE_ADMISSION'),
            (command.operation_id in self.operations, 'DUPLICATE_OPERATION'),
            (cls in (t.StartCapture, t.MoveStage, t.MoveStageXYZ) and (self.session is not None or self.motion is not None), 'BUSY_SESSION'),
            (cls in (t.ConfigureLive, t.FreezeLive) and (self.session is None or self.session['mode'] != 'LIVE'), 'NO_LIVE_SESSION'),
        )
        for failed, reason in predicates:
            if failed: return reason
        if cls is t.FreezeLive:
            if command.live_view_id != self.session['view']: return 'STALE_SOURCE'
            if self.capture is not None and self.capture['config'] != self.session['config']: return 'GEOMETRY_PENDING'
        if cls is t.ConfigureLive and self.session['freeze'] is not None: return 'FREEZE_PENDING'
        if cls in (t.StartCapture, t.ConfigureLive):
            try: config = command.request.bind(*self.pose)
            except ValueError: return 'SOURCE_DOMAIN'
            if cls is t.StartCapture and self.now+APPLICATION_DELAY+duration(config) > t.SAFE_INTEGER: return 'TIME_RANGE'
        if cls is t.SetOptics:
            if not t.same_settings(command.settings, self.applied) and self.now+APPLICATION_DELAY > t.SAFE_INTEGER: return 'TIME_RANGE'
            heights = (self.pose[2],) if self.motion is None else (self.pose[2], self.motion['target'][2])
            if any(abs(command.settings.focus_offset_m+z) > 25e-6 for z in heights): return 'SOURCE_DOMAIN'
            if not t.same_settings(command.settings, self.applied) and self.target is None and self.budget.free('A') < 1:
                return 'NUMERIC_BACKLOG_CAPACITY'
        if cls in (t.MoveStage, t.MoveStageXYZ):
            z = command.z_m if cls is t.MoveStageXYZ else self.pose[2]
            settings = (self.applied,) if self.target is None else (self.applied, self.target['settings'])
            if any(abs(item.focus_offset_m+z) > 25e-6 for item in settings): return 'SOURCE_DOMAIN'
            if self.now+self._motion_ns(command)+80_000_000 > t.SAFE_INTEGER: return 'TIME_RANGE'
        return None

    def _motion_ns(self, command):
        z = command.z_m if type(command) is t.MoveStageXYZ else self.pose[2]
        return math.ceil(max(math.hypot(command.x_m-self.pose[0], command.y_m-self.pose[1])/.001,
                             abs(z-self.pose[2])/.00002)*1e9)

    def _normal_command(self, command, stop_valid):
        if command is None: return
        reason = self._normal_reason(command, stop_valid)
        if reason:
            if reason == 'NUMERIC_BACKLOG_CAPACITY' and not self.emode: self._interlock(reason)
            self._disposition(command, reason, 'REJECTED'); return
        problem = self._remember(command.operation_id)
        if problem:
            self._interlock(problem); self._disposition(command, problem, 'REJECTED'); return
        self.revision += 1; cls = type(command)
        if cls is t.SetOptics:
            equal = t.same_settings(command.settings, self.applied)
            slot = self._retire('TARGET_SUPERSEDED', keep=not equal)
            self.settings_generation += 1
            if equal:
                if self.capture is not None: self._hold(False, self.now, self.rreserve)
                self._disposition(command, status='SATISFIED_NO_CHANGE'); return
            if slot is None: slot = self.budget.take('A', 1)
            if self.capture is not None: config = self.capture['config']
            else:
                old = self.requested
                config = t.ScanConfiguration(t.EpisodeGeometry(1 if old is None else old.geometry.width_px,
                    1 if old is None else old.geometry.height_px, 1e-6 if old is None else old.geometry.field_width_m,
                    self.pose[0], self.pose[1], 0. if old is None else old.geometry.offset_x_m,
                    0. if old is None else old.geometry.offset_y_m, self.pose[2]), 1000 if old is None else old.dwell_ns)
            self.target = {'op': command.operation_id, 'authority': command.authority, 'settings': command.settings,
                'generation': self.settings_generation, 'due': self.now+APPLICATION_DELAY,
                'config': config, 'ready': None, 'slot': slot}
        elif cls in (t.MoveStage, t.MoveStageXYZ):
            terminal = self.budget.take('T', 7)
            if terminal is None:
                self._interlock('NUMERIC_BACKLOG_CAPACITY'); self._disposition(command, 'NUMERIC_BACKLOG_CAPACITY', 'REJECTED'); return
            xyz = cls is t.MoveStageXYZ
            target = (command.x_m, command.y_m, command.z_m if xyz else self.pose[2])
            end = self.now+self._motion_ns(command); settled = end+80_000_000
            body = (command.operation_id, *self.pose, *target, end, settled) if xyz else (
                command.operation_id, *self.pose[:2], *target[:2], end, settled)
            self._record('MOTION_XYZ_START' if xyz else 'MOTION_START', body, self.now, self.rreserve)
            self.motion = {'op': command.operation_id, 'start': self.pose, 'target': target, 'xyz': xyz,
                'origin': self.now, 'moving_end': end, 'settled': settled, 'last': self.now, 'terminal': terminal}
        elif cls is t.FreezeLive:
            self.session['freeze'] = command.operation_id
            if self.capture is None and self.session['sweep'] >= 0: self._end_session('COMPLETED')
        else:
            self.geometry_generation += 1
            config = command.request.bind(*self.pose); self.requested = config
            self._control('GEOMETRY', (command.operation_id, self.geometry_generation, config))
            if cls is t.StartCapture:
                self.session_generation += 1
                self.session = {'op': command.operation_id, 'authority': command.authority,
                    'generation': self.session_generation, 'mode': command.mode, 'config': config,
                    'due': self.now+APPLICATION_DELAY, 'sweep': -1,
                    'view': 'view-'+str(self.session_generation) if command.mode == 'LIVE' else None,
                    'stop': self.stop_generation, 'freeze': None}
            else: self.session['config'] = config
        self._disposition(command)

    def _bank_result(self, result):
        if result is None or self.job is None or not same(result.ticket, self.job): return
        ticket = self.job; self.job = None
        if self.interlock is not None or not self._authorized(ticket.authority): return
        if ticket.purpose == 'SETTINGS':
            valid = self.target is not None and ticket.settings_generation == self.target['generation'] and (
                ticket.request_id == self.target['op'] and same(ticket.settings, self.target['settings']))
            destination = 'target'
        else:
            valid = self.session is not None and ticket.session_generation == self.session['generation'] and (
                ticket.geometry_generation == self.geometry_generation and ticket.applied_generation == self.applied_generation and
                same(ticket.configuration, self.session['config']) and same(ticket.settings, self.applied))
            destination = 'bank'
        if valid and type(result) is t.BankFailed: self._interlock('BANK_FAILED')
        elif valid:
            handle = result.handle
            if handle.source_binding_digest != self.science.solver_source_digest:
                raise ValueError('Unattested scientific source binding')
            if destination == 'target': self.target['ready'] = handle
            else: self.bank = handle

    def _application(self, stop_valid):
        target = self.target
        if (stop_valid or self.interlock is not None or target is None or target['ready'] is None or
                self.now < target['due'] or not self._authorized(target['authority'])): return
        handle = target['ready']; c = self.capture
        if c is not None:
            if c['records'] >= RECORD_LIMIT:
                self._prefix(self.now, c['terminal']); self._end_capture(self.now, 'CAPTURE_RECORD_LIMIT'); c = None
            elif not same(handle.geometry, c['config'].geometry): self._interlock('CAUSAL_FAILURE'); return
        if c is not None: self._hold(False, self.now, self.rreserve)
        self.applied_generation += 1
        self._record('SETTINGS_APPLIED', (target['op'], self.applied, handle.settings, self.applied_generation,
            handle, c['id'] if c else None, c['elapsed'] if c else None), self.now, target['slot'])
        self.budget.release(target['slot'])
        self.applied, self.bank, self.target = handle.settings, handle, None
        self.revision += 1
        if c is not None: c['handle'], c['label'], c['records'] = handle, target['op'], c['records']+1

    def _dispatch(self):
        if self.interlock is not None or self.job is not None: return None
        target, session = self.target, self.session
        if target is not None and target['ready'] is None and self._authorized(target['authority']):
            op, ref, config, settings, due, purpose = (target['op'], target['authority'], target['config'],
                target['settings'], target['due'], 'SETTINGS')
        elif session is not None and self.capture is None and self._authorized(session['authority']):
            config, settings = session['config'], self.applied
            if self.bank is not None and same(self.bank.geometry, config.geometry) and same(self.bank.settings, settings): return None
            op, ref, due, purpose = session['op'], session['authority'], session['due'], 'INITIAL_CAPTURE'
        else: return None
        self.job_generation += 1
        self.job = t.BankTicket('job-'+str(self.job_generation), op, purpose, ref, self.session_generation,
            self.settings_generation, self.geometry_generation, self.applied_generation, self.custodian, self.science, config, settings, due)
        return self.job

    def _start(self, stop_valid):
        s = self.session
        if stop_valid or self.interlock is not None or s is None or self.capture is not None or self.motion is not None: return
        if s['stop'] != self.stop_generation or not self._authorized(s['authority']): self._end_session('STOPPED_BEFORE_ADMISSION'); return
        if s['sweep'] == -1 and self.now < s['due']: return
        if self.target is not None and self.now >= self.target['due']: return
        if self.bank is None or not same(self.bank.geometry, s['config'].geometry) or not same(self.bank.settings, self.applied): return
        terminal = self.budget.take('T', 7)
        if terminal is None or self.rreserve is None or self.rreserve[1] < 1:
            if terminal is not None: self.budget.release(terminal)
            self._interlock('NUMERIC_BACKLOG_CAPACITY'); return
        self.raster_generation += 1; s['sweep'] += 1
        identifier = 'raster-'+str(self.raster_generation)
        self._record('RASTER_START', (identifier, s['generation'], s['sweep'], s['mode'], s['op'], s['view'],
            s['config'], self.bank, 'initial'), self.now, self.rreserve)
        self.capture = {'id': identifier, 'origin': self.now, 'sweep': s['sweep'], 'config': s['config'],
            'handle': self.bank, 'terminal': terminal, 'elapsed': 0, 'nominal': 0, 'total': 0,
            'hold': None, 'hold_nominal': None, 'label': 'initial', 'records': 1}
        self.started.append(identifier); self.last_capture_total = 0

    def _snapshot(self):
        c, s = self.capture, self.session
        phase = ('INTERLOCKED' if self.interlock else 'MOVING' if self.motion else 'CAPTURING' if c else
            'PREPARING' if s and s['sweep'] == -1 else 'BETWEEN_SWEEPS' if s else 'STOPPED')
        blank = not(c is not None and c['hold'] is None and
            beam_time(c['config'], min(c['nominal']+1, duration(c['config']))) > beam_time(c['config'], c['nominal']))
        return EpisodeState(self.now, self.revision, phase, blank, self.applied,
            self.target['settings'] if self.target else None, self.lease, self.stop_generation,
            self.session_generation, self.settings_generation, self.geometry_generation, self.applied_generation,
            c['config'] if c else None, self.requested, c['id'] if c else None, s['view'] if s else None,
            c['sweep'] if c else s['sweep'] if s and s['sweep'] >= 0 else None,
            self.pose[0], self.pose[1], self.ordinal, self.physical, self.budget.ack,
            c['total'] if c else self.last_capture_total, self.total, self.interlock, self.pose[2])

    def _certificate(self, begin):
        self.now = begin.at_ns; inputs = begin.inputs
        self.expected, self.started, self.ended, self.sites = [], [], [], {}
        ack = inputs.verified_ack
        if ack is not None and ack.episode_namespace == self.namespace:
            if ack.last_ordinal > (self.cut.last_ordinal if self.cut else 0): raise ValueError('ACK exceeds complete verified cut')
            self.budget.acknowledge(ack.last_ordinal)
        if self.interlock is not None: return None
        self.rreserve, self.creserve = self.budget.take('R', 6), self.budget.take('C', 10)
        self.emode = False
        stop = inputs.stop
        stop_valid = stop is not None and stop.operation_id not in self.operations and self._authorized(stop.authority, True)
        problem = None
        if stop_valid:
            problem = self._remember(stop.operation_id, True); stop_valid = problem is None
            if stop_valid: self.stop_generation += 1; self.revision += 1
        revoke = inputs.authority
        revoked = (type(revoke) is t.RevokeAuthority and revoke.operation_id not in self.operations and
            self._authorized(revoke.authority) and len(self.operations) < self.capacity.admission_record_slots-1)
        fault = inputs.fault if inputs.fault is not None and inputs.fault.episode_namespace == self.namespace else None
        self.physical_reason = 'STOP' if stop_valid else 'REVOKED' if revoked else None
        if self.rreserve is None or self.creserve is None or fault is not None:
            self._interlock(fault.reason if fault else 'NUMERIC_BACKLOG_CAPACITY', 'STOP' if stop_valid else None)
        elif self.now == t.SAFE_INTEGER: self._interlock('TIME_RANGE', 'STOP' if stop_valid else None)
        else:
            self._advance(self.physical_reason)
            if self.lease is not None and self.lease.expires_ns <= self.now:
                deadline = self.lease.expires_ns
                self._lease(None, 'EXPIRED', deadline); self._end_session('EXPIRED'); self._retire('EXPIRED')
        if stop is not None:
            if stop_valid:
                if not self.emode: self._end_session('STOP')
                self._disposition(stop)
            else:
                reason = problem or self.interlock or ('DUPLICATE_OPERATION' if stop.operation_id in self.operations else 'UNAUTHORIZED')
                self._disposition(stop, reason, 'REJECTED')
        self._authority_command(inputs.authority)
        self._normal_command(inputs.normal, stop_valid)
        self._bank_result(inputs.bank_result)
        self._application(stop_valid)
        dispatch = self._dispatch(); self._start(stop_valid)
        if self.rreserve is not None: self.budget.release(self.rreserve)
        if self.creserve is not None: self.budget.release(self.creserve)
        return dispatch

    def verify(self, begin, facts, end):
        """Only successful whole-service verification advances cut. No ACK here."""
        if self.poison is not None: raise ValueError('Causal verifier quarantined: '+self.poison)
        try:
            t.exact(begin, TickBegin); t.exact(end, TickEnd)
            if type(facts) is not tuple or any(type(f) is not EpisodeFact for f in facts): raise ValueError('Exact complete fact tuple')
            if begin.tick_id != self.tick_id+1 or end.tick_id != begin.tick_id or begin.at_ns < self.now:
                raise ValueError('Missing/backward causal service witness')
            expected_dispatch = self._certificate(begin)
            if not same(facts, tuple(self.expected)): raise ValueError('Causal fact certificate mismatch')
            if not same(end.bank_dispatch, expected_dispatch): raise ValueError('Owned bank dispatch certificate mismatch')
            if not same((end.started, end.ended), (tuple(self.started), tuple(self.ended))): raise ValueError('Raster lifecycle certificate mismatch')
            expected_state = self._snapshot()
            if not same(end.state, expected_state): raise ValueError('Physical state certificate mismatch')
            self.tick_id = begin.tick_id
            self.cut = CausalCut(self.tick_id, self.ordinal, self.physical, self.now, end.state)
            return self.cut
        except Exception as exc:
            self.poison = str(exc)
            raise
