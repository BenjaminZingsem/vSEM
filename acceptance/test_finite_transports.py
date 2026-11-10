"""Actual autonomous causal/count service and distinct HTTP credential tests."""
import os
import http.client
import json
from pathlib import Path
import tempfile
import time
import unittest

from functools import partial
from runtime.core_human_service import GUI,API
from runtime.finite_human_service import FiniteHumanService
from runtime.finite_launch_spec import FrozenFiniteLaunch
ROOT=Path(__file__).resolve().parents[1]
from runtime.hierarchical_http import HierarchicalHTTP as CoreHTTP


@unittest.skipUnless(os.environ.get('VSEM_TEST_CATALOGUE'), 'explicit GPU/catalogue integration test')
class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='vsem-core-http-')
        cls.service = FiniteHumanService(Path(cls.temp.name)/'episode', finite_catalogue=FrozenFiniteLaunch(
            os.environ['VSEM_TEST_CATALOGUE'], os.environ['VSEM_TEST_CATALOGUE_SHA256']))
        cls.http = CoreHTTP(cls.service)
    @classmethod
    def tearDownClass(cls):
        cls.http.close();cls.service.close();cls.temp.cleanup()
    def request(self,server,path,method='GET',body=None,headers=None):
        connection = http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
        payload = json.dumps(body) if body is not None else None
        supplied = dict(headers or {})
        if body is not None:supplied['Content-Type']='application/json'
        connection.request(method,path,payload,supplied);response = connection.getresponse()
        data = response.read();result = response.status,dict(response.getheaders()),data
        connection.close();return result
    def bearer(self):return {'Authorization':'Bearer '+self.http.api.token}
    def browser(self):return {'Cookie':'vsem_core='+self.http.ui.session,'Origin':self.http.ui.origin,'X-CSRF-Token':self.http.ui.csrf}
    def operation(self,record,timeout=10):
        deadline = time.perf_counter()+timeout
        while time.perf_counter()<deadline:
            result = self.service.operation(record['operation_id'])
            if result['status'] in ('COMPLETED','REJECTED','CANCELLED'):return result
            time.sleep(.01)
        self.fail('actual operation did not finish')
    def test_api_credentials_do_not_authenticate_gui(self):
        self.assertEqual(self.request(self.http.ui,'/state',headers=self.bearer())[0],403)
        self.assertEqual(self.request(self.http.ui,'/state')[0],401)
    def test_gui_cookie_origin_never_authenticates_api(self):
        self.assertEqual(self.request(self.http.api,'/state',headers=self.browser())[0],401)
        self.assertEqual(self.request(self.http.api,'/state')[0],401)
        headers=self.bearer();headers['Origin']=self.http.ui.origin
        self.assertEqual(self.request(self.http.api,'/state',headers=headers)[0],401)
    def test_gui_requires_invitation_session_origin_csrf(self):
        status,headers,_=self.request(self.http.ui,'/open/'+self.http.ui.invitation)
        self.assertEqual(status,303);self.assertIn('HttpOnly',headers['Set-Cookie'])
        self.assertEqual(self.request(self.http.ui,'/open/'+self.http.ui.invitation)[0],403)
        headers=self.browser();del headers['X-CSRF-Token']
        self.assertEqual(self.request(self.http.ui,'/lease','POST',{},headers)[0],403)
        headers=self.browser();headers['Origin']='http://attacker.invalid'
        self.assertEqual(self.request(self.http.ui,'/lease','POST',{},headers)[0],403)
    def test_host_path_and_unknown_truth_routes_are_closed(self):
        self.assertEqual(self.request(self.http.api,'/state',headers={**self.bearer(),'Host':'attacker.invalid'})[0],401)
        for path in ('/truth','/admin','/image/../seed','/state?seed=1','/owner.cells'):
            self.assertEqual(self.request(self.http.api,path,headers=self.bearer())[0],404)
    def test_unknown_command_identity_and_provider_fields_are_rejected(self):
        good={'action':'stop','parameters':{},'expected_stop_generation':0}
        for field in ('holder_id','source','seed','ideal_focus','provider','role'):
            value={**good,field:'forged'}
            self.assertEqual(self.request(self.http.api,'/command','POST',value,self.bearer())[0],400)
    def test_quarantined_service_cannot_acknowledge_new_admission(self):
        prior=self.service.failure
        try:
            self.service.failure='service_unavailable'
            before=len(self.service.operations)
            with self.assertRaisesRegex(BufferError,'service_unavailable'):
                self.service.request(API,'lease')
            self.assertEqual(len(self.service.operations),before)
            self.assertEqual(self.service.snapshot(API)['availability'],'QUARANTINED')
        finally:self.service.failure=prior
    def test_actual_api_live_acquisition_evolves_without_requests_and_stop(self):
        status,_,raw=self.request(self.http.api,'/lease','POST',{},self.bearer())
        self.assertEqual(status,202);self.assertEqual(self.operation(json.loads(raw))['status'],'COMPLETED')
        scan={'action':'scan_live','parameters':{'width_px':64,'height_px':64,'field_width_m':1e-6,
            'offset_x_m':0.,'offset_y_m':0.,'dwell_ns':20000},'expected_stop_generation':0}
        self.assertEqual(self.request(self.http.api,'/command','POST',scan,self.bearer())[0],202)
        # No HTTP request drives the service/owner. Allow real cached counts.
        deadline=time.perf_counter()+15
        while time.perf_counter()<deadline and self.service.latest_image is None:time.sleep(.02)
        self.assertIsNotNone(self.service.latest_image)
        before=self.service.snapshot(API)['episode_incident_pA_ns'];time.sleep(.5)
        after=self.service.snapshot(API)['episode_incident_pA_ns'];self.assertGreater(after,before)
        state=self.service.snapshot(API);self.assertTrue(state['control_owned'])
        denied=self.request(self.http.ui,'/command','POST',{'action':'stop','parameters':{},'expected_stop_generation':state['stop_generation']},self.browser())
        self.assertEqual(denied[0],202);self.assertEqual(self.operation(json.loads(denied[2]))['reason'],'control_not_owned')
        status,_,raw=self.request(self.http.api,'/command','POST',{'action':'stop','parameters':{},'expected_stop_generation':state['stop_generation']},self.bearer())
        self.assertEqual(status,202);self.assertEqual(self.operation(json.loads(raw))['status'],'COMPLETED')
        state=self.service.snapshot(API);self.assertTrue(state['beam_blank'])
        self.assertGreater(state['causal_verified_ordinal'],0)
        self.assertGreater(state['numerical_verified_ordinal'],0)
        serialized=json.dumps(state)
        for word in ('seed','ideal_focus','world_height','solver','descriptor','expected_rate','source_binding','pid'):
            self.assertNotIn(word,serialized)
        image=state['latest_image'];status,_,raw=self.request(self.http.api,'/image/'+image['image_id']+'/SE',headers=self.bearer())
        self.assertEqual(status,200);self.assertEqual(len(raw),64*64*4)

    def test_actual_live_configure_and_freeze_terminal_receipts(self):
        from examples.agent_client import InstrumentClient
        client=InstrumentClient(self.http.api.origin,self.http.api.token)
        acquired=False
        def wait(condition,timeout=600):
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                if client.renewal_error:raise RuntimeError('Lease renewal failed') from client.renewal_error
                state=client.request('/state')
                self.assertNotEqual(state.get('phase'),'INTERLOCKED')
                self.assertNotEqual(state.get('availability'),'QUARANTINED')
                if condition(state):return state
                time.sleep(.05)
            self.fail('Actual live observable condition did not finish')
        try:
            client.acquire_control();acquired=True
            client.wait_operation(client.command('optics',dict(current_pA=50,
                focus_offset_m=0.,stigmator_x=0.,stigmator_y=0.)),600)
            live=client.command('scan_live',dict(width_px=64,height_px=64,field_width_m=2e-6,
                offset_x_m=0.,offset_y_m=0.,dwell_ns=1000000))
            state=wait(lambda s:s.get('progress') and s['progress']['completed_pixels']>0
                and s.get('current_scan') and s['current_scan']['width_px']==64)
            generation=state['stop_generation']
            config=client.command('configure_live',dict(width_px=128,height_px=128,field_width_m=2e-6,
                offset_x_m=0.,offset_y_m=0.,dwell_ns=100000))
            client.wait_operation(config,600)
            state=wait(lambda s:s.get('progress') and s['progress']['completed_pixels']>0
                and s.get('current_scan') and s['current_scan']['width_px']==128)
            before_freeze=state['observed_at_ns'];source=state['live_source_id']
            frozen=client.command('freeze',{'source_id':source})
            client.wait_operation(frozen,600)
            client.wait_operation(live,600)
            state=wait(lambda s:s.get('phase')=='STOPPED' and s['beam_blank']
                and s.get('live_source_id') is None)
            self.assertEqual(state['stop_generation'],generation)
            image=wait(lambda s:s.get('latest_image') and s['latest_image']['source_id']==source
                and s['latest_image']['outcome']=='COMPLETED'
                and s['latest_image']['width_px']==128
                and s['latest_image']['origin_ns']+s['latest_image']['cut_elapsed_ns']>=before_freeze)['latest_image']
            self.assertEqual(image['completed_pixels'],128*128)
            self.assertGreaterEqual(image['cut_elapsed_ns'],128*128*100000)
            raw=client.request('/image/'+image['image_id']+'/SE',raw=True)
            self.assertEqual(len(raw),128*128*4)
            for op in (config,frozen):
                receipt=client.request('/operation/'+op['operation_id'])
                self.assertEqual(receipt['status'],'COMPLETED')
            client.wait_operation(client.command('stop',{}),600)
            state=wait(lambda s:s['beam_blank'] and s['stop_generation']>generation)
            self.assertIsNone(state['live_source_id'])
            forbidden=('diagnostic_id','ticket_id','preparation-diagnostics','seed','world_height','ideal_focus')
            public=json.dumps(state)+json.dumps(image)
            for name in forbidden:self.assertNotIn(name,public)
        finally:
            try:
                if acquired:client.wait_operation(client.command('stop',{}),600)
            finally:client.close()


if __name__=='__main__':unittest.main()
