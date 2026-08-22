"""Per-account anti-sybil style. Not a Hub option."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Any

from .utils import CancelCheck, interruptible_sleep


def _rng(*parts: str) -> random.Random:
    blob = "|".join(parts).encode("utf-8")
    return random.Random(int(hashlib.sha256(blob).hexdigest()[:16], 16))


@dataclass(frozen=True)
class Personality:
    family: str
    cycles: int
    start_lo: float
    start_hi: float
    action_lo: float
    action_hi: float
    cycle_lo: float
    cycle_hi: float
    think_p: float
    think_lo: float
    think_hi: float
    mint_lo: str
    mint_hi: str
    wrap_lo: str
    wrap_hi: str
    lp_lo: str
    lp_hi: str
    redeem_lo: float
    redeem_hi: float
    sell_lo: float
    sell_hi: float
    mint_repeats: int
    redeem_repeats: int
    sell_repeats: int
    wrap_repeats: int
    unwrap_repeats: int
    lp_repeats: int
    do_mint: bool
    do_redeem: bool
    do_sell: bool
    do_wrap: bool
    do_unwrap: bool
    do_lp: bool
    rng: random.Random

    def sleep_start(self, cancel: CancelCheck | None = None) -> None:
        interruptible_sleep(self.rng.uniform(self.start_lo, self.start_hi), cancel)

    def sleep_action(self, cancel: CancelCheck | None = None) -> None:
        interruptible_sleep(self.rng.uniform(self.action_lo, self.action_hi), cancel)
        if self.rng.random() < self.think_p:
            interruptible_sleep(self.rng.uniform(self.think_lo, self.think_hi), cancel)

    def sleep_cycle(self, cancel: CancelCheck | None = None) -> None:
        interruptible_sleep(self.rng.uniform(self.cycle_lo, self.cycle_hi), cancel)

    def public(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "cycles": self.cycles,
            "mint": self.do_mint,
            "lp": self.do_lp,
            "wrap": self.do_wrap,
        }


def roll_personality(address: str, run_id: str, cycles_from: int, cycles_to: int) -> Personality:
    stable = _rng("sekai", address.lower())
    jitter = _rng("sekai", address.lower(), run_id)
    families = ("snappy", "steady", "leisure", "bursty", "night")
    family = families[stable.randrange(len(families))]

    if family == "snappy":
        action, start, cycle, think_p = (4.0, 11.0), (0.4, 3.5), (8.0, 18.0), 0.07
        mint = ("0.04", "0.22")
        wrap = ("0.03", "0.18")
        lp = ("0.04", "0.16")
    elif family == "leisure":
        action, start, cycle, think_p = (12.0, 32.0), (3.0, 14.0), (20.0, 55.0), 0.24
        mint = ("0.02", "0.12")
        wrap = ("0.02", "0.10")
        lp = ("0.03", "0.12")
    elif family == "bursty":
        action, start, cycle, think_p = (2.5, 24.0), (0.6, 9.0), (6.0, 40.0), 0.16
        mint = ("0.03", "0.35")
        wrap = ("0.02", "0.28")
        lp = ("0.05", "0.25")
    elif family == "night":
        action, start, cycle, think_p = (9.0, 22.0), (4.0, 18.0), (15.0, 45.0), 0.20
        mint = ("0.025", "0.14")
        wrap = ("0.02", "0.12")
        lp = ("0.04", "0.14")
    else:
        action, start, cycle, think_p = (7.0, 18.0), (1.0, 7.0), (12.0, 28.0), 0.12
        mint = ("0.04", "0.20")
        wrap = ("0.03", "0.16")
        lp = ("0.06", "0.18")

    def spread(lo: float, hi: float) -> tuple[float, float]:
        a = max(0.2, lo * jitter.uniform(0.8, 1.2))
        b = max(a + 0.4, hi * jitter.uniform(0.85, 1.25))
        return a, b

    lo_c = max(1, min(int(cycles_from), int(cycles_to)))
    hi_c = max(lo_c, max(int(cycles_from), int(cycles_to)))
    skip_lp = stable.random() < 0.18
    skip_wrap = stable.random() < 0.22
    skip_sell = stable.random() < 0.08
    skip_redeem = stable.random() < 0.08

    def repeats(base: int, skip: bool) -> int:
        if skip:
            return 0
        return jitter.randint(1, max(1, base))

    return Personality(
        family=family,
        cycles=jitter.randint(lo_c, hi_c),
        start_lo=spread(*start)[0],
        start_hi=spread(*start)[1],
        action_lo=spread(*action)[0],
        action_hi=spread(*action)[1],
        cycle_lo=spread(*cycle)[0],
        cycle_hi=spread(*cycle)[1],
        think_p=min(0.38, think_p * jitter.uniform(0.6, 1.5)),
        think_lo=jitter.uniform(2.0, 6.0),
        think_hi=jitter.uniform(7.0, 16.0),
        mint_lo=mint[0],
        mint_hi=mint[1],
        wrap_lo=wrap[0],
        wrap_hi=wrap[1],
        lp_lo=lp[0],
        lp_hi=lp[1],
        redeem_lo=0.15 if family != "leisure" else 0.10,
        redeem_hi=0.40 if family != "bursty" else 0.55,
        sell_lo=0.18,
        sell_hi=0.48,
        mint_repeats=repeats(2, False),
        redeem_repeats=repeats(2, skip_redeem),
        sell_repeats=repeats(2, skip_sell),
        wrap_repeats=repeats(2, skip_wrap),
        unwrap_repeats=repeats(2, skip_wrap and stable.random() < 0.5),
        lp_repeats=repeats(3, skip_lp),
        do_mint=True,
        do_redeem=not skip_redeem,
        do_sell=not skip_sell,
        do_wrap=not skip_wrap,
        do_unwrap=not (skip_wrap and stable.random() < 0.5),
        do_lp=not skip_lp,
        rng=jitter,
    )
