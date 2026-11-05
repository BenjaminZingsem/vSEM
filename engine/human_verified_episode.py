"""Verified-admission scalar causal owner; no NumPy,source,bank graph,count or transport import.

Private representational kernel. Runtime/resource/scientific activation needs
independent numerical,process,transport and visual acceptance.
"""
import math
from .human_episode_types import (SAFE_INTEGER, MINIMUM_APPLICATION_NS, ScienceIdentity,
    EpisodeSettings, EpisodeGeometry, ScanConfiguration, AuthorityRef, LeaseState, GrantAuthority,
    RenewAuthority, RevokeAuthority, StartCapture, ConfigureLive, SetOptics,
    MoveStage, MoveStageXYZ, MAX_STAGE_Z_M, SafetyStop, FreezeLive, BankTicket, BankReady, BankFailed,
    EpisodeInputs, integer, exact, identity, same_settings)
from .episode_credits import (EpisodeCapacity, EpisodeCredits, CONTROL_SITES,
    REGULAR_PHYSICAL_RESERVE, TERMINAL_PHYSICAL_RESERVE, APPLICATION_RESERVE,
    REGULAR_CONTROL_RESERVE, EMERGENCY_CONTROL_RESERVE)
from .episode_raster import RasterPlan
from .human_episode_facts import EpisodeFact, EpisodeState, EpisodeTickResult

RECORD_LIMIT = 131072


def active_prefix(plan, cursor):
    if cursor <= plan.settling_ns:
        return 0
    if cursor >= plan.raster_end_ns:
        return plan.pixel_count*plan.dwell_ns
    row, offset = divmod(cursor-plan.settling_ns,
                         plan.width_px*plan.dwell_ns+plan.line_flyback_ns)
    return row*plan.width_px*plan.dwell_ns+min(offset, plan.width_px*plan.dwell_ns)


class _Capture:
    def __init__(self, identifier, session, origin, configuration, handle, terminal):
        self.identity, self.origin = identifier, origin
        self.session_generation, self.sweep = session['generation'], session['sweep']
        self.configuration, self.handle, self.terminal = configuration, handle, terminal
        self.plan = RasterPlan(configuration.geometry.width_px, configuration.geometry.height_px,
                               configuration.dwell_ns)
        self.elapsed = self.nominal = self.incident = 0
        self.hold = self.hold_cursor = None
        self.label = 'initial'
        self.records = 1


