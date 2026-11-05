"""Observable-only HTTP client; no imports from engine or private runtime.

The administrator supplies API origin/token. Never give an evaluated operator
the server filesystem or the administrator's connection.json (which also holds
the separate human invitation). This example is for trusted development.
"""
import argparse
import http.client
import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit


class InstrumentClient:
    def __init__(self, origin, token):
        url = urlsplit(origin)
        if url.scheme != 'http' or url.hostname != '127.0.0.1' or url.path or url.query or url.fragment:
            raise ValueError('Explicit loopback HTTP origin required')
        self.port, self.token = url.port, token
        self.stop_renewal = threading.Event()
        self.renewal = None
        self.renewal_error = None

    def request(self, path, value=None, raw=False):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=30)
        try:
            headers = {'Authorization':'Bearer '+self.token}
            payload = None if value is None else json.dumps(value)
            if payload is not None: headers['Content-Type'] = 'application/json'
            connection.request('GET' if value is None else 'POST', path, payload, headers)
            response = connection.getresponse()
            data = response.read()
            if response.status not in (200,202):
                raise RuntimeError('HTTP '+str(response.status)+': '+data.decode('utf-8','replace'))
            return data if raw else json.loads(data)
        finally:
            connection.close()

    def wait_operation(self, operation, timeout=300):
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            if self.renewal_error: raise RuntimeError('Control renewal failed') from self.renewal_error
            value = self.request('/operation/'+operation['operation_id'])
            if value['status'] == 'COMPLETED': return value
            if value['status'] in ('REJECTED','CANCELLED','UNKNOWN'):
                raise RuntimeError('Operation did not complete: '+json.dumps(value))
            time.sleep(.1)
        raise TimeoutError('Operation still pending; inspect state, do not blindly resubmit')

    def acquire_control(self):
        self.wait_operation(self.request('/lease', {}))
        if self.renewal is not None: return
        def renew():
            while not self.stop_renewal.wait(5):
                try: self.wait_operation(self.request('/lease', {}), 20)
                except Exception as exc:
                    self.renewal_error = exc
                    return
        self.renewal = threading.Thread(target=renew, daemon=True)
        self.renewal.start()

    def command(self, action, parameters):
        state = self.request('/state')
        return self.request('/command', {'action':action,'parameters':parameters,
            'expected_stop_generation':state['stop_generation']})

    def wait_image(self, source_id=None, previous=None, timeout=1800):
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            if self.renewal_error: raise RuntimeError('Control renewal failed') from self.renewal_error
            state = self.request('/state')
            if state['availability'] == 'QUARANTINED': raise RuntimeError('Instrument quarantined')
            image = state.get('latest_image')
            if (image and image['outcome']=='COMPLETED' and image['image_id']!=previous
                    and (source_id is None or image['source_id']==source_id)):
                return image
            time.sleep(.2)
        raise TimeoutError('Image not yet delivered; slower accurate rendering is allowed')

    def close(self):
        self.stop_renewal.set()
        if self.renewal: self.renewal.join(35)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', default=os.environ.get('VSEM_API_ORIGIN'))
    parser.add_argument('--output', required=True, help='New directory for acquired counts and metadata')
    parser.add_argument('--pixels', type=int, choices=(64,128,256,512,1024), default=1024)
    args = parser.parse_args()
    client = InstrumentClient(args.origin, os.environ['VSEM_API_TOKEN'])
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    owned = False
    try:
        client.acquire_control()
        owned = True
        state = client.request('/state')
        previous = (state.get('latest_image') or {}).get('image_id')
        operation = client.command('scan_single', {'width_px':args.pixels,'height_px':args.pixels,
            'field_width_m':2e-6,'offset_x_m':0.,'offset_y_m':0.,'dwell_ns':20000})
        client.wait_operation(operation, 1800)
        image = client.wait_image(previous=previous)
        raw = client.request('/image/'+image['image_id']+'/SE', raw=True)
        if len(raw)!=args.pixels**2*4: raise ValueError('Incomplete acquired count plane')
        (output/'SE.uint32').write_bytes(raw)
        (output/'metadata.json').write_text(json.dumps(image,indent=2)+'\n',encoding='utf-8')
        print('Saved acquired SE counts and observable metadata to '+str(output))
    finally:
        try:
            if owned: client.wait_operation(client.command('stop', {}))
        finally:
            client.close()


if __name__ == '__main__':
    main()
