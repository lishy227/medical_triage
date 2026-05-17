"""
Web服务器 - 医疗导诊系统后端主入口

功能：
- 提供HTTP API服务（用户认证、导诊对话、会员管理、历史记录）
- 提供静态文件服务（前端页面）
- 实现会员分层：普通用户仅返回科室推荐，会员返回详细医疗建议
- 服务器重启检测：每次启动生成唯一实例ID

主要接口：
- /api/auth/* : 用户认证（注册、登录、退出）
- /api/chat : 导诊对话（核心功能）
- /api/membership/* : 会员管理
- /api/user/* : 用户中心、历史记录
- /api/server/info : 服务器信息（用于重启检测）
"""
import os
import sys
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from flask import Flask, g, jsonify, request, send_from_directory
from flask_cors import CORS

# 添加当前目录到路径，确保可以导入本地模块
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from auth import create_token, hash_password, login_required, verify_password
from config import Config, load_config
from database import TriageHistory, User, get_session_factory, init_database
from triage import TriageEngine
from social_routes import register_social_routes

# 静态文件路径配置
WEB_ROOT = os.path.normpath(os.path.join(BASE_DIR, '..', 'medical_triage_web'))
WEB_WWW_DIR = os.path.join(WEB_ROOT, 'www')

# 创建Flask应用实例
app = Flask(__name__, static_folder=WEB_WWW_DIR)
CORS(app)  # 启用跨域支持

# 服务器实例ID - 每次重启都会生成新的UUID，用于检测服务器是否重启
SERVER_INSTANCE_ID = str(uuid.uuid4())

# 初始化数据库连接
engine = init_database()
SessionLocal = get_session_factory(engine)

# 打印数据库连接信息（调试用）
print(f"数据库连接: {engine.url}")
if 'sqlite' in str(engine.url):
    print("警告: 当前使用 SQLite 数据库")
else:
    print(f"使用 MySQL 数据库: {engine.url.database}")

# 存储导诊会话引擎（内存中，按session_id索引）
sessions: Dict[str, TriageEngine] = {}


def get_db_session():
    """
    获取数据库会话
    
    Returns:
        SQLAlchemy会话对象，用于数据库操作
    """
    return SessionLocal()


def build_user_payload(user: User) -> Dict[str, Any]:
    """
    构建用户信息返回体
    
    将User对象转换为字典格式，用于API响应
    处理日期字段的序列化（转换为ISO格式字符串）
    
    Args:
        user: User数据库模型对象
        
    Returns:
        包含用户信息的字典
    """
    return {
        'id': user.id,
        'username': user.username,
        'created_at': user.created_at.isoformat() if user.created_at else None,
        'last_login': user.last_login.isoformat() if user.last_login else None,
        'membership_type': user.membership_type or 'free',
        'member_started_at': user.member_started_at.isoformat() if user.member_started_at else None,
        'member_expires_at': user.member_expires_at.isoformat() if user.member_expires_at else None,
    }


def get_current_user() -> Optional[User]:
    """
    获取当前登录用户
    
    从JWT token解析的user_id查询用户信息
    注意：返回的用户对象已expunge，可以在会话外使用
    
    Returns:
        User对象，如果未登录或用户不存在则返回None
    """
    user_id = getattr(g, 'user_id', None)
    if not user_id:
        return None

    session = get_db_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return None
        session.expunge(user)  # 将对象从会话中分离，避免会话关闭后无法访问
        return user
    finally:
        session.close()


def get_engine(session_id: str) -> TriageEngine:
    """
    获取或创建导诊会话引擎
    
    每个session_id对应一个独立的导诊会话，包含完整的对话状态
    如果session_id不存在，则创建新的TriageEngine实例
    
    Args:
        session_id: 会话唯一标识符
        
    Returns:
        TriageEngine导诊引擎实例
    """
    if session_id not in sessions:
        config: Config = load_config()
        sessions[session_id] = TriageEngine(config)
    return sessions[session_id]


