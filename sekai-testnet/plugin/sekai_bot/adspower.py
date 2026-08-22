"""AdsPower Local API — loopback only, no secret logs."""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

from .config import ADSPOWER_API

LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "local.adspower.net"})
_START_LOCK = threading.Lock()
_LAST_START_MONO = 0.0
_MIN_START_INTERVAL_SEC = 1.8
_START_MAX_RETRIES = 6


class AdsPowerError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass
class AdsPowerSession:
    ws_url: str
    started_by_us: bool


def normalize_profile_id(value: str | None) -> str:
    return (value or "").strip()


def find_duplicate_profiles(pairs: list[tuple[str, str]]) -> list[list[str]]:
    buckets: dict[str, list[str]] = {}
    for account_id, profile_id in pairs:
        pid = normalize_profile_id(profile_id)
        if not pid:
            continue
        buckets.setdefault(pid, []).append(account_id)
    return [ids for ids in buckets.values() if len(ids) > 1]


def assert_local_http_base(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise AdsPowerError("unsafe_endpoint", "AdsPower API должен быть http(s)")
    host = (parsed.hostname or "").lower()
    if host not in LOCAL_HOSTS:
        raise AdsPowerError("unsafe_endpoint", "AdsPower API не локальный")
    if parsed.username or parsed.password:
        raise AdsPowerError("unsafe_endpoint", "AdsPower API URL не должен содержать credentials")
    return url.rstrip("/")


def assert_local_cdp_ws(ws_url: str) -> str:
    parsed = urlparse(ws_url)
    if parsed.scheme not in {"ws", "wss", "http", "https"}:
        raise AdsPowerError("unsafe_endpoint", "AdsPower вернул небезопасный browser endpoint")
    host = (parsed.hostname or "").lower()
    if host not in LOCAL_HOSTS:
        raise AdsPowerError("unsafe_endpoint", "AdsPower CDP endpoint не локальный")
    if not ws_url:
        raise AdsPowerError("adspower_unavailable", "AdsPower start не вернул puppeteer ws")
    return ws_url


class AdsPowerClient:
    def __init__(self, api_key: str, *, api_base: str = ADSPOWER_API, timeout_seconds: int = 20) -> None:
        key = (api_key or "").strip()
        if len(key) < 4:
            raise AdsPowerError("missing_secret", "Не задан AdsPower API key")
        self._api_key = key
        self.api_base = assert_local_http_base(api_base)
        self.timeout_seconds = timeout_seconds
        self._http = requests.Session()
        self._http.trust_env = False
        self._http.headers.update({"Authorization": f"Bearer {key}"})

    def close(self) -> None:
        self._http.headers.pop("Authorization", None)
        self._http.close()
        self._api_key = ""

    def require_profile(self, profile_id: str) -> None:
        pid = normalize_profile_id(profile_id)
        if len(pid) < 4:
            raise AdsPowerError("profile_missing", "У аккаунта нет AdsPower profile ID")
        payload = self._get("/api/v1/user/list", {"user_id": pid, "page": 1, "page_size": 10})
        if int(payload.get("code") or -1) != 0:
            raise AdsPowerError("profile_missing", "AdsPower не нашёл профиль")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        rows = data.get("list") if isinstance(data, dict) else None
        if not isinstance(rows, list) or not rows:
            raise AdsPowerError("profile_missing", "AdsPower не нашёл профиль")

    def start_or_attach(self, profile_id: str) -> AdsPowerSession:
        pid = normalize_profile_id(profile_id)
        active = self._active_ws(pid)
        if active:
            return AdsPowerSession(ws_url=active, started_by_us=False)
        return AdsPowerSession(ws_url=self._start(pid), started_by_us=True)

    def stop_if_started(self, profile_id: str, started_by_us: bool) -> None:
        if not started_by_us:
            return
        try:
            self._get("/api/v1/browser/stop", {"user_id": normalize_profile_id(profile_id)})
        except Exception:
            return

    def _active_ws(self, profile_id: str) -> str | None:
        payload = self._get("/api/v1/browser/active", {"user_id": profile_id})
        if int(payload.get("code") or -1) != 0:
            return None
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        if str((data or {}).get("status") or "").lower() != "active":
            return None
        ws = (data or {}).get("ws") if isinstance(data, dict) else None
        url = str(ws.get("puppeteer") or "") if isinstance(ws, dict) else ""
        return assert_local_cdp_ws(url) if url else None

    def _start(self, profile_id: str) -> str:
        global _LAST_START_MONO
        params = {"user_id": profile_id, "open_tabs": 0, "ip_tab": 0, "headless": 0}
        last = "adspower_unavailable"
        for attempt in range(1, _START_MAX_RETRIES + 1):
            with _START_LOCK:
                wait = _MIN_START_INTERVAL_SEC - (time.monotonic() - _LAST_START_MONO)
                if wait > 0:
                    time.sleep(wait)
                try:
                    payload = self._get("/api/v1/browser/start", params)
                except AdsPowerError as exc:
                    _LAST_START_MONO = time.monotonic()
                    last = exc.code
                    payload = {"code": -1, "msg": exc.code}
                else:
                    _LAST_START_MONO = time.monotonic()
            code = int(payload.get("code") or -1) if isinstance(payload, dict) else -1
            if code == 0:
                data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
                ws = (data or {}).get("ws") if isinstance(data, dict) else None
                url = str(ws.get("puppeteer") or "") if isinstance(ws, dict) else ""
                if not url:
                    raise AdsPowerError("adspower_unavailable", "AdsPower start не вернул puppeteer ws")
                return assert_local_cdp_ws(url)
            msg = str((payload or {}).get("msg") or last).lower()
            transient = any(token in msg for token in ("too many", "rate", "timeout", "busy", "connection"))
            if transient and attempt < _START_MAX_RETRIES:
                time.sleep(min(8.0, 1.4 * attempt + random.uniform(0.3, 1.1)))
                continue
            raise AdsPowerError("adspower_unavailable", "Не удалось запустить AdsPower-профиль")
        raise AdsPowerError("adspower_unavailable", "Не удалось запустить AdsPower-профиль")

    def _get(self, path: str, params: dict[str, Any] | None) -> dict[str, Any]:
        try:
            resp = self._http.get(f"{self.api_base}{path}", params=params, timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            raise AdsPowerError("adspower_unavailable", "Локальный AdsPower API недоступен") from exc
        try:
            payload = resp.json() if resp.content else {}
        except Exception as exc:
            raise AdsPowerError("adspower_unavailable", "AdsPower вернул не JSON") from exc
        if not isinstance(payload, dict):
            raise AdsPowerError("adspower_unavailable", "AdsPower вернул неожиданный ответ")
        if resp.status_code in {401, 403}:
            raise AdsPowerError("adspower_unavailable", "AdsPower API key отклонён")
        if resp.status_code >= 500:
            raise AdsPowerError("adspower_unavailable", "AdsPower API недоступен")
        payload.pop("msg", None)
        return payload
