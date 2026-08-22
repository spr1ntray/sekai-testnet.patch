from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Any

import requests
from eth_account import Account
from web3 import Web3

from .abi import DEX_KERNEL_ABI, ERC20_ABI, NATIVE_HYPE_ROUTER_ABI, VAULT_ABI, WHYPE_ABI
from .config import (
    CHAIN_ID,
    GAS_MULTIPLIER,
    GG_HYPE_TOKEN,
    GG_HYPE_VAULT,
    LP_TOKEN,
    MINT_CANDIDATES,
    NATIVE_HYPE_ROUTER,
    RECEIPT_TIMEOUT,
    REQUEST_TIMEOUT,
    RPC_URL,
    SEKAI_API,
    SEKAI_DEX,
    TREASURY,
    WHYPE,
)
from .utils import MAX_UINT256, checksum

_NONCE_LOCKS: dict[str, threading.Lock] = {}
_NONCE_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class TxResult:
    action: str
    tx_hash: str | None
    ok: bool


class SekaiClient:
    def __init__(self, private_key: str, proxy: str | None, *, timeout: int = REQUEST_TIMEOUT) -> None:
        self.account = Account.from_key(private_key)
        self.address = checksum(self.account.address)
        self.timeout = timeout
        self.http = requests.Session()
        self.http.trust_env = False
        self.http.headers.update({"accept": "application/json"})
        request_kwargs: dict[str, Any] = {"timeout": timeout}
        if proxy:
            proxies = {"http": proxy, "https": proxy}
            self.http.proxies.update(proxies)
            request_kwargs["proxies"] = proxies
        self.w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs=request_kwargs))
        self.vault = checksum(GG_HYPE_VAULT)
        self.lst = checksum(GG_HYPE_TOKEN)
        self.dex = checksum(SEKAI_DEX)
        self.treasury = checksum(TREASURY)
        self.whype = checksum(WHYPE)
        self.router = checksum(NATIVE_HYPE_ROUTER)
        self.lp = checksum(LP_TOKEN)

    def ensure_chain(self) -> None:
        chain_id = int(self.w3.eth.chain_id)
        if chain_id != CHAIN_ID:
            raise RuntimeError(f"wrong_chain:{chain_id}")

    def refresh_dex(self) -> None:
        try:
            response = self.http.get(f"{SEKAI_API}/api/dex/config", timeout=self.timeout)
            payload = response.json()
        except Exception:
            return
        if not response.ok or not payload.get("success"):
            return
        data = payload.get("data") or {}
        self.dex = checksum(str(data.get("dexAddress") or data.get("kernelAddress") or self.dex))
        self.treasury = checksum(str(data.get("treasuryAddress") or self.treasury))
        self.whype = checksum(str(data.get("whypeAddress") or self.whype))
        self.router = checksum(str(data.get("nativeHypeRouterAddress") or self.router))
        self.lp = checksum(str(data.get("lpTokenAddress") or self.lp))

    def native_balance(self) -> int:
        return int(self.w3.eth.get_balance(self.address))

    def nonce(self, block: str = "latest") -> int:
        return int(self.w3.eth.get_transaction_count(self.address, block))

    def erc20_balance(self, token: str) -> int:
        contract = self.w3.eth.contract(address=checksum(token), abi=ERC20_ABI)
        return int(contract.functions.balanceOf(self.address).call())

    def erc20_allowance(self, token: str, spender: str) -> int:
        contract = self.w3.eth.contract(address=checksum(token), abi=ERC20_ABI)
        return int(contract.functions.allowance(self.address, checksum(spender)).call())

    def quote_sell(self, vault: str, amount_wei: int) -> dict[str, Any]:
        response = self.http.get(
            f"{SEKAI_API}/api/dex/quote-sell-lst",
            params={"vault": vault, "lstAmountWei": str(amount_wei)},
            timeout=self.timeout,
        )
        payload = response.json()
        if not response.ok or not payload.get("success"):
            raise RuntimeError("quote_failed")
        return payload["data"]

    def active_lsts(self, limit: int = MINT_CANDIDATES) -> list[dict[str, Any]]:
        response = self.http.get(
            f"{SEKAI_API}/api/lsts",
            params={
                "status": "active",
                "limit": str(max(1, int(limit))),
                "sortBy": "createdAt",
                "sortOrder": "desc",
            },
            timeout=self.timeout,
        )
        payload = response.json()
        if not response.ok or not payload.get("success"):
            return []
        data = payload.get("data") or []
        return data if isinstance(data, list) else []

    def associated_lst(self, vault: str) -> str:
        contract = self.w3.eth.contract(address=checksum(vault), abi=VAULT_ABI)
        return checksum(contract.functions.getAssociatedLST().call())

    def find_mintable(self, amount_wei: int) -> tuple[str, str] | None:
        candidates: list[tuple[str, str | None]] = [(self.vault, self.lst)]
        for item in self.active_lsts():
            vault = item.get("vaultAddress") or item.get("vault") or item.get("address")
            token = item.get("tokenId") or item.get("lstAddress")
            if vault:
                candidates.append((str(vault), str(token) if token else None))
        seen: set[str] = set()
        for vault, token in candidates:
            try:
                vault_cs = checksum(vault)
            except Exception:
                continue
            if vault_cs.lower() in seen:
                continue
            seen.add(vault_cs.lower())
            try:
                contract = self.w3.eth.contract(address=vault_cs, abi=VAULT_ABI)
                contract.functions.deposit(self.address).estimate_gas({"from": self.address, "value": amount_wei})
                try:
                    token_cs = self.associated_lst(vault_cs)
                except Exception:
                    token_cs = checksum(token) if token else self.lst
                self.vault, self.lst = vault_cs, token_cs
                return vault_cs, token_cs
            except Exception:
                continue
        return None

    def approve(self, token: str, spender: str) -> TxResult:
        contract = self.w3.eth.contract(address=checksum(token), abi=ERC20_ABI)
        return self._send(contract.functions.approve(checksum(spender), MAX_UINT256), "approve", 0)

    def mint(self, amount_wei: int) -> TxResult:
        contract = self.w3.eth.contract(address=self.vault, abi=VAULT_ABI)
        return self._send(contract.functions.deposit(self.address), "mint_lst", amount_wei)

    def redeem(self, amount_wei: int) -> TxResult:
        contract = self.w3.eth.contract(address=self.vault, abi=VAULT_ABI)
        return self._send(contract.functions.redeemLST(amount_wei, self.address, 0), "redeem_lst", 0)

    def sell(self, amount_wei: int, min_out: int, deadline_ts: int) -> TxResult:
        contract = self.w3.eth.contract(address=self.dex, abi=DEX_KERNEL_ABI)
        return self._send(
            contract.functions.sellLST(self.vault, amount_wei, self.address, min_out, deadline_ts),
            "sell_lst",
            0,
        )

    def wrap(self, amount_wei: int) -> TxResult:
        contract = self.w3.eth.contract(address=self.whype, abi=WHYPE_ABI)
        return self._send(contract.functions.deposit(), "wrap_hype", amount_wei)

    def unwrap(self, amount_wei: int) -> TxResult:
        contract = self.w3.eth.contract(address=self.whype, abi=WHYPE_ABI)
        return self._send(contract.functions.withdraw(amount_wei), "unwrap_hype", 0)

    def add_lp(self, amount_wei: int, deadline_ts: int) -> TxResult:
        contract = self.w3.eth.contract(address=self.router, abi=NATIVE_HYPE_ROUTER_ABI)
        return self._send(contract.functions.addLiquidityWithHype(0, deadline_ts), "add_liquidity", amount_wei)

    def remove_lp(self, shares_wei: int, deadline_ts: int) -> TxResult:
        contract = self.w3.eth.contract(address=self.router, abi=NATIVE_HYPE_ROUTER_ABI)
        return self._send(contract.functions.removeLiquidityToHype(shares_wei, 0, deadline_ts), "remove_liquidity", 0)

    def _send(self, func: Any, action: str, value: int) -> TxResult:
        gas_price = int(self.w3.eth.gas_price * GAS_MULTIPLIER)
        with _nonce_lock(self.address):
            tx = func.build_transaction(
                {
                    "from": self.address,
                    "chainId": CHAIN_ID,
                    "nonce": self.w3.eth.get_transaction_count(self.address, "pending"),
                    "gas": 1,
                    "gasPrice": gas_price,
                    "value": value,
                }
            )
            estimate = dict(tx)
            estimate.pop("gas", None)
            tx["gas"] = int(self.w3.eth.estimate_gas(estimate) * GAS_MULTIPLIER)
            signed = self.account.sign_transaction(tx)
            raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
            tx_hash = self.w3.eth.send_raw_transaction(raw)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=RECEIPT_TIMEOUT, poll_latency=2.0)
        return TxResult(action=action, tx_hash=Web3.to_hex(tx_hash), ok=int(receipt.get("status", 0)) == 1)


def _nonce_lock(address: str) -> threading.Lock:
    key = address.lower()
    with _NONCE_LOCKS_GUARD:
        lock = _NONCE_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _NONCE_LOCKS[key] = lock
        return lock
