from __future__ import annotations

import random
import sys
import threading
from typing import Any

from eth_account import Account
from soft_hub.sdk import CancelledError, HubAccount, HubContext

from plugin.sekai_bot.adspower import AdsPowerClient, AdsPowerError, find_duplicate_profiles
from plugin.sekai_bot.client import SekaiClient
from plugin.sekai_bot.config import CHAIN_ID, GAS_RESERVE_HYPE, RunOptions
from plugin.sekai_bot.faucet import claim_hype
from plugin.sekai_bot.onchain import run_cycles
from plugin.sekai_bot.parse import snapshot
from plugin.sekai_bot.personality import roll_personality
from plugin.sekai_bot.utils import (
    from_wei,
    interruptible_sleep,
    normalize_private_key,
    normalize_proxy,
    safe_error,
    to_wei,
)

SUPPORTED_OS = frozenset({"darwin"})
WRITE_ACTIONS = frozenset({"farm", "activities"})
FAUCET_ACTIONS = frozenset({"farm", "faucet"})


def run(context: HubContext) -> dict[str, Any]:
    if sys.platform not in SUPPORTED_OS:
        raise RuntimeError("Этот софт собран для macOS")
    if context.action_id not in {"inspect", "farm", "activities", "faucet"}:
        raise ValueError("Неизвестное действие")

    options = _options(context)
    _protect_all(context)
    blocked = _preflight_adspower(context) if context.action_id in FAUCET_ACTIONS else set()

    counters = {
        "total": len(context.accounts),
        "succeeded": 0,
        "partial": 0,
        "failed": 0,
        "blocked": len(blocked),
        "cancelled": 0,
        "transactions": 0,
    }
    lock = threading.Lock()

    context.log(
        "Старт Sekai",
        data={
            "действие": context.action_id,
            "аккаунтов": len(context.accounts),
            "одновременно": context.account_concurrency,
            "сеть": CHAIN_ID,
        },
    )

    def worker(account: HubAccount) -> str:
        if account.id in blocked:
            return "blocked"
        try:
            status = _run_account(context, account, options)
        except CancelledError:
            with lock:
                counters["cancelled"] += 1
            _terminal(context, account, "cancelled", "cancelled", "Остановлено")
            raise
        except Exception as exc:
            with lock:
                counters["failed"] += 1
            _terminal(context, account, "failed", "failed", "Ошибка обработки аккаунта", {"error": safe_error(exc)})
            return "failed"
        with lock:
            counters[status] = counters.get(status, 0) + 1
        return status

    queue = [account for account in context.accounts if account.id not in blocked]
    random.shuffle(queue)
    batch_size = max(1, int(context.account_concurrency))
    total_batches = (len(queue) + batch_size - 1) // batch_size if queue else 0
    for batch_index in range(0, len(queue), batch_size):
        context.check_cancelled()
        batch = tuple(queue[batch_index : batch_index + batch_size])
        number = batch_index // batch_size + 1
        labels = ", ".join(account.label for account in batch)
        context.log(
            f"Пачка {number}/{total_batches}: {len(batch)} аккаунтов — {labels}",
            data={"batch": number, "size": len(batch)},
        )
        context.map_accounts(worker, accounts=batch)
    return {
        "total": counters["total"],
        "succeeded": counters["succeeded"],
        "partial": counters["partial"],
        "failed": counters["failed"],
        "blocked": counters["blocked"],
        "cancelled": counters["cancelled"],
        "chain_id": CHAIN_ID,
        "action": context.action_id,
        "account_concurrency": context.account_concurrency,
    }


