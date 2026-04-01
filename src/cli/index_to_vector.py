"""
将已抓取的帖子 JSON 文件导入向量数据库

使用方法:
    python -m src.cli.index_to_vector                    # 导入 output/ 目录下所有 JSON 文件
    python -m src.cli.index_to_vector --file output/jl韭菜抄家_20260326_123456.json  # 导入指定文件
    python -m src.cli.index_to_vector --dir output/jl韭菜抄家  # 导入指定目录
    python -m src.cli.index_to_vector --collection my_collection  # 指定集合名称
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from loguru import logger

from src.vector.vector_store import VectorStore, TaogubaVectorizer

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent


def setup_logging():
    """配置日志"""
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    logger.add(PROJECT_ROOT / "logs" / "index_to_vector_{time}.log", rotation="10 MB", level="DEBUG")


def parse_datetime(dt_str: str) -> Optional[datetime]:
    """解析日期时间字符串"""
    if not dt_str:
        return None
    
    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(dt_str[:19] if 'T' in dt_str else dt_str, fmt)
        except ValueError:
            continue
    
    return None


def load_json_file(filepath: Path) -> Optional[Dict[str, Any]]:
    """加载 JSON 文件"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载文件失败 {filepath}: {e}")
        return None


def find_json_files(source_path: Path) -> List[Path]:
    """
    查找所有 JSON 文件
    
    Args:
        source_path: 文件或目录路径
        
    Returns:
        JSON 文件路径列表
    """
    if source_path.is_file():
        if source_path.suffix.lower() == '.json':
            return [source_path]
        else:
            logger.warning(f"跳过非 JSON 文件: {source_path}")
            return []
    
    elif source_path.is_dir():
        json_files = []
        for json_file in source_path.glob("*.json"):
            json_files.append(json_file)
        return json_files
    
    else:
        logger.error(f"路径不存在: {source_path}")
        return []


def process_post_to_documents(post: Dict[str, Any], blogger_name: str) -> List[Dict[str, Any]]:
    """
    将帖子转换为文档列表
    
    Args:
        post: 帖子数据
        blogger_name: 博主名称
        
    Returns:
        文档列表
    """
    documents = []
    
    post_id = post.get('post_id', '')
    title = post.get('title', '')
    content = post.get('content', '')
    author_name = post.get('author_name', blogger_name)
    publish_time = post.get('publish_time', '')
    url = post.get('url', '')
    
    # 1. 添加帖子标题
    if title:
        documents.append({
            "id": f"title_{post_id}",
            "content": f"标题: {title}",
            "metadata": {
                "doc_type": "post_title",
                "post_id": post_id,
                "author_name": author_name,
                "publish_time": publish_time,
                "url": url,
            }
        })
    
    # 2. 添加帖子正文
    if content:
        documents.append({
            "id": f"content_{post_id}",
            "content": content,
            "metadata": {
                "doc_type": "post_content",
                "post_id": post_id,
                "author_name": author_name,
                "publish_time": publish_time,
                "url": url,
                "title": title,
            }
        })
    
    # 3. 处理评论
    comments = post.get('comments', [])
    for comment in comments:
        comment_docs = process_comment_to_documents(comment, post_id, author_name, title, url)
        documents.extend(comment_docs)
    
    return documents


def process_comment_to_documents(
    comment: Dict[str, Any],
    post_id: str,
    post_author: str,
    post_title: str,
    post_url: str
) -> List[Dict[str, Any]]:
    """
    将评论转换为文档列表（递归处理子评论）
    
    Args:
        comment: 评论数据
        post_id: 帖子ID
        post_author: 帖子作者
        post_title: 帖子标题
        post_url: 帖子URL
        
    Returns:
        文档列表
    """
    documents = []
    
    comment_id = comment.get('comment_id', '')
    content = comment.get('content', '')
    author_name = comment.get('author_name', '未知')
    publish_time = comment.get('publish_time', '')
    floor_number = comment.get('floor_number', '')
    
    if content:
        # 使用 post_id + comment_id 确保唯一性
        unique_comment_id = f"{post_id}_{comment_id}" if comment_id else f"{post_id}_{hash(content) & 0xFFFFFFFF}"
        documents.append({
            "id": f"comment_{unique_comment_id}",
            "content": content,
            "metadata": {
                "doc_type": "comment",
                "post_id": post_id,
                "post_author": post_author,
                "post_title": post_title,
                "post_url": post_url,
                "comment_id": comment_id,
                "author_name": author_name,
                "publish_time": publish_time,
                "floor_number": floor_number,
            }
        })
    
    # 递归处理子评论
    children = comment.get('children', [])
    for child in children:
        child_docs = process_comment_to_documents(child, post_id, post_author, post_title, post_url)
        documents.extend(child_docs)
    
    return documents


