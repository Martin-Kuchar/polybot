from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from api import MarketState


@dataclass
class BetDecision:
    side: str       # "Up" or "Down"
    token_id: str   # CLOB token ID to buy
    price: float    # current ask price
    reason: str     # human-readable explanation


@dataclass
class StrategyContext:
    """Per-market mutable state. Strategies read/write freely."""
    flagged: bool = False
    flagged_side: Optional[str] = None
    bet_placed: bool = False
    resolved: bool = False


class Strategy:
    name: str = "base"

    def evaluate(self, ctx: StrategyContext, snapshot: "MarketState") -> Optional[BetDecision]:
        raise NotImplementedError
