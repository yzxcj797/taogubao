"""
Agent 模块

提供基于 LLM 的 Agent 框架，支持：
- 基类 BaseAgent：可定制 LLM、记忆、工具
- 博主人格 Agent：通过向量数据库获取博主风格
- 博主讨论组 BloggerPanel：多 Agent 讨论
"""

from src.agents.base_agent import BaseAgent, AgentConfig, AgentResponse
from src.agents.blogger_agent import BloggerAgent, BloggerPersona
from src.agents.blogger_panel import BloggerPanel, DiscussionRound

__all__ = [
    'BaseAgent',
    'AgentConfig',
    'AgentResponse',
    'BloggerAgent',
    'BloggerPersona',
    'BloggerPanel',
    'DiscussionRound',
]
