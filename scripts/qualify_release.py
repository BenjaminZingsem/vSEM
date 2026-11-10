"""Administrator-run GPU acceptance through actual public HTTP, with owned cleanup.

No hidden specimen fields are used to operate the instrument. Run on a dedicated
GPU with VSEM_GPU_UUID set. Results/logs/counts stay outside version control.
"""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from examples.agent_client import InstrumentClient


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalogue-directory',required=True)
    parser.add_argument('--catalogue-manifest-sha256',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    directory=Path(args.output).absolute();directory.mkdir(mode=0o700,parents=True,exist_ok=False)
    log=os.fdopen(os.open(directory/'service.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb')
    process=subprocess.Popen([sys.executable,'-B','-m','runtime.serve','--no-world-generation',
        '--catalogue-directory',str(Path(args.catalogue_directory).resolve()),
        '--catalogue-manifest-sha256',args.catalogue_manifest_sha256,
        '--run-directory',str(directory/'service'),'--ui-port','0','--api-port','0'],
        cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
    client=None;result={'status':'RUNNING','checks':{},'images':{}}
    children=[]
    try:
        connection=directory/'service/connection.json';deadline=time.monotonic()+900
        while not connection.exists():
            if process.poll() is not None: raise RuntimeError('Startup failed; inspect private service.log')
            if time.monotonic()>deadline: raise TimeoutError('Startup did not complete')
            time.sleep(.2)
        credentials=json.loads(connection.read_bytes())
        children=Path('/proc/'+str(process.pid)+'/task/'+str(process.pid)+'/children').read_text().split()
        client=InstrumentClient(credentials['api_origin'],credentials['api_token'])
        # A transport-level refusal, before any command or control acquisition.
        c=http.client.HTTPConnection('127.0.0.1',client.port,timeout=10)
        c.request('GET','/state');r=c.getresponse();r.read();assert r.status==401;c.close()
        client.acquire_control();result['checks']['separate_authenticated_api']=True
        def wait(condition,timeout=600):
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                state=client.request('/state')
                if state['availability']=='QUARANTINED':raise RuntimeError('quarantined')
                if condition(state):return state
                time.sleep(.05)
            raise TimeoutError('Observable condition not reached')
        def optics(focus=0.,sx=0.,sy=0.):
            client.wait_operation(client.command('optics',{'current_pA':100,
                'focus_offset_m':focus,'stigmator_x':sx,'stigmator_y':sy}))
        def stage(x=0.,y=0.,z=0.):
            client.wait_operation(client.command('stage_move',{'x_m':x,'y_m':y,'z_m':z}))
        def scan(name,pixels=64,width=2e-6,offset=0.,during=None):
            prior=(client.request('/state').get('latest_image') or {}).get('image_id')
            begun=time.monotonic()
            op=client.command('scan_single',{'width_px':pixels,'height_px':pixels,'field_width_m':width,
                'offset_x_m':offset,'offset_y_m':0.,'dwell_ns':20000})
            if during:
                wait(lambda s:s.get('progress') and s['progress']['completed_pixels']>pixels*pixels//5
                     and s['progress']['completed_pixels']<pixels*pixels*4//5)
                during()
            client.wait_operation(op,1800)
            meta=client.wait_image(previous=prior,timeout=1800)
            raw=client.request('/image/'+meta['image_id']+'/SE',raw=True)
            assert len(raw)==pixels*pixels*4 and meta['completed_pixels']==pixels*pixels
            assert meta['cut_elapsed_ns']>=pixels*pixels*20000
            assert meta['width_px']==pixels and meta['field_width_m']==width
            serialized=json.dumps(meta)+json.dumps(client.request('/state'))
            for forbidden in ('ideal_focus','world_height','expected_rate','source_binding','solver','seed'):
                assert forbidden not in serialized,forbidden
            (directory/(name+'.uint32')).write_bytes(raw)
            (directory/(name+'.json')).write_text(json.dumps(meta,indent=2)+'\n')
            array=np.frombuffer(raw,dtype='<u4').reshape(pixels,pixels).astype(float)
            result['images'][name]={'sha256':hashlib.sha256(raw).hexdigest(),'pixels':pixels,
                'mean':float(array.mean()),'std':float(array.std()),'seconds':time.monotonic()-begun,
                'segments':len(meta['parameter_segments'])}
            print(json.dumps({'image':name,**result['images'][name]}),flush=True)
            return array,meta
        focused,_=scan('focused')
        optics(15e-6);defocused,_=scan('defocused')
        assert focused.std()>defocused.std()*1.05,'visible focus contrast required'
        optics();stage(z=15e-6);height,_=scan('height_defocused')
        assert focused.std()>height.std()*1.05,'stage Z must change focus'
        stage();optics(sx=.8,sy=.4);stig,_=scan('astigmatic')
        assert np.mean((stig-focused)**2)>max(1.,2*focused.mean()),'stigmation must alter signal beyond shot noise'
        optics();stage(x=.25e-6,y=-.125e-6);shifted,_=scan('stage_shift')
        # HFW=2um/64: +250nm X and -125nm Y move features left8/up4.
        # Image row zero is at positive specimen Y. Check that exact sign/scale.
        correlation=float(np.corrcoef(focused[4:,8:].ravel(),shifted[:-4,:-8].ravel())[0,1])
        unshifted=float(np.corrcoef(focused.ravel(),shifted.ravel())[0,1])
        assert correlation>unshifted+.1 and correlation>.6,'signed stage image displacement required'
        result['stage_shift_correlation']=correlation
        stage();zoom,_=scan('zoomed',width=1e-6)
        assert np.mean((zoom-focused)**2)>2*focused.mean(),'physical zoom must change acquired content'
        scan('roi',width=.5e-6,offset=.25e-6)
        _,meta=scan('native1024_mid_scan_focus',pixels=1024,during=lambda:optics(15e-6))
        segments=meta['parameter_segments']
        assert any(s['focus_offset_m']==0. for s in segments)
        assert any(s['focus_offset_m']==15e-6 for s in segments)
        assert any(s['focus_offset_m']==15e-6 and s['end_elapsed_ns']>s['start_elapsed_ns'] for s in segments)
        client.wait_operation(client.command('stop',{}))
        wait(lambda s:s['beam_blank'])
        result['checks'].update(visible_focus=True,stage_z_prefocus=True,stigmation_signal=True,
            stage_displacement=True,zoom=True,roi_acquisition=True,native1024=True,
            within_raster_parameter_segments=True,observable_boundary=True,stop_beam_blank=True)
        result['status']='PASS'
    finally:
        if client:client.close()
        if process.poll() is None:process.terminate()
        try:process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            result['status']='FAILED_OWNED_CLEANUP'
            raise RuntimeError('Owned launcher did not close; inspect before any relaunch')
        finally:log.close()
        result['launcher_exit_code']=process.returncode
        result['owned_children_absent']=all(not Path('/proc/'+pid).exists() for pid in children)
        if process.returncode!=0 or not result['owned_children_absent']:result['status']='FAILED_OWNED_CLEANUP'
        (directory/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    assert result['status']=='PASS',result
    print(json.dumps({'status':'PASS','report':str(directory/'result.json')}),flush=True)


if __name__=='__main__':main()
