# Polymarket BTC 5min Trading Bot

## Project Overview

This is a Python trading bot for Polymarket's BTC 5-minute UP/DOWN binary markets. The strategy was developed and backtested over a multi-week conversation; full context is in `docs/`. The user (Martin, based in Slovakia) is technical, hands-on, and already runs a TypeScript version of a related bot (`DumpHedgeTrader` from a forked `Poly-Mike/polymarket-arbitrage-trading-bot` repo). They want a clean Python rewrite with a Bloomberg-terminal-style dashboard.

## Critical Context Before You Code

**Read these files in order before starting any work:**

1. `docs/STRATEGY.md` — what the bot does and why
2. `docs/BACKTEST_RESULTS.md` — the data behind every decision
3. `docs/POLYMARKET_INTEGRATION.md` — Polymarket API quirks, wallet setup
4. `docs/ARCHITECTURE.md` — file layout and design decisions
5. `docs/USER_PREFERENCES.md` — how Martin works and communicates

## What Has Already Been Decided

These are NOT open questions. The user confirmed them after extensive analysis:

- **Language**: Python (not TypeScript)
- **Strategy**: Pluggable architecture — start with `watch_120_bet_90`
- **Dashboard**: Bloomberg-terminal aesthetic (black bg, green/amber monospace), Flask + WebSocket, real-time
- **Dashboard features**: Live P&L + open positions, trade history + win rate, live market prices + countdown, wallet balance + start/stop controls
- **Wallet**: EOA private key signs orders via proxy wallet (signature_type=1)
- **Default thresholds**: T-120s watch in [0.85, 0.96), T-90s bet with cap < 0.98
- **Default shares**: 2 per bet (small — user wants to validate live before scaling)

## What Was Half-Built Before Switching to Claude Code

A previous session started building this in `/home/claude/polybot/` but never finished. **Discard that work and start fresh.** Files that existed: `config.py`, `api.py`, `strategies/base.py`, `strategies/watch_120_bet_90.py`, `strategies/__init__.py`, `tracker.py`. They are reasonable starting references but were not tested and the bot core / dashboard were never written. The `docs/` folder in this directory is the canonical source of truth.

## Build Order

1. `config.py` — load .env settings
2. `api.py` — Polymarket client (gamma + CLOB + balance + redemption)
3. `strategies/` — base class + Watch120Bet90
4. `tracker.py` — CSV trade ledger with thread-safe P&L tracking
5. `bot.py` — main loop: discover markets, snapshot every second, run strategy, place orders
6. `dashboard/app.py` — Flask + Socket.IO server
7. `dashboard/templates/index.html` + static assets — Bloomberg-style UI
8. `main.py` — entrypoint that runs bot and dashboard together

## Key Technical Decisions

- **Polling, not WebSocket**, for market data: Polymarket's WebSocket API is unreliable and the user's existing bot polls every 1s successfully.
- **Sliding-second tolerance** when matching snapshots to "T-120s" — actual capture might be 119s or 121s. Use ±2s tolerance.
- **Per-market state machine** — a market is FLAGGED at T-120s and BET at T-90s. State stored in `StrategyContext` per market.
- **Don't double-bet** — `TradeTracker.has_bet_in_market()` check before placing.
- **CSV is the source of truth** — not in-memory state. Bot restart should resume cleanly from CSV.
- **Simulation mode** — when `PRODUCTION=false`, log "would have placed" and update tracker with simulated fills, but never call the CLOB.

## Polymarket API Gotchas (Critical — Read POLYMARKET_INTEGRATION.md)

- Use `signature_type=1` (proxy wallet flow). Direct EOA signing gives `"maker address not allowed, please use the deposit wallet flow"`.
- `polygon-rpc.com` (default in many examples) is **unreliable** — use `https://polygon-bor-rpc.publicnode.com` or implement RPC fallback.
- Markets have URL slug pattern `btc-updown-5m-{end_timestamp}` where the timestamp increments every 300 seconds.
- The CLOB client's `createOrder` signature changed recently: tickSize is now an **options object**, not a positional arg.
- `OrderType.FOK` (Fill Or Kill) is preferred for market orders, not GTC.
- Fee formula: `fee = shares × 0.07 × price × (1 - price)`. Maximum 1.75% at price 0.50, drops to ~0% at the extremes.

## Strategy Rules (Don't Change Without Re-Running Backtest)

```
At every 1-second snapshot of a BTC 5m market:

  if remaining_seconds is approximately 120 (±2):
    if 0.85 <= favourite_ask < 0.96:
      FLAG this market with favourite side
    else:
      skip this market entirely

  if remaining_seconds is approximately 90 (±2) AND market is FLAGGED:
    if current_favourite_side != flagged_side:
      skip (side flipped — too risky)
    if current_favourite_ask >= 0.98:
      skip (payout too small to be worth fee/slippage risk)
    else:
      place market buy on favourite side at current ask price
      mark market as BET PLACED
```

This produces ~14 bets/day at 94% win rate on 12.5 days of backtested data. Expected EV is +2.5% per dollar wagered.

## Communication Preferences

- Martin prefers **concise responses**, **prose over heavy bullets** for explanations
- Show **concrete numbers and examples**, not abstract descriptions
- He has **strong technical depth** — don't over-explain Python or APIs
- He values **honest assessments over reassurance** — flag risks clearly
- He's already paranoid about the original bot's author leaving a wallet drain — be extra clear about anything involving wallet addresses or signing

## What Not to Do

- Don't pull in heavy dependencies — `requests`, `flask`, `flask-socketio`, `python-dotenv`, `py-clob-client`, `web3`, `eth-account`. That's it.
- Don't add ML, prediction models, or "smart" features. The strategy is decided.
- Don't auto-scale share size. Martin scales manually after reviewing live results.
- Don't fetch Polymarket APIs during the build — they're blocked in sandbox environments. Test logic with mocks.
- Don't reference Discord, Telegram, or any external community — the original repo had a sketchy Discord CTA Martin found suspicious.
