from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _str(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _bool(key: str, default: bool = False) -> bool:
    return os.environ.get(key, str(default)).lower() in ("1", "true", "yes")


def _int(key: str, default: int = 0) -> int:
    return int(os.environ.get(key, str(default)))


def _float(key: str, default: float = 0.0) -> float:
    return float(os.environ.get(key, str(default)))


@dataclass
class Config:
    # Wallet
    private_key: str = field(default_factory=lambda: _str("PRIVATE_KEY"))
    deposit_wallet_address: str = field(default_factory=lambda: _str("DEPOSIT_WALLET_ADDRESS"))
    signature_type: int = field(default_factory=lambda: _int("SIGNATURE_TYPE", 3))

    # Mode
    production: bool = field(default_factory=lambda: _bool("PRODUCTION", False))
    shares_per_bet: int = field(default_factory=lambda: _int("SHARES_PER_BET", 2))

    # Strategy
    active_strategy: str = field(default_factory=lambda: _str("ACTIVE_STRATEGY", "watch_120_bet_90"))
    watch_second: int = field(default_factory=lambda: _int("WATCH_SECOND", 120))
    bet_second: int = field(default_factory=lambda: _int("BET_SECOND", 90))
    price_min: float = field(default_factory=lambda: _float("PRICE_MIN", 0.85))
    price_max: float = field(default_factory=lambda: _float("PRICE_MAX", 0.96))
    bet_price_max: float = field(default_factory=lambda: _float("BET_PRICE_MAX", 0.98))

    # APIs
    gamma_api_url: str = field(default_factory=lambda: _str("GAMMA_API_URL", "https://gamma-api.polymarket.com"))
    clob_api_url: str = field(default_factory=lambda: _str("CLOB_API_URL", "https://clob.polymarket.com"))
    rpc_url: str = field(default_factory=lambda: _str("RPC_URL", "https://polygon-bor-rpc.publicnode.com"))

    # Timing
    poll_interval_ms: int = field(default_factory=lambda: _int("POLL_INTERVAL_MS", 1000))

    # Dashboard
    dashboard_port: int = field(default_factory=lambda: _int("DASHBOARD_PORT", 8080))
    dashboard_host: str = field(default_factory=lambda: _str("DASHBOARD_HOST", "127.0.0.1"))

    # Paths
    trades_csv: str = field(default_factory=lambda: _str("TRADES_CSV", "data/trades.csv"))
    log_file: str = field(default_factory=lambda: _str("LOG_FILE", "logs/bot.log"))

    def __post_init__(self):
        Path(self.trades_csv).parent.mkdir(parents=True, exist_ok=True)
        Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)

    @property
    def poll_interval(self) -> float:
        return self.poll_interval_ms / 1000.0
