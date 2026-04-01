"""
清空向量数据库工具

使用方法:
    python clear_vector_db.py              # 使用默认配置清空
    python clear_vector_db.py --stats      # 仅查看统计信息，不清空
    python clear_vector_db.py --yes        # 跳过确认直接清空
    python clear_vector_db.py --collection my_collection --persist ./my_db
"""

import argparse
import sys
from src.vector.vector_store import VectorStore, TaogubaVectorizer


def get_stats(vectorizer: TaogubaVectorizer):
    """获取并显示向量数据库统计信息"""
    stats = vectorizer.get_stats()
    
    print("\n" + "="*50)
    print("向量数据库统计信息")
    print("="*50)
    
    if "error" in stats:
        print(f"错误: {stats['error']}")
        return
    
    print(f"集合名称: {stats.get('collection_name', 'N/A')}")
    print(f"存储类型: {stats.get('storage_type', 'N/A')}")
    print(f"总文档数: {stats.get('document_count', 0)}")
    
    type_counts = stats.get('type_counts', {})
    if type_counts:
        print("\n文档类型分布:")
        for doc_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {doc_type}: {count} 条")
    
    persist_dir = stats.get('persist_directory')
    if persist_dir:
        print(f"\n存储路径: {persist_dir}")
    
    print("="*50 + "\n")


def clear_database(vectorizer: TaogubaVectorizer, skip_confirm: bool = False):
    """清空向量数据库"""
    # 先显示当前统计
    get_stats(vectorizer)
    
    # 确认操作
    if not skip_confirm:
        print("⚠️  警告: 此操作将永久删除向量数据库中的所有数据！")
        response = input("确定要清空数据库吗？请输入 'yes' 确认: ")
        if response.lower() != 'yes':
            print("操作已取消")
            return False
    
    # 执行清空
    print("\n正在清空向量数据库...")
    result = vectorizer.clear_vector_store()
    
    if result:
        print("✅ 向量数据库已清空")
        return True
    else:
        print("❌ 清空失败")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="清空淘股吧向量数据库工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python clear_vector_db.py              # 交互式清空（默认配置）
  python clear_vector_db.py --stats      # 仅查看统计信息
  python clear_vector_db.py --yes        # 直接清空，跳过确认
  python clear_vector_db.py --collection taoguba_posts --persist ./vector_db
        """
    )
    
    parser.add_argument(
        "--collection",
        default="taoguba_posts",
        help="集合名称 (默认: taoguba_posts)"
    )
    
    parser.add_argument(
        "--persist",
        default="./vector_db",
        help="持久化目录路径 (默认: ./vector_db)"
    )
    
    parser.add_argument(
        "--stats",
        action="store_true",
        help="仅查看统计信息，不清空数据库"
    )
    
    parser.add_argument(
        "--yes",
        action="store_true",
        help="跳过确认直接清空"
    )
    
    args = parser.parse_args()
    
    # 创建向量存储
    print(f"正在连接向量数据库...")
    print(f"  集合: {args.collection}")
    print(f"  路径: {args.persist}")
    
    try:
        vector_store = VectorStore(
            collection_name=args.collection,
            persist_directory=args.persist,
            use_chroma=True
        )
        vectorizer = TaogubaVectorizer(vector_store)
        
        if args.stats:
            # 仅查看统计
            get_stats(vectorizer)
        else:
            # 清空数据库
            success = clear_database(vectorizer, skip_confirm=args.yes)
            sys.exit(0 if success else 1)
            
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
