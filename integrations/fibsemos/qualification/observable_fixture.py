"""Maintainer-owned observable HTTP fixture; no engine, evaluator or physical truth."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading


class ObservableFixture:
    def __init__(self):
        self.commands, self.paths, self.records = [], [], {}
        self.leases = 0
        self.change_epoch = False
        self.drop_next_command = False
        self.confirm_stop = True
        self.lock = threading.RLock()
        self.state = {
            'protocol': 'vsem.core-human.v3', 'availability': 'AVAILABLE',
            'observed_at_ns': 100, 'delivery_age_ns': 0, 'interlock_reason': None,
            'stop_generation': 8, 'control_owned': True,
            'control': {'holder': 'operator-api', 'epoch': 3, 'expires_ns': 30_000_000_000},
            'applied': {'current_pA': 100, 'focus_offset_m': 0., 'stigmator_x': .1, 'stigmator_y': -.2},
            'requested': None, 'stage': {'x_m': 0., 'y_m': 0., 'z_m': 0.},
            'capabilities': {'detectors': ['SE']},
            'current_scan': {'width_px': 64, 'height_px': 64, 'field_width_m': 80e-6,
                             'pixel_pitch_m': 80e-6 / 64, 'magnification': .1 / 80e-6,
                             'magnification_reference_width_m': .1,
                             'stage_x_m': 0., 'stage_y_m': 0., 'stage_z_m': 0.,
                             'offset_x_m': 0., 'offset_y_m': 0., 'dwell_ns': 20000},
        }
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def response(self, code, value):
                raw = json.dumps(value, allow_nan=False).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def authenticate(self):
                fixture.paths.append(self.path)
                return (self.headers.get('Authorization') == 'Bearer qualification-fixture-only' and
                        self.headers.get('Cookie') is None and self.headers.get('Origin') is None)

            def do_GET(self):
                with fixture.lock:
                    if not self.authenticate():
                        return self.response(401, {})
                    if self.path == '/state':
                        return self.response(200, deepcopy(fixture.state))
                    if self.path.startswith('/operation/'):
                        value = fixture.records.get(self.path.rsplit('/', 1)[-1])
                        return self.response(200 if value else 404, deepcopy(value or {}))
                    return self.response(404, {})

            def do_POST(self):
                with fixture.lock:
                    if not self.authenticate():
                        return self.response(401, {})
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length < 65536:
                        return self.response(400, {})
                    value = json.loads(self.rfile.read(length))
                    if self.path == '/lease':
                        if value != {}:
                            return self.response(400, {})
                        fixture.leases += 1
                        if fixture.change_epoch:
                            fixture.state['control']['epoch'] += 1
                    elif self.path == '/command':
                        if (set(value) != {'action', 'parameters', 'expected_stop_generation'} or
                                value['expected_stop_generation'] != fixture.state['stop_generation']):
                            return self.response(400, {})
                        fixture.commands.append(deepcopy(value))
                        action, params = value['action'], value['parameters']
                        if action == 'optics':
                            fixture.state['applied'] = deepcopy(params)
                        elif action == 'stage_move':
                            fixture.state['stage'] = deepcopy(params)
                        elif action == 'stop':
                            if fixture.confirm_stop:
                                fixture.state['stop_generation'] += 1
                        elif action not in ('scan_single', 'scan_live', 'configure_live', 'freeze'):
                            return self.response(400, {})
                        if fixture.drop_next_command:
                            fixture.drop_next_command = False
                            self.connection.shutdown(socket.SHUT_RDWR)
                            self.connection.close()
                            return
                    else:
                        return self.response(404, {})
                    operation = 'op-' + str(len(fixture.records) + 1)
                    fixture.records[operation] = {'operation_id': operation, 'status': 'COMPLETED',
                                                  'reason': 'OK', 'observed_at_ns': 120}
                    return self.response(202, {'operation_id': operation, 'status': 'RECEIVED',
                                               'reason': None, 'observed_at_ns': None})

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = False
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=.01),
                                       name='m05b1-observable-http')
        self.thread.start()
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5.)
        if self.thread.is_alive():
            raise RuntimeError('owned HTTP fixture did not close')
