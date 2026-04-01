"""
投资分析工作流 CLI 入口

运行完整的四步投资分析流程：
  NewsAgent（资讯获取）-> BloggerPanel（博主讨论）-> RiskAgent（风险评估）-> DecisionAgent（最终决策）

使用流式模式逐步执行，实时展示每个步骤的输出。
结果保存到 output/analysis/ 目录。
"""

import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

from src.agents.investment_workflow import InvestmentWorkflow

PROJECT_ROOT = Path(__file__).parent.parent.parent

# 配置日志
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add(PROJECT_ROOT / "logs" / "workflow_{time}.log", rotation="10 MB", level="DEBUG")


def main():
    # ============ 配置区域 ============

    # 投资问题 / 查询主题
    QUERY = "明天必须买一个股票！请你们给出具体的股票名"

    # 参与讨论的博主（需要与 blogger_agent.py 中 PERSONA_PROMPTS 定义的名字一致）
    BLOGGER_NAMES = ["jl韭菜抄家", "延边刺客", "短狙作手", "只核大学生", "小宝"]

    # 讨论轮数
    DISCUSSION_ROUNDS = 1

    # LLM 提供商：zhipu / deepseek / openai / qwen / minimax / kimi
    # 默认从 .env 的 DEFAULT_LLM_PROVIDER 读取，也可手动覆盖
    from src.utils.config import get_config
    LLM_PROVIDER = get_config().default_llm_provider

    # 输出目录
    OUTPUT_DIR = PROJECT_ROOT / "output" / "analysis"

    # ==================================

    print("=" * 60)
    print("投资分析工作流")
    print("=" * 60)
    print(f"问题: {QUERY}")
    print(f"博主: {', '.join(BLOGGER_NAMES)}")
    print(f"讨论轮数: {DISCUSSION_ROUNDS}")
    print(f"LLM: {LLM_PROVIDER}")
    print("=" * 60)
    print()

    # 初始化工作流
    try:
        workflow = InvestmentWorkflow(
            blogger_names=BLOGGER_NAMES,
            discussion_rounds=DISCUSSION_ROUNDS,
            llm_provider=LLM_PROVIDER,
        )
    except ImportError as e:
        print(f"初始化失败: {e}")
        return

    # 逐步执行，实时展示
    step_labels = ["资讯获取", "博主讨论", "风险评估", "最终决策"]
    final_state = None

    for i, (label, state) in enumerate(zip(step_labels, workflow.run_stream(QUERY)), 1):
        print()
        print(f"{'=' * 60}")
        print(f"  Step {i}/4: {label} 完成")
        print(f"{'=' * 60}")
        print()

        if i == 1:
            # 资讯获取
            summary = state.market_summary or ""
            print(f"市场资讯摘要 (共 {len(summary)} 字符):")
            print("-" * 40)
            print(summary if summary else "（无摘要）")
            print()

        elif i == 2:
            # 博主讨论
            print(f"讨论记录 ({len(state.blogger_discussions)} 条):")
            print("-" * 40)
            for d in state.blogger_discussions:
                print(f"\n【第{d['round']}轮 · {d['speaker']}】")
                print(d["content"][:500])
            if state.blogger_consensus:
                print()
                print("博主共识:")
                print(state.blogger_consensus[:800])
            print()

        elif i == 3:
            # 风险评估
            print(f"风险等级: {state.risk_level.upper()}")
            print("-" * 40)
            print(state.risk_assessment[:1500] if state.risk_assessment else "（无评估）")
            if state.risk_warnings:
                print()
                print("风险警告:")
                for w in state.risk_warnings:
                    print(f"  - {w}")
            print()

        elif i == 4:
            # 最终决策
            print(state.final_answer[:2000] if state.final_answer else "（无决策）")
            print()
            final_state = state

    # 保存结果
    if final_state:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_query = final_state.query[:30].replace(" ", "_")
        md_filename = f"analysis_{safe_query}_{timestamp}.md"

        lines = []
        lines.append("# 投资分析报告")
        lines.append("")
        lines.append(f"**问题**: {final_state.query}")
        lines.append(f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**博主**: {', '.join(BLOGGER_NAMES)}")
        lines.append(f"**风险等级**: {final_state.risk_level.upper()}")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 市场资讯")
        lines.append("")
        lines.append(final_state.market_summary or "（无）")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 博主讨论记录")
        lines.append("")
        for d in final_state.blogger_discussions:
            lines.append(f"### 第{d['round']}轮 · {d['speaker']}")
            lines.append("")
            lines.append(d["content"])
            lines.append("")
        if final_state.blogger_consensus:
            lines.append("### 共识")
            lines.append("")
            lines.append(final_state.blogger_consensus)
            lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 风险评估")
        lines.append("")
        lines.append(final_state.risk_assessment or "（无）")
        lines.append("")
        if final_state.risk_warnings:
            lines.append("**风险警告:**")
            for w in final_state.risk_warnings:
                lines.append(f"- {w}")
            lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 最终决策")
        lines.append("")
        lines.append(final_state.final_answer or "（无）")
        lines.append("")

        md_path = OUTPUT_DIR / md_filename
        md_path.write_text("\n".join(lines), encoding="utf-8")
        print()
        print("=" * 60)
        print("分析完成!")
        print(f"报告已保存: {md_path}")
        print(f"日志目录: {PROJECT_ROOT / 'logs'}/")
        print("=" * 60)


if __name__ == "__main__":
    main()
