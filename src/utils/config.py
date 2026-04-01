"""
配置文件管理
支持从 .env 文件加载环境变量
"""

import os
from pathlib import Path
from typing import Optional
from loguru import logger


def load_env_file(env_path: Optional[str] = None) -> bool:
    """
    加载 .env 文件
    
    Args:
        env_path: .env 文件路径，None 则使用默认路径
        
    Returns:
        是否成功加载
    """
    if env_path is None:
        # 默认在项目根目录查找 .env (config.py 在 src/utils/ 下，需要向上两级)
        env_path = Path(__file__).parent.parent.parent / ".env"
    else:
        env_path = Path(env_path)

    if not env_path.exists():
        logger.warning(f".env file not found: {env_path}")
        return False

    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过空行和注释
                if not line or line.startswith('#'):
                    continue

                # 解析 KEY=VALUE
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()

                    # 去除引号
                    if (value.startswith('"') and value.endswith('"')) or \
                            (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]

                    # 设置环境变量（如果尚未设置）
                    if key and key not in os.environ:
                        os.environ[key] = value

        logger.info(f"Loaded environment variables from {env_path}")
        return True

    except Exception as e:
        logger.error(f"Error loading .env file: {e}")
        return False


class RAGConfig:
    """RAG 系统配置类"""

    def __init__(self):
        # 加载 .env 文件
        load_env_file()

    @property
    def zhipu_api_key(self) -> Optional[str]:
        """智谱 AI API Key"""
        return os.getenv("ZHIPU_API_KEY")

    @property
    def deepseek_api_key(self) -> Optional[str]:
        """DeepSeek API Key"""
        return os.getenv("DEEPSEEK_API_KEY")

    @property
    def openai_api_key(self) -> Optional[str]:
        """OpenAI API Key"""
        return os.getenv("OPENAI_API_KEY")

    @property
    def qwen_api_key(self) -> Optional[str]:
        """通义千问 API Key"""
        return os.getenv("QWEN_API_KEY")

    @property
    def deepseek_api_key(self) -> Optional[str]:
        """deepseek API Key"""
        return os.getenv("DEEPSEEK_API_KEY")

    @property
    def minimax_api_key(self) -> Optional[str]:
        """MiniMax API Key"""
        return os.getenv("MINIMAX_API_KEY")

    @property
    def kimi_api_key(self) -> Optional[str]:
        """Kimi (Moonshot) API Key"""
        return os.getenv("KIMI_API_KEY")

    @property
    def openrouter_api_key(self) -> Optional[str]:
        """OpenRouter API Key"""
        return os.getenv("OPENROUTER_API_KEY")

    @property
    def vector_db_path(self) -> str:
        """向量数据库路径"""
        return os.getenv("VECTOR_DB_PATH", "./vector_db")

    @property
    def collection_name(self) -> str:
        """集合名称"""
        return os.getenv("COLLECTION_NAME", "taoguba_posts")

    @property
    def top_k(self) -> int:
        """检索结果数量"""
        return int(os.getenv("TOP_K", "5"))

    @property
    def max_context_length(self) -> int:
        """最大上下文长度"""
        return int(os.getenv("MAX_CONTEXT_LENGTH", "3000"))

    @property
    def default_llm_provider(self) -> str:
        """默认 LLM 提供商"""
        return os.getenv("DEFAULT_LLM_PROVIDER", "zhipu")

    @property
    def zhipu_model(self) -> str:
        """智谱 AI 模型名称"""
        return os.getenv("ZHIPU_MODEL", "glm-4-flash")

    @property
    def qwen_model(self) -> str:
        """通义千问模型名称"""
        return os.getenv("QWEN_MODEL", "qwen-plus")

    @property
    def deepseek_model(self) -> str:
        """deepseek模型名称"""
        return os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    @property
    def minimax_model(self) -> str:
        """MiniMax 模型名称"""
        return os.getenv("MINIMAX_MODEL", "MiniMax-M2.7")

    @property
    def kimi_model(self) -> str:
        """Kimi (Moonshot) 模型名称"""
        return os.getenv("KIMI_MODEL", "kimi-k2.5")

    @property
    def openrouter_model(self) -> str:
        """OpenRouter 模型名称"""
        return os.getenv("OPENROUTER_MODEL", "z-ai/glm-4.5-air:free")

    def get_api_key(self, provider: Optional[str] = None) -> Optional[str]:
        """
        获取指定提供商的 API Key
        
        Args:
            provider: 提供商名称，None 则使用默认
            
        Returns:
            API Key 或 None
        """
        provider = provider or self.default_llm_provider

        if provider == "zhipu":
            return self.zhipu_api_key
        elif provider == "deepseek":
            return self.deepseek_api_key
        elif provider == "openai":
            return self.openai_api_key
        elif provider == "qwen":
            return self.qwen_api_key
        elif provider == "minimax":
            return self.minimax_api_key
        elif provider == "kimi":
            return self.kimi_api_key
        elif provider == "openrouter":
            return self.openrouter_api_key
        else:
            return None

    def check_api_key(self, provider: Optional[str] = None) -> bool:
        """
        检查指定提供商的 API Key 是否已配置
        
        Args:
            provider: 提供商名称，None 则使用默认
            
        Returns:
            是否已配置
        """
        return self.get_api_key(provider) is not None

    def print_config(self, hide_api_key: bool = True):
        """
        打印当前配置
        
        Args:
            hide_api_key: 是否隐藏 API Key
        """
        print("=" * 60)
        print("RAG 系统配置")
        print("=" * 60)

        # API Keys
        print("\nAPI Keys:")
        for provider in ["zhipu", "deepseek", "openai", "qwen", "minimax", "kimi", "openrouter"]:
            key = self.get_api_key(provider)
            if key:
                display_key = key[:8] + "..." + key[-4:] if hide_api_key and len(key) > 12 else key
                print(f"  {provider.upper()}: {display_key}")
            else:
                print(f"  {provider.upper()}: 未设置")

        # 其他配置
        print("\n其他配置:")
        print(f"  向量数据库路径: {self.vector_db_path}")
        print(f"  集合名称: {self.collection_name}")
        print(f"  默认 LLM: {self.default_llm_provider}")
        print(f"  智谱模型: {self.zhipu_model}")
        print(f"  通义千问模型: {self.qwen_model}")
        print(f"  deepseek模型: {self.deepseek_model}")
        print(f"  MiniMax模型: {self.minimax_model}")
        print(f"  Kimi模型: {self.kimi_model}")
        print(f"  OpenRouter模型: {self.openrouter_model}")
        print(f"  检索数量: {self.top_k}")
        print(f"  最大上下文: {self.max_context_length}")
        print("=" * 60)


# 全局配置实例
_config = None


def get_config() -> RAGConfig:
    """获取全局配置实例"""
    global _config
    if _config is None:
        _config = RAGConfig()
    return _config


# 便捷的函数
def load_dotenv(env_path: Optional[str] = None) -> bool:
    """加载 .env 文件"""
    return load_env_file(env_path)


def get_api_key(provider: Optional[str] = None) -> Optional[str]:
    """获取 API Key"""
    return get_config().get_api_key(provider)


if __name__ == "__main__":
    # 测试配置加载
    config = get_config()
    config.print_config()
