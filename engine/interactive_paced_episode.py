"""New immediate live-grid transition variant;not yet selected by a runtime.

Original admission,clock,Stop,lease,application and reservations are inherited.
An accepted changed live grid closes its actual partial raster immediately while
retaining the live session. The next raster still waits for actual old-cut
delivery and a correctly prepared new source. No old profile is relabelled.
"""
from .human_paced_episode import GroundedEpisode as PacedOwner
from .human_episode_types import ConfigureLive


class GroundedEpisode(PacedOwner):
    def _end_capture(self,capture,at,reason):
        if not getattr(self,'_switching_grid',False):
            return super()._end_capture(capture,at,reason)
        self._hold_end(capture,at,capture.terminal)
        self._emit('RASTER_END',(capture.identity,capture.elapsed,capture.nominal,
            capture.incident,reason),at,capture.terminal)
        self._ends.append(capture.identity)
        self.last_capture_incident=capture.incident
        self.credits.release(capture.terminal)
        self.capture=None
        # _emit does not return the fact;use the authoritative retained ordinal.
        ended=self._facts[-1]
        self.last_ended=(capture.identity,ended.ordinal,capture.session_generation)

    def _normal(self,intent,stop_valid):
        previous=self.session
        old=previous['configuration'] if previous is not None else None
        super()._normal(intent,stop_valid)
        if type(intent) is not ConfigureLive or self.session is not previous or previous is None:
            return
        accepted=any(f.kind=='DISPOSITION' and f.body[:2]==(intent.operation_id,'ACCEPTED') and f.body[3]=='ConfigureLive' for f in self._facts)
        if not accepted or self.session['configuration']==old:return
        if self.capture is not None:
            self._switching_grid=True
            try:self._end_capture(self.capture,self.now,'GEOMETRY_CHANGED')
            finally:self._switching_grid=False
        if self.pending is not None:
            self.pending['configuration']=self.session['configuration']
            self.pending['ready']=None

    def _result(self,result):
        if (result is not None and self.job is not None and result.ticket==self.job and
            self.job.purpose=='SETTINGS' and self.pending is not None and
            self.job.configuration!=self.pending['configuration']):
            # A genuine old-grid reply is obsolete,not a failure of the new grid.
            self.job=None
            return
        return super()._result(result)
