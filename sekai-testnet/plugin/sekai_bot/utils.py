from __future__ import annotations

import random
import time
from decimal import Decimal, ROUND_DOWN
from typing import Callable
from urllib.parse import quote

from eth_account import Account
from web3 import Web3

WEI = Decimal(10) ** 18
MAX_UINT256 = 2**256 - 1
CancelCheck = Callable[[], None]


def to_wei(value: str | Decimal | int | float) -> int:
    amount = Decimal(str(value))
    return int((amount * WEI).to_integral_value(rounding=ROUND_DOWN))


def from_wei(value: int, decimals: int = 6) -> str:
    amount = Decimal(int(value)) / WEI
    quant = Decimal(1).scaleb(-decimals)
    return str(amount.quantize(quant, rounding=ROUND_DOWN).normalize())


def random_wei(min_value: str, max_value: str, rng: random.Random | None = None) -> int:
    pick = rng.random() if rng is not None else random.random()
    lo = Decimal(str(min_value))
    hi = Decimal(str(max_value))
    if hi < lo:
        lo, hi = hi, lo
    return to_wei(lo + (hi - lo) * Decimal(str(pick)))


def fraction_amount(balance: int, min_fraction: float, max_fraction: float, rng: random.Random | None = None) -> int:
    pick = rng.random() if rng is not None else random.random()
    lo = max(0.0, min(1.0, float(min_fraction)))
    hi = max(0.0, min(1.0, float(max_fraction)))
    if hi < lo:
        lo, hi = hi, lo
    return int(balance * (lo + (hi - lo) * pick))


def interruptible_sleep(seconds: float, cancel: CancelCheck | None = None) -> None:
    deadline = time.monotonic() + max(0.0, float(seconds))
    while True:
        if cancel is not None:
            cancel()
        left = deadline - time.monotonic()
        if left <= 0:
            return
        time.sleep(min(0.4, left))


def normalize_private_key(private_key: str) -> str:
    key = (private_key or "").strip()
    if not key:
        raise ValueError("empty private key")
    if not key.startswith("0x"):
        key = f"0x{key}"
    Account.from_key(key)
    return key


def normalize_proxy(proxy: str | None) -> str | None:
    if not proxy:
        return None
    value = proxy.strip()
    if not value:
        return None
    scheme = "http"
    if "://" in value:
        scheme, value = value.split("://", 1)
    if "@" not in value:
        parts = value.split(":")
        if len(parts) == 4 and parts[1].isdigit():
            host, port, username, password = parts
            value = f"{quote(username, safe='')}:{quote(password, safe='')}@{host}:{port}"
    if "://" not in value:
        value = f"{scheme}://{value}"
    return value


def checksum(value: str) -> str:
    return Web3.to_checksum_address(value)


def deadline(seconds: int) -> int:
    return int(time.time()) + int(seconds)


def safe_error(exc: BaseException) -> str:
    text = str(exc) or exc.__class__.__name__
    return text.replace("\n", " ")[:240]
