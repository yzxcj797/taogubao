"""
数据存储模块
支持JSON和Markdown格式的数据导出
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.crawler.models import MainPost, CrawlResult, CommentNode


class DateTimeEncoder(json.JSONEncoder):
    """自定义JSON编码器，处理datetime类型"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class DataStorage:
    """数据存储管理器"""
    
    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名中的非法字符"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename[:100]  # 限制长度
    
    def save_to_json(self, result: CrawlResult, filename: Optional[str] = None) -> str:
        """
        将爬取结果保存为JSON文件
        
        Args:
            result: 爬取结果
            filename: 可选的文件名，默认自动生成
            
        Returns:
            保存的文件路径
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_username = self._sanitize_filename(result.blogger.username)
            filename = f"{safe_username}_{timestamp}.json"
        
        filepath = self.output_dir / filename
        
        # 转换为字典并保存
        data = result.model_dump()
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
        
        return str(filepath)
    
    def save_to_markdown(self, result: CrawlResult, filename: Optional[str] = None) -> str:
        """
        将爬取结果保存为Markdown文件（便于阅读）
        
        Args:
            result: 爬取结果
            filename: 可选的文件名，默认自动生成
            
        Returns:
            保存的文件路径
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_username = self._sanitize_filename(result.blogger.username)
            filename = f"{safe_username}_{timestamp}.md"
        
        filepath = self.output_dir / filename
        
        md_content = self._generate_markdown(result)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        return str(filepath)
    
    def _generate_markdown(self, result: CrawlResult) -> str:
        """生成Markdown格式的内容"""
        lines = []
        
        # 标题
        lines.append(f"# 淘股吧博主：{result.blogger.username} 帖子汇总")
        lines.append("")
        
        # 博主信息
        lines.append("## 博主信息")
        lines.append(f"- **用户名**: {result.blogger.username}")
        if result.blogger.nickname:
            lines.append(f"- **昵称**: {result.blogger.nickname}")
        if result.blogger.user_id:
            lines.append(f"- **用户ID**: {result.blogger.user_id}")
        if result.blogger.followers_count:
            lines.append(f"- **粉丝数**: {result.blogger.followers_count}")
        if result.blogger.posts_count:
            lines.append(f"- **发帖数**: {result.blogger.posts_count}")
        if result.blogger.description:
            lines.append(f"- **简介**: {result.blogger.description}")
        lines.append("")
        
        # 爬取统计
        lines.append("## 爬取统计")
        lines.append(f"- **爬取时间**: {result.crawl_time.strftime('%Y-%m-%d %H:%M:%S')}")
        if result.start_date:
            lines.append(f"- **开始日期**: {result.start_date.strftime('%Y-%m-%d')}")
        if result.end_date:
            lines.append(f"- **结束日期**: {result.end_date.strftime('%Y-%m-%d')}")
        lines.append(f"- **主帖总数**: {result.total_posts}")
        lines.append(f"- **评论总数**: {result.total_comments}")
        lines.append("")
        
        # 帖子详情
        lines.append("## 帖子详情")
        lines.append("")
        
        for idx, post in enumerate(result.posts, 1):
            lines.append(f"### {idx}. {post.title}")
            lines.append("")
            lines.append(f"**发布时间**: {post.publish_time.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"**浏览数**: {post.view_count} | **评论数**: {post.comment_count} | **点赞数**: {post.like_count}")
            if post.post_type:
                lines.append(f"**类型**: {post.post_type}")
            lines.append(f"**链接**: {post.url}")
            lines.append("")
            
            # 正文内容
            lines.append("#### 正文")
            lines.append(post.content)
            lines.append("")
            
            # 评论
            if post.comments:
                lines.append(f"#### 评论 ({len(post.comments)}条)")
                lines.append("")
                for comment in post.comments:
                    lines.extend(self._format_comment_tree(comment, level=0))
                lines.append("")
            
            lines.append("---")
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_comment_tree(self, comment: CommentNode, level: int = 0) -> List[str]:
        """格式化评论树为Markdown列表"""
        lines = []
        indent = "  " * level
        
        # 评论头部
        time_str = comment.publish_time.strftime('%m-%d %H:%M')
        lines.append(f"{indent}- **{comment.author_name}** ({time_str})")
        
        # 评论内容
        content_lines = comment.content.strip().split('\n')
        for content_line in content_lines:
            lines.append(f"{indent}  > {content_line}")
        
        # 互动数据
        lines.append(f"{indent}  👍 {comment.like_count}  💬 {comment.reply_count}")
        lines.append("")
        
        # 递归处理子评论
        for child in comment.children:
            lines.extend(self._format_comment_tree(child, level + 1))
        
        return lines
    
    def save_post_separately(self, post: MainPost, blogger_name: str) -> str:
        """
        将单个帖子保存为单独的文件
        
        Args:
            post: 主帖
            blogger_name: 博主名称
            
        Returns:
            保存的文件路径
        """
        # 创建博主专属目录
        blogger_dir = self.output_dir / self._sanitize_filename(blogger_name)
        blogger_dir.mkdir(exist_ok=True)
        
        # 生成文件名
        timestamp = post.publish_time.strftime("%Y%m%d_%H%M%S")
        safe_title = self._sanitize_filename(post.title[:30])
        filename = f"{timestamp}_{safe_title}.json"
        
        filepath = blogger_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(post.model_dump(), f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
        
        return str(filepath)
