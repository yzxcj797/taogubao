"""
Agent 基类模块

提供可扩展的 Agent 框架，支持：
- 可定制的 LLM 后端（智谱、DeepSeek、OpenAI 等）
- 记忆管理（短期/长期记忆）
- 工具调用
- 多轮对话
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union
from datetime import datetime
from pathlib import Path
import sys

from loguru import logger

# 获取项目根目录并添加到路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import get_config, RAGConfig


@dataclass
class AgentConfig:
    """Agent 配置"""
    name: str = "BaseAgent"
    description: str = "基础 Agent"
    
    # LLM 配置
    llm_provider: Optional[str] = None  # None 表示使用 .env 中的 DEFAULT_LLM_PROVIDER
    llm_model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2048
    
    # 记忆配置
    enable_memory: bool = True
    max_memory_rounds: int = 10
    
    # 系统提示词
    system_prompt: str = "你是一个 helpful 的 AI 助手。"


@dataclass
class Message:
    """对话消息"""
    role: str  # system, user, assistant
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResponse:
    """Agent 响应"""
    content: str
    reasoning: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """
    Agent 基类
    
    子类应该重写：
    - _build_system_prompt(): 构建系统提示词
    - _pre_process(): 预处理用户输入
    - _post_process(): 后处理模型输出
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        """
        初始化 Agent
        
        Args:
            config: Agent 配置，None 则使用默认配置
        """
        self.config = config or AgentConfig()
        self.app_config: RAGConfig = get_config()
        
        # 对话历史
        self.memory: List[Message] = []
        
        # 工具注册表
        self.tools: Dict[str, Callable] = {}
        
        # LLM 客户端
        self._llm_client = None
        
        # 初始化
        self._llm_model = ""  # 占位，由 _init_llm() 填充
        self._init_llm()
        self._setup_tools()
        
        logger.info(f"Agent '{self.config.name}' initialized | provider={self.config.llm_provider} | model={self._llm_model}")
    
    def _init_llm(self):
        """初始化 LLM 客户端"""
        # 优先级：config.llm_provider > .env DEFAULT_LLM_PROVIDER > zhipu
        if self.config.llm_provider:
            provider = self.config.llm_provider.lower()
        else:
            provider = self.app_config.default_llm_provider.lower()
        
        if provider == "zhipu":
            self._init_zhipu()
        elif provider == "deepseek":
            self._init_deepseek()
        elif provider == "openai":
            self._init_openai()
        elif provider == "qwen":
            self._init_qwen()
        elif provider == "minimax":
            self._init_minimax()
        elif provider == "kimi":
            self._init_kimi()
        elif provider == "openrouter":
            self._init_openrouter()
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")
    
    def _init_zhipu(self):
        """初始化智谱 AI 客户端"""
        try:
            from zhipuai import ZhipuAI
            
            api_key = self.app_config.get_api_key("zhipu")
            if not api_key:
                raise ValueError("ZHIPU_API_KEY not found")
            
            self._llm_client = ZhipuAI(api_key=api_key)
            self._llm_model = self.config.llm_model or self.app_config.zhipu_model or "glm-4-flash"
            
        except ImportError:
            raise ImportError("zhipuai not installed. Run: pip install zhipuai")
    
    def _init_deepseek(self):
        """初始化 DeepSeek 客户端"""
        try:
            import openai
            
            api_key = self.app_config.get_api_key("deepseek")
            if not api_key:
                raise ValueError("DEEPSEEK_API_KEY not found")
            
            self._llm_client = openai.OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com"
            )
            self._llm_model = self.config.llm_model or self.app_config.deepseek_model or "deepseek-chat"
            
        except ImportError:
            raise ImportError("openai not installed. Run: pip install openai")
    
    def _init_openai(self):
        """初始化 OpenAI 客户端"""
        try:
            import openai
            
            api_key = self.app_config.get_api_key("openai")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found")
            
            self._llm_client = openai.OpenAI(api_key=api_key)
            self._llm_model = self.config.llm_model or "gpt-4"
            
        except ImportError:
            raise ImportError("openai not installed. Run: pip install openai")
    
    def _init_qwen(self):
        """初始化通义千问客户端（OpenAI 兼容接口）"""
        try:
            import openai
            
            api_key = self.app_config.get_api_key("qwen")
            if not api_key:
                raise ValueError("QWEN_API_KEY not found")
            
            self._llm_client = openai.OpenAI(
                api_key=api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
            self._llm_model = self.config.llm_model or self.app_config.qwen_model or "qwen-plus"
            
        except ImportError:
            raise ImportError("openai not installed. Run: pip install openai")
    
    def _init_minimax(self):
        """初始化 MiniMax 客户端（OpenAI 兼容接口）"""
        try:
            import openai
            
            api_key = self.app_config.get_api_key("minimax")
            if not api_key:
                raise ValueError("MINIMAX_API_KEY not found")
            
            self._llm_client = openai.OpenAI(
                api_key=api_key,
                base_url="https://api.minimaxi.com/v1"
            )
            self._llm_model = self.config.llm_model or self.app_config.minimax_model or "MiniMax-M2.7"
            
        except ImportError:
            raise ImportError("openai not installed. Run: pip install openai")
    
    def _init_kimi(self):
        """初始化 Kimi (Moonshot) 客户端（OpenAI 兼容接口）"""
        try:
            import openai
            
            api_key = self.app_config.get_api_key("kimi")
            if not api_key:
                raise ValueError("KIMI_API_KEY not found")
            
            self._llm_client = openai.OpenAI(
                api_key=api_key,
                base_url="https://api.moonshot.cn/v1"
            )
            self._llm_model = self.config.llm_model or self.app_config.kimi_model or "kimi-k2.5"
            
        except ImportError:
            raise ImportError("openai not installed. Run: pip install openai")
    
    def _init_openrouter(self):
        """初始化 OpenRouter 客户端（OpenAI 兼容接口）"""
        try:
            import openai
            
            api_key = self.app_config.get_api_key("openrouter")
            if not api_key:
                raise ValueError("OPENROUTER_API_KEY not found")
            
            self._llm_client = openai.OpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1"
            )
            self._llm_model = self.config.llm_model or self.app_config.openrouter_model or "z-ai/glm-4.5-air:free"
            
        except ImportError:
            raise ImportError("openai not installed. Run: pip install openai")
    
    def _setup_tools(self):
        """设置工具（子类可重写）"""
        pass
    
    def register_tool(self, name: str, func: Callable, description: str = ""):
        """
        注册工具
        
        Args:
            name: 工具名称
            func: 工具函数
            description: 工具描述
        """
        self.tools[name] = {
            "func": func,
            "description": description
        }
        logger.debug(f"Registered tool: {name}")
    
    def _build_system_prompt(self) -> str:
        """
        构建系统提示词
        
        子类可以重写此方法来自定义系统提示词
        """
        return self.config.system_prompt
    
    def _pre_process(self, user_input: str) -> str:
        """
        预处理用户输入
        
        子类可以重写此方法来实现输入转换
        """
        return user_input
    
    def _post_process(self, llm_output: str) -> AgentResponse:
        """
        后处理模型输出
        
        子类可以重写此方法来实现输出解析
        """
        return AgentResponse(content=llm_output)
    
    def _call_llm(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        调用 LLM
        
        Args:
            messages: 消息列表
            **kwargs: 额外的参数
            
        Returns:
            LLM 输出文本
        """
        provider = (self.config.llm_provider or "zhipu").lower()
        
        try:
            if provider == "zhipu":
                return self._call_zhipu(messages, **kwargs)
            elif provider in ["deepseek", "openai", "qwen", "minimax", "kimi", "openrouter"]:
                return self._call_openai_compatible(messages, **kwargs)
            else:
                raise ValueError(f"Unknown provider: {provider}")
                
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise
    
    def _call_zhipu(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """调用智谱 AI"""
        response = self._llm_client.chat.completions.create(
            model=self._llm_model,
            messages=messages,
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
        )
        return response.choices[0].message.content
    
    def _call_openai_compatible(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """调用 OpenAI 兼容接口"""
        response = self._llm_client.chat.completions.create(
            model=self._llm_model,
            messages=messages,
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
        )
        return response.choices[0].message.content
    
    def _build_messages(self, user_input: str) -> List[Dict[str, str]]:
        """
        构建消息列表
        
        Args:
            user_input: 用户输入
            
        Returns:
            消息列表
        """
        messages = []
        
        # 系统提示词
        system_prompt = self._build_system_prompt()
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # 历史记忆
        if self.config.enable_memory:
            for msg in self.memory[-self.config.max_memory_rounds:]:
                messages.append({"role": msg.role, "content": msg.content})
        
        # 当前用户输入
        messages.append({"role": "user", "content": user_input})
        
        return messages
    
    def think(self, user_input: str, **kwargs) -> AgentResponse:
        """
        处理用户输入并生成响应
        
        Args:
            user_input: 用户输入
            **kwargs: 额外的参数
            
        Returns:
            Agent 响应
        """
        # 预处理
        processed_input = self._pre_process(user_input)
        
        # 构建消息
        messages = self._build_messages(processed_input)
        
        # 调用 LLM
        logger.debug(f"Calling LLM with {len(messages)} messages")
        llm_output = self._call_llm(messages, **kwargs)
        
        # 后处理
        response = self._post_process(llm_output)
        
        # 更新记忆
        if self.config.enable_memory:
            self.memory.append(Message(role="user", content=user_input))
            self.memory.append(Message(role="assistant", content=response.content))
        
        return response
    
    def chat(self, user_input: str, **kwargs) -> str:
        """
        简化的对话接口，只返回文本
        
        Args:
            user_input: 用户输入
            **kwargs: 额外的参数
            
        Returns:
            响应文本
        """
        response = self.think(user_input, **kwargs)
        return response.content
    
    def clear_memory(self):
        """清空对话记忆"""
        self.memory.clear()
        logger.info("Memory cleared")
    
    def get_memory(self) -> List[Message]:
        """获取对话历史"""
        return self.memory.copy()
    
    @abstractmethod
    def get_persona_description(self) -> str:
        """
        获取人格描述
        
        子类必须实现此方法，返回 Agent 的人格描述
        """
        pass
