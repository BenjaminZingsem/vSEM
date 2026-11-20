"""Authored public HTTP data oracle, NOT a vSEM engine or physics qualification."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import struct
import threading
import time


COUNTS = (0, 9, 65535, 65536, 2**32-1, 101, 99, 1)


def metadata(parameters, image='image-fixture', source='raster-fixture', origin=0):
    width, height = parameters['width_px'], parameters['height_px']
    elapsed = width*height*parameters['dwell_ns']+20_000_000+(height-1)*100_000+1_000_000
    pose = dict(x_m=.001, y_m=-.002, z_m=1e-6, working_distance_m=.009999)
    def segment(start, end, focus):
        return dict(start_elapsed_ns=start, end_elapsed_ns=end, current_pA=100,
            focus_offset_m=focus, stigmator_x=.1, stigmator_y=-.2, stage=dict(pose))
    return dict(protocol='vsem.core-native-image.v2', image_id=image, source_id=source,
        mode='SINGLE', outcome='COMPLETED', terminal_reason='COMPLETED', origin_ns=origin,
        cut_elapsed_ns=elapsed, numerical_verified_ordinal=42, causal_verified_ordinal=42,
        width_px=width, height_px=height, completed_pixels=width*height,
        active_dwell_ns=0, dwell_ns=parameters['dwell_ns'], field_width_m=parameters['field_width_m'],
        pixel_pitch_m=parameters['field_width_m']/width, magnification=.1/parameters['field_width_m'],
        magnification_reference_width_m=.1, stage=pose,
        offset_x_m=parameters['offset_x_m'], offset_y_m=parameters['offset_y_m'],
        incident_pA_ns=width*height*parameters['dwell_ns']*100,
        parameter_segments=[segment(0, elapsed//2, 0.), segment(elapsed//2, elapsed, 4e-6)],
        blank_holds=[dict(start_elapsed_ns=0, end_elapsed_ns=1_000_000)],
        raw_format='uint32_little_endian', calibration_status='generic_uncalibrated', detector='SE')


class ImageFixture:
    def __init__(self, *, paced=False, publication_delay_s=0., vacuum=False):
        self.paced, self.publication_delay_s, self.vacuum = paced, publication_delay_s, vacuum
        self.commands, self.paths, self.records, self.images = [], [], {}, {}
        self.leases = 0
        self.lock = threading.RLock()
        self.origin_clock = time.monotonic()
        self.enabled = True
        self.probe_overrides = {}
        self.association_overrides = {}
        self.metadata_overrides = {}
        self.raw_override = None
        self.fail_next_association = False
        self.drop_next_command = False
        self.receipt_status = 'COMPLETED'
        self.block_raw = False
        self.raw_blocked, self.release_raw = threading.Event(), threading.Event()
        self.allow_publication = threading.Event()
        self.allow_publication.set()
        self.state = dict(protocol='vsem.core-human.v3', availability='AVAILABLE',
            interlock_reason=None, delivery_age_ns=0, stop_generation=8, control_owned=True,
            control=dict(holder='operator-api', epoch=3, expires_ns=30_000_000_000),
            applied=dict(current_pA=100, focus_offset_m=0., stigmator_x=.1, stigmator_y=-.2),
            requested=None, stage=dict(x_m=0., y_m=0., z_m=0.), capabilities=dict(detectors=['SE']))
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def authenticate(self):
                with fixture.lock:
                    fixture.paths.append(self.path)
                return (self.headers.get_all('Authorization') == ['Bearer qualification-fixture-only']
                    and self.headers.get_all('Cookie') is None and self.headers.get_all('Origin') is None)

            def reply(self, code, value):
                if code == 0:
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                raw = value if type(value) is bytes else json.dumps(value, allow_nan=False).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/octet-stream' if type(value) is bytes else 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def do_GET(self):
                if not self.authenticate():
                    return self.reply(401, {})
                if self.path.endswith('/SE') and fixture.block_raw:
                    fixture.raw_blocked.set()
                    fixture.release_raw.wait(30.)  # Outside the oracle lock: Stop/lease remain independent.
                code, value = fixture.get(self.path)
                return self.reply(code, value)

            def do_POST(self):
                if not self.authenticate():
                    return self.reply(401, {})
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size < 65536:
                    return self.reply(400, {})
                value = json.loads(self.rfile.read(size))
                code, value = fixture.post(self.path, value)
                return self.reply(code, value)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = False
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=.01),
                                       name='m05b2b0-image-oracle')
        self.thread.start()
        self.origin = 'http://127.0.0.1:'+str(self.server.server_port)

    def now(self):
        return int((time.monotonic()-self.origin_clock)*1e9)

    def receipt(self, operation):
        record = self.records[operation]
        status = record['status']
        if status == 'COMPLETED' and record['command'] == 'scan_single' and time.monotonic() < record['physical_end']:
            status = 'RUNNING'
        return dict(operation_id=operation, status=status,
            reason='OK' if status not in ('CANCELLED', 'REJECTED') else 'STOP', observed_at_ns=self.now())

    def association(self, operation):
        record = self.records[operation]
        result = dict(protocol='vsem.operation-acquisitions.v1', operation_id=operation,
            command=record['command'], receipt=self.receipt(operation),
            association=None, latest_cut=None, final_cut=None)
        if record['command'] == 'scan_single':
            meta = record['metadata']
            result['association'] = dict(relation='started_single', source_id=meta['source_id'],
                raster_id=meta['source_id'], applied_at_ns=meta['origin_ns'])
            if self.allow_publication.is_set() and time.monotonic() >= record['publish_at']:
                result['final_cut'] = dict(image_id=meta['image_id'], source_id=meta['source_id'],
                    raster_id=meta['source_id'], cut_elapsed_ns=meta['cut_elapsed_ns'], outcome=meta['outcome'])
                result['latest_cut'] = dict(result['final_cut'])
            result.update(deepcopy(self.association_overrides))
        else:
            result.update(deepcopy(self.probe_overrides))
        return result

    def get(self, path):
        with self.lock:
            pieces = path.split('/')
            if path == '/state':
                return 200, dict(deepcopy(self.state), observed_at_ns=self.now())
            if len(pieces) in (3, 4) and pieces[1] == 'operation' and pieces[2] in self.records:
                operation = pieces[2]
                if len(pieces) == 3:
                    return 200, self.receipt(operation)
                if pieces[3] == 'acquisitions':
                    if not self.enabled:
                        return 404, {}
                    if self.records[operation]['command'] == 'scan_single' and self.fail_next_association:
                        self.fail_next_association = False
                        return 0, {}
                    return 200, self.association(operation)
            if len(pieces) in (3, 4) and pieces[1] == 'image' and pieces[2] in self.images:
                meta, raw = self.images[pieces[2]]
                if len(pieces) == 4 and pieces[3] == 'SE':
                    return 200, raw if self.raw_override is None else self.raw_override
                if len(pieces) == 3:
                    return 200, dict(deepcopy(meta), **deepcopy(self.metadata_overrides))
            return 404, {}

    def post(self, path, value):
        with self.lock:
            now = time.monotonic()
            if path == '/lease' and value == {}:
                command = 'lease'
                self.leases += 1
                self.state['control']['expires_ns'] = self.now()+30_000_000_000
            elif path == '/command' and set(value) == {'action', 'parameters', 'expected_stop_generation'}:
                if value['expected_stop_generation'] != self.state['stop_generation']:
                    return 400, {}
                self.commands.append(deepcopy(value))
                command = value['action']
                if command == 'stop':
                    self.state['stop_generation'] += 1
                    for record in self.records.values():
                        if record['command'] == 'scan_single' and now < record['physical_end']:
                            record['status'] = 'CANCELLED'
                if self.drop_next_command:
                    self.drop_next_command = False
                    return 0, {}
            else:
                return 404, {}
            operation = 'op-'+str(len(self.records)+1)
            record = dict(command=command, status='COMPLETED')
            self.records[operation] = record
            if command == 'scan_single':
                meta = metadata(value['parameters'], 'image-'+operation, 'raster-'+operation, self.now())
                count = meta['width_px']*meta['height_px']
                raw = bytes(count*4) if self.vacuum else struct.pack('<8I', *COUNTS)*(count//8)
                self.images[meta['image_id']] = (meta, raw)
                duration = meta['cut_elapsed_ns']/1e9 if self.paced else 0.
                record.update(status=self.receipt_status, metadata=meta,
                    physical_end=now+duration, publish_at=now+duration+self.publication_delay_s)
            return 202, dict(operation_id=operation, status='RECEIVED', reason=None, observed_at_ns=None)

    def close(self):
        self.release_raw.set()
        self.allow_publication.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5.)
        if self.thread.is_alive():
            raise RuntimeError('owned image HTTP fixture remains')
