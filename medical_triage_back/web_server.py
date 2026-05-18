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
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

from flask import Flask, g, jsonify, request, send_from_directory
from flask_cors import CORS
from pydantic import BaseModel, Field, field_validator

# 添加当前目录到路径
BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR))

from auth import create_token, hash_password, login_required, verify_password
from config import get_config
from database import TriageHistory, User, get_db_session, init_database
from triage import TriageEngine

# 尝试导入社交路由
try:
    from social_routes import register_social_routes
    SOCIAL_ROUTES_AVAILABLE = True
except ImportError:
    SOCIAL_ROUTES_AVAILABLE = False

# ==================== Pydantic 模型定义 ====================

class UserRegisterRequest(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)

class UserLoginRequest(BaseModel):
    """用户登录请求"""
    username: str
    password: str

class ChatRequest(BaseModel):
    """聊天请求"""
    session_id: str = Field(default='default')
    message: str = Field(..., min_length=1)

class ResetRequest(BaseModel):
    """重置请求"""
    session_id: str = Field(default='default')

class HistoryQueryParams(BaseModel):
    """历史记录查询参数"""
    limit: int = Field(default=20, ge=1, le=100)

# ==================== Flask 应用配置 ====================

WEB_ROOT = BASE_DIR.parent / 'medical_triage_web'
WEB_WWW_DIR = WEB_ROOT / 'www'

app = Flask(__name__, static_folder=str(WEB_WWW_DIR))
CORS(app)

# 服务器实例ID
SERVER_INSTANCE_ID = str(uuid.uuid4())

# 初始化数据库
engine = init_database()

# ==================== 会话管理 ================================================

from session_manager import SessionManager

sessions = SessionManager(ttl_seconds=1800)  # 空闲 30 分钟过期


# ==================== 上下文管理器 ====================

def db_session_scope():
    """数据库会话上下文管理器"""
    return get_db_session()


# ==================== 辅助函数 ====================

def get_current_user() -> Optional[User]:
    """获取当前登录用户"""
    user_id = getattr(g, 'user_id', None)
    if not user_id:
        return None
    
    with db_session_scope() as session:
        user = session.query(User).filter_by(id=user_id).first()
        if user:
            session.expunge(user)
            return user
    return None


def get_engine(session_id: str) -> TriageEngine:
    """获取或创建导诊会话引擎（从后端恢复状态）"""
    return sessions.get_engine(session_id)


def save_triage_history(
    user_id: int, 
    symptom_input: str, 
    result_text: str, 
    engine: TriageEngine
) -> None:
    """保存导诊历史记录"""
    with db_session_scope() as session:
        record = TriageHistory(
            user_id=user_id,
            symptom_input=symptom_input,
            triage_result={
                'message': result_text,
                'stage': int(getattr(engine.state, 'stage', 0)),
                'records': list(getattr(engine.state, 'records', []) or []),
            },
            conversation_log=engine.get_history_for_display() or [],
        )
        session.add(record)


# ==================== 静态文件路由 ====================

@app.route('/')
def index():
    """主页"""
    return send_from_directory(WEB_WWW_DIR, 'index.html')


@app.route('/<path:path>')
def static_files(path):
    """静态文件服务"""
    target_path = WEB_WWW_DIR / path
    if target_path.is_file():
        return send_from_directory(WEB_WWW_DIR, path)
    return send_from_directory(WEB_WWW_DIR, 'index.html')


# ==================== 认证相关接口 ====================

@app.route('/api/auth/register', methods=['POST'])
def register():
    """用户注册"""
    try:
        data = UserRegisterRequest.model_validate(request.json or {})
    except Exception as e:
        return jsonify({'error': f'参数错误: {str(e)}'}), 400
    
    with db_session_scope() as session:
        # 检查用户名是否已存在
        existing_user = session.query(User).filter_by(username=data.username).first()
        if existing_user:
            return jsonify({'error': '用户名已存在'}), 409
        
        # 创建新用户
        user = User(
            username=data.username,
            password_hash=hash_password(data.password),
            membership_type='free',
        )
        session.add(user)
        session.flush()  # 获取ID
        session.refresh(user)
        
        token = create_token(user.id)
        
        return jsonify({
            'message': '注册成功',
            'token': token,
            'user': user.to_dict(),
        }), 201


