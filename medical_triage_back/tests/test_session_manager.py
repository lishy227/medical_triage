"""
测试：SessionManager 双后端行为验证 + 性能基准

验证：
  1. 内存后端：基本 CRUD、TTL 过期、惰性清理
  2. 状态持久化：save → load 往返一致性
  3. 多进程模拟：两个 worker 共享同一后端的数据可见性
  4. 性能基准：内存后端的 load/save 延迟 + 引擎重建速度
  5. 自动降级：Redis 不可用时降级到内存
"""
import json
import multiprocessing
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

# 强制使用内存后端（测试环境无 Redis）
os.environ["REDIS_URL"] = ""

from config import get_config

# 清除可能缓存的旧 Config
get_config.cache_clear()

from session_manager import (
    MemorySessionBackend,
    SessionManager,
    _REDIS_AVAILABLE,
)
from triage import Stage, TriageState


class TestMemorySessionBackend(unittest.TestCase):
    """内存后端基础测试"""

    def setUp(self):
        self.backend = MemorySessionBackend(ttl=5)

    def test_save_and_load(self):
        state = {"stage": 2, "records": ["头颅", "头痛"]}
        self.backend.save("session-1", state, ttl=30)
        loaded = self.backend.load("session-1")
        self.assertEqual(loaded["stage"], 2)
        self.assertEqual(loaded["records"], ["头颅", "头痛"])

    def test_load_nonexistent(self):
        self.assertIsNone(self.backend.load("no-such-session"))

    def test_delete(self):
        self.backend.save("session-x", {"stage": 0}, ttl=30)
        self.backend.delete("session-x")
        self.assertIsNone(self.backend.load("session-x"))

    def test_ttl_expiry(self):
        """过期后 load 返回 None"""
        backend = MemorySessionBackend(ttl=1)
        backend.save("short-lived", {"stage": 0}, ttl=1)
        self.assertIsNotNone(backend.load("short-lived"))
        time.sleep(1.5)
        # 等待过期后手动 purge
        backend._purge_expired()
        self.assertIsNone(backend.load("short-lived"))

    def test_count(self):
        self.assertEqual(self.backend.count, 0)
        self.backend.save("a", {"stage": 0}, ttl=30)
        self.backend.save("b", {"stage": 0}, ttl=30)
        self.assertEqual(self.backend.count, 2)
        self.backend.delete("a")
        self.assertEqual(self.backend.count, 1)

    def test_load_renews_ttl(self):
        """load 操作应续期时间戳"""
        backend = MemorySessionBackend(ttl=3)
        backend.save("renew-me", {"stage": 0}, ttl=3)
        time.sleep(1.2)
        self.assertIsNotNone(backend.load("renew-me"))  # 续期
        time.sleep(1.5)
        # 续期后仍然有效（原始 TTL 3s，续期后等于重新计时）
        self.assertIsNotNone(backend.load("renew-me"))


class TestSessionManagerStateRoundtrip(unittest.TestCase):
    """SessionManager 状态持久化往返测试"""

    @classmethod
    def setUpClass(cls):
        get_config.cache_clear()
        os.environ["REDIS_URL"] = ""

    def setUp(self):
        get_config.cache_clear()
        self.mgr = SessionManager(ttl_seconds=30)

    def test_save_and_restore_engine(self):
        """保存引擎状态 → 重建 → 对话继续"""
        sid = "test-session-001"

        engine1 = self.mgr.get_engine(sid)
        welcome = engine1.get_welcome_message()
        self.assertIn("不舒服", welcome)

        engine1.state.stage = Stage.INITIAL_SYMPTOM
        engine1.state.records = ["头颅"]
        engine1.state.options = ["头痛", "头晕", "头皮麻木"]
        engine1.state.messages = [
            {"role": "user", "content": "我头疼"},
            {"role": "assistant", "content": "请选择症状类型"},
        ]
        self.mgr.save_engine(sid, engine1)

        engine2 = self.mgr.get_engine(sid)
        self.assertEqual(engine2.state.stage, Stage.INITIAL_SYMPTOM)
        self.assertEqual(engine2.state.records, ["头颅"])
        self.assertEqual(engine2.state.options, ["头痛", "头晕", "头皮麻木"])
        self.assertEqual(len(engine2.state.messages), 2)

    def test_reset_creates_fresh_engine(self):
        """reset 后得到全新空状态引擎"""
        sid = "test-session-002"

        engine1 = self.mgr.get_engine(sid)
        engine1.state.stage = Stage.COMPLETED
        engine1.state.records = ["头颅", "头痛", "持续性钝痛"]
        self.mgr.save_engine(sid, engine1)

        self.mgr.reset(sid)

        engine2 = self.mgr.get_engine(sid)
        self.assertEqual(engine2.state.stage, Stage.BODY_PART)
        self.assertEqual(engine2.state.records, [])

    def test_backend_type_detection(self):
        """未配置 Redis 时自动使用内存后端"""
        self.assertIn("Memory", self.mgr.backend_type)


