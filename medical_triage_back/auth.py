"""
认证模块 - JWT Token 管理和密码哈希

使用标准库和第三方库：
- bcrypt: 密码哈希
- PyJWT: JWT令牌管理
- functools.wraps: 装饰器保留元数据

功能：
- 用户密码的哈希存储和验证（使用bcrypt）
- JWT Token的生成、解码和验证（支持过期时间）
- 登录验证装饰器（用于保护需要登录的接口）

使用示例：
    from auth import login_required, create_token, hash_password
    
    # 保护接口
    @app.route('/api/protected')
    @login_required
    def protected():
        user_id = g.user_id  # 从g对象获取当前用户ID
        ...
"""
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional

import bcrypt
import jwt
from flask import g, jsonify, request

from config import get_config


# ==================== 密码哈希 ====================

def hash_password(password: str) -> str:
    """
    使用bcrypt对密码进行哈希处理
    
    使用12轮salt生成，安全性较高但计算成本适中
    
    Args:
        password: 明文密码
        
    Returns:
        哈希后的密码字符串（可直接存入数据库）
    """
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """
    验证明文密码是否与哈希密码匹配
    
    Args:
        password: 明文密码（用户输入）
        hashed: 哈希密码（数据库存储）
        
    Returns:
        True表示密码匹配，False表示不匹配
    """
    return bcrypt.checkpw(
        password.encode('utf-8'), 
        hashed.encode('utf-8')
    )


# ==================== JWT Token管理 ====================

def create_token(user_id: int, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建JWT访问令牌
    
    Payload包含：
    - user_id: 用户ID
    - exp: 过期时间
    - iat: 签发时间
    - type: 令牌类型
    
    Args:
        user_id: 用户ID（数据库主键）
        expires_delta: 自定义过期时间，默认使用配置值
        
    Returns:
        JWT令牌字符串
    """
    config = get_config()
    
    if expires_delta is None:
        expires_delta = timedelta(hours=config.jwt_expire_hours)
    
    expire = datetime.utcnow() + expires_delta
    payload = {
        'user_id': user_id,
        'exp': expire,
        'iat': datetime.utcnow(),
        'type': 'access'
    }
    
    return jwt.encode(
        payload, 
        config.jwt_secret, 
        algorithm='HS256'
    )


def decode_token(token: str) -> dict:
    """
    解码并验证JWT令牌
    
    Args:
        token: JWT令牌字符串
        
    Returns:
        解码后的payload字典，如果验证失败返回包含'error'键的字典
    """
    config = get_config()
    
    try:
        return jwt.decode(
            token, 
            config.jwt_secret, 
            algorithms=['HS256']
        )
    except jwt.ExpiredSignatureError:
        return {'error': 'Token已过期'}
    except jwt.InvalidTokenError:
        return {'error': '无效的Token'}


def get_token_from_header() -> Optional[str]:
    """
    从HTTP请求头中提取JWT令牌
    
    预期格式：Authorization: Bearer <token>
    
    Returns:
        令牌字符串，如果未找到则返回None
    """
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:].strip()
    return None


# ==================== 登录验证装饰器 ====================

def login_required(f):
    """
    登录验证装饰器
    
    用于保护需要登录才能访问的接口。
    会自动从请求头中提取Token，验证有效性，并将user_id存入g对象。
    
    使用方式：
        @app.route('/api/protected')
        @login_required
        def protected():
            user_id = g.user_id  # 获取当前登录用户ID
            ...
    
    错误响应：
        401: 缺少Token或Token无效/过期
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 从请求头获取Token
        token = get_token_from_header()
        if not token:
            return jsonify({'error': '缺少认证Token'}), 401
        
        # 解码并验证Token
        payload = decode_token(token)
        if 'error' in payload:
            return jsonify({'error': payload['error']}), 401
        
        # 检查令牌类型
        if payload.get('type') != 'access':
            return jsonify({'error': '无效的Token类型'}), 401
        
        # 将用户信息存储在Flask的g对象中
        g.user_id = payload['user_id']
        g.token_payload = payload
        
        return f(*args, **kwargs)
    
    return decorated_function


def optional_login(f):
    """
    可选登录装饰器
    
    如果提供了有效的Token，则设置g.user_id
    如果没有Token或Token无效，不报错，只是不设置user_id
    
    使用场景：某些接口支持匿名访问，但登录用户有额外功能
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = get_token_from_header()
        g.user_id = None
        g.token_payload = None
        
        if token:
            payload = decode_token(token)
            if 'error' not in payload and payload.get('type') == 'access':
                g.user_id = payload['user_id']
                g.token_payload = payload
        
        return f(*args, **kwargs)
    
    return decorated_function
