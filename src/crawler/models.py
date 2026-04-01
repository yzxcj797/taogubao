"""
淘股吧爬虫数据模型定义
定义主帖、跟帖/评论的数据结构和树状关系
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class CommentNode(BaseModel):
    """
    评论/跟帖节点模型 - 树状结构
    每个节点代表一条评论或回复
    """
    comment_id: str = Field(..., description="评论唯一ID")
    parent_id: Optional[str] = Field(None, description="父评论ID，顶级评论为None")
    author_id: Optional[str] = Field(None, description="评论者用户ID")
    author_name: str = Field(..., description="评论者昵称")
    author_avatar: Optional[str] = Field(None, description="评论者头像URL")
    content: str = Field(..., description="评论内容")
    publish_time: datetime = Field(..., description="发布时间")
    like_count: int = Field(0, description="点赞数")
    reply_count: int = Field(0, description="回复数")
    floor_number: Optional[int] = Field(None, description="楼层号")
    children: List['CommentNode'] = Field(default_factory=list, description="子评论列表")
    
    # 额外元数据
    extra_data: Dict[str, Any] = Field(default_factory=dict, description="额外数据")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class MainPost(BaseModel):
    """
    主帖模型
    代表博主发布的主帖子
    """
    post_id: str = Field(..., description="帖子唯一ID")
    title: str = Field(..., description="帖子标题")
    content: str = Field(..., description="帖子正文内容")
    content_html: Optional[str] = Field(None, description="原始HTML内容")
    
    # 作者信息
    author_id: Optional[str] = Field(None, description="作者用户ID")
    author_name: str = Field(..., description="作者昵称")
    author_avatar: Optional[str] = Field(None, description="作者头像URL")
    
    # 统计数据
    view_count: int = Field(0, description="浏览数")
    comment_count: int = Field(0, description="评论数")
    like_count: int = Field(0, description="点赞数")
    
    # 时间信息
    publish_time: datetime = Field(..., description="发布时间")
    update_time: Optional[datetime] = Field(None, description="更新时间")
    
    # 帖子元数据
    post_type: Optional[str] = Field(None, description="帖子类型：原创、精华等")
    tags: List[str] = Field(default_factory=list, description="标签列表")
    category: Optional[str] = Field(None, description="所属分类")
    
    # URL
    url: str = Field(..., description="帖子URL")
    
    # 评论树
    comments: List[CommentNode] = Field(default_factory=list, description="评论树列表")
    
    # 额外元数据
    extra_data: Dict[str, Any] = Field(default_factory=dict, description="额外数据")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class BloggerInfo(BaseModel):
    """
    博主信息模型
    """
    user_id: Optional[str] = Field(None, description="用户ID")
    username: str = Field(..., description="用户名")
    nickname: Optional[str] = Field(None, description="昵称")
    avatar: Optional[str] = Field(None, description="头像URL")
    followers_count: Optional[int] = Field(None, description="粉丝数")
    following_count: Optional[int] = Field(None, description="关注数")
    posts_count: Optional[int] = Field(None, description="发帖数")
    likes_count: Optional[int] = Field(None, description="被赞数")
    cheers_count: Optional[int] = Field(None, description="被加油数")
    profile_url: Optional[str] = Field(None, description="个人主页URL")
    description: Optional[str] = Field(None, description="个人简介")


class CrawlResult(BaseModel):
    """
    爬取结果模型
    """
    blogger: BloggerInfo = Field(..., description="博主信息")
    posts: List[MainPost] = Field(default_factory=list, description="主帖列表")
    crawl_time: datetime = Field(default_factory=datetime.now, description="爬取时间")
    start_date: Optional[datetime] = Field(None, description="开始日期")
    end_date: Optional[datetime] = Field(None, description="结束日期")
    total_posts: int = Field(0, description="主帖总数")
    total_comments: int = Field(0, description="评论总数")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# 解决循环引用
CommentNode.model_rebuild()
MainPost.model_rebuild()
