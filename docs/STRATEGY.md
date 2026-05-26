# Strategy: Watch T-120s, Bet T-90s

## The One-Sentence Version

At 2 minutes before a BTC 5m market resolves, watch the favourite. If its price is between 85¢ and 96¢, wait 30 seconds. At T-90s, if the same side is still the favourite and its price is below 98¢, buy market on that side.

## Why It Works (Hypothesis)

In BTC 5-minute UP/DOWN markets, the favourite at T-120s is already the genuine likely winner — BTC has had 3 minutes to move and the market reflects that. But the price hasn't fully converged to 1.0 yet because:

1. The 60-second confirmation window between T-120s and T-90s catches markets that genuinely stabilized (good edge) and rejects ones where BTC reversed (cuts losses)
2. At avg price ~0.91 you collect ~9¢ per win
3. With ~94% real win rate, the math works out to +2.5% EV per bet after fees

## The Numbers

From 12.5 days of historical data (3,580 markets):

| Metric | Value |
|---|---|
| Bets placed | 740 |
| Wins | 696 |
| Losses | 44 |
| Win rate | 94.05% |
| Avg entry price (a) | 0.9092 |
| Fee rate | 7% × p × (1-p), avg ~0.6% |
| EV per dollar | +2.50% |
| Bets per day | ~59 (varies by BTC volatility) |
| Daily P&L @ 10 shares | +$13.45 |
| Negative days | 2 of 13 (May 20: -$10.97, May 22: -$6.32) |

The two losing days each had unusual loss clustering — 4-5 losses in a few hours coinciding with BTC volatility spikes. This is the expected worst case.

## Exact Logic

```python
# At every 1-second snapshot of a BTC 5m market:

# Phase 1 — Watch (only fires once)
if not ctx.flagged and 118 <= remaining_seconds <= 122:
    fav_price = max(up_ask, down_ask)
    fav_side  = "Up" if up_ask >= down_ask else "Down"
    if 0.85 <= fav_price < 0.96:
        ctx.flagged = True
        ctx.flagged_side = fav_side
    else:
        ctx.bet_placed = True  # mark resolved, never check again

# Phase 2 — Bet (only fires if flagged, fires once)
if ctx.flagged and not ctx.bet_placed and 88 <= remaining_seconds <= 92:
    current_fav = "Up" if up_ask >= down_ask else "Down"
    current_price = max(up_ask, down_ask)
    
    if current_fav != ctx.flagged_side:
        ctx.bet_placed = True  # side flipped, skip
        return None
    
    if current_price >= 0.98:
        ctx.bet_placed = True  # payout too small
        return None
    
    return BetDecision(
        side = current_fav,
        token_id = up_token_id if current_fav == "Up" else down_token_id,
        price = current_price,
        reason = f"watch T-120 in [0.85,0.96), bet T-90 @ {current_price:.3f}"
    )
```

## Tolerance Note

The "120s" and "90s" check uses ±2 second tolerance because:
- Snapshots happen every 1 second but with small jitter
- A bot poll might capture 119s, 120s, or 121s
- Without tolerance you'd miss ~10% of valid markets

The phase guards (`not ctx.flagged`, `not ctx.bet_placed`) ensure each phase only fires once per market even with the tolerance window.

## Why Not Other Strategies (Tested and Rejected)

The user and I scanned dozens of alternatives on the same data. Summary:

| Strategy | Result | Why Rejected |
|---|---|---|
| Bet at T-120s directly (no T-90s confirm) | EV +1.24% | Lower edge, more losses |
| Bet at T-10s | EV +0.5% raw, but 58% of markets are unbuyable at 1.0 by then | Liquidity issues |
| Underdog (cheap side) | EV -4% to -7% across all variants | Market correctly prices longshots |
| Fade the drop (bet underdog when favourite drops) | EV -3% | Confirmed: BTC moves continue, not reverse |
| Mean reversion (bet opposite of previous market) | EV -3.6% | BTC has no memory between 5m windows |
| Momentum (bet if price rising T-180 to T-60) | EV +0.5% at best | Less edge than simple threshold |
| Full consensus (all 5 timestamps rising) | EV +3% but only 35 bets in dataset | Too few for confidence |
| Triple confirmation T-150/T-120/T-90 at 0.90+ | EV +2.68% (97.2% wr) | Higher EV but lower volume; current strategy wins on total profit |
| Hedge / leg-in both sides | Net ~breakeven realistically | Leg 2 doesn't get cheap enough 63% of the time |
| Bonereaper's market-making (buy both sides cheap) | Same problem | Requires both sides to swing cheap in same window — rare |

## Tunable Parameters (in .env)

```dotenv
WATCH_SECOND=120          # When to flag the market
BET_SECOND=90             # When to place the bet
PRICE_MIN=0.85            # Min favourite price at watch
PRICE_MAX=0.96            # Max favourite price at watch (exclusive)
BET_PRICE_MAX=0.98        # Skip if price at bet time is this high (exclusive)
SHARES_PER_BET=2          # Start small, scale after 100+ live bets
```

## Scaling Plan

Martin will start at 2 shares to validate live execution matches backtest. Scaling protocol:

| Live bets collected | Action |
|---|---|
| 0-100 | Stay at 2 shares |
| 100-300 | If live win rate >90%, move to 10 shares |
| 300-500 | If still >90%, move to 50 shares |
| 500+ | Full confidence, scale to 100 shares or until slippage hurts |

Stop scaling when actual fill price diverges from quoted price by more than 0.5% — that's the liquidity wall.

## Known Risks

1. **Edge may disappear if more bots discover it**. The user is small enough (10-100 shares) to likely stay under the radar of large arbitrage bots.
2. **High-volatility BTC days** cluster losses. The two negative days in backtest correlate with sharp BTC moves.
3. **Liquidity at T-90s can be thin** — orderbook may jump 1-2¢ between fills. Use FOK orders to either fill at quoted price or cancel.
4. **Sample size is still small** — 740 bets is the data we have, not enough for full statistical confidence. Need 1500+ for real certainty.