def save_triage_history(user_id: int, symptom_input: str, result_text: str, engine: TriageEngine) -> None:
    """
    保存导诊历史记录
    
    将用户的导诊对话记录保存到数据库，包括：
    - 用户输入的症状描述
    - 导诊结果（消息、阶段、记录）
    - 完整的对话历史
    
    Args:
        user_id: 用户ID
        symptom_input: 用户输入的症状
        result_text: 导诊结果文本
        engine: 导诊引擎实例，用于获取状态和历史
    """
    session = get_db_session()
    try:
        record = TriageHistory(
            user_id=user_id,
            symptom_input=symptom_input,
            triage_result={
                'message': result_text,
                'stage': int(getattr(engine.state, 'stage', 0)),
                'records': list(getattr(engine.state, 'records', []) or []),
            },
            conversation_log=getattr(engine, 'get_history_for_display', lambda: [])() or [],
        )
        session.add(record)
        session.commit()
    finally:
        session.close()


# ==================== 静态文件路由 ====================

@app.route('/')
def index():
    """
    主页 - 返回前端入口页面
    
    服务于 medical_triage_web/www/index.html
    """
    return send_from_directory(WEB_WWW_DIR, 'index.html')


@app.route('/<path:path>')
def static_files(path):
    """
    静态文件服务
    
    如果请求的文件存在，返回该文件
    如果不存在（如前端路由），返回index.html（支持SPA单页应用）
    
    Args:
        path: 请求的文件路径
        
    Returns:
        静态文件或index.html
    """
    target_path = os.path.join(WEB_WWW_DIR, path)
    if os.path.isfile(target_path):
        return send_from_directory(WEB_WWW_DIR, path)
    return send_from_directory(WEB_WWW_DIR, 'index.html')


# ==================== 认证相关接口 ====================

