"""Independent counted certificate for concurrent mechanical/raster evolution.

No authoritative owner import,execution,replay or predicted image response.
The certificate admits stage motion during a session and holds the nominal
raster cursor until a source bound to actual settled coordinates is applied.
"""
from engine import human_episode_types as t
from .interactive_paced_verifier import PacedCausalVerifier as GridVerifier
from .human_causal_verifier import same,RECORD_LIMIT,APPLICATION_DELAY


def rebound(configuration,position):
    g=configuration.geometry
    return t.ScanConfiguration(t.EpisodeGeometry(g.width_px,g.height_px,g.field_width_m,
        *position[:2],g.offset_x_m,g.offset_y_m,position[2]),configuration.dwell_ns)


def raster_key(configuration):
    g=configuration.geometry
    return (g.width_px,g.height_px,g.field_width_m,g.offset_x_m,g.offset_y_m,configuration.dwell_ns)


class PacedCausalVerifier(GridVerifier):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.motion_binding=None

    def _control(self,kind,body,event=None):
        if kind!='SESSION_ENDED':return super()._control(kind,body,event)
        tag=(kind,self.emode);self.sites[tag]=self.sites.get(tag,0)+1
        if self.sites[tag]>2:raise ValueError('Certificate simultaneous terminal inventory exceeded')
        self._record(kind,body,self.now if event is None else event,
            self.emergency if self.emode else self.creserve,self.emode)

    def _bind_motion(self):
        if self.motion_binding is None:return
        if self.target is None:
            if self.capture is None and self.session is None:return
            slot=self.budget.take('A',1)
            if slot is None:self._interlock('NUMERIC_BACKLOG_CAPACITY');return
            self.settings_generation+=1
            config=self.capture['config'] if self.capture is not None else self.session['config']
            self.target={'op':'source-stage-'+str(self.revision),'authority':self.session['authority'],
                'settings':self.applied,'generation':self.settings_generation,'due':min(self.now+APPLICATION_DELAY,t.SAFE_INTEGER),
                'config':config,'ready':None,'slot':slot,'stage_only':True}
        new_config=rebound(self.target['config'],self.motion_binding)
        if not same(new_config,self.target['config']):
            self.target['config']=new_config;self.target['ready']=None
        if self.motion is not None:self.target['due']=max(self.target['due'],self.motion['settled'])
        if self.capture is not None and self.capture['hold'] is None:
            if self.capture['records']>=RECORD_LIMIT:self._end_capture(self.now,'CAPTURE_RECORD_LIMIT')
            else:self._hold(True,self.now,self.rreserve)

    def _move_command(self,command,stop_valid):
        cls=type(command);reason=None
        predicates=((self.emode or self.interlock is not None,self.interlock or 'NUMERIC_BACKLOG_CAPACITY'),
            (not self._authorized(command.authority),'UNAUTHORIZED'),(stop_valid,'STOP'),
            (command.expected_stop_generation!=self.stop_generation,'STOPPED_BEFORE_ADMISSION'),
            (command.operation_id in self.operations,'DUPLICATE_OPERATION'),(self.motion is not None,'BUSY_SESSION'))
        for failed,label in predicates:
            if failed:reason=label;break
        target=(command.x_m,command.y_m,command.z_m if cls is t.MoveStageXYZ else self.pose[2])
        duration=self._motion_ns(command)
        if reason is None:
            optics=(self.applied,) if self.target is None else (self.applied,self.target['settings'])
            if any(abs(s.focus_offset_m+target[2])>25e-6 for s in optics):reason='SOURCE_DOMAIN'
            elif self.now+duration+80_000_000>t.SAFE_INTEGER:reason='TIME_RANGE'
        needs_bank=self.capture is not None or self.session is not None
        if reason is None and needs_bank and self.target is None and self.budget.free('A')<1:
            self._interlock('NUMERIC_BACKLOG_CAPACITY');reason='NUMERIC_BACKLOG_CAPACITY'
        if reason is not None:self._disposition(command,reason,'REJECTED');return
        problem=self._remember(command.operation_id)
        if problem:self._interlock(problem);self._disposition(command,problem,'REJECTED');return
        self.revision+=1;terminal=self.budget.take('T',7)
        if terminal is None:
            self._interlock('NUMERIC_BACKLOG_CAPACITY');self._disposition(command,'NUMERIC_BACKLOG_CAPACITY','REJECTED');return
        end=self.now+duration;settled=end+80_000_000;xyz=cls is t.MoveStageXYZ
        body=(command.operation_id,*self.pose,*target,end,settled) if xyz else (command.operation_id,*self.pose[:2],*target[:2],end,settled)
        self._record('MOTION_XYZ_START' if xyz else 'MOTION_START',body,self.now,self.rreserve)
        self.motion={'op':command.operation_id,'start':self.pose,'target':target,'xyz':xyz,'origin':self.now,
            'moving_end':end,'settled':settled,'last':self.now,'terminal':terminal}
        if needs_bank or self.target is not None:self.motion_binding=target;self._bind_motion()
        self._disposition(command)

    def _normal_command(self,command,stop_valid):
        if type(command) in (t.MoveStage,t.MoveStageXYZ):return self._move_command(command,stop_valid)
        super()._normal_command(command,stop_valid)
        admitted=command is not None and any(f.kind=='DISPOSITION' and f.body[3]==type(command).__name__ and f.body[:2] in (
            (command.operation_id,'ACCEPTED'),(command.operation_id,'SATISFIED_NO_CHANGE')) for f in self.expected)
        if admitted and type(command) in (t.SetOptics,t.ConfigureLive):self._bind_motion()

    def _advance(self,reason=None):
        concurrent=self.capture is not None;previous=self.motion
        super()._advance(reason)
        if concurrent and self.motion is not None:
            m=self.motion;event=self.now;why=reason
            if self.lease is not None and (self.lease.expires_ns<event or self.lease.expires_ns==event and why!='STOP'):
                event,why=self.lease.expires_ns,'EXPIRED'
            if m['settled']<event or m['settled']==event and why is None:event,why=m['settled'],'COMPLETED'
            if event>=m['moving_end'] or m['moving_end']==m['origin']:position=m['target']
            else:
                fraction=(event-m['origin'])/(m['moving_end']-m['origin'])
                position=tuple(a+fraction*(b-a) for a,b in zip(m['start'],m['target']))
            reserve=m['terminal'] if why is not None else self.rreserve
            if event!=m['last']:
                phase='SETTLING' if event>=m['moving_end'] else 'MOVING'
                body=(m['op'],*self.pose,*position,phase) if m['xyz'] else (m['op'],*self.pose[:2],*position[:2],phase)
                self._record('MOTION_XYZ_ADVANCE' if m['xyz'] else 'MOTION_ADVANCE',body,event,reserve)
                self.pose,m['last']=position,event
            if why is not None:
                body=(m['op'],*self.pose,why) if m['xyz'] else (m['op'],*self.pose[:2],why)
                self._record('MOTION_XYZ_END' if m['xyz'] else 'MOTION_END',body,event,reserve)
                self.budget.release(m['terminal']);self.motion=None
                self._control('SESSION_ENDED',(m['op'],why,None))
        if previous is None or self.motion is not None:return
        ended=next(f for f in reversed(self.expected) if f.kind in ('MOTION_END','MOTION_XYZ_END') and f.body[0]==previous['op'])
        if ended.body[-1]=='COMPLETED':return
        self.motion_binding=None
        if self.target is not None:
            if self.target.get('stage_only'):self._retire('MOTION_CANCELLED')
            else:self.target['config']=rebound(self.target['config'],self.pose);self.target['ready']=None

    def _application(self,stop_valid):
        target=self.target
        if (stop_valid or self.interlock is not None or self.motion is not None or target is None or
            target['ready'] is None or self.now<target['due'] or not self._authorized(target['authority'])):return
        handle=target['ready'];g=handle.geometry;c=self.capture
        if ((g.stage_x_m,g.stage_y_m,g.stage_z_m)!=self.pose or not same(handle.geometry,target['config'].geometry)
            or not same(handle.settings,target['settings'])):self._interlock('CAUSAL_FAILURE');return
        if c is not None:
            if c['records']>=RECORD_LIMIT:self._end_capture(self.now,'CAPTURE_RECORD_LIMIT');c=None
            elif raster_key(c['config'])!=raster_key(target['config']):self._interlock('CAUSAL_FAILURE');return
        if c is not None:self._hold(False,self.now,self.rreserve)
        self.applied_generation+=1
        self._record('SETTINGS_APPLIED',(target['op'],self.applied,handle.settings,self.applied_generation,handle,
            c['id'] if c else None,c['elapsed'] if c else None),self.now,target['slot'])
        self.budget.release(target['slot']);self.applied,self.bank=handle.settings,handle
        self.target=None;self.motion_binding=None;self.revision+=1
        if c is not None:
            c['config'],c['handle'],c['label'],c['records']=target['config'],handle,target['op'],c['records']+1
        if self.session is not None:
            self.session['config']=rebound(self.session['config'],self.pose);self.requested=self.session['config']
