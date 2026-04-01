"""
淘股吧多博主批量爬虫 - 仅抓取帖子（不存入向量数据库）
支持配置多个博主，批量抓取帖子并合并保存到 output/news/ 目录下的统一 JSON/MD 文件
"""

import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from src.crawler.taoguba_crawler import TaogubaCrawler
from src.crawler.storage import DataStorage, DateTimeEncoder
from src.crawler.models import BloggerInfo, CrawlResult

# 获取项目根目录（基于当前文件位置：src/cli/crawl_multi.py -> 项目根目录）
PROJECT_ROOT = Path(__file__).parent.parent.parent

# 配置日志 - 日志文件存放在项目根目录的 logs/ 下
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add(PROJECT_ROOT / "logs" / "crawler_multi_{time}.log", rotation="10 MB", level="DEBUG")


def main():
    """
    主函数：批量爬取多个博主的帖子（仅保存到本地文件，不存入向量数据库）

    所有博主的帖子合并到一个 JSON 文件和一个 MD 文件中，存放到 output/news/ 目录下。
    """

    # ============ 配置区域 ============

    # 博主列表 - 在此添加/删除要抓取的博主
    BLOGGERS = [
        {"username": "jl韭菜抄家",   "user_id": "7737030"},
        {"username": "延边刺客",     "user_id": "5894557"},
        {"username": "主升龙头真经",  "user_id": "2776047"},
        {"username": "小宝1105",    "user_id": "9239701"},
        {"username": "短狙作手",     "user_id": "8423616"},
        {"username": "小土堆爆金币",  "user_id": "9259508"},
        {"username": "涅槃重生2018", "user_id": "2888425"},
        {"username": "米开朗基瑞",   "user_id": "11056656"},
    ]

    # 时间范围配置
    DAYS = 7  # 爬取最近多少天的帖子

    # 或者指定具体日期范围（会覆盖 days 参数）
    START_DATE = datetime(2026, 3, 28)
    END_DATE = datetime(2026, 3, 30)

    # 最大帖子数限制（每个博主）
    MAX_POSTS = 100

    # 每篇帖子最大评论数限制
    # 设为 -1 或 0 表示不抓取评论（只抓取主帖）
    # 设为 250 表示最多抓取 250 条评论
    MAX_COMMENTS = 0

    # 输出目录 - 存放在项目根目录的 output/news/ 下
    OUTPUT_DIR = PROJECT_ROOT / "output" / "news"

    # ==================================

    print("=" * 60)
    print("淘股吧多博主批量爬虫 - 仅抓取模式")
    print("=" * 60)
    print(f"博主数量: {len(BLOGGERS)}")
    print(f"博主列表: {', '.join(b['username'] for b in BLOGGERS)}")

    if START_DATE and END_DATE:
        print(f"时间范围: {START_DATE.date()} 至 {END_DATE.date()}")
    else:
        end = END_DATE or datetime.now()
        start = end - timedelta(days=DAYS)
        print(f"时间范围: 最近{DAYS}天 ({start.date()} 至 {end.date()})")

    print(f"每博主最大帖子数: {MAX_POSTS}")
    print(f"每篇最大评论数: {MAX_COMMENTS}")
    print(f"输出目录: {OUTPUT_DIR}")
    print("=" * 60)
    print()

    # 创建输出目录
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 创建共享的爬虫实例（统一输出到 output/news/）
    crawler = TaogubaCrawler(
        output_dir=str(OUTPUT_DIR),
        max_comments=MAX_COMMENTS,
        enable_vector_store=False,
    )

    # 汇总数据
    all_results = []  # 每个博主的 CrawlResult
    all_posts = []    # 所有帖子平铺
    total_stats = {
        "success": [],
        "failed": [],
        "total_posts": 0,
        "total_comments": 0,
    }

    for idx, blogger_cfg in enumerate(BLOGGERS, 1):
        username = blogger_cfg["username"]
        user_id = blogger_cfg["user_id"]

        print(f"\n{'─' * 60}")
        print(f"[{idx}/{len(BLOGGERS)}] 正在抓取: {username} (ID: {user_id})")
        print(f"{'─' * 60}")

        try:
            # 记录爬取前 output_dir 下已有的文件，用于事后清理 crawler 自动生成的单博主文件
            existing_files = set(OUTPUT_DIR.iterdir()) if OUTPUT_DIR.exists() else set()

            result = crawler.crawl_blogger(
                username=username,
                user_id=user_id,
                days=DAYS,
                start_date=START_DATE,
                end_date=END_DATE,
                max_posts=MAX_POSTS,
                max_comments=MAX_COMMENTS,
            )

            # 清理 crawler.crawl_blogger() 自动为该博主生成的单独 json/md 文件
            for f in OUTPUT_DIR.iterdir():
                if f not in existing_files and f.suffix in ('.json', '.md'):
                    f.unlink()
                    logger.debug(f"Cleaned up per-blogger file: {f}")

            all_results.append(result)
            all_posts.extend(result.posts)

            total_stats["success"].append(username)
            total_stats["total_posts"] += result.total_posts
            total_stats["total_comments"] += result.total_comments

            print(f"\n  博主: {result.blogger.username}")
            if result.blogger.nickname:
                print(f"  昵称: {result.blogger.nickname}")
            print(f"  主帖: {result.total_posts} | 评论: {result.total_comments}")

        except ValueError as e:
            print(f"  错误: {e}")
            total_stats["failed"].append(username)
            logger.warning(f"Failed to crawl {username}: {e}")

        except Exception as e:
            print(f"  异常: {e}")
            total_stats["failed"].append(username)
            logger.exception(f"Error crawling {username}")

    # 按发布时间倒序排列所有帖子
    all_posts.sort(key=lambda p: p.publish_time or datetime.min, reverse=True)

    # 合并保存为一个 JSON 文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    date_range = ""
    if START_DATE and END_DATE:
        date_range = f"{START_DATE.strftime('%Y%m%d')}_{END_DATE.strftime('%Y%m%d')}"
    else:
        date_range = f"recent_{DAYS}d"

    json_filename = f"all_bloggers_{date_range}_{timestamp}.json"
    md_filename = f"all_bloggers_{date_range}_{timestamp}.md"

    # --- 保存 JSON ---
    json_data = {
        "crawl_info": {
            "crawl_time": datetime.now().isoformat(),
            "start_date": START_DATE.isoformat() if START_DATE else None,
            "end_date": END_DATE.isoformat() if END_DATE else None,
            "bloggers": [b["username"] for b in BLOGGERS],
            "success": total_stats["success"],
            "failed": total_stats["failed"],
            "total_posts": total_stats["total_posts"],
            "total_comments": total_stats["total_comments"],
        },
        "bloggers": [
            {
                "username": r.blogger.username,
                "nickname": r.blogger.nickname,
                "user_id": r.blogger.user_id,
                "followers_count": r.blogger.followers_count,
                "posts_count": r.total_posts,
                "comments_count": r.total_comments,
            }
            for r in all_results
        ],
        "posts": [
            {
                "post_id": p.post_id,
                "title": p.title,
                "content": p.content,
                "author_name": p.author_name,
                "author_id": p.author_id,
                "publish_time": p.publish_time.isoformat() if p.publish_time else None,
                "url": p.url,
                "view_count": p.view_count,
                "comment_count": p.comment_count,
                "like_count": p.like_count,
                "post_type": p.post_type,
                "comments": [
                    {
                        "comment_id": c.comment_id,
                        "author_name": c.author_name,
                        "content": c.content,
                        "publish_time": c.publish_time.isoformat() if c.publish_time else None,
                        "like_count": c.like_count,
                    }
                    for c in p.comments
                ],
            }
            for p in all_posts
        ],
    }

    json_path = OUTPUT_DIR / json_filename
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)

    # --- 保存 Markdown ---
    md_lines = []
    md_lines.append(f"# 淘股吧多博主帖子汇总")
    md_lines.append("")
    md_lines.append("## 抓取信息")
    md_lines.append(f"- **抓取时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if START_DATE and END_DATE:
        md_lines.append(f"- **时间范围**: {START_DATE.date()} 至 {END_DATE.date()}")
    md_lines.append(f"- **博主数量**: {len(BLOGGERS)}（成功 {len(total_stats['success'])}，失败 {len(total_stats['failed'])}）")
    md_lines.append(f"- **总帖数**: {total_stats['total_posts']}")
    md_lines.append(f"- **总评论数**: {total_stats['total_comments']}")
    if total_stats["failed"]:
        md_lines.append(f"- **失败博主**: {', '.join(total_stats['failed'])}")
    md_lines.append("")

    # 各博主统计
    md_lines.append("## 各博主统计")
    for r in all_results:
        name = r.blogger.nickname or r.blogger.username
        md_lines.append(f"- **{name}**: {r.total_posts} 篇帖子, {r.total_comments} 条评论")
    md_lines.append("")

    # 所有帖子
    md_lines.append("## 帖子详情")
    md_lines.append("")

    for idx, post in enumerate(all_posts, 1):
        md_lines.append(f"### {idx}. {post.title}")
        md_lines.append("")
        time_str = post.publish_time.strftime('%Y-%m-%d %H:%M') if post.publish_time else "未知时间"
        md_lines.append(f"**作者**: {post.author_name or '未知'} | **发布时间**: {time_str}")
        md_lines.append(f"**浏览**: {post.view_count} | **评论**: {post.comment_count} | **点赞**: {post.like_count}")
        if post.post_type:
            md_lines.append(f"**类型**: {post.post_type}")
        md_lines.append(f"**链接**: {post.url}")
        md_lines.append("")
        md_lines.append("#### 正文")
        md_lines.append(post.content or "（无内容）")
        md_lines.append("")

        if post.comments:
            md_lines.append(f"#### 评论 ({len(post.comments)}条)")
            md_lines.append("")
            for comment in post.comments:
                c_time = comment.publish_time.strftime('%m-%d %H:%M') if comment.publish_time else ""
                md_lines.append(f"- **{comment.author_name}** ({c_time})")
                for line in comment.content.strip().split('\n'):
                    md_lines.append(f"  > {line}")
                md_lines.append("")

        md_lines.append("---")
        md_lines.append("")

    md_path = OUTPUT_DIR / md_filename
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(md_lines))

    # 打印汇总报告
    print()
    print("=" * 60)
    print("批量爬取完成!")
    print("=" * 60)
    print(f"成功: {len(total_stats['success'])} 个博主")
    if total_stats["failed"]:
        print(f"失败: {len(total_stats['failed'])} 个博主: {', '.join(total_stats['failed'])}")
    print(f"总帖子数: {total_stats['total_posts']}")
    print(f"总评论数: {total_stats['total_comments']}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    print(f"日志文件: {PROJECT_ROOT / 'logs'}/")
    print("=" * 60)


if __name__ == "__main__":
    main()
