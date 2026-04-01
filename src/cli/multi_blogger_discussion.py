"""
多博主讨论脚本

支持多个博主进行讨论，使用 agents 模块中预定义的 prompt
"""

import sys
from pathlib import Path

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agents import BloggerAgent, BloggerPanel, AgentConfig


def create_blogger(blogger_name: str, llm_provider: str = None) -> BloggerAgent:
    """
    创建博主 Agent
    
    使用 agents/blogger_agent.py 中 PERSONA_PROMPTS 预定义的 prompt
    
    Args:
        blogger_name: 博主名称
        llm_provider: LLM 提供商，None 则使用 .env 中的 DEFAULT_LLM_PROVIDER
        
    Returns:
        BloggerAgent 实例
    """
    # 如果未指定 provider，使用 .env 中的默认配置
    if llm_provider is None:
        from src.utils.config import get_config
        config = get_config()
        llm_provider = config.default_llm_provider
    
    agent_config = AgentConfig(
        llm_provider=llm_provider,
        temperature=0.7,  # 降低温度以获得更连贯的讨论
        max_tokens=2048
    )
    
    agent = BloggerAgent(
        blogger_name=blogger_name,
        config=agent_config
    )
    
    return agent


def get_blogger_llm_info(agent: BloggerAgent) -> str:
    """获取博主使用的 LLM 信息"""
    provider = agent.config.llm_provider
    model = agent._llm_model if hasattr(agent, '_llm_model') else "unknown"
    return f"{provider.upper()} / {model}"


def run_multi_blogger_discussion():
    """
    运行多博主讨论
    
    示例： jl韭菜抄家 vs 延边刺客 vs A拉神灯
    """
    print("=" * 80)
    print("多博主讨论系统")
    print("=" * 80)
    print()
    
    # 创建讨论组
    panel = BloggerPanel()
    
    # ============ 配置博主 ============
    # 从 blogger_agent.py 的 PERSONA_PROMPTS 中加载已定义的博主
    
    available_bloggers = ["jl韭菜抄家", "延边刺客", "A拉神灯"]
    
    print("【可用博主】")
    for i, name in enumerate(available_bloggers, 1):
        print(f"  {i}. {name}")
    print()
    
    # 博主1: jl韭菜抄家
    print("【配置博主1】jl韭菜抄家")
    blogger1 = create_blogger("jl韭菜抄家")
    panel.add_blogger(blogger1)
    print(f"  ✓ 已添加: {blogger1.blogger_name}")
    print(f"    LLM: {get_blogger_llm_info(blogger1)}")
    print(f"    Prompt长度: {len(blogger1.persona.system_prompt)} 字符")
    print()
    
    # 博主2: 延边刺客
    print("【配置博主2】延边刺客")
    blogger2 = create_blogger("延边刺客")
    panel.add_blogger(blogger2)
    print(f"  ✓ 已添加: {blogger2.blogger_name}")
    print(f"    LLM: {get_blogger_llm_info(blogger2)}")
    print(f"    Prompt长度: {len(blogger2.persona.system_prompt)} 字符")
    print()
    
    # 博主3: A拉神灯
    print("【配置博主3】A拉神灯")
    blogger3 = create_blogger("A拉神灯")
    panel.add_blogger(blogger3)
    print(f"  ✓ 已添加: {blogger3.blogger_name}")
    print(f"    LLM: {get_blogger_llm_info(blogger3)}")
    print(f"    Prompt长度: {len(blogger3.persona.system_prompt)} 字符")
    print()
    
    # ============ 设置讨论主题 ============
    print("=" * 80)
    print("【讨论配置】")
    topic = input("请输入讨论问题: ").strip()
    while not topic:
        print("问题不能为空，请重新输入")
        topic = input("请输入讨论问题: ").strip()
    
    context = input("请输入背景信息 (可选，直接回车跳过): ").strip()
    
    rounds_input = input("讨论轮数 (默认: 1): ").strip()
    rounds = int(rounds_input) if rounds_input.isdigit() else 1
    
    print("=" * 80)
    print()
    print(f"【讨论开始】")
    print(f"问题: {topic}")
    if context:
        print(f"背景: {context}")
    print(f"轮数: {rounds}")
    print("-" * 80)
    print()
    
    # ============ 开始讨论 ============
    try:
        discussion = panel.discuss(topic, context, rounds=rounds, verbose=True)
        
        # 保存讨论记录
        save_option = input("\n是否保存讨论记录? (y/n, 默认: n): ").strip().lower()
        if save_option == 'y':
            from datetime import datetime
            filename = f"discussion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = PROJECT_ROOT / "output" / "view" / filename
            panel.save_discussion(str(filepath))
            print(f"讨论记录已保存: {filepath}")
        
    except Exception as e:
        print(f"\n讨论过程中出错: {e}")
        import traceback
        traceback.print_exc()


