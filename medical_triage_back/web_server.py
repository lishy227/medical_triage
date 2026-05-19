"""
Web服务器 - 医疗导诊系统后端主入口 (FastAPI)

功能：
- 提供 REST API 服务（用户认证、导诊对话、会员管理、历史记录）
- 提供静态文件服务（前端页面）
- 实现会员分层：普通用户仅返回科室推荐，会员返回详细医疗建议
- 服务器重启检测：每次启动生成唯一实例ID
- 自动生成 OpenAPI 文档: http://localhost:5001/docs

主要接口：
- /api/auth/* : 用户认证（注册、登录、退出）
- /api/chat : 导诊对话（核心功能）
- /api/membership/* : 会员管理
- /api/user/* : 用户中心、历史记录
- /api/server/info : 服务器信息（用于重启检测）
"""
import json
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func

BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR))

from auth import (
    create_token,
    get_current_user,
    hash_password,
    verify_password,
)
from config import get_config
from database import DiseaseModel, TriageHistory, User, get_db_session, init_database, search_diseases
from session_manager import SessionManager
from triage import TriageEngine

# 社交路由
try:
    from social_routes import social_router
    SOCIAL_ROUTES_AVAILABLE = True
except ImportError:
    SOCIAL_ROUTES_AVAILABLE = False

# ---- Pydantic 请求模型 -----------------------------------------------------

class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)


class UserLoginRequest(BaseModel):
    username: str
    password: str


class ChatRequest(BaseModel):
    session_id: str = Field(default='default')
    message: str = Field(..., min_length=1)


class ResetRequest(BaseModel):
    session_id: str = Field(default='default')


# ---- FastAPI 应用 ----------------------------------------------------------

WEB_ROOT = BASE_DIR.parent / 'medical_triage_web'
WEB_WWW_DIR = WEB_ROOT / 'www'

app = FastAPI(
    title='AI 医疗导诊系统',
    description='基于 LLM 多智能体协作的智能医疗导诊系统',
    version='1.0.0',
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# 服务器实例 ID
SERVER_INSTANCE_ID = str(uuid.uuid4())

# 初始化数据库
_db_engine = init_database()

# 会话管理
sessions = SessionManager(ttl_seconds=1800)

# ---- 辅助函数 ---------------------------------------------------------------

def get_engine(session_id: str) -> TriageEngine:
    """获取或创建导诊会话引擎"""
    return sessions.get_engine(session_id)


def save_triage_history(
    user_id: int,
    symptom_input: str,
    result_text: str,
    engine: TriageEngine,
) -> None:
    """保存导诊历史记录"""
    with get_db_session() as db:
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
        db.add(record)
        db.commit()


# ---- 疾病检索（DB 优先，JSON 自动回退）-------------------------------

# JSON 文件缓存（仅在 DB 不可用时使用）
_json_disease_cache: Optional[List[Dict[str, Any]]] = None


def _load_diseases_from_json() -> List[Dict[str, Any]]:
    """加载 medical.json 到内存（仅 DB 回退时调用，惰性加载 + 缓存）"""
    global _json_disease_cache
    if _json_disease_cache is not None:
        return _json_disease_cache

    medical_file = BASE_DIR / 'knowledge_base' / 'medical.json'
    if not medical_file.exists():
        print(f'[JSON回退] 文件不存在: {medical_file}')
        return []

    diseases = []
    try:
        with medical_file.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    diseases.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        _json_disease_cache = diseases
        print(f'[JSON回退] 加载完成，共 {len(diseases)} 条记录（注意：高内存占用）')
    except Exception as e:
        print(f'[JSON回退] 加载失败: {e}')
    return diseases


def _build_advice_details(diseases: list) -> Dict[str, Any]:
    """从疾病列表构建详细建议（DB 和 JSON 共用此函数）"""
    if not diseases:
        return {
            'possible_diseases': [],
            'diet_suggestions': {
                'recommended': ['清淡饮食', '多喝水'],
                'avoid': ['辛辣刺激食物', '油腻食物'],
            },
            'general_tips': [
                '暂未匹配到相关疾病，建议前往医院做进一步检查',
                '注意休息，避免过度劳累',
                '如症状加重，请立即前往急诊',
            ],
            'loading': True,
        }

    detailed = {'possible_diseases': [], 'diet_suggestions': {}, 'general_tips': []}
    for d in diseases:
        desc = d.get('desc', '')
        detailed['possible_diseases'].append({
            'name': d.get('name', ''),
            'description': desc[:200] + '...' if len(desc) > 200 else desc,
            'symptoms': d.get('symptom', [])[:5],
            'cure_way': d.get('cure_way', []),
            'cure_lasttime': d.get('cure_lasttime', ''),
            'cured_prob': d.get('cured_prob', ''),
            'cost_money': d.get('cost_money', ''),
        })

    all_do_eat, all_not_eat = [], []
    for d in diseases:
        all_do_eat.extend(d.get('do_eat', []))
        all_not_eat.extend(d.get('not_eat', []))

    detailed['diet_suggestions'] = {
        'recommended': list(dict.fromkeys(all_do_eat))[:5] or ['清淡饮食', '多喝水'],
        'avoid': list(dict.fromkeys(all_not_eat))[:5] or ['辛辣刺激食物', '油腻食物'],
    }
    detailed['general_tips'] = [
        '建议及时就医，进行专业检查',
        '注意休息，避免过度劳累',
        '保持良好的心态，积极配合治疗',
        '如症状加重，请立即前往急诊',
    ]
    return detailed


def generate_detailed_advice(
    body_part: str,
    initial_symptom: str,
    specific_symptom: str,
    departments: List[str],
) -> Dict[str, Any]:
    """生成详细医疗建议 — 优先 MySQL，表不存在自动回退 JSON"""
    terms = [body_part, initial_symptom, specific_symptom]

    # 1. 尝试数据库检索
    try:
        diseases = search_diseases(terms, top_k=3)
        if diseases:
            return _build_advice_details(diseases)
    except Exception:
        pass

    # 2. 回退到 JSON 文件全量扫描
    all_diseases = _load_diseases_from_json()
    if not all_diseases:
        return _build_advice_details([])

    import random as _random
    matched = []
    for disease in all_diseases:
        name = disease.get('name', '')
        symptoms = disease.get('symptom', [])
        desc = disease.get('desc', '')
        match_score = 0
        for term in terms:
            if term in name or term in desc:
                match_score += 2
            if isinstance(symptoms, list):
                for sym in symptoms:
                    if term in str(sym):
                        match_score += 1
        if match_score > 0:
            matched.append((match_score, disease))

    matched.sort(key=lambda x: x[0], reverse=True)
    top = [d for _, d in matched[:3]]
    if not top and all_diseases:
        top = _random.sample(all_diseases, min(3, len(all_diseases)))

    return _build_advice_details(top)


# ===========================================================================
# 认证接口
# ===========================================================================

@app.post('/api/auth/register', status_code=201, tags=['认证'])
def register(data: UserRegisterRequest):
    """用户注册"""
    with get_db_session() as db:
        existing = db.query(User).filter_by(username=data.username).first()
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, '用户名已存在')

        user = User(
            username=data.username,
            password_hash=hash_password(data.password),
            membership_type='free',
        )
        db.add(user)
        db.flush()
        db.refresh(user)

        token = create_token(user.id)
        return {'message': '注册成功', 'token': token, 'user': user.to_dict()}


