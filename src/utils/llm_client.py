"""
LLM 客户端工具模块

提供统一的 LLM 客户端获取接口
"""

import os
from typing import Optional
from loguru import logger


def get_llm_client(provider: Optional[str] = None):
    """
    获取 LLM 客户端实例
    
    Args:
        provider: LLM 提供商 (zhipu, deepseek, openai, qwen, minimax, kimi, openrouter)
                  如果为 None，则从环境变量 DEFAULT_LLM_PROVIDER 读取，默认 zhipu
    
    Returns:
        LLM 客户端实例（OpenAI 兼容接口）
        
    Raises:
        ValueError: API Key 未配置
        ImportError: 缺少必要的包
    """
    from src.utils.config import get_config
    
    config = get_config()
    provider = (provider or config.default_llm_provider or "zhipu").lower()
    
    # 获取 API Key
    api_key = config.get_api_key(provider)
    if not api_key:
        raise ValueError(f"{provider.upper()}_API_KEY 未配置")
    
    # 根据提供商初始化客户端
    if provider == "zhipu":
        try:
            from zhipuai import ZhipuAI
            client = ZhipuAI(api_key=api_key)
            client.model = config.zhipu_model or "glm-4-flash"
            logger.info(f"Initialized ZhipuAI client with model {client.model}")
            return client
        except ImportError:
            # 降级为 OpenAI 兼容模式
            from openai import OpenAI
            client = OpenAI(
                api_key=api_key,
                base_url="https://open.bigmodel.cn/api/paas/v4"
            )
            client.model = config.zhipu_model or "glm-4-flash"
            logger.info(f"Initialized ZhipuAI client (OpenAI compatible) with model {client.model}")
            return client
    
    elif provider == "deepseek":
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        client.model = "deepseek-chat"
        logger.info(f"Initialized DeepSeek client with model {client.model}")
        return client
    
    elif provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        client.model = "gpt-4"
        logger.info(f"Initialized OpenAI client with model {client.model}")
        return client
    
    elif provider == "qwen":
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        client.model = config.qwen_model or "qwen-plus"
        logger.info(f"Initialized Qwen client with model {client.model}")
        return client
    
    elif provider == "minimax":
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.minimaxi.com/v1"
        )
        client.model = config.minimax_model or "MiniMax-M2.7"
        logger.info(f"Initialized MiniMax client with model {client.model}")
        return client
    
    elif provider == "kimi":
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.moonshot.cn/v1"
        )
        client.model = config.kimi_model or "kimi-k2.5"
        logger.info(f"Initialized Kimi client with model {client.model}")
        return client
    
    elif provider == "openrouter":
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1"
        )
        client.model = config.openrouter_model or "z-ai/glm-4.5-air:free"
        logger.info(f"Initialized OpenRouter client with model {client.model}")
        return client
    
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
