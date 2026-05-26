# Architecture

## File Layout

```
polybot/
├── CLAUDE.md                       # Project intro for Claude Code (read first)
├── README.md                       # User-facing run instructions
├── .env.example                    # Template config
├── .gitignore                      # Excludes .env, data/, logs/
├── requirements.txt                # Python dependencies
├── docs/
│   ├── STRATEGY.md                 # What the bot does and why
│   ├── BACKTEST_RESULTS.md         # Data backing every decision
│   ├── POLYMARKET_INTEGRATION.md   # API gotchas
│   ├── ARCHITECTURE.md             # This file
│   └── USER_PREFERENCES.md         # How Martin works
├── config.py                       # Load .env, dataclass Config
├── api.py                          # PolymarketAPI: gamma, CLOB, balance, redemption
├── tracker.py                      # TradeTracker: CSV-backed, thread-safe ledger
├── bot.py                          # Main loop: discover, snapshot, evaluate, place orders
├── main.py                         # Entrypoint — runs bot + dashboard together
├── strategies/
│   ├── __init__.py                 # Registry: get_strategy(name) -> Strategy
│   ├── base.py                     # Strategy + StrategyContext + BetDecision dataclasses
│   └── watch_120_bet_90.py         # The implemented strategy
├── dashboard/
│   ├── app.py                      # Flask + Socket.IO server
│   ├── templates/
│   │   └── index.html              # Single-page dashboard
│   └── static/
│       ├── terminal.css            # Bloomberg-style theme
│       └── terminal.js             # WebSocket client, chart rendering
├── data/
│   └── trades.csv                  # Generated, source of truth for trades
└── logs/
    └── bot.log                     # Rotated bot log
```

## Component Responsibilities

### config.py
Single dataclass `Config` loaded once on startup from `.env`. All other modules accept a Config instance.

### api.py
- `MarketState` dataclass — point-in-time snapshot of a market's prices and tokens
- `PolymarketAPI` class wraps Gamma + CLOB + Web3:
  - `get_market_snapshot(timestamp)` — full state of a BTC 5m market
  - `place_market_buy(token_id, shares, price)` — FOK order
  - `get_balance()` — USDC and MATIC from on-chain
  - `get_market_resolution(condition_id)` — winner side or None
  - `get_clob_client()` — lazily creates and caches authenticated CLOB client

### strategies/
- `base.py` defines the protocol: every strategy gets `evaluate(ctx, snapshot)` called on each tick. Returns `BetDecision` or `None`.
- `StrategyContext` holds per-market state (snapshots seen, flags set) — strategies write to it freely.
- `__init__.py` provides `get_strategy(name, config)` lookup. Add new strategies by importing the class and registering it here.
- `watch_120_bet_90.py` implements the chosen strategy.

### tracker.py
- `Trade` dataclass — all fields needed for analysis
- `TradeTracker` class — thread-safe, persists every change to CSV
  - `record(trade)` — add a new bet
  - `update_resolution(condition_id, resolution)` — settle a market, compute P&L
  - `stats()` — aggregate numbers for dashboard
  - `all_trades(limit)` — for trade history view
  - `has_bet_in_market(condition_id)` — dedup check

CSV is the source of truth. On startup, tracker loads existing CSV. Restart-safe.

### bot.py
The trading engine. Single class `Bot` with main loop:
1. Compute upcoming 5m market timestamps (next 3-4)
2. For each, fetch market snapshot
3. For each market, run active strategy's `evaluate()`
4. If strategy returns BetDecision and we haven't bet on this market: place order, record Trade
5. For markets that have ended, check resolution and update tracker
6. Sleep until next poll interval
7. Broadcast state to dashboard via shared callback

Key methods:
- `tick()` — single pass through all active markets
- `discover_markets()` — find upcoming markets
- `process_market(timestamp)` — snapshot, evaluate, maybe bet
- `settle_resolved_markets()` — check resolutions, update P&L
- `start()` / `stop()` — lifecycle for dashboard control

The bot exposes a `status` dict for the dashboard with live state (open markets, last action, errors).

### dashboard/app.py
Flask + Flask-SocketIO server. Runs on the same Python process as the bot but in a separate thread.

