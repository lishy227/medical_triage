"""
会话管理器 — 双后端（内存 / Redis），统一接口，自动降级

架构：
  ┌──────────────────────────────────────────────┐
  │              SessionManager                  │
  │  ┌─────────────────┐  ┌──────────────────┐   │
  │  │ MemoryBackend   │  │  RedisBackend    │   │
  │  │ (开发/单进程)    │  │ (生产/多worker)  │   │
  │  └─────────────────┘  └──────────────────┘   │
  └──────────────────────────────────────────────┘

行为：
  - 配置了 REDIS_URL → 使用 Redis（多 worker 共享，持久化）
  - 未配置 REDIS_URL → 使用内存 dict（向后兼容，零依赖）
  - Redis 不可达 → 自动降级到内存 + 打印警告

TTL 策略：
  - 内存模式：惰性清理（get/reset 时 purge 过期会话）
  - Redis  模式：原生 EXPIRE，每次 get 自动续期
"""
import json
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple

from config import Config, get_config
from triage import TriageEngine, TriageState

# ---- Redis 可选导入 ---------------------------------------------------------
try:
    import redis as redis_lib

    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False


# ===========================================================================
# 抽象后端
# ===========================================================================

class BaseSessionBackend(ABC):
    """会话存储后端抽象基类"""

    @abstractmethod
    def load(self, session_id: str) -> Optional[Dict[str, Any]]:
        """加载会话状态，不存在返回 None"""
        ...

    @abstractmethod
    def save(
        self, session_id: str, state: Dict[str, Any], ttl: int
    ) -> None:
        """保存会话状态并设置 TTL（秒）"""
        ...

    @abstractmethod
    def delete(self, session_id: str) -> None:
        """删除会话"""
        ...

    @property
    @abstractmethod
    def count(self) -> int:
        """当前活跃会话数"""
        ...

    def ping(self) -> bool:
        """健康检查（默认 True，子类可覆盖）"""
        return True


# ===========================================================================
# 内存后端（开发 / 单进程）
# ===========================================================================

class MemorySessionBackend(BaseSessionBackend):
    """进程内 dict 存储，带惰性过期清理"""

    def __init__(self, ttl: int = 1800) -> None:
        self._ttl = ttl
        self._store: Dict[str, Tuple[Dict[str, Any], float]] = {}

    # ---- 内部 ----

    def _purge_expired(self) -> int:
        now = time.time()
        expired = [
            sid
            for sid, (_, ts) in self._store.items()
            if now - ts > self._ttl
        ]
        for sid in expired:
            del self._store[sid]
        return len(expired)

    # ---- 接口 ----

    def load(self, session_id: str) -> Optional[Dict[str, Any]]:
        self._purge_expired()
        entry = self._store.get(session_id)
        if entry is None:
            return None
        state, _ = entry
        self._store[session_id] = (state, time.time())  # 续期
        return state

    def save(self, session_id: str, state: Dict[str, Any], ttl: int) -> None:
        self._store[session_id] = (state, time.time())

    def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)

    @property
    def count(self) -> int:
        self._purge_expired()
        return len(self._store)


# ===========================================================================
# Redis 后端（生产 / 多 worker）
# ===========================================================================

class RedisSessionBackend(BaseSessionBackend):
    """Redis 持久化存储，多进程共享"""

    PREFIX = "triage:session:"

    def __init__(self, redis_url: str, ttl: int = 1800) -> None:
        if not _REDIS_AVAILABLE:
            raise RuntimeError(
                "redis 包未安装，请执行: pip install redis"
            )
        self._ttl = ttl
        self._client = redis_lib.from_url(
            redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )

    def _key(self, session_id: str) -> str:
        return f"{self.PREFIX}{session_id}"

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception:
            return False

    def load(self, session_id: str) -> Optional[Dict[str, Any]]:
        try:
            raw = self._client.get(self._key(session_id))
            if raw is None:
                return None
            # 续期
            self._client.expire(self._key(session_id), self._ttl)
            return json.loads(raw)
        except Exception as exc:
            print(f"[RedisSessionBackend] load 失败: {exc}")
            return None

    def save(self, session_id: str, state: Dict[str, Any], ttl: int) -> None:
        try:
            key = self._key(session_id)
            self._client.setex(key, ttl, json.dumps(state, ensure_ascii=False))
        except Exception as exc:
            print(f"[RedisSessionBackend] save 失败: {exc}")

    def delete(self, session_id: str) -> None:
        try:
            self._client.delete(self._key(session_id))
        except Exception as exc:
            print(f"[RedisSessionBackend] delete 失败: {exc}")

    @property
    def count(self) -> int:
        try:
            # 只扫描 triage:session:* 前缀
            cursor, keys = self._client.scan(
                0, match=f"{self.PREFIX}*", count=100
            )
            return len(keys)
        except Exception:
            return 0


# ===========================================================================
# 会话管理器门面
# ===========================================================================

class SessionManager:
    """
    会话管理器 — 封装 TriageEngine 的生命周期

    用法：
        mgr = SessionManager(ttl_seconds=1800)

        # 获取或创建引擎
        engine = mgr.get_engine(session_id)  # 不存在则新建，存在则从后端恢复

        # 处理完请求后持久化
        mgr.save_engine(session_id, engine)

        # 重置
        mgr.reset(session_id)

        # 查活跃数
        print(mgr.count)
    """

    def __init__(self, ttl_seconds: int = 1800) -> None:
        config = get_config()
        self._config = config
        self._ttl = ttl_seconds

        # 后端选择：Redis > 内存（自动降级）
        self._backend: BaseSessionBackend = self._create_backend(config)

    def _create_backend(self, config: Config) -> BaseSessionBackend:
        """选择并初始化存储后端"""
        if config.redis_url:
            try:
                backend = RedisSessionBackend(config.redis_url, self._ttl)
                if backend.ping():
                    print(
                        f"[SessionManager] 使用 Redis 后端: {config.redis_url}"
                    )
                    return backend
                else:
                    print(
                        "[SessionManager] Redis 连接失败，降级到内存后端"
                    )
            except Exception as exc:
                print(
                    f"[SessionManager] Redis 初始化失败 ({exc})，降级到内存后端"
                )

        print("[SessionManager] 使用内存后端 (单进程)")
        return MemorySessionBackend(self._ttl)

    # ---- 引擎操作 ----

    def get_engine(self, session_id: str) -> TriageEngine:
        """获取或创建 TriageEngine（自动从后端恢复状态）"""
        saved = self._backend.load(session_id)
        if saved is not None:
            return TriageEngine(self._config, saved_state=saved)
        return TriageEngine(self._config)

    def save_engine(self, session_id: str, engine: TriageEngine) -> None:
        """持久化引擎状态到后端"""
        state = engine.save_state()
        self._backend.save(session_id, state, self._ttl)

    def reset(self, session_id: str) -> None:
        """重置会话（删除后端记录）"""
        self._backend.delete(session_id)

    # ---- 查询 ----

    @property
    def count(self) -> int:
        return self._backend.count

    @property
    def backend_type(self) -> str:
        return type(self._backend).__name__
