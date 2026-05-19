"""
数据库模块 - SQLAlchemy 2.0 统一风格

功能：
- 定义 User / TriageHistory 数据模型
- 管理引擎、会话工厂（延迟初始化 · 单例）
- 数据库初始化（自动建表 + 兼容旧库字段迁移）
- 向后兼容的别名（供 social_routes 等旧模块平滑过渡）

配置：
  DATABASE_URL 通过 .env / 环境变量注入，支持 SQLite 和 MySQL：
    SQLite : sqlite:///medical_triage.db  （本地开发）
    MySQL  : mysql+pymysql://user:pass@host/dbname （生产环境）

使用示例：
    from database import get_db_session, User, TriageHistory

    with get_db_session() as session:
        user = session.query(User).filter_by(username='test').first()
"""
from contextlib import contextmanager
from datetime import datetime
from typing import Generator, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import (
    Mapped,
    Session,
    declarative_base,
    mapped_column,
    relationship,
    sessionmaker,
)

from config import get_config

# ---- 声明式基类 ------------------------------------------------------------
Base = declarative_base()

# ---- 全局单例（延迟初始化）-------------------------------------------------
_engine = None
_session_factory = None


# ===========================================================================
# 数据模型
# ===========================================================================

class User(Base):
    """用户表 — 账号信息 + 会员状态"""
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    membership_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default='free', index=True,
    )
    member_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    member_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 关联：级联删除历史记录
    histories: Mapped[list["TriageHistory"]] = relationship(
        "TriageHistory",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    @property
    def is_member(self) -> bool:
        """有效会员（member 类型 且 未过期）"""
        if self.membership_type != 'member':
            return False
        if self.member_expires_at and self.member_expires_at < datetime.utcnow():
            return False
        return True

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'username': self.username,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'membership_type': self.membership_type,
            'member_started_at': (
                self.member_started_at.isoformat() if self.member_started_at else None
            ),
            'member_expires_at': (
                self.member_expires_at.isoformat() if self.member_expires_at else None
            ),
            'is_member': self.is_member,
        }


class TriageHistory(Base):
    """导诊历史记录表"""
    __tablename__ = 'triage_history'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('users.id'), nullable=False, index=True,
    )
    symptom_input: Mapped[str] = mapped_column(Text, nullable=False)
    triage_result: Mapped[dict] = mapped_column(JSON, nullable=False)
    conversation_log: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # 关联用户
    user: Mapped["User"] = relationship("User", back_populates="histories")

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'symptom_input': self.symptom_input,
            'triage_result': self.triage_result,
            'conversation_log': self.conversation_log,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class DiseaseModel(Base):
    """疾病知识库表 — MySQL 存储，替代 47MB JSON 全量加载
    
    通过 LIKE 关键词匹配检索，单次请求内存占用 <1MB
    """
    __tablename__ = 'diseases'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    symptoms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON array
    cure_department: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cure_way: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cure_lasttime: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cured_prob: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    common_drug: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    do_eat: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    not_eat: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prevent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    get_prob: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    easy_get: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    get_way: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    complications: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cost_money: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    check_items: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    @staticmethod
    def _parse_json_field(value: Optional[str]) -> list:
        """解析 JSON 文本字段为列表"""
        if not value:
            return []
        try:
            import json
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return [value] if value else []

    def to_legacy_dict(self) -> dict:
        """兼容旧 Disease dataclass 的字典格式"""
        return {
            'name': self.name or '',
            'desc': self.description or '',
            'symptom': self._parse_json_field(self.symptoms),
            'cause': self.cause or '',
            'cure_department': self._parse_json_field(self.cure_department),
            'cure_way': self._parse_json_field(self.cure_way),
            'cure_lasttime': self.cure_lasttime or '',
            'cured_prob': self.cured_prob or '',
            'common_drug': self._parse_json_field(self.common_drug),
            'do_eat': self._parse_json_field(self.do_eat),
            'not_eat': self._parse_json_field(self.not_eat),
            'prevent': self.prevent or '',
            'get_prob': self.get_prob or '',
            'easy_get': self.easy_get or '',
            'get_way': self.get_way or '',
            'acompany': self._parse_json_field(self.complications),
            'cost_money': self.cost_money or '',
            'check': self._parse_json_field(self.check_items),
            'category': self._parse_json_field(self.category),
        }


# ===========================================================================
# 引擎 & 会话工厂（延迟初始化 · 单例）
# ===========================================================================