class GroundedEpisode:
    def __init__(self, science, initial_settings, *, episode_namespace, capacity,
                 stage_x_m=0.0, stage_y_m=0.0, stage_z_m=0.0, custodian_generation=1):
        exact(science, ScienceIdentity); exact(initial_settings, EpisodeSettings)
        exact(capacity, EpisodeCapacity); identity(episode_namespace)
        integer(custodian_generation, 1)
        # A motion request uses exactly the existing +/-25mm human envelope.
        from .human_episode_types import real
        self.stage_x = real(stage_x_m, -.025, .025)
        self.stage_y = real(stage_y_m, -.025, .025)
        self.stage_z = real(stage_z_m, -MAX_STAGE_Z_M, MAX_STAGE_Z_M)
        if abs(initial_settings.focus_offset_m+self.stage_z) > 25e-6:
            raise ValueError('initial combined Z/lens defocus outside qualified envelope')
        self.science, self.episode, self.capacity = science, episode_namespace, capacity
        self.custodian_generation = custodian_generation
        self.credits = EpisodeCredits(capacity)
        self.emergency = self.credits.reserve('C', EMERGENCY_CONTROL_RESERVE)
        self.now = self.epoch = self.revision = self.stop_generation = 0
        self.session_generation = self.settings_generation = self.geometry_generation = 0
        self.applied_generation = self.job_generation = self.capture_generation = 0
        self.physical_sequence = self.total = self.last_capture_incident = 0
        self.applied = initial_settings
        self.lease = self.session = self.capture = self.motion = self.pending = self.job = None
        self.bank = None
        self.requested = None
        self.interlock = None
        self.ops = set()
        self._facts = []; self._starts = []; self._ends = []
        self._r = self._c = None
        self._sites = {}
        self._emergency_mode = False

    def _authorized(self, reference, *, stop=False):
        return (self.lease is not None and reference == self.lease.authority and
                (self.now <= self.lease.expires_ns if stop else self.now < self.lease.expires_ns))

    def _remember(self, op, *, safety=False):
        if op in self.ops:
            return 'DUPLICATE_OPERATION'
        limit = self.capacity.admission_record_slots-(0 if safety else 1)
        if len(self.ops) >= limit:
            return 'OPERATION_CAPACITY'
        self.ops.add(op)
        return None

    def _emit(self, kind, body, at, reservation, *, emergency=False):
        if reservation is None or reservation.remaining <= 0:
            raise RuntimeError('physical mutation has no prior reserved fact credit')
        physical = reservation.lane != 'C'
        next_physical = self.physical_sequence+1 if physical else None
        ordinal = self.credits.ordinal+1
        fact = EpisodeFact(ordinal, ordinal-1, self.now, at, self.episode,
            reservation.lane, emergency, next_physical,
            self.physical_sequence if physical else None, kind, body)
        if self.credits.emit(reservation) != ordinal:
            raise RuntimeError('scalar fact ordinal differs from its credit checkpoint')
        if physical:
            self.physical_sequence = next_physical
        self._facts.append(fact)

    def _control(self, site, kind, body, *, at=None):
        key = (site, self._emergency_mode)
        count = self._sites.get(key, 0)+1
        limits = {name: (emergency if self._emergency_mode else normal)
                  for name, normal, emergency in CONTROL_SITES}
        if site not in limits or count > limits[site]:
            raise RuntimeError('unfrozen control emission site or multiplicity')
        self._sites[key] = count
        self._emit(kind, body, self.now if at is None else at,
                   self.emergency if self._emergency_mode else self._c,
                   emergency=self._emergency_mode)

    def _disposition(self, intent, status, reason):
        self._control('disposition', 'DISPOSITION',
                      (intent.operation_id, status, reason, type(intent).__name__))

    def _retire_target(self, reason, *, keep_slot=False):
        pending = self.pending
        if pending is None:
            return None
        self._control('target_retired', 'TARGET_RETIRED', (pending['op'], reason))
        self.pending = None
        if not keep_slot:
            self.credits.release(pending['slot'])
        return pending['slot']

    def _end_session(self, reason):
        if self.session is None:
            return
        self._control('session_ended', 'SESSION_ENDED',
                      (self.session['op'], reason, self.session['freeze']))
        self.session = None

    def _lease_changed(self, state, reason, at=None):
        self._control('lease_changed', 'LEASE', (state, reason), at=at)
        self.lease = state
        self.revision += 1

    def _advance_capture(self, capture, at, reservation):
        elapsed = at-capture.origin
        if elapsed == capture.elapsed:
            return
        old_elapsed, old_nominal = capture.elapsed, capture.nominal
        nominal = old_nominal if capture.hold is not None else old_nominal+elapsed-old_elapsed
        delta = (active_prefix(capture.plan, nominal)-active_prefix(capture.plan, old_nominal))*capture.handle.settings.current_pA
        total = capture.incident+delta
        self._emit('PREFIX', (capture.identity, old_elapsed, elapsed, old_nominal,
            nominal, capture.hold is not None, capture.handle, capture.label, delta, total), at, reservation)
        capture.elapsed, capture.nominal, capture.incident = elapsed, nominal, total
        self.total += delta

    def _hold_start(self, capture, at, reservation):
        if capture.hold is not None:
            return
        if capture.records >= RECORD_LIMIT:
            raise RuntimeError('hold record reservation not checked before progression')
        self._emit('HOLD_START', (capture.identity, capture.elapsed, capture.nominal, capture.label), at, reservation)
        capture.hold, capture.hold_cursor = capture.elapsed, capture.nominal
        capture.records += 1

    def _hold_end(self, capture, at, reservation):
        if capture.hold is None:
            return
        self._emit('HOLD_END', (capture.identity, capture.hold, capture.elapsed,
            capture.hold_cursor, capture.label), at, reservation)
        if capture.hold == capture.elapsed:
            capture.records -= 1
        capture.hold = capture.hold_cursor = None

    def _end_capture(self, capture, at, reason):
        self._hold_end(capture, at, capture.terminal)
        self._emit('RASTER_END', (capture.identity, capture.elapsed, capture.nominal,
            capture.incident, reason), at, capture.terminal)
        self._ends.append(capture.identity)
        self.last_capture_incident = capture.incident
        self.credits.release(capture.terminal)
        self.capture = None
        if reason != 'COMPLETED' or self.session['mode'] == 'SINGLE' or self.session['freeze'] is not None:
            self._end_session(reason)

    def _progress_capture(self, terminal_reason):
        capture = self.capture
        if capture is None:
            return
        cut, reason = self.now, terminal_reason
        expiry = self.lease.expires_ns if self.lease else None
        if expiry is not None and (expiry < cut or (expiry == cut and reason != 'STOP')):
            cut, reason = expiry, 'EXPIRED'
        completion = (capture.origin+capture.elapsed+capture.plan.program_end_ns-capture.nominal
                      if capture.hold is None else None)
        pending = self.pending
        due = pending['due'] if pending is not None and self.lease is not None and (
            pending['authority'] == self.lease.authority and pending['due'] < self.lease.expires_ns) else None
        if completion is not None and (completion < cut or (completion == cut and reason is None)):
            if due is None or due >= completion or pending['ready'] is not None:
                cut, reason = completion, 'COMPLETED'
        lane = capture.terminal if reason is not None else self._r
        if (due is not None and pending['ready'] is None and capture.hold is None
                and due <= cut and (due < cut or reason is None)
                and (completion is None or due < completion)):
            boundary = max(due, capture.origin+capture.elapsed)
            if capture.records >= RECORD_LIMIT:
                self._advance_capture(capture, boundary, capture.terminal)
                self._end_capture(capture, boundary, 'CAPTURE_RECORD_LIMIT')
                return
            self._advance_capture(capture, boundary, lane)
            self._hold_start(capture, boundary, lane)
            if reason == 'COMPLETED':
                cut, reason = self.now, terminal_reason
        self._advance_capture(capture, cut, lane)
        if reason is not None:
            self._end_capture(capture, cut, reason)

    def _progress_motion(self, terminal_reason):
        motion = self.motion
        if motion is None:
            return
        cut, reason = self.now, terminal_reason
        expiry = self.lease.expires_ns if self.lease else None
        if expiry is not None and (expiry < cut or (expiry == cut and reason != 'STOP')):
            cut, reason = expiry, 'EXPIRED'
        if motion['settled'] < cut or (motion['settled'] == cut and reason is None):
            cut, reason = motion['settled'], 'COMPLETED'
        if motion['moving_end'] == motion['start'] or cut >= motion['moving_end']:
            x, y = motion['x'], motion['y']
            z = motion['z']
        else:
            fraction = (cut-motion['start'])/(motion['moving_end']-motion['start'])
            x = motion['x0']+fraction*(motion['x']-motion['x0'])
            y = motion['y0']+fraction*(motion['y']-motion['y0'])
            z = motion['z0']+fraction*(motion['z']-motion['z0'])
        lane = motion['terminal'] if reason is not None else self._r
        if cut != motion['last']:
            phase = 'SETTLING' if cut >= motion['moving_end'] else 'MOVING'
            if motion['xyz']:
                self._emit('MOTION_XYZ_ADVANCE', (motion['op'], self.stage_x, self.stage_y,
                    self.stage_z, x, y, z, phase), cut, lane)
            else:
                self._emit('MOTION_ADVANCE', (motion['op'], self.stage_x, self.stage_y, x, y, phase), cut, lane)
            self.stage_x, self.stage_y, motion['last'] = x, y, cut
            self.stage_z = z
        if reason is not None:
            if motion['xyz']:
                self._emit('MOTION_XYZ_END', (motion['op'], self.stage_x, self.stage_y, self.stage_z, reason), cut, lane)
            else:
                self._emit('MOTION_END', (motion['op'], self.stage_x, self.stage_y, reason), cut, lane)
            self.credits.release(motion['terminal'])
            self.motion = None
            self._control('session_ended', 'SESSION_ENDED', (motion['op'], reason, None))

    def _terminal(self, reason, *, physical_reason=None):
        if self.interlock is not None:
            return
        self._emergency_mode = True
        self._progress_capture(physical_reason or reason); self._progress_motion(physical_reason or reason)
        self._end_session(reason)
        self._retire_target(reason)
        if self.lease is not None:
            expired = self.lease.expires_ns <= self.now
            self._lease_changed(None, 'EXPIRED' if expired else reason,
                                self.lease.expires_ns if expired else None)
        self._control('interlock_latched', 'INTERLOCK', (reason,))
        self.interlock = reason

    def _authority(self, intent):
        if intent is None:
            return
        if self._emergency_mode:
            self._disposition(intent, 'REJECTED', self.interlock or 'NUMERIC_BACKLOG_CAPACITY')
            return
        if intent.operation_id in self.ops:
            self._disposition(intent, 'REJECTED', 'DUPLICATE_OPERATION')
            return
        if type(intent) is GrantAuthority:
            if self.lease is not None or intent.expires_ns <= self.now:
                self._disposition(intent, 'REJECTED', 'CONTROL_HELD')
                return
        elif not self._authorized(intent.authority):
            self._disposition(intent, 'REJECTED', 'UNAUTHORIZED')
            return
        elif type(intent) is RenewAuthority and intent.expires_ns <= self.now:
            self._disposition(intent, 'REJECTED', 'EXPIRED')
            return
        problem = self._remember(intent.operation_id)
        if problem is not None:
            self._disposition(intent, 'REJECTED', problem)
            return
        if type(intent) is GrantAuthority:
            self.epoch += 1
            self._lease_changed(LeaseState(AuthorityRef(intent.holder_id, self.epoch), intent.expires_ns), 'GRANTED')
        elif type(intent) is RenewAuthority:
            self._lease_changed(LeaseState(self.lease.authority, intent.expires_ns), 'RENEWED')
        else:
            self._lease_changed(None, 'REVOKED')
            self._end_session('REVOKED'); self._retire_target('REVOKED')
        self._disposition(intent, 'ACCEPTED', 'OK')

    def _normal(self, intent, stop_valid):
        if intent is None:
            return
        if self._emergency_mode or self.interlock is not None:
            self._disposition(intent, 'REJECTED', self.interlock or 'NUMERIC_BACKLOG_CAPACITY')
            return
        if not self._authorized(intent.authority):
            self._disposition(intent, 'REJECTED', 'UNAUTHORIZED')
            return
        if stop_valid:
            self._disposition(intent, 'REJECTED', 'STOP')
            return
        if hasattr(intent, 'expected_stop_generation') and intent.expected_stop_generation != self.stop_generation:
            self._disposition(intent, 'REJECTED', 'STOPPED_BEFORE_ADMISSION')
            return
        if intent.operation_id in self.ops:
            self._disposition(intent, 'REJECTED', 'DUPLICATE_OPERATION')
            return
        if type(intent) in (StartCapture, MoveStage, MoveStageXYZ) and (self.session is not None or self.motion is not None):
            self._disposition(intent, 'REJECTED', 'BUSY_SESSION')
            return
        if type(intent) in (ConfigureLive, FreezeLive) and (
                self.session is None or self.session['mode'] != 'LIVE'):
            self._disposition(intent, 'REJECTED', 'NO_LIVE_SESSION')
            return
        if type(intent) is FreezeLive and intent.live_view_id != self.session['view']:
            self._disposition(intent, 'REJECTED', 'STALE_SOURCE')
            return
        if type(intent) is ConfigureLive and self.session['freeze'] is not None:
            self._disposition(intent, 'REJECTED', 'FREEZE_PENDING')
            return
        if type(intent) is FreezeLive and self.capture is not None and (
                self.capture.configuration != self.session['configuration']):
            self._disposition(intent, 'REJECTED', 'GEOMETRY_PENDING')
            return
        configuration = None
        if type(intent) in (StartCapture, ConfigureLive):
            try:
                configuration = intent.request.bind(self.stage_x, self.stage_y, self.stage_z)
            except ValueError:
                self._disposition(intent, 'REJECTED', 'SOURCE_DOMAIN')
                return
        if type(intent) is StartCapture:
            plan = RasterPlan(configuration.geometry.width_px, configuration.geometry.height_px, configuration.dwell_ns)
            if self.now+MINIMUM_APPLICATION_NS+plan.program_end_ns > SAFE_INTEGER:
                self._disposition(intent, 'REJECTED', 'TIME_RANGE')
                return
        if type(intent) is SetOptics and not same_settings(intent.settings, self.applied) and (
                self.now+MINIMUM_APPLICATION_NS > SAFE_INTEGER):
            self._disposition(intent, 'REJECTED', 'TIME_RANGE')
            return
        if type(intent) is SetOptics:
            heights = (self.stage_z,) if self.motion is None else (self.stage_z, self.motion['z'])
            if any(abs(intent.settings.focus_offset_m+z) > 25e-6 for z in heights):
                self._disposition(intent, 'REJECTED', 'SOURCE_DOMAIN')
                return
        if type(intent) in (MoveStage, MoveStageXYZ):
            z_target = intent.z_m if type(intent) is MoveStageXYZ else self.stage_z
            targets = (self.applied,) if self.pending is None else (self.applied, self.pending['settings'])
            if any(abs(settings.focus_offset_m+z_target) > 25e-6 for settings in targets):
                self._disposition(intent, 'REJECTED', 'SOURCE_DOMAIN')
                return
            duration = math.ceil(max(math.hypot(intent.x_m-self.stage_x, intent.y_m-self.stage_y)/.001,
                                     abs(z_target-self.stage_z)/.00002)*1e9)
            if self.now+duration+80_000_000 > SAFE_INTEGER:
                self._disposition(intent, 'REJECTED', 'TIME_RANGE')
                return
        if type(intent) is SetOptics and not same_settings(intent.settings, self.applied) and (
                self.pending is None and self.credits.free('A') < APPLICATION_RESERVE):
            self._terminal('NUMERIC_BACKLOG_CAPACITY')
            self._disposition(intent, 'REJECTED', 'NUMERIC_BACKLOG_CAPACITY')
            return
        problem = self._remember(intent.operation_id)
        if problem is not None:
            self._terminal(problem)
            self._disposition(intent, 'REJECTED', problem)
            return
        self.revision += 1
        if type(intent) is SetOptics:
            equal = same_settings(intent.settings, self.applied)
            slot = self._retire_target('TARGET_SUPERSEDED', keep_slot=not equal)
            self.settings_generation += 1
            if equal:
                if self.capture is not None:
                    self._hold_end(self.capture, self.now, self._r)
                self._disposition(intent, 'SATISFIED_NO_CHANGE', 'OK')
                return
            if slot is None:
                slot = self.credits.reserve('A', APPLICATION_RESERVE)
            if self.capture is not None:
                configuration = self.capture.configuration
            elif self.requested is None:
                configuration = ScanConfiguration(EpisodeGeometry(1, 1, 1e-6,
                    self.stage_x, self.stage_y, stage_z_m=self.stage_z), 1000)
            else:
                g = self.requested.geometry
                configuration = ScanConfiguration(EpisodeGeometry(g.width_px, g.height_px,
                    g.field_width_m, self.stage_x, self.stage_y, g.offset_x_m, g.offset_y_m,
                    self.stage_z), self.requested.dwell_ns)
            self.pending = {'op': intent.operation_id, 'authority': intent.authority,
                'settings': intent.settings, 'generation': self.settings_generation,
                'due': min(self.now+MINIMUM_APPLICATION_NS, SAFE_INTEGER),
                'configuration': configuration, 'ready': None, 'slot': slot}
        elif type(intent) in (MoveStage, MoveStageXYZ):
            terminal = self.credits.reserve('T', TERMINAL_PHYSICAL_RESERVE)
            if terminal is None:
                self._terminal('NUMERIC_BACKLOG_CAPACITY')
                self._disposition(intent, 'REJECTED', 'NUMERIC_BACKLOG_CAPACITY')
                return
            xyz = type(intent) is MoveStageXYZ
            z_target = intent.z_m if xyz else self.stage_z
            duration = math.ceil(max(math.hypot(intent.x_m-self.stage_x, intent.y_m-self.stage_y)/.001,
                                     abs(z_target-self.stage_z)/.00002)*1e9)
            moving_end = min(self.now+duration, SAFE_INTEGER)
            settled = min(moving_end+80_000_000, SAFE_INTEGER)
            if xyz:
                self._emit('MOTION_XYZ_START', (intent.operation_id, self.stage_x, self.stage_y,
                    self.stage_z, intent.x_m, intent.y_m, z_target, moving_end, settled), self.now, self._r)
            else:
                self._emit('MOTION_START', (intent.operation_id, self.stage_x, self.stage_y,
                    intent.x_m, intent.y_m, moving_end, settled), self.now, self._r)
            self.motion = {'op': intent.operation_id, 'x0': self.stage_x, 'y0': self.stage_y,
                'x': intent.x_m, 'y': intent.y_m, 'start': self.now,
                'z0': self.stage_z, 'z': z_target, 'xyz': xyz,
                'moving_end': moving_end, 'settled': settled, 'last': self.now, 'terminal': terminal}
        elif type(intent) is FreezeLive:
            self.session['freeze'] = intent.operation_id
            if self.capture is None and self.session['sweep'] >= 0:
                self._end_session('COMPLETED')
        else:
            self.geometry_generation += 1
            self.requested = configuration
            self._control('geometry_configured', 'GEOMETRY',
                          (intent.operation_id, self.geometry_generation, configuration))
            if type(intent) is StartCapture:
                self.session_generation += 1
                self.session = {'op': intent.operation_id, 'authority': intent.authority,
                    'generation': self.session_generation, 'mode': intent.mode,
                    'request': intent.request, 'configuration': configuration,
                    'due': min(self.now+MINIMUM_APPLICATION_NS, SAFE_INTEGER), 'sweep': -1,
                    'view': 'view-'+str(self.session_generation) if intent.mode == 'LIVE' else None,
                    'stop_generation': self.stop_generation, 'freeze': None}
            else:
                self.session['request'], self.session['configuration'] = intent.request, configuration
        self._disposition(intent, 'ACCEPTED', 'OK')

    def _result(self, result):
        if result is None or self.job is None or result.ticket != self.job:
            return
        ticket = self.job
        self.job = None
        if self.interlock is not None or not self._authorized(ticket.authority):
            return
        pending, session = self.pending, self.session
        if ticket.purpose == 'SETTINGS':
            valid = pending is not None and ticket.settings_generation == pending['generation'] and (
                ticket.request_id == pending['op'] and ticket.settings == pending['settings'])
            if valid and type(result) is BankReady:
                pending['ready'] = result.handle
        else:
            valid = session is not None and ticket.session_generation == session['generation'] and (
                ticket.geometry_generation == self.geometry_generation and ticket.applied_generation == self.applied_generation
                and ticket.configuration == session['configuration'] and ticket.settings == self.applied)
            if valid and type(result) is BankReady:
                self.bank = result.handle
        if valid and type(result) is BankFailed:
            self._terminal('BANK_FAILED')

    def _apply(self, stop_valid):
        pending = self.pending
        if stop_valid or self.interlock is not None or pending is None or pending['ready'] is None or (
                self.now < pending['due'] or not self._authorized(pending['authority'])):
            return
        capture, handle, previous = self.capture, pending['ready'], self.applied
        if capture is not None:
            if capture.records >= RECORD_LIMIT:
                self._advance_capture(capture, self.now, capture.terminal)
                self._end_capture(capture, self.now, 'CAPTURE_RECORD_LIMIT')
                capture = None
            elif handle.geometry != capture.configuration.geometry:
                self._terminal('CAUSAL_FAILURE')
                return
        if capture is not None:
            self._hold_end(capture, self.now, self._r)
        next_generation = self.applied_generation+1
        self._emit('SETTINGS_APPLIED', (pending['op'], previous, handle.settings,
            next_generation, handle, capture.identity if capture else None,
            capture.elapsed if capture else None), self.now, pending['slot'])
        self.credits.release(pending['slot'])
        self.applied, self.bank, self.applied_generation = handle.settings, handle, next_generation
        self.pending = None
        self.revision += 1
        if capture is not None:
            capture.handle, capture.label = handle, pending['op']
            capture.records += 1

    def _dispatch(self):
        if self.interlock is not None or self.job is not None:
            return None
        pending, session = self.pending, self.session
        if pending is not None and pending['ready'] is None and self._authorized(pending['authority']):
            op, authority, config, settings, due, purpose = (pending['op'], pending['authority'],
                pending['configuration'], pending['settings'], pending['due'], 'SETTINGS')
        elif session is not None and self.capture is None and self._authorized(session['authority']):
            config, settings = session['configuration'], self.applied
            if self.bank is not None and self.bank.geometry == config.geometry and self.bank.settings == settings:
                return None
            op, authority, due, purpose = session['op'], session['authority'], session['due'], 'INITIAL_CAPTURE'
        else:
            return None
        self.job_generation += 1
        ticket = BankTicket('job-'+str(self.job_generation), op, purpose, authority,
            self.session_generation, self.settings_generation, self.geometry_generation,
            self.applied_generation, self.custodian_generation, self.science, config, settings, due)
        self.job = ticket
        return ticket

    def _start(self, stop_valid):
        session = self.session
        if stop_valid or self.interlock is not None or session is None or self.capture is not None or self.motion is not None:
            return
        if session['stop_generation'] != self.stop_generation or not self._authorized(session['authority']):
            self._end_session('STOPPED_BEFORE_ADMISSION')
            return
        if session['sweep'] == -1 and self.now < session['due']:
            return
        if self.pending is not None and self.now >= self.pending['due']:
            return
        config = session['configuration']
        if self.bank is None or self.bank.geometry != config.geometry or self.bank.settings != self.applied:
            return
        terminal = self.credits.reserve('T', TERMINAL_PHYSICAL_RESERVE)
        if terminal is None or self._r is None or self._r.remaining < 1:
            if terminal is not None:
                self.credits.release(terminal)
            self._terminal('NUMERIC_BACKLOG_CAPACITY')
            return
        self.capture_generation += 1
        session['sweep'] += 1
        identifier = 'raster-'+str(self.capture_generation)
        capture = _Capture(identifier, session, self.now, config, self.bank, terminal)
        self._emit('RASTER_START', (identifier, session['generation'], session['sweep'], session['mode'],
            session['op'], session['view'], config, self.bank, 'initial'), self.now, self._r)
        self.capture = capture
        self._starts.append(identifier)
        self.last_capture_incident = 0

    def snapshot(self):
        capture, session = self.capture, self.session
        phase = ('INTERLOCKED' if self.interlock else 'MOVING' if self.motion else 'CAPTURING' if capture else
                 'PREPARING' if session and session['sweep'] == -1 else 'BETWEEN_SWEEPS' if session else 'STOPPED')
        blank = True
        if capture is not None and capture.hold is None:
            blank = active_prefix(capture.plan, min(capture.nominal+1, capture.plan.program_end_ns)) == active_prefix(capture.plan, capture.nominal)
        return EpisodeState(self.now, self.revision, phase, blank, self.applied,
            self.pending['settings'] if self.pending else None, self.lease, self.stop_generation,
            self.session_generation, self.settings_generation, self.geometry_generation, self.applied_generation,
            capture.configuration if capture else None, self.requested,
            capture.identity if capture else None, session['view'] if session else None,
            capture.sweep if capture else session['sweep'] if session and session['sweep'] >= 0 else None,
            self.stage_x, self.stage_y, self.credits.ordinal, self.physical_sequence,
            self.credits.acknowledged_ordinal, capture.incident if capture else self.last_capture_incident,
            self.total, self.interlock, stage_z_m=self.stage_z)

    def tick(self, at_ns, inputs=EpisodeInputs()):
        integer(at_ns); exact(inputs, EpisodeInputs)
        if at_ns < self.now:
            raise ValueError('backward physical owner tick')
        if inputs.verified_ack is not None and inputs.verified_ack.episode_namespace == self.episode and (
                inputs.verified_ack.last_ordinal > self.credits.ordinal):
            raise ValueError('future verification acknowledgement is forbidden')
        self.now = at_ns
        self._facts, self._starts, self._ends, self._sites = [], [], [], {}
        self._r = self._c = None
        if inputs.verified_ack is not None and inputs.verified_ack.episode_namespace == self.episode:
            self.credits.acknowledge(inputs.verified_ack.last_ordinal)
        if self.interlock is not None:
            return EpisodeTickResult(self.snapshot(), (), None, (), ())
        self._r = self.credits.reserve('R', REGULAR_PHYSICAL_RESERVE)
        self._c = self.credits.reserve('C', REGULAR_CONTROL_RESERVE)
        stop = inputs.stop
        stop_valid = stop is not None and stop.operation_id not in self.ops and self._authorized(stop.authority, stop=True)
        stop_problem = None
        if stop_valid:
            stop_problem = self._remember(stop.operation_id, safety=True)
            stop_valid = stop_problem is None
            if stop_valid:
                self.stop_generation += 1
                self.revision += 1
        revoked = (type(inputs.authority) is RevokeAuthority and
                   inputs.authority.operation_id not in self.ops and self._authorized(inputs.authority.authority) and
                   len(self.ops) < self.capacity.admission_record_slots-1)
        fault = inputs.fault if inputs.fault is not None and inputs.fault.episode_namespace == self.episode else None
        if self._r is None or self._c is None or fault is not None:
            self._emergency_mode = True
            self._terminal(fault.reason if fault else 'NUMERIC_BACKLOG_CAPACITY',
                           physical_reason='STOP' if stop_valid else None)
        elif self.now == SAFE_INTEGER:
            self._terminal('TIME_RANGE', physical_reason='STOP' if stop_valid else None)
        else:
            reason = 'STOP' if stop_valid else 'REVOKED' if revoked else None
            self._progress_capture(reason); self._progress_motion(reason)
            if self.lease is not None and self.lease.expires_ns <= self.now:
                deadline = self.lease.expires_ns
                self._lease_changed(None, 'EXPIRED', deadline)
                self._end_session('EXPIRED'); self._retire_target('EXPIRED')
        if stop is not None:
            if stop_valid:
                if not self._emergency_mode:
                    self._end_session('STOP')
                self._disposition(stop, 'ACCEPTED', 'OK')
            else:
                why = stop_problem or self.interlock or ('DUPLICATE_OPERATION' if stop.operation_id in self.ops else 'UNAUTHORIZED')
                self._disposition(stop, 'REJECTED', why)
        self._authority(inputs.authority)
        self._normal(inputs.normal, stop_valid)
        self._result(inputs.bank_result)
        self._apply(stop_valid)
        dispatch = self._dispatch()
        self._start(stop_valid)
        if self._r is not None:
            self.credits.release(self._r)
        if self._c is not None:
            self.credits.release(self._c)
        self._r = self._c = None
        return EpisodeTickResult(self.snapshot(), tuple(self._facts), dispatch,
                                 tuple(self._starts), tuple(self._ends))
