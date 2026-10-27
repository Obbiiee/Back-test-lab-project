"""New-family private orchestration. No HTTP-supplied frames or source paths."""
from contracts.primitives import require
from .observed_profile import ObservedExecutionProfile
from .observed_admission import AdmittedObservedSource
from .observed_kernel import apply,command_wire,seed_state


class ObservedExecutionController:
    def __init__(self,store,resolve_source):
        require(callable(resolve_source),'sourceResolver');self.store=store;self.resolve_source=resolve_source

    def _source(self,profile):
        source=self.resolve_source(profile.profile_hash)
        require(type(source) is AdmittedObservedSource and source.profile.profile_hash==profile.profile_hash,'source','REFUSED_OBSERVED_SOURCE_IDENTITY');source.assert_current();return source

    def create(self,scope,session_id,profile,policy,*,period,day=None,balance='10000'):
        require(type(profile) is ObservedExecutionProfile,'profile');source=self._source(profile);start=source.start_for_period(period,day=day)
        timeline=source.cache.new_timeline(scope,session_id,start)
        try:
            cp=timeline.checkpoint();state=seed_state(session_id,profile,policy,cp,balance);self.store.create(scope,state,cp);source.cache.seed(scope,session_id,timeline)
        except BaseException:timeline.close();raise
        return state

    def apply(self,scope,raw):
        command=command_wire(raw);before,prior=self.store.prepare(scope,command)
        if prior is not None:return prior
        state=before['state'];cp=before['controller'];kwargs={};replay=None
        if command['kind']=='ADVANCE':
            source=self._source(ObservedExecutionProfile.from_wire(state['profile']))
            frame,next_cp=source.cache.reveal(scope,state['sessionId'],cp,command['payload']['targetNs'])
            kwargs=dict(reveal=frame,checkpoint=next_cp);cp=next_cp
            replay=dict(throughNs=frame['throughNs'],exhaustedThroughBoundary=frame['exhaustedThroughBoundary'])
        proposed,events=apply(state,command,**kwargs)
        return self.store.commit(scope,command,before,proposed,cp,events,replay)

    def inspect(self,scope,session_id,after_sequence=0,maximum=64):
        return self.store.inspect(scope,session_id,after_sequence,maximum)
