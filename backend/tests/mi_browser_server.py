"""Serve the built QA UI and real API on a disposable HTTPS loopback listener."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sys

import uvicorn
from psycopg.conninfo import conninfo_to_dict
from starlette.staticfiles import StaticFiles

from cloud.app import create_app
from contracts.canonical import canonical_bytes
from execution import mi_checkpoint
from infrastructure.database import migrate
from tests.mi_harness import MI
from tests.test_identity import RecordingDelivery, client, PASSWORD
from tests.test_research_sessions import method


def main(root):
    dsn = os.environ["BTL_TEST_DATABASE_URL"]
    connection = conninfo_to_dict(dsn)
    require_disposable = (connection.get("host") == str(root) and not connection.get("hostaddr")
                          and root.parent == Path("/tmp") and root.name.startswith("riksora-mi-browser."))
    if not require_disposable:
        raise RuntimeError("use the harness-owned disposable Unix socket")
    migrate(dsn)
    model = MI(["EURUSD", "GBPUSD"], steps=8)
    manifest = canonical_bytes(dict(schemaVersion=1, artifact="BTL-MI-QA-PRODUCT-SOURCE-1",
                              pins=mi_checkpoint.pins_from_state(model.state), profiles=model.wires,
                              ticks=model.ticks, startPeriod="1970-01"))
    file = root / "market.json"
    file.write_bytes(manifest)
    os.environ.update(BTL_PRODUCT_PROFILE="development", BTL_QA_MI_MANIFEST=str(file),
                      BTL_QA_MI_MANIFEST_SHA256=hashlib.sha256(manifest).hexdigest())
    delivery = RecordingDelivery()
    app = create_app(dsn, secrets.token_urlsafe(64), delivery)
    fixture = client(app)
    accounts = []
    for viewport in ("desktop", "mobile"):
        email = viewport + "@example.com"
        assert fixture.post("/api/v1/auth/register", json=dict(email=email, password=PASSWORD)).status_code == 201
        assert fixture.post("/api/v1/auth/verify", json=dict(token=delivery.token(email, "verification"))).status_code == 200
        login = fixture.post("/api/v1/auth/login", data=dict(username=email, password=PASSWORD))
        token = {"Authorization": "Bearer " + login.json()["access_token"]}
        workspace = fixture.post("/api/v1/workspaces", headers=token, json={"name": "Isolated MI QA"}).json()["id"]
        base = "/api/v1/workspaces/" + workspace + "/research"
        assert fixture.post(base + "/methods", json=dict(method(), name="Free style QA"), headers=token).status_code == 200
        assert fixture.post(base + "/methods", json=dict(method(), name="Second method QA"), headers=token).status_code == 200
        assert fixture.post(base + "/methods", json=dict(method("PROTOCOL", on=True), name="Protocol QA"), headers=token).status_code == 200
        fixture.post("/api/v1/auth/logout", headers=token)
        accounts.append(dict(email=email, password=PASSWORD, viewport=viewport))
    fixture.close()
    # Inject only in the harness's real native child, after COMMIT but before
    # its result is written to the parent pipe. The product lease expires normally.
    from cloud import worker
    worker.SERVE_ENTRY = f"""import json, os, signal, sys
from pathlib import Path
sys.path[:0] = sys.argv[1:]
from execution.mi_postgres import MultiInstrumentStore
from cloud.worker import serve
apply = MultiInstrumentStore.apply
marker = Path({str(root / 'crash-on-exit')!r})
def kill_after(self, *args, **kwargs):
    result = apply(self, *args, **kwargs)
    exits = [event["eventId"] for event in result["events"] if event["kind"] == "EXIT_FILL"]
    if exits and marker.is_file():
        marker.unlink()
        marker.with_name("crash-proof.json").write_text(json.dumps(exits))
        os.kill(os.getpid(), signal.SIGKILL)
    return result
MultiInstrumentStore.apply = kill_after
serve()
"""
    app.mount("/", StaticFiles(directory=Path(__file__).resolve().parents[2] / "frontend/dist",
                               html=True))
    with socket.socket() as bound:
        bound.bind(("127.0.0.1", 0))
        address = "https://127.0.0.1:" + str(bound.getsockname()[1])
        config = uvicorn.Config(app, ssl_certfile=str(root / "tls.crt"),
                                ssl_keyfile=str(root / "tls.key"), access_log=False, log_level="warning")
        (root / "browser.json").write_text(json.dumps(dict(url=address, accounts=accounts)))
        uvicorn.Server(config).run(sockets=[bound])


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
