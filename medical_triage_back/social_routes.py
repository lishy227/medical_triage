"""
社交互动 API 路由 - 评论和点赞接口

功能：
- 评论的增删查（支持分页、排序）
- 点赞/取消点赞
- 评论回复（楼中楼）

接口列表：
- GET    /api/comments          获取评论列表
- POST   /api/comments          发表评论
- DELETE /api/comments/<id>     删除评论
- GET    /api/comments/<id>/replies  获取评论回复
- POST   /api/likes             点赞
- DELETE /api/likes             取消点赞
- GET    /api/likes/status      查询点赞状态

使用示例：
    from flask import Flask
    from social_routes import register_social_routes
    
    app = Flask(__name__)
    register_social_routes(app)
"""
from typing import Any, Dict, List, Optional
from datetime import datetime

from flask import Blueprint, g, jsonify, request

from auth import login_required
from database import get_session_factory_with_engine, init_database
from social import Comment, Like, validate_comment_content

# 创建蓝图
social_bp = Blueprint('social', __name__, url_prefix='/api')

# 初始化数据库连接
engine = init_database()
SessionLocal = get_session_factory_with_engine(engine)


def get_db_session():
    """获取数据库会话"""
    return SessionLocal()


def get_current_user_id() -> Optional[int]:
    """获取当前登录用户ID"""
    return getattr(g, 'user_id', None)


# ==================== 评论接口 ====================

@social_bp.route('/comments', methods=['GET'])
@login_required
def get_comments():
    """
    获取评论列表
    
    查询参数：
    - target_type: 目标类型（必需，如 'triage'）
    - target_id: 目标ID（必需）
    - page: 页码，默认1
    - limit: 每页数量，默认20，最大100
    - sort: 排序方式，'hot'(热度)/'new'(最新)/'top'(点赞最多)，默认'hot'
    - include_replies: 是否包含回复，默认true
    
    响应：
    {
        "items": [...],
        "total": 156,
        "page": 1,
        "limit": 20,
        "has_more": true
    }
    """
    # 获取查询参数
    target_type = request.args.get('target_type', '').strip()
    target_id = request.args.get('target_id', '').strip()
    page = request.args.get('page', 1, type=int) or 1
    limit = request.args.get('limit', 20, type=int) or 20
    sort = request.args.get('sort', 'hot').strip() or 'hot'
    include_replies = request.args.get('include_replies', 'true').lower() == 'true'
    
    # 参数校验
    if not target_type or not target_id:
        return jsonify({'error': '缺少必需参数 target_type 或 target_id'}), 400
    
    # 限制分页参数
    page = max(1, page)
    limit = max(1, min(limit, 100))
    offset = (page - 1) * limit
    
    session = get_db_session()
    try:
        # 构建基础查询
        query = session.query(Comment).filter(
            Comment.target_type == target_type,
            Comment.target_id == target_id,
            Comment.status == 'active',
            Comment.parent_id == None  # 只查顶层评论
        )
        
        # 获取总数
        total = query.count()
        
        # 排序
        if sort == 'new':
            query = query.order_by(Comment.created_at.desc())
        elif sort == 'top':
            query = query.order_by(Comment.like_count.desc(), Comment.created_at.desc())
        else:  # hot - 热度排序（点赞数 + 回复数 + 时间衰减）
            # 简化版热度排序：点赞数优先，时间次之
            query = query.order_by(Comment.like_count.desc(), Comment.created_at.desc())
        
        # 分页
        comments = query.offset(offset).limit(limit).all()
        
        # 获取当前用户的点赞状态
        user_id = get_current_user_id()
        liked_comment_ids = set()
        if user_id:
            likes = session.query(Like).filter(
                Like.user_id == user_id,
                Like.target_type == 'comment',
                Like.target_id.in_([str(c.id) for c in comments])
            ).all()
            liked_comment_ids = {int(like.target_id) for like in likes}
        
        # 构建响应
        items = []
        for comment in comments:
            item = comment.to_dict(include_replies=include_replies)
            item['is_liked'] = comment.id in liked_comment_ids
            items.append(item)
        
        return jsonify({
            'items': items,
            'total': total,
            'page': page,
            'limit': limit,
            'has_more': offset + len(items) < total
        })
    finally:
        session.close()


