"""
社交互动模块 - 评论和点赞功能的数据模型

功能：
- 评论系统：支持对导诊记录、疾病知识等进行评论和回复
- 点赞系统：支持对评论、导诊记录等进行点赞
- 内容审核：敏感词过滤和反垃圾机制

数据模型：
- Comment: 评论表，支持楼中楼回复
- Like: 点赞表，记录用户的点赞行为

使用示例：
    from social import Comment, Like, create_comment, toggle_like
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship, backref
from database import Base


class Comment(Base):
    """
    评论表 - 存储用户评论和回复
    
    字段说明：
    - id: 主键，自增
    - user_id: 外键，关联到users表（评论作者）
    - target_type: 评论目标类型（'triage'/'disease'/'article'）
    - target_id: 评论目标ID（导诊记录ID/疾病ID/文章ID）
    - content: 评论内容（纯文本）
    - parent_id: 父评论ID，支持楼中楼回复（可为空）
    - like_count: 点赞数（冗余字段，加速查询）
    - status: 评论状态（'active'/'deleted'/'hidden'）
    - created_at: 创建时间
    - updated_at: 更新时间
    
    关联：
    - user: 评论作者
    - parent: 父评论（被回复的评论）
    - replies: 子回复列表
    """
    __tablename__ = 'comments'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    target_type = Column(String(20), nullable=False)  # 'triage' | 'disease' | 'article'
    target_id = Column(String(50), nullable=False, index=True)
    content = Column(Text, nullable=False)
    parent_id = Column(Integer, ForeignKey('comments.id'), nullable=True, index=True)
    like_count = Column(Integer, default=0)
    status = Column(String(10), default='active')  # active | deleted | hidden
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联关系
    user = relationship("User", backref="comments")
    replies = relationship("Comment", 
                          backref=backref("parent", remote_side="Comment.id"),
                          cascade="all, delete-orphan")
    
    # 复合索引：加速按目标查询评论
    __table_args__ = (
        Index('idx_target', 'target_type', 'target_id'),
    )
    
    def to_dict(self, include_user=True, include_replies=False):
        """转换为字典格式，用于API响应"""
        data = {
            'id': self.id,
            'target_type': self.target_type,
            'target_id': self.target_id,
            'content': self.content,
            'parent_id': self.parent_id,
            'like_count': self.like_count,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_user and self.user:
            data['user'] = {
                'id': self.user.id,
                'username': self.user.username,
                'membership_type': self.user.membership_type or 'free'
            }
        if include_replies and self.replies:
            # 只返回前3条活跃回复
            active_replies = [r for r in self.replies if r.status == 'active'][:3]
            data['replies'] = [r.to_dict(include_replies=False) for r in active_replies]
            data['reply_count'] = len([r for r in self.replies if r.status == 'active'])
        return data


class Like(Base):
    """
    点赞表 - 记录用户的点赞行为
    
    字段说明：
    - id: 主键，自增
    - user_id: 外键，关联到users表（点赞用户）
    - target_type: 点赞目标类型（'comment'/'triage'/'disease'）
    - target_id: 点赞目标ID
    - created_at: 点赞时间
    
    约束：
    - 联合唯一索引：同一用户对同一目标只能点赞一次
    """
    __tablename__ = 'likes'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    target_type = Column(String(20), nullable=False)  # 'comment' | 'triage' | 'disease'
    target_id = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 联合唯一约束：防止重复点赞
    __table_args__ = (
        UniqueConstraint('user_id', 'target_type', 'target_id', name='unique_like'),
        Index('idx_like_target', 'target_type', 'target_id'),
    )
    
    user = relationship("User", backref="likes")


# ==================== 敏感词过滤 ====================

# 基础敏感词列表（实际项目中应从配置文件或数据库加载）
SENSITIVE_WORDS = {
    'spam': ['广告', '推广', '加微信', '加QQ', '联系方式', '点击链接', '免费领'],
    'inappropriate': ['脏话', '攻击', '歧视'],  # 示例，实际应扩展
}

def check_sensitive_content(content: str) -> tuple[bool, str]:
    """
    检查内容是否包含敏感词
    
    Args:
        content: 待检查的内容
        
    Returns:
        (是否通过, 违规类型或空字符串)
    """
    content_lower = content.lower()
    
    for category, words in SENSITIVE_WORDS.items():
        for word in words:
            if word in content_lower:
                return False, category
    
    return True, ''


def validate_comment_content(content: str) -> tuple[bool, str]:
    """
    验证评论内容
    
    检查规则：
    - 长度：10-500字符
    - 敏感词过滤
    - 重复内容检测（简单实现）
    
    Args:
        content: 评论内容
        
    Returns:
        (是否有效, 错误信息)
    """
    if not content:
        return False, '评论内容不能为空'
    
    if len(content) < 10:
        return False, '评论内容至少需要10个字符'
    
    if len(content) > 500:
        return False, '评论内容不能超过500个字符'
    
    # 敏感词检查
    passed, category = check_sensitive_content(content)
    if not passed:
        return False, f'内容包含不当信息({category})，请修改后重试'
    
    return True, ''