@app.route('/api/auth/register', methods=['POST'])
def register():
    """
    用户注册接口
    
    接收用户名和密码，创建新用户账号
    新用户默认membership_type为'free'（普通用户）
    
    请求体：
        {
            "username": "用户名",
            "password": "密码"
        }
    
    返回：
        {
            "message": "注册成功",
            "token": "JWT令牌",
            "user": {用户信息}
        }
    
    错误码：
        400: 参数错误（用户名/密码为空、长度不符合要求）
        409: 用户名已存在
    """
    data: Dict[str, Any] = request.json or {}
    username = str(data.get('username', '')).strip()
    password = str(data.get('password', ''))

    # 参数校验
    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400

    if len(username) < 3 or len(username) > 50:
        return jsonify({'error': '用户名长度需在 3-50 个字符之间'}), 400

    if len(password) < 6:
        return jsonify({'error': '密码长度至少需要 6 个字符'}), 400

    session = get_db_session()
    try:
        # 检查用户名是否已存在
        existing_user = session.query(User).filter_by(username=username).first()
        if existing_user:
            return jsonify({'error': '用户名已存在'}), 409

        # 创建新用户
        user = User(
            username=username,
            password_hash=hash_password(password),
            membership_type='free',  # 默认普通用户
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        # 生成JWT令牌
        token = create_token(user.id)

        return jsonify({
            'message': '注册成功',
            'token': token,
            'user': build_user_payload(user),
        }), 201
    finally:
        session.close()


@app.route('/api/auth/login', methods=['POST'])
def login():
    """用户登录"""
    data: Dict[str, Any] = request.json or {}
    username = str(data.get('username', '')).strip()
    password = str(data.get('password', ''))

    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400

    session = get_db_session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user or not verify_password(password, user.password_hash):
            return jsonify({'error': '用户名或密码错误'}), 401

        user.last_login = datetime.utcnow()
        session.commit()
        session.refresh(user)

        token = create_token(user.id)
        return jsonify({
            'message': '登录成功',
            'token': token,
            'user': build_user_payload(user),
        })
    finally:
        session.close()


@app.route('/api/auth/logout', methods=['POST'])
@login_required
def logout():
    """用户登出"""
    return jsonify({'message': '退出登录成功'})


@app.route('/api/auth/profile', methods=['GET'])
@login_required
def get_profile():
    """获取当前用户资料"""
    user = get_current_user()
    if not user:
        return jsonify({'error': '用户不存在'}), 404

    return jsonify({'user': build_user_payload(user)})


@app.route('/api/profile', methods=['GET'])
@login_required
def get_profile_alias():
    """个人中心资料别名接口"""
    return get_profile()


@app.route('/api/user/center', methods=['GET'])
@login_required
def get_user_center():
    """个人中心"""
    user = get_current_user()
    if not user:
        return jsonify({'error': '用户不存在'}), 404

    session = get_db_session()
    try:
        history_count = session.query(TriageHistory).filter_by(user_id=user.id).count()
    finally:
        session.close()

    return jsonify({
        'user': build_user_payload(user),
        'summary': {
            'history_count': history_count,
        }
    })


@app.route('/api/history', methods=['GET'])
@login_required
def get_history_alias():
    """历史记录别名接口"""
    return get_user_history()


@app.route('/api/user/history', methods=['GET'])
@login_required
def get_user_history():
    """获取用户历史记录"""
    user = get_current_user()
    if not user:
        return jsonify({'error': '用户不存在'}), 404

    limit = request.args.get('limit', default=20, type=int) or 20
    limit = max(1, min(limit, 100))

    session = get_db_session()
    try:
        rows = (
            session.query(TriageHistory)
            .filter_by(user_id=user.id)
            .order_by(TriageHistory.created_at.desc())
            .limit(limit)
            .all()
        )

        history = []
        for row in rows:
            history.append({
                'id': row.id,
                'symptom_input': row.symptom_input,
                'triage_result': row.triage_result,
                'conversation_log': row.conversation_log,
                'created_at': row.created_at.isoformat() if row.created_at else None,
            })

        return jsonify({
            'user': build_user_payload(user),
            'history': history,
            'count': len(history),
        })
    finally:
        session.close()


@app.route('/api/welcome', methods=['GET'])
@login_required
def welcome():
    """获取欢迎消息"""
    session_id = request.args.get('session_id', 'default')
    engine = get_engine(session_id)
    return jsonify({
        'message': engine.get_welcome_message(),
        'session_id': session_id,
    })


# ==================== 会员系统 - 详细建议生成 ====================

import json
import os
import random
import threading
import time
from typing import List, Dict, Any, Optional
from functools import lru_cache

# 全局缓存变量 - 使用线程安全的方式
_diseases_cache = None
_cache_file_path = None
_cache_mtime = None
_cache_lock = threading.Lock()
_cache_loaded = False

def _load_medical_json_async(medical_file: str):
    """
    异步加载 medical.json 文件到缓存
    在后台线程中执行，避免阻塞主线程
    """
    global _diseases_cache, _cache_file_path, _cache_mtime, _cache_loaded
    
    try:
        # 检查文件大小，提前预警
        file_size = os.path.getsize(medical_file)
        if file_size > 50 * 1024 * 1024:  # 大于50MB
            print(f"警告: medical.json 文件较大 ({file_size / 1024 / 1024:.1f}MB)，将在后台加载")
        
        diseases = []
        with open(medical_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    disease = json.loads(line)
                    diseases.append(disease)
                except json.JSONDecodeError:
                    continue
                
                # 每加载1000条让出时间片，避免阻塞
                if len(diseases) % 1000 == 0:
                    time.sleep(0.001)
        
        # 线程安全地更新缓存
        with _cache_lock:
            _diseases_cache = diseases
            _cache_file_path = medical_file
            _cache_mtime = os.path.getmtime(medical_file)
            _cache_loaded = True
        
        print(f"医学知识库加载完成，共 {len(diseases)} 条记录")
        
    except Exception as e:
        print(f"加载 medical.json 失败: {e}")

def _start_medical_json_loader(medical_file: str):
    """启动后台线程加载 medical.json"""
    global _cache_loaded
    
    with _cache_lock:
        if _cache_loaded:
            return  # 已经加载过了
    
    # 启动后台线程加载
    loader_thread = threading.Thread(
        target=_load_medical_json_async,
        args=(medical_file,),
        daemon=True,
        name="MedicalJsonLoader"
    )
    loader_thread.start()
    print(f"正在后台加载医学知识库: {medical_file}")

def _load_medical_json(medical_file: str) -> List[Dict]:
    """
    获取 medical.json 数据（从缓存或等待加载完成）
    如果缓存未加载完成，返回空列表
    """
    global _diseases_cache, _cache_file_path, _cache_mtime
    
    with _cache_lock:
        # 检查缓存是否有效
        if (_diseases_cache is not None and 
            _cache_file_path == medical_file):
            try:
                current_mtime = os.path.getmtime(medical_file)
                if current_mtime == _cache_mtime:
                    return _diseases_cache
            except OSError:
                pass
        
        # 缓存未加载或已过期
        if not _cache_loaded:
            print("警告: 医学知识库尚未加载完成，详细建议功能暂时不可用")
            return []
    
    return []

def generate_detailed_advice(body_part: str, initial_symptom: str, specific_symptom: str, departments: List[str]) -> Dict[str, Any]:
    """
    基于 medical.json 生成详细医疗建议（会员专享功能）
    
    根据用户输入的症状，从知识库中匹配相关疾病，生成包含以下内容的详细建议：
    - 可能的相关疾病列表（含描述、症状、治疗方式、周期、费用）
    - 饮食建议（推荐食用/避免食用）
    - 通用就医建议
    
    匹配算法：
    1. 根据身体部位、初步症状、具体症状进行关键词匹配
    2. 计算匹配度分数（名称/描述匹配得2分，症状匹配得1分）
    3. 按匹配度排序，取前3个最相关的疾病
    4. 如果无匹配，随机返回示例疾病
    
    Args:
        body_part: 身体部位（如"头部"、"胸部"）
        initial_symptom: 初步症状（如"头痛"、"咳嗽"）
        specific_symptom: 具体症状描述
        departments: 推荐科室列表
        
    Returns:
        包含详细建议的字典，结构如下：
        {
            'possible_diseases': [疾病列表],
            'diet_suggestions': {'recommended': [], 'avoid': []},
            'general_tips': [建议列表]
        }
    """
    import json
    import os
    import random
    
    # 加载 medical.json
    medical_file = os.path.join(BASE_DIR, 'knowledge_base', 'medical.json')
    diseases = _load_medical_json(medical_file)
    
    # 如果知识库尚未加载完成，返回提示信息
    if not diseases:
        return {
            'possible_diseases': [],
            'diet_suggestions': {
                'recommended': ['清淡饮食', '多喝水'],
                'avoid': ['辛辣刺激食物', '油腻食物']
            },
            'general_tips': [
                '医学知识库正在加载中，详细建议暂时不可用',
                '建议及时就医，进行专业检查',
                '注意休息，避免过度劳累',
                '如症状加重，请立即前往急诊'
            ],
            'loading': True
        }

    # 根据症状匹配相关疾病
    matched_diseases = []
    search_terms = [body_part, initial_symptom, specific_symptom]
    
    for disease in diseases:
        disease_name = disease.get('name', '')
        disease_symptoms = disease.get('symptom', [])
        disease_desc = disease.get('desc', '')
        
        # 计算匹配度
        match_score = 0
        for term in search_terms:
            if term in disease_name or term in disease_desc:
                match_score += 2
            if isinstance(disease_symptoms, list):
                for sym in disease_symptoms:
                    if term in str(sym):
                        match_score += 1
        
        if match_score > 0:
            matched_diseases.append((match_score, disease))
    
    # 按匹配度排序，取前3个
    matched_diseases.sort(key=lambda x: x[0], reverse=True)
    top_diseases = [d for _, d in matched_diseases[:3]]
    
    if not top_diseases:
        # 如果没有匹配到，随机返回几个常见疾病作为示例
        top_diseases = random.sample(diseases, min(3, len(diseases)))
    
    # 构建详细建议
    detailed_advice = {
        'possible_diseases': [],
        'medical_advice': '',
        'diet_suggestions': {},
        'general_tips': []
    }
    
    for disease in top_diseases:
        disease_info = {
            'name': disease.get('name', ''),
            'description': disease.get('desc', '')[:200] + '...' if len(disease.get('desc', '')) > 200 else disease.get('desc', ''),
            'symptoms': disease.get('symptom', [])[:5],
            'cure_way': disease.get('cure_way', []),
            'cure_lasttime': disease.get('cure_lasttime', ''),
            'cured_prob': disease.get('cured_prob', ''),
            'cost_money': disease.get('cost_money', '')
        }
        detailed_advice['possible_diseases'].append(disease_info)
    
    # 合并所有饮食建议
    all_do_eat = []
    all_not_eat = []
    for disease in top_diseases:
        all_do_eat.extend(disease.get('do_eat', []))
        all_not_eat.extend(disease.get('not_eat', []))
    
    detailed_advice['diet_suggestions'] = {
        'recommended': list(set(all_do_eat))[:5] if all_do_eat else ['清淡饮食', '多喝水'],
        'avoid': list(set(all_not_eat))[:5] if all_not_eat else ['辛辣刺激食物', '油腻食物']
    }
    
    # 通用建议
    detailed_advice['general_tips'] = [
        '建议及时就医，进行专业检查',
        '注意休息，避免过度劳累',
        '保持良好的心态，积极配合治疗',
        '如症状加重，请立即前往急诊'
    ]
    
    return detailed_advice


# ==================== 导诊核心接口 ====================

@app.route('/api/chat', methods=['POST'])
@login_required
def chat():
    """
    处理聊天消息 - 导诊核心接口（支持会员分级）
    
    这是系统的核心接口，处理用户的症状描述，返回导诊回复。
    根据用户会员状态，返回不同详细程度的结果：
    
    普通用户(free)：
        - 导诊对话回复
        - 导诊完成后返回推荐科室
        - detail_locked = true（详细建议锁定）
    
    会员用户(member)：
        - 导诊对话回复
        - 导诊完成后返回推荐科室
        - 返回详细医疗建议（疾病分析、治疗建议、饮食指导等）
        - detail_locked = false
    
    请求体：
        {
            "session_id": "会话ID（可选，默认'default'）",
            "message": "用户输入的消息"
        }
    
    返回：
        {
            "message": "导诊回复消息",
            "is_complete": false/true,  // 是否完成导诊
            "stage": 0/1/2/3,  // 当前阶段
            "records": ["身体部位", "初步症状", "具体症状"],
            // 导诊完成后额外返回：
            "departments": ["科室1", "科室2"],
            "conversation_summary": "问诊摘要",
            "detail_locked": true/false,  // 详细建议是否锁定
            "detail_level": "basic"/"member",
            // 会员用户额外返回：
            "detailed_medical_advice": {详细建议}
        }
    
    特殊命令：
        - 'reset'/'重启'/'重置'：重置当前会话
    """
    data: Dict[str, Any] = request.json or {}
    session_id = data.get('session_id', 'default')
    user_input = str(data.get('message', '')).strip()

    if not user_input:
        return jsonify({'error': '消息不能为空'}), 400

    # 获取当前用户及其会员状态
    user = get_current_user()
    is_member = user and user.membership_type == 'member'

    # 获取或创建导诊引擎
    engine = get_engine(session_id)

    # 处理重置命令
    if user_input.lower() in ['reset', '重启', '重置']:
        engine.reset()
        return jsonify({
            'message': engine.get_welcome_message(),
            'is_complete': False,
            'is_reset': True,
        })

    # 处理用户输入，获取导诊回复
    response, is_complete = engine.process(user_input)

    # 构建响应数据
    result_data = {
        'message': response,
        'is_complete': is_complete,
        'stage': int(engine.state.stage),
        'records': engine.state.records,
    }

    # 导诊完成时，根据会员状态返回不同详细程度的结果
    if is_complete:
        # 获取科室推荐
        if len(engine.state.records) >= 3:
            body_part = engine.state.records[0]
            initial_symptom = engine.state.records[1]
            specific_symptom = engine.state.records[2]
            
            from triage import SymptomRepository
            repo = SymptomRepository(engine.config.data_file, engine.config.encoding)
            departments = repo.find_departments(body_part, initial_symptom, specific_symptom)
            
            result_data['departments'] = departments
            result_data['conversation_summary'] = f"{body_part} - {initial_symptom} - {specific_symptom}"
            
            if is_member:
                # 会员用户：返回详细建议
                detailed = generate_detailed_advice(body_part, initial_symptom, specific_symptom, departments)
                result_data['detailed_medical_advice'] = detailed
                result_data['detail_level'] = 'member'
                result_data['detail_locked'] = False
            else:
                # 普通用户：只返回科室推荐，详细建议锁定
                result_data['detail_level'] = 'basic'
                result_data['detail_locked'] = True
        
        # 保存历史记录
        if getattr(g, 'user_id', None):
            save_triage_history(g.user_id, user_input, response, engine)

    return jsonify(result_data)


@app.route('/api/reset', methods=['POST'])
@login_required
def reset():
    """重置会话"""
    data: Dict[str, Any] = request.json or {}
    session_id = data.get('session_id', 'default')

    if session_id in sessions:
        sessions[session_id].reset()

    engine = get_engine(session_id)
    return jsonify({
        'message': engine.get_welcome_message(),
        'session_id': session_id,
    })


@app.route('/api/membership/upgrade', methods=['POST'])
@login_required
def upgrade_membership():
    """模拟升级会员（实际项目中应接入支付系统）"""
    user_id = getattr(g, 'user_id', None)
    if not user_id:
        return jsonify({'error': '未登录'}), 401
    
    session = get_db_session()
    try:
        # 在同一个会话中查询和更新用户
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return jsonify({'error': '用户不存在'}), 404
        
        if user.membership_type == 'member':
            return jsonify({'error': '您已经是会员了'}), 400
        
        # 更新会员信息
        user.membership_type = 'member'
        user.member_started_at = datetime.utcnow()
        # 会员有效期30天
        user.member_expires_at = datetime.utcnow() + timedelta(days=30)
        session.commit()
        
        # 重新查询获取最新数据
        user = session.query(User).filter_by(id=user_id).first()
        
        return jsonify({
            'message': '会员升级成功！',
            'user': build_user_payload(user),
        })
    finally:
        session.close()


@app.route('/api/membership/status', methods=['GET'])
@login_required
def get_membership_status():
    """获取会员状态"""
    user = get_current_user()
    if not user:
        return jsonify({'error': '用户不存在'}), 404
    
    return jsonify({
        'membership_type': user.membership_type or 'free',
        'member_started_at': user.member_started_at.isoformat() if user.member_started_at else None,
        'member_expires_at': user.member_expires_at.isoformat() if user.member_expires_at else None,
        'is_member': user.membership_type == 'member',
    })


@app.route('/api/server/info', methods=['GET'])
def get_server_info():
    """获取服务器信息（用于检测服务器是否重启）"""
    return jsonify({
        'instance_id': SERVER_INSTANCE_ID,
        'started_at': datetime.utcnow().isoformat(),
    })


# 注册社交互动路由（评论、点赞）
register_social_routes(app)


if __name__ == '__main__':
    print('=' * 50)
    print('医疗导诊系统 Web 服务')
    print('=' * 50)
    print('访问地址: http://localhost:5001')
    print('=' * 50)
    
    # 启动后台线程加载医学知识库，避免阻塞主线程
    medical_file = os.path.join(BASE_DIR, 'knowledge_base', 'medical.json')
    if os.path.exists(medical_file):
        _start_medical_json_loader(medical_file)
    else:
        print(f"警告: 医学知识库文件不存在: {medical_file}")
    
    # 使用 threaded=True 启用多线程模式，避免单线程阻塞
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)
