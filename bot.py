from __future__ import annotations
import logging
import threading
import time
import uuid
from typing import Callable, Optional

from config import Config
from api import PolymarketAPI, MarketState
from tracker import TradeTracker, Trade
from strategies import get_strategy
from strategies.base import StrategyContext, BetDecision

log = logging.getLogger(__name__)


def _upcoming_market_timestamps(n: int = 4) -> list[int]:
    """Return the next n BTC 5m market end-timestamps (300s boundaries)."""
    now = int(time.time())
    first = ((now // 300) + 1) * 300
    return [first + i * 300 for i in range(n)]


class Bot:
    def __init__(
        self,
        config: Config,
        tracker: TradeTracker,
        on_tick: Optional[Callable] = None,
    ):
        self.config = config
        self.tracker = tracker
        self.api = PolymarketAPI(config)
        self.strategy = get_strategy(config.active_strategy, config)
        self.on_tick = on_tick
        self.on_resolution: Optional[Callable] = None

        # Per-market state keyed by end-timestamp
        self._contexts: dict[int, StrategyContext] = {}
        self._active_markets: dict[int, dict] = {}  # for dashboard

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self.status: dict = {
            "running": False,
            "production": config.production,
            "active_markets": [],
            "last_action": "",
            "last_error": "",
            "tick_count": 0,
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            self.status["running"] = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="bot-loop")
        self._thread.start()
        log.info(
            "Bot started — strategy=%s production=%s shares=%d",
            self.strategy.name, self.config.production, self.config.shares_per_bet,
        )

    def stop(self):
        with self._lock:
            self._running = False
            self.status["running"] = False
        log.info("Bot stop requested")

    def is_running(self) -> bool:
        return self._running

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _loop(self):
        try:
            self._resolve_pending_bets()
        except Exception as e:
            log.warning("Startup resolution pass failed: %s", e)

        while self._running:
            t0 = time.monotonic()
            try:
                self.tick()
            except Exception as e:
                log.exception("Unhandled error in tick: %s", e)
                self.status["last_error"] = str(e)
            elapsed = time.monotonic() - t0
            sleep_for = max(0.0, self.config.poll_interval - elapsed)
            time.sleep(sleep_for)

    def tick(self):
        timestamps = _upcoming_market_timestamps(4)
        market_infos = []

        for ts in timestamps:
            try:
                snapshot = self.api.get_market_snapshot(ts)
            except Exception as e:
                log.warning("Snapshot failed for ts=%d: %s", ts, e)
                continue

            if snapshot is None:
                continue

            if ts not in self._contexts:
                self._contexts[ts] = StrategyContext()
            ctx = self._contexts[ts]

            # Resolution path
            if snapshot.closed or snapshot.remaining_seconds <= 0:
                if not ctx.resolved:
                    self._handle_resolution(snapshot, ctx)
                continue

            # Strategy evaluation
            decision = self.strategy.evaluate(ctx, snapshot)
            if decision is not None:
                self._place_bet(snapshot, decision)

            market_infos.append({
                "timestamp": ts,
                "remaining": snapshot.remaining_seconds,
                "up_ask": snapshot.up_ask,
                "down_ask": snapshot.down_ask,
                "flagged": ctx.flagged,
                "flagged_side": ctx.flagged_side,
                "bet_placed": ctx.bet_placed,
                "condition_id": snapshot.condition_id,
            })

        # Prune contexts for markets that ended more than 10 minutes ago
        cutoff = int(time.time()) - 600
        for ts in [k for k in self._contexts if k < cutoff]:
            del self._contexts[ts]

        self._resolve_pending_bets()

        self.status["active_markets"] = market_infos
        self.status["tick_count"] += 1

        if self.on_tick:
            try:
                self.on_tick(self.status)
            except Exception as e:
                log.warning("on_tick callback error: %s", e)

    def _resolve_pending_bets(self):
        """Check any past markets that have bets but no resolution yet."""
        now = time.time()
        any_resolved = False
        for condition_id, market_ts in self.tracker.pending_past_bets(now):
            resolution = self.api.get_market_resolution(market_ts)
            if resolution is None:
                continue
            updated = self.tracker.update_resolution(condition_id, resolution)
            if updated:
                log.info("Resolved pending bet: %s → %s", condition_id[:8], resolution)
                any_resolved = True
                if self.config.production:
                    self._maybe_redeem(condition_id, resolution)
        if any_resolved and self.on_resolution:
            try:
                self.on_resolution({"stats": self.tracker.stats()})
            except Exception as e:
                log.warning("on_resolution callback error: %s", e)

    # ── Resolution ────────────────────────────────────────────────────────────

    def _handle_resolution(self, snapshot: MarketState, ctx: StrategyContext):
        if not self.tracker.has_bet_in_market(snapshot.condition_id):
            ctx.resolved = True
            return

        resolution = self.api.get_market_resolution(snapshot.timestamp)
        if resolution is None:
            return  # not resolved yet — retry next tick

        updated = self.tracker.update_resolution(snapshot.condition_id, resolution)
        ctx.resolved = True

        if updated:
            log.info("Market %s resolved: %s", snapshot.condition_id[:8], resolution)
            if self.config.production:
                self._maybe_redeem(snapshot.condition_id, resolution)

    def _maybe_redeem(self, condition_id: str, resolution: str):
        for t in self.tracker._trades:
            if t.condition_id == condition_id and t.won == "1":
                self.api.redeem_winning_position(condition_id, t.side == "Up")
                break

    # ── Order placement ───────────────────────────────────────────────────────

    def _place_bet(self, snapshot: MarketState, decision: BetDecision):
        if self.tracker.has_bet_in_market(snapshot.condition_id):
            log.debug("Already bet in %s — skipping", snapshot.condition_id[:8])
            return

        shares = self.config.shares_per_bet
        cost = decision.price * shares
        fee = shares * 0.07 * decision.price * (1.0 - decision.price)

        if not self.config.production:
            log.info(
                "SIMULATED: %s %d shares @ %.3f  market=%s  (%s)",
                decision.side, shares, decision.price,
                snapshot.condition_id[:8], decision.reason,
            )
            status = "simulated"
        else:
            try:
                exec_price = round(decision.price + 0.03, 2)  # 3-tick slippage to walk the book
                resp = self.api.place_market_buy(
                    token_id=decision.token_id,
                    shares=shares,
                    price=exec_price,
                )
                log.info(
                    "ORDER PLACED: %s %d @ %.3f (limit %.3f)  market=%s  resp=%s",
                    decision.side, shares, decision.price, exec_price,
                    snapshot.condition_id[:8], resp,
                )
                status = "placed"
            except Exception as e:
                err = str(e)
                # Polymarket quirk: FOK errors sometimes include an orderID meaning
                # the order was actually filled. Treat as placed so tracker is accurate.
                if "orderID" in err and "couldn't be fully filled" in err:
                    log.warning(
                        "FOK soft-fill for %s (order likely placed): %s",
                        snapshot.condition_id[:8], e,
                    )
                    status = "placed"
                else:
                    log.error("Order failed for %s: %s", snapshot.condition_id[:8], e)
                    self.status["last_error"] = err
                    status = "failed"

        trade = Trade(
            trade_id=str(uuid.uuid4()),
            timestamp=time.time(),
            market_timestamp=snapshot.timestamp,
            condition_id=snapshot.condition_id,
            side=decision.side,
            token_id=decision.token_id,
            price=decision.price,
            shares=shares,
            cost_usdc=cost,
            fee_estimate=fee,
            status=status,
            reason=decision.reason,
        )
        self.tracker.record(trade)
        self.status["last_action"] = (
            f"{status.upper()}: {decision.side} @ {decision.price:.3f} "
            f"({snapshot.condition_id[:8]})"
        )
