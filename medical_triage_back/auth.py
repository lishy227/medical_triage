"""
认证模块 - JWT Token 管理和密码哈希

使用标准库和第三方库：
- bcrypt: 密码哈希
- PyJWT: JWT令牌管理

FastAPI 依赖注入替代 Flask 装饰器：
- get_current_user: 从 Bearer Token 解析用户 → 路由参数注入
- get_optional_user: 可选登录 → 匿名用户返回 None

使用示例：
    from auth import get_current_user

    @app.post('/api/protected')
    def protected(user: User = Depends(get_current_user)):
        # user 是已验证的 User 对象
        ...
"""
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import jwt
from fastapi import Header, HTTPException, status

from config import get_config
from database import User, get_db_session


# ==================== 密码哈希 ====================

def hash_password(password: str) -> str:
    """
    使用bcrypt对密码进行哈希处理

    使用12轮salt生成，安全性较高但计算成本适中
    """
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """
    验证明文密码是否与哈希密码匹配
    """
    return bcrypt.checkpw(
        password.encode('utf-8'),
        hashed.encode('utf-8'),
    )


# ==================== JWT Token管理 ====================

def create_token(user_id: int, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建JWT访问令牌

    Payload: user_id, exp, iat, type
    """
    config = get_config()

    if expires_delta is None:
        expires_delta = timedelta(hours=config.jwt_expire_hours)

    expire = datetime.utcnow() + expires_delta
    payload = {
        'user_id': user_id,
        'exp': expire,
        'iat': datetime.utcnow(),
        'type': 'access',
    }
    return jwt.encode(payload, config.jwt_secret, algorithm='HS256')


def decode_token(token: str) -> dict:
    """
    解码并验证JWT令牌

    Returns:
        payload字典，失败时返回含 'error' 键的字典
    """
    config = get_config()
    try:
        return jwt.decode(token, config.jwt_secret, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return {'error': 'Token已过期'}
    except jwt.InvalidTokenError:
        return {'error': '无效的Token'}


def parse_bearer_token(authorization: Optional[str]) -> Optional[str]:
    """从 Authorization: Bearer <token> 头中提取令牌"""
    if authorization and authorization.startswith('Bearer '):
        return authorization[7:].strip()
    return None


# ==================== FastAPI 依赖注入 ====================

def get_current_user(
    authorization: Optional[str] = Header(None),
) -> User:
    """
    FastAPI 依赖：从 Bearer Token 解析并返回当前 User 对象

    用法:
        @app.post('/api/chat')
        def chat(user: User = Depends(get_current_user)):
            ...

    未登录/Token无效 → 自动返回 401
    """
    token = parse_bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='缺少认证Token',
        )

    payload = decode_token(token)
    if 'error' in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=payload['error'],
        )

    if payload.get('type') != 'access':
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='无效的Token类型',
        )

    with get_db_session() as session:
        user = session.query(User).filter_by(id=payload['user_id']).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='用户不存在',
            )
        session.expunge(user)  # 脱离 session，让调用方自由使用
        return user


def get_optional_user(
    authorization: Optional[str] = Header(None),
) -> Optional[User]:
    """
    FastAPI 依赖：可选登录——有 Token 且有效时返回 User，否则返回 None

    用法:
        @app.get('/api/public')
        def public_endpoint(user: Optional[User] = Depends(get_optional_user)):
            if user: ...
    """
    token = parse_bearer_token(authorization)
    if not token:
        return None

    payload = decode_token(token)
    if 'error' in payload or payload.get('type') != 'access':
        return None

    with get_db_session() as session:
        user = session.query(User).filter_by(id=payload['user_id']).first()
        if user:
            session.expunge(user)
            return user
    return None
