"""Separate unchanged authenticated transports;new GUI asset filenames only.

Authentication,CSRF,GUI/API principals,one-use invitations and public dispatch
remain inherited/AST-identical. No new instrument or private development route.
"""
from http.server import ThreadingHTTPServer
import secrets
import threading
from urllib.parse import urlsplit
from .core_human_http import CoreHTTP,GUIGateway,APIGateway,ASSETS
from .core_human_service import GUI,API


class HierarchicalGUIGateway(GUIGateway):
    def do_GET(self):
        if not self.valid_host() or self.headers.get_all('Authorization') is not None:
            return self.error(403, 'wrong_transport')
        path = urlsplit(self.path).path
        if path != self.path:
            return self.error(404, 'not_found')
        if path == '/open/' + self.server.invitation:
            with self.server.invitation_lock:
                if self.server.invitation_used and (not self.authenticated()):
                    return self.error(403, 'invitation_used')
                self.server.invitation_used = True
            return self.reply(303, b'', 'text/plain', {'Location': '/', 'Set-Cookie': 'vsem_core=' + self.server.session + '; HttpOnly; SameSite=Strict; Path=/'})
        if not self.authenticated():
            return self.error(401, 'browser_session_required')
        if path == '/session':
            return self.reply(200, {'csrf': self.server.csrf})
        if path == '/':
            file = ASSETS / 'hierarchical_sem_console.html'
            if not file.is_file():
                return self.error(503, 'console_not_ready')
            return self.reply(200, file.read_bytes(), 'text/html; charset=utf-8')
        scripts = {'/core_sem_console.js': 'hierarchical_sem_console.js', '/native_counts_rgba.js': 'native_counts_rgba.js', '/stage_pose_controls.js': 'stage_pose_controls.js', '/scan_display_buffer.js': 'scan_display_buffer.js', '/intensity_transfer.js': 'intensity_transfer.js'}
        if path in scripts:
            file = ASSETS / scripts[path]
            if not file.is_file():
                return self.error(404, 'not_found')
            return self.reply(200, file.read_bytes(), 'text/javascript; charset=utf-8')
        return self.dispatch_get(path)


class HierarchicalHTTP(CoreHTTP):
    def __init__(self, service, ui_port=0, api_port=0):
        self.ui = ThreadingHTTPServer(('127.0.0.1', ui_port), HierarchicalGUIGateway)
        try:
            self.api = ThreadingHTTPServer(('127.0.0.1', api_port), APIGateway)
        except BaseException:
            self.ui.server_close()
            raise
        for (server, principal) in ((self.ui, GUI), (self.api, API)):
            server.service = service
            server.principal = principal
            server.daemon_threads = True
            server.public_host = '127.0.0.1:' + str(server.server_port)
            server.origin = 'http://' + server.public_host
        self.ui.session = secrets.token_urlsafe(32)
        self.ui.csrf = secrets.token_urlsafe(32)
        self.ui.invitation = secrets.token_urlsafe(32)
        self.ui.invitation_used = False
        self.ui.invitation_lock = threading.Lock()
        self.api.token = secrets.token_urlsafe(32)
        self.threads = [threading.Thread(target=server.serve_forever, name='vsem-core-' + principal.transport, daemon=True) for (server, principal) in ((self.ui, GUI), (self.api, API))]
        for thread in self.threads:
            thread.start()
