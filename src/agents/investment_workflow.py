"""
投资分析工作流

基于 LangGraph 的多 Agent 协作系统

工作流：
NewsAgent -> BloggerPanel -> RiskAgent -> DecisionAgent
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Dict, List, Optional, TypedDict
from datetime import datetime
from loguru import logger

# 尝试导入 langgraph，如果未安装则用 None 占位
try:
    from langgraph.graph import StateGraph, START, END
    _HAS_LANGGRAPH = True
except ImportError:
    StateGraph = None
    START = None
    END = None
    _HAS_LANGGRAPH = False
    from loguru import logger as _lg
    _lg.warning("langgraph not installed, will use fallback sequential execution. Run: pip install langgraph")

from src.agents.agent_state import AgentState
from src.agents.news_agent import NewsAgent
from src.agents.risk_agent import RiskAgent
from src.agents.decision_agent import DecisionAgent
from src.agents.blogger_panel import BloggerPanel
from src.agents.blogger_agent import BloggerAgent


# ============================================================================
# Reducer 函数（LangGraph 节点返回值合并策略）
# ============================================================================

def _overwrite(a, b):
    """覆盖式 reducer：节点返回新值时直接替换旧值"""
    return b


# ============================================================================
# 状态序列化 / 反序列化（AgentState dataclass <-> dict）
# ============================================================================

def _state_to_dict(state: AgentState) -> Dict[str, Any]:
    """将 AgentState dataclass 序列化为可 JSON 化的字典"""
    return {
        "query": state.query,
        "final_answer": state.final_answer,
        "news_data": state.news_data,
        "market_summary": state.market_summary,
        "raw_news_content": state.raw_news_content,
        "blogger_discussions": state.blogger_discussions,
        "blogger_consensus": state.blogger_consensus,
        "risk_assessment": state.risk_assessment,
        "risk_level": state.risk_level,
        "risk_warnings": state.risk_warnings,
        "current_step": state.current_step,
        "start_time": state.start_time.isoformat() if state.start_time else None,
        "end_time": state.end_time.isoformat() if state.end_time else None,
    }


def _dict_to_state(d: Dict[str, Any]) -> AgentState:
    """将字典反序列化为 AgentState dataclass"""
    st = datetime.fromisoformat(d["start_time"]) if d.get("start_time") else None
    et = datetime.fromisoformat(d["end_time"]) if d.get("end_time") else None
    return AgentState(
        query=d.get("query", ""),
        final_answer=d.get("final_answer", ""),
        news_data=d.get("news_data", []),
        market_summary=d.get("market_summary", ""),
        raw_news_content=d.get("raw_news_content", ""),
        blogger_discussions=d.get("blogger_discussions", []),
        blogger_consensus=d.get("blogger_consensus", ""),
        risk_assessment=d.get("risk_assessment", ""),
        risk_level=d.get("risk_level", "medium"),
        risk_warnings=d.get("risk_warnings", []),
        current_step=d.get("current_step", ""),
        start_time=st or datetime.now(),
        end_time=et,
    )


# ============================================================================
# WorkflowState —— LangGraph 图的正式状态类型
# ============================================================================

class WorkflowState(TypedDict, total=False):
    """工作流状态类型（全部是 JSON-safe 的值）"""
    query: str
    final_answer: str
    news_data: Annotated[List[Dict[str, Any]], _overwrite]
    market_summary: str
    raw_news_content: str
    blogger_discussions: Annotated[List[Dict[str, Any]], _overwrite]
    blogger_consensus: str
    risk_assessment: str
    risk_level: str
    risk_warnings: Annotated[List[str], _overwrite]
    current_step: str
    start_time: str
    end_time: str
    messages: Annotated[List[Dict[str, Any]], _overwrite]


def _ws_from_agent(agent_state: AgentState) -> WorkflowState:
    """AgentState -> WorkflowState 初始值"""
    d = _state_to_dict(agent_state)
    d.setdefault("messages", [])
    return WorkflowState(**d)


def _ws_to_agent(ws: WorkflowState) -> AgentState:
    """WorkflowState -> AgentState（运行结束后的转换）"""
    return _dict_to_state(dict(ws))


def _ws_to_intermediate_agent(ws: WorkflowState) -> AgentState:
    """WorkflowState -> AgentState（中间节点用，不设置 end_time）"""
    d = dict(ws)
    d["end_time"] = None
    return _dict_to_state(d)


# ============================================================================
# InvestmentWorkflow
# ============================================================================

class InvestmentWorkflow:
    """
    投资分析工作流

    整合四个 Agent，通过 LangGraph 实现协作：
    1. NewsAgent: 搜集资讯
    2. BloggerPanel: 博主讨论
    3. RiskAgent: 风险评估
    4. DecisionAgent: 最终决策
    """

    def __init__(
        self,
        blogger_names: List[str] = None,
        discussion_rounds: int = 1,
        llm_provider: str = None,
        progress_callback: Optional[callable] = None
    ):
        self.blogger_names = blogger_names or ["jl韭菜抄家", "只核大学生"]
        self.discussion_rounds = discussion_rounds
        self.llm_provider = llm_provider
        self.progress_callback = progress_callback

        # 初始化 Agents（延迟到实际使用时，避免初始化失败阻断流程图构建）
        self._news_agent: Optional[NewsAgent] = None
        self._risk_agent: Optional[RiskAgent] = None
        self._decision_agent: Optional[DecisionAgent] = None

        # 尝试构建 LangGraph 工作流
        self.workflow = None
        if _HAS_LANGGRAPH:
            try:
                self.workflow = self._build_workflow()
                logger.info("InvestmentWorkflow initialized (langgraph=yes)")
            except Exception as e:
                logger.warning(f"LangGraph workflow build failed, falling back to sequential: {e}")
        else:
            logger.warning("langgraph not installed, using fallback sequential execution")

    # ---- 延迟初始化 Agent（首次调用时才创建，避免 import 时缺 SDK 报错） ----

    @property
    def news_agent(self) -> NewsAgent:
        if self._news_agent is None:
            self._news_agent = NewsAgent()
        return self._news_agent

    @property
    def risk_agent(self) -> RiskAgent:
        if self._risk_agent is None:
            self._risk_agent = RiskAgent()
        return self._risk_agent

    @property
    def decision_agent(self) -> DecisionAgent:
        if self._decision_agent is None:
            self._decision_agent = DecisionAgent()
        return self._decision_agent

    # ---- LangGraph 图构建 ----

    def _build_workflow(self):
        """构建 LangGraph 工作流"""
        workflow = StateGraph(WorkflowState)

        workflow.add_node("news_agent", self._news_agent_node)
        workflow.add_node("blogger_panel", self._blogger_panel_node)
        workflow.add_node("risk_agent", self._risk_agent_node)
        workflow.add_node("decision_agent", self._decision_agent_node)

        workflow.add_edge(START, "news_agent")
        workflow.add_edge("news_agent", "blogger_panel")
        workflow.add_edge("blogger_panel", "risk_agent")
        workflow.add_edge("risk_agent", "decision_agent")
        workflow.add_edge("decision_agent", END)

        return workflow.compile()

    # ---- 节点函数（接收 WorkflowState dict，返回部分更新 dict） ----

    def _news_agent_node(self, state: WorkflowState) -> dict:
        """NewsAgent 节点"""
        logger.info("=== Step 1: NewsAgent gathering information ===")
        agent_state = _ws_to_intermediate_agent(state)
        agent_state = self.news_agent.process(agent_state)
        logger.info("NewsAgent completed")
        return _state_to_dict(agent_state)

    def _blogger_panel_node(self, state: WorkflowState) -> dict:
        """BloggerPanel 节点"""
        logger.info("=== Step 2: BloggerPanel discussion ===")
        agent_state = _ws_to_intermediate_agent(state)
        agent_state.current_step = "blogger_discussion"

        # 创建博主讨论组
        panel = BloggerPanel()

        from src.agents.base_agent import AgentConfig
        for blogger_name in self.blogger_names:
            config = AgentConfig(
                llm_provider=self.llm_provider,
                temperature=0.8,
                max_tokens=2048
            )
            blogger = BloggerAgent(blogger_name=blogger_name, config=config)
            panel.add_blogger(blogger)

        news_content = agent_state.raw_news_content or agent_state.market_summary or ""
        topic = f"{agent_state.query}\n\n请基于以下市场资讯展开讨论。"

        try:
            discussions = panel.discuss(
                topic=topic,
                context=news_content,
                rounds=self.discussion_rounds,
                verbose=False,
                progress_callback=self.progress_callback
            )

            agent_state.blogger_discussions = [
                {"round": d.round_num, "speaker": d.speaker, "content": d.content}
                for d in discussions
            ]

            if discussions:
                last_round = max(d.round_num for d in discussions)
                final_discussions = [d for d in discussions if d.round_num == last_round]
                consensus_parts = [f"【{d.speaker}】\n{d.content[:300]}..." for d in final_discussions]
                agent_state.blogger_consensus = "\n\n".join(consensus_parts)

            logger.info(f"BloggerPanel completed with {len(discussions)} discussions")
        except Exception as e:
            logger.error(f"BloggerPanel discussion failed: {e}")
            agent_state.blogger_consensus = f"讨论过程出错: {str(e)}"

        return _state_to_dict(agent_state)

    def _risk_agent_node(self, state: WorkflowState) -> dict:
        """RiskAgent 节点"""
        logger.info("=== Step 3: RiskAgent assessing risk ===")
        agent_state = _ws_to_intermediate_agent(state)
        agent_state = self.risk_agent.process(agent_state)
        logger.info(f"RiskAgent completed, risk level: {agent_state.risk_level}")
        return _state_to_dict(agent_state)

    def _decision_agent_node(self, state: WorkflowState) -> dict:
        """DecisionAgent 节点"""
        logger.info("=== Step 4: DecisionAgent making decision ===")
        agent_state = _ws_to_intermediate_agent(state)
        agent_state = self.decision_agent.process(agent_state)
        logger.info("DecisionAgent completed")
        return _state_to_dict(agent_state)

    # ---- 公开接口 ----

    def run(self, query: str) -> AgentState:
        """
        运行工作流

        Args:
            query: 用户查询/投资问题

        Returns:
            最终的 AgentState
        """
        logger.info(f"Starting investment workflow for query: {query}")

        if self.workflow:
            # LangGraph 模式
            initial_state = _ws_from_agent(AgentState(query=query))
            try:
                final_state = self.workflow.invoke(initial_state)
                logger.info("Investment workflow completed successfully (langgraph)")
                return _ws_to_agent(final_state)
            except Exception as e:
                logger.error(f"Investment workflow failed: {e}")
                import traceback
                traceback.print_exc()
                error_state = AgentState(query=query, final_answer=f"工作流执行失败: {str(e)}")
                error_state.end_time = datetime.now()
                return error_state
        else:
            # 降级模式：顺序执行
            result = None
            for state in self.run_stream(query):
                result = state
            return result if result else AgentState(query=query, final_answer="工作流未产生结果")

    def run_stream(self, query: str):
        """
        流式运行工作流（逐步返回状态）

        Args:
            query: 用户查询/投资问题

        Yields:
            每个步骤的 AgentState
        """
        logger.info(f"Starting streaming workflow for query: {query}")

        agent_state = AgentState(query=query)
        messages: List[Dict[str, Any]] = []

        steps = [
            (self._news_agent_node, "资讯获取"),
            (self._blogger_panel_node, "博主讨论"),
            (self._risk_agent_node, "风险评估"),
            (self._decision_agent_node, "最终决策"),
        ]

        for step_func, step_desc in steps:
            logger.info(f"Executing step: {step_desc}")
            try:
                # 构造当前 WorkflowState
                ws = _ws_from_agent(agent_state)
                ws["messages"] = messages
                # 执行节点
                updates = step_func(ws)
                # 合并更新
                for k, v in updates.items():
                    if k == "messages":
                        messages = v
                    elif k == "start_time":
                        # 节点返回的是 isoformat 字符串，需转回 datetime
                        agent_state.start_time = datetime.fromisoformat(v) if isinstance(v, str) else v
                    elif k == "end_time":
                        agent_state.end_time = datetime.fromisoformat(v) if isinstance(v, str) else v
                    else:
                        setattr(agent_state, k, v)
                yield agent_state
            except Exception as e:
                logger.error(f"Step {step_desc} failed: {e}")
                agent_state.final_answer = f"步骤 {step_desc} 失败: {str(e)}"
                agent_state.end_time = datetime.now()
                yield agent_state
                break


# 便捷函数
def run_investment_analysis(
    query: str,
    blogger_names: List[str] = None,
    discussion_rounds: int = 1,
    llm_provider: str = None
) -> AgentState:
    """
    运行投资分析

    Args:
        query: 投资问题
        blogger_names: 博主列表
        discussion_rounds: 讨论轮数
        llm_provider: LLM 提供商

    Returns:
        分析结果状态
    """
    workflow = InvestmentWorkflow(
        blogger_names=blogger_names,
        discussion_rounds=discussion_rounds,
        llm_provider=llm_provider
    )
    return workflow.run(query)
