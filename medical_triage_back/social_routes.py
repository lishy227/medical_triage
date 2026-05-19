"""
社交互动 API 路由 - 评论和点赞接口

FastAPI 版本：APIRouter + Depends 依赖注入

接口列表：
- GET    /api/comments              获取评论列表
- POST   /api/comments              发表评论
- DELETE /api/comments/{comment_id}  删除评论
- GET    /api/comments/{comment_id}/replies  获取评论回复
- POST   /api/likes                 点赞
- DELETE /api/likes                 取消点赞
- GET    /api/likes/status          查询点赞状态
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_current_user
from database import User, get_db_session
from social import Comment, Like, validate_comment_content

# ---- 路由器 ----------------------------------------------------------------
social_router = APIRouter(prefix='/api', tags=['社交互动'])

# ---- 请求模型 -------------------------------------------------------------

class CommentCreateRequest(BaseModel):
    target_type: str = Field(..., description='目标类型: triage / disease / article')
    target_id: str = Field(..., description='目标ID')
    content: str = Field(..., min_length=1, max_length=500, description='评论内容')
    parent_id: Optional[int] = Field(None, description='父评论ID（回复时填写）')


class LikeRequest(BaseModel):
    target_type: str = Field(..., description='目标类型: comment / triage / disease')
    target_id: str = Field(..., description='目标ID')

# ---- 辅助函数 -------------------------------------------------------------

def _get_liked_ids(user: User, comment_ids: list, db: Session) -> set[int]:
    """查询当前用户对一批评论的点赞状态"""
    if not comment_ids:
        return set()
    likes = db.query(Like).filter(
        Like.user_id == user.id,
        Like.target_type == 'comment',
        Like.target_id.in_([str(cid) for cid in comment_ids]),
    ).all()
    return {int(like.target_id) for like in likes}

# ---- 评论接口 -------------------------------------------------------------

@social_router.get('/comments')
def get_comments(
    target_type: str = Query(..., description='目标类型'),
    target_id: str = Query(..., description='目标ID'),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sort: str = Query('hot', pattern='^(hot|new|top)$'),
    include_replies: bool = Query(True),
    user: User = Depends(get_current_user),
):
    """获取评论列表（分页、排序）"""
    limit = min(limit, 100)
    offset = (page - 1) * limit

    with get_db_session() as db:
        query = db.query(Comment).filter(
            Comment.target_type == target_type,
            Comment.target_id == target_id,
            Comment.status == 'active',
            Comment.parent_id == None,  # 只查顶层评论
        )
        total = query.count()

        # 排序
        sort_key = (
            Comment.like_count.desc() if sort in ('hot', 'top')
            else Comment.created_at.desc()
        )
        query = query.order_by(sort_key, Comment.created_at.desc())

        comments = query.offset(offset).limit(limit).all()

        cids = [c.id for c in comments]
        liked = _get_liked_ids(user, cids, db)

        items = []
        for c in comments:
            item = c.to_dict(include_replies=include_replies)
            item['is_liked'] = c.id in liked
            items.append(item)

        return {
            'items': items,
            'total': total,
            'page': page,
            'limit': limit,
            'has_more': offset + len(items) < total,
        }


@social_router.post('/comments', status_code=201)
def create_comment(
    data: CommentCreateRequest,
    user: User = Depends(get_current_user),
):
    """发表评论 / 回复"""
    valid, error_msg = validate_comment_content(data.content)
    if not valid:
        raise HTTPException(status_code=400, detail=error_msg)

    with get_db_session() as db:
        parent = None
        if data.parent_id:
            parent = db.query(Comment).filter(
                Comment.id == data.parent_id,
                Comment.status == 'active',
            ).first()
            if not parent:
                raise HTTPException(404, '回复的评论不存在或已被删除')
            if (parent.target_type != data.target_type or
                parent.target_id != data.target_id):
                raise HTTPException(400, '回复的评论与目标不匹配')

        comment = Comment(
            user_id=user.id,
            target_type=data.target_type,
            target_id=data.target_id,
            content=data.content,
            parent_id=data.parent_id,
            status='active',
        )
        db.add(comment)
        db.commit()
        db.refresh(comment)

        return {
            'message': '评论成功',
            'comment': comment.to_dict(include_replies=False),
        }


@social_router.delete('/comments/{comment_id}')
def delete_comment(
    comment_id: int,
    user: User = Depends(get_current_user),
):
    """删除评论（软删除，仅作者可操作）"""
    with get_db_session() as db:
        comment = db.query(Comment).filter(
            Comment.id == comment_id,
            Comment.status == 'active',
        ).first()
        if not comment:
            raise HTTPException(404, '评论不存在或已被删除')
        if comment.user_id != user.id:
            raise HTTPException(403, '无权删除此评论')

        comment.status = 'deleted'
        comment.updated_at = datetime.utcnow()
        db.commit()
        return {'message': '删除成功'}


@social_router.get('/comments/{comment_id}/replies')
def get_comment_replies(
    comment_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    user: User = Depends(get_current_user),
):
    """获取评论的回复列表"""
    limit = min(limit, 50)
    offset = (page - 1) * limit

    with get_db_session() as db:
        parent = db.query(Comment).filter(
            Comment.id == comment_id,
            Comment.status == 'active',
        ).first()
        if not parent:
            raise HTTPException(404, '评论不存在或已被删除')

        query = db.query(Comment).filter(
            Comment.parent_id == comment_id,
            Comment.status == 'active',
        ).order_by(Comment.created_at.asc())

        total = query.count()
        replies = query.offset(offset).limit(limit).all()

        rids = [r.id for r in replies]
        liked = _get_liked_ids(user, rids, db)

        items = []
        for r in replies:
            item = r.to_dict(include_replies=False)
            item['is_liked'] = r.id in liked
            items.append(item)

        return {
            'items': items,
            'total': total,
            'page': page,
            'has_more': offset + len(items) < total,
        }

# ---- 点赞接口 -------------------------------------------------------------

@social_router.post('/likes')
def create_like(
    data: LikeRequest,
    user: User = Depends(get_current_user),
):
    """点赞"""
    if data.target_type not in ('comment', 'triage', 'disease'):
        raise HTTPException(400, '无效的 target_type')

    with get_db_session() as db:
        existing = db.query(Like).filter(
            Like.user_id == user.id,
            Like.target_type == data.target_type,
            Like.target_id == data.target_id,
        ).first()
        if existing:
            raise HTTPException(409, '已经点赞过了')

        like = Like(
            user_id=user.id,
            target_type=data.target_type,
            target_id=data.target_id,
        )
        db.add(like)

        like_count = 0
        if data.target_type == 'comment':
            comment = db.query(Comment).filter(
                Comment.id == int(data.target_id),
                Comment.status == 'active',
            ).first()
            if comment:
                comment.like_count = (comment.like_count or 0) + 1
                like_count = comment.like_count

        db.commit()
        return {'message': '点赞成功', 'liked': True, 'like_count': like_count}


@social_router.delete('/likes')
def delete_like(
    data: LikeRequest,
    user: User = Depends(get_current_user),
):
    """取消点赞"""
    if data.target_type not in ('comment', 'triage', 'disease'):
        raise HTTPException(400, '无效的 target_type')

    with get_db_session() as db:
        like = db.query(Like).filter(
            Like.user_id == user.id,
            Like.target_type == data.target_type,
            Like.target_id == data.target_id,
        ).first()
        if not like:
            raise HTTPException(404, '尚未点赞')

        db.delete(like)

        like_count = 0
        if data.target_type == 'comment':
            comment = db.query(Comment).filter(
                Comment.id == int(data.target_id),
                Comment.status == 'active',
            ).first()
            if comment:
                comment.like_count = max(0, (comment.like_count or 0) - 1)
                like_count = comment.like_count

        db.commit()
        return {'message': '取消点赞成功', 'liked': False, 'like_count': like_count}


@social_router.get('/likes/status')
def get_like_status(
    target_type: str = Query(..., description='目标类型'),
    target_id: str = Query(..., description='目标ID'),
    user: User = Depends(get_current_user),
):
    """查询当前用户对某目标的点赞状态"""
    with get_db_session() as db:
        like = db.query(Like).filter(
            Like.user_id == user.id,
            Like.target_type == target_type,
            Like.target_id == target_id,
        ).first()
        return {'liked': like is not None}