def run_custom_bloggers():
    """
    自定义博主组合讨论
    
    从预定义的博主中选择任意组合进行讨论
    """
    print("=" * 80)
    print("自定义博主讨论")
    print("=" * 80)
    print()
    
    panel = BloggerPanel()
    
    # 显示可用博主
    from src.agents.blogger_agent import BloggerAgent as BA
    available_bloggers = list(BA.PERSONA_PROMPTS.keys())
    
    print("【可用博主】")
    for i, name in enumerate(available_bloggers, 1):
        prompt_preview = BA.PERSONA_PROMPTS[name][:50] if name in BA.PERSONA_PROMPTS else "未定义"
        print(f"  {i}. {name}")
    print()
    
    # 选择博主
    selected = input("请输入要参与的博主编号（用逗号分隔，如: 1,2,3）: ").strip()
    if not selected:
        selected = "1,2,3"
    
    try:
        indices = [int(x.strip()) - 1 for x in selected.split(",")]
        selected_bloggers = [available_bloggers[i] for i in indices if 0 <= i < len(available_bloggers)]
    except:
        selected_bloggers = available_bloggers[:3]
    
    print()
    
    # 创建博主 Agent
    for i, blogger_name in enumerate(selected_bloggers, 1):
        print(f"【配置博主{i}】{blogger_name}")
        blogger = create_blogger(blogger_name)
        panel.add_blogger(blogger)
        print(f"  ✓ 已添加: {blogger.blogger_name}")
        print(f"    LLM: {get_blogger_llm_info(blogger)}")
        print(f"    Prompt长度: {len(blogger.persona.system_prompt)} 字符")
        print()
    
    # 设置讨论主题
    print("=" * 80)
    print("【讨论配置】")
    topic = input("请输入讨论问题: ").strip()
    while not topic:
        print("问题不能为空，请重新输入")
        topic = input("请输入讨论问题: ").strip()
    
    context = input("请输入背景信息 (可选，直接回车跳过): ").strip()
    
    rounds_input = input("讨论轮数 (默认: 1): ").strip()
    rounds = int(rounds_input) if rounds_input.isdigit() else 1
    
    print("=" * 80)
    print()
    print(f"【讨论开始】")
    print(f"问题: {topic}")
    if context:
        print(f"背景: {context}")
    print(f"轮数: {rounds}")
    print("-" * 80)
    print()
    
    # 开始讨论
    try:
        discussion = panel.discuss(topic, context, rounds=rounds, verbose=True)
        
        # 保存讨论记录
        save_option = input("\n是否保存讨论记录? (y/n, 默认: n): ").strip().lower()
        if save_option == 'y':
            from datetime import datetime
            filename = f"discussion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = PROJECT_ROOT / "output" / "view" / filename
            panel.save_discussion(str(filepath))
            print(f"讨论记录已保存: {filepath}")
        
    except Exception as e:
        print(f"\n讨论过程中出错: {e}")
        import traceback
        traceback.print_exc()


def main():
    """主函数"""
    print("=" * 80)
    print("多博主讨论系统")
    print("=" * 80)
    print()
    print("请选择模式:")
    print("  1. 固定组合讨论 (jl韭菜抄家 + 延边刺客 + A拉神灯)")
    print("  2. 自定义博主组合")
    print()
    
    choice = input("请输入选项 (1/2, 默认: 1): ").strip()
    
    if choice == "2":
        run_custom_bloggers()
    else:
        run_multi_blogger_discussion()


if __name__ == "__main__":
    main()