def index_json_file(
    json_file: Path,
    vectorizer: TaogubaVectorizer,
    skip_existing: bool = True
) -> tuple[int, int]:
    """
    索引单个 JSON 文件
    
    Args:
        json_file: JSON 文件路径
        vectorizer: 向量化器
        skip_existing: 是否跳过已存在的文档
        
    Returns:
        (成功数量, 跳过数量)
    """
    logger.info(f"正在处理文件: {json_file}")
    
    data = load_json_file(json_file)
    if not data:
        return 0, 0
    
    # 获取博主信息
    blogger = data.get('blogger', {})
    blogger_name = blogger.get('username', '未知博主')
    
    # 获取帖子列表
    posts = data.get('posts', [])
    if not posts:
        logger.warning(f"文件中没有帖子: {json_file}")
        return 0, 0
    
    logger.info(f"博主: {blogger_name}, 帖子数: {len(posts)}")
    
    # 收集所有文档
    all_documents = []
    seen_ids = set()  # 用于去重
    
    for post in posts:
        docs = process_post_to_documents(post, blogger_name)
        for doc in docs:
            doc_id = doc.get("id")
            if doc_id and doc_id not in seen_ids:
                seen_ids.add(doc_id)
                all_documents.append(doc)
            elif doc_id:
                logger.debug(f"跳过重复文档: {doc_id}")
    
    logger.info(f"共生成 {len(all_documents)} 个文档块 (已去重)")
    
    # 批量添加到向量数据库
    if all_documents:
        doc_ids = vectorizer.vector_store.add_documents(all_documents, skip_if_exists=skip_existing)
        
        # 统计结果
        success_count = sum(1 for doc_id in doc_ids if doc_id is not None)
        skip_count = len(doc_ids) - success_count
        
        logger.info(f"成功添加: {success_count}, 跳过已存在: {skip_count}")
        return success_count, skip_count
    
    return 0, 0


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="将已抓取的帖子 JSON 文件导入向量数据库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m src.cli.index_to_vector
    导入 output/ 目录下所有 JSON 文件
    
  python -m src.cli.index_to_vector --file output/jl韭菜抄家_20260326_123456.json
    导入指定文件
    
  python -m src.cli.index_to_vector --dir output/jl韭菜抄家
    导入指定目录
    
  python -m src.cli.index_to_vector --collection my_collection --force
    使用指定集合名称，强制重新索引（不跳过已存在）
        """
    )
    
    parser.add_argument(
        "--file",
        type=str,
        help="指定要导入的 JSON 文件路径"
    )
    
    parser.add_argument(
        "--dir",
        type=str,
        help="指定要导入的目录路径（会递归查找所有 JSON 文件）"
    )
    
    parser.add_argument(
        "--collection",
        type=str,
        default="taoguba_posts",
        help="向量数据库集合名称 (默认: taoguba_posts)"
    )
    
    parser.add_argument(
        "--persist",
        type=str,
        default=str(PROJECT_ROOT / "vector_db"),
        help=f"向量数据库持久化目录 (默认: {PROJECT_ROOT / 'vector_db'})"
    )
    
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新索引，不跳过已存在的文档"
    )
    
    args = parser.parse_args()
    
    # 配置日志
    setup_logging()
    
    # 确定源路径
    if args.file:
        source_path = Path(args.file)
    elif args.dir:
        source_path = Path(args.dir)
    else:
        # 默认使用 output 目录
        source_path = PROJECT_ROOT / "output"
    
    # 查找所有 JSON 文件
    json_files = find_json_files(source_path)
    
    if not json_files:
        logger.error(f"未找到 JSON 文件: {source_path}")
        sys.exit(1)
    
    logger.info(f"找到 {len(json_files)} 个 JSON 文件")
    
    # 初始化向量数据库
    logger.info(f"正在连接向量数据库...")
    logger.info(f"  集合: {args.collection}")
    logger.info(f"  路径: {args.persist}")
    
    try:
        vector_store = VectorStore(
            collection_name=args.collection,
            persist_directory=args.persist,
            use_chroma=True
        )
        vectorizer = TaogubaVectorizer(vector_store)
        
        # 显示当前统计
        stats = vectorizer.get_stats()
        if "error" not in stats:
            logger.info(f"当前数据库文档数: {stats.get('document_count', 0)}")
        
    except Exception as e:
        logger.error(f"初始化向量数据库失败: {e}")
        sys.exit(1)
    
    # 处理所有文件
    total_success = 0
    total_skip = 0
    
    print("\n" + "=" * 60)
    print("开始导入数据到向量数据库")
    print("=" * 60)
    
    for i, json_file in enumerate(json_files, 1):
        print(f"\n[{i}/{len(json_files)}] 处理: {json_file.name}")
        success, skip = index_json_file(
            json_file,
            vectorizer,
            skip_existing=not args.force
        )
        total_success += success
        total_skip += skip
    
    # 最终统计
    print("\n" + "=" * 60)
    print("导入完成!")
    print("=" * 60)
    print(f"处理的文件数: {len(json_files)}")
    print(f"成功添加: {total_success}")
    print(f"跳过已存在: {total_skip}")
    
    # 显示最终统计
    final_stats = vectorizer.get_stats()
    if "error" not in final_stats:
        print(f"数据库总文档数: {final_stats.get('document_count', 0)}")
    
    print("=" * 60)


if __name__ == "__main__":
    main()
