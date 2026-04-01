"""
风险管理 Agent

负责评估投资风险，识别潜在风险因素
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from loguru import logger

from src.agents.base_agent import BaseAgent, AgentConfig, AgentResponse
from src.agents.agent_state import AgentState


class RiskAgent(BaseAgent):
    """
    风险管理 Agent
    
    职责：
    1. 评估市场风险
    2. 识别潜在风险因素
    3. 提供风险等级和警告
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        if config is None:
            config = AgentConfig(
                name="RiskAgent",
                description="风险管理 Agent，负责评估投资风险",
                system_prompt="""你是专业的风险管理专家，擅长识别和评估投资风险。

你的职责：
1. 评估市场风险（系统性风险、流动性风险）
2. 识别个股/板块的特定风险
3. 分析宏观经济和政策风险
4. 评估情绪面和资金面风险

风险等级定义：
- LOW：风险可控，可以正常操作
- MEDIUM：存在不确定因素，需要谨慎
- HIGH：风险较高，建议减仓或观望

输出要求：
- 明确给出风险等级（LOW/MEDIUM/HIGH）
- 列出具体的风险因素
- 提供风险应对建议
- 保持客观理性，不夸大也不忽视风险

记住：你的任务是保护投资者本金，宁可过度谨慎也不要忽视风险。""",
                temperature=0.3,
                max_tokens=1200  # 风险评估输出通常 600-1000 字
            )
        super().__init__(config)
        logger.info("RiskAgent initialized")
    
    def _setup_tools(self):
        """设置工具"""
        pass
    
    def get_persona_description(self) -> str:
        """获取人格描述"""
        return "风险管理 Agent - 负责评估投资风险"
    
    def assess_risk(self, state: AgentState) -> AgentState:
        """
        评估风险
        
        Args:
            state: 共享状态对象
            
        Returns:
            更新后的状态对象
        """
        logger.info("RiskAgent assessing risk")
        state.current_step = "risk_assessment"
        
        # 构建上下文
        context = state.get_full_context()
        
        prompt = f"""基于以下市场信息和博主讨论，进行全面的风险评估：

{context}

请提供：
1. 总体风险等级（LOW/MEDIUM/HIGH）
2. 主要风险因素分析
3. 具体风险警告（列出3-5条）
4. 风险应对建议

输出格式：
风险等级: [LOW/MEDIUM/HIGH]

风险评估:
[详细分析]

风险警告:
1. [警告1]
2. [警告2]
3. [警告3]
...

应对建议:
[具体建议]"""
        
        try:
            response = self.chat(prompt)
            state.risk_assessment = response
            
            # 解析风险等级
            if "风险等级: HIGH" in response.upper() or "风险等级：HIGH" in response.upper():
                state.risk_level = "high"
            elif "风险等级: LOW" in response.upper() or "风险等级：LOW" in response.upper():
                state.risk_level = "low"
            else:
                state.risk_level = "medium"
            
            # 提取风险警告
            state.risk_warnings = self._extract_warnings(response)
            
            logger.info(f"RiskAgent completed assessment, risk level: {state.risk_level}")
        except Exception as e:
            logger.error(f"RiskAgent failed to assess risk: {e}")
            state.risk_assessment = f"风险评估失败: {str(e)}"
            state.risk_level = "high"  # 评估失败时默认为高风险
        
        return state
    
    def _extract_warnings(self, text: str) -> List[str]:
        """从响应中提取风险警告"""
        warnings = []
        lines = text.split('\n')
        in_warnings = False
        
        for line in lines:
            if '风险警告' in line or '警告:' in line:
                in_warnings = True
                continue
            if in_warnings:
                if line.strip().startswith(('1.', '2.', '3.', '4.', '5.', '-', '•')):
                    warning = line.strip().lstrip('12345.-• ').strip()
                    if warning:
                        warnings.append(warning)
                elif line.strip() == '' or '应对建议' in line or '建议:' in line:
                    break
        
        return warnings[:5]  # 最多返回5条警告
    
    def process(self, state: AgentState) -> AgentState:
        """
        处理入口（用于 LangGraph 节点）
        
        Args:
            state: 共享状态
            
        Returns:
            更新后的状态
        """
        return self.assess_risk(state)
