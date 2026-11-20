"""Actual loopback HTTP route/authentication tests, with no GPU fixture."""
import http.client
import json
import threading
import unittest

from acceptance.test_operation_acquisitions import service_fixture, parameters
from runtime.core_human_service import API, GUI
from runtime.hierarchical_http import HierarchicalHTTP


class AssociationHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = service_fixture()
        cls.http = HierarchicalHTTP(cls.service)

    @classmethod
    def tearDownClass(cls):
        cls.http.close()
        if any(t.is_alive() for t in cls.http.threads):
            raise AssertionError('owned HTTP server thread remains')

    def setUp(self):
        self.service.failure = self.service.kernel.causal_error = None
        self.service.stop_event.clear()
        self.operation = self.service.request(API, 'command', dict(action='scan_single',
            parameters=parameters(), expected_stop_generation=0))['operation_id']
        self.path = '/operation/' + self.operation + '/acquisitions'

    def request(self, path=None, headers=None, server=None, method='GET'):
        server = self.http.api if server is None else server
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        try:
            connection.putrequest(method, self.path if path is None else path, skip_host=True)
            fields = [('Host', server.public_host)]
            fields += [('Authorization', 'Bearer ' + self.http.api.token)] if headers is None else headers
            for key, value in fields:
                connection.putheader(key, value)
            connection.endheaders()
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_valid_authenticated_route_and_original_receipt(self):
        status, value = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(value['operation_id'], self.operation)
        self.assertEqual(value['receipt'], self.service.operation(self.operation))
        self.assertIsNone(value['association'])

    def test_missing_wrong_duplicate_bearer_and_foreign_headers(self):
        bearer = ('Authorization', 'Bearer ' + self.http.api.token)
        for headers in ([], [('Authorization', 'Bearer wrong')], [bearer, bearer],
                [bearer, ('Cookie', '')], [bearer, ('Origin', self.http.api.origin)],
                [bearer, ('Host', self.http.api.public_host)],
                [bearer, ('Host', 'localhost:' + str(self.http.api.server_port))],
                [bearer, ('Transfer-Encoding', 'chunked')],
                [('Authorization', 'Bearer ' + self.http.ui.session)]):
            with self.subTest(headers=[k for k, _ in headers]):
                self.assertEqual(self.request(headers=headers)[0], 401)

    def test_gui_transport_and_gui_owned_operations_are_unavailable(self):
        self.assertEqual(self.request(server=self.http.ui)[0], 403)
        cookie = [('Cookie', 'vsem_core=' + self.http.ui.session)]
        self.assertEqual(self.request(server=self.http.ui, headers=cookie)[0], 404)
        operation = self.service.request(GUI, 'lease')['operation_id']
        path = '/operation/' + operation + '/acquisitions'
        self.assertEqual(self.request(path)[0], 404)
        self.service.failure = 'unavailable'
        try:
            self.assertEqual(self.request(path)[0], 404)
        finally:
            self.service.failure = None

    def test_malformed_unknown_query_encoded_and_extra_paths(self):
        for path in (self.path + '?x=1', self.path + '/', self.path + '/SE',
                self.path.replace('/acquisitions', '//acquisitions'),
                '/operation//acquisitions', '/operation/op-1/acquisitions',
                '/operation/op-' + 'A' * 24 + '/acquisitions',
                '/operation/op-' + '0' * 24 + '/acquisitions',
                self.path.replace('/acquisitions', '%2Facquisitions'),
                self.path.replace(self.operation, '..'), self.path + '#fragment'):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 404)

    def test_removed_operation_and_legacy_profile_return_404(self):
        del self.service.operations[self.operation]
        self.assertEqual(self.request()[0], 404)
        # Original profiles without the projection must never synthesize it.
        prior = self.http.api.service
        self.http.api.service = object()
        try:
            self.assertEqual(self.request()[0], 404)
        finally:
            self.http.api.service = prior

    def test_failure_is_bounded_503_and_never_contains_private_reason(self):
        for fail in ('failure', 'causal_error', 'closed'):
            with self.subTest(fail=fail):
                if fail == 'failure':
                    self.service.failure = 'private/specimen/seed.txt'
                elif fail == 'causal_error':
                    self.service.kernel.causal_error = 'private/specimen/seed.txt'
                else:
                    self.service.stop_event.set()
                try:
                    self.assertEqual(self.request(), (503, {'error': 'service_unavailable'}))
                finally:
                    self.service.failure = self.service.kernel.causal_error = None
                    self.service.stop_event.clear()

    def test_concurrent_gets_are_read_only_and_do_not_delay_reserved_stop_admission(self):
        before = dict(self.service.operations[self.operation])
        errors = []
        def read():
            try:
                for _ in range(10):
                    if self.request()[0] != 200:
                        errors.append('HTTP failure')
            except Exception as error:
                errors.append(type(error).__name__)
        readers = [threading.Thread(target=read) for _ in range(3)]
        for thread in readers:
            thread.start()
        stop = self.service.request(API, 'command', dict(action='stop',
            parameters={}, expected_stop_generation=0))
        for thread in readers:
            thread.join(10)
            self.assertFalse(thread.is_alive())
        self.assertFalse(errors)
        self.assertEqual(self.service.operations[self.operation], before)
        self.assertEqual(self.service.safety.get_nowait()[-1], stop['operation_id'])


if __name__ == '__main__':
    unittest.main()
