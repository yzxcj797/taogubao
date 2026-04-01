"""
RAG + LLM 对话系统

简洁的交互式问答，结合向量数据库检索和 LLM 生成

使用方法:
    python -m src.cli.rag_chat              # 启动交互式对话
    python -m src.cli.rag_chat --llm zhipu  # 指定 LLM 提供商
"""

import argparse
import sys
from pathlib import Path

from loguru import logger

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent

from src.rag import create_rag_system
from src.utils.config import get_config


def main():
    parser = argparse.ArgumentParser(description="RAG + LLM 对话系统")
    parser.add_argument("--llm", default="zhipu", help="LLM 提供商 (zhipu/deepseek/openai)")
    parser.add_argument("--no-rag", action="store_true", help="禁用向量检索")
    args = parser.parse_args()

    # 配置日志
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    # 加载配置
    config = get_config()
    
    # 检查 API Key
    if not config.check_api_key(args.llm):
        print(f"错误: 未找到 {args.llm} 的 API Key")
        print(f"请在 .env 文件中设置 {args.llm.upper()}_API_KEY")
        sys.exit(1)

    # 创建 RAG 系统
    print("正在初始化 RAG 系统...")
    rag = create_rag_system(
        llm_provider=args.llm,
        enable_memory=True,
        max_history_rounds=5
    )
    
    # 预热 embedding 模型
    if not args.no_rag:
        print("正在加载向量模型...")
        _ = rag.vector_store._get_default_embedding("预热")
    
    print("\n" + "=" * 60)
    print("🤖 RAG 对话系统")
    print("=" * 60)
    print(f"LLM: {args.llm}")
    print(f"向量检索: {'启用' if not args.no_rag else '禁用'}")
    print("输入 'quit' 或 'q' 退出，'clear' 清空记忆")
    print("=" * 60 + "\n")

    # 交互循环
    while True:
        try:
            question = input("🤔 你的问题: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n再见！")
            break

        if not question:
            continue

        if question.lower() in ['quit', 'exit', 'q', '退出']:
            print("\n👋 再见！")
            break

        if question.lower() == 'clear':
            rag.clear_history()
            print("\n🗑️ 对话历史已清空\n")
            continue

        # 查询
        try:
            if not args.no_rag:
                print("\n🔍 正在检索...")
            
            response = rag.query(question, use_rag=not args.no_rag)
            
            print(f"\n💡 回答:\n{response.answer}\n")
            
            # 显示来源
            if response.sources and not args.no_rag:
                print(f"📚 参考来源 ({len(response.sources)} 条):")
                for i, source in enumerate(response.sources[:3], 1):
                    author = source.metadata.get('author_name', '未知')
                    doc_type = source.metadata.get('doc_type', '')
                    time_str = source.metadata.get('publish_time', '')[:10] if source.metadata.get('publish_time') else '未知日期'
                    print(f"  {i}. [{time_str}] {doc_type} | {author}: {source.content[:50]}...")
                print()

        except Exception as e:
            print(f"\n❌ 错误: {e}\n")


if __name__ == "__main__":
    main()
