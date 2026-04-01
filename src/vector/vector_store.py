"""
向量数据库模块
支持将帖子和评论内容嵌入到向量数据库，用于RAG检索
"""

import os
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable, Union
from dataclasses import dataclass

from loguru import logger


@dataclass
class DocumentChunk:
    """文档块数据结构"""
    id: str                          # 唯一ID
    content: str                     # 文本内容
    metadata: Dict[str, Any]         # 元数据
    embedding: Optional[List[float]] = None  # 向量嵌入


class VectorStore:
    """
    向量数据库管理器
    支持ChromaDB和内存存储两种模式
    """
    
    def __init__(
        self,
        collection_name: str = "taoguba_posts",
        persist_directory: Optional[str] = None,
        embedding_function: Optional[Callable[[str], List[float]]] = None,
        use_chroma: bool = True
    ):
        """
        初始化向量数据库
        
        Args:
            collection_name: 集合名称
            persist_directory: 持久化目录，None则使用内存存储
            embedding_function: 嵌入函数，None则使用默认的sentence-transformers
            use_chroma: 是否使用ChromaDB，False则使用内存存储
        """
        self.collection_name = collection_name
        self.persist_directory = persist_directory or "./vector_db"
        self.embedding_function = embedding_function
        self.use_chroma = use_chroma
        
        # 内存存储模式
        self._memory_store: Dict[str, DocumentChunk] = {}
        
        # ChromaDB客户端
        self._chroma_client = None
        self._chroma_collection = None
        
        if use_chroma:
            self._init_chroma()
        
        logger.info(f"VectorStore initialized: collection={collection_name}, use_chroma={use_chroma}")
    
    def _init_chroma(self):
        """初始化ChromaDB"""
        try:
            import chromadb
            from chromadb.config import Settings
            
            # 创建持久化客户端
            self._chroma_client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=Settings(anonymized_telemetry=False)
            )
            
            # 获取或创建集合
            self._chroma_collection = self._chroma_client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            
            logger.info(f"ChromaDB initialized at {self.persist_directory}")
            
        except ImportError:
            logger.warning("chromadb not installed, falling back to memory storage")
            self.use_chroma = False
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            self.use_chroma = False
    
    # 类级别的模型缓存，所有实例共享
    _embedding_model_cache = None
    
    def _get_default_embedding(self, text: str) -> List[float]:
        """
        获取默认的文本嵌入
        使用sentence-transformers的all-MiniLM-L6-v2模型
        """
        try:
            from sentence_transformers import SentenceTransformer
            
            # 使用类级别的缓存，所有实例共享同一个模型
            if VectorStore._embedding_model_cache is None:
                logger.info("Loading sentence-transformers model...")
                VectorStore._embedding_model_cache = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            
            embedding = VectorStore._embedding_model_cache.encode(text, convert_to_numpy=True)
            return embedding.tolist()
            
        except ImportError:
            logger.error("sentence-transformers not installed. Please install: pip install sentence-transformers")
            raise
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise
    
    def _generate_embedding(self, text: str) -> List[float]:
        """生成文本嵌入向量"""
        if self.embedding_function:
            return self.embedding_function(text)
        return self._get_default_embedding(text)
    
    def _generate_id(self, content: str, prefix: str = "") -> str:
        """生成文档唯一ID"""
        hash_obj = hashlib.md5(content.encode('utf-8'))
        return f"{prefix}{hash_obj.hexdigest()[:16]}"
    
    def document_exists(self, doc_id: str) -> bool:
        """
        检查文档是否已存在
        
        Args:
            doc_id: 文档ID
            
        Returns:
            是否存在
        """
        if self.use_chroma and self._chroma_collection:
            try:
                result = self._chroma_collection.get(ids=[doc_id])
                return len(result["ids"]) > 0
            except Exception:
                return False
        else:
            return doc_id in self._memory_store
    
    def add_document(
        self,
        content: str,
        metadata: Dict[str, Any],
        doc_id: Optional[str] = None,
        skip_if_exists: bool = True
    ) -> Optional[str]:
        """
        添加单个文档到向量数据库
        
        Args:
            content: 文档内容
            metadata: 元数据
            doc_id: 文档ID，None则自动生成
            skip_if_exists: 如果文档已存在是否跳过（默认True）
            
        Returns:
            文档ID，如果跳过则返回None
        """
        if not doc_id:
            doc_id = self._generate_id(content, prefix=metadata.get("type", "doc") + "_")
        
        # 检查是否已存在
        if skip_if_exists and self.document_exists(doc_id):
            logger.debug(f"Document already exists, skipping: {doc_id}")
            return None
        
        # 生成嵌入向量
        embedding = self._generate_embedding(content)
        
        # 创建文档块
        chunk = DocumentChunk(
            id=doc_id,
            content=content,
            metadata=metadata,
            embedding=embedding
        )
        
        if self.use_chroma and self._chroma_collection:
            # 添加到ChromaDB
            self._chroma_collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[metadata]
            )
        else:
            # 添加到内存存储
            self._memory_store[doc_id] = chunk
        
        logger.debug(f"Added document: {doc_id}")
        return doc_id
    
    def add_documents(
        self,
        documents: List[Dict[str, Any]],
        skip_if_exists: bool = True
    ) -> List[str]:
        """
        批量添加文档（使用批量embedding提高效率）
        
        Args:
            documents: 文档列表，每个文档包含content和metadata
            skip_if_exists: 如果文档已存在是否跳过（默认True）
            
        Returns:
            文档ID列表（跳过的文档返回None）
        """
        if not documents:
            return []
        
        # 为每个文档生成ID并检查是否存在
        doc_status = []  # [(doc, doc_id, is_existing), ...]
        for doc in documents:
            doc_id = doc.get("id") or self._generate_id(doc["content"], prefix=doc.get("metadata", {}).get("type", "doc") + "_")
            is_existing = self.document_exists(doc_id) if skip_if_exists else False
            doc_status.append((doc, doc_id, is_existing))
        
        # 过滤掉已存在的文档
        new_documents = [(doc, doc_id) for doc, doc_id, is_existing in doc_status if not is_existing]
        
        if len(new_documents) < len(documents):
            logger.debug(f"Skipping {len(documents) - len(new_documents)} existing documents")
            
        if not new_documents:
            # 所有文档都已存在
            return [doc_id if is_existing else None for _, doc_id, is_existing in doc_status]
        
        # 批量生成embeddings
        texts = [doc["content"] for doc, _ in new_documents]
        embeddings = self._generate_embeddings_batch(texts)
        
        doc_ids = []
        chunks = []
        
        for i, (doc, doc_id) in enumerate(new_documents):
            doc_ids.append(doc_id)
            
            chunk = DocumentChunk(
                id=doc_id,
                content=doc["content"],
                metadata=doc.get("metadata", {}),
                embedding=embeddings[i]
            )
            chunks.append(chunk)
        
        if self.use_chroma and self._chroma_collection:
            # 批量添加到ChromaDB
            self._chroma_collection.add(
                ids=doc_ids,
                embeddings=embeddings,
                documents=[doc["content"] for doc, _ in new_documents],
                metadatas=[doc.get("metadata", {}) for doc, _ in new_documents]
            )
        else:
            # 添加到内存存储
            for chunk in chunks:
                self._memory_store[chunk.id] = chunk
        
        logger.debug(f"Added {len(doc_ids)} documents in batch")
        
        # 构建返回列表，保持原始顺序
        new_doc_id_iter = iter(doc_ids)
        result = []
        for _, doc_id, is_existing in doc_status:
            if is_existing:
                result.append(None)
            else:
                result.append(next(new_doc_id_iter))
        return result
    
    def _generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        批量生成文本嵌入向量
        
        Args:
            texts: 文本列表
            
        Returns:
            向量列表
        """
        if self.embedding_function:
            # 如果提供了自定义embedding函数，逐个处理
            return [self.embedding_function(text) for text in texts]
        
        try:
            from sentence_transformers import SentenceTransformer
            
            # 使用单例模式缓存模型
            if not hasattr(self, '_embedding_model'):
                logger.info("Loading sentence-transformers model...")
                import os
                # 设置本地缓存目录
                cache_dir = os.path.expanduser("~/.cache/torch/sentence_transformers")
                os.makedirs(cache_dir, exist_ok=True)
                
                model_name = 'paraphrase-multilingual-MiniLM-L12-v2'
                try:
                    # 尝试从本地加载
                    self._embedding_model = SentenceTransformer(model_name, cache_folder=cache_dir)
                except Exception:
                    # 如果本地没有，尝试从网络加载
                    logger.warning("Loading model from HuggingFace Hub...")
                    self._embedding_model = SentenceTransformer(model_name)
            
            # 批量生成embeddings
            embeddings = self._embedding_model.encode(
                texts, 
                convert_to_numpy=True,
                batch_size=32,
                show_progress_bar=False
            )
            return embeddings.tolist()
            
        except ImportError:
            logger.error("sentence-transformers not installed. Please install: pip install sentence-transformers")
            raise
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}")
            raise
    
    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[DocumentChunk]:
        """
        相似度搜索
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            filter_metadata: 元数据过滤条件
            
        Returns:
            匹配的文档块列表
        """
        # 生成查询向量
        query_embedding = self._generate_embedding(query)
        
        if self.use_chroma and self._chroma_collection:
            # ChromaDB搜索
            where_clause = self._build_chroma_filter(filter_metadata) if filter_metadata else None
            
            results = self._chroma_collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_clause
            )
            
            documents = []
            for i in range(len(results["ids"][0])):
                doc = DocumentChunk(
                    id=results["ids"][0][i],
                    content=results["documents"][0][i],
                    metadata=results["metadatas"][0][i],
                    embedding=results["embeddings"][0][i] if results["embeddings"] else None
                )
                documents.append(doc)
            
            return documents
        else:
            # 内存搜索
            return self._memory_search(query_embedding, top_k, filter_metadata)
    
    def _memory_search(
        self,
        query_embedding: List[float],
        top_k: int,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[DocumentChunk]:
        """内存存储的相似度搜索"""
        import numpy as np
        
        query_vec = np.array(query_embedding)
        scores = []
        
        for doc_id, chunk in self._memory_store.items():
            # 元数据过滤
            if filter_metadata:
                match = True
                for key, value in filter_metadata.items():
                    if chunk.metadata.get(key) != value:
                        match = False
                        break
                if not match:
                    continue
            
            # 计算余弦相似度
            doc_vec = np.array(chunk.embedding)
            similarity = np.dot(query_vec, doc_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(doc_vec))
            scores.append((doc_id, similarity))
        
        # 按相似度排序
        scores.sort(key=lambda x: x[1], reverse=True)
        
        # 返回top_k结果
        results = []
        for doc_id, score in scores[:top_k]:
            chunk = self._memory_store[doc_id]
            # 添加相似度到metadata
            chunk.metadata["similarity_score"] = float(score)
            results.append(chunk)
        
        return results
    
    def _build_chroma_filter(self, filter_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """构建ChromaDB过滤条件"""
        # 简单实现：只支持等值过滤
        where_clause = {}
        for key, value in filter_metadata.items():
            where_clause[key] = value
        return where_clause
    
    def delete_document(self, doc_id: str) -> bool:
        """删除文档"""
        try:
            if self.use_chroma and self._chroma_collection:
                self._chroma_collection.delete(ids=[doc_id])
            else:
                if doc_id in self._memory_store:
                    del self._memory_store[doc_id]
            return True
        except Exception as e:
            logger.error(f"Error deleting document {doc_id}: {e}")
            return False
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """获取集合统计信息"""
        if self.use_chroma and self._chroma_collection:
            total_count = self._chroma_collection.count()
            
            # 尝试获取各类型的数量
            type_counts = {}
            try:
                # 获取所有数据并统计类型
                all_data = self._chroma_collection.get(limit=10000)  # 最多获取10000条
                if all_data and 'metadatas' in all_data:
                    for metadata in all_data['metadatas']:
                        doc_type = metadata.get('type', 'unknown')
                        type_counts[doc_type] = type_counts.get(doc_type, 0) + 1
            except Exception as e:
                logger.warning(f"Failed to get type counts: {e}")
        else:
            total_count = len(self._memory_store)
            # 统计内存中的类型
            type_counts = {}
            for doc in self._memory_store.values():
                doc_type = doc.metadata.get('type', 'unknown')
                type_counts[doc_type] = type_counts.get(doc_type, 0) + 1
        
        return {
            "collection_name": self.collection_name,
            "document_count": total_count,
            "storage_type": "chroma" if self.use_chroma else "memory",
            "persist_directory": self.persist_directory if self.use_chroma else None,
            "type_counts": type_counts
        }
    
    def clear_collection(self):
        """清空集合"""
        if self.use_chroma and self._chroma_collection:
            # 删除并重新创建集合
            self._chroma_client.delete_collection(self.collection_name)
            self._chroma_collection = self._chroma_client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
        else:
            self._memory_store.clear()
        
        logger.info(f"Cleared collection: {self.collection_name}")


class TaogubaVectorizer:
    """
    淘股吧数据向量化处理器
    将爬取的主帖和评论转换为向量数据库文档
    """
    
    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50
    ):
        """
        初始化向量化处理器
        
        Args:
            vector_store: 向量数据库实例，None则创建默认实例
            chunk_size: 文本分块大小
            chunk_overlap: 分块重叠大小
        """
        self.vector_store = vector_store or VectorStore()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def process_main_post(self, post: Dict[str, Any]) -> List[str]:
        """
        处理主帖，将其添加到向量数据库
        
        Args:
            post: 主帖数据字典
            
        Returns:
            添加的文档ID列表（已存在的返回None）
        """
        doc_ids = []
        post_id = post.get("post_id", "")
        
        # 1. 添加主帖标题
        title = post.get("title", "")
        if title:
            doc_id = self.vector_store.add_document(
                content=title,
                metadata={
                    "type": "post_title",
                    "post_id": post_id,
                    "author_name": post.get("author_name", ""),
                    "publish_time": post.get("publish_time", ""),
                    "url": post.get("url", "")
                },
                doc_id=f"title_{post_id}"
            )
            if doc_id:
                doc_ids.append(doc_id)
        
        # 2. 添加主帖内容（分块处理）
        content = post.get("content", "")
        if content:
            chunks = self._split_text(content)
            for i, chunk in enumerate(chunks):
                doc_id = self.vector_store.add_document(
                    content=chunk,
                    metadata={
                        "type": "post_content",
                        "post_id": post_id,
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                        "author_name": post.get("author_name", ""),
                        "publish_time": post.get("publish_time", ""),
                        "url": post.get("url", "")
                    },
                    doc_id=f"content_{post_id}_{i}"
                )
                if doc_id:
                    doc_ids.append(doc_id)
        
        skipped = len([doc_id for doc_id in doc_ids if doc_id is None])
        added = len([doc_id for doc_id in doc_ids if doc_id is not None])
        logger.info(f"Processed main post {post_id}: {added} added, {skipped} skipped")
        return doc_ids
    
    def process_comment(self, comment: Dict[str, Any], post_id: str) -> Optional[str]:
        """
        处理单条评论，将其添加到向量数据库
        
        Args:
            comment: 评论数据字典
            post_id: 所属帖子ID
            
        Returns:
            文档ID或None
        """
        content = comment.get("content", "")
        if not content or content.strip() in ["", "1", "2", "3", "沙发", "板凳", "地板"]:
            # 跳过无意义评论
            return None
        
        comment_id = comment.get("comment_id", "")
        doc_id = self.vector_store.add_document(
            content=content,
            metadata={
                "type": "comment",
                "post_id": post_id,
                "comment_id": comment_id,
                "author_name": comment.get("author_name", ""),
                "author_id": comment.get("author_id", ""),
                "floor_number": comment.get("floor_number", 0),
                "publish_time": comment.get("publish_time", ""),
                "like_count": comment.get("like_count", 0)
            },
            doc_id=f"comment_{comment_id}"
        )
        
        return doc_id
    
    def process_comments(self, comments: List[Dict[str, Any]], post_id: str) -> List[str]:
        """
        批量处理评论
        
        Args:
            comments: 评论列表
            post_id: 所属帖子ID
            
        Returns:
            文档ID列表（已存在的返回None）
        """
        doc_ids = []
        batch_size = 32  # 每批处理32条评论
        total = len(comments)
        added_count = 0
        skipped_count = 0
        
        for i in range(0, total, batch_size):
            batch = comments[i:i+batch_size]
            batch_docs = []
            
            for comment in batch:
                content = comment.get("content", "")
                if not content or content.strip() in ["", "1", "2", "3", "沙发", "板凳", "地板"]:
                    continue
                
                comment_id = comment.get("comment_id", "")
                batch_docs.append({
                    "content": content,
                    "metadata": {
                        "type": "comment",
                        "post_id": post_id,
                        "comment_id": comment_id,
                        "author_name": comment.get("author_name", ""),
                        "author_id": comment.get("author_id", ""),
                        "floor_number": comment.get("floor_number", 0),
                        "publish_time": comment.get("publish_time", ""),
                        "like_count": comment.get("like_count", 0)
                    },
                    "id": f"comment_{comment_id}"
                })
            
            # 批量添加
            if batch_docs:
                try:
                    batch_ids = self.vector_store.add_documents(batch_docs)
                    doc_ids.extend(batch_ids)
                    batch_added = len([doc_id for doc_id in batch_ids if doc_id is not None])
                    batch_skipped = len([doc_id for doc_id in batch_ids if doc_id is None])
                    added_count += batch_added
                    skipped_count += batch_skipped
                    logger.debug(f"Processed batch {i//batch_size + 1}/{(total-1)//batch_size + 1}: {batch_added} added, {batch_skipped} skipped")
                except Exception as e:
                    logger.error(f"Error processing batch {i//batch_size + 1}: {e}")
            
            # 每处理10批输出一次进度
            if (i // batch_size + 1) % 10 == 0:
                logger.info(f"Progress: {min(i + batch_size, total)}/{total} comments processed ({added_count} added, {skipped_count} skipped)")
        
        logger.info(f"Processed comments for post {post_id}: {added_count} added, {skipped_count} skipped")
        return doc_ids
    
    def process_post_with_comments(self, post: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        处理完整帖子（主帖+评论）
        
        Args:
            post: 帖子数据字典
            
        Returns:
            {"post_ids": [...], "comment_ids": [...]}
        """
        post_ids = self.process_main_post(post)
        
        comment_ids = []
        comments = post.get("comments", [])
        if comments:
            comment_ids = self.process_comments(comments, post.get("post_id", ""))
        
        return {
            "post_ids": post_ids,
            "comment_ids": comment_ids
        }
    
    def process_crawl_result(self, crawl_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理整个爬取结果
        
        Args:
            crawl_result: 爬取结果字典
            
        Returns:
            处理统计信息
        """
        all_post_ids = []
        all_comment_ids = []
        
        posts = crawl_result.get("posts", [])
        logger.info(f"Processing {len(posts)} posts from crawl result")
        
        for idx, post in enumerate(posts, 1):
            logger.info(f"Processing post {idx}/{len(posts)}: {post.get('title', 'Unknown')[:50]}...")
            try:
                result = self.process_post_with_comments(post)
                all_post_ids.extend(result["post_ids"])
                all_comment_ids.extend(result["comment_ids"])
                
                # 统计新增和跳过的数量
                post_added = len([doc_id for doc_id in result["post_ids"] if doc_id is not None])
                post_skipped = len([doc_id for doc_id in result["post_ids"] if doc_id is None])
                comment_added = len([doc_id for doc_id in result["comment_ids"] if doc_id is not None])
                comment_skipped = len([doc_id for doc_id in result["comment_ids"] if doc_id is None])
                
                logger.info(f"Post {idx} processed: {post_added} chunks added ({post_skipped} skipped), {comment_added} comments added ({comment_skipped} skipped)")
            except Exception as e:
                logger.error(f"Error processing post {idx}: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        # 统计总数
        post_added_total = len([doc_id for doc_id in all_post_ids if doc_id is not None])
        post_skipped_total = len([doc_id for doc_id in all_post_ids if doc_id is None])
        comment_added_total = len([doc_id for doc_id in all_comment_ids if doc_id is not None])
        comment_skipped_total = len([doc_id for doc_id in all_comment_ids if doc_id is None])
        
        stats = {
            "total_posts": len(posts),
            "post_chunks": {
                "added": post_added_total,
                "skipped": post_skipped_total,
                "total": len(all_post_ids)
            },
            "comments": {
                "added": comment_added_total,
                "skipped": comment_skipped_total,
                "total": len(all_comment_ids)
            },
            "total_documents": {
                "added": post_added_total + comment_added_total,
                "skipped": post_skipped_total + comment_skipped_total,
                "total": len(all_post_ids) + len(all_comment_ids)
            }
        }
        
        logger.info(f"Vectorization complete: {stats['total_documents']['added']} added, {stats['total_documents']['skipped']} skipped")
        return stats
    
    def clear_vector_store(self) -> bool:
        """
        清空向量数据库中的所有数据
        
        Returns:
            是否成功清空
        """
        try:
            if self.vector_store:
                self.vector_store.clear_collection()
                logger.info("Vector store cleared successfully")
                return True
            else:
                logger.warning("Vector store not initialized")
                return False
        except Exception as e:
            logger.error(f"Error clearing vector store: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取向量数据库统计信息
        
        Returns:
            统计信息字典
        """
        if self.vector_store:
            return self.vector_store.get_collection_stats()
        return {"error": "Vector store not initialized"}
    
    def _split_text(self, text: str) -> List[str]:
        """
        将长文本分割成小块
        
        Args:
            text: 原始文本
            
        Returns:
            文本块列表
        """
        if len(text) <= self.chunk_size:
            return [text]
        
        chunks = []
        start = 0
        text_length = len(text)
        
        while start < text_length:
            end = min(start + self.chunk_size, text_length)
            
            # 尝试在句子边界分割（如果不是文本末尾）
            if end < text_length:
                # 查找最近的句号、问号或感叹号
                for sep in [".", "。", "!", "！", "?", "？", "\n"]:
                    pos = text.rfind(sep, start, end)
                    if pos > start:
                        end = pos + 1
                        break
            
            # 提取块并确保有实际内容
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            # 计算下一个起始位置，确保至少前进一部分
            next_start = end - self.chunk_overlap
            if next_start <= start:
                next_start = end  # 如果没有重叠或重叠太大，直接跳到end
            start = next_start
            
            # 防止无限循环
            if start >= text_length:
                break
        
        return chunks
    
    def search_posts(
        self,
        query: str,
        top_k: int = 5,
        author: Optional[str] = None
    ) -> List[DocumentChunk]:
        """
        搜索帖子
        
        Args:
            query: 查询文本
            top_k: 返回结果数
            author: 按作者过滤
            
        Returns:
            匹配的文档列表
        """
        filter_metadata = {"type": "post_content"}
        if author:
            filter_metadata["author_name"] = author
        
        return self.vector_store.search(query, top_k, filter_metadata)
    
    def search_comments(
        self,
        query: str,
        top_k: int = 5,
        author: Optional[str] = None
    ) -> List[DocumentChunk]:
        """
        搜索评论
        
        Args:
            query: 查询文本
            top_k: 返回结果数
            author: 按作者过滤
            
        Returns:
            匹配的文档列表
        """
        filter_metadata = {"type": "comment"}
        if author:
            filter_metadata["author_name"] = author
        
        return self.vector_store.search(query, top_k, filter_metadata)
    
    def search_all(
        self,
        query: str,
        top_k: int = 10
    ) -> Dict[str, List[DocumentChunk]]:
        """
        搜索所有内容
        
        Args:
            query: 查询文本
            top_k: 每种类型返回结果数
            
        Returns:
            {"posts": [...], "comments": [...], "titles": [...]}
        """
        return {
            "posts": self.vector_store.search(query, top_k, {"type": "post_content"}),
            "comments": self.vector_store.search(query, top_k, {"type": "comment"}),
            "titles": self.vector_store.search(query, top_k, {"type": "post_title"})
        }


# 便捷函数
def create_vector_store(
    collection_name: str = "taoguba_posts",
    persist_directory: str = "./vector_db"
) -> VectorStore:
    """
    创建向量数据库实例
    
    Args:
        collection_name: 集合名称
        persist_directory: 持久化目录
        
    Returns:
        VectorStore实例
    """
    return VectorStore(
        collection_name=collection_name,
        persist_directory=persist_directory,
        use_chroma=True
    )


def vectorize_crawl_result(
    crawl_result: Dict[str, Any],
    vector_store: Optional[VectorStore] = None
) -> Dict[str, Any]:
    """
    便捷函数：将爬取结果向量化
    
    Args:
        crawl_result: 爬取结果
        vector_store: 向量数据库实例，None则创建默认实例
        
    Returns:
        处理统计信息
    """
    if vector_store is None:
        vector_store = create_vector_store()
    
    vectorizer = TaogubaVectorizer(vector_store)
    return vectorizer.process_crawl_result(crawl_result)