@app.route('/api/auth/login', methods=['POST'])
def login():
    """用户登录"""
    try:
        data = UserLoginRequest.model_validate(request.json or {})
    except Exception as e:
        return jsonify({'error': f'参数错误: {str(e)}'}), 400
    
    with db_session_scope() as session:
        user = session.query(User).filter_by(username=data.username).first()
        if not user or not verify_password(data.password, user.password_hash):
            return jsonify({'error': '用户名或密码错误'}), 401
        
        user.last_login = datetime.utcnow()
        session.flush()
        session.refresh(user)
        
        token = create_token(user.id)
        return jsonify({
            'message': '登录成功',
            'token': token,
            'user': user.to_dict(),
        })


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
    
    return jsonify({'user': user.to_dict()})


@app.route('/api/user/center', methods=['GET'])
@login_required
def get_user_center():
    """个人中心"""
    user = get_current_user()
    if not user:
        return jsonify({'error': '用户不存在'}), 404
    
    with db_session_scope() as session:
        history_count = session.query(TriageHistory).filter_by(user_id=user.id).count()
    
    return jsonify({
        'user': user.to_dict(),
        'summary': {'history_count': history_count},
    })


@app.route('/api/user/history', methods=['GET'])
@login_required
def get_user_history():
    """获取用户历史记录"""
    user = get_current_user()
    if not user:
        return jsonify({'error': '用户不存在'}), 404
    
    try:
        params = HistoryQueryParams(limit=request.args.get('limit', 20))
    except Exception:
        params = HistoryQueryParams()
    
    with db_session_scope() as session:
        rows = (
            session.query(TriageHistory)
            .filter_by(user_id=user.id)
            .order_by(TriageHistory.created_at.desc())
            .limit(params.limit)
            .all()
        )
        
        history = [row.to_dict() for row in rows]
        
        return jsonify({
            'user': user.to_dict(),
            'history': history,
            'count': len(history),
        })


@app.route('/api/welcome', methods=['GET'])
@login_required
def welcome():
    """获取欢迎消息"""
    session_id = request.args.get('session_id', 'default')
    engine = get_engine(session_id)
    result = jsonify({
        'message': engine.get_welcome_message(),
        'session_id': session_id,
    })
    sessions.save_engine(session_id, engine)
    return result


# ==================== 医学知识库缓存 ====================

from functools import lru_cache
from threading import Lock

_medical_cache_lock = Lock()
_medical_cache: Optional[List[Dict[str, Any]]] = None


def load_medical_json() -> List[Dict[str, Any]]:
    """加载 medical.json 文件"""
    global _medical_cache
    
    with _medical_cache_lock:
        if _medical_cache is not None:
            return _medical_cache
    
    medical_file = BASE_DIR / 'knowledge_base' / 'medical.json'
    
    if not medical_file.exists():
        print(f"警告: 医学知识库文件不存在: {medical_file}")
        return []
    
    diseases = []
    try:
        # 尝试作为 JSONL 格式加载（每行一个 JSON 对象）
        with medical_file.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    disease = json.loads(line)
                    diseases.append(disease)
                except json.JSONDecodeError:
                    continue
        
        with _medical_cache_lock:
            _medical_cache = diseases
        
        print(f"医学知识库加载完成，共 {len(diseases)} 条记录")
        
    except Exception as e:
        print(f"加载 medical.json 失败: {e}")
    
    return diseases


