"""Independent certificate extension for immediate live-grid interruption.

No authoritative owner import/replay or numerical prediction. Original counted
reservations,ordered admission,integer exposure and actual delivery attestation
are retained. This new variant is not enabled by the original runtime.
"""
from engine import human_episode_types as t
from .human_paced_verifier import PacedCausalVerifier as OriginalVerifier
from .human_causal_verifier import same


class PacedCausalVerifier(OriginalVerifier):
    def _end_capture(self,event,reason):
        if not getattr(self,'_switching_grid',False):return super()._end_capture(event,reason)
        c=self.capture
        self._hold(False,event,c['terminal'])
        self._record('RASTER_END',(c['id'],c['elapsed'],c['nominal'],c['total'],reason),event,c['terminal'])
        self.ended.append(c['id']);self.last_capture_total=c['total']
        self.budget.release(c['terminal']);self.capture=None
        self.last_ended=(c['id'],self.expected[-1].ordinal,self.session['generation'])

    def _normal_command(self,command,stop_valid):
        previous=self.session
        prior=previous['config'] if previous is not None else None
        super()._normal_command(command,stop_valid)
        if type(command) is not t.ConfigureLive or self.session is not previous or previous is None:return
        admitted=any(f.kind=='DISPOSITION' and f.body[:2]==(command.operation_id,'ACCEPTED') and f.body[3]=='ConfigureLive' for f in self.expected)
        if not admitted or same(self.session['config'],prior):return
        if self.capture is not None:
            self._switching_grid=True
            try:self._end_capture(self.now,'GEOMETRY_CHANGED')
            finally:self._switching_grid=False
        if self.target is not None:
            self.target['config']=self.session['config'];self.target['ready']=None

    def _bank_result(self,result):
        if (result is not None and self.job is not None and same(result.ticket,self.job) and
            self.job.purpose=='SETTINGS' and self.target is not None and
            not same(self.job.configuration,self.target['config'])):
            self.job=None
            return
        return super()._bank_result(result)
