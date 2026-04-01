"""
淘股吧通用爬虫工具
基于Scrapling框架开发，适配淘股吧实际页面结构
支持抓取指定博主的主帖和跟帖树状结构
"""

import re
import time
import json
import random
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from urllib.parse import urljoin, urlparse
from loguru import logger
from concurrent.futures import ThreadPoolExecutor, as_completed

from scrapling.fetchers import StealthyFetcher

from src.crawler.models import MainPost, CommentNode, BloggerInfo, CrawlResult
from src.crawler.storage import DataStorage
from src.vector.vector_store import VectorStore, TaogubaVectorizer


class TaogubaCrawler:
    """
    淘股吧通用爬虫类
    适配淘股吧实际页面结构
    
    使用示例:
        crawler = TaogubaCrawler()
        result = crawler.crawl_blogger("jl韭菜抄家", user_id="7737030", days=7)
    """
    
    BASE_URL = "https://www.tgb.cn"
    
    def __init__(
        self,
        delay: Tuple[float, float] = (0.02, 0.05),
        output_dir: str = "output",
        max_comments: int = 250,
        enable_vector_store: bool = False,
        vector_store_config: Optional[Dict[str, Any]] = None,
        fast_mode: bool = True
    ):
        """
        初始化爬虫
        
        Args:
            delay: 请求间隔范围(最小, 最大)秒
            output_dir: 输出目录
            max_comments: 每篇帖子最大抓取评论数，默认250，设为0或负数表示不抓取评论
            enable_vector_store: 是否启用向量数据库
            vector_store_config: 向量数据库配置，如 {"collection_name": "...", "persist_directory": "..."}
            fast_mode: 快速模式，减少页面等待时间
        """
        self.delay = delay
        self.output_dir = output_dir
        self.max_comments = max_comments
        self.fast_mode = fast_mode
        self.storage = DataStorage(output_dir)
        self.fetcher = StealthyFetcher()
        # 使用configure方法配置fetcher（v0.3+版本）
        self.fetcher.configure(adaptive=True)
        
        # 向量数据库
        self.enable_vector_store = enable_vector_store
        self.vector_store = None
        self.vectorizer = None
        
        if enable_vector_store:
            self._init_vector_store(vector_store_config)
        
        # 统计信息
        self.stats = {
            "requests": 0,
            "posts_found": 0,
            "posts_crawled": 0,
            "comments_crawled": 0,
            "errors": 0
        }
    
    def _init_vector_store(self, config: Optional[Dict[str, Any]] = None):
        """初始化向量数据库"""
        try:
            config = config or {}
            self.vector_store = VectorStore(
                collection_name=config.get("collection_name", "taoguba_posts"),
                persist_directory=config.get("persist_directory", "./vector_db"),
                use_chroma=config.get("use_chroma", True)
            )
            self.vectorizer = TaogubaVectorizer(self.vector_store)
            logger.info("Vector store initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}")
            self.enable_vector_store = False
    
    def _random_delay(self):
        """随机延迟，避免请求过快"""
        time.sleep(random.uniform(*self.delay))
    
    def _get_page(self, url: str, retries: int = 3) -> Optional[Any]:
        """
        获取页面内容
        
        Args:
            url: 页面URL
            retries: 重试次数
            
        Returns:
            页面对象或None
        """
        for attempt in range(retries):
            try:
                self._random_delay()
                logger.debug(f"Fetching: {url} (attempt {attempt + 1})")
                
                # 快速模式：减少等待时间
                if self.fast_mode:
                    # 不等待 network_idle，只等待 DOM 加载
                    page = self.fetcher.fetch(
                        url, 
                        headless=True, 
                        network_idle=False,
                        wait_for_selector='.article_tittle, .p_coten, .comment-data'  # 等待关键元素
                    )
                else:
                    page = self.fetcher.fetch(url, headless=True, network_idle=True)
                
                self.stats["requests"] += 1
                return page
                
            except Exception as e:
                logger.warning(f"Request failed ({attempt + 1}/{retries}): {url}, error: {e}")
                self.stats["errors"] += 1
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # 指数退避
                
        logger.error(f"Failed to fetch: {url}")
        return None
    
    def get_blogger_info(self, user_id: str, username: str) -> Optional[BloggerInfo]:
        """获取博主详细信息"""
        blog_url = f"{self.BASE_URL}/blog/{user_id}"
        page = self._get_page(blog_url)
        
        if not page:
            return None
        
        try:
            # 提取用户信息
            info = BloggerInfo(
                user_id=user_id,
                username=username,
                profile_url=blog_url
            )
            
            # 尝试提取昵称 - 淘股吧通常在页面标题或用户信息区
            # 页面标题格式: "用户名_博客_淘股吧"
            title_elem = page.css('title').first
            if title_elem:
                title_text = title_elem.text.get()
                # 提取 "用户名_博客_淘股吧" 中的用户名
                match = re.match(r'(.+?)_博客_淘股吧', title_text)
                if match:
                    info.nickname = match.group(1)
            
            # 尝试提取头像
            avatar_elem = page.css('.user-header img, .avatar img, img[src*="avatar"]').first
            if avatar_elem:
                info.avatar = avatar_elem.attrib.get('src')
            
            # 尝试提取统计数据 - 从页面文本中提取
            # Scrapling的text返回TextHandler对象，需要调用get()方法
            page_text = page.text.get()
            
            # 粉丝数
            followers_match = re.search(r'粉丝[:：]\s*(\d+)', page_text)
            if followers_match:
                info.followers_count = int(followers_match.group(1))
            
            # 被赞数
            likes_match = re.search(r'被赞[:：]\s*(\d+)', page_text)
            if likes_match:
                info.likes_count = int(likes_match.group(1))
            
            # 发帖数（从页面统计）
            posts_match = re.search(r'发帖[:：]\s*(\d+)', page_text)
            if posts_match:
                info.posts_count = int(posts_match.group(1))
            
            return info
            
        except Exception as e:
            logger.error(f"Error parsing blogger info: {e}")
            return BloggerInfo(user_id=user_id, username=username, profile_url=blog_url)
    
    def get_blogger_posts(
        self, 
        user_id: str, 
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_pages: int = 50
    ) -> List[Dict[str, Any]]:
        """
        获取博主的所有帖子列表
        
        Args:
            user_id: 用户ID
            start_date: 开始日期
            end_date: 结束日期
            max_pages: 最大页数
            
        Returns:
            帖子列表（包含基本信息的字典）
        """
        posts = []
        page_num = 1
        stop_fetching = False
        last_page_post_ids = set()  # 用于检测页面内容是否重复
        
        # 默认时间范围：最近30天
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            start_date = end_date - timedelta(days=30)
        
        logger.info(f"Fetching posts from {start_date.date()} to {end_date.date()}")
        
        while page_num <= max_pages and not stop_fetching:
            # 淘股吧用户博客页面URL格式
            # 第一页: /blog/{user_id}
            # 更多页面: /user/blog/moreTopic?userID={user_id}&page={page}
            if page_num == 1:
                url = f"{self.BASE_URL}/blog/{user_id}"
            else:
                # 尝试不同的翻页URL格式
                # 格式1: /user/blog/moreTopic?userID={user_id}&page={page_num}
                # 格式2: /blog/{user_id}?page={page_num}
                url = f"{self.BASE_URL}/blog/{user_id}?page={page_num}"
            
            page = self._get_page(url)
            if not page:
                logger.warning(f"Failed to fetch page {page_num}, trying alternative URL")
                # 尝试备用URL格式
                if page_num > 1:
                    alt_url = f"{self.BASE_URL}/user/blog/moreTopic?userID={user_id}&page={page_num}"
                    page = self._get_page(alt_url)
                    if not page:
                        break
            
            page_posts = self._parse_post_list(page, user_id)
            
            if not page_posts:
                logger.info(f"No more posts found at page {page_num}")
                break
            
            # 检测页面内容是否重复（未登录时翻页可能无效）
            current_page_post_ids = {post.get('post_id') for post in page_posts if post.get('post_id')}
            if current_page_post_ids and current_page_post_ids == last_page_post_ids:
                logger.warning(f"Page {page_num} has same content as previous page, pagination may not work (possibly not logged in). Stopping.")
                break
            last_page_post_ids = current_page_post_ids
            
            logger.info(f"Found {len(page_posts)} posts on page {page_num}")
            
            for post in page_posts:
                post_date = post.get('publish_time')
                post_title = post.get('title', 'N/A')[:30]
                
                # 检查时间范围
                if post_date:
                    if post_date < start_date:
                        # 超过时间范围，停止抓取
                        logger.info(f"Post '{post_title}...' date {post_date.date()} < {start_date.date()}, stopping")
                        stop_fetching = True
                        break
                    if post_date > end_date:
                        # 还未到时间范围，跳过
                        logger.debug(f"Post '{post_title}...' date {post_date.date()} > {end_date.date()}, skipping")
                        continue
                
                posts.append(post)
                logger.debug(f"Added post '{post_title}...' ({post_date.date()})")
            
            if not stop_fetching:
                logger.info(f"Page {page_num} complete, moving to page {page_num + 1}")
            
            page_num += 1
        
        self.stats["posts_found"] = len(posts)
        logger.info(f"Total posts found in range: {len(posts)}")
        return posts
    
    def _parse_post_list(self, page, user_id: str = None) -> List[Dict[str, Any]]:
        """
        解析帖子列表页面
        
        Args:
            page: 页面对象
            user_id: 当前博主的用户ID，用于过滤只保留该博主的帖子
        
        Returns:
            帖子基本信息列表
        """
        posts = []
        
        # 淘股吧博客页面结构：
        # 帖子列表在 .allblog_article 容器中
        # 每个帖子是 .article_tittle 元素
        # 注意：要排除 "热文推荐" 区域的帖子
        
        # 首先尝试查找博主文章列表容器
        article_container = page.css('.allblog_article').first
        
        if article_container:
            logger.debug("Found .allblog_article container")
            # 在容器内查找帖子项
            post_items = article_container.css('.article_tittle')
            logger.debug(f"Found {len(post_items)} post items in .allblog_article")
            
            for item in post_items:
                try:
                    post = self._parse_article_tittle(item)
                    if post:
                        posts.append(post)
                        logger.debug(f"Parsed post: {post.get('title', 'N/A')[:30]}...")
                except Exception as e:
                    logger.warning(f"Error parsing post item: {e}")
                    continue
        else:
            # 备用方案：尝试其他选择器
            logger.debug("No .allblog_article found, trying alternative selectors")
            posts = self._parse_post_list_alternative(page)
        
        logger.info(f"Parsed {len(posts)} posts from page")
        return posts
    
    def _parse_article_tittle(self, item) -> Optional[Dict[str, Any]]:
        """
        解析淘股吧 .article_tittle 帖子项
        
        结构示例：
        <div class="article_tittle">
            <div class="tittle_data left">
                <span class="tittle_jinghua">[精] </span>
                <a href="a/2qipM89a9Wu" title="...">标题</a>
            </div>
            <div class="tittle_llhf left">9453/184</div>
            <div class="tittle_fbshijian left">2026-03-19</div>
        </div>
        """
        try:
            post = {}
            
            # 查找标题链接 - 注意淘股吧的链接格式是 "a/xxxx" 而不是 "/a/xxxx"
            link = item.css('a[href^="a/"]').first
            if not link:
                # 尝试其他格式
                link = item.css('a[href*="/a/"]').first
            if not link:
                return None
            
            # 提取标题
            post['title'] = link.text.get().strip()
            
            # 提取链接和post_id
            href = link.attrib.get('href')
            if href:
                # 确保链接完整
                if href.startswith('a/'):
                    href = '/' + href
                post['url'] = urljoin(self.BASE_URL, href)
                post['post_id'] = self._extract_post_id(href)
            
            if not post.get('post_id'):
                return None
            
            # 提取帖子类型 - 检查是否有精华标记
            jinghua_elem = item.css('.tittle_jinghua').first
            if jinghua_elem:
                jinghua_text = jinghua_elem.text.get()
                if '[精]' in jinghua_text:
                    post['post_type'] = '精华'
                elif '[原]' in jinghua_text:
                    post['post_type'] = '原创'
                elif '[转]' in jinghua_text:
                    post['post_type'] = '转载'
                else:
                    post['post_type'] = '普通'
            else:
                # 从标题中判断
                title = post['title']
                if '[原]' in title:
                    post['post_type'] = '原创'
                elif '[精]' in title:
                    post['post_type'] = '精华'
                elif '[转]' in title:
                    post['post_type'] = '转载'
                else:
                    post['post_type'] = '普通'
            
            # 提取浏览/回复数 - 格式: "浏览数/回复数"
            llhf_elem = item.css('.tittle_llhf').first
            if llhf_elem:
                llhf_text = llhf_elem.text.get().strip()
                view_comment_match = re.search(r'(\d+)\s*/\s*(\d+)', llhf_text)
                if view_comment_match:
                    post['view_count'] = int(view_comment_match.group(1))
                    post['comment_count'] = int(view_comment_match.group(2))
            
            # 提取发布时间
            time_elem = item.css('.tittle_fbshijian').first
            if time_elem:
                time_text = time_elem.text.get().strip()
                parsed_time = self._parse_time(time_text)
                if parsed_time:
                    post['publish_time'] = parsed_time
            
            return post
            
        except Exception as e:
            logger.warning(f"Error parsing article_tittle: {e}")
            return None
    
    def _parse_post_list_alternative(self, page) -> List[Dict[str, Any]]:
        """
        备用解析方法：当标准方法失败时使用
        只查找明确属于博主文章列表区域的帖子
        """
        posts = []
        
        # 尝试多种可能的选择器
        post_item_selectors = [
            '.article_tittle',  # 淘股吧博客页面
            '.post-list .post-item',
            '.topic-list .topic-item', 
            '.article-list .article-item',
        ]
        
        for selector in post_item_selectors:
            post_items = page.css(selector)
            if post_items:
                logger.debug(f"Found {len(post_items)} post items with selector: {selector}")
                
                for item in post_items:
                    try:
                        # 对于 .article_tittle 使用专用解析
                        if selector == '.article_tittle':
                            post = self._parse_article_tittle(item)
                        else:
                            post = self._parse_generic_post_item(item)
                        
                        if post:
                            posts.append(post)
                    except Exception as e:
                        logger.warning(f"Error parsing post item: {e}")
                        continue
                
                if posts:
                    break
        
        return posts
    
    def _parse_generic_post_item(self, item) -> Optional[Dict[str, Any]]:
        """通用帖子项解析"""
        try:
            post = {}
            
            # 查找标题链接
            link = item.css('a[href*="/a/"]').first
            if not link:
                return None
            
            post['title'] = link.text.get().strip()
            
            href = link.attrib.get('href')
            if href:
                post['url'] = urljoin(self.BASE_URL, href)
                post['post_id'] = self._extract_post_id(href)
            
            if not post.get('post_id'):
                return None
            
            # 提取帖子类型
            title = post['title']
            if '[原]' in title:
                post['post_type'] = '原创'
            elif '[精]' in title:
                post['post_type'] = '精华'
            elif '[转]' in title:
                post['post_type'] = '转载'
            else:
                post['post_type'] = '普通'
            
            # 提取时间
            item_text = item.text.get()
            time_patterns = [
                r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})',
                r'(\d{4}-\d{2}-\d{2})',
                r'(\d{2}-\d{2}\s+\d{2}:\d{2})',
                r'(\d{2}-\d{2})',
            ]
            for pattern in time_patterns:
                time_match = re.search(pattern, item_text)
                if time_match:
                    post['publish_time'] = self._parse_time(time_match.group(1))
                    break
            
            # 提取浏览/评论数
            view_comment_match = re.search(r'(\d+)\s*/\s*(\d+)', item_text)
            if view_comment_match:
                post['view_count'] = int(view_comment_match.group(1))
                post['comment_count'] = int(view_comment_match.group(2))
            
            return post
            
        except Exception as e:
            logger.warning(f"Error parsing generic post item: {e}")
            return None
    
    def _extract_post_id(self, url: str) -> Optional[str]:
        """从帖子URL中提取ID"""
        # 格式: /a/1RsChtHhZuU 或 a/1RsChtHhZuU
        match = re.search(r'/a/([a-zA-Z0-9]+)', url)
        if match:
            return match.group(1)
        # 尝试不带斜杠的格式
        match = re.search(r'^a/([a-zA-Z0-9]+)', url)
        if match:
            return match.group(1)
        return None
    
    def _parse_time(self, time_str: str) -> Optional[datetime]:
        """解析时间字符串"""
        time_str = time_str.strip()
        
        formats = [
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
            '%m-%d %H:%M',
            '%H:%M',
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(time_str, fmt)
                # 如果没有年份，假设为今年
                if dt.year == 1900:
                    dt = dt.replace(year=datetime.now().year)
                return dt
            except ValueError:
                continue
        
        # 尝试从文本中提取日期
        # 格式: 2026-03-19 或 03-19
        date_match = re.search(r'(\d{4})?(\d{2})-(\d{2})', time_str)
        if date_match:
            year = int(date_match.group(1)) if date_match.group(1) else datetime.now().year
            month = int(date_match.group(2))
            day = int(date_match.group(3))
            try:
                return datetime(year, month, day)
            except ValueError:
                pass
        
        return None
    
    def get_post_detail(self, post_id: str, post_url: str) -> Optional[MainPost]:
        """
        获取帖子详情和评论树
        
        Args:
            post_id: 帖子ID
            post_url: 帖子URL
            
        Returns:
            主帖对象或None
        """
        logger.info(f"Fetching post detail: {post_id}")
        
        page = self._get_page(post_url)
        if not page:
            return None
        
        try:
            # 解析主帖内容
            post = self._parse_post_content(page, post_id, post_url)
            if not post:
                return None
            
            # 解析评论树（支持多页）
            comments = self._parse_comments(page, post_id, post_url)
            post.comments = comments
            
            self.stats["posts_crawled"] += 1
            self.stats["comments_crawled"] += sum(self._count_comments(c) for c in comments)
            
            return post
            
        except Exception as e:
            logger.error(f"Error parsing post {post_id}: {e}")
            self.stats["errors"] += 1
            return None
    
    def _count_comments(self, comment: CommentNode) -> int:
        """递归计算评论总数"""
        count = 1
        for child in comment.children:
            count += self._count_comments(child)
        return count
    
    def _html_to_text(self, html: str) -> str:
        """
        将HTML转换为纯文本
        移除HTML标签，保留文本内容
        """
        if not html:
            return ""
        
        # 移除script和style标签及其内容
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        
        # 将<br>, <br/>, <br /> 替换为换行符
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        
        # 将</p>, </div> 等块级元素替换为换行符
        text = re.sub(r'</(p|div|h[1-6]|li|tr)>', '\n', text, flags=re.IGNORECASE)
        
        # 移除所有HTML标签
        text = re.sub(r'<[^>]+>', '', text)
        
        # 解码HTML实体
        import html as html_module
        text = html_module.unescape(text)
        
        # 清理多余空白
        text = re.sub(r'\n\s*\n', '\n\n', text)  # 保留段落间距
        text = re.sub(r'[ \t]+', ' ', text)  # 合并连续空格
        text = text.strip()
        
        return text
    
    def _parse_post_content(self, page, post_id: str, post_url: str) -> Optional[MainPost]:
        """解析帖子主体内容"""
        try:
            # 提取标题 - 淘股吧标题通常在h1或特定class中
            title = ""
            title_selectors = ['h1', '.post-title', '.article-title', '#b_subject', '.title']
            for selector in title_selectors:
                title_elem = page.css(selector).first
                if title_elem:
                    title = title_elem.text.get().strip()
                    if title:
                        break
            
            # 提取内容 - 淘股吧正文通常在 .p_coten 或 .post-content 中
            content = ""
            content_html = ""
            content_selectors = ['.p_coten', '.post-content', '.article-content', '.content', '[class*="content"]']
            for selector in content_selectors:
                content_elem = page.css(selector).first
                if content_elem:
                    # 获取完整HTML内容
                    content_html = content_elem.html_content.get()
                    # 从HTML中提取纯文本
                    content = self._html_to_text(content_html)
                    if content:
                        break
            
            # 提取作者信息
            # 优先从 JavaScript 变量或特定元素中提取，避免匹配到评论者
            author_name = ""
            author_id = None
            
            # 方法1: 从页面脚本中的 creatorName_var 提取
            try:
                page_text = page.text.get()
                creator_match = re.search(r'creatorName_var\s*=\s*"([^"]+)"', page_text)
                if creator_match:
                    author_name = creator_match.group(1).strip()
                creator_id_match = re.search(r'creator_id_var\s*=\s*"(\d+)"', page_text)
                if creator_id_match:
                    author_id = creator_id_match.group(1)
            except:
                pass
            
            # 方法2: 从 #gioMsg 元素的 username 属性提取
            if not author_name:
                try:
                    gio_elem = page.css('#gioMsg').first
                    if gio_elem:
                        author_name = gio_elem.attrib.get('username', '').strip()
                        if not author_id:
                            author_id = gio_elem.attrib.get('userid')
                except:
                    pass
            
            # 方法3: 从帖子作者区域提取（避免评论者）
            if not author_name:
                # 使用更具体的选择器，优先匹配帖子作者区域
                author_selectors = [
                    '.right-data-user a[href*="/blog/"]',  # 右侧作者信息区
                    '.data-userid a[href*="/blog/"]',      # 帖子头部作者
                    '.author-name',
                    '.p_tationl span'
                ]
                for selector in author_selectors:
                    author_elem = page.css(selector).first
                    if author_elem:
                        author_name = author_elem.text.get().strip()
                        if author_name:
                            # 尝试从链接中提取作者ID
                            href = author_elem.attrib.get('href', '')
                            blog_match = re.search(r'/blog/(\d+)', href)
                            if blog_match and not author_id:
                                author_id = blog_match.group(1)
                            break
            
            # 方法4: 从页面标题提取作为备选
            if not author_name:
                try:
                    title_elem = page.css('title').first
                    if title_elem:
                        title_text = title_elem.text.get()
                        # 标题格式: "标题_用户名_淘股吧"
                        match = re.search(r'_(.+?)_淘股吧', title_text)
                        if match:
                            author_name = match.group(1).strip()
                except:
                    pass
            
            # 提取作者头像
            author_avatar = None
            avatar_selectors = ['.author-avatar img', '.user-avatar img', '.avatar img']
            for selector in avatar_selectors:
                avatar_elem = page.css(selector).first
                if avatar_elem:
                    author_avatar = avatar_elem.attrib.get('src')
                    break
            
            # 提取统计数据
            view_count = 0
            comment_count = 0
            like_count = 0
            
            # 浏览数
            view_selectors = ['#totalViewNum', '.view-count', '.view-num', '[class*="view"]']
            for selector in view_selectors:
                view_elem = page.css(selector).first
                if view_elem:
                    try:
                        view_count = int(view_elem.text.get().replace(',', '').replace(' ', '') or 0)
                        break
                    except:
                        pass
            
            # 评论数
            comment_selectors = ['#replyNum', '.comment-count', '.reply-count', '[class*="reply"]']
            for selector in comment_selectors:
                comment_elem = page.css(selector).first
                if comment_elem:
                    try:
                        comment_count = int(comment_elem.text.get().replace(',', '').replace(' ', '') or 0)
                        break
                    except:
                        pass
            
            # 点赞/加油数
            like_selectors = ['.like-count', '.cheer-count', '.praise-count', '[class*="like"]']
            for selector in like_selectors:
                like_elem = page.css(selector).first
                if like_elem:
                    try:
                        like_count = int(like_elem.text.get().replace(',', '').replace(' ', '') or 0)
                        break
                    except:
                        pass
            
            # 提取发布时间
            publish_time = None
            
            # 方法1: 从页面HTML中直接提取时间（最可靠）
            try:
                page_html = page.html_content.get()
                # 查找时间格式: 2026-03-19 18:52
                time_match = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', page_html)
                if time_match:
                    publish_time = self._parse_time(time_match.group(1))
                    if publish_time:
                        logger.info(f"Parsed publish time from page HTML: {publish_time}")
            except Exception as e:
                logger.debug(f"Error parsing time from page HTML: {e}")
                pass
            
            # 方法2: 从 .article-data 中提取（淘股吧帖子页面）
            if not publish_time:
                try:
                    article_data = page.css('.article-data').first
                    if article_data:
                        # 获取所有 span 的文本
                        spans = article_data.css('span')
                        for span in spans:
                            text = span.text.get().strip()
                            # 匹配时间格式: 2026-03-19 18:52
                            parsed = self._parse_time(text)
                            if parsed:
                                publish_time = parsed
                                logger.info(f"Parsed publish time from article-data: {publish_time}")
                                break
                except Exception as e:
                    logger.debug(f"Error parsing time from article-data: {e}")
                    pass
            
            # 如果都解析失败，不设置时间（让上层使用列表页的时间）
            if not publish_time:
                logger.warning(f"Could not parse publish time for post {post_id}, will use list page time")
            
            post = MainPost(
                post_id=post_id,
                title=title,
                content=content,
                content_html=content_html,
                author_id=author_id,
                author_name=author_name,
                author_avatar=author_avatar,
                view_count=view_count,
                comment_count=comment_count,
                like_count=like_count,
                publish_time=publish_time,
                url=post_url
            )
            
            return post
            
        except Exception as e:
            logger.error(f"Error parsing post content: {e}")
            return None
    
    def _parse_comments(self, page, post_id: str = None, post_url: str = None) -> List[CommentNode]:
        """
        解析评论树 - 支持多页抓取，带最大数量限制
        
        Args:
            page: 第一页页面对象
            post_id: 帖子ID
            post_url: 帖子URL
        
        Returns:
            顶层评论节点列表（每个节点包含子评论树）
        """
        all_comments = []
        max_comments = self.max_comments
        
        # 如果 max_comments 为 0 或负数，表示不抓取评论
        if max_comments <= 0:
            logger.info("Comment crawling disabled (max_comments <= 0)")
            return []
        
        # 解析第一页评论
        first_page_comments = self._parse_single_page_comments(page)
        all_comments.extend(first_page_comments)
        
        # 检查是否已达到最大限制
        if len(all_comments) >= max_comments:
            logger.info(f"Reached max comments limit ({max_comments}) after first page")
            return all_comments[:max_comments]
        
        # 如果第一页有50条评论（达到上限），说明可能有更多页
        if len(first_page_comments) >= 50 and post_id:
            logger.info(f"First page has {len(first_page_comments)} comments, checking for more pages... (max: {max_comments})")
            
            # 抓取后续页面
            page_num = 2
            max_pages = 20  # 最多抓取20页，防止无限循环
            
            while page_num <= max_pages:
                # 计算还需要抓取多少条评论
                remaining = max_comments - len(all_comments)
                if remaining <= 0:
                    logger.info(f"Reached max comments limit ({max_comments}), stopping")
                    break
                
                page_comments = self._fetch_comment_page(post_id, page_num, remaining)
                
                if not page_comments:
                    logger.info(f"No more comments on page {page_num}, stopping")
                    break
                
                all_comments.extend(page_comments)
                logger.info(f"Fetched page {page_num}: {len(page_comments)} comments (total: {len(all_comments)}/{max_comments})")
                
                # 如果这一页少于50条，说明是最后一页
                if len(page_comments) < 50:
                    break
                
                # 检查是否已达到最大限制
                if len(all_comments) >= max_comments:
                    logger.info(f"Reached max comments limit ({max_comments}), stopping")
                    break
                
                page_num += 1
        
        # 确保不超过最大限制
        if len(all_comments) > max_comments:
            all_comments = all_comments[:max_comments]
        
        logger.info(f"Total comments parsed: {len(all_comments)} (max: {max_comments})")
        return all_comments
    
    def _parse_single_page_comments(self, page) -> List[CommentNode]:
        """解析单页评论"""
        comments = []
        
        # 淘股吧评论选择器 - 基于实际页面结构
        # 评论列表在 .comment-lists.list-reply 容器中
        # 每个评论是 .comment-data 元素
        comment_list = page.css('.comment-lists.list-reply').first
        
        if comment_list:
            comment_elements = comment_list.css('.comment-data')
            logger.debug(f"Found {len(comment_elements)} comments in .comment-lists.list-reply")
        else:
            # 备用选择器
            comment_elements = page.css('.comment-data')
            logger.debug(f"Found {len(comment_elements)} comments with .comment-data")
        
        for idx, elem in enumerate(comment_elements, 1):
            try:
                comment = self._parse_single_comment(elem, idx)
                if comment:
                    comments.append(comment)
                    self.stats["comments_crawled"] += 1
            except Exception as e:
                logger.warning(f"Error parsing comment: {e}")
                continue
        
        return comments
    
    def _fetch_comment_page(self, post_id: str, page_num: int, max_to_fetch: int = 50) -> List[CommentNode]:
        """
        抓取指定页码的评论
        
        Args:
            post_id: 帖子ID
            page_num: 页码（从2开始，因为第1页已经在主页面抓取了）
            max_to_fetch: 最多抓取多少条评论（用于控制总数）
        
        Returns:
            该页的评论列表
        """
        # 淘股吧评论分页URL格式: /a/{post_id}-{page_num}
        page_url = f"{self.BASE_URL}/a/{post_id}-{page_num}"
        
        try:
            logger.debug(f"Fetching comment page {page_num}: {page_url}")
            page = self._get_page(page_url)
            
            if not page:
                logger.warning(f"Failed to fetch page {page_num}")
                return []
            
            # 解析该页评论
            comments = []
            comment_list = page.css('.comment-lists.list-reply').first
            
            if comment_list:
                comment_elements = comment_list.css('.comment-data')
            else:
                comment_elements = page.css('.comment-data')
            
            # 计算楼层偏移量（每页50条）
            floor_offset = (page_num - 1) * 50
            
            for idx, elem in enumerate(comment_elements, 1):
                # 检查是否已达到本次抓取上限
                if len(comments) >= max_to_fetch:
                    break
                
                try:
                    comment = self._parse_single_comment(elem, floor_offset + idx)
                    if comment:
                        comments.append(comment)
                        self.stats["comments_crawled"] += 1
                except Exception as e:
                    logger.warning(f"Error parsing comment on page {page_num}: {e}")
                    continue
            
            logger.debug(f"Page {page_num}: parsed {len(comments)} comments")
            return comments
            
        except Exception as e:
            logger.error(f"Error fetching comment page {page_num}: {e}")
            return []
    
    def _parse_single_comment(self, elem, floor_number: int) -> Optional[CommentNode]:
        """
        解析单条评论（淘股吧 .comment-data 结构）
        
        结构示例：
        <div class="comment-data user_9226837" id="reply_9226837_1">
            <div class="comment-data-left">
                <img class="comment-data-user-img" data-original="...">
            </div>
            <div class="comment-data-right">
                <div class="comment-data-user">
                    <a class="user-name">作者名</a>
                </div>
                <div class="comment-data-text">评论内容</div>
                <div class="comment-data-button">
                    <span>沙发</span>  <!-- 楼层标记 -->
                </div>
            </div>
        </div>
        """
        try:
            # 提取评论ID
            comment_id = elem.attrib.get('id') or f"comment_{floor_number}"
            
            # 提取作者名
            author_name = ""
            author_elem = elem.css('.user-name').first
            if author_elem:
                author_name = author_elem.text.get().strip()
            
            # 提取作者ID
            author_id = None
            author_link = elem.css('a[href*="/blog/"]').first
            if author_link:
                href = author_link.attrib.get('href')
                match = re.search(r'/blog/(\d+)', href)
                if match:
                    author_id = match.group(1)
            
            # 如果没有从链接中提取到作者ID，尝试从class中提取
            if not author_id:
                class_attr = elem.attrib.get('class', '')
                match = re.search(r'user_(\d+)', class_attr)
                if match:
                    author_id = match.group(1)
            
            # 提取作者头像
            author_avatar = None
            avatar_elem = elem.css('img.comment-data-user-img').first
            if avatar_elem:
                # 淘股吧使用 data-original 存储真实图片地址
                author_avatar = avatar_elem.attrib.get('data-original') or avatar_elem.attrib.get('src')
            
            # 提取评论内容 - 使用HTML转文本方法获取完整内容
            content = ""
            content_html = ""
            content_elem = elem.css('.comment-data-text').first
            if content_elem:
                content_html = content_elem.html_content.get()
                content = self._html_to_text(content_html)
            
            # 提取发布时间
            publish_time = None
            
            # 方法1: 从 .pcyclspan 中提取（淘股吧评论时间）
            time_elem = elem.css('.pcyclspan').first
            if time_elem:
                time_text = time_elem.text.get().strip()
                publish_time = self._parse_time(time_text)
            
            # 方法2: 使用传统选择器
            if not publish_time:
                time_elem = elem.css('.comment-data-time, .time, .date').first
                if time_elem:
                    time_text = time_elem.text.get().strip()
                    publish_time = self._parse_time(time_text)
            
            # 提取点赞数
            like_count = 0
            like_elem = elem.css('.useful-num, .like-count, [class*="useful"]').first
            if like_elem:
                like_text = like_elem.text.get()
                like_match = re.search(r'(\d+)', like_text)
                if like_match:
                    like_count = int(like_match.group(1))
            
            # 提取楼层信息（沙发、板凳、地板等）
            floor_text = ""
            floor_elem = elem.css('.comment-data-button span').first
            if floor_elem:
                floor_text = floor_elem.text.get().strip()
            
            # 淘股吧评论是平铺结构，没有明显的楼中楼
            # 如果有引用回复，会在内容中体现
            children = []
            
            comment = CommentNode(
                comment_id=comment_id,
                parent_id=None,  # 顶层评论
                author_id=author_id,
                author_name=author_name,
                author_avatar=author_avatar,
                content=content,
                publish_time=publish_time or datetime.now(),
                like_count=like_count,
                reply_count=len(children),
                floor_number=floor_number,
                children=children,
                extra_data={
                    "floor_text": floor_text,  # 沙发、板凳、地板等
                    "content_html": content_html,  # 原始HTML内容
                }
            )
            
            return comment
            
        except Exception as e:
            logger.warning(f"Error parsing comment element: {e}")
            return None
    
    def crawl_blogger(
        self,
        username: str,
        user_id: Optional[str] = None,
        days: int = 7,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_posts: int = 100,
        max_comments: Optional[int] = None
    ) -> CrawlResult:
        """
        爬取指定博主的帖子
        
        Args:
            username: 博主用户名
            user_id: 可选的用户ID，如果已知
            days: 爬取最近多少天的帖子（当start_date未指定时生效）
            start_date: 开始日期
            end_date: 结束日期
            max_posts: 最大帖子数
            max_comments: 每篇帖子最大抓取评论数，None表示使用默认值，0或负数表示不抓取评论
            
        Returns:
            爬取结果
        """
        logger.info(f"Starting crawl for blogger: {username}")
        
        # 更新最大评论数（如果提供了）
        if max_comments is not None:
            self.max_comments = max_comments
        
        if self.max_comments <= 0:
            logger.info("Comment crawling disabled (max_comments <= 0)")
        else:
            logger.info(f"Max comments per post: {self.max_comments}")

        # 确定时间范围
        if end_date is None:
            end_date = datetime.now()
            logger.info(f"no end_date")
        if start_date is None:
            start_date = end_date - timedelta(days=days)
            logger.info(f"no start_date")

        logger.info(f"Fetching time from {start_date.date()} to {end_date.date()}")

        # 获取博主信息
        if not user_id:
            raise ValueError(f"需要用户ID才能爬取，请提供 {username} 的用户ID")
        
        blogger = self.get_blogger_info(user_id, username)
        if not blogger:
            blogger = BloggerInfo(user_id=user_id, username=username)
        
        logger.info(f"Found blogger: {blogger.username} (ID: {blogger.user_id})")
        
        # 获取帖子列表
        post_list = self.get_blogger_posts(
            blogger.user_id,
            start_date=start_date,
            end_date=end_date
        )
        
        logger.info(f"Found {len(post_list)} posts in date range")
        
        # 限制帖子数量
        post_list = post_list[:max_posts]
        
        # 获取每个帖子的详情（并发抓取）
        posts = []
        
        def fetch_single_post(post_info):
            """抓取单个帖子的详情"""
            post = self.get_post_detail(
                post_info['post_id'],
                post_info['url']
            )
            if post:
                # 合并列表页获取的信息
                post.title = post_info.get('title', post.title)
                post.view_count = post_info.get('view_count', post.view_count)
                post.comment_count = post_info.get('comment_count', post.comment_count)
                post.post_type = post_info.get('post_type', post.post_type)
                
                # 时间处理：优先使用详情页的时间（如果有），否则使用列表页的时间
                list_time = post_info.get('publish_time')
                detail_time = post.publish_time
                
                # 检查详情页时间是否是今天（脚本运行时间）
                today = datetime.now().date()
                if detail_time and detail_time.date() != today:
                    # 详情页时间不是今天，使用详情页的完整时间
                    post.publish_time = detail_time
                elif list_time:
                    # 详情页时间是今天（脚本运行时间）或不存在，使用列表页时间
                    post.publish_time = list_time
                
                return post
            return None
        
        # 使用线程池并发抓取（最多3个并发）
        max_workers = 3
        logger.info(f"Fetching {len(post_list)} posts with {max_workers} concurrent workers...")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_single_post, post_info): post_info for post_info in post_list}
            
            for future in as_completed(futures):
                try:
                    post = future.result()
                    if post:
                        posts.append(post)
                        logger.info(f"Fetched post: {post.title[:30]}...")
                except Exception as e:
                    post_info = futures[future]
                    logger.warning(f"Failed to fetch post {post_info.get('post_id')}: {e}")
        
        # 按原始顺序排序
        post_ids_order = {p['post_id']: i for i, p in enumerate(post_list)}
        posts.sort(key=lambda p: post_ids_order.get(p.post_id, float('inf')))
        
        # 构建结果
        total_comments = sum(self._count_comments(c) for p in posts for c in p.comments)
        
        result = CrawlResult(
            blogger=blogger,
            posts=posts,
            start_date=start_date,
            end_date=end_date,
            total_posts=len(posts),
            total_comments=total_comments
        )
        
        # 保存完整结果
        json_path = self.storage.save_to_json(result)
        md_path = self.storage.save_to_markdown(result)
        
        # 如果启用了向量数据库，将数据向量化存储
        vector_stats = None
        if self.enable_vector_store and self.vectorizer:
            logger.info("Vectorizing crawl result to vector store...")
            try:
                result_dict = json.loads(result.model_dump_json())
                vector_stats = self.vectorizer.process_crawl_result(result_dict)
                logger.info(f"Vectorization complete: {vector_stats}")
            except Exception as e:
                logger.error(f"Error vectorizing crawl result: {e}")
        
        logger.info(f"Crawl completed!")
        logger.info(f"  - Posts: {len(posts)}")
        logger.info(f"  - Comments: {total_comments}")
        logger.info(f"  - JSON saved: {json_path}")
        logger.info(f"  - Markdown saved: {md_path}")
        if vector_stats:
            logger.info(f"  - Vector documents: {vector_stats.get('total_documents', 0)}")
        
        return result
    
    def clear_vector_store(self) -> bool:
        """
        清空向量数据库中的所有数据
        
        Returns:
            是否成功清空
        """
        if not self.enable_vector_store or not self.vectorizer:
            logger.warning("Vector store is not enabled")
            return False
        
        try:
            result = self.vectorizer.clear_vector_store()
            if result:
                logger.info("Vector store cleared successfully")
            return result
        except Exception as e:
            logger.error(f"Error clearing vector store: {e}")
            return False
    
    def get_vector_store_stats(self) -> Dict[str, Any]:
        """
        获取向量数据库统计信息
        
        Returns:
            统计信息字典
        """
        if not self.enable_vector_store or not self.vectorizer:
            return {"error": "Vector store is not enabled"}
        
        return self.vectorizer.get_stats()


