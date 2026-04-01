"""
博主讨论组
支持多个博主人格 Agent 进行讨论
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from loguru import logger
from tqdm import tqdm

from src.agents.blogger_agent import BloggerAgent


@dataclass
class DiscussionRound:
    """讨论轮次记录"""
    round_num: int
    speaker: str
    content: str
    topic: str


class BloggerPanel:
    """
    博主讨论组
    
    管理多个博主人格 Agent，组织他们进行讨论
    """
    
    def __init__(self):
        """初始化讨论组"""
        self.agents: List[BloggerAgent] = []
        self.discussion_history: List[DiscussionRound] = []
        logger.info("BloggerPanel initialized")
    
    def add_blogger(self, agent: BloggerAgent):
        """
        添加博主到讨论组
        
        Args:
            agent: BloggerAgent 实例
        """
        self.agents.append(agent)
        logger.info(f"Added blogger '{agent.blogger_name}' to panel")
    
    def remove_blogger(self, blogger_name: str):
        """
        从讨论组移除博主
        
        Args:
            blogger_name: 博主名称
        """
        self.agents = [a for a in self.agents if a.blogger_name != blogger_name]
        logger.info(f"Removed blogger '{blogger_name}' from panel")
    
    def get_blogger_names(self) -> List[str]:
        """获取讨论组中所有博主名称"""
        return [a.blogger_name for a in self.agents]
    
    def discuss(
        self, 
        topic: str, 
        context: str = "", 
        rounds: int = 1,
        verbose: bool = True,
        progress_callback: Optional[callable] = None
    ) -> List[DiscussionRound]:
        """
        组织讨论
        
        Args:
            topic: 讨论主题
            context: 背景信息
            rounds: 讨论轮数
            verbose: 是否打印讨论过程
            progress_callback: 进度回调函数，签名为 callback(current: int, total: int, blogger_name: str)
            
        Returns:
            讨论记录列表
        """
        if not self.agents:
            logger.warning("No agents in panel, cannot start discussion")
            return []
        
        discussion = []
        
        if verbose:
            print(f"\n开始讨论: {topic}")
            if context:
                print(f"背景: {context[:200]}...")
            print(f"参与博主: {', '.join(self.get_blogger_names())}")
            print("-" * 70)
        
        logger.info(f"讨论主题: {topic[:100]}...")
        logger.info(f"参与博主: {', '.join(self.get_blogger_names())} ({len(self.agents)}人)")
        logger.info(f"讨论轮数: {rounds}")
        
        # 计算总发言次数，用于进度条
        total_turns = rounds * len(self.agents)
        current_turn = 0

        # 使用 tqdm 进度条（仅在终端显示）
        pbar = tqdm(
            total=total_turns, 
            desc="博主讨论进度",
            unit="人",
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
            disable=progress_callback is not None  # 如果有回调函数，禁用 tqdm（避免重复）
        )

        for round_num in range(1, rounds + 1):
            logger.info(f"--- 第 {round_num}/{rounds} 轮讨论 ---")

            for agent in self.agents:
                current_turn += 1
                blogger_name = agent.blogger_name
                logger.info(f"[第{round_num}轮] {blogger_name} 正在发言... ({len(self.agents)}人本轮)")
                
                # 更新进度条描述
                if not pbar.disable:
                    pbar.set_description(f"博主讨论进度 [{blogger_name}发言中]")
                
                # 调用进度回调
                if progress_callback:
                    progress_callback(current_turn, total_turns, blogger_name)

                if verbose:
                    print(f"\n{'='*70}")
                    print(f"【第 {round_num} 轮讨论】")
                    print(f"{'='*70}")
                    print(f"\n{'─'*70}")
                    print(f"🎤 {blogger_name} 正在发言...")
                    print(f"{'─'*70}")
                
                # 将历史讨论记录注入到该博主的 memory 中，
                # 这样 _build_messages() 会自动把之前的对话放入 messages 列表
                self._inject_discussion_memory(agent, discussion)
                
                # 构建提示，包含之前所有博主的完整讨论内容
                prompt = self._build_discussion_prompt(
                    agent, topic, context, discussion, round_num
                )
                
                # 获取回应
                response = agent.discuss(prompt)
                
                # 记录
                round_record = DiscussionRound(
                    round_num=round_num,
                    speaker=agent.blogger_name,
                    content=response,
                    topic=topic
                )
                discussion.append(round_record)
                self.discussion_history.append(round_record)
                
                logger.info(f"[第{round_num}轮] {blogger_name} 发言完成 ({len(response)}字)")
                
                # 更新进度条
                if not pbar.disable:
                    pbar.update(1)
                
                if verbose:
                    print(f"\n【{agent.blogger_name}】")
                    print(response)
        
        if not pbar.disable:
            pbar.close()
        
        if verbose:
            print("\n" + "=" * 70)
            print("讨论结束")
        
        return discussion
    
    def _inject_discussion_memory(self, agent, discussion: List[DiscussionRound]):
        """
        将历史讨论记录注入到博主 Agent 的 memory 中，
        使得 _build_messages() 会把之前所有人的发言作为对话历史发送给 LLM。
        
        只追加本轮之前尚未注入的记录，避免重复。
        """
        from src.agents.base_agent import Message
        
        # 找出该 agent 的 memory 中已有的对话条数
        existing_count = len(agent.memory)
        new_records = discussion[existing_count:]
        
        for record in new_records:
            agent.memory.append(Message(
                role="assistant" if record.speaker == agent.blogger_name else "user",
                content=f"[{record.speaker}·第{record.round_num}轮]\n{record.content}"
            ))
    
    def _build_discussion_prompt(
        self,
        agent: BloggerAgent,
        topic: str,
        context: str,
        previous_discussion: List[DiscussionRound],
        current_round: int
    ) -> str:
        """
        构建讨论提示
        
        包含主题、背景、之前的讨论内容
        """
        prompt_parts = []
        
        # 主题和背景
        prompt_parts.append(f"讨论主题: {topic}")
        if context:
            prompt_parts.append(f"背景信息: {context}")
        
        # 构建其他博主的发言历史（完整的、未截断的内容）
        other_speakers_content = []
        for record in previous_discussion:
            # 包含：1) 之前所有轮次的内容 2) 当前轮次中其他博主的发言
            if record.round_num < current_round or (
                record.round_num == current_round and record.speaker != agent.blogger_name
            ):
                other_speakers_content.append(record)
        
        if other_speakers_content:
            prompt_parts.append("\n" + "="*50)
            prompt_parts.append("【讨论历史 - 请认真阅读并回应其他人的观点】")
            prompt_parts.append("="*50)
            
            # 优化：限制每个历史记录的长度，避免 prompt 过长
            MAX_HISTORY_LENGTH = 500  # 每个博主的历史发言最多 500 字
            
            for record in other_speakers_content:
                content_preview = record.content[:MAX_HISTORY_LENGTH]
                if len(record.content) > MAX_HISTORY_LENGTH:
                    content_preview += "..."
                prompt_parts.append(f"\n[{record.speaker}] 在第{record.round_num}轮说：")
                prompt_parts.append(content_preview)
            
            prompt_parts.append("\n" + "="*50)
            prompt_parts.append("【你的任务】")
            prompt_parts.append(f"你是 {agent.blogger_name}，请基于以上讨论发表你的观点：")
            prompt_parts.append("1. 如果同意某人的观点，可以表示支持并补充你的看法")
            prompt_parts.append("2. 如果不同意，可以直接反驳并说明理由")
            prompt_parts.append("3. 避免简单重复已经说过的内容")
            prompt_parts.append("4. 保持你的人格特征和语言风格")
            prompt_parts.append("="*50 + "\n")
        else:
            prompt_parts.append(f"\n你是 {agent.blogger_name}，请发表你对这个主题的观点：")
        
        return "\n".join(prompt_parts)
    
    def get_summary(self) -> str:
        """
        获取讨论总结
        
        Returns:
            总结文本
        """
        if not self.discussion_history:
            return "暂无讨论记录"
        
        summary_parts = []
        summary_parts.append(f"讨论主题: {self.discussion_history[0].topic}")
        summary_parts.append(f"参与人数: {len(self.agents)}")
        summary_parts.append(f"总轮次: {max(r.round_num for r in self.discussion_history)}")
        summary_parts.append(f"总发言数: {len(self.discussion_history)}")
        summary_parts.append("")
        summary_parts.append("主要观点:")
        
        # 按博主分组
        blogger_views: Dict[str, List[str]] = {}
        for record in self.discussion_history:
            if record.speaker not in blogger_views:
                blogger_views[record.speaker] = []
            blogger_views[record.speaker].append(record.content[:50] + "...")
        
        for blogger, views in blogger_views.items():
            summary_parts.append(f"\n{blogger}:")
            for i, view in enumerate(views[:2], 1):  # 只显示前2个观点
                summary_parts.append(f"  {i}. {view}")
        
        return "\n".join(summary_parts)
    
    def clear_history(self):
        """清空讨论历史"""
        self.discussion_history.clear()
        logger.info("Discussion history cleared")
    
    def save_discussion(self, filepath: str):
        """
        保存讨论记录到文件
        
        Args:
            filepath: 文件路径
        """
        import json
        from pathlib import Path
        
        data = [
            {
                "round": r.round_num,
                "speaker": r.speaker,
                "content": r.content,
                "topic": r.topic
            }
            for r in self.discussion_history
        ]
        
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Discussion saved to {filepath}")
