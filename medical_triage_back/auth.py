"""
认证模块 - JWT Token 管理和密码哈希

功能：
- 用户密码的哈希存储和验证（使用bcrypt）
- JWT Token的生成、解码和验证
- 登录验证装饰器（用于保护需要登录的接口）

配置（通过环境变量）：
- JWT_SECRET_KEY: JWT签名密钥（生产环境必须修改）
- JWT_ACCESS_TOKEN_EXPIRE_DAYS: Token有效期（默认30天）

使用示例：
    from auth import login_required, create_token, hash_password
    
    # 保护接口
    @app.route('/api/protected')
    @login_required
    def protected():
        user_id = g.user_id  # 从g对象获取当前用户ID
        ...
"""
import jwt
import bcrypt
import os
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, g

# ==================== JWT配置 ====================

# JWT签名密钥（生产环境必须通过环境变量设置，不要使用默认值）
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key-change-this-in-production')

# Token有效期（天数）
JWT_ACCESS_TOKEN_EXPIRE_DAYS = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRE_DAYS', '30'))


# ==================== 密码哈希 ====================

def hash_password(password: str) -> str:
    """
    使用bcrypt对密码进行哈希处理
    
    使用12轮salt生成，安全性较高但计算成本适中
    
    Args:
        password: 明文密码
        
    Returns:
        哈希后的密码字符串（可直接存入数据库）
        
    示例：
        hashed = hash_password('user_password')
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
        
    示例：
        if verify_password(input_password, stored_hash):
            # 密码正确，允许登录
            ...
    """
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


# ==================== JWT Token管理 ====================

def create_token(user_id: int) -> str:
    """
    创建JWT访问令牌
    
    Payload包含：
    - user_id: 用户ID
    - exp: 过期时间
    - iat: 签发时间
    
    Args:
        user_id: 用户ID（数据库主键）
        
    Returns:
        JWT令牌字符串（用于前端存储和后续请求）
        
    示例：
        token = create_token(user.id)
        return jsonify({'token': token, 'user': user_info})
    """
    expire = datetime.utcnow() + timedelta(days=JWT_ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {
        'user_id': user_id,
        'exp': expire,
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm='HS256')


def decode_token(token: str) -> dict:
    """
    解码并验证JWT令牌
    
    Args:
        token: JWT令牌字符串
        
    Returns:
        解码后的payload字典，如果验证失败返回包含'error'键的字典
        
    可能的错误：
    - 'Token已过期': 令牌超过有效期
    - '无效的Token': 令牌格式错误或签名无效
    """
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return {'error': 'Token已过期'}
    except jwt.InvalidTokenError:
        return {'error': '无效的Token'}


def get_token_from_header() -> str | None:
    """
    从HTTP请求头中提取JWT令牌
    
    预期格式：Authorization: Bearer <token>
    
    Returns:
        令牌字符串，如果未找到则返回None
        
    示例：
        token = get_token_from_header()
        if token:
            payload = decode_token(token)
            ...
    """
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:]
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
        
    Returns:
        装饰后的函数，如果验证失败直接返回401响应
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
        
        # 将用户信息存储在Flask的g对象中（仅当前请求有效）
        g.user_id = payload['user_id']
        return f(*args, **kwargs)
    return decorated_function
