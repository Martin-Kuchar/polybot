from __future__ import annotations
from typing import Optional

from strategies.base import BetDecision, Strategy, StrategyContext
from api import MarketState

TOLERANCE = 2  # ±2 seconds around watch/bet timestamps


class Watch120Bet90(Strategy):
    name = "watch_120_bet_90"

    def __init__(self, config):
        self.watch_second = config.watch_second   # default 120
        self.bet_second = config.bet_second       # default 90
        self.price_min = config.price_min         # default 0.85
        self.price_max = config.price_max         # default 0.96
        self.bet_price_min = config.bet_price_min # default 0.0
        self.bet_price_max = config.bet_price_max # default 0.98

    def evaluate(self, ctx: StrategyContext, snapshot: MarketState) -> Optional[BetDecision]:
        t = snapshot.remaining_seconds
        up_ask = snapshot.up_ask
        down_ask = snapshot.down_ask

        fav_ask = max(up_ask, down_ask)
        fav_side = "Up" if up_ask >= down_ask else "Down"

        # Phase 1 — Watch (fires once per market around T-120s)
        if not ctx.flagged and not ctx.bet_placed:
            lo = self.watch_second - TOLERANCE
            hi = self.watch_second + TOLERANCE
            if lo <= t <= hi:
                if self.price_min <= fav_ask < self.price_max:
                    ctx.flagged = True
                    ctx.flagged_side = fav_side
                else:
                    ctx.bet_placed = True  # outside range, never check again

        # Phase 2 — Bet (fires once per market around T-90s, only if flagged)
        if ctx.flagged and not ctx.bet_placed:
            lo = self.bet_second - TOLERANCE
            hi = self.bet_second + TOLERANCE
            if lo <= t <= hi:
                if fav_side != ctx.flagged_side:
                    ctx.bet_placed = True  # side flipped — skip
                    return None
                if fav_ask < self.bet_price_min:
                    ctx.bet_placed = True  # price too low — skip
                    return None
                if fav_ask >= self.bet_price_max:
                    ctx.bet_placed = True  # payout too small — skip
                    return None

                ctx.bet_placed = True
                token_id = snapshot.up_token_id if fav_side == "Up" else snapshot.down_token_id
                return BetDecision(
                    side=fav_side,
                    token_id=token_id,
                    price=fav_ask,
                    reason=(
                        f"watch T-{self.watch_second}s in [{self.price_min},{self.price_max}), "
                        f"bet T-{self.bet_second}s @ {fav_ask:.3f}"
                    ),
                )

        return None
