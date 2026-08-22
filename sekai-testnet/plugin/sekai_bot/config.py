from __future__ import annotations

from dataclasses import dataclass

CHAIN_ID = 998
RPC_URL = "https://rpc.hyperliquid-testnet.xyz/evm"
SEKAI_API = "https://testnet.sekai.fi"
FAUCET_URL = "https://faucet.quicknode.com/hyperliquid/testnet"
ADSPOWER_API = "http://local.adspower.net:50325"

GG_HYPE_VAULT = "0x92531c1707bbf54949ab143d44dc9e354d9903a9"
GG_HYPE_TOKEN = "0xb31eff3350e0f24728660e59c23d8be31d33d9fe"
SEKAI_DEX = "0x633b786173c3FdbFb96bD0D7C8AEE6a8B376C14D"
TREASURY = "0x77692c324d49F60aB6e77037a2F9409c19bBb997"
WHYPE = "0x5555555555555555555555555555555555555555"
NATIVE_HYPE_ROUTER = "0x920B79B3804015aa6582d8eb88F659b341cCcdB3"
LP_TOKEN = "0xFC7c8EA91DB258bf43e9024Db775956c9d1B04b7"

GAS_RESERVE_HYPE = "0.015"
GAS_MULTIPLIER = 1.20
REQUEST_TIMEOUT = 30
RECEIPT_TIMEOUT = 100
MINT_CANDIDATES = 50
SELL_SLIPPAGE_BPS = 75


@dataclass(frozen=True)
class RunOptions:
    cycles_from: int = 2
    cycles_to: int = 4
    timeout_seconds: int = REQUEST_TIMEOUT
