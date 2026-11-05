"""Transactional actual-pose source rebinding for the new interactive variant.

Old grounded ledgers are unchanged. This module retains the initial raster
geometry and requires mechanical facts to settle before changing its source.
StageBindingMixin is separately applicable to future causal material ledgers;
the included image ledger remains explicitly grounded and dose-independent.
"""
import math
from . import human_episode_types as t
from .human_fast_mapped_ledger import EpisodeExposureLedger as FullLedger
from .human_live_image_ledger import EpisodeExposureLedger as ImageLedger


def xyz(geometry):return (geometry.stage_x_m,geometry.stage_y_m,geometry.stage_z_m)


def grid(configuration):
    g=configuration.geometry
    return (g.width_px,g.height_px,g.field_width_m,g.offset_x_m,g.offset_y_m,configuration.dwell_ns)


class StageBindingMixin:
    def __init__(self,*args,initial_stage=(0.,0.,0.),**kwargs):
        if type(initial_stage) is not tuple or len(initial_stage)!=3:raise ValueError('explicit initial stage required')
        self.initial_stage=self.stage_pose=(t.real(initial_stage[0],-.025,.025),
            t.real(initial_stage[1],-.025,.025),t.real(initial_stage[2],-t.MAX_STAGE_Z_M,t.MAX_STAGE_Z_M))
        self.stage_motion=None
        super().__init__(*args,**kwargs)

    def _process(self,fact,transaction):
        kind,body=fact.kind,fact.body
        if kind in ('MOTION_START','MOTION_XYZ_START'):
            has_z=kind=='MOTION_XYZ_START'
            if has_z:op,x0,y0,z0,x,y,z,end,settled=body
            else:op,x0,y0,x,y,end,settled=body;z0=z=self.stage_pose[2]
            t.identity(op)
            target=(t.real(x,-.025,.025),t.real(y,-.025,.025),t.real(z,-t.MAX_STAGE_Z_M,t.MAX_STAGE_Z_M))
            expected=math.ceil(max(math.hypot(x-x0,y-y0)/.001,abs(z-z0)/.00002)*1e9)
            if (self.stage_motion is not None or (x0,y0,z0)!=self.stage_pose or
                fact.event_at_ns!=fact.issued_at_ns or end!=fact.event_at_ns+expected or settled!=end+80_000_000):
                raise ValueError('stage start predecessor/timing mismatch')
            motion=(op,self.stage_pose,target,fact.event_at_ns,end,settled,fact.event_at_ns,has_z)
            transaction.attr(self,'stage_motion',motion)
            if self.active is not None:transaction.attr(self.captures[self.active],'stage_needs_binding',True)
        elif kind in ('MOTION_ADVANCE','MOTION_XYZ_ADVANCE'):
            m=self.stage_motion
            if m is None:raise ValueError('stage advance without original trajectory')
            op,start,target,origin,end,settled,last,has_z=m
            if kind=='MOTION_XYZ_ADVANCE':identifier,*points,phase=body;old=tuple(points[:3]);position=tuple(points[3:])
            else:identifier,x0,y0,x,y,phase=body;old=(x0,y0,self.stage_pose[2]);position=(x,y,self.stage_pose[2])
            at=fact.event_at_ns
            expected=target if at>=end or end==origin else tuple(a+(at-origin)/(end-origin)*(b-a) for a,b in zip(start,target))
            expected_phase='SETTLING' if at>=end else 'MOVING'
            if (identifier!=op or has_z!=(kind=='MOTION_XYZ_ADVANCE') or old!=self.stage_pose or
                not last<at<=settled or position!=expected or phase!=expected_phase):
                raise ValueError('stage advance disagrees with actual linear trajectory')
            transaction.attr(self,'stage_pose',position)
            transaction.attr(self,'stage_motion',(op,start,target,origin,end,settled,at,has_z))
        elif kind in ('MOTION_END','MOTION_XYZ_END'):
            m=self.stage_motion
            if m is None:raise ValueError('stage end without trajectory')
            op,start,target,origin,end,settled,last,has_z=m
            if kind=='MOTION_XYZ_END':identifier,x,y,z,reason=body;position=(x,y,z)
            else:identifier,x,y,reason=body;position=(x,y,self.stage_pose[2])
            if (identifier!=op or has_z!=(kind=='MOTION_XYZ_END') or position!=self.stage_pose or
                fact.event_at_ns!=last or reason=='COMPLETED' and (last!=settled or position!=target)):
                raise ValueError('stage terminal pose/settlement mismatch')
            transaction.attr(self,'stage_motion',None)
        elif kind=='RASTER_START':
            if self.stage_motion is not None or xyz(body[6].geometry)!=self.stage_pose:
                raise ValueError('raster source not bound to actual stationary stage')
        elif kind=='PREFIX' and self.stage_motion is not None and body[5] is not True:
            raise ValueError('moving stage advanced beam-on raster cursor')
        elif kind=='SETTINGS_APPLIED':
            handle,identifier=body[4],body[5]
            if self.stage_motion is not None or xyz(handle.geometry)!=self.stage_pose:
                raise ValueError('source applied before actual stage settlement')
            if identifier is not None:
                capture=self.captures.get(identifier)
                if capture is None:raise ValueError('source rebind has no original capture')
                configuration=t.ScanConfiguration(handle.geometry,capture.config.dwell_ns)
                if grid(configuration)!=grid(capture.config):raise ValueError('source rebind changed raster grid')
                if xyz(capture.config.geometry)!=self.stage_pose:
                    if not capture.stage_needs_binding:raise ValueError('source position changed without original movement')
                    self._seal_fragment(transaction)
                    transaction.attr(capture,'config',configuration)
                transaction.attr(capture,'stage_needs_binding',False)
        super()._process(fact,transaction)
        if kind=='RASTER_START':
            capture=self.captures[body[0]]
            transaction.item(capture.__dict__,'initial_configuration',body[6])
            transaction.item(capture.__dict__,'stage_needs_binding',False)


class FullStageLedger(StageBindingMixin,FullLedger):pass


class EpisodeExposureLedger(StageBindingMixin,ImageLedger):
    def dose_snapshot(self):
        replay=FullStageLedger(self.science,self._initial_settings,episode_namespace=self.episode,
            seed=self.seed,bank_resolver=self.resolve,initial_stage=self.initial_stage)
        receipt=replay.ingest(tuple(self.facts[i] for i in range(1,self.last+1)))
        if receipt.status!='COMMITTED' or replay.total!=self.total:
            raise ValueError('actual-pose retained spatial-dose reconstruction failed')
        return replay.dose_snapshot()
