from __future__ import annotations

from typing import Any

from .client import SekaiClient
from .config import GAS_RESERVE_HYPE
from .utils import from_wei, to_wei


def snapshot(client: SekaiClient) -> dict[str, Any]:
    native = client.native_balance()
    lst = client.erc20_balance(client.lst)
    whype = client.erc20_balance(client.whype)
    lp = client.erc20_balance(client.lp)
    nonce = client.nonce("latest")
    pending = client.nonce("pending")
    mint_ready = native >= to_wei(GAS_RESERVE_HYPE) + to_wei("0.02")
    return {
        "hype": from_wei(native),
        "whype": from_wei(whype),
        "lst": from_wei(lst),
        "lp": from_wei(lp),
        "tx_count": nonce,
        "pending": max(0, pending - nonce),
        "mint_ready": bool(mint_ready),
    }