@social_bp.route('/comments', methods=['POST'])
@login_required
def create_comment():
    """
    发表评论
    
    请求体：
    {
        "target_type": "triage",
        "target_id": "12345",
        "content": "评论内容",
        "parent_id": null  // 可选，回复某条评论时填写
    }
    
    响应：
    {
        "message": "评论成功",
        "comment": {...}
    }
    """
    data: Dict[str, Any] = request.json or {}
    target_type = str(data.get('target_type', '')).strip()
    target_id = str(data.get('target_id', '')).strip()
    content = str(data.get('content', '')).strip()
    parent_id = data.get('parent_id')
    
    # 参数校验
    if not target_type or not target_id:
        return jsonify({'error': '缺少必需参数 target_type 或 target_id'}), 400
    
    # 内容校验
    valid, error_msg = validate_comment_content(content)
    if not valid:
        return jsonify({'error': error_msg}), 400
    
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({'error': '请先登录'}), 401
    
    session = get_db_session()
    try:
        # 如果 parent_id 存在，验证父评论是否存在
        if parent_id:
            parent = session.query(Comment).filter(
                Comment.id == parent_id,
                Comment.status == 'active'
            ).first()
            if not parent:
                return jsonify({'error': '回复的评论不存在或已被删除'}), 404
            # 确保回复的是同一目标
            if parent.target_type != target_type or parent.target_id != target_id:
                return jsonify({'error': '回复的评论与目标不匹配'}), 400
        
        # 创建评论
        comment = Comment(
            user_id=user_id,
            target_type=target_type,
            target_id=target_id,
            content=content,
            parent_id=parent_id,
            status='active'
        )
        session.add(comment)
        session.commit()
        session.refresh(comment)
        
        return jsonify({
            'message': '评论成功',
            'comment': comment.to_dict(include_replies=False)
        }), 201
    finally:
        session.close()


@social_bp.route('/comments/<int:comment_id>', methods=['DELETE'])
@login_required
def delete_comment(comment_id: int):
    """
    删除评论（软删除，仅评论作者可操作）
    
    响应：
    {
        "message": "删除成功"
    }
    """
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({'error': '请先登录'}), 401
    
    session = get_db_session()
    try:
        comment = session.query(Comment).filter(
            Comment.id == comment_id,
            Comment.status == 'active'
        ).first()
        
        if not comment:
            return jsonify({'error': '评论不存在或已被删除'}), 404
        
        # 只能删除自己的评论
        if comment.user_id != user_id:
            return jsonify({'error': '无权删除此评论'}), 403
        
        # 软删除
        comment.status = 'deleted'
        comment.updated_at = datetime.utcnow()
        session.commit()
        
        return jsonify({'message': '删除成功'})
    finally:
        session.close()


@social_bp.route('/comments/<int:comment_id>/replies', methods=['GET'])
@login_required
def get_comment_replies(comment_id: int):
    """
    获取评论的回复列表
    
    查询参数：
    - page: 页码，默认1
    - limit: 每页数量，默认10，最大50
    
    响应：
    {
        "items": [...],
        "total": 20,
        "page": 1,
        "has_more": false
    }
    """
    page = request.args.get('page', 1, type=int) or 1
    limit = request.args.get('limit', 10, type=int) or 10
    
    page = max(1, page)
    limit = max(1, min(limit, 50))
    offset = (page - 1) * limit
    
    session = get_db_session()
    try:
        # 验证父评论是否存在
        parent = session.query(Comment).filter(
            Comment.id == comment_id,
            Comment.status == 'active'
        ).first()
        if not parent:
            return jsonify({'error': '评论不存在或已被删除'}), 404
        
        # 查询回复
        query = session.query(Comment).filter(
            Comment.parent_id == comment_id,
            Comment.status == 'active'
        ).order_by(Comment.created_at.asc())
        
        total = query.count()
        replies = query.offset(offset).limit(limit).all()
        
        # 获取当前用户的点赞状态
        user_id = get_current_user_id()
        liked_reply_ids = set()
        if user_id:
            likes = session.query(Like).filter(
                Like.user_id == user_id,
                Like.target_type == 'comment',
                Like.target_id.in_([str(r.id) for r in replies])
            ).all()
            liked_reply_ids = {int(like.target_id) for like in likes}
        
        items = []
        for reply in replies:
            item = reply.to_dict(include_replies=False)
            item['is_liked'] = reply.id in liked_reply_ids
            items.append(item)
        
        return jsonify({
            'items': items,
            'total': total,
            'page': page,
            'has_more': offset + len(items) < total
        })
    finally:
        session.close()


