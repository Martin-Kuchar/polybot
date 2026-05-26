# Polymarket Integration Notes

This is a collection of every Polymarket API gotcha hit during development. Read this before writing API code.

## Account Setup

The user's setup:
- MetaMask address: `0xD52687FaC73674Ee9D66f49c9bE81D7bB4189B07`
- Polymarket username: `MartinCICI`
- Polymarket profile URL: `polymarket.com/@martincici`

### Proxy Wallet Activation Issue

When a Polymarket account is created but never used, the profile API returns:
```json
{
  "walletActivated": false,
  "proxyWallet": "0xd52687fac73674ee9d66f49c9bE81D7bB4189b07"  // same as MetaMask
}
```

`walletActivated: false` causes order placement to fail with:
```
"maker address not allowed, please use the deposit wallet flow"
```

**To activate**: place one manual bet through the polymarket.com UI. The first real on-chain transaction deploys a proxy contract. After that, `walletActivated: true` and `proxyWallet` returns a **different** address (a deployed smart contract).

User has likely activated by now since they were getting real fills as of May 24, 2026.

### Getting Proxy Wallet Address

Browser console while logged into polymarket.com:
```javascript
fetch('https://gamma-api.polymarket.com/profiles?address=0xD52687FaC73674Ee9D66f49c9bE81D7bB4189B07')
  .then(r => r.json())
  .then(d => console.log(JSON.stringify(d, null, 2)))
```

Look for `proxyWallet` field. That address goes into `.env` as `PROXY_WALLET_ADDRESS`.

## .env Config

```dotenv
PRIVATE_KEY=0x{metamask_private_key}
PROXY_WALLET_ADDRESS=0x{proxy_address}
SIGNATURE_TYPE=1                # 0=EOA, 1=Proxy, 2=GnosisSafe — must be 1
PRODUCTION=false                # true to enable real orders
```

## API Endpoints

