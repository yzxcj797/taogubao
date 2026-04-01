"""
查看向量数据库内容

使用方法:
    python -m src.cli.view_vector_db              # 查看统计信息
    python -m src.cli.view_vector_db --list       # 列出所有文档
    python -m src.cli.view_vector_db --limit 10   # 限制显示数量
    python -m src.cli.view_vector_db --author "jl韭菜抄家"  # 按作者筛选
"""

import argparse
import sys
from pathlib import Path
from collections import Counter

from loguru import logger

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent

from src.vector.vector_store import VectorStore


def format_metadata(metadata: dict) -> str:
    """格式化元数据"""
    parts = []
    if 'author_name' in metadata:
        parts.append(f"作者:{metadata['author_name']}")
    if 'doc_type' in metadata:
        parts.append(f"类型:{metadata['doc_type']}")
    if 'publish_time' in metadata:
        time_str = metadata['publish_time'][:10] if len(metadata['publish_time']) > 10 else metadata['publish_time']
        parts.append(f"时间:{time_str}")
    if 'floor_number' in metadata:
        parts.append(f"楼层:{metadata['floor_number']}")
    return " | ".join(parts)


def main():
    parser = argparse.ArgumentParser(description="查看向量数据库内容")
    parser.add_argument("--collection", default="taoguba_posts", help="集合名称")
    parser.add_argument("--persist", default=str(PROJECT_ROOT / "vector_db"), help="数据库路径")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有文档")
    parser.add_argument("--limit", type=int, default=20, help="显示数量限制")
    parser.add_argument("--author", help="按作者筛选")
    parser.add_argument("--type", choices=["post_title", "post_content", "comment"], help="按类型筛选")
    args = parser.parse_args()

    # 配置日志
    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    print("=" * 70)
    print("向量数据库查看工具")
    print("=" * 70)
    print(f"集合: {args.collection}")
    print(f"路径: {args.persist}")
    print("=" * 70)

    try:
        # 连接数据库
        vector_store = VectorStore(
            collection_name=args.collection,
            persist_directory=args.persist,
            use_chroma=True
        )

        # 获取集合信息
        collection = vector_store._chroma_collection
        
        # 获取所有数据
        result = collection.get()
        
        total_docs = len(result["ids"])
        print(f"\n总文档数: {total_docs}")
        
        if total_docs == 0:
            print("数据库为空")
            return

        # 统计信息
        metadatas = result.get("metadatas", []) or []
        
        # 按类型统计
        doc_types = Counter(m.get("doc_type", "unknown") for m in metadatas if m)
        print("\n文档类型分布:")
        for doc_type, count in doc_types.most_common():
            print(f"  {doc_type}: {count}")
        
        # 按作者统计
        authors = Counter(m.get("author_name", "unknown") for m in metadatas if m)
        print("\n作者分布:")
        for author, count in authors.most_common(10):
            print(f"  {author}: {count}")
        
        # 按帖子统计
        posts = Counter(m.get("post_id", "unknown") for m in metadatas if m and m.get("post_id"))
        print(f"\n帖子数量: {len(posts)}")

        # 列出文档
        if args.list or args.author or args.type:
            print("\n" + "=" * 70)
            print("文档列表")
            print("=" * 70)
            
            ids = result["ids"]
            documents = result.get("documents", []) or []
            
            displayed = 0
            for i, (doc_id, content, metadata) in enumerate(zip(ids, documents, metadatas)):
                if displayed >= args.limit:
                    print(f"\n... 还有 {total_docs - args.limit} 条数据 ...")
                    break
                
                # 筛选
                if args.author and metadata.get("author_name") != args.author:
                    continue
                if args.type and metadata.get("doc_type") != args.type:
                    continue
                
                displayed += 1
                meta_str = format_metadata(metadata) if metadata else "无元数据"
                content_preview = content[:150] + "..." if len(content) > 150 else content
                
                print(f"\n[{displayed}] ID: {doc_id}")
                print(f"    {meta_str}")
                print(f"    内容: {content_preview}")

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
