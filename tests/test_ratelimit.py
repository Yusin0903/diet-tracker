"""ratelimit.py 的單元測試:鎖定、重置、per-key 隔離、過期、記憶體上限。"""
import time

import pytest
from fastapi import HTTPException

from ratelimit import RateLimiter


def test_locks_after_threshold():
    rl = RateLimiter(max_failures=3, window_s=600, block_s=600)
    ip = "1.1.1.1"
    for _ in range(3):
        rl.check(ip)  # 未鎖前不應丟
        rl.record_failure(ip)
    # 第 3 次失敗後應被鎖
    with pytest.raises(HTTPException) as ei:
        rl.check(ip)
    assert ei.value.status_code == 429
    assert "Retry-After" in ei.value.headers


def test_success_resets():
    rl = RateLimiter(max_failures=3, window_s=600, block_s=600)
    ip = "2.2.2.2"
    rl.record_failure(ip)
    rl.record_failure(ip)
    rl.reset(ip)  # 成功
    # 重置後再兩次失敗仍不該鎖(門檻是 3)
    rl.record_failure(ip)
    rl.record_failure(ip)
    rl.check(ip)  # 不應丟


def test_per_key_isolation():
    rl = RateLimiter(max_failures=2, window_s=600, block_s=600)
    for _ in range(2):
        rl.record_failure("attacker")
    with pytest.raises(HTTPException):
        rl.check("attacker")
    # 另一個 IP 不受影響
    rl.check("innocent")


def test_block_expires():
    rl = RateLimiter(max_failures=1, window_s=600, block_s=1)
    rl.record_failure("3.3.3.3")
    with pytest.raises(HTTPException):
        rl.check("3.3.3.3")
    time.sleep(1.1)
    rl.check("3.3.3.3")  # 鎖過期後放行


def test_window_slides():
    rl = RateLimiter(max_failures=3, window_s=1, block_s=600)
    rl.record_failure("4.4.4.4")
    rl.record_failure("4.4.4.4")
    time.sleep(1.1)  # 前兩次失敗滑出視窗
    rl.record_failure("4.4.4.4")
    rl.check("4.4.4.4")  # 視窗內只剩 1 次,不鎖


def test_prune_bounds_memory():
    rl = RateLimiter(max_failures=10, window_s=0, block_s=600)
    # window_s=0 => 每筆失敗都立刻過期;塞 > 2048 個 key 觸發 prune
    for i in range(2100):
        rl.record_failure(f"ip-{i}")
    # prune 後應大幅縮小(不會無上限累積)
    assert len(rl._fails) < 2048
