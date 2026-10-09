"""Private provider -> timeline acknowledgement -> pure reducer -> durable commit."""
from contracts.models import MethodPolicy
from contracts.primitives import require, revision
from ticks.timeline import TickTimeline
from .contracts import MAX_STEPS, command_wire, seed_state, profile_wire
from .engine import submit, advance, emit


class ExecutionController:
    __slots__ = ("__store", "__provider")

    def __init__(self, store, provider):
        self.__store, self.__provider = store, provider

    def create(self, scope, session_id, profile, policy=None, balance="10000"):
        profile = profile_wire(profile)
        provider = self.__provider
        manifest = provider.describe(provider.dataset_id, provider.dataset_version)
        require(manifest["evidenceClass"] == "SYNTHETIC_CONTRACT_ONLY" and manifest["rights"]["class"] == "SYNTHETIC",
                "mode", "REFUSED_NON_FIXTURE_MODE")
        require(sum(c["eventCount"] for c in manifest["chunks"]) <= 4096, "fixture", "REFUSED_FIXTURE_LIMIT")
        require((profile["providerId"],profile["feedId"],profile["feedInstrumentId"]) ==
                (manifest["providerId"],manifest["feedId"],manifest["instrumentId"]), "profileFeed")
        start = manifest["range"]["startNs"]
        timeline = TickTimeline(provider, provider.dataset_id, provider.dataset_version, start)
        policy = policy or MethodPolicy("fixture:free", "0"*64, "FREE_STYLE", False, ())
        state = seed_state(session_id, provider.dataset_id, provider.dataset_version, start, profile, policy, balance)
        self.__store.create(scope, state, timeline.checkpoint())
        return state

    def apply(self, scope, raw_command):
        command = command_wire(raw_command)
        if command["kind"] == "FORK":
            return self.__store.fork(scope, command)

        def operation(state, checkpoint):
            require(len(checkpoint["advanceTargets"]) <= MAX_STEPS, "fixtureRecovery", "REFUSED_RECOVERY_LIMIT")
            next_state, events = submit(state, command)
            replay = None
            next_checkpoint = checkpoint
            if command["kind"] == "ADVANCE":
                timeline = TickTimeline.resume(self.__provider, checkpoint)
                require(len(checkpoint["advanceTargets"]) < MAX_STEPS, "fixtureSteps", "REFUSED_RECOVERY_LIMIT")
                ack = timeline.advance_through(command["payload"]["targetNs"], timeline.cursor)
                next_state, financial = advance(next_state, ack["groups"], ack["coverage"], ack["diagnostics"], ack["throughNs"])
                events += financial
                replay = {"throughNs":ack["throughNs"], "exhaustedThroughBoundary":ack["exhaustedThroughBoundary"]}
                next_checkpoint = timeline.checkpoint()
            elif command["kind"] == "SEEK":
                timeline = TickTimeline.resume(self.__provider, checkpoint)
                ack = timeline.seek(command["payload"]["targetNs"])
                require(len(timeline.checkpoint()["advanceTargets"]) <= MAX_STEPS, "fixtureSteps", "REFUSED_RECOVERY_LIMIT")
                next_state["throughNs"] = ack["throughNs"]
                next_state["nextGroupIndex"] = ack["cursor"]["nextGroupIndex"]
                emit(next_state, events, "SESSION_SEEK", classification="ACCEPTED_COMMAND", throughNs=ack["throughNs"])
                replay = {"throughNs":ack["throughNs"], "exhaustedThroughBoundary":True}
                next_checkpoint = timeline.checkpoint()
            # Order commands do not reveal ticks or change the controller checkpoint.
            # Replay validation belongs to ADVANCE/SEEK, avoiding long row locks on
            # concurrent confirmation retries while retaining durable CAS/dedup.
            return next_state, next_checkpoint, events, replay

        return self.__store.run(scope, command, operation)

    def inspect(self, scope, session_id, after_sequence=0, maximum=64):
        revision(after_sequence)
        require(type(maximum) is int and 1 <= maximum <= 256, "maximum")
        return self.__store.inspect(scope, session_id, after_sequence, maximum)

    def fork(self, scope, parent_session, parent_revision, child_session, command_id="fork:create"):
        return self.apply(scope, dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-COMMAND-1",
                                     sessionId=child_session, commandId=command_id, expectedRevision=0,
                                     kind="FORK", payload={"parentSessionId":parent_session,"parentRevision":parent_revision}))
