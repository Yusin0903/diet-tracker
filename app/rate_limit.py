"""記憶體版 per-IP 速率限制,擋邀請碼/密碼暴力嘗試。

滑動視窗:某 key 在 window_s 內失敗達 max_failures 次,就鎖 block_s 秒。
- 只計「失敗」,成功會 reset,不影響正常使用者。
- 單機部署夠用;若日後多副本/水平擴展,改用 Redis 等共享儲存。
"""
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request


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


def client_ip(request: Request) -> str:
    """取得真實來源 IP。Zeabur 等反向代理會帶 X-Forwarded-For。"""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
