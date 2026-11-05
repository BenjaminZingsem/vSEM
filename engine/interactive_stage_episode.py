"""Frontier-owned concurrent held-raster/stage variant;not runtime enabled.

The original namespaces remain unchanged. A stage move retains raster identity
and blanks its nominal cursor during actual movement,settling and source prep.
SETTINGS_APPLIED identifies source/pose binding as well as lens settings here.
"""
import math
from . import human_episode_types as t
from .interactive_paced_episode import GroundedEpisode as GridOwner
from .episode_credits import TERMINAL_PHYSICAL_RESERVE,APPLICATION_RESERVE
from .human_verified_episode import RECORD_LIMIT


def pose_configuration(configuration,pose):
    g=configuration.geometry
    return t.ScanConfiguration(t.EpisodeGeometry(g.width_px,g.height_px,g.field_width_m,
        pose[0],pose[1],g.offset_x_m,g.offset_y_m,pose[2]),configuration.dwell_ns)


def same_raster(a,b):
    x,y=a.geometry,b.geometry
    return (x.width_px,x.height_px,x.field_width_m,x.offset_x_m,x.offset_y_m,a.dwell_ns)==(
        y.width_px,y.height_px,y.field_width_m,y.offset_x_m,y.offset_y_m,b.dwell_ns)


