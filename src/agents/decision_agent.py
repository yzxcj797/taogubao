"""
最终决策者 Agent

综合所有信息，做出最终投资决策
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from loguru import logger

from src.agents.base_agent import BaseAgent, AgentConfig, AgentResponse
from src.agents.agent_state import AgentState


class DecisionAgent(BaseAgent):
    """
    最终决策者 Agent
    
    职责：
    1. 综合分析所有信息
    2. 做出最终投资决策
    3. 提供明确的操作建议
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        if config is None:
            config = AgentConfig(
                name="DecisionAgent",
                description="最终决策者 Agent，负责做出投资决策",
                system_prompt="""你是资深的投资决策专家，拥有丰富的市场经验和决策能力。

你的职责：
1. 综合分析市场资讯、博主观点、风险评估
2. 做出明确的投资决策（买/卖/持有/观望）
3. 提供具体的操作建议（仓位、标的、时机）
4. 给出决策理由和依据

决策原则：
1. 风险控制优先 - 在风险较高时宁可错过也不冒险
2. 顺势而为 - 尊重市场趋势，不逆势操作
3. 独立思考 - 综合各方观点，形成独立判断
4. 明确果断 - 决策要清晰明确，不模棱两可

输出要求：
- 明确的决策结论（买入/卖出/持有/观望）
- 具体的操作建议（仓位比例、目标标的）
- 决策理由和逻辑
- 风险提示和注意事项

记住：你的决策将直接影响投资结果，务必谨慎负责。""",
                temperature=0.4,
                max_tokens=1200  # 最终决策输出通常 600-1000 字
            )
        super().__init__(config)
        logger.info("DecisionAgent initialized")
    
    def _setup_tools(self):
        """设置工具"""
        pass
    
    def get_persona_description(self) -> str:
        """获取人格描述"""
        return "最终决策者 Agent - 负责做出投资决策"
    
    def make_decision(self, state: AgentState) -> AgentState:
        """
        做出最终决策
        
        Args:
            state: 共享状态对象
            
        Returns:
            更新后的状态对象
        """
        logger.info("DecisionAgent making final decision")
        state.current_step = "decision_making"
        
        # 获取完整上下文
        context = state.get_full_context()
        
        prompt = f"""基于以下全面信息，做出最终投资决策：

原始问题：{state.query}

{context}

请提供：
1. 明确的决策结论（买入/卖出/持有/观望）
2. 具体的操作建议：
   - 仓位建议（如：3成仓位）
   - 关注标的（如有）
   - 操作时机
3. 详细的决策理由
4. 风险提示

输出格式：
【决策结论】
[买入/卖出/持有/观望]

【操作建议】
- 仓位：[建议]
- 标的：[如有]
- 时机：[建议]

【决策理由】
[详细分析]

【风险提示】
[注意事项]"""
        
        try:
            response = self.chat(prompt)
            state.final_answer = response
            state.end_time = datetime.now()
            logger.info("DecisionAgent completed decision making")
        except Exception as e:
            logger.error(f"DecisionAgent failed to make decision: {e}")
            state.final_answer = f"决策失败: {str(e)}"
            state.end_time = datetime.now()
        
        return state
    
    def process(self, state: AgentState) -> AgentState:
        """
        处理入口（用于 LangGraph 节点）
        
        Args:
            state: 共享状态
            
        Returns:
            更新后的状态
        """
        return self.make_decision(state)