# ==================== 点赞接口 ====================

@social_bp.route('/likes', methods=['POST'])
@login_required
def create_like():
    """
    点赞
    
    请求体：
    {
        "target_type": "comment",
        "target_id": "123"
    }
    
    响应：
    {
        "message": "点赞成功",
        "liked": true,
        "like_count": 10
    }
    """
    data: Dict[str, Any] = request.json or {}
    target_type = str(data.get('target_type', '')).strip()
    target_id = str(data.get('target_id', '')).strip()
    
    if not target_type or not target_id:
        return jsonify({'error': '缺少必需参数 target_type 或 target_id'}), 400
    
    if target_type not in ('comment', 'triage', 'disease'):
        return jsonify({'error': '无效的 target_type'}), 400
    
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({'error': '请先登录'}), 401
    
    session = get_db_session()
    try:
        # 检查是否已点赞
        existing = session.query(Like).filter(
            Like.user_id == user_id,
            Like.target_type == target_type,
            Like.target_id == target_id
        ).first()
        
        if existing:
            return jsonify({'error': '已经点赞过了', 'liked': True}), 409
        
        # 创建点赞
        like = Like(
            user_id=user_id,
            target_type=target_type,
            target_id=target_id
        )
        session.add(like)
        
        # 更新评论的点赞数（如果是评论）
        like_count = 0
        if target_type == 'comment':
            comment = session.query(Comment).filter(
                Comment.id == int(target_id),
                Comment.status == 'active'
            ).first()
            if comment:
                comment.like_count = (comment.like_count or 0) + 1
                like_count = comment.like_count
        
        session.commit()
        
        return jsonify({
            'message': '点赞成功',
            'liked': True,
            'like_count': like_count
        })
    finally:
        session.close()


@social_bp.route('/likes', methods=['DELETE'])
@login_required
def delete_like():
    """
    取消点赞
    
    请求体：
    {
        "target_type": "comment",
        "target_id": "123"
    }
    
    响应：
    {
        "message": "取消点赞成功",
        "liked": false,
        "like_count": 9
    }
    """
    data: Dict[str, Any] = request.json or {}
    target_type = str(data.get('target_type', '')).strip()
    target_id = str(data.get('target_id', '')).strip()
    
    if not target_type or not target_id:
        return jsonify({'error': '缺少必需参数 target_type 或 target_id'}), 400
    
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({'error': '请先登录'}), 401
    
    session = get_db_session()
    try:
        # 查找点赞记录
        like = session.query(Like).filter(
            Like.user_id == user_id,
            Like.target_type == target_type,
            Like.target_id == target_id
        ).first()
        
        if not like:
            return jsonify({'error': '尚未点赞', 'liked': False}), 404
        
        session.delete(like)
        
        # 更新评论的点赞数（如果是评论）
        like_count = 0
        if target_type == 'comment':
            comment = session.query(Comment).filter(
                Comment.id == int(target_id),
                Comment.status == 'active'
            ).first()
            if comment:
                comment.like_count = max(0, (comment.like_count or 0) - 1)
                like_count = comment.like_count
        
        session.commit()
        
        return jsonify({
            'message': '取消点赞成功',
            'liked': False,
            'like_count': like_count
        })
    finally:
        session.close()


@social_bp.route('/likes/status', methods=['GET'])
@login_required
def get_like_status():
    """
    查询当前用户对某目标的点赞状态
    
    查询参数：
    - target_type: 目标类型（必需）
    - target_id: 目标ID（必需）
    
    响应：
    {
        "liked": true
    }
    """
    target_type = request.args.get('target_type', '').strip()
    target_id = request.args.get('target_id', '').strip()
    
    if not target_type or not target_id:
        return jsonify({'error': '缺少必需参数 target_type 或 target_id'}), 400
    
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({'liked': False})
    
    session = get_db_session()
    try:
        like = session.query(Like).filter(
            Like.user_id == user_id,
            Like.target_type == target_type,
            Like.target_id == target_id
        ).first()
        
        return jsonify({'liked': like is not None})
    finally:
        session.close()


# ==================== 注册函数 ====================

def register_social_routes(app):
    """
    注册社交互动路由到 Flask 应用
    
    Args:
        app: Flask 应用实例
    """
    app.register_blueprint(social_bp)
