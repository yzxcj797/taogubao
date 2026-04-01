"""
提取博主观点
读取output下的JSON文件，提取博主的所有观点，保存为纯文本
"""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from loguru import logger

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
VIEW_DIR = OUTPUT_DIR / "view"


def clean_text(text: str) -> str:
    """清理文本内容"""
    if not text:
        return ""
    # 移除HTML标签
    text = re.sub(r'<[^>]+>', '', text)
    # 移除多余空白
    text = re.sub(r'\s+', ' ', text)
    # 移除特殊字符
    text = text.replace('\xa0', ' ').replace('\u3000', ' ')
    return text.strip()


def extract_post_opinions(post_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    从帖子数据中提取观点
    
    Returns:
        观点列表，每个观点包含日期、标题、内容
    """
    opinions = []
    
    # 提取帖子基本信息
    publish_time = post_data.get('publish_time', '')
    if publish_time:
        # 转换日期格式
        try:
            if isinstance(publish_time, str):
                dt = datetime.fromisoformat(publish_time.replace('Z', '+00:00'))
                date_str = dt.strftime('%Y-%m-%d')
            else:
                date_str = publish_time.strftime('%Y-%m-%d') if hasattr(publish_time, 'strftime') else str(publish_time)[:10]
        except:
            date_str = str(publish_time)[:10]
    else:
        date_str = '未知日期'
    
    title = clean_text(post_data.get('title', ''))
    content = clean_text(post_data.get('content', ''))
    
    # 构建观点
    opinion = {
        'date': date_str,
        'title': title,
        'content': content,
        'url': post_data.get('url', '')
    }
    opinions.append(opinion)
    
    return opinions


def process_json_file(json_path: Path):
    """
    处理单个JSON文件，返回 (blogger_name, opinions) 元组
    
    Returns:
        (博主名称, 观点列表)
    """
    opinions = []
    blogger_name = None
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 判断JSON结构
        if isinstance(data, dict):
            # 可能是单个帖子或包含posts数组
            if 'blogger' in data:
                # 博主数据格式（crawl_only 生成的格式）
                blogger_name = data.get('blogger', {}).get('username', '未知博主')
            elif 'crawl_info' in data:
                # crawl_multi 生成的汇总格式
                # 从 posts 中取第一个帖子的 author_name 作为博主名
                posts = data.get('posts', [])
                if posts:
                    blogger_name = posts[0].get('author_name', '未知博主')

            if 'posts' in data:
                posts = data.get('posts', [])
                if not blogger_name:
                    blogger_name = posts[0].get('author_name', '未知博主') if posts else '未知博主'
                logger.info(f"Processing {len(posts)} posts from {blogger_name}")
                for post in posts:
                    opinions.extend(extract_post_opinions(post))
            elif 'blogger' in data and 'username' in data.get('blogger', {}):
                # 单博主JSON格式
                blogger_name = data['blogger']['username']
                posts = data.get('posts', [])
                for post in posts:
                    opinions.extend(extract_post_opinions(post))
            else:
                # 单个帖子格式
                if not blogger_name:
                    blogger_name = data.get('author_name', '未知博主')
                opinions.extend(extract_post_opinions(data))
                
        elif isinstance(data, list):
            # 帖子列表格式
            for post in data:
                opinions.extend(extract_post_opinions(post))
        
        if not blogger_name:
            blogger_name = '未知博主'
        
        logger.info(f"Extracted {len(opinions)} opinions from {json_path.name} (blogger: {blogger_name})")
        
    except Exception as e:
        logger.error(f"Error processing {json_path}: {e}")
        return '未知博主', []
    
    return blogger_name, opinions


def save_opinions_to_text(opinions: List[Dict[str, str]], output_file: Path, blogger_name: str = "jl韭菜抄家"):
    """将观点保存为纯文本文件"""
    
    # 按日期排序
    opinions.sort(key=lambda x: x['date'])
    
    # 构建文本内容
    lines = []
    lines.append("=" * 80)
    lines.append(f"博主观点汇总 - {blogger_name}")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"观点数量: {len(opinions)}")
    lines.append("=" * 80)
    lines.append("")
    
    current_date = ""
    for i, opinion in enumerate(opinions, 1):
        date = opinion['date']
        
        # 日期分隔
        if date != current_date:
            current_date = date
            lines.append("")
            lines.append("-" * 80)
            lines.append(f"【{date}】")
            lines.append("-" * 80)
            lines.append("")
        
        # 添加观点
        title = opinion['title']
        content = opinion['content']
        url = opinion['url']
        
        if title:
            lines.append(f"标题: {title}")
        
        if content:
            lines.append(f"内容: {content}")
        
        if url:
            lines.append(f"链接: {url}")
        
        lines.append("")
    
    lines.append("=" * 80)
    lines.append(f"汇总完成 - 共 {len(opinions)} 条观点")
    lines.append("=" * 80)
    
    # 写入文件
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    logger.info(f"Saved {len(opinions)} opinions to {output_file}")


def main():
    """主函数"""
    print("=" * 60)
    print("博主观点提取工具")
    print("=" * 60)
    
    # 确保view目录存在
    VIEW_DIR.mkdir(parents=True, exist_ok=True)
    
    # 查找所有JSON文件
    json_files = list(OUTPUT_DIR.glob("**/*.json"))
    
    if not json_files:
        print(f"未在 {OUTPUT_DIR} 下找到JSON文件")
        return
    
    print(f"找到 {len(json_files)} 个JSON文件")
    print("-" * 60)
    
    # 按博主分类收集观点
    blogger_opinions: Dict[str, List[Dict[str, str]]] = {}
    
    for json_path in json_files:
        # 跳过view目录下的文件
        if "view" in str(json_path) or "analysis" in str(json_path) or "news_input" in str(json_path):
            continue
        
        print(f"处理: {json_path.name}")
        blogger_name, opinions = process_json_file(json_path)
        
        if opinions:
            if blogger_name not in blogger_opinions:
                blogger_opinions[blogger_name] = []
            blogger_opinions[blogger_name].extend(opinions)
            print(f"  -> {blogger_name}: {len(opinions)} 条观点")
        else:
            print(f"  -> 未提取到观点")
    
    # 按博主分别输出文件
    total_opinions = 0
    print()
    print("-" * 60)
    print("生成汇总文件:")
    print("-" * 60)
    
    for blogger_name, opinions in blogger_opinions.items():
        timestamp = datetime.now().strftime('%Y%m%d')
        output_name = f"{blogger_name}_观点汇总_{timestamp}.txt"
        output_path = VIEW_DIR / output_name
        
        save_opinions_to_text(opinions, output_path, blogger_name)
        total_opinions += len(opinions)
        print(f"  {blogger_name}: {len(opinions)} 条观点 -> {output_name}")
    
    print()
    print("=" * 60)
    print(f"完成! 共 {len(blogger_opinions)} 位博主，{total_opinions} 条观点")
    print(f"输出目录: {VIEW_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