@app.post('/api/auth/login', tags=['认证'])
def login(data: UserLoginRequest):
    """用户登录"""
    with get_db_session() as db:
        user = db.query(User).filter_by(username=data.username).first()
        if not user or not verify_password(data.password, user.password_hash):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, '用户名或密码错误')

        user.last_login = datetime.utcnow()
        db.flush()
        db.refresh(user)

        token = create_token(user.id)
        return {'message': '登录成功', 'token': token, 'user': user.to_dict()}


@app.post('/api/auth/logout', tags=['认证'])
def logout(user: User = Depends(get_current_user)):
    """用户登出"""
    return {'message': '退出登录成功'}


@app.get('/api/auth/profile', tags=['认证'])
def get_profile(user: User = Depends(get_current_user)):
    """获取当前用户资料"""
    return {'user': user.to_dict()}


# ===========================================================================
# 用户中心接口
# ===========================================================================

@app.get('/api/user/center', tags=['用户中心'])
def get_user_center(user: User = Depends(get_current_user)):
    """个人中心"""
    with get_db_session() as db:
        history_count = db.query(TriageHistory).filter_by(user_id=user.id).count()
    return {'user': user.to_dict(), 'summary': {'history_count': history_count}}


@app.get('/api/user/history', tags=['用户中心'])
def get_user_history(
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    """获取用户历史记录"""
    with get_db_session() as db:
        rows = (
            db.query(TriageHistory)
            .filter_by(user_id=user.id)
            .order_by(TriageHistory.created_at.desc())
            .limit(limit)
            .all()
        )
        return {
            'user': user.to_dict(),
            'history': [r.to_dict() for r in rows],
            'count': len(rows),
        }


# ===========================================================================
# 导诊核心接口
# ===========================================================================

@app.get('/api/welcome', tags=['导诊'])
def welcome(
    session_id: str = Query('default'),
    user: User = Depends(get_current_user),
):
    """获取欢迎消息"""
    engine = get_engine(session_id)
    result = {'message': engine.get_welcome_message(), 'session_id': session_id}
    sessions.save_engine(session_id, engine)
    return result


@app.post('/api/chat', tags=['导诊'])
def chat(
    data: ChatRequest,
    user: User = Depends(get_current_user),
):
    """处理聊天消息 - 导诊核心接口"""
    engine = get_engine(data.session_id)

    # 处理重置命令
    if data.message.lower() in ('reset', '重启', '重置'):
        engine.reset()
        return {
            'message': engine.get_welcome_message(),
            'is_complete': False,
            'is_reset': True,
        }

    response_text, is_complete = engine.process(data.message)
    sessions.save_engine(data.session_id, engine)

    result: Dict[str, Any] = {
        'message': response_text,
        'is_complete': is_complete,
        'stage': int(engine.state.stage),
        'records': engine.state.records,
    }

    if is_complete and len(engine.state.records) >= 3:
        body_part = engine.state.records[0]
        initial_symptom = engine.state.records[1]
        specific_symptom = engine.state.records[2]

        departments = engine.repository.find_departments(
            body_part, initial_symptom, specific_symptom,
        )
        result['departments'] = departments
        result['conversation_summary'] = (
            f'{body_part} - {initial_symptom} - {specific_symptom}'
        )

        if user.is_member:
            result['detailed_medical_advice'] = generate_detailed_advice(
                body_part, initial_symptom, specific_symptom, departments,
            )
            result['detail_level'] = 'member'
            result['detail_locked'] = False
        else:
            result['detail_level'] = 'basic'
            result['detail_locked'] = True

        save_triage_history(user.id, data.message, response_text, engine)

    return result


@app.post('/api/reset', tags=['导诊'])
def reset(
    data: ResetRequest,
    user: User = Depends(get_current_user),
):
    """重置会话"""
    if data.session_id:
        sessions.reset(data.session_id)

    engine = get_engine(data.session_id)
    result = {'message': engine.get_welcome_message(), 'session_id': data.session_id}
    sessions.save_engine(data.session_id, engine)
    return result


# ===========================================================================
# 会员管理接口
# ===========================================================================

@app.post('/api/membership/upgrade', tags=['会员'])
def upgrade_membership(user: User = Depends(get_current_user)):
    """模拟升级会员"""
    with get_db_session() as db:
        u = db.query(User).filter_by(id=user.id).first()
        if not u:
            raise HTTPException(404, '用户不存在')
        if u.membership_type == 'member':
            raise HTTPException(400, '您已经是会员了')

        u.membership_type = 'member'
        u.member_started_at = datetime.utcnow()
        u.member_expires_at = datetime.utcnow() + timedelta(days=30)
        db.flush()
        db.refresh(u)
        return {'message': '会员升级成功！', 'user': u.to_dict()}


@app.get('/api/membership/status', tags=['会员'])
def get_membership_status(user: User = Depends(get_current_user)):
    """获取会员状态"""
    return {
        'membership_type': user.membership_type or 'free',
        'member_started_at': (
            user.member_started_at.isoformat() if user.member_started_at else None
        ),
        'member_expires_at': (
            user.member_expires_at.isoformat() if user.member_expires_at else None
        ),
        'is_member': user.is_member,
    }


# ===========================================================================
# 服务器信息
# ===========================================================================

@app.get('/api/server/info', tags=['系统'])
def get_server_info():
    """获取服务器信息（用于重启检测）"""
    return {
        'instance_id': SERVER_INSTANCE_ID,
        'started_at': datetime.utcnow().isoformat(),
    }


# ===========================================================================
# 社交路由注册
# ===========================================================================

if SOCIAL_ROUTES_AVAILABLE:
    app.include_router(social_router)


# ===========================================================================
# 静态文件服务（放在最后，避免拦截 API 路由）
# ===========================================================================

@app.get('/', include_in_schema=False)
def index():
    """主页"""
    return HTMLResponse((WEB_WWW_DIR / 'index.html').read_text(encoding='utf-8'))


if WEB_WWW_DIR.exists():
    app.mount('/', StaticFiles(directory=str(WEB_WWW_DIR), html=True), name='static')


# ===========================================================================
# 启动入口
# ===========================================================================

if __name__ == '__main__':
    import uvicorn

    print('=' * 50)
    print('医疗导诊系统 Web 服务 (FastAPI)')
    print('=' * 50)
    print('访问地址: http://localhost:5001')
    print('API 文档: http://localhost:5001/docs')
    print('=' * 50)

    uvicorn.run(app, host='0.0.0.0', port=5001)
