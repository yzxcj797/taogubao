"""
淘股宝

项目结构:
- src/crawler: 爬虫模块
- src/vector: 向量数据库模块
- src/rag: RAG问答模块
- src/utils: 工具模块
- src/cli: 命令行工具

使用示例:
    from src.crawler import TaogubaCrawler, crawl_blogger
    from src.rag import RAGSystem, create_rag_system
    from src.vector import VectorStore
"""

__version__ = "1.0.0"

# 便捷导入
from src.crawler import (
    TaogubaCrawler,
    crawl_blogger,
    MainPost,
    CommentNode,
    BloggerInfo,
    CrawlResult,
    DataStorage,
)
from src.vector import VectorStore, TaogubaVectorizer, DocumentChunk
from src.rag import RAGSystem, create_rag_system, RAGResponse
from src.utils import get_config, RAGConfig

__all__ = [
    # 爬虫
    'TaogubaCrawler',
    'crawl_blogger',
    'MainPost',
    'CommentNode',
    'BloggerInfo',
    'CrawlResult',
    'DataStorage',
    # 向量
    'VectorStore',
    'TaogubaVectorizer',
    'DocumentChunk',
    # RAG
    'RAGSystem',
    'create_rag_system',
    'RAGResponse',
    # 工具
    'get_config',
    'RAGConfig',
]
