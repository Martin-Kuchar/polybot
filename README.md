# Polybot

Polymarket BTC 5-minute trading bot with Bloomberg-terminal-style dashboard.

## Quick Start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env: set PRIVATE_KEY and PROXY_WALLET_ADDRESS

# 3. Run in simulation mode first
python main.py

# 4. Open dashboard
open http://localhost:8080

# 5. When ready for real trading, set PRODUCTION=true in .env and restart
```

## What It Does

At T-120s of every BTC 5-minute Polymarket market:
- Flags markets where the favourite is priced between 0.85 and 0.96

At T-90s (30 seconds later):
- If the same side is still the favourite and price is below 0.98, places a market-buy order on that side

Backtested: ~94% win rate, ~14 bets/day, +2.5% EV per dollar.

See `docs/STRATEGY.md` and `docs/BACKTEST_RESULTS.md` for full details.

## Configuration

All settings in `.env`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `PRIVATE_KEY` | (required) | Your MetaMask private key |
| `PROXY_WALLET_ADDRESS` | (required) | Your Polymarket proxy wallet |
| `SIGNATURE_TYPE` | 1 | Always 1 for proxy mode |
| `PRODUCTION` | false | true = real orders, false = simulate |
| `SHARES_PER_BET` | 2 | Start small until you've validated live |
| `ACTIVE_STRATEGY` | watch_120_bet_90 | Which strategy to run |
| `WATCH_SECOND` | 120 | When to flag a market |
| `BET_SECOND` | 90 | When to place the bet |
| `PRICE_MIN` | 0.85 | Min favourite price at watch |
| `PRICE_MAX` | 0.96 | Max favourite price at watch |
| `BET_PRICE_MAX` | 0.98 | Skip if price at bet time too high |
| `DASHBOARD_PORT` | 8080 | Local dashboard port |

## Adding Strategies

1. Create `strategies/my_strategy.py` extending `Strategy`
2. Register in `strategies/__init__.py`
3. Set `ACTIVE_STRATEGY=my_strategy` in `.env`

See `strategies/base.py` for the protocol.

## Architecture

```
config.py     →  loads .env
api.py        →  Polymarket client (orderbook, orders, balance, redemption)
strategies/   →  pluggable trading logic
tracker.py    →  CSV-backed trade ledger with P&L
bot.py        →  main polling loop
dashboard/    →  Flask + SocketIO real-time dashboard
main.py       →  entrypoint, runs bot + dashboard
```

See `docs/ARCHITECTURE.md` for full details.

## Safety

- `PRODUCTION=false` by default — no real orders placed
- Start with 2 shares
- The bot will NEVER:
  - Place an order on a market you've already bet on
  - Bet at a price above `BET_PRICE_MAX`
  - Continue after the wallet runs out of USDC
- Watch wallet balance on dashboard for MATIC and USDC

## Disclaimer

This is a personal trading tool. Past performance doesn't predict future results. Polymarket markets carry full loss risk. Sample size of backtest is still small (740 bets); strategy may stop working as more bots discover it.
