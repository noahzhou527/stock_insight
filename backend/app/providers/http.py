"""Shared HTTP client: one session per provider, throttle, timeout, backoff, proxy fix.

Replaces the three copies of ``_clear_broken_local_proxy`` in the legacy code.
Every request goes through ``HttpClient.get`` so that rate limiting and the
30 s → 2 min → 10 min backoff (§4.1 其它规则) actually apply.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from curl_cffi import requests
from curl_cffi.const import CurlHttpVersion

from .base import DataFetchError

BACKOFF_STEPS = (30.0, 120.0, 600.0)
# Consecutive failures before backoff kicks in (one transient error must not block a source).
BACKOFF_AFTER = 3


def clear_broken_local_proxy() -> None:
    """Remove the known broken loopback proxy (port 9) from this process only."""
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        value = os.environ.get(name)
        if not value:
            continue
        parsed = urlparse(value if "://" in value else f"http://{value}")
        if parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.port == 9:
            os.environ.pop(name, None)


@dataclass
class HttpClient:
    provider: str
    min_interval: float = 0.3
    timeout: float = 20.0
    # Eastmoney push2/push2his fail the TLS handshake over HTTP/2 (curl 35); force HTTP/1.1.
    force_http11: bool = False
    default_headers: dict = field(default_factory=dict)
    clock: callable = time.monotonic
    sleep: callable = time.sleep

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._last_request = 0.0
        self._failures = 0
        self._blocked_until = 0.0
        self._session = None

    def _get_session(self):
        if self._session is None:
            clear_broken_local_proxy()
            self._session = requests.Session(impersonate="chrome", trust_env=False)
        return self._session

    @property
    def blocked_for(self) -> float:
        return max(0.0, self._blocked_until - self.clock())

    def _record_failure(self) -> None:
        self._failures += 1
        if self._failures >= BACKOFF_AFTER:
            step = BACKOFF_STEPS[min(self._failures - BACKOFF_AFTER, len(BACKOFF_STEPS) - 1)]
            self._blocked_until = self.clock() + step

    def get(self, url: str, *, params: dict | None = None, headers: dict | None = None):
        """GET and return the response; raises DataFetchError with a Chinese message."""
        with self._lock:
            if self.blocked_for > 0:
                raise DataFetchError(
                    "provider_backoff",
                    f"{self.provider} 连续请求失败，{int(self.blocked_for)} 秒内暂停访问。",
                )
            wait = self.min_interval - (self.clock() - self._last_request)
            if wait > 0:
                self.sleep(wait)
            self._last_request = self.clock()

        merged = {**self.default_headers, **(headers or {})}
        extra = {}
        if self.force_http11:
            extra["http_version"] = CurlHttpVersion.V1_1
            merged.setdefault("Connection", "close")
        try:
            response = self._get_session().get(url, params=params, headers=merged, timeout=self.timeout, **extra)
        except Exception as error:  # curl_cffi raises its own RequestException family
            self._record_failure()
            text = str(error).lower()
            if "timed out" in text or "timeout" in text:
                raise DataFetchError("timeout", f"{self.provider} 请求超时。", error) from error
            raise DataFetchError("network_error", f"无法连接 {self.provider}，请检查网络或代理。", error) from error

        status = response.status_code
        if status == 404:
            # A definitive "no such resource" (e.g. a year before listing) is not a source failure.
            self._failures = 0
            raise DataFetchError("not_found", f"{self.provider} 没有该数据（HTTP 404）。", url)
        if status == 429:
            self._record_failure()
            raise DataFetchError("rate_limit", f"{self.provider} 限制了访问频率，请稍后再试。", url)
        if status >= 400:
            self._record_failure()
            raise DataFetchError("http_error", f"{self.provider} 返回错误（HTTP {status}）。", url)
        if b"/__verify" in response.content[:4096]:
            self._record_failure()
            raise DataFetchError("provider_blocked", f"{self.provider} 要求浏览器人机校验，无法自动取数。", url)
        self._failures = 0
        self._blocked_until = 0.0
        return response
