"""
RAG + LLM 系统
结合向量数据库检索和 LLM 生成能力
支持工具调用和自我反思
"""

import os
import json
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass
from loguru import logger

from src.vector.vector_store import VectorStore, TaogubaVectorizer, DocumentChunk
from src.utils.config import get_config, load_dotenv


@dataclass
class Tool:
    """工具定义"""
    name: str
    description: str
    parameters: Dict[str, Any]
    function: Callable
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }


@dataclass
class RAGResponse:
    """RAG 响应结构"""
    answer: str                    # LLM 生成的答案
    sources: List[DocumentChunk]   # 引用的来源
    context: str                   # 提供给 LLM 的上下文
    reasoning: str = ""            # 自我反思/推理过程
    tools_used: List[str] = None   # 使用的工具列表


@dataclass
class ChatMessage:
    """对话消息"""
    role: str      # "user" 或 "assistant"
    content: str   # 消息内容


class RAGSystem:
    """
    RAG 系统：检索增强生成（支持工具调用和自我反思）
    
    工作流程：
    1. 接收用户问题
    2. 【自我反思】分析问题类型和所需信息
    3. 【工具调用】动态获取数据库元信息
    4. 从向量数据库检索相关内容
    5. 【智能上下文】构建结构化的上下文
    6. 调用 LLM 生成回答
    
    支持对话历史记忆功能
    """
    
    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        llm_client=None,
        top_k: int = 10,
        max_context_length: int = 4000,
        max_history_rounds: int = 5,
        enable_memory: bool = True,
        enable_tools: bool = True,      # 是否启用工具调用
        enable_reflection: bool = True   # 是否启用自我反思
    ):
        """
        初始化 RAG 系统
        
        Args:
            vector_store: 向量数据库实例
            llm_client: LLM 客户端（OpenAI、DeepSeek等）
            top_k: 检索结果数量
            max_context_length: 最大上下文长度
            max_history_rounds: 最大保留对话轮数
            enable_memory: 是否启用对话记忆
            enable_tools: 是否启用工具调用
            enable_reflection: 是否启用自我反思
        """
        self.vector_store = vector_store or VectorStore()
        self.vectorizer = TaogubaVectorizer(self.vector_store)
        self.llm_client = llm_client
        self.top_k = top_k
        self.max_context_length = max_context_length
        self.max_history_rounds = max_history_rounds
        self.enable_memory = enable_memory
        self.enable_tools = enable_tools
        self.enable_reflection = enable_reflection
        
        # 对话历史
        self.chat_history: List[ChatMessage] = []
        
        # 注册工具
        self.tools: Dict[str, Tool] = {}
        if enable_tools:
            self._register_default_tools()
        
        logger.info(f"RAG System initialized (memory={'enabled' if enable_memory else 'disabled'}, "
                   f"tools={'enabled' if enable_tools else 'disabled'}, "
                   f"reflection={'enabled' if enable_reflection else 'disabled'})")
    
    def _register_default_tools(self):
        """注册默认工具"""
        self.register_tool(Tool(
            name="get_date_range",
            description="获取数据库中所有文档的日期范围，返回最早日期、最新日期和所有日期列表",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            },
            function=self._tool_get_date_range
        ))
        
        self.register_tool(Tool(
            name="get_author_list",
            description="获取数据库中所有作者列表及每个作者的文档数量",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            },
            function=self._tool_get_author_list
        ))
        
        self.register_tool(Tool(
            name="get_database_stats",
            description="获取数据库统计信息，包括文档总数、类型分布等",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            },
            function=self._tool_get_database_stats
        ))
        
        self.register_tool(Tool(
            name="search_by_date",
            description="按特定日期搜索内容，格式为YYYY-MM-DD",
            parameters={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "日期，格式YYYY-MM-DD"
                    }
                },
                "required": ["date"]
            },
            function=self._tool_search_by_date
        ))
    
    def register_tool(self, tool: Tool):
        """注册工具"""
        self.tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")
    
    def _tool_get_date_range(self) -> Dict[str, Any]:
        """工具：获取日期范围"""
        try:
            collection = self.vector_store._chroma_collection
            result = collection.get()
            metadatas = result.get("metadatas", []) or []
            
            dates = set()
            for m in metadatas:
                if m and "publish_time" in m:
                    date = m["publish_time"][:10] if len(m["publish_time"]) >= 10 else m["publish_time"]
                    if date:
                        dates.add(date)
            
            if dates:
                sorted_dates = sorted(dates)
                return {
                    "earliest_date": sorted_dates[0],
                    "latest_date": sorted_dates[-1],
                    "total_dates": len(sorted_dates),
                    "all_dates": sorted_dates[-30:]  # 最近30天
                }
            return {"error": "No date information found"}
        except Exception as e:
            return {"error": str(e)}
    
    def _tool_get_author_list(self) -> Dict[str, Any]:
        """工具：获取作者列表"""
        try:
            collection = self.vector_store._chroma_collection
            result = collection.get()
            metadatas = result.get("metadatas", []) or []
            
            author_counts = {}
            for m in metadatas:
                if m and "author_name" in m:
                    author = m["author_name"]
                    author_counts[author] = author_counts.get(author, 0) + 1
            
            # 按文档数量排序
            sorted_authors = sorted(author_counts.items(), key=lambda x: x[1], reverse=True)
            
            return {
                "total_authors": len(sorted_authors),
                "top_authors": sorted_authors[:20],  # 前20名
                "all_authors": [a[0] for a in sorted_authors]
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _tool_get_database_stats(self) -> Dict[str, Any]:
        """工具：获取数据库统计"""
        return self._get_db_stats()
    
    def _tool_search_by_date(self, date: str) -> Dict[str, Any]:
        """工具：按日期搜索"""
        try:
            collection = self.vector_store._chroma_collection
            result = collection.get()
            metadatas = result.get("metadatas", [])
            documents = result.get("documents", [])
            
            matching = []
            for i, m in enumerate(metadatas):
                if m and "publish_time" in m and date in m["publish_time"]:
                    matching.append({
                        "content": documents[i][:200] if i < len(documents) else "",
                        "author": m.get("author_name", "未知"),
                        "type": m.get("chunk_type", "unknown")
                    })
            
            return {
                "date": date,
                "match_count": len(matching),
                "results": matching[:10]  # 前10条
            }
        except Exception as e:
            return {"error": str(e)}
    
    def clear_history(self):
        """清空对话历史"""
        self.chat_history.clear()
        logger.info("Chat history cleared")
    
    def get_history(self) -> List[ChatMessage]:
        """获取当前对话历史"""
        return self.chat_history.copy()
    
    def _add_to_history(self, role: str, content: str):
        """添加消息到历史记录"""
        if not self.enable_memory:
            return
        
        self.chat_history.append(ChatMessage(role=role, content=content))
        
        # 限制历史记录长度（保留最近的几轮对话）
        # 每轮对话包含 user + assistant 两条消息
        max_messages = self.max_history_rounds * 2
        if len(self.chat_history) > max_messages:
            self.chat_history = self.chat_history[-max_messages:]
    
    def _build_messages_with_history(self, system_prompt: str, current_prompt: str) -> List[Dict[str, str]]:
        """构建包含历史记录的 messages"""
        messages = [{"role": "system", "content": system_prompt}]
        
        # 添加历史对话
        for msg in self.chat_history:
            messages.append({"role": msg.role, "content": msg.content})
        
        # 添加当前问题
        messages.append({"role": "user", "content": current_prompt})
        
        return messages
    
    def query(self, question: str, use_rag: bool = True) -> RAGResponse:
        """
        处理用户查询（支持工具调用和自我反思）
        
        Args:
            question: 用户问题
            use_rag: 是否使用 RAG 检索
            
        Returns:
            RAGResponse 包含答案、来源、推理过程
        """
        sources = []
        context = ""
        reasoning = ""
        tools_used = []
        
        if use_rag and self.llm_client:
            # === 阶段1: 自我反思 - 分析问题 ===
            if self.enable_reflection:
                logger.info("Phase 1: Self-reflection")
                reasoning = self._self_reflect(question)
            
            # === 阶段2: 工具调用 - 动态获取元信息 ===
            if self.enable_tools and self.tools:
                logger.info("Phase 2: Tool calling")
                tool_results = self._execute_tools_for_question(question, reasoning)
                tools_used = list(tool_results.keys())
            else:
                tool_results = {}
            
            # === 阶段3: 智能检索 ===
            logger.info("Phase 3: Context retrieval")
            # 对于时间/日期类问题，使用工具获取的最新日期进行检索
            search_query = question
            if "get_date_range" in tool_results and "error" not in tool_results["get_date_range"]:
                latest_date = tool_results["get_date_range"].get("latest_date")
                if latest_date and self._is_date_related_question(question):
                    # 对于日期相关问题，同时检索最新日期的内容
                    logger.info(f"Date-related question detected, will include content from {latest_date}")
            
            sources = self._retrieve_context(search_query)
            
            # 阶段3.5: 如果时间相关，额外获取最新日期的内容
            if "get_date_range" in tool_results and "error" not in tool_results["get_date_range"]:
                latest_date = tool_results["get_date_range"].get("latest_date")
                if latest_date:
                    latest_sources = self._retrieve_by_date(latest_date, top_k=3)
                    # 合并并去重
                    existing_ids = {s.metadata.get('doc_id', '') for s in sources}
                    for s in latest_sources:
                        if s.metadata.get('doc_id', '') not in existing_ids:
                            sources.append(s)
                    # 重新排序
                    sources.sort(key=lambda x: x.metadata.get('publish_time', ''), reverse=True)
                    sources = sources[:self.top_k]
            
            # === 阶段4: 智能上下文构建 ===
            context = self._build_smart_context(sources, tool_results, reasoning)
            
            # === 阶段5: 生成回答 ===
            answer = self._generate_with_llm(question, context, reasoning)
            
        elif use_rag:
            # 无 LLM，仅检索
            sources = self._retrieve_context(question)
            context = self._build_smart_context(sources, {}, "")
            answer = self._generate_simple_answer(question, sources)
        else:
            # 纯 LLM 模式
            answer = self._generate_with_llm(question, "", "")
        
        # 保存到对话历史
        self._add_to_history("user", question)
        self._add_to_history("assistant", answer)
        
        return RAGResponse(
            answer=answer,
            sources=sources,
            context=context,
            reasoning=reasoning,
            tools_used=tools_used
        )
    
    def _is_date_related_question(self, question: str) -> bool:
        """判断是否是时间/日期相关问题"""
        date_keywords = [
            "今天", "昨天", "明天", "日期", "时间", "几号", "什么时候",
            "最新", "最近", "当前", "现在", "today", "date", "latest"
        ]
        question_lower = question.lower()
        return any(kw in question_lower for kw in date_keywords)
    
    def _retrieve_by_date(self, date: str, top_k: int = 5) -> List[DocumentChunk]:
        """按日期检索内容"""
        try:
            collection = self.vector_store._chroma_collection
            result = collection.get()
            metadatas = result.get("metadatas", [])
            documents = result.get("documents", [])
            ids = result.get("ids", [])
            
            matching = []
            for i, m in enumerate(metadatas):
                if m and "publish_time" in m and date in m["publish_time"]:
                    chunk_id = ids[i] if i < len(ids) else f"date_search_{i}"
                    # 数据库存储用的是 "type" 字段
                    doc_type = m.get("type", "unknown")
                    chunk = DocumentChunk(
                        id=chunk_id,
                        content=documents[i] if i < len(documents) else "",
                        metadata={
                            **m,
                            'doc_id': chunk_id,
                            'doc_type': doc_type,  # 使用 "type" 字段
                            'similarity_score': 1.0  # 日期匹配给高分
                        }
                    )
                    matching.append(chunk)
            
            return matching[:top_k]
        except Exception as e:
            logger.warning(f"Failed to retrieve by date: {e}")
            return []
    
    def _self_reflect(self, question: str) -> str:
        """
        自我反思：分析问题类型和所需信息
        """
        reflect_prompt = f"""请分析以下用户问题，思考回答这个问题需要什么信息：

用户问题：{question}

请从以下角度分析：
1. 这个问题涉及什么主题？
2. 是否需要时间/日期信息？
3. 是否需要了解数据来源的范围？
4. 可能需要哪些工具来获取背景信息？
5. 回答时需要注意什么？

请用简洁的方式输出你的分析。"""
        
        try:
            reflection = self._call_llm_simple(reflect_prompt, max_tokens=500)
            logger.info(f"Self-reflection result: {reflection[:100]}...")
            return reflection
        except Exception as e:
            logger.warning(f"Self-reflection failed: {e}")
            return ""
    
    def _execute_tools_for_question(self, question: str, reflection: str) -> Dict[str, Any]:
        """
        根据问题和反思结果，决定调用哪些工具
        """
        results = {}
        
        # 构建工具选择提示
        tools_desc = "\n".join([
            f"- {name}: {tool.description}"
            for name, tool in self.tools.items()
        ])
        
        tool_select_prompt = f"""基于用户问题和你的分析，决定需要调用哪些工具来获取背景信息。

用户问题：{question}

你的分析：{reflection}

可用工具：
{tools_desc}

请输出需要调用的工具名称列表（JSON数组格式），如：["get_date_range", "get_author_list"]
如果不需要任何工具，输出：[]

只输出JSON数组，不要其他内容。"""
        
        try:
            # 让 LLM 决定调用哪些工具
            response = self._call_llm_simple(tool_select_prompt, max_tokens=200)
            
            # 解析工具列表
            try:
                tools_to_call = json.loads(response.strip())
                if not isinstance(tools_to_call, list):
                    tools_to_call = []
            except:
                # 如果解析失败，根据关键词判断
                tools_to_call = self._infer_tools_from_question(question, reflection)
            
            # 执行工具调用
            for tool_name in tools_to_call:
                if tool_name in self.tools:
                    logger.info(f"Executing tool: {tool_name}")
                    try:
                        result = self.tools[tool_name].function()
                        results[tool_name] = result
                    except Exception as e:
                        results[tool_name] = {"error": str(e)}
            
        except Exception as e:
            logger.warning(f"Tool selection failed: {e}")
        
        return results
    
    def _infer_tools_from_question(self, question: str, reflection: str) -> List[str]:
        """
        从问题和反思中推断需要调用的工具（备用方案）
        """
        question_lower = question.lower()
        tools = []
        
        # 时间相关问题
        time_keywords = ["今天", "昨天", "日期", "时间", "什么时候", "最近", "最新"]
        if any(kw in question_lower for kw in time_keywords):
            tools.append("get_date_range")
        
        # 作者相关问题
        author_keywords = ["作者", "谁", "博主", "发帖人"]
        if any(kw in question_lower for kw in author_keywords):
            tools.append("get_author_list")
        
        # 统计相关问题
        stat_keywords = ["多少", "数量", "统计", "总共", "几个"]
        if any(kw in question_lower for kw in stat_keywords):
            tools.append("get_database_stats")
        
        # 默认调用日期范围
        if not tools:
            tools.append("get_date_range")
        
        return tools
    
    def _call_llm_simple(self, prompt: str, max_tokens: int = 1000, temperature: float = 0.3) -> str:
        """简单调用 LLM"""
        if not self.llm_client:
            return ""
        
        try:
            if hasattr(self.llm_client, 'chat'):
                # 智谱 AI
                response = self.llm_client.chat.completions.create(
                    model=os.getenv("ZHIPU_MODEL", "glm-4-flash"),
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                return response.choices[0].message.content
            elif hasattr(self.llm_client, 'generate'):
                return self.llm_client.generate(prompt)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
        
        return ""
    

    
    def _retrieve_context(self, question: str) -> List[DocumentChunk]:
        """检索相关上下文"""
        # 搜索所有类型的内容
        results = self.vectorizer.search_all(question, top_k=self.top_k)
        
        # 合并所有结果并按相似度排序
        all_results = []
        for doc_type, docs in results.items():
            for doc in docs:
                doc.metadata['doc_type'] = doc_type
                all_results.append(doc)
        
        # 按相似度排序（如果有的话）
        all_results.sort(
            key=lambda x: x.metadata.get('similarity_score', 0),
            reverse=True
        )
        
        return all_results[:self.top_k]
    
    def _build_smart_context(
        self, 
        sources: List[DocumentChunk], 
        tool_results: Dict[str, Any],
        reasoning: str
    ) -> str:
        """
        智能上下文构建：整合检索结果、工具结果和反思
        """
        if not sources and not tool_results:
            return ""
        
        context_parts = []
        
        # === 1. 数据概览 ===
        context_parts.append("【数据概览】")
        
        # 从工具结果中提取概览信息
        if "get_database_stats" in tool_results:
            stats = tool_results["get_database_stats"]
            context_parts.append(f"- 文档总数: {stats.get('total_documents', '未知')}")
            context_parts.append(f"- 帖子数量: {stats.get('posts', '未知')}")
            context_parts.append(f"- 评论数量: {stats.get('comments', '未知')}")
        
        if "get_date_range" in tool_results:
            date_info = tool_results["get_date_range"]
            if "error" not in date_info:
                context_parts.append(f"- 时间跨度: {date_info.get('earliest_date', '未知')} 至 {date_info.get('latest_date', '未知')}")
                context_parts.append(f"- 数据天数: {date_info.get('total_dates', '未知')} 天")
        
        if "get_author_list" in tool_results:
            author_info = tool_results["get_author_list"]
            if "error" not in author_info:
                context_parts.append(f"- 涉及作者: {author_info.get('total_authors', '未知')} 人")
                top_authors = author_info.get('top_authors', [])[:5]
                if top_authors:
                    author_names = ", ".join([a[0] for a in top_authors])
                    context_parts.append(f"- 主要作者: {author_names}")
        
        context_parts.append("")
        
        # === 2. 分析提示 ===
        if reasoning:
            context_parts.append("【分析提示】")
            context_parts.append(reasoning)
            context_parts.append("")
        
        # === 3. 详细内容 ===
        if sources:
            context_parts.append("【详细内容】")
            context_parts.append("格式: 日期 | 类型 | 作者 | 内容")
            context_parts.append("-" * 50)
            
            current_length = sum(len(p) for p in context_parts)
            
            for i, source in enumerate(sources, 1):
                doc_type = source.metadata.get('doc_type', 'unknown')
                author = source.metadata.get('author_name', '未知')
                publish_time = source.metadata.get('publish_time', '')
                
                # 提取日期部分
                date_str = publish_time[:10] if publish_time and len(publish_time) >= 10 else (publish_time or "未知日期")
                
                # 构建格式化的内容
                if doc_type == 'post_title':
                    part = f"{i}. {date_str} | 标题 | {source.content}\n"
                elif doc_type in ('post_content', 'posts'):
                    part = f"{i}. {date_str} | 帖子 | {author} | {source.content}\n"
                elif doc_type == 'comment':
                    floor = source.metadata.get('floor_number', '')
                    part = f"{i}. {date_str} | 评论 | {author} {floor}楼 | {source.content}\n"
                else:
                    part = f"{i}. {date_str} | {doc_type} | {source.content}\n"
                
                # 检查是否超过最大长度
                if current_length + len(part) > self.max_context_length:
                    context_parts.append(f"\n... (已截断，共 {len(sources)} 条结果)")
                    break
                
                context_parts.append(part)
                current_length += len(part)
        
        return "\n".join(context_parts)
    
    def _generate_with_llm(self, question: str, context: str, reasoning: str = "") -> str:
        """使用 LLM 生成回答（支持自我反思）"""
        # 构建系统提示词
        system_prompt = self._build_system_prompt()
        
        # 构建用户提示词
        user_prompt = self._build_user_prompt(question, context, reasoning)
        
        try:
            # 智谱 AI (Zhipu AI) 调用
            if hasattr(self.llm_client, 'chat'):
                messages = self._build_messages_with_history(system_prompt, user_prompt)
                
                response = self.llm_client.chat.completions.create(
                    model=os.getenv("ZHIPU_MODEL", "glm-4-flash"),
                    messages=messages,
                    temperature=0.7,
                    max_tokens=2000
                )
                return response.choices[0].message.content
            
            elif hasattr(self.llm_client, 'generate'):
                full_prompt = f"{system_prompt}\n\n{user_prompt}"
                return self.llm_client.generate(full_prompt)
            
            else:
                return self._generate_simple_answer(question, [])
                
        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            return self._generate_simple_answer(question, [])
    
    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return """你是智能助手，可以分析股票数据并回答各类问题。

【重要 - 数据优先级】
1. 【数据概览】中的元信息（时间跨度、最新日期等）是权威的数据库统计信息，优先级最高
2. 【详细内容】是检索到的具体内容，可能存在时间上的偏向性
3. 当用户问"今天是几号"时，必须以【数据概览】中的"最新日期"为准，而不是从【详细内容】中推断

【回答原则】
1. 基于参考内容中的实际信息作答
2. 注意内容的时间顺序和上下文关系
3. 如果用户问"今天"，严格根据【数据概览】中的"最新日期"来判断
4. 如果信息不足，请明确说明"根据现有资料无法确定"
5. 不要编造参考内容中不存在的信息
6. 分析时要考虑数据的局限性和偏向性"""
    
    def _get_db_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        stats = self.vector_store.get_collection_stats()
        
        type_counts = stats.get("type_counts", {})
        total = stats.get("document_count", 0)
        
        # 分类统计
        post_titles = type_counts.get("post_title", 0)
        post_contents = type_counts.get("post_content", 0) + type_counts.get("posts", 0)
        comments = type_counts.get("comment", 0)
        posts_total = post_titles + post_contents
        
        return {
            "total_documents": total,
            "posts": posts_total,  # 帖子总数（标题+内容）
            "comments": comments,
            "post_titles": post_titles,
            "post_contents": post_contents,
            "collection_name": stats.get("collection_name", "unknown"),
            "storage_type": stats.get("storage_type", "unknown")
        }
    
    def _build_user_prompt(self, question: str, context: str, reasoning: str = "") -> str:
        """构建用户提示词"""
        if context:
            return f"""{context}

【用户问题】
{question}

请基于以上信息回答。注意利用数据概览中的元信息进行推理。"""
        else:
            return f"【用户问题】\n{question}\n\n（未检索到相关内容）"
    

    
    def _generate_simple_answer(self, question: str, sources: List[DocumentChunk]) -> str:
        """简单回答（无 LLM 时）"""
        if not sources:
            return "未找到相关内容。"
        
        answer_parts = [f"关于'{question}'，找到以下内容：\n"]
        
        for i, source in enumerate(sources[:3], 1):
            doc_type = source.metadata.get('doc_type', 'unknown')
            author = source.metadata.get('author_name', '未知')
            
            if doc_type == 'comment':
                floor = source.metadata.get('floor_number', 'N/A')
                answer_parts.append(f"{i}. [{author} {floor}楼] {source.content[:100]}...")
            else:
                answer_parts.append(f"{i}. [{author}] {source.content[:100]}...")
        
        return "\n".join(answer_parts)


# 便捷的 RAG 查询函数
def create_rag_system(
    collection_name: Optional[str] = None,
    persist_directory: Optional[str] = None,
    llm_api_key: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    llm_provider: Optional[str] = None,  # zhipu, deepseek, openai, qwen, minimax, kimi, openrouter
    use_env_config: bool = True,
    enable_memory: bool = True,
    max_history_rounds: int = 5,
    enable_tools: bool = True,
    enable_reflection: bool = True
) -> RAGSystem:
    """
    创建 RAG 系统
    
    Args:
        collection_name: 向量数据库集合名
        persist_directory: 向量数据库目录
        llm_api_key: LLM API 密钥
        llm_base_url: LLM API 基础 URL
        llm_provider: LLM 提供商 (zhipu, deepseek, openai)
        use_env_config: 是否从 .env 文件加载配置
        enable_memory: 是否启用对话记忆
        max_history_rounds: 最大保留对话轮数
        enable_tools: 是否启用工具调用
        enable_reflection: 是否启用自我反思
        
    Returns:
        RAGSystem 实例
    """
    # 加载 .env 文件配置
    if use_env_config:
        load_dotenv()
        config = get_config()
    else:
        config = None
    
    # 使用传入参数或环境变量
    collection_name = collection_name or (config.collection_name if config else "taoguba_posts")
    persist_directory = persist_directory or (config.vector_db_path if config else "./vector_db")
    llm_provider = llm_provider or (config.default_llm_provider if config else "zhipu")
    
    # 如果没有传入 API Key，尝试从配置获取
    if llm_api_key is None and config:
        llm_api_key = config.get_api_key(llm_provider)
    
    # 创建向量数据库
    vector_store = VectorStore(
        collection_name=collection_name,
        persist_directory=persist_directory,
        use_chroma=True
    )
    
    # 创建 LLM 客户端（如果提供了 API key）
    llm_client = None
    if llm_api_key:
        try:
            if llm_provider == "zhipu":
                # 智谱 AI
                try:
                    from zhipuai import ZhipuAI
                    llm_client = ZhipuAI(api_key=llm_api_key)
                    logger.info("Zhipu AI client initialized")
                except ImportError:
                    # 如果没有 zhipuai SDK，使用 OpenAI 兼容模式
                    from openai import OpenAI
                    llm_client = OpenAI(
                        api_key=llm_api_key,
                        base_url=llm_base_url or "https://open.bigmodel.cn/api/paas/v4"
                    )
                    logger.info("Zhipu AI client initialized (OpenAI compatible mode)")
            
            elif llm_provider == "deepseek":
                # DeepSeek
                from openai import OpenAI
                llm_client = OpenAI(
                    api_key=llm_api_key,
                    base_url=llm_base_url or "https://api.deepseek.com"
                )
                logger.info("DeepSeek client initialized")
            
            elif llm_provider == "openai":
                # OpenAI
                from openai import OpenAI
                llm_client = OpenAI(api_key=llm_api_key)
                logger.info("OpenAI client initialized")
            
            elif llm_provider == "qwen":
                # 通义千问
                from openai import OpenAI
                llm_client = OpenAI(
                    api_key=llm_api_key,
                    base_url=llm_base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
                )
                logger.info("Qwen client initialized")
            
            elif llm_provider == "minimax":
                # MiniMax
                from openai import OpenAI
                llm_client = OpenAI(
                    api_key=llm_api_key,
                    base_url=llm_base_url or "https://api.minimaxi.com/v1"
                )
                logger.info("MiniMax client initialized")
            
            elif llm_provider == "kimi":
                # Kimi (Moonshot)
                from openai import OpenAI
                llm_client = OpenAI(
                    api_key=llm_api_key,
                    base_url=llm_base_url or "https://api.moonshot.cn/v1"
                )
                logger.info("Kimi client initialized")
            
            elif llm_provider == "openrouter":
                # OpenRouter
                from openai import OpenAI
                llm_client = OpenAI(
                    api_key=llm_api_key,
                    base_url=llm_base_url or "https://openrouter.ai/api/v1"
                )
                logger.info("OpenRouter client initialized")
            
            else:
                logger.warning(f"Unknown LLM provider: {llm_provider}")
                
        except ImportError as e:
            logger.warning(f"Required package not installed: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize LLM client: {e}")
    
    return RAGSystem(
        vector_store=vector_store,
        llm_client=llm_client,
        enable_memory=enable_memory,
        max_history_rounds=max_history_rounds,
        enable_tools=enable_tools,
        enable_reflection=enable_reflection
    )


# 交互式 RAG 查询
def interactive_rag():
    """交互式 RAG 查询"""
    print("=" * 70)
    print("RAG + LLM 智能问答系统")
    print("=" * 70)
    
    # 检查是否需要 LLM
    use_llm = input("\n是否使用 LLM？(y/n，默认n): ").strip().lower() == 'y'
    
    llm_client = None
    llm_provider = "zhipu"  # 默认智谱 AI
    
    if use_llm:
        # 选择 LLM 提供商
        provider_choice = input("选择 LLM 提供商 (1-智谱AI, 2-DeepSeek, 3-OpenAI, 4-通义千问, 5-MiniMax, 6-Kimi，默认1): ").strip()
        if provider_choice == "2":
            llm_provider = "deepseek"
        elif provider_choice == "3":
            llm_provider = "openai"
        elif provider_choice == "4":
            llm_provider = "qwen"
        elif provider_choice == "5":
            llm_provider = "minimax"
        elif provider_choice == "6":
            llm_provider = "kimi"
        
        api_key = input(f"请输入 {llm_provider.upper()} API Key: ").strip()
        
        # 默认 base_url
        default_urls = {
            "zhipu": "https://open.bigmodel.cn/api/paas/v4",
            "deepseek": "https://api.deepseek.com",
            "openai": "https://api.openai.com/v1",
            "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "minimax": "https://api.minimaxi.com/v1",
            "kimi": "https://api.moonshot.cn/v1"
        }
        base_url = input(f"请输入 API Base URL (默认{default_urls.get(llm_provider, '')}): ").strip()
        
        if api_key:
            try:
                if llm_provider == "zhipu":
                    try:
                        from zhipuai import ZhipuAI
                        llm_client = ZhipuAI(api_key=api_key)
                    except ImportError:
                        from openai import OpenAI
                        llm_client = OpenAI(
                            api_key=api_key,
                            base_url=base_url or default_urls["zhipu"]
                        )
                else:
                    from openai import OpenAI
                    llm_client = OpenAI(
                        api_key=api_key,
                        base_url=base_url or default_urls.get(llm_provider, "")
                    )
                print(f"✅ {llm_provider.upper()} LLM 已连接")
            except Exception as e:
                print(f"❌ LLM 连接失败: {e}")
                print("将继续使用简单检索模式")
    
    # 创建 RAG 系统
    print("\n正在加载向量数据库...")
    rag = RAGSystem(llm_client=llm_client)
    
    print("\n" + "=" * 70)
    print("开始问答（输入 'quit' 退出）")
    print("=" * 70)
    
    while True:
        print()
        question = input("🤔 你的问题: ").strip()
        
        if question.lower() in ['quit', 'exit', '退出', 'q']:
            print("\n再见！")
            break
        
        if not question:
            continue
        
        print("\n🔍 检索中...")
        response = rag.query(question)
        
        print("\n" + "-" * 70)
        
        # 显示推理过程（如果启用）
        if response.reasoning:
            print("🤔 分析过程:")
            print(response.reasoning[:300] + "..." if len(response.reasoning) > 300 else response.reasoning)
            print("-" * 70)
        
        # 显示使用的工具
        if response.tools_used:
            print(f"🔧 使用工具: {', '.join(response.tools_used)}")
            print("-" * 70)
        
        print("💡 回答:")
        print(response.answer)
        print("-" * 70)
        
        # 显示来源
        if response.sources:
            print("\n📚 参考来源:")
            for i, source in enumerate(response.sources[:3], 1):
                author = source.metadata.get('author_name', '未知')
                doc_type = source.metadata.get('doc_type', '')
                
                if doc_type == 'comment':
                    floor = source.metadata.get('floor_number', '')
                    print(f"  {i}. [{author} {floor}楼]")
                else:
                    print(f"  {i}. [{author} {doc_type}]")


if __name__ == "__main__":
    interactive_rag()
