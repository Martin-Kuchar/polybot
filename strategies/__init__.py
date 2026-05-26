from strategies.base import Strategy
from strategies.watch_120_bet_90 import Watch120Bet90

_REGISTRY: dict[str, type] = {
    Watch120Bet90.name: Watch120Bet90,
}


def get_strategy(name: str, config) -> Strategy:
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown strategy '{name}'. Available: {list(_REGISTRY)}")
    return cls(config)