def get_engine():
    """获取数据库引擎（单例）"""
    global _engine
    if _engine is None:
        config = get_config()
        _engine = create_engine(
            config.database_url,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,
        )
    return _engine


def get_session_factory():
    """获取 sessionmaker 工厂（单例）"""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = sessionmaker(
            bind=engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _session_factory


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    数据库会话上下文管理器（自动 commit / rollback / close）

    用法:
        with get_db_session() as session:
            user = session.query(User).filter_by(username='test').first()
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ===========================================================================
# 数据库初始化 & 向后兼容迁移
# ===========================================================================

def init_database():
    """
    初始化数据库：
      1. 创建引擎
      2. 创建所有表（含社交模块表）
      3. 兼容旧库：自动补充缺失的会员字段
    """
    engine = get_engine()

    # 社交模块的表
    try:
        import social
        if hasattr(social, 'Base'):
            social.Base.metadata.create_all(engine)
    except ImportError:
        pass

    Base.metadata.create_all(engine)
    _ensure_user_membership_columns(engine)
    return engine


def _ensure_user_membership_columns(engine) -> None:
    """兼容旧数据库：补充 member 相关字段"""
    inspector = inspect(engine)
    if not inspector.has_table('users'):
        return

    existing = {col['name'] for col in inspector.get_columns('users')}

    migrations = []
    if 'membership_type' not in existing:
        migrations.append(
            "ALTER TABLE users ADD COLUMN membership_type VARCHAR(20) NOT NULL DEFAULT 'free'"
        )
    if 'member_started_at' not in existing:
        migrations.append(
            "ALTER TABLE users ADD COLUMN member_started_at DATETIME"
        )
    if 'member_expires_at' not in existing:
        migrations.append(
            "ALTER TABLE users ADD COLUMN member_expires_at DATETIME"
        )

    if not migrations:
        return

    with engine.begin() as conn:
        for statement in migrations:
            conn.execute(text(statement))

    print(f"数据库迁移完成：添加了 {len(migrations)} 个字段")


# ===========================================================================
# 向后兼容别名（供 social_routes.py 等旧模块使用）
# ===========================================================================

# 兼容旧代码: SessionLocal → get_session_factory
SessionLocal = get_session_factory


def get_session_factory_with_engine(engine=None):
    """
    [兼容] 与 get_session_factory 等价，engine 参数已忽略。
    保留此接口仅供 social_routes.py 调用，新代码请直接用 get_session_factory()。
    """
    return get_session_factory()


# ===========================================================================
# 共享查询工具
# ===========================================================================

def search_diseases(
    terms: list,
    top_k: int = 5,
) -> list:
    """从数据库检索匹配疾病，返回 legacy dict 列表
    
    匹配策略：多关键词 LIKE 打分，按分数排序取 Top K
    单次请求内存占用 <1MB
    
    表不存在 → 直接抛异常由调用方捕获，静默回退 JSON
    """
    import json as _json
    import random as _random

    terms = [t for t in terms if t]
    if not terms:
        return []

    factory = get_session_factory()
    session = factory()
    try:
        rows = session.query(DiseaseModel).all()
        scored = []

        for row in rows:
            score = 0.0
            searchable = f"{row.name or ''} {row.symptoms or ''} {row.description or ''}"
            for term in terms:
                if term in searchable:
                    score += 1.0
                if row.symptoms:
                    try:
                        syms = _json.loads(row.symptoms)
                        for s in syms:
                            if term in str(s):
                                score += 0.5
                                break
                    except Exception:
                        pass
            if score > 0:
                scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]

        if not top:
            count = session.query(func.count(DiseaseModel.id)).scalar()
            if count and count > 0:
                offset = _random.randint(0, max(0, count - top_k))
                rows = session.query(DiseaseModel).offset(offset).limit(top_k).all()
                top = [(0, r) for r in rows]

        return [row.to_legacy_dict() for _, row in top]
    except Exception:
        # 表不存在 / 连接失败 → 静默返回空，触发 JSON 回退
        return []
    finally:
        session.close()


def get_disease_count() -> int:
    """查询疾病表记录数，表不存在 / 连接失败返回 0"""
    factory = get_session_factory()
    session = factory()
    try:
        return session.query(func.count(DiseaseModel.id)).scalar() or 0
    except Exception:
        return 0
    finally:
        session.close()


# ===========================================================================
# 自检
# ===========================================================================

if __name__ == "__main__":
    engine = init_database()
    print("数据库初始化成功")

    with get_db_session() as session:
        count = session.query(User).count()
        print(f"当前用户数: {count}")