# 便捷的调用函数
def crawl_blogger(
    username: str,
    user_id: Optional[str] = None,
    days: int = 7,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    max_posts: int = 100,
    max_comments: int = 250,
    output_dir: str = "output",
    enable_vector_store: bool = False,
    vector_store_config: Optional[Dict[str, Any]] = None,
    fast_mode: bool = True
) -> CrawlResult:
    """
    便捷函数：爬取指定博主的帖子
    
    Args:
        username: 博主用户名
        user_id: 可选的用户ID
        days: 爬取最近多少天的帖子
        start_date: 开始日期
        end_date: 结束日期
        max_posts: 最大帖子数
        max_comments: 每篇帖子最大抓取评论数，默认250
        output_dir: 输出目录
        enable_vector_store: 是否启用向量数据库
        vector_store_config: 向量数据库配置
        fast_mode: 快速模式，减少页面等待时间
        
    Returns:
        爬取结果
    """
    crawler = TaogubaCrawler(
        output_dir=output_dir,
        max_comments=max_comments,
        enable_vector_store=enable_vector_store,
        vector_store_config=vector_store_config,
        fast_mode=fast_mode
    )
    return crawler.crawl_blogger(
        username=username,
        user_id=user_id,
        days=days,
        start_date=start_date,
        end_date=end_date,
        max_posts=max_posts,
        max_comments=max_comments
    )
