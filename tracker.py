from __future__ import annotations
import csv
import datetime
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

CSV_FIELDS = [
    "trade_id",
    "timestamp",
    "market_timestamp",
    "condition_id",
    "side",
    "token_id",
    "price",
    "shares",
    "cost_usdc",
    "fee_estimate",
    "status",       # "simulated" | "placed" | "failed"
    "resolution",   # "Up" | "Down" | "" (pending)
    "won",          # "1" | "0" | ""
    "pnl",          # float string | "" (pending)
    "reason",
]


@dataclass
class Trade:
    trade_id: str
    timestamp: float        # Unix timestamp when bet was placed
    market_timestamp: int   # end timestamp of the BTC 5m market
    condition_id: str
    side: str               # "Up" or "Down"
    token_id: str
    price: float
    shares: int
    cost_usdc: float
    fee_estimate: float
    status: str             # "simulated" | "placed" | "failed"
    resolution: str = ""
    won: str = ""
    pnl: str = ""
    reason: str = ""


class TradeTracker:
    def __init__(self, csv_path: str):
        self.csv_path = Path(csv_path)
        self._lock = threading.Lock()
        self._trades: list[Trade] = []
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self):
        if not self.csv_path.exists():
            self._write_header()
            return
        try:
            with open(self.csv_path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        self._trades.append(Trade(
                            trade_id=row["trade_id"],
                            timestamp=float(row["timestamp"]),
                            market_timestamp=int(row["market_timestamp"]),
                            condition_id=row["condition_id"],
                            side=row["side"],
                            token_id=row["token_id"],
                            price=float(row["price"]),
                            shares=int(row["shares"]),
                            cost_usdc=float(row["cost_usdc"]),
                            fee_estimate=float(row["fee_estimate"]),
                            status=row["status"],
                            resolution=row.get("resolution", ""),
                            won=row.get("won", ""),
                            pnl=row.get("pnl", ""),
                            reason=row.get("reason", ""),
                        ))
                    except (KeyError, ValueError) as e:
                        log.warning("Skipping malformed CSV row: %s", e)
            log.info("Loaded %d trades from %s", len(self._trades), self.csv_path)
        except Exception as e:
            log.error("Failed to load trades CSV: %s", e)

    def _write_header(self):
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()

    def _append_row(self, trade: Trade):
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        exists = self.csv_path.exists()
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            if not exists:
                writer.writeheader()
            writer.writerow({k: getattr(trade, k) for k in CSV_FIELDS})

    def _rewrite_all(self):
        tmp = self.csv_path.with_suffix(".tmp")
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for t in self._trades:
                writer.writerow({k: getattr(t, k) for k in CSV_FIELDS})
        os.replace(tmp, self.csv_path)

    # ── Public API ────────────────────────────────────────────────────────────

    def record(self, trade: Trade):
        with self._lock:
            self._trades.append(trade)
            self._append_row(trade)
        log.info(
            "Trade [%s] %s %s @ %.3f x%d",
            trade.status, trade.condition_id[:8], trade.side, trade.price, trade.shares,
        )

    def update_resolution(self, condition_id: str, resolution: str) -> bool:
        """Settle all pending trades for this market. Returns True if any were updated."""
        with self._lock:
            updated = False
            for t in self._trades:
                if t.condition_id != condition_id or t.resolution != "":
                    continue
                t.resolution = resolution
                t.won = "1" if t.side == resolution else "0"
                if t.won == "1":
                    # Net gain: payout (1.0/share) minus what we paid minus fee
                    pnl = t.shares * (1.0 - t.price) - t.fee_estimate
                else:
                    pnl = -(t.cost_usdc + t.fee_estimate)
                t.pnl = f"{pnl:.4f}"
                updated = True
            if updated:
                self._rewrite_all()
        return updated

    def has_bet_in_market(self, condition_id: str) -> bool:
        with self._lock:
            return any(t.condition_id == condition_id for t in self._trades)

    def pending_past_bets(self, now: float) -> list[tuple[str, int]]:
        """Return (condition_id, market_timestamp) for bets in ended markets not yet resolved."""
        with self._lock:
            seen: set[str] = set()
            result: list[tuple[str, int]] = []
            for t in self._trades:
                if t.resolution or t.condition_id in seen:
                    continue
                if t.market_timestamp < now:
                    seen.add(t.condition_id)
                    result.append((t.condition_id, t.market_timestamp))
            return result

    def all_trades(self, limit: int = 50) -> list[dict]:
        with self._lock:
            recent = self._trades[-limit:]
            recent.reverse()
            return [{k: getattr(t, k) for k in CSV_FIELDS} for t in recent]

    def stats(self) -> dict:
        with self._lock:
            today_start = datetime.datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            ).timestamp()

            total = wins = losses = pending = simulated = 0
            total_pnl = today_bets = today_wins = 0
            today_pnl = 0.0

            for t in self._trades:
                total += 1
                if t.status == "simulated":
                    simulated += 1
                if t.won == "1":
                    wins += 1
                    if t.pnl:
                        total_pnl += float(t.pnl)
                elif t.won == "0":
                    losses += 1
                    if t.pnl:
                        total_pnl += float(t.pnl)
                else:
                    pending += 1

                if t.timestamp >= today_start:
                    today_bets += 1
                    if t.won == "1":
                        today_wins += 1
                    if t.pnl:
                        today_pnl += float(t.pnl)

            resolved = wins + losses
            win_rate = wins / resolved if resolved > 0 else 0.0

            return {
                "total_bets": total,
                "wins": wins,
                "losses": losses,
                "pending": pending,
                "win_rate": win_rate,
                "total_pnl": round(total_pnl, 4),
                "today_bets": today_bets,
                "today_wins": today_wins,
                "today_pnl": round(today_pnl, 4),
                "simulated": simulated,
            }
