"""Frontier-owned bounded loopback HTTP/RPC boundary. No engine/truth imports."""
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
import json
import os
import threading


def pairs(items):
    result = {}
    for key,value in items:
        if key in result:
            raise ValueError('duplicate_key')
        result[key] = value
    return result


class Gateway(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'
    server_version = 'vSEM'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(3)

    def log_message(self, *args):
        pass

    def reply(self, status, body, content_type='application/json', extra=None):
        data = json.dumps(body, allow_nan=False, separators=(',',':')).encode() if content_type=='application/json' else body
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for key,value in (extra or {}).items():
            self.send_header(key,value)
        self.end_headers()
        self.wfile.write(data)

    def error(self, status, code):
        self.reply(status, {'error': code})

    def valid_host(self):
        return (self.headers.get_all('Host')==[self.server.public_host]
                and self.headers.get_all('Transfer-Encoding') is None)

    def payload_bytes(self, limit_bytes=131072):
        lengths = self.headers.get_all('Content-Length')
        if lengths is None or len(lengths)!=1 or not lengths[0].isdigit():
            raise ValueError('invalid_length')
        length = int(lengths[0])
        if length > limit_bytes or self.headers.get_all('Content-Type')!=['application/json']:
            raise ValueError('invalid_body')
        data = self.rfile.read(length)
        if len(data)!=length:
            raise ValueError('short_body')
        return data

    def payload(self, limit_bytes=131072):
        data = self.payload_bytes(limit_bytes)
        return json.loads(data.decode('utf-8'),object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))

    def rpc(self, request):
        # One complete transaction owns the uncorrelated legacy pipe. Pure
        # presentation handlers never enter this lock.
        with self.server.rpc_lock:
            if self.server.rpc_poisoned:
                self.error(503,'engine_unavailable')
                return None
            try:
                self.server.pipe.send(request)
                available = self.server.pipe.poll(30)
                result = self.server.pipe.recv() if available else None
            except (EOFError,BrokenPipeError,OSError):
                result = None
            if result is None:
                self.server.rpc_poisoned = True
        if result is None:
            # Completion is unknown after a timeout; never retry a command here.
            self.error(504,'completion_unknown' if request['action'] in ('command','live_command') else 'engine_unavailable')
            if not self.server.retain_presentation:
                self.server.shutdown_requested = True
            return None
        if not result['ok']:
            self.error(409,result['error'])
            return None
        return result['value']

    def serve_public_get(self, path):
        if path=='/state':
            value = self.rpc({'action':'snapshot'})
        elif path=='/live-reference':
            value = self.rpc({'action':'completed_reference'})
        elif path.startswith('/image/') and '/' not in path[len('/image/'):]:
            value = self.rpc({'action':'image','image_id':path[len('/image/'):]})
        else:
            self.error(404,'not_found')
            return
        if value is not None:
            self.reply(200,value)


def serve(port, pipe, handler, ready, stop, *, concurrent=False,
          retain_presentation=False, **attributes):
    server = (ThreadingHTTPServer if concurrent else HTTPServer)(('127.0.0.1',port),handler)
    if concurrent:
        server.daemon_threads = True
    server.timeout = 0.2
    server.pipe = pipe
    server.public_host = '127.0.0.1:'+str(server.server_port)
    server.origin = 'http://'+server.public_host
    server.shutdown_requested = False
    server.rpc_lock = threading.Lock()
    server.rpc_poisoned = False
    server.retain_presentation = retain_presentation
    for name,value in attributes.items():
        setattr(server,name,value)
    ready.send({'port': server.server_port, 'pid': os.getpid()})
    try:
        while not stop.is_set() and not server.shutdown_requested:
            server.handle_request()
    finally:
        server.server_close()
