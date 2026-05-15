"""
数据库模块 - 数据模型定义和数据库连接管理

功能：
- 定义用户表(User)和历史记录表(TriageHistory)的数据模型
- 管理数据库连接和会话
- 提供数据库初始化功能（自动创建表）
- 兼容旧数据库的字段迁移

配置（通过环境变量）：
- DATABASE_URL: 数据库连接URL，支持SQLite和MySQL
  - SQLite: sqlite:///medical_triage.db（默认，本地开发）
  - MySQL: mysql+pymysql://user:password@host/dbname（生产环境）

使用示例：
    from database import init_database, get_session_factory, User, TriageHistory
    
    # 初始化数据库
    engine = init_database()
    SessionLocal = get_session_factory(engine)
    
    # 使用会话
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(username='test').first()
        ...
    finally:
        session.close()
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey, JSON, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os

# 创建声明式基类，用于定义数据模型
Base = declarative_base()


# ==================== 数据模型定义 ====================

class User(Base):
    """
    用户表 - 存储用户账号信息和会员状态
    
    字段说明：
    - id: 主键，自增
    - username: 用户名，唯一，长度限制50字符
    - password_hash: 密码哈希值（bcrypt生成），长度255字符
    - created_at: 账号创建时间（UTC）
    - last_login: 最后登录时间（UTC）
    - membership_type: 会员类型，'free'（普通）或'member'（会员）
    - member_started_at: 会员开始时间
    - member_expires_at: 会员过期时间
    
    关联：
    - histories: 一对多关联到TriageHistory，用户的历史导诊记录
    
    示例：
        user = User(
            username='test_user',
            password_hash='hashed_password',
            membership_type='free'
        )
    """
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    membership_type = Column(String(20), nullable=False, default='free')
    member_started_at = Column(DateTime, nullable=True)
    member_expires_at = Column(DateTime, nullable=True)
    
    # 关联历史记录，级联删除（用户删除时同时删除历史记录）
    histories = relationship("TriageHistory", back_populates="user", cascade="all, delete-orphan")


class TriageHistory(Base):
    """
    导诊历史记录表 - 存储用户的导诊对话历史
    
    字段说明：
    - id: 主键，自增
    - user_id: 外键，关联到users表
    - symptom_input: 用户输入的症状描述（文本）
    - triage_result: 导诊结果（JSON格式），包含message、stage、records
    - conversation_log: 完整对话历史（JSON数组）
    - created_at: 记录创建时间（UTC）
    
    关联：
    - user: 多对一关联到User，表示记录所属用户
    
    示例：
        history = TriageHistory(
            user_id=1,
            symptom_input='头痛',
            triage_result={'message': '推荐科室: 神经内科', 'stage': 3, ...},
            conversation_log=[{'role': 'user', 'content': '...'}, ...]
        )
    """
    __tablename__ = 'triage_history'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    symptom_input = Column(Text, nullable=False)
    triage_result = Column(JSON, nullable=False)
    conversation_log = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关联用户
    user = relationship("User", back_populates="histories")


# ==================== 数据库连接管理 ====================

def get_database_url() -> str:
    """
    获取数据库连接URL
    
    优先级：
    1. 环境变量 DATABASE_URL
    2. 默认值：sqlite:///medical_triage.db（本地开发）
    
    自动处理：
    - 如果没有指定协议（如只有文件名），自动添加sqlite:///
    
    Returns:
        数据库连接URL字符串
        
    示例：
        # SQLite（本地开发）
        DATABASE_URL=sqlite:///medical_triage.db
        
        # MySQL（生产环境）
        DATABASE_URL=mysql+pymysql://root:password@localhost/medical_triage
    """
    db_url = os.getenv('DATABASE_URL', 'sqlite:///medical_triage.db')
    # 如果没有指定协议，默认使用SQLite（本地开发）
    if '://' not in db_url:
        db_url = f"sqlite:///{db_url}"
    return db_url


def _ensure_user_membership_columns(engine) -> None:
    """
    确保用户表包含会员相关字段（兼容旧数据库迁移）
    
    用于数据库升级场景：
    - 如果数据库是旧版本，缺少membership相关字段
    - 自动执行ALTER TABLE添加缺失的字段
    
    检查字段：
    - membership_type
    - member_started_at
    - member_expires_at
    
    Args:
        engine: SQLAlchemy数据库引擎
        
    注意：
    - 仅支持SQLite和MySQL的ALTER TABLE语法
    - 如果表不存在，直接返回（新数据库不需要迁移）
    """
    inspector = inspect(engine)
    if not inspector.has_table('users'):
        return

    existing_columns = {col['name'] for col in inspector.get_columns('users')}
    missing_columns = []

    if 'membership_type' not in existing_columns:
        missing_columns.append("ALTER TABLE users ADD COLUMN membership_type VARCHAR(20) NOT NULL DEFAULT 'free'")
    if 'member_started_at' not in existing_columns:
        missing_columns.append("ALTER TABLE users ADD COLUMN member_started_at DATETIME")
    if 'member_expires_at' not in existing_columns:
        missing_columns.append("ALTER TABLE users ADD COLUMN member_expires_at DATETIME")

    if not missing_columns:
        return

    # 执行迁移语句
    with engine.begin() as conn:
        for statement in missing_columns:
            conn.execute(text(statement))


def init_database():
    """
    初始化数据库
    
    执行以下操作：
    1. 创建数据库引擎
    2. 创建所有定义的表（如果不存在）
    3. 检查并添加缺失的会员字段（兼容旧数据库）
    
    Returns:
        SQLAlchemy数据库引擎对象
        
    使用示例：
        engine = init_database()
        # 后续使用engine创建会话
        SessionLocal = get_session_factory(engine)
    """
    engine = create_engine(get_database_url())
    # 导入社交模块模型，确保表被创建
    try:
        import social
    except ImportError:
        pass
    # 创建所有表（如果不存在）
    Base.metadata.create_all(engine)
    # 确保会员字段存在（兼容旧数据库）
    _ensure_user_membership_columns(engine)
    return engine


def get_session_factory(engine):
    """
    获取会话工厂
    
    使用sessionmaker创建可复用的会话类，
    每个请求应该创建一个新的会话实例，使用完毕后关闭。
    
    Args:
        engine: SQLAlchemy数据库引擎
        
    Returns:
        sessionmaker类，调用后创建新的会话实例
        
    使用示例：
        SessionLocal = get_session_factory(engine)
        
        # 在请求处理中
        session = SessionLocal()
        try:
            user = session.query(User).filter_by(username='test').first()
            session.commit()
        finally:
            session.close()
    """
    return sessionmaker(bind=engine)
