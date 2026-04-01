"""
淘股吧爬虫 - 仅抓取帖子（不存入向量数据库）
以"jl韭菜抄家"为例，抓取最近一周的帖子并保存到本地文件
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from src.crawler.taoguba_crawler import crawl_blogger, TaogubaCrawler

# 获取项目根目录（基于当前文件位置：src/cli/crawl_only.py -> 项目根目录）
PROJECT_ROOT = Path(__file__).parent.parent.parent

# 配置日志 - 日志文件存放在项目根目录的 logs/ 下
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add(PROJECT_ROOT / "logs" / "crawler_{time}.log", rotation="10 MB", level="DEBUG")


def main():
    """
    主函数：爬取指定博主的帖子（仅保存到本地文件，不存入向量数据库）
    
    你可以修改以下参数来自定义爬取行为：
    - username: 博主用户名（必需）
    - user_id: 用户ID（可选，如果知道可以加快爬取）
    - days: 爬取最近多少天的帖子
    - start_date/end_date: 指定日期范围
    - max_posts: 最大爬取帖子数
    - MAX_COMMENTS: 最大爬取评论数
    """

    # ============ 配置区域 ============

    # 目标博主用户名
    USERNAME = "短狙作手"
    USER_ID = "8423616"  # jl韭菜抄家的用户ID

    # USERNAME = "A拉神灯"
    # USER_ID = "5727139"  # A拉神灯的用户ID
    # 用户ID（如果知道的话，可以加快爬取速度）
    # 可以通过访问博主主页从URL中获取，格式：https://www.tgb.cn/blog/{user_id}
    # [{"jl韭菜抄家": "7737030"}, {"A拉神灯": "5727139"}, {"大曾子": "11808691"}, {"涅槃重生2018": "2888425"}, {"只核大学生": "11310249"},
    #  {"延边刺客": "5894557"}, {"主升龙头真经": "2776047"}, {"晋王殿下": "9512726"}, {"小u神": "8462463"}, {"小宝1105": "9239701"},
    #  {"狼王行千里": "2747572"}, {"短狙作手": "8423616"}]


    # 时间范围配置
    DAYS = 7  # 爬取最近7天的帖子

    # 或者指定具体日期范围（会覆盖days参数）
    # START_DATE = datetime(2026, 3, 13)
    # END_DATE = datetime(2026, 3, 20)
    # START_DATE = None
    # END_DATE = None
    START_DATE = datetime(2026, 1, 1)
    END_DATE = datetime(2026, 3, 27)

    # 最大帖子数限制
    MAX_POSTS = 100

    # 每篇帖子最大评论数限制
    # 设为 -1 或 0 表示不抓取评论（只抓取主帖）
    # 设为 250 表示最多抓取250条评论
    MAX_COMMENTS = 0

    # 输出目录 - 存放在项目根目录的 output/ 下
    OUTPUT_DIR = PROJECT_ROOT / "output"

    # ==================================

    print("=" * 60)
    print("淘股吧爬虫工具 - 仅抓取模式（不存入向量数据库）")
    print("=" * 60)
    print(f"目标博主: {USERNAME}")

    if START_DATE and END_DATE:
        print(f"时间范围: {START_DATE.date()} 至 {END_DATE.date()}")
    else:
        end = END_DATE or datetime.now()
        start = end - timedelta(days=DAYS)
        print(f"时间范围: 最近{DAYS}天 ({start.date()} 至 {end.date()})")

    print(f"最大帖子数: {MAX_POSTS}")
    print(f"每篇最大评论数: {MAX_COMMENTS}")
    print(f"向量数据库: 禁用（仅保存到本地文件）")
    print("=" * 60)
    print()

    try:
        # 执行爬取 - 不启用向量数据库
        result = crawl_blogger(
            username=USERNAME,
            user_id=USER_ID,
            days=DAYS,
            start_date=START_DATE,
            end_date=END_DATE,
            max_posts=MAX_POSTS,
            max_comments=MAX_COMMENTS,
            output_dir=OUTPUT_DIR,
            enable_vector_store=False  # 禁用向量数据库
        )

        # 打印结果摘要
        print()
        print("=" * 60)
        print("爬取完成!")
        print("=" * 60)
        print(f"博主: {result.blogger.username}")
        if result.blogger.nickname:
            print(f"昵称: {result.blogger.nickname}")
        if result.blogger.user_id:
            print(f"用户ID: {result.blogger.user_id}")
        print(f"粉丝数: {result.blogger.followers_count or '未知'}")
        print("-" * 60)
        print(f"主帖数量: {result.total_posts}")
        print(f"评论数量: {result.total_comments}")
        print(f"爬取时间: {result.crawl_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        # 打印帖子列表
        if result.posts:
            print()
            print("帖子列表:")
            print("-" * 60)
            for idx, post in enumerate(result.posts, 1):
                print(f"{idx}. {post.title}")
                print(f"   时间: {post.publish_time.strftime('%Y-%m-%d %H:%M')}")
                print(f"   浏览: {post.view_count} | 评论: {post.comment_count} | 点赞: {post.like_count}")
                print(f"   链接: {post.url}")
                print()

        print()
        print(f"数据已保存到 {OUTPUT_DIR}/ 目录")
        print(f"日志文件保存在 {PROJECT_ROOT / 'logs'}/ 目录")

    except ValueError as e:
        print(f"错误: {e}")
        print()
        print("提示: 如果无法找到博主，请尝试:")
        print("1. 确认用户名拼写正确")
        print("2. 手动访问博主主页获取用户ID")
        print("3. 将用户ID填入 USER_ID 变量")

    except Exception as e:
        print(f"爬取过程中发生错误: {e}")
        logger.exception("Crawl failed")


# 高级用法示例 - 不使用向量数据库
def advanced_example():
    """
    高级用法示例：更精细的控制（不启用向量数据库）
    """
    # 创建爬虫实例（不启用向量数据库）
    crawler = TaogubaCrawler(
        delay=(1.0, 3.0),  # 请求间隔1-3秒
        output_dir=PROJECT_ROOT / "output",
        max_comments=100,  # 每篇帖子最多抓取100条评论
        enable_vector_store=False  # 禁用向量数据库
    )

    # 自定义日期范围
    start_date = datetime(2026, 3, 1)
    end_date = datetime(2026, 3, 20)

    # 执行爬取
    result = crawler.crawl_blogger(
        username="jl韭菜抄家",
        start_date=start_date,
        end_date=end_date,
        max_posts=50,
        max_comments=100  # 可以在这里覆盖默认值
    )

    # 处理结果
    for post in result.posts:
        print(f"标题: {post.title}")
        print(f"评论数: {len(post.comments)}")

        # 遍历评论树
        def print_comments(comments, level=0):
            for comment in comments:
                indent = "  " * level
                print(f"{indent}- {comment.author_name}: {comment.content[:50]}...")
                if comment.children:
                    print_comments(comment.children, level + 1)

        print_comments(post.comments)


if __name__ == "__main__":
    main()

    # 如需使用高级用法，取消下面的注释
    # advanced_example()
