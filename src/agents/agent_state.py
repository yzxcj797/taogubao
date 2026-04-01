"""
AgentState - 共享状态管理

用于在 LangGraph 的各个 Agent 节点之间传递信息
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime


@dataclass
class AgentState:
    """
    共享 Agent 状态
    
    所有 Agent 通过此状态对象传递信息
    """
    # 输入/输出
    query: str = ""  # 用户原始查询
    final_answer: str = ""  # 最终决策结果
    
    # 资讯获取 Agent 的输出
    news_data: List[Dict[str, Any]] = field(default_factory=list)
    market_summary: str = ""
    raw_news_content: str = ""  # 本地采集的原始资讯全文
    
    # 博主讨论相关
    blogger_discussions: List[Dict[str, Any]] = field(default_factory=list)
    blogger_consensus: str = ""
    
    # 风险管理 Agent 的输出
    risk_assessment: str = ""
    risk_level: str = "medium"  # low, medium, high
    risk_warnings: List[str] = field(default_factory=list)
    
    # 元数据
    current_step: str = ""
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "query": self.query,
            "final_answer": self.final_answer,
            "news_data": self.news_data,
            "market_summary": self.market_summary,
            "blogger_discussions": self.blogger_discussions,
            "blogger_consensus": self.blogger_consensus,
            "risk_assessment": self.risk_assessment,
            "risk_level": self.risk_level,
            "risk_warnings": self.risk_warnings,
            "current_step": self.current_step,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }
    
    def get_full_context(self) -> str:
        """获取完整上下文信息，用于传递给后续 Agent"""
        context_parts = []

        if self.market_summary:
            context_parts.append("=== 市场资讯 ===")
            context_parts.append(self.market_summary)

        if self.blogger_discussions:
            context_parts.append("\n=== 博主讨论记录 ===")
            for d in self.blogger_discussions:
                context_parts.append(f"\n【第{d['round']}轮 · {d['speaker']}】")
                context_parts.append(d['content'])

        if self.blogger_consensus:
            context_parts.append("\n=== 博主讨论共识 ===")
            context_parts.append(self.blogger_consensus)

        if self.risk_assessment:
            context_parts.append("\n=== 风险评估 ===")
            context_parts.append(self.risk_assessment)
            context_parts.append(f"风险等级: {self.risk_level}")

        return "\n".join(context_parts)
