from __future__ import annotations
import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests
from web3 import Web3

log = logging.getLogger(__name__)

# Polygon mainnet
PUSD_ADDRESS = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"  # pUSD (CLOB v2 collateral)
CTF_ADDRESS  = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"  # Conditional Tokens Framework

ERC20_BALANCE_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    }
]

CTF_ABI = [
    {
        "name": "redeemPositions",
        "type": "function",
        "inputs": [
            {"name": "collateralToken", "type": "address"},
            {"name": "parentCollectionId", "type": "bytes32"},
            {"name": "conditionId", "type": "bytes32"},
            {"name": "indexSets", "type": "uint256[]"},
        ],
        "outputs": [],
    }
]


@dataclass
class MarketState:
    timestamp: int          # end Unix timestamp of the market
    condition_id: str       # conditionId from Polymarket (hex string)
    up_token_id: str        # CLOB token id for Up
    down_token_id: str      # CLOB token id for Down
    up_ask: float           # best ask price for Up
    down_ask: float         # best ask price for Down
    remaining_seconds: int  # seconds until market closes
    closed: bool            # True once resolved


@dataclass
class Balance:
    usdc: float
    matic: float


class PolymarketAPI:
    def __init__(self, config):
        self.config = config
        self._clob_client = None
        self._w3: Optional[Web3] = None
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    # ── Web3 ──────────────────────────────────────────────────────────────────

    def _web3(self) -> Web3:
        if self._w3 is None:
            self._w3 = Web3(Web3.HTTPProvider(self.config.rpc_url))
            try:
                from web3.middleware import ExtraDataToPOAMiddleware
                self._w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            except Exception:
                pass  # older web3 versions may not need this
        return self._w3

    # ── CLOB client (v2) ──────────────────────────────────────────────────────

    def get_clob_client(self):
        if self._clob_client is not None:
            return self._clob_client

        from py_clob_client_v2 import ClobClient

        # Step 1: derive API credentials (key only — no funder needed)
        temp = ClobClient(
            host=self.config.clob_api_url,
            chain_id=137,
            key=self.config.private_key,
        )
        creds = temp.create_or_derive_api_key()

        # Step 2: full client with deposit wallet + POLY_1271 (signature_type=3)
        self._clob_client = ClobClient(
            host=self.config.clob_api_url,
            chain_id=137,
            key=self.config.private_key,
            creds=creds,
            signature_type=self.config.signature_type,  # 3
            funder=self.config.deposit_wallet_address,
        )
        return self._clob_client

    def get_deposit_wallet(self) -> str:
        """Derive the deposit wallet address without deploying it."""
        client = self.get_clob_client()
        try:
            return client.get_deposit_wallet()
        except Exception as e:
            log.warning("get_deposit_wallet failed: %s", e)
            return ""

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def _get(self, url: str, timeout: int = 5) -> Optional[dict]:
        try:
            resp = self._session.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None  # market not yet live — not an error
            log.warning("GET %s → %s", url, e)
            return None
        except Exception as e:
            log.warning("GET %s failed: %s", url, e)
            return None

    def _get_best_ask(self, token_id: str) -> Optional[float]:
        url = f"{self.config.clob_api_url}/book?token_id={token_id}"
        data = self._get(url)
        if not data:
            return None
        asks = data.get("asks", [])
        if not asks:
            return None
        try:
            return min(float(a["price"]) for a in asks)
        except (KeyError, ValueError, TypeError):
            return None

    # ── Market data ───────────────────────────────────────────────────────────

    def get_market_snapshot(self, timestamp: int) -> Optional[MarketState]:
        # Polymarket slug uses the market START timestamp; our timestamp is the end (start + 300)
        slug = f"btc-updown-5m-{timestamp - 300}"
        url = f"{self.config.gamma_api_url}/events/slug/{slug}"
        data = self._get(url)
        if not data:
            return None

        markets = data.get("markets")
        if not markets:
            return None

        market = markets[0]
        condition_id = market.get("conditionId", "")
        closed = bool(market.get("closed", False))

        try:
            token_ids = json.loads(market["clobTokenIds"])
            outcomes = json.loads(market["outcomes"])
        except (KeyError, json.JSONDecodeError, TypeError) as e:
            log.warning("Failed to parse tokens for %s: %s", slug, e)
            return None

        if len(token_ids) != 2 or len(outcomes) != 2:
            return None

        up_idx = outcomes.index("Up") if "Up" in outcomes else 0
        down_idx = 1 - up_idx
        up_token_id = token_ids[up_idx]
        down_token_id = token_ids[down_idx]

        now = int(time.time())
        remaining = max(0, timestamp - now)

        # Skip orderbook fetch for resolved markets
        if closed:
            return MarketState(
                timestamp=timestamp,
                condition_id=condition_id,
                up_token_id=up_token_id,
                down_token_id=down_token_id,
                up_ask=1.0,
                down_ask=1.0,
                remaining_seconds=0,
                closed=True,
            )

        up_ask = self._get_best_ask(up_token_id) or 0.0
        down_ask = self._get_best_ask(down_token_id) or 0.0

        if up_ask == 0.0 and down_ask == 0.0:
            log.debug("No asks for %s at T-%ds — showing market without prices", slug, remaining)

        return MarketState(
            timestamp=timestamp,
            condition_id=condition_id,
            up_token_id=up_token_id,
            down_token_id=down_token_id,
            up_ask=up_ask,
            down_ask=down_ask,
            remaining_seconds=remaining,
            closed=False,
        )

    def get_market_resolution(self, market_timestamp: int) -> Optional[str]:
        """Returns 'Up', 'Down', or None if not yet resolved."""
        slug = f"btc-updown-5m-{market_timestamp - 300}"
        url = f"{self.config.gamma_api_url}/events/slug/{slug}"
        data = self._get(url)
        if not data:
            return None
        markets = data.get("markets", [])
        if not markets:
            return None
        market = markets[0]

        # Method 1: tokens[].winner (present on some responses)
        for token in market.get("tokens", []):
            if token.get("winner"):
                outcome = token.get("outcome")
                if outcome:
                    return outcome

        # Method 2: outcomePrices — winner resolves to "1" (or nearest to 1.0)
        try:
            prices = json.loads(market.get("outcomePrices", "[]"))
            outcomes = json.loads(market.get("outcomes", "[]"))
            if len(prices) == len(outcomes) == 2:
                idx = max(range(2), key=lambda i: float(prices[i]))
                if float(prices[idx]) >= 0.9:
                    log.debug("Resolution via outcomePrices: %s → %s", slug, outcomes[idx])
                    return outcomes[idx]
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        return None

    # ── Order placement (CLOB v2) ─────────────────────────────────────────────

    def place_market_buy(self, token_id: str, shares: int, price: float) -> dict:
        from py_clob_client_v2 import OrderArgs, OrderType, PartialCreateOrderOptions, Side

        client = self.get_clob_client()
        return client.create_and_post_order(
            order_args=OrderArgs(
                token_id=token_id,
                price=price,
                side=Side.BUY,
                size=float(shares),
            ),
            options=PartialCreateOrderOptions(tick_size="0.01"),
            order_type=OrderType.FAK,
        )

    # ── Balance ───────────────────────────────────────────────────────────────

    def get_balance(self) -> Balance:
        w3 = self._web3()
        # v2: pUSD lives in the deposit wallet (not the EOA)
        wallet = Web3.to_checksum_address(self.config.deposit_wallet_address)

        usdc = 0.0
        try:
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(PUSD_ADDRESS),
                abi=ERC20_BALANCE_ABI,
            )
            raw = contract.functions.balanceOf(wallet).call()
            usdc = raw / 1e6  # pUSD has 6 decimals
        except Exception as e:
            log.warning("pUSD balance check failed: %s", e)

        matic = 0.0
        try:
            matic = float(w3.from_wei(w3.eth.get_balance(wallet), "ether"))
        except Exception as e:
            log.warning("POL balance check failed: %s", e)

        return Balance(usdc=usdc, matic=matic)

    # ── Redemption ────────────────────────────────────────────────────────────

    def redeem_winning_position(self, condition_id: str, won_up: bool) -> bool:
        """Submit CTF redeemPositions transaction. Returns True if tx was sent."""
        w3 = self._web3()
        try:
            ctf = w3.eth.contract(
                address=Web3.to_checksum_address(CTF_ADDRESS),
                abi=CTF_ABI,
            )
            cid_hex = condition_id.replace("0x", "").zfill(64)
            cid_bytes = bytes.fromhex(cid_hex)
            index_sets = [1] if won_up else [2]

            account = w3.eth.account.from_key(self.config.private_key)
            nonce = w3.eth.get_transaction_count(account.address)

            tx = ctf.functions.redeemPositions(
                Web3.to_checksum_address(PUSD_ADDRESS),
                b"\x00" * 32,
                cid_bytes,
                index_sets,
            ).build_transaction({
                "from": account.address,
                "nonce": nonce,
                "gas": 200_000,
                "gasPrice": w3.eth.gas_price,
            })

            signed = w3.eth.account.sign_transaction(tx, self.config.private_key)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            log.info("Redemption tx: %s", tx_hash.hex())
            return True
        except Exception as e:
            log.error("Redemption failed for %s: %s", condition_id, e)
            return False