class GroundedEpisode(GridOwner):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._stage_target_pose=None

    def _control(self,site,kind,body,*,at=None):
        if site!='session_ended':return super()._control(site,kind,body,at=at)
        key=(site,self._emergency_mode);count=self._sites.get(key,0)+1
        if count>2:raise RuntimeError('concurrent stage/raster terminal inventory exceeded')
        self._sites[key]=count
        self._emit(kind,body,self.now if at is None else at,
            self.emergency if self._emergency_mode else self._c,emergency=self._emergency_mode)

    def _rebind_target(self):
        target=self._stage_target_pose
        if target is None:return
        if self.pending is None:
            if self.session is None and self.capture is None:return
            slot=self.credits.reserve('A',APPLICATION_RESERVE)
            if slot is None:
                self._terminal('NUMERIC_BACKLOG_CAPACITY');return
            self.settings_generation+=1
            config=self.capture.configuration if self.capture else self.session['configuration']
            self.pending={'op':'source-stage-'+str(self.revision),'authority':self.session['authority'],
                'settings':self.applied,'generation':self.settings_generation,
                'due':min(self.now+t.MINIMUM_APPLICATION_NS,t.SAFE_INTEGER),
                'configuration':config,'ready':None,'slot':slot,'stage_only':True}
        pending=self.pending
        config=pose_configuration(pending['configuration'],target)
        if config!=pending['configuration']:
            pending['configuration']=config;pending['ready']=None
        if self.motion is not None:pending['due']=max(pending['due'],self.motion['settled'])
        if self.capture is not None and self.capture.hold is None:
            if self.capture.records>=RECORD_LIMIT:
                self._end_capture(self.capture,self.now,'CAPTURE_RECORD_LIMIT')
            else:self._hold_start(self.capture,self.now,self._r)

    def _move(self,intent,stop_valid):
        reason=None
        if self._emergency_mode or self.interlock is not None:reason=self.interlock or 'NUMERIC_BACKLOG_CAPACITY'
        elif not self._authorized(intent.authority):reason='UNAUTHORIZED'
        elif stop_valid:reason='STOP'
        elif intent.expected_stop_generation!=self.stop_generation:reason='STOPPED_BEFORE_ADMISSION'
        elif intent.operation_id in self.ops:reason='DUPLICATE_OPERATION'
        elif self.motion is not None:reason='BUSY_SESSION'
        z=intent.z_m if type(intent) is t.MoveStageXYZ else self.stage_z
        duration=math.ceil(max(math.hypot(intent.x_m-self.stage_x,intent.y_m-self.stage_y)/.001,
            abs(z-self.stage_z)/.00002)*1e9)
        if reason is None:
            settings=(self.applied,) if self.pending is None else (self.applied,self.pending['settings'])
            if any(abs(s.focus_offset_m+z)>25e-6 for s in settings):reason='SOURCE_DOMAIN'
            elif self.now+duration+80_000_000>t.SAFE_INTEGER:reason='TIME_RANGE'
        needs_source=self.session is not None or self.capture is not None
        if reason is None and needs_source and self.pending is None and self.credits.free('A')<APPLICATION_RESERVE:
            self._terminal('NUMERIC_BACKLOG_CAPACITY');reason='NUMERIC_BACKLOG_CAPACITY'
        if reason is not None:
            self._disposition(intent,'REJECTED',reason);return
        problem=self._remember(intent.operation_id)
        if problem:
            self._terminal(problem);self._disposition(intent,'REJECTED',problem);return
        self.revision+=1
        terminal=self.credits.reserve('T',TERMINAL_PHYSICAL_RESERVE)
        if terminal is None:
            self._terminal('NUMERIC_BACKLOG_CAPACITY');self._disposition(intent,'REJECTED','NUMERIC_BACKLOG_CAPACITY');return
        xyz=type(intent) is t.MoveStageXYZ;moving_end=self.now+duration;settled=moving_end+80_000_000
        if xyz:body=(intent.operation_id,self.stage_x,self.stage_y,self.stage_z,intent.x_m,intent.y_m,z,moving_end,settled)
        else:body=(intent.operation_id,self.stage_x,self.stage_y,intent.x_m,intent.y_m,moving_end,settled)
        self._emit('MOTION_XYZ_START' if xyz else 'MOTION_START',body,self.now,self._r)
        self.motion={'op':intent.operation_id,'x0':self.stage_x,'y0':self.stage_y,'z0':self.stage_z,
            'x':intent.x_m,'y':intent.y_m,'z':z,'xyz':xyz,'start':self.now,'moving_end':moving_end,
            'settled':settled,'last':self.now,'terminal':terminal}
        if needs_source or self.pending is not None:
            self._stage_target_pose=(intent.x_m,intent.y_m,z);self._rebind_target()
        self._disposition(intent,'ACCEPTED','OK')

    def _normal(self,intent,stop_valid):
        if type(intent) in (t.MoveStage,t.MoveStageXYZ):return self._move(intent,stop_valid)
        super()._normal(intent,stop_valid)
        accepted=intent is not None and any(f.kind=='DISPOSITION' and f.body[3]==type(intent).__name__ and f.body[:2] in (
            (intent.operation_id,'ACCEPTED'),(intent.operation_id,'SATISFIED_NO_CHANGE')) for f in self._facts)
        if accepted and type(intent) in (t.SetOptics,t.ConfigureLive):self._rebind_target()

    def _progress_motion(self,terminal_reason):
        previous=self.motion
        super()._progress_motion(terminal_reason)
        if previous is None or self.motion is not None:return
        ended=next(f for f in reversed(self._facts) if f.kind in ('MOTION_END','MOTION_XYZ_END') and f.body[0]==previous['op'])
        if ended.body[-1]=='COMPLETED':return
        # A cancelled trajectory cannot bind a bank at the unreached target.
        self._stage_target_pose=None
        if self.pending is not None:
            if self.pending.get('stage_only'):self._retire_target('MOTION_CANCELLED')
            else:
                self.pending['configuration']=pose_configuration(self.pending['configuration'],(self.stage_x,self.stage_y,self.stage_z))
                self.pending['ready']=None

    def _apply(self,stop_valid):
        pending=self.pending
        if (stop_valid or self.interlock is not None or self.motion is not None or pending is None or
            pending['ready'] is None or self.now<pending['due'] or not self._authorized(pending['authority'])):return
        handle=pending['ready'];capture=self.capture
        pose=(self.stage_x,self.stage_y,self.stage_z);g=handle.geometry
        if ((g.stage_x_m,g.stage_y_m,g.stage_z_m)!=pose or
            handle.geometry!=pending['configuration'].geometry or handle.settings!=pending['settings']):
            self._terminal('CAUSAL_FAILURE');return
        if capture is not None:
            if capture.records>=RECORD_LIMIT:
                self._end_capture(capture,self.now,'CAPTURE_RECORD_LIMIT');capture=None
            elif not same_raster(capture.configuration,pending['configuration']):
                self._terminal('CAUSAL_FAILURE');return
        if capture is not None:self._hold_end(capture,self.now,self._r)
        generation=self.applied_generation+1
        self._emit('SETTINGS_APPLIED',(pending['op'],self.applied,handle.settings,generation,handle,
            capture.identity if capture else None,capture.elapsed if capture else None),self.now,pending['slot'])
        self.credits.release(pending['slot'])
        self.applied,self.bank,self.applied_generation=handle.settings,handle,generation
        self.pending=None;self._stage_target_pose=None;self.revision+=1
        if capture is not None:
            capture.configuration=pending['configuration'];capture.handle=handle;capture.label=pending['op'];capture.records+=1
        if self.session is not None:
            self.session['configuration']=pose_configuration(self.session['configuration'],pose)
            self.requested=self.session['configuration']
