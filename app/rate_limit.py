"""記憶體版 per-IP 速率限制,擋邀請碼/密碼暴力嘗試。

滑動視窗:某 key 在 window_s 內失敗達 max_failures 次,就鎖 block_s 秒。
- 只計「失敗」,成功會 reset,不影響正常使用者。
- 單機部署夠用;若日後多副本/水平擴展,改用 Redis 等共享儲存。
"""
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request

from app.settings import settings


class RateLimiter:
    def __init__(self, max_failures: int, window_s: int, block_s: int):
        self.max_failures = max_failures
        self.window_s = window_s
        self.block_s = block_s
        self._fails: dict[str, deque] = defaultdict(deque)
        self._blocked: dict[str, float] = {}
        self._lock = Lock()

    def check(self, key: str) -> None:
        """進入端點前先呼叫:若該 key 正在鎖定就丟 429。"""
        now = time.time()
        with self._lock:
            until = self._blocked.get(key)
            if until is not None:
                if now < until:
                    retry = int(until - now) + 1
                    raise HTTPException(
                        status_code=429,
                        detail=f"嘗試太多次,請 {retry} 秒後再試",
                        headers={"Retry-After": str(retry)},
                    )
                # 鎖過期,清掉
                del self._blocked[key]

    def record_failure(self, key: str) -> None:
        """一次失敗的嘗試;達門檻就上鎖。"""
        now = time.time()
        with self._lock:
            dq = self._fails[key]
            dq.append(now)
            while dq and dq[0] < now - self.window_s:
                dq.popleft()
            if len(dq) >= self.max_failures:
                self._blocked[key] = now + self.block_s
                del self._fails[key]  # 已上鎖,失敗記錄不必再留
            # 定期清掉早就過期的 key,避免大量不同 IP 累積佔記憶體
            if len(self._fails) > 2048:
                self._prune(now)

    def _prune(self, now: float) -> None:
        """移除視窗外已無有效失敗記錄的 key(呼叫端需持有 _lock)。"""
        for k in list(self._fails):
            dq = self._fails[k]
            while dq and dq[0] < now - self.window_s:
                dq.popleft()
            if not dq:
                del self._fails[k]
        for k in [k for k, until in self._blocked.items() if until <= now]:
            del self._blocked[k]

    def reset(self, key: str) -> None:
        """成功後清除該 key 的失敗記錄。"""
        with self._lock:
            self._fails.pop(key, None)
            self._blocked.pop(key, None)


class UsageLimiter:
    """Sliding-window cap on the *total* number of calls per key (not just
    failures). Used to throttle expensive endpoints such as /analyze so a
    single (possibly invited) account can't run up the vision API usage or DoS it.
    """

    def __init__(self, max_calls: int, window_s: int):
        self.max_calls = max_calls
        self.window_s = window_s
        self._calls: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()

    def hit(self, key: str) -> None:
        """Record one call; raise 429 once the key exceeds the window cap."""
        now = time.time()
        with self._lock:
            dq = self._calls[key]
            while dq and dq[0] < now - self.window_s:
                dq.popleft()
            if len(dq) >= self.max_calls:
                retry = int(dq[0] + self.window_s - now) + 1
                raise HTTPException(
                    status_code=429,
                    detail=f"操作太頻繁,請 {retry} 秒後再試",
                    headers={"Retry-After": str(retry)},
                )
            dq.append(now)
            if len(self._calls) > 4096:  # Bound memory across many keys
                for k in list(self._calls):
                    d = self._calls[k]
                    while d and d[0] < now - self.window_s:
                        d.popleft()
                    if not d:
                        del self._calls[k]


def client_ip(request: Request) -> str:
    """Resolve the real client IP behind a reverse proxy.

    Each proxy *appends* the address that connected to it, so with N trusted
    proxies in front of us the real client is the Nth-from-last entry. Reading
    from the right means a client that forges `X-Forwarded-For: <fake>` only
    pollutes the left side, which we ignore — so the limiter can't be bypassed
    by spoofing the header.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            hops = max(1, settings.trusted_proxy_hops)
            return parts[max(0, len(parts) - hops)]
    return request.client.host if request.client else "unknown"
