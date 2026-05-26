# Working with Martin

This is context about the user. Useful for tone, depth of explanation, and avoiding things that don't help.

## Background

- **Name**: Martin (Polymarket username: MartinCICI)
- **Location**: Slovakia (UTC+1/+2)
- **Background**: Technical, hands-on. Builds trading bots, does electronics/automotive repair, runs Spring Boot + React projects. Native speaker is Slovak; English is fluent but sometimes typos.
- **Previous experience**: Built a 5m BTC trading bot in TypeScript (DumpHedgeTrader fork from Poly-Mike). Familiar with Polymarket API, proxy wallets, CLOB orders.

## Communication Style

- **Prefers prose with concrete numbers** over heavily-bulleted answers
- **Asks short questions** — answer them directly first, expand only if needed
- **Pushes back when something doesn't add up** — appreciate that, work with it
- **Doesn't need hand-holding** on technical fundamentals — Python, async, HTTP, smart contracts are all familiar
- **Honesty over optimism** — when a strategy shows promise but small sample size, say "+2.5% EV but only 740 bets, need 1500 for real confidence"

## What Worked Well in the Conversation

- Showing **EV math step by step** when explaining strategy formulas
- **Threshold scans** with actual numbers across a range, not just "the best is X"
- **Daily breakdowns** so he could see variance, not just averages
- **Flagging when a strategy had a lookahead bias** (e.g. the original T-120s + T-10s confirmation idea was actually invalid because we were using future info at the decision point)
- **Naming risks honestly** — "this is small sample, don't bet the house on it"

## What Annoyed Him (Don't Repeat)

- **Inconsistent recommendations** — at one point I gave a T-90s price filter recommendation in one message and contradicted it in the next. He caught it. Always cross-check the data before stating a number.
- **Lookahead bias errors** — I once analyzed a strategy that used T-10s info as a filter for a T-120s bet, which is impossible in live trading. He spotted it. Always verify the strategy is executable in real time.
- **The original bot's sketchy author** — he forked `polymarket-arbitrage-trading-bot` from someone with a Discord CTA and a pre-filled foreign proxy wallet in the .env. He's correctly paranoid about anything wallet-related. Be extra clear about any address, any signing logic, any external service.

## Things He Cares About

- **Live testing before scaling** — won't go from 2 shares to 100 without 100+ bets of validation
- **The strategy actually being executable** — no lookahead, no impossible-to-poll timing
- **Total daily profit, not just EV%** — high EV with few bets loses to medium EV with high bets if the math works out (it does for the chosen strategy)
- **Safety nets** — the 0.98 cap at T-90s costs $0.73/day but he wants it for protection against thin liquidity
- **Bloomberg terminal aesthetic for the dashboard** — he asked for this specifically, not "modern minimal" or "cyberpunk"

## What He Already Has Running

Don't tell him to do these — he's done them:
- Has a TypeScript bot collecting data continuously
- Has a Polymarket account with MetaMask + proxy wallet activated
- Has USDC and MATIC funded
- Has placed live bets (1 win, 1 loss as of last check at 2 shares)
- Knows the math: EV = p - a - fee, fee = 0.07 × p × (1-p)

## Things to Always Do

1. **Cite actual numbers from the backtest** when recommending a parameter
2. **Show the math** when claiming an edge
3. **Flag uncertainty** — "this is on 12.5 days of data, treat as preliminary"
4. **Verify executability** — does the bot have access to the data needed at the decision time?
5. **Keep responses focused** — he's iterating fast, doesn't want walls of text

## Things to Never Do

1. **Never claim a fee number from memory** — Polymarket changed theirs; always recompute with `0.07 × p × (1-p)`
2. **Never suggest scaling to large share sizes** without 100+ live bets of validation
3. **Never connect to Discord/external community services** in the bot
4. **Never use the original repo's pre-filled wallet address** — it was the original author's, not Martin's
5. **Never use lookahead in strategy logic** — the bot only has access to current and past data at decision time

## How He Tracks the Strategy

His current TypeScript bot already does:
- CSV log of every trade with timestamp, side, price, shares, result
- Sometimes negative days (May 20, 22) get him concerned; explain it's normal variance
- He checks daily P&L manually; the dashboard should make this easier

## The Final State of the Conversation

Before switching to Claude Code:
- Strategy confirmed: watch T-120s in [0.85, 0.96), bet T-90s same side capped at 0.98, 2 shares
- His existing TypeScript bot is running this live
- He wanted a clean Python rewrite with dashboard
- I had started writing the Python bot (`config.py`, `api.py`, `strategies/`, `tracker.py`) but never finished `bot.py`, `main.py`, or the dashboard
- He decided to switch to Claude Code for the implementation — better tooling for a multi-file project

Pick up from there. Don't redo the analysis. The strategy is locked.
