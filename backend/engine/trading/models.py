"""Data models for deterministic market order execution."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class TradingConfig:
    initial_balance: float = 10_000.0
    contract_size: float = 100.0
    spread: float = 0.0
    slippage: float = 0.0
    commission_per_lot: float = 0.0


@dataclass(frozen=True)
class Position:
    side: str
    lots: float
    entry_time: datetime
    entry_price: float
    stop_loss: float
    take_profit: Optional[float]
    risk_amount: float

    def to_dict(self) -> dict:
        return {
            "side": self.side,
            "lots": self.lots,
            "entry_time": int(self.entry_time.timestamp()),
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "risk_amount": self.risk_amount,
        }


@dataclass(frozen=True)
class PendingOrder:
    order_type: str
    entry_price: float
    stop_distance: float
    take_profit_distance: Optional[float]
    risk_percent: float
    placed_time: datetime

    @property
    def side(self) -> str:
        return "BUY" if self.order_type.startswith("BUY") else "SELL"

    def to_dict(self) -> dict:
        return {
            "order_type": self.order_type,
            "side": self.side,
            "entry_price": self.entry_price,
            "stop_distance": self.stop_distance,
            "take_profit_distance": self.take_profit_distance,
            "risk_percent": self.risk_percent,
            "placed_time": int(self.placed_time.timestamp()),
        }


@dataclass(frozen=True)
class ClosedTrade:
    side: str
    lots: float
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: Optional[float]
    gross_pnl: float
    commission: float
    pnl: float
    risk_amount: float
    r_multiple: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "side": self.side,
            "lots": self.lots,
            "entry_time": int(self.entry_time.timestamp()),
            "exit_time": int(self.exit_time.timestamp()),
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "gross_pnl": self.gross_pnl,
            "commission": self.commission,
            "pnl": self.pnl,
            "risk_amount": self.risk_amount,
            "r_multiple": self.r_multiple,
            "reason": self.reason,
        }
