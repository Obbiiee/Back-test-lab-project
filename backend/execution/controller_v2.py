"""Private synthetic v2 orchestration; no HTTP or caller-supplied tick frames."""
from copy import deepcopy
from contracts.canonical import content_hash
from contracts.primitives import require
from .kernel_v2 import seed_state, command_wire, submit, advance
from .profile_v2 import ExecutionProfileV2
from .sources_v2 import SourceJoinV2


class ExecutionControllerV2:
    def __init__(self,store,profile,primary_provider,*,conversion_provider=None):
        require(type(profile) is ExecutionProfileV2,"profile")
        self.__store,self.__profile=store,profile
        self.__primary,self.__fx=primary_provider,conversion_provider

    def create(self,scope,session_id,policy,*,start_ns,balance="10000"):
        source=SourceJoinV2(self.__profile,self.__primary,start_ns=start_ns,conversion_provider=self.__fx)
        cp=source.checkpoint();state=seed_state(session_id,self.__profile,policy,cp,balance)
        self.__store.create(scope,state,cp)
        return deepcopy(state)

    def apply(self,scope,raw):
        command=command_wire(raw)
        if command["kind"]=="FORK":return self.__store.fork(scope,command)
        stored,prior=self.__store.prepare(scope,command)
        if prior is not None:return prior
        state,cp=stored["state"],stored["controller"]
        require(state["profileHash"]==self.__profile.profile_hash,"profile","REFUSED_V2_PROFILE")
        source=None;basis=None
        if command["kind"] in ("OPEN","ADVANCE"):
            source=SourceJoinV2.resume(self.__profile,self.__primary,cp,conversion_provider=self.__fx)
            if command["kind"]=="OPEN":basis=source.risk_basis(source.checkpoint())
        proposed,events=submit(state,command,basis)
        next_cp=cp;replay=None
        if command["kind"]=="ADVANCE":
            frame=source.reveal(command["payload"]["targetNs"],source.checkpoint())
            proposed,financial=advance(proposed,frame,command["payload"]["targetNs"]);events+=financial
            next_cp=frame["checkpoint"]
            replay=dict(throughNs=frame["throughNs"],exhaustedThroughBoundary=frame["exhaustedThroughBoundary"])
        elif command["kind"]=="OPEN":next_cp=basis["checkpoint"]
        # Source acceptance/recovery/math is outside the financial row lock.
        state_hash,cp_hash=content_hash(state),content_hash(cp)
        def operation(live,checkpoint):
            require(content_hash(live)==state_hash and content_hash(checkpoint)==cp_hash,
                    "basis","REFUSED_STALE_REVISION")
            return deepcopy(proposed),deepcopy(next_cp),deepcopy(events),deepcopy(replay)
        return self.__store.run(scope,command,operation)

    def inspect(self,scope,session_id,after_sequence=0,maximum=64):
        return self.__store.inspect(scope,session_id,after_sequence,maximum)

    def statistics(self,scope,session_id):
        return self.__store.statistics(scope,session_id)
