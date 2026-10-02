"""Small deterministic market-order engine used by a replay session.

OHLC prices are treated as mid prices. Entry and exit fills pay half the configured
spread plus adverse slippage. SL/TP distances are measured from the actual entry fill.
If one candle reaches both levels, SL wins because candle OHLC cannot reveal their order.
"""
import math
from datetime import datetime
from typing import List, Optional

from ..market_data.models import Candle
from .models import ClosedTrade, PendingOrder, Position, TradingConfig


class TradingEngine:
    def __init__(self, config: TradingConfig = TradingConfig()):
        self._validate_config(config)
        self.config = config
        self.balance = config.initial_balance
        self.position: Optional[Position] = None
        self.pending_order: Optional[PendingOrder] = None
        self.trades: List[ClosedTrade] = []
        self.last_processed_time: Optional[datetime] = None

    @staticmethod
    def _finite_positive(value: float, label: str) -> None:
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{label} harus lebih besar dari 0")

    @classmethod
    def _validate_config(cls, config: TradingConfig) -> None:
        cls._finite_positive(config.initial_balance, "saldo awal")
        cls._finite_positive(config.contract_size, "ukuran kontrak")
        for value, label in (
            (config.spread, "spread"),
            (config.slippage, "slippage"),
            (config.commission_per_lot, "komisi per lot"),
        ):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{label} tidak boleh negatif")

    def open_market(
        self,
        side: str,
        candle: Candle,
        stop_distance: float,
        take_profit_distance: Optional[float] = None,
        risk_percent: float = 1.0,
    ) -> Position:
        side = (side or "").strip().upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError("arah order harus BUY atau SELL")
        if self.position is not None:
            raise ValueError("tutup posisi yang sedang terbuka sebelum membuka posisi baru")
        if self.pending_order is not None:
            raise ValueError("batalkan pending order sebelum membuka posisi market")
        self._finite_positive(stop_distance, "jarak stop loss")
        if take_profit_distance is not None:
            self._finite_positive(take_profit_distance, "jarak take profit")
        if not math.isfinite(risk_percent) or not 0 < risk_percent <= 100:
            raise ValueError("risiko harus lebih besar dari 0% dan tidak lebih dari 100%")
        if self.last_processed_time is not None and candle.time < self.last_processed_time:
            raise ValueError("order tidak dapat dibuka pada candle yang sudah dilewati")

        return self._open_at_mid(side, candle, candle.close, stop_distance, take_profit_distance, risk_percent)

    def place_pending(
        self,
        order_type: str,
        candle: Candle,
        entry_price: float,
        stop_distance: float,
        take_profit_distance: Optional[float] = None,
        risk_percent: float = 1.0,
    ) -> PendingOrder:
        order_type = (order_type or "").strip().upper()
        if order_type not in {"BUY_LIMIT", "SELL_LIMIT", "BUY_STOP", "SELL_STOP"}:
            raise ValueError("tipe pending order tidak dikenal")
        if self.position is not None or self.pending_order is not None:
            raise ValueError("hanya satu posisi atau pending order yang dapat aktif")
        self._finite_positive(entry_price, "harga pemicu")
        self._validate_order_size(stop_distance, take_profit_distance, risk_percent)
        current = candle.close
        is_buy = order_type.startswith("BUY")
        is_limit = order_type.endswith("LIMIT")
        if is_buy and is_limit and entry_price >= current:
            raise ValueError("BUY LIMIT harus berada di bawah harga saat ini")
        if is_buy and not is_limit and entry_price <= current:
            raise ValueError("BUY STOP harus berada di atas harga saat ini")
        if not is_buy and is_limit and entry_price <= current:
            raise ValueError("SELL LIMIT harus berada di atas harga saat ini")
        if not is_buy and not is_limit and entry_price >= current:
            raise ValueError("SELL STOP harus berada di bawah harga saat ini")
        self.pending_order = PendingOrder(
            order_type=order_type,
            entry_price=entry_price,
            stop_distance=stop_distance,
            take_profit_distance=take_profit_distance,
            risk_percent=risk_percent,
            placed_time=candle.time,
        )
        if self.last_processed_time is None or candle.time > self.last_processed_time:
            self.last_processed_time = candle.time
        return self.pending_order

    @classmethod
    def _validate_order_size(cls, stop_distance: float, take_profit_distance: Optional[float], risk_percent: float) -> None:
        cls._finite_positive(stop_distance, "jarak stop loss")
        if take_profit_distance is not None:
            cls._finite_positive(take_profit_distance, "jarak take profit")
        if not math.isfinite(risk_percent) or not 0 < risk_percent <= 100:
            raise ValueError("risiko harus lebih besar dari 0% dan tidak lebih dari 100%")

    def _open_at_mid(
        self,
        side: str,
        candle: Candle,
        entry_mid: float,
        stop_distance: float,
        take_profit_distance: Optional[float],
        risk_percent: float,
    ) -> Position:
        direction = 1 if side == "BUY" else -1
        half_spread = self.config.spread / 2
        entry_price = entry_mid + direction * (half_spread + self.config.slippage)
        stop_loss = entry_price - direction * stop_distance
        take_profit = (
            entry_price + direction * take_profit_distance
            if take_profit_distance is not None
            else None
        )

        # Estimate the loss at SL, including the adverse exit fill and round-trip fees.
        risk_per_lot = (
            (stop_distance + half_spread + self.config.slippage) * self.config.contract_size
            + 2 * self.config.commission_per_lot
        )
        risk_budget = self.balance * risk_percent / 100
        raw_lots = risk_budget / risk_per_lot
        lots = math.floor(raw_lots * 1000) / 1000
        if lots <= 0:
            raise ValueError("risiko terlalu kecil untuk membuka ukuran minimum 0,001 lot")

        risk_amount = lots * risk_per_lot
        self.position = Position(
            side=side,
            lots=lots,
            entry_time=candle.time,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_amount=risk_amount,
        )
        self.last_processed_time = candle.time
        return self.position

    def process_candle(self, candle: Candle) -> Optional[ClosedTrade]:
        """Process a newly revealed bar once. Older replay navigation is ignored."""
        if self.last_processed_time is not None and candle.time <= self.last_processed_time:
            return None
        self.last_processed_time = candle.time
        if self.pending_order is not None:
            fill_mid = self._pending_fill_mid(candle, self.pending_order)
            if fill_mid is None:
                return None
            order = self.pending_order
            self.pending_order = None
            self._open_at_mid(
                order.side,
                candle,
                fill_mid,
                order.stop_distance,
                order.take_profit_distance,
                order.risk_percent,
            )
        position = self.position
        if position is None:
            return None

        if position.side == "BUY":
            stop_hit = candle.low <= position.stop_loss
            target_hit = position.take_profit is not None and candle.high >= position.take_profit
            if stop_hit:
                exit_mid = min(candle.open, position.stop_loss)  # gap through stop fills worse
                return self.close_market(candle, "SL", exit_mid)
            if target_hit:
                exit_mid = max(candle.open, position.take_profit)  # favorable gap through target
                return self.close_market(candle, "TP", exit_mid)
        else:
            stop_hit = candle.high >= position.stop_loss
            target_hit = position.take_profit is not None and candle.low <= position.take_profit
            if stop_hit:
                exit_mid = max(candle.open, position.stop_loss)
                return self.close_market(candle, "SL", exit_mid)
            if target_hit:
                exit_mid = min(candle.open, position.take_profit)
                return self.close_market(candle, "TP", exit_mid)
        return None

    @staticmethod
    def _pending_fill_mid(candle: Candle, order: PendingOrder) -> Optional[float]:
        trigger = order.entry_price
        if order.order_type == "BUY_LIMIT" and candle.low <= trigger:
            return min(candle.open, trigger)
        if order.order_type == "SELL_LIMIT" and candle.high >= trigger:
            return max(candle.open, trigger)
        if order.order_type == "BUY_STOP" and candle.high >= trigger:
            return max(candle.open, trigger)
        if order.order_type == "SELL_STOP" and candle.low <= trigger:
            return min(candle.open, trigger)
        return None

    def cancel_pending(self) -> None:
        if self.pending_order is None:
            raise ValueError("tidak ada pending order untuk dibatalkan")
        self.pending_order = None

    def close_market(self, candle: Candle, reason: str = "MANUAL", mid_price: Optional[float] = None) -> ClosedTrade:
        if self.position is None:
            raise ValueError("tidak ada posisi terbuka")
        if reason not in {"SL", "TP", "MANUAL"}:
            raise ValueError("alasan penutupan tidak dikenal")
        position = self.position
        direction = 1 if position.side == "BUY" else -1
        exit_mid = candle.close if mid_price is None else mid_price
        exit_price = exit_mid - direction * (self.config.spread / 2 + self.config.slippage)
        gross_pnl = (exit_price - position.entry_price) * direction * position.lots * self.config.contract_size
        commission = 2 * self.config.commission_per_lot * position.lots
        pnl = gross_pnl - commission
        trade = ClosedTrade(
            side=position.side,
            lots=position.lots,
            entry_time=position.entry_time,
            exit_time=candle.time,
            entry_price=position.entry_price,
            exit_price=exit_price,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            gross_pnl=gross_pnl,
            commission=commission,
            pnl=pnl,
            risk_amount=position.risk_amount,
            r_multiple=pnl / position.risk_amount,
            reason=reason,
        )
        self.balance += pnl
        self.trades.append(trade)
        self.position = None
        return trade

    def state(self) -> dict:
        return {
            "balance": self.balance,
            "position": self.position.to_dict() if self.position else None,
            "pending_order": self.pending_order.to_dict() if self.pending_order else None,
            "trades": [trade.to_dict() for trade in self.trades],
            "config": {
                "initial_balance": self.config.initial_balance,
                "contract_size": self.config.contract_size,
                "spread": self.config.spread,
                "slippage": self.config.slippage,
                "commission_per_lot": self.config.commission_per_lot,
            },
        }
