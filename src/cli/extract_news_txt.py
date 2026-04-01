"""
从 news/ 目录下读取 all_bloggers JSON 文件，提取所有帖子内容汇总为一个 txt 文件
输出到 output/news_input/ 目录
"""

import json
from datetime import datetime
from pathlib import Path

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent

NEWS_DIR = PROJECT_ROOT / "output" / "news"
OUTPUT_DIR = PROJECT_ROOT / "output" / "news_input"


def main():
    # 查找所有匹配的 JSON 文件
    json_files = sorted(NEWS_DIR.glob("all_bloggers_*.json"))

    if not json_files:
        print(f"在 {NEWS_DIR} 下未找到 all_bloggers_*.json 文件")
        return

    print(f"找到 {len(json_files)} 个 all_bloggers JSON 文件")

    all_posts = []
    crawl_info = None

    for json_file in json_files:
        print(f"  读取: {json_file.name}")
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if crawl_info is None and "crawl_info" in data:
            crawl_info = data["crawl_info"]

        for post in data.get("posts", []):
            all_posts.append(post)

    print(f"共提取 {len(all_posts)} 篇帖子")

    # 按发布时间倒序
    all_posts.sort(
        key=lambda p: p.get("publish_time") or "0000-01-01T00:00:00",
        reverse=True,
    )

    # 生成 txt
    lines = []

    if crawl_info:
        lines.append("=" * 60)
        lines.append(f"淘股吧多博主帖子汇总")
        lines.append(f"抓取时间: {crawl_info.get('crawl_time', '未知')}")
        start = crawl_info.get("start_date", "")
        end = crawl_info.get("end_date", "")
        if start and end:
            lines.append(f"时间范围: {start[:10]} 至 {end[:10]}")
        bloggers = crawl_info.get("bloggers", [])
        lines.append(f"博主: {', '.join(bloggers)}")
        lines.append(f"总帖数: {len(all_posts)}")
        lines.append("=" * 60)
        lines.append("")

    for idx, post in enumerate(all_posts, 1):
        title = post.get("title", "无标题")
        author = post.get("author_name", "未知")
        pub_time = post.get("publish_time", "未知时间")
        content = post.get("content", "").strip()

        lines.append(f"【第{idx}篇】")
        lines.append(f"标题: {title}")
        lines.append(f"作者: {author}")
        lines.append(f"时间: {pub_time}")
        lines.append("-" * 40)
        if content:
            lines.append(content)
        else:
            lines.append("（无正文内容）")
        lines.append("")
        lines.append("=" * 60)
        lines.append("")

    # 写入文件
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = OUTPUT_DIR / f"news_input_{timestamp}.txt"

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n已保存到: {output_file}")


if __name__ == "__main__":
    main()