| Purpose | URL |
|---------|-----|
| Markets/events metadata | `https://gamma-api.polymarket.com` |
| Order placement, orderbook | `https://clob.polymarket.com` |
| User activity, trades | `https://data-api.polymarket.com` |
| Polygon RPC (use this one) | `https://polygon-bor-rpc.publicnode.com` |
| Polygon RPC (DON'T USE) | `https://polygon-rpc.com` (unreliable, throws `noNetwork` errors) |

## Market URL Pattern

BTC 5-minute markets follow a deterministic slug:
```
https://polymarket.com/event/btc-updown-5m-{end_timestamp}
```
Where `end_timestamp` is the Unix timestamp of when the market resolves. It always lands on a 5-minute boundary (300-second increments).

Bot discovery: from current time, compute next few 5-minute boundaries and fetch each slug. Most will exist; ones that don't are too far in the future yet.

```python
def get_upcoming_market_timestamps(n=3):
    now = int(time.time())
    # Snap up to next 5-min boundary
    first = ((now // 300) + 1) * 300
    return [first + i * 300 for i in range(n)]
```

## Fetching Market Data

```python
GET https://gamma-api.polymarket.com/events/slug/btc-updown-5m-1779650100
```

Response includes a `markets` array. Each market has:
- `conditionId` — used for redemption
- `clobTokenIds` — JSON-string array of two token IDs, one for Up, one for Down
- `outcomes` — JSON-string array `["Up", "Down"]` (order matches clobTokenIds)
- `closed` — true when resolved
- `tokens` — array with `winner: true/false` once resolved

### Orderbook

```python
GET https://clob.polymarket.com/book?token_id={token_id}
```

Returns `bids` and `asks` arrays. Each entry has `price` (string) and `size` (string).
- Best ask = lowest price in asks (sort ascending)
- Best bid = highest price in bids (sort descending)

## Placing Orders (py-clob-client)

The `@polymarket/clob-client` package recently changed its API. The new way:

```python
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

# Auth
client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=POLYGON,
    key=PRIVATE_KEY,
    signature_type=1,        # proxy mode
    funder=PROXY_WALLET,     # the proxy address
)
creds = client.create_or_derive_api_creds()
client.set_api_creds(creds)

# Place order
order = OrderArgs(
    token_id=TOKEN_ID,
    price=0.91,
    size=2,                  # number of shares
    side=BUY,
)
signed = client.create_order(order, {"tickSize": "0.01"})  # tickSize as OPTIONS dict
resp = client.post_order(signed, OrderType.FOK)
```

### Recent API Changes (Hit During Conversation)

1. `tickSize` is no longer a positional argument. It's now `{"tickSize": "0.01"}` in an options dict.
2. `OrderType.FOK` (Fill Or Kill) is correct for market-like orders. `GTC` keeps stale orders open across rounds — bad for 5m markets.
3. The `order_version_mismatch` error means `py-clob-client` is outdated. Run `pip install -U py-clob-client`.

## Fee Structure

Polymarket charges a parabolic fee based on price:
```
fee_dollars = shares × 0.07 × price × (1 - price)
```

Per dollar wagered: `fee_rate = 0.07 × (1 - price)` (approx)

| Price | Per-dollar fee |
|-------|----------------|
| 0.50 | 1.75% |
| 0.80 | 1.12% |
| 0.85 | 0.89% |
| 0.90 | 0.63% |
| 0.95 | 0.33% |
| 0.99 | 0.07% |

This is why high-price favourite betting has low fee drag.

## Wallet Balance Query

USDC balance lives on Polygon. Use:

```python
from web3 import Web3

w3 = Web3(Web3.HTTPProvider("https://polygon-bor-rpc.publicnode.com"))

USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC.e on Polygon

abi = [{"constant": True, "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"}]

contract = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=abi)
balance_raw = contract.functions.balanceOf(Web3.to_checksum_address(PROXY_WALLET)).call()
balance = balance_raw / 1e6  # USDC has 6 decimals

# MATIC for gas
matic_wei = w3.eth.get_balance(Web3.to_checksum_address(PROXY_WALLET))
matic = w3.from_wei(matic_wei, "ether")
```

**MATIC for gas**: needs maybe $0.50-1 worth in the wallet to pay gas fees. Without it, all transactions silently fail.

## Redemption (Claiming Winning Tokens)

When a market resolves and you held the winning side, you have to manually redeem the tokens for USDC. The CTF contract handles this:

```
Contract: 0x4d97dcd97ec945f40cf65f87097ace5ea0476045
This is the Polymarket Conditional Tokens Framework (verified)
```

The function call is `redeemPositions(collateralToken, parentCollectionId, conditionId, indexSets)`. Index set is `1` for Up, `2` for Down.

The user's existing TypeScript code does this with manual ABI encoding which is fragile. Python with `web3.py` should use the proper ABI interface:

```python
# Use proper contract ABI rather than manual calldata encoding
ctf_abi = [...]  # get from Polygonscan verified source
ctf = w3.eth.contract(address=CTF_CONTRACT, abi=ctf_abi)
tx = ctf.functions.redeemPositions(
    USDC_ADDRESS,
    "0x" + "00" * 32,  # parentCollectionId
    condition_id_bytes32,
    [1] if won_up else [2],
).build_transaction({...})
signed = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
w3.eth.send_raw_transaction(signed.rawTransaction)
```

## Liquidity Notes

- At T-300s (market open): both sides ~50¢, sum to ~$1.01-1.02 (small spread)
- At T-120s: favourite typically 0.75-0.95, sum still ~$1.01
- At T-10s: 58% of markets have favourite at 1.0 (unbuyable — no asks at any price < 1.0)
- Order sizes at T-90s typically 30-300 shares available at quoted ask
- For 100+ share orders expect 1-2¢ slippage (next-tier asks)

## What Bonereaper Does (Competitor Analysis)

User found a successful bot operator `bonereaper` (15,143 trades, +$19,165 P&L since March 2026, wallet `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`). Their visible positions suggest they run multiple strategies:

1. Buy high-confidence favourites (similar to ours)
2. Market making — buy both Up and Down when sum is < $1.00 after fees
3. Occasional underdog lottery bets at 3-15¢

The market-making strategy is **conditional arbitrage** — it requires both sides to swing cheap during the 5-minute window, which only happens about 36% of the time in our backtest. Net is roughly breakeven realistically. Not pursued.

## What Could Go Wrong in Production

1. **Rate limits** — Polymarket may throttle if we poll too aggressively. 1s interval has been fine.
2. **Stale prices** — Orderbook can move between snapshot and order placement. Use FOK to fail loudly rather than fill at bad price.
3. **API downtime** — Both Gamma and CLOB occasionally return 5xx. Catch and retry with backoff.
4. **Wallet runs out of MATIC** — Bot can't redeem winnings. Monitor MATIC balance on dashboard.
5. **Network forks / chain reorgs** — On Polygon this is extremely rare but possible. Trust on-chain confirmation, not just API response.
