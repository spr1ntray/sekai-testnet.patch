from __future__ import annotations

from typing import Callable

from .client import SekaiClient, TxResult
from .config import GAS_RESERVE_HYPE, SELL_SLIPPAGE_BPS
from .personality import Personality
from .utils import CancelCheck, deadline, fraction_amount, from_wei, random_wei, to_wei

LogFn = Callable[[str], None]


def run_cycles(
    client: SekaiClient,
    personality: Personality,
    *,
    log: LogFn,
    cancel: CancelCheck,
    on_tx: Callable[[TxResult], None],
) -> int:
    txs = 0
    reserve = to_wei(GAS_RESERVE_HYPE)
    for cycle in range(1, personality.cycles + 1):
        cancel()
        log(f"Круг {cycle}/{personality.cycles}")
        steps: list[tuple[str, Callable[[], TxResult | None]]] = []
        if personality.do_mint:
            for _ in range(personality.mint_repeats):
                steps.append(("mint", lambda: _mint(client, personality, reserve, log)))
        extras: list[tuple[str, Callable[[], TxResult | None]]] = []
        if personality.do_redeem:
            for _ in range(personality.redeem_repeats):
                extras.append(("redeem", lambda: _redeem(client, personality, log)))
        if personality.do_sell:
            for _ in range(personality.sell_repeats):
                extras.append(("sell", lambda: _sell(client, personality, log)))
        if personality.do_wrap:
            for _ in range(personality.wrap_repeats):
                extras.append(("wrap", lambda: _wrap(client, personality, reserve, log)))
        if personality.do_unwrap:
            for _ in range(personality.unwrap_repeats):
                extras.append(("unwrap", lambda: _unwrap(client, personality, log)))
        if personality.do_lp:
            for _ in range(personality.lp_repeats):
                extras.append(("lp", lambda: _lp(client, personality, reserve, log)))
        personality.rng.shuffle(extras)
        steps.extend(extras)
        for index, (name, fn) in enumerate(steps):
            cancel()
            try:
                result = fn()
            except Exception as exc:
                log(f"{name}: пропуск ({exc})")
                result = None
            if result is not None:
                on_tx(result)
                if result.ok:
                    txs += 1
            if index + 1 < len(steps):
                personality.sleep_action(cancel)
        if cycle < personality.cycles:
            personality.sleep_cycle(cancel)
    return txs


def _mint(client: SekaiClient, p: Personality, reserve: int, log: LogFn) -> TxResult | None:
    native = client.native_balance()
    available = max(0, native - reserve)
    amount = min(random_wei(p.mint_lo, p.mint_hi, p.rng), available)
    if amount <= 0:
        log("Mint пропущен: мало HYPE на газ")
        return None
    found = client.find_mintable(amount)
    if not found:
        log("Mint пропущен: нет рабочего vault")
        return None
    result = client.mint(amount)
    log(f"Mint {from_wei(amount)} HYPE" + (f" | {result.tx_hash}" if result.tx_hash else ""))
    return result


def _redeem(client: SekaiClient, p: Personality, log: LogFn) -> TxResult | None:
    balance = client.erc20_balance(client.lst)
    amount = fraction_amount(balance, p.redeem_lo, p.redeem_hi, p.rng)
    if amount <= 0:
        log("Redeem пропущен: нет LST")
        return None
    result = client.redeem(amount)
    log(f"Redeem {from_wei(amount)} LST")
    return result


def _sell(client: SekaiClient, p: Personality, log: LogFn) -> TxResult | None:
    balance = client.erc20_balance(client.lst)
    amount = fraction_amount(balance, p.sell_lo, p.sell_hi, p.rng)
    if amount <= 0:
        log("Swap пропущен: нет LST")
        return None
    allowance = client.erc20_allowance(client.lst, client.treasury)
    if allowance < amount:
        client.approve(client.lst, client.treasury)
        p.sleep_action(None)
    quote_data = client.quote_sell(client.vault, amount)
    quote = quote_data.get("quote", quote_data)
    if not quote.get("executable", False):
        log("Swap пропущен: quote не исполняется")
        return None
    whype_out = int(quote.get("whypeOutWei") or 0)
    if whype_out <= 0:
        log("Swap пропущен: quote = 0")
        return None
    min_out = whype_out * (10_000 - SELL_SLIPPAGE_BPS) // 10_000
    result = client.sell(amount, min_out, deadline(1200))
    log(f"Swap {from_wei(amount)} LST")
    return result


def _wrap(client: SekaiClient, p: Personality, reserve: int, log: LogFn) -> TxResult | None:
    amount = random_wei(p.wrap_lo, p.wrap_hi, p.rng)
    native = client.native_balance()
    if amount <= 0 or native - amount < reserve:
        log("Wrap пропущен: мало HYPE")
        return None
    result = client.wrap(amount)
    log(f"Wrap {from_wei(amount)} HYPE")
    return result


def _unwrap(client: SekaiClient, p: Personality, log: LogFn) -> TxResult | None:
    balance = client.erc20_balance(client.whype)
    amount = fraction_amount(balance, 0.25, 0.75, p.rng)
    if amount <= 0:
        log("Unwrap пропущен: нет WHYPE")
        return None
    result = client.unwrap(amount)
    log(f"Unwrap {from_wei(amount)} WHYPE")
    return result


def _lp(client: SekaiClient, p: Personality, reserve: int, log: LogFn) -> TxResult | None:
    amount = random_wei(p.lp_lo, p.lp_hi, p.rng)
    native = client.native_balance()
    last: TxResult | None = None
    if amount > 0 and native - amount >= reserve:
        last = client.add_lp(amount, deadline(1200))
        log(f"LP add {from_wei(amount)} HYPE")
        p.sleep_action(None)
    shares = client.erc20_balance(client.lp)
    remove = fraction_amount(shares, 0.25, 0.75, p.rng)
    if remove > 0:
        allowance = client.erc20_allowance(client.lp, client.router)
        if allowance < remove:
            client.approve(client.lp, client.router)
            p.sleep_action(None)
        last = client.remove_lp(remove, deadline(1200))
        log("LP remove")
    if last is None:
        log("LP пропущен")
    return last
