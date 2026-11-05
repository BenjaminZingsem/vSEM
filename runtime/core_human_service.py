"""Trusted autonomous coordinator;HTTP requests never drive physical evolution."""
from collections import deque
from dataclasses import dataclass
import json
import queue
import secrets
import threading
import time

from engine import human_episode_types as t
from engine.episode_credits import EpisodeCapacity
from .core_human_kernel import LiveRealtimeKernel,LiveKernelConfiguration
from .human_realtime_records import TickEnd
from .core_public_protocol import observable_state,image_observation,validate_command,make_input


class ObservedKernel(LiveRealtimeKernel):
    def __init__(self,*args,**kwargs):
        self.events = deque()
        super().__init__(*args,**kwargs)
    def _retain(self,value,cell):
        super()._retain(value,cell)
        if type(value) is TickEnd and self.causal_error is None:
            self.events.extend(self.verifier.expected)


@dataclass(frozen=True)
class Principal:
    holder: str
    transport: str


GUI = Principal('human-gui','GUI')
API = Principal('operator-api','API')


class CoreHumanService:
    def __init__(self,directory,*,capacity=None):
        self.kernel = ObservedKernel(directory,t.EpisodeSettings(100,0.,0.,0.),LiveKernelConfiguration(
            capacity or EpisodeCapacity(4096,256,128,4096,65536,65536)))
        self.normal = queue.Queue(256); self.safety = queue.Queue(64)
        self.lock = threading.Lock(); self.stop_event = threading.Event()
        self.operations = {}; self.latest = {'protocol':'vsem.core-human.v1','availability':'INITIALIZING'}
        self.image_records = {}; self.latest_image = None; self.history = []
        self.failure = None; self._image_index = 0
        self.thread = threading.Thread(target=self._run,name='vsem-trusted-service',daemon=True); self.thread.start()

    def request(self,principal,kind,value=None):
        if principal not in (GUI,API):raise ValueError('unknown_principal')
        if self.failure or self.kernel.causal_error or self.stop_event.is_set():
            raise BufferError('service_unavailable')
        if kind == 'command':value = validate_command(value)
        elif kind != 'lease':raise ValueError('unsupported_request')
        operation_id = 'op-'+secrets.token_hex(12)
        record = {'operation_id':operation_id,'status':'RECEIVED','reason':None,'observed_at_ns':None}
        with self.lock:self.operations[operation_id] = dict(record)
        work = (principal,kind,value,operation_id)
        target = self.safety if kind == 'command' and value['action'] == 'stop' else self.normal
        try:target.put_nowait(work)
        except queue.Full:
            with self.lock:self.operations[operation_id].update(status='REJECTED',reason='ingress_capacity')
            raise BufferError('ingress_capacity')
        return record

    def _admit(self,work):
        principal,kind,value,operation_id = work
        state = self.kernel.causal_cut.state if self.kernel.causal_cut else None
        lease = state.lease if state else None
        if kind == 'lease':
            deadline = self.kernel.elapsed_ns()+30_000_000_000
            command = t.RenewAuthority(operation_id,lease.authority,deadline) if lease and lease.authority.holder_id == principal.holder else t.GrantAuthority(operation_id,principal.holder,deadline)
            inputs = t.EpisodeInputs(authority=command)
        else:
            if lease is None or lease.authority.holder_id != principal.holder:
                with self.lock:self.operations[operation_id].update(status='REJECTED',reason='control_not_owned')
                return
            if value['action'] in ('optics','stage_move'):
                focus=value['parameters']['focus_offset_m'] if value['action']=='optics' else state.settings.focus_offset_m
                z=value['parameters']['z_m'] if value['action']=='stage_move' else state.stage_z_m
                if not -25e-6<=focus+z<=25e-6:
                    with self.lock:self.operations[operation_id].update(status='REJECTED',reason='combined_focus_z_envelope')
                    return
            inputs = make_input(value,operation_id,lease.authority)
        try:self.kernel.submit(inputs)
        except BufferError:
            with self.lock:self.operations[operation_id].update(status='UNKNOWN',reason='admission_unknown')

    def _event(self,fact):
        kind,body = fact.kind,fact.body
        operation = None; status = reason = None
        if kind == 'DISPOSITION':
            operation,status,reason,_ = body
            if status == 'SATISFIED_NO_CHANGE':status = 'COMPLETED'
            if body[3] in ('GrantAuthority','RenewAuthority','RevokeAuthority','SafetyStop') and status == 'ACCEPTED':status = 'COMPLETED'
        elif kind == 'SETTINGS_APPLIED':operation,status,reason = body[0],'COMPLETED','OK'
        elif kind in ('MOTION_START','MOTION_XYZ_START'):operation,status,reason = body[0],'RUNNING','OK'
        elif kind in ('MOTION_END','MOTION_XYZ_END'):
            operation = body[0]; reason = body[-1]; status = 'COMPLETED' if reason == 'COMPLETED' else 'CANCELLED'
        elif kind == 'RASTER_START':operation,status,reason = body[4],'RUNNING','OK'
        elif kind == 'SESSION_ENDED':operation,reason = body[:2];status = 'COMPLETED' if reason == 'COMPLETED' else 'CANCELLED'
        if operation is not None:
            with self.lock:
                if operation in self.operations:
                    prior = self.operations[operation]['status']
                    # Accepted disposition follows a motion/start fact. It cannot
                    # downgrade the verified physical RUNNING state to admission.
                    if not(status == 'ACCEPTED' and prior == 'RUNNING'):
                        self.operations[operation].update(status=status,reason=reason,observed_at_ns=fact.event_at_ns)

    def _run(self):
        try:
            while not self.stop_event.is_set():
                self.kernel.refresh()
                while self.kernel.events:self._event(self.kernel.events.popleft())
                state = observable_state(self.kernel)
                with self.lock:self.latest = state
                while self._image_index < len(self.kernel.native_images):
                    ready = self.kernel.native_images[self._image_index]; self._image_index += 1
                    metadata,_ = self.kernel.read_image(ready); observation = image_observation(metadata)
                    with self.lock:
                        self.image_records[ready.image_id] = (ready,observation)
                        self.latest_image = observation
                        if metadata['mode'] == 'SINGLE' and metadata['outcome'] != 'ACQUIRING':self.history.append(observation)
                for source in (self.safety,self.normal):
                    try:work = source.get_nowait()
                    except queue.Empty:continue
                    self._admit(work)
                time.sleep(.002)
        except BaseException:
            self.failure = 'service_unavailable'
            try:self.kernel.fault('CAUSAL_FAILURE')
            except Exception:pass

    def snapshot(self,principal):
        with self.lock:
            result = json.loads(json.dumps(self.latest))
            result['latest_image'] = json.loads(json.dumps(self.latest_image))
            result['recorded_images'] = [dict(item) for item in self.history]
        control = result.get('control')
        result['control_owned'] = bool(control and control['holder'] == principal.holder)
        if self.failure:result['availability'] = 'QUARANTINED'
        return result

    def operation(self,operation_id):
        with self.lock:
            if operation_id not in self.operations:raise KeyError('not_found')
            return dict(self.operations[operation_id])

    def image(self,image_id):
        with self.lock:
            if image_id not in self.image_records:raise KeyError('not_found')
            ready,metadata = self.image_records[image_id]
        # Artifact IO is outside the service/cache lock and does not drive its
        # physical clock or interrupt verified Stop publication.
        _,channels = self.kernel.read_image(ready)
        return dict(metadata),channels['SE']

    def close(self):
        self.stop_event.set();self.thread.join(5.)
        self.kernel.close()

