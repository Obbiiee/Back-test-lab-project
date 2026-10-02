"""API FastAPI untuk Backtest Lab (Fase 1: impor data dan replay).

Jalankan dari folder backend:
    uvicorn api.main:app --reload --port 8000
Dokumentasi interaktif otomatis: http://127.0.0.1:8000/docs
"""
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from services.replay_service import NotFound, ReplayService
from engine.trading import TradingConfig

app = FastAPI(title="Backtest Lab API", version="0.4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "null",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

service = ReplayService()


class StartRequest(BaseModel):
    dataset_id: str
    start_index: Optional[int] = None
    start_time: Optional[str] = None  # ISO, dianggap UTC, contoh "2026-01-15T08:00:00"
    initial_balance: float = 10_000.0
    contract_size: float = 100.0
    spread: float = 0.0
    slippage: float = 0.0
    commission_per_lot: float = 0.0


class NextRequest(BaseModel):
    steps: int = 1


class JumpRequest(BaseModel):
    time: str  # ISO, dianggap UTC


class MarketOrderRequest(BaseModel):
    side: str
    stop_distance: float
    take_profit_distance: Optional[float] = None
    risk_percent: float = 1.0


class PendingOrderRequest(BaseModel):
    order_type: str
    entry_price: float
    stop_distance: float
    take_profit_distance: Optional[float] = None
    risk_percent: float = 1.0


async def _read_csv(file: UploadFile) -> str:
    raw = await file.read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="file harus berformat teks UTF-8")


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/datasets/validate")
async def validate_dataset(file: UploadFile = File(...), symbol: str = Form(...),
                           timeframe: str = Form(...), timezone: str = Form("UTC")):
    return service.validate(await _read_csv(file), symbol, timeframe, timezone)


@app.post("/api/datasets/import")
async def import_dataset(file: UploadFile = File(...), symbol: str = Form(...),
                         timeframe: str = Form(...), timezone: str = Form("UTC")):
    return service.import_dataset(await _read_csv(file), symbol, timeframe, timezone)


@app.post("/api/replay/start")
def start_replay(body: StartRequest):
    config = TradingConfig(
        initial_balance=body.initial_balance,
        contract_size=body.contract_size,
        spread=body.spread,
        slippage=body.slippage,
        commission_per_lot=body.commission_per_lot,
    )
    return _guard(service.start, body.dataset_id, body.start_index, body.start_time, config)


@app.get("/api/replay/{session_id}/state")
def replay_state(session_id: str, max_candles: int = 5000):
    return _guard(service.state, session_id, max_candles)


@app.post("/api/replay/{session_id}/next")
def replay_next(session_id: str, body: NextRequest = NextRequest()):
    return _guard(service.next, session_id, body.steps)


@app.post("/api/replay/{session_id}/previous")
def replay_previous(session_id: str):
    return _guard(service.previous, session_id)


@app.post("/api/replay/{session_id}/jump")
def replay_jump(session_id: str, body: JumpRequest):
    return _guard(service.jump, session_id, body.time)


@app.post("/api/replay/{session_id}/reset")
def replay_reset(session_id: str):
    return _guard(service.reset, session_id)


@app.post("/api/replay/{session_id}/orders/market")
def replay_market_order(session_id: str, body: MarketOrderRequest):
    return _guard(
        service.market_order,
        session_id,
        body.side,
        body.stop_distance,
        body.take_profit_distance,
        body.risk_percent,
    )


@app.post("/api/replay/{session_id}/position/close")
def replay_close_position(session_id: str):
    return _guard(service.close_position, session_id)


@app.post("/api/replay/{session_id}/orders/pending")
def replay_pending_order(session_id: str, body: PendingOrderRequest):
    return _guard(
        service.pending_order,
        session_id,
        body.order_type,
        body.entry_price,
        body.stop_distance,
        body.take_profit_distance,
        body.risk_percent,
    )


@app.delete("/api/replay/{session_id}/orders/pending")
def replay_cancel_pending(session_id: str):
    return _guard(service.cancel_pending_order, session_id)
