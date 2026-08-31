from __future__ import annotations

import time
from typing import Callable

from .adspower import AdsPowerClient
from .client import SekaiClient
from .config import FAUCET_URL
from .personality import Personality
from .utils import CancelCheck, from_wei

ADDRESS_SELECTORS = (
    'input[name="address"]',
    'input[placeholder*="address" i]',
    'input[placeholder*="wallet" i]',
    'input[type="text"]',
    "textarea",
)
CLAIM_SELECTORS = (
    'button:has-text("Claim")',
    'button:has-text("Request")',
    'button:has-text("Send")',
    'button:has-text("Get")',
    'button[type="submit"]',
)


def claim_hype(
    *,
    client: SekaiClient,
    ads: AdsPowerClient,
    profile_id: str,
    personality: Personality,
    log: Callable[[str], None],
    cancel: CancelCheck,
    target_wei: int,
) -> int:
    start = client.native_balance()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("playwright не установлен в окружении софта") from exc

    last = start
    try:
        session = ads.start_or_attach(profile_id)
        with sync_playwright() as playwright:
            cancel()
            browser = playwright.chromium.connect_over_cdp(session.ws_url, timeout=20_000)
            try:
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(FAUCET_URL, wait_until="domcontentloaded", timeout=20_000)
                page.bring_to_front()
                filled = False
                for selector in ADDRESS_SELECTORS:
                    try:
                        locator = page.locator(selector).first
                        locator.wait_for(state="visible", timeout=8_000)
                        locator.fill(client.address, timeout=8_000)
                        filled = True
                        break
                    except Exception:
                        continue
                if not filled:
                    raise RuntimeError("Не нашёл поле адреса на странице крана")
                log("Адрес вставлен в кран")
                time.sleep(personality.rng.uniform(0.4, 1.2))
                attempts = personality.rng.randint(2, 4)
                for attempt in range(1, attempts + 1):
                    cancel()
                    _click_claim(page)
                    log(f"Нажал Claim ({attempt}/{attempts}). Если есть капча — реши в окне профиля")
                    end = time.monotonic() + personality.rng.uniform(4.0, 8.0)
                    while time.monotonic() < end:
                        cancel()
                        time.sleep(0.4)
                    _click_claim(page)
                    last = client.native_balance()
                    log(f"Баланс после попытки {attempt}: {from_wei(last)} HYPE")
                    if target_wei > 0 and last >= target_wei:
                        break
                    if last > start and last >= start + (15 * 10**15):
                        break
                    if attempt < attempts:
                        try:
                            page.reload(wait_until="domcontentloaded", timeout=15_000)
                            for selector in ADDRESS_SELECTORS:
                                try:
                                    locator = page.locator(selector).first
                                    locator.wait_for(state="visible", timeout=4_000)
                                    locator.fill(client.address, timeout=4_000)
                                    break
                                except Exception:
                                    continue
                        except Exception:
                            pass
                        personality.sleep_action(cancel)
                try:
                    page.close()
                except Exception:
                    pass
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
    finally:
        ads.stop(profile_id)
    return client.native_balance()


def _click_claim(page: object) -> None:
    for selector in CLAIM_SELECTORS:
        try:
            locator = page.locator(selector).first  # type: ignore[attr-defined]
            locator.wait_for(state="visible", timeout=4_000)
            locator.click(timeout=4_000, force=True)
            return
        except Exception:
            continue