def _run_account(context: HubContext, hub: HubAccount, options: RunOptions) -> str:
    context.check_cancelled()
    context.account_state(hub.id, status="running", stage="preflight", progress=0.06, message="Проверяю ключ, прокси и сеть")

    private_key = normalize_private_key(hub.secret("evm_private_key"))
    if hub.evm_address:
        derived = Account.from_key(private_key).address
        if derived.lower() != hub.evm_address.lower():
            raise RuntimeError("Ключ не совпадает с адресом в Hub")
    try:
        proxy = normalize_proxy(hub.secret("proxy"))
    except KeyError:
        proxy = None
    _protect(context, private_key)
    if private_key.startswith("0x"):
        _protect(context, private_key[2:])
    if proxy:
        _protect(context, proxy)

    client = SekaiClient(private_key, proxy, timeout=options.timeout_seconds)
    client.ensure_chain()
    client.refresh_dex()

    personality = roll_personality(client.address, context.run_id, options.cycles_from, options.cycles_to)
    context.log(
        f"{hub.label}: стиль {personality.family}, кругов {personality.cycles}",
        account_id=hub.id,
        data=personality.public(),
    )
    interruptible_sleep(random.uniform(0.2, 1.4), context.check_cancelled)

    if context.action_id == "inspect":
        context.account_state(hub.id, status="running", stage="inspect", progress=0.45, message="Читаю балансы")
        data = snapshot(client)
        context.result(f"{hub.label}: балансы", kind="account_snapshot", status="succeeded", account_id=hub.id, data=data)
        context.account_state(hub.id, status="succeeded", stage="completed", progress=1.0, message=f"HYPE {data['hype']}")
        return "succeeded"

    txs = 0
    if context.action_id in FAUCET_ACTIONS:
        context.account_state(hub.id, status="running", stage="faucet", progress=0.16, message="Открываю кран в AdsPower")
        profile_id = hub.secret("adspower_profile")
        api_key = context.settings.secret("adspower_api")
        _protect(context, profile_id)
        _protect(context, api_key)
        ads = AdsPowerClient(api_key)
        opened = False
        try:
            bal = claim_hype(
                client=client,
                ads=ads,
                profile_id=profile_id,
                personality=personality,
                log=lambda msg: context.log(msg, account_id=hub.id),
                cancel=context.check_cancelled,
                target_wei=to_wei("0.08"),
            )
            opened = True
            context.log(f"После крана: {from_wei(bal)} HYPE", account_id=hub.id)
        except AdsPowerError as exc:
            context.log(str(exc), level="warning", account_id=hub.id)
        except Exception as exc:
            context.log(f"Кран не удался: {safe_error(exc)}", level="warning", account_id=hub.id)
        finally:
            ads.close()
        context.account_state(
            hub.id,
            status="running",
            stage="funded" if opened else "faucet_failed",
            progress=0.28,
            message="Профиль открыт, кран отработал" if opened else "Профиль AdsPower не открылся",
        )

    if context.action_id == "faucet":
        data = snapshot(client)
        data["style"] = personality.family
        context.result(f"{hub.label}: кран", kind="account_summary", status="succeeded", account_id=hub.id, data={"hype": data["hype"], "style": personality.family})
        context.account_state(hub.id, status="succeeded", stage="completed", progress=1.0, message=f"HYPE {data['hype']}")
        return "succeeded"

    context.account_state(hub.id, status="running", stage="onchain", progress=0.36, message="Ончейн-активности")
    total_cycles = max(1, personality.cycles)

    def on_tx(result: Any) -> None:
        nonlocal txs
        if getattr(result, "ok", False):
            txs += 1

    txs += run_cycles(
        client,
        personality,
        log=lambda msg: context.log(msg, account_id=hub.id),
        cancel=context.check_cancelled,
        on_tx=on_tx,
    )
    # Milestone after work, before snapshot.
    progress = min(0.92, 0.36 + 0.50)
    context.account_state(hub.id, status="running", stage="snapshot", progress=progress, message="Снимаю итог")
    snap = snapshot(client)
    payload = {
        "hype": snap["hype"],
        "lst": snap["lst"],
        "lp": snap["lp"],
        "transactions": txs,
        "cycles": total_cycles,
        "style": personality.family,
    }
    status = "succeeded" if txs > 0 or to_wei(snap["hype"]) >= to_wei(GAS_RESERVE_HYPE) else "partial"
    context.result(
        f"{hub.label}: цикл завершён",
        kind="account_summary",
        status=status,
        account_id=hub.id,
        data=payload,
    )
    if status == "succeeded":
        context.account_state(hub.id, status="succeeded", stage="completed", progress=1.0, message=f"HYPE {snap['hype']}, tx {txs}")
    else:
        context.account_state(hub.id, status="partial", stage="completed", message=f"Мало активности, HYPE {snap['hype']}")
    return status


def _options(context: HubContext) -> RunOptions:
    raw = context.options or {}
    lo = int(raw.get("cycles_from", 2))
    hi = int(raw.get("cycles_to", 4))
    lo = max(1, min(8, lo))
    hi = max(lo, min(8, hi))
    return RunOptions(cycles_from=lo, cycles_to=hi)


def _protect(context: HubContext, value: str | None) -> None:
    if isinstance(value, str) and 4 <= len(value) <= 4096:
        try:
            context.protect_secret(value)
        except Exception:
            return


def _protect_all(context: HubContext) -> None:
    for account in context.accounts:
        for kind in ("evm_private_key", "proxy", "adspower_profile"):
            try:
                _protect(context, account.secret(kind))
            except KeyError:
                continue
    for kind in ("adspower_api",):
        try:
            _protect(context, context.settings.secret(kind))
        except KeyError:
            continue


def _preflight_adspower(context: HubContext) -> set[str]:
    blocked: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for account in context.accounts:
        try:
            profile = account.secret("adspower_profile")
        except KeyError:
            _terminal(context, account, "blocked", "missing_adspower", "Нет AdsPower профиля")
            blocked.add(account.id)
            continue
        if not (profile or "").strip():
            _terminal(context, account, "blocked", "missing_adspower", "Пустой AdsPower профиль")
            blocked.add(account.id)
            continue
        pairs.append((account.id, profile))
    try:
        context.settings.secret("adspower_api")
    except KeyError:
        for account in context.accounts:
            if account.id not in blocked:
                _terminal(context, account, "blocked", "missing_adspower_api", "Нет AdsPower API key в настройках Hub")
                blocked.add(account.id)
        return blocked
    for group in find_duplicate_profiles(pairs):
        for account_id in group:
            account = next(item for item in context.accounts if item.id == account_id)
            _terminal(context, account, "blocked", "adspower_conflict", "Один AdsPower-профиль на двух аккаунтах")
            blocked.add(account_id)
    return blocked


def _terminal(
    context: HubContext,
    account: HubAccount,
    status: str,
    stage: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> None:
    kwargs: dict[str, Any] = {"status": status, "stage": stage, "message": message}
    if data:
        kwargs["data"] = data
    if status == "succeeded":
        kwargs["progress"] = 1.0
    context.account_state(account.id, **kwargs)