Endpoints:
- `GET /` — serves `index.html`
- `GET /api/stats` — current TradeTracker.stats()
- `GET /api/trades` — recent trades for the history table
- `GET /api/markets` — current live markets the bot is watching
- `GET /api/balance` — wallet USDC + MATIC
- `POST /api/control/start` — start bot
- `POST /api/control/stop` — stop bot
- WebSocket `/socket.io` — pushes:
  - `tick` event every 1s with snapshot of all live markets
  - `trade` event when a new trade is placed
  - `resolution` event when a market resolves

### dashboard/templates/index.html
Single page, Bloomberg terminal aesthetic:
- Pure black background `#000`
- Monospace font (JetBrains Mono or Courier)
- Primary color: phosphor green `#00ff00`
- Secondary: amber `#ffb000`
- Critical/loss: red `#ff3030`
- All caps for headers and labels
- Solid box borders, no rounded corners
- Layout: grid of panels, each with title bar

Panel layout:
```
┌─────────────────────────────────────────────────────────────┐
│ POLYBOT [TIMESTAMP UTC]    [BALANCE] [P&L] [WIN%] [STATUS]  │  status bar
├─────────────────────┬───────────────────────────────────────┤
│                     │                                       │
│  LIVE MARKETS       │  PNL CHART                            │
│  (countdown + side  │  (cumulative P&L over time)           │
│   + price + bet/no) │                                       │
│                     │                                       │
├─────────────────────┼───────────────────────────────────────┤
│                     │                                       │
│  TRADE HISTORY      │  WIN RATE / STATS                     │
│  (scrolling list)   │  (last 50 bets, win/loss counts,      │
│                     │   today vs all-time)                  │
│                     │                                       │
├─────────────────────┴───────────────────────────────────────┤
│ LOG TAIL (recent bot actions)                               │  bottom bar
└─────────────────────────────────────────────────────────────┘
```

### dashboard/static/terminal.js
- Connect to Socket.IO on load
- On `tick` event: update Live Markets panel
- On `trade` event: prepend to Trade History, flash the row
- On `resolution`: update P&L chart, refresh stats
- Render P&L chart with Chart.js or a tiny custom canvas (no heavy library)

## Concurrency Model

Single Python process, two threads:
1. **Bot thread** — runs the main polling loop
2. **Flask/SocketIO thread** — serves the dashboard

Shared state:
- `TradeTracker` (thread-safe via internal lock)
- `Bot.status` dict (read by dashboard, written by bot — use lock or atomic dict)

No multiprocessing needed. The workload is I/O-bound (HTTP polls) so the GIL isn't a bottleneck.

## Error Handling

The bot should NEVER crash. Every external call wrapped in try/except:
- API timeout → log warning, retry next tick
- Order placement failure → log error, mark Trade as `status="failed"`, continue
- Resolution check failure → retry on next tick

Errors flow to:
1. Log file (`logs/bot.log`)
2. Dashboard status panel (last error visible)
3. Trade tracker (for failed trades)

## Simulation Mode

When `PRODUCTION=false`:
- Bot runs everything normally
- Strategy evaluates and returns BetDecisions
- Instead of calling `place_market_buy`, log "SIMULATED: would buy..."
- Still record the Trade in tracker with a marker `status="simulated"`
- Still wait for resolution and compute P&L
- Lets the user validate strategy logic without risking funds

This is critical for the user — they want to switch to simulation easily.

## Deployment

Runs as a single command:
```bash
python main.py
```

That starts:
- The bot loop in a thread
- The Flask + SocketIO server on port 8080 (configurable)

User opens `http://localhost:8080` to see the dashboard.

Stop with Ctrl+C — should cleanly shut down both threads.

## Dependencies (requirements.txt)

```
requests>=2.31
python-dotenv>=1.0
py-clob-client>=0.18    # latest stable
web3>=6.11
eth-account>=0.10
flask>=3.0
flask-socketio>=5.3
python-socketio>=5.10
eventlet>=0.33          # for SocketIO async mode
```

Keep it minimal. No pandas (use stdlib csv), no plotly (use Chart.js in browser).
