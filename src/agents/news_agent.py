"""
实时资讯获取 Agent

负责搜集实时市场资讯，包括新闻、行情数据等
优先使用实时数据源，无实时数据时降级为读取本地 news_input 下的 txt 文件
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from loguru import logger

from src.agents.base_agent import BaseAgent, AgentConfig, AgentResponse
from src.agents.agent_state import AgentState

# 默认的本地资讯文件目录（项目根目录/output/news_input）
_DEFAULT_NEWS_INPUT_DIR = Path(__file__).parent.parent.parent / "output" / "news_input"


class NewsAgent(BaseAgent):
    """
    实时资讯获取 Agent
    
    职责：
    1. 搜集实时市场新闻
    2. 获取行情数据
    3. 整理市场摘要
    
    降级策略：
    当无法获取实时数据时，从 output/news_input/ 目录读取本地 txt 文件作为资讯来源
    """
    
    def __init__(self, config: Optional[AgentConfig] = None,
                 news_input_dir: Optional[str] = None):
        """
        初始化 NewsAgent
        
        Args:
            config: Agent 配置
            news_input_dir: 本地资讯文件目录，默认为 output/news_input/
        """
        self.news_input_dir = Path(news_input_dir) if news_input_dir else _DEFAULT_NEWS_INPUT_DIR
        
        if config is None:
            config = AgentConfig(
                name="NewsAgent",
                description="实时资讯获取 Agent，负责搜集市场新闻和行情数据",
                system_prompt="""你是专业的金融资讯分析师，擅长搜集和整理实时市场信息。

你的职责：
1. 搜集最新的市场新闻和公告
2. 关注宏观经济数据和政策变化
3. 追踪板块轮动和热点题材
4. 整理清晰、客观的市场摘要

输出要求：
- 提供结构化、条理清晰的资讯摘要
- 区分事实和观点
- 标注信息来源和时间
- 突出可能影响市场的关键信息

记住：你的任务是为后续的投资决策提供信息基础，保持客观中立。""",
                temperature=0.5,
                max_tokens=1200  # 资讯摘要通常 600-1000 字
            )
        super().__init__(config)
        logger.info(f"NewsAgent initialized (news_input_dir: {self.news_input_dir})")
    
    def _setup_tools(self):
        """设置工具"""
        pass
    
    def get_persona_description(self) -> str:
        """获取人格描述"""
        return "实时资讯获取 Agent - 负责搜集市场新闻和行情数据"
    
    def _load_local_news(self) -> Optional[str]:
        """
        降级策略：从本地 news_input 目录读取所有 txt 文件内容
        
        Returns:
            合并后的文本内容，如果目录不存在或为空则返回 None
        """
        if not self.news_input_dir.exists():
            logger.warning(f"Local news directory not found: {self.news_input_dir}")
            return None
        
        txt_files = sorted(self.news_input_dir.glob("*.txt"))
        if not txt_files:
            logger.warning(f"No txt files found in: {self.news_input_dir}")
            return None
        
        logger.info(f"Loading {len(txt_files)} local news files from {self.news_input_dir}")
        
        all_content = []
        for txt_file in txt_files:
            try:
                text = txt_file.read_text(encoding="utf-8")
                all_content.append(text)
                logger.debug(f"Loaded {txt_file.name}: {len(text)} chars")
            except Exception as e:
                logger.warning(f"Failed to read {txt_file.name}: {e}")
        
        if not all_content:
            return None
        
        merged = "\n\n".join(all_content)
        logger.info(f"Total local news content: {len(merged)} chars from {len(txt_files)} files")
        return merged
    
    def gather_news(self, query: str, state: AgentState) -> AgentState:
        """
        搜集资讯
        
        降级策略：尝试读取本地资讯文件，如果存在则直接使用，否则让 LLM 生成摘要。
        
        Args:
            query: 用户查询/关注主题
            state: 共享状态对象
            
        Returns:
            更新后的状态对象
        """
        logger.info(f"NewsAgent gathering news for query: {query}")
        state.current_step = "news_gathering"
        state.query = query
        
        # 降级策略：尝试从本地读取资讯
        local_news = self._load_local_news()
        
        if local_news:
            logger.info(f"Using local news files as data source ({len(local_news)} chars, no truncation)")
            # 直接将完整原文作为 market_summary，不做摘要不截断
            state.market_summary = local_news
            state.raw_news_content = local_news
        else:
            logger.info("No local news available, using LLM generation (best-effort mode)")
            # 完全没有数据，让 LLM 尽力生成
            prompt = f"""请基于当前时间 ({datetime.now().strftime('%Y-%m-%d %H:%M')})，
针对以下主题搜集和整理市场资讯：

主题：{query}

请提供：
1. 最新市场动态（新闻、公告）
2. 相关板块/个股表现
3. 宏观经济影响因素
4. 市场情绪概况

请以结构化格式输出，便于后续分析使用。"""
            
            try:
                response = self.chat(prompt)
                state.market_summary = response
                logger.info("NewsAgent completed with LLM generation (no real data)")
            except Exception as e:
                logger.error(f"NewsAgent failed: {e}")
                state.market_summary = f"资讯获取失败: {str(e)}"
        
        return state
    
    def process(self, state: AgentState) -> AgentState:
        """
        处理入口（用于 LangGraph 节点）
        
        Args:
            state: 共享状态
            
        Returns:
            更新后的状态
        """
        return self.gather_news(state.query, state)
