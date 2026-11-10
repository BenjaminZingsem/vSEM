"""Read-only Linux child identity and finite exit observation for qualification."""
from pathlib import Path
import time


def process_identity(pid):
    pid=int(pid)
    if pid<=0:raise ValueError('positive process ID required')
    try:raw=Path('/proc',str(pid),'stat').read_text()
    except FileNotFoundError:return None
    fields=raw[raw.rfind(')')+2:].split()
    return {'pid':pid,'birth':int(fields[19]),'state':fields[0]}


def observe_owned_exit(identities, timeout_s=5., *, reader=process_identity,
                       clock=time.monotonic, sleep=time.sleep):
    """Never kills/reaps a process or calls a present zombie absent."""
    if not 0<=timeout_s<=60:raise ValueError('finite observation deadline required')
    started=clock();deadline=started+timeout_s
    records=[{'pid':item['pid'],'birth':item['birth'],'states_seen':[]} for item in identities]
    while True:
        pending=False
        for record in records:
            if record.get('outcome') in ('ABSENT','PID_REUSED'):continue
            try:current=reader(record['pid'])
            except (OSError,ValueError,IndexError):
                current='UNKNOWN'
            if current is None:
                record['outcome']='ABSENT'
            elif current=='UNKNOWN':
                record['outcome']='UNKNOWN';pending=True
            elif current['birth']!=record['birth']:
                record['outcome']='PID_REUSED'
            else:
                record['outcome']='PRESENT';pending=True
                if current['state'] not in record['states_seen']:
                    record['states_seen'].append(current['state'])
        now=clock()
        if not pending or now>=deadline:
            return {'owned_children_absent':not pending,'wait_seconds':now-started,'children':records}
        sleep(min(.02,deadline-now))