def generate_detailed_advice(
    body_part: str, 
    initial_symptom: str, 
    specific_symptom: str, 
    departments: List[str]
) -> Dict[str, Any]:
    """基于 medical.json 生成详细医疗建议"""
    
    diseases = load_medical_json()
    
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
    search_terms = [body_part, initial_symptom, specific_symptom]
    matched_diseases = []
    
    for disease in diseases:
        disease_name = disease.get('name', '')
        disease_symptoms = disease.get('symptom', [])
        disease_desc = disease.get('desc', '')
        
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
        import random
        top_diseases = random.sample(diseases, min(3, len(diseases)))
    
    # 构建详细建议
    detailed_advice = {
        'possible_diseases': [],
        'diet_suggestions': {},
        'general_tips': []
    }
    
    for disease in top_diseases:
        desc = disease.get('desc', '')
        disease_info = {
            'name': disease.get('name', ''),
            'description': desc[:200] + '...' if len(desc) > 200 else desc,
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
        'recommended': list(dict.fromkeys(all_do_eat))[:5] if all_do_eat else ['清淡饮食', '多喝水'],
        'avoid': list(dict.fromkeys(all_not_eat))[:5] if all_not_eat else ['辛辣刺激食物', '油腻食物']
    }
    
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
    """处理聊天消息 - 导诊核心接口"""
    try:
        data = ChatRequest.model_validate(request.json or {})
    except Exception as e:
        return jsonify({'error': f'参数错误: {str(e)}'}), 400
    
    user = get_current_user()
    is_member = user and user.is_member
    
    engine = get_engine(data.session_id)
    
    # 处理重置命令
    if data.message.lower() in ['reset', '重启', '重置']:
        engine.reset()
        return jsonify({
            'message': engine.get_welcome_message(),
            'is_complete': False,
            'is_reset': True,
        })
    
    # 处理用户输入
    response, is_complete = engine.process(data.message)

    # 每次请求后持久化会话状态
    sessions.save_engine(data.session_id, engine)
    
    result_data = {
        'message': response,
        'is_complete': is_complete,
        'stage': int(engine.state.stage),
        'records': engine.state.records,
    }
    
    if is_complete and len(engine.state.records) >= 3:
        body_part = engine.state.records[0]
        initial_symptom = engine.state.records[1]
        specific_symptom = engine.state.records[2]
        
        # 直接复用 TriageEngine 内置的 repository，避免重复加载 table.json
        departments = engine.repository.find_departments(body_part, initial_symptom, specific_symptom)
        
        result_data['departments'] = departments
        result_data['conversation_summary'] = f"{body_part} - {initial_symptom} - {specific_symptom}"
        
        if is_member:
            detailed = generate_detailed_advice(body_part, initial_symptom, specific_symptom, departments)
            result_data['detailed_medical_advice'] = detailed
            result_data['detail_level'] = 'member'
            result_data['detail_locked'] = False
        else:
            result_data['detail_level'] = 'basic'
            result_data['detail_locked'] = True
        
        # 保存历史记录
        if getattr(g, 'user_id', None):
            save_triage_history(g.user_id, data.message, response, engine)
    
    return jsonify(result_data)


@app.route('/api/reset', methods=['POST'])
@login_required
def reset():
    """重置会话"""
    try:
        data = ResetRequest.model_validate(request.json or {})
    except Exception as e:
        return jsonify({'error': f'参数错误: {str(e)}'}), 400
    
    if data.session_id:
        sessions.reset(data.session_id)
    
    engine = get_engine(data.session_id)
    result = jsonify({
        'message': engine.get_welcome_message(),
        'session_id': data.session_id,
    })
    sessions.save_engine(data.session_id, engine)
    return result


@app.route('/api/membership/upgrade', methods=['POST'])
@login_required
def upgrade_membership():
    """模拟升级会员"""
    user_id = getattr(g, 'user_id', None)
    if not user_id:
        return jsonify({'error': '未登录'}), 401
    
    with db_session_scope() as session:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return jsonify({'error': '用户不存在'}), 404
        
        if user.membership_type == 'member':
            return jsonify({'error': '您已经是会员了'}), 400
        
        user.membership_type = 'member'
        user.member_started_at = datetime.utcnow()
        user.member_expires_at = datetime.utcnow() + timedelta(days=30)
        session.flush()
        session.refresh(user)
        
        return jsonify({
            'message': '会员升级成功！',
            'user': user.to_dict(),
        })


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
        'is_member': user.is_member,
    })


@app.route('/api/server/info', methods=['GET'])
def get_server_info():
    """获取服务器信息"""
    return jsonify({
        'instance_id': SERVER_INSTANCE_ID,
        'started_at': datetime.utcnow().isoformat(),
    })


# 注册社交互动路由
if SOCIAL_ROUTES_AVAILABLE:
    register_social_routes(app)


if __name__ == '__main__':
    print('=' * 50)
    print('医疗导诊系统 Web 服务')
    print('=' * 50)
    print('访问地址: http://localhost:5001')
    print('=' * 50)
    
    # 后台加载医学知识库
    import threading
    loader_thread = threading.Thread(target=load_medical_json, daemon=True)
    loader_thread.start()
    
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)
