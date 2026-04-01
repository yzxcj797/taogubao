"""
博主人格 Agent 模块

通过 System Prompt 直接注入人格，模拟博主的思维方式和表达习惯
人格配置目录: src/agents/personas/（每个博主一个 .md 文件，文件名即博主名）
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime
from pathlib import Path

from loguru import logger

from src.agents.base_agent import BaseAgent, AgentConfig, AgentResponse


# 人格配置目录（与本文件同目录下的 personas/）
_PERSONAS_DIR = Path(__file__).parent / "personas"


def _load_personas() -> Dict[str, str]:
    """从 personas/ 目录加载所有博主人格 prompt（每个 .md 文件 = 一个博主）"""
    if not _PERSONAS_DIR.is_dir():
        logger.warning(f"Personas directory not found: {_PERSONAS_DIR}")
        return {}
    personas: Dict[str, str] = {}
    try:
        for md_file in sorted(_PERSONAS_DIR.glob("*.md")):
            blogger_name = md_file.stem  # 文件名去掉 .md 即博主名
            content = md_file.read_text(encoding="utf-8").strip()
            if content:
                personas[blogger_name] = content
        logger.info(f"Loaded {len(personas)} blogger personas from {_PERSONAS_DIR}/")
    except Exception as e:
        logger.error(f"Failed to load personas: {e}")
    return personas


@dataclass
class BloggerPersona:
    """博主人格数据"""
    username: str
    system_prompt: str  # 完整的 system prompt


class BloggerAgent(BaseAgent):
    """
    博主人格 Agent
    
    通过 System Prompt 直接注入人格特征，无需依赖向量数据库。
    人格 prompt 从 personas/ 目录下的 .md 文件加载。
    """
    
    # 从配置文件加载的人格 prompt（类变量，首次使用时加载）
    _PERSONA_CACHE: Optional[Dict[str, str]] = None
    
    @classmethod
    def get_persona_prompts(cls) -> Dict[str, str]:
        """获取所有博主人格 prompt（带缓存）"""
        if cls._PERSONA_CACHE is None:
            cls._PERSONA_CACHE = _load_personas()
        return cls._PERSONA_CACHE
    
    @classmethod
    def reload_personas(cls):
        """强制重新加载人格配置（修改 personas/ 目录下的 .md 文件后调用）"""
        cls._PERSONA_CACHE = _load_personas()
    
    def __init__(
        self,
        blogger_name: str,
        config: Optional[AgentConfig] = None,
        persona: Optional[BloggerPersona] = None
    ):
        """
        初始化博主人格 Agent
        
        Args:
            blogger_name: 博主用户名
            config: Agent 配置
            persona: 预设的人格数据，None 则从 personas.json 加载
        """
        self.blogger_name = blogger_name
        
        # 如果未提供配置，创建默认配置
        if config is None:
            config = AgentConfig(
                name=f"BloggerAgent-{blogger_name}",
                description=f"模拟博主 '{blogger_name}' 的人格 Agent",
                enable_memory=True,
                max_tokens=800,  # 博主发言通常 300-600 字足够
            )
        else:
            config.name = f"BloggerAgent-{blogger_name}"
        
        super().__init__(config)
        
        # 加载或创建人格
        self.persona = persona or self._create_persona(blogger_name)
        
        logger.info(f"BloggerAgent '{blogger_name}' initialized")
    
    def _create_persona(self, blogger_name: str) -> BloggerPersona:
        """
        创建博主人格
        
        优先从 personas/ 目录加载，否则使用默认 prompt
        """
        prompts = self.get_persona_prompts()
        if blogger_name in prompts:
            return BloggerPersona(
                username=blogger_name,
                system_prompt=prompts[blogger_name]
            )
        else:
            logger.warning(f"No persona found for '{blogger_name}' in personas/ directory, using default")
            default_prompt = f"""你是淘股吧博主 "{blogger_name}" 的数字人格。

【角色要求】
1. 在讨论中，你应该以 "{blogger_name}" 的身份发言
2. 保持对股票市场的关注和热情
3. 展现你的个性特点

【当前任务】
参与投资讨论，分享你的观点和分析。"""
            return BloggerPersona(
                username=blogger_name,
                system_prompt=default_prompt
            )
    
    def _build_system_prompt(self) -> str:
        """
        构建系统提示词
        
        直接返回预定义的完整 system prompt
        """
        return self.persona.system_prompt
    
    def _pre_process(self, user_input: str) -> str:
        """
        预处理用户输入
        """
        return user_input
    
    def _post_process(self, llm_output: str) -> AgentResponse:
        """后处理模型输出"""
        return AgentResponse(
            content=llm_output,
            metadata={
                "blogger_name": self.blogger_name,
                "timestamp": datetime.now().isoformat()
            }
        )
    
    def get_persona_description(self) -> str:
        """获取人格描述"""
        return f"""博主: {self.persona.username}
System Prompt 长度: {len(self.persona.system_prompt)} 字符"""
    
    def discuss(self, topic: str, context: Optional[str] = None) -> str:
        """
        参与讨论
        
        Args:
            topic: 讨论主题或完整提示
            context: 可选的上下文信息
            
        Returns:
            博主的观点
        """
        # 如果 context 为 None，说明传入的是完整的讨论提示（来自 BloggerPanel）
        if context is None:
            return self.chat(topic)
        
        # 否则按原来的方式构建提示
        prompt = f"""讨论主题: {topic}

背景信息:
{context}

请分享你的观点和分析。"""
        
        return self.chat(prompt)
    
    def analyze_stock(self, stock_name: str, market_context: Optional[str] = None) -> str:
        """
        分析特定股票
        
        Args:
            stock_name: 股票名称或代码
            market_context: 市场背景
            
        Returns:
            分析观点
        """
        prompt = f"""请分析股票: {stock_name}

{market_context if market_context else ""}

请给出你的分析观点，包括：
1. 对该股票的基本判断
2. 操作建议
3. 风险提示"""
        
        return self.chat(prompt)
    
    def update_system_prompt(self, new_prompt: str):
        """
        更新 System Prompt
        
        Args:
            new_prompt: 新的完整 system prompt
        """
        self.persona.system_prompt = new_prompt
        logger.info(f"Updated system prompt for {self.blogger_name}")