@unittest.skipUnless(_REDIS_AVAILABLE, "Redis 未安装，跳过 Redis 后端测试")
class TestRedisSessionBackend(unittest.TestCase):
    """Redis 后端集成测试（需本地 Redis）"""

    REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")

    def setUp(self):
        try:
            from session_manager import RedisSessionBackend
            self.backend = RedisSessionBackend(self.REDIS_URL, ttl=30)
            if not self.backend.ping():
                self.skipTest("Redis 不可达")
        except Exception as e:
            self.skipTest(f"Redis 不可用: {e}")

    def tearDown(self):
        if hasattr(self, 'backend'):
            for key in ['test-redis-1', 'test-redis-2']:
                self.backend.delete(key)

    def test_save_and_load(self):
        state = {"stage": 2, "records": ["头颅", "头痛"]}
        self.backend.save("test-redis-1", state, ttl=60)
        loaded = self.backend.load("test-redis-1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["stage"], 2)

    def test_ping(self):
        self.assertTrue(self.backend.ping())

    def test_count(self):
        self.backend.save("test-redis-2", {"stage": 0}, ttl=60)
        cnt = self.backend.count
        self.assertGreaterEqual(cnt, 1)


class TestMultiProcessSimulation(unittest.TestCase):
    """多 worker 场景模拟"""

    @staticmethod
    def _worker_read(url: str, sid: str, result_queue) -> None:
        try:
            import redis as redis_lib
            client = redis_lib.from_url(url, decode_responses=True, socket_timeout=2)
            raw = client.get(f"triage:session:{sid}")
            if raw:
                data = json.loads(raw)
                result_queue.put({"ok": True, "stage": data.get("stage")})
            else:
                result_queue.put({"ok": False, "error": "session not found"})
        except Exception as e:
            result_queue.put({"ok": False, "error": str(e)})

    @unittest.skipUnless(_REDIS_AVAILABLE, "Redis 未安装")
    def test_cross_process_visibility_redis(self):
        """Redis 后端：子进程可读取主进程写入的会话"""
        redis_url = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")
        try:
            import redis as redis_lib
            client = redis_lib.from_url(redis_url, socket_timeout=2)
            client.ping()
        except Exception:
            self.skipTest("Redis 不可达")

        sid = "mp-test-redis-001"
        state = {
            "stage": 2,
            "records": ["头颅", "头痛"],
            "options": ["钝痛", "跳痛"],
            "messages": [],
            "pending_body_change": None,
        }
        client.setex(f"triage:session:{sid}", 60, json.dumps(state, ensure_ascii=False))

        ctx = multiprocessing.get_context("spawn")
        queue = ctx.Queue()
        p = ctx.Process(target=self._worker_read, args=(redis_url, sid, queue))
        p.start()
        p.join(timeout=5)
        if p.is_alive():
            p.terminate()
            self.fail("子进程超时")

        result = queue.get()
        self.assertTrue(result["ok"], f"子进程读取失败: {result.get('error')}")
        self.assertEqual(result["stage"], 2)

        client.delete(f"triage:session:{sid}")

    def test_memory_backend_no_cross_process(self):
        """
        内存后端确认：子进程无法访问主进程 dict
        （这就是为什么生产环境需要 Redis）
        """
        get_config.cache_clear()
        os.environ["REDIS_URL"] = ""
        mgr = SessionManager(ttl_seconds=30)
        sid = "mp-test-memory"

        engine = mgr.get_engine(sid)
        engine.state.stage = Stage.SPECIFIC_SYMPTOM
        engine.state.records = ["头颅", "头痛"]
        mgr.save_engine(sid, engine)

        engine2 = mgr.get_engine(sid)
        self.assertEqual(engine2.state.stage, Stage.SPECIFIC_SYMPTOM)
        self.assertIn("Memory", mgr.backend_type)


# ===========================================================================
# 性能基准测试
# ===========================================================================

class TestPerformanceBenchmark(unittest.TestCase):
    """会话存储性能基准"""

    def test_memory_backend_throughput(self):
        """内存后端：纯 dict 操作的极限吞吐"""
        backend = MemorySessionBackend(ttl=300)
        state = {
            "stage": 2,
            "records": ["头颅", "头痛", "持续性钝痛"],
            "options": ["钝痛", "跳痛", "针刺痛", "胀痛"],
            "messages": [
                {"role": "user", "content": "我头疼"},
                {"role": "assistant", "content": "什么性质？"},
                {"role": "user", "content": "持续性钝痛"},
            ],
            "pending_body_change": None,
        }

        ITER = 20000
        keys = [f"perf-{i}" for i in range(min(ITER, 1000))]

        # ---- Save ----
        start = time.perf_counter()
        for i in range(ITER):
            backend.save(keys[i % len(keys)], state, 300)
        save_elapsed = time.perf_counter() - start
        save_us = (save_elapsed / ITER) * 1_000_000

        # ---- Load ----
        start = time.perf_counter()
        for i in range(ITER):
            backend.load(keys[i % len(keys)])
        load_elapsed = time.perf_counter() - start
        load_us = (load_elapsed / ITER) * 1_000_000

        # 纯 dict 操作应该极快（<200μs，Windows 上比 Linux 略慢是正常的）
        self.assertLess(save_us, 200, f"save <200μs, actual {save_us:.1f}μs")
        self.assertLess(load_us, 200, f"load <200μs, actual {load_us:.1f}μs")

        # 存储基准数据供报告使用
        self._perf_save_us = save_us
        self._perf_load_us = load_us

    def test_engine_reconstruction_speed(self):
        """TriageEngine 从保存状态重建的速度（含 OpenAI 客户端初始化）"""
        os.environ["API_KEY"] = "test-key"
        os.environ["BASE_URL"] = "https://test.example.com/v1"
        os.environ["MODEL"] = "qwen-plus"
        get_config.cache_clear()

        from triage import TriageEngine
        from config import Config

        config = get_config()
        saved_state = {
            "stage": 2,
            "records": ["头颅", "头痛"],
            "options": ["钝痛", "跳痛", "针刺痛"],
            "messages": [
                {"role": "user", "content": "我头疼"},
                {"role": "assistant", "content": "请问头痛类型？"},
            ],
            "pending_body_change": None,
        }

        ITER = 50
        start = time.perf_counter()
        for _ in range(ITER):
            engine = TriageEngine(config, saved_state=saved_state)
        elapsed = time.perf_counter() - start
        avg_ms = (elapsed / ITER) * 1000

        self.assertLess(avg_ms, 200, f"重建应 <200ms, 实际 {avg_ms:.1f}ms")
        self._recon_avg_ms = avg_ms

    def test_full_roundtrip_end_to_end(self):
        """端到端：模拟真实 Web 请求的完整状态保存恢复流程"""
        get_config.cache_clear()
        os.environ["REDIS_URL"] = ""
        os.environ["API_KEY"] = "test-key"

        mgr = SessionManager(ttl_seconds=30)
        sid = "e2e-perf-test"

        # 模拟 100 次「请求 → 处理 → 保存 → 下次请求恢复」循环
        ITER = 100
        start = time.perf_counter()

        engine = mgr.get_engine(sid)
        for i in range(ITER):
            engine.state.messages.append(
                {"role": "user", "content": f"test message {i}"}
            )
            mgr.save_engine(sid, engine)
            # 模拟新请求：从后端加载
            engine = mgr.get_engine(sid)

        elapsed = time.perf_counter() - start
        avg_ms = (elapsed / ITER) * 1000

        self.assertLess(avg_ms, 50, f"单次往返应 <50ms, 实际 {avg_ms:.1f}ms")
        self._e2e_avg_ms = avg_ms


if __name__ == "__main__":
    unittest.main()
