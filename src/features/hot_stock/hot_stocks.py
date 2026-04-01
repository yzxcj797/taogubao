# -*- coding: utf-8 -*-
"""
A股人气热股榜

数据来源：
  1. 东方财富 — 实时人气排名（Playwright 拦截）+ 实时行情
  2. 同花顺   — 实时人气热度榜（HTTP 直连）

用法：
  python -m src.features.hot_stock.hot_stocks              # 双榜各 TOP 30
  python -m src.features.hot_stock.hot_stocks -n 50        # TOP 50
  python -m src.features.hot_stock.hot_stocks -s dc        # 仅东财
  python -m src.features.hot_stock.hot_stocks -s ths       # 仅同花顺
"""

import sys
import time
import argparse
import urllib.request
import urllib.parse
import json
from datetime import datetime
from typing import Optional

from loguru import logger
from playwright.sync_api import sync_playwright


# =====================================================================
#  常量
# =====================================================================

# 东方财富
DC_RANK_URL = "https://vipmoney.eastmoney.com/collect/app_ranking/ranking/app.html?appfenxiang=1#/stock"
DC_QUOTE_API = "https://push2.eastmoney.com/api/qt/ulist.np/get"
DC_QUOTE_BATCH_API = "https://push2his.eastmoney.com/api/qt/stock/get"

# 新浪行情（盘后也能用，HTTP 直连，支持批量）
SINA_QUOTE_API = "https://hq.sinajs.cn/list="

# 同花顺人气热度榜（type=hour 为实时榜，list_type=normal 为综合热度）
THS_HOT_API = "https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock"


# =====================================================================
#  东方财富
# =====================================================================

def _fetch_dc_rank(top_n: int = 30, timeout: int = 30) -> list[dict]:
    """通过 Playwright 拦截东财人气排名数据。"""
    result = [None]

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()

        def on_response(resp):
            if "getAllCurrentList" in resp.url and result[0] is None:
                try:
                    result[0] = json.loads(resp.text())
                except Exception:
                    pass

        page.on("response", on_response)
        page.goto(DC_RANK_URL, wait_until="networkidle", timeout=timeout * 1000)

        for _ in range(int(timeout / 2)):
            if result[0] and result[0].get("data"):
                break
            page.wait_for_timeout(2000)

        browser.close()

    if not result[0] or not result[0].get("data"):
        raise RuntimeError("未能获取东财人气排名数据")

    items = result[0]["data"]
    logger.info(f"东财人气榜: 获取 {len(items)} 条排名")
    return items[:top_n]


def _dc_sc_to_secid(sc: str) -> str:
    """SZ000592 → 0.000592, SH600036 → 1.600036"""
    if sc.startswith("SZ"):
        return f"0.{sc[2:]}"
    elif sc.startswith("SH"):
        return f"1.{sc[2:]}"
    return sc


def _dc_sc_to_ts_code(sc: str) -> str:
    """SZ000592 → 000592.SZ, SH600036 → 600036.SH"""
    if sc.startswith("SZ"):
        return f"{sc[2:]}.SZ"
    elif sc.startswith("SH"):
        return f"{sc[2:]}.SH"
    return sc


def _fetch_dc_quotes(secids: list[str], max_retries: int = 2) -> dict[str, dict]:
    """批量获取东财行情。

    策略：
      1. 先尝试 push2（实时接口，交易时间内稳定）
      2. 若失败则降级到 push2his（历史快照）
      3. push2his 也失败则降级到新浪行情接口（盘后最稳定）
    """
    if not secids:
        return {}

    # ── 尝试 push2 实时接口（批量） ──
    merged = _fetch_dc_quotes_push2(secids, max_retries)
    if merged:
        return merged

    # ── 降级：push2his 逐只查询 ──
    logger.info("东财 push2 实时接口不可用，降级使用 push2his 历史快照接口")
    merged = _fetch_dc_quotes_his(secids, max_retries)
    if merged:
        return merged

    # ── 最终兜底：新浪行情接口 ──
    logger.info("东财接口均不可用，降级使用新浪行情接口")
    return _fetch_sina_quotes(secids)


def _fetch_dc_quotes_push2(secids: list[str], max_retries: int) -> dict[str, dict]:
    """通过 push2 批量接口获取实时行情。"""
    merged = {}
    BATCH = 50

    for i in range(0, len(secids), BATCH):
        batch = secids[i : i + BATCH]
        params = urllib.parse.urlencode({
            "fltt": "2",
            "fields": "f2,f3,f12,f14",
            "secids": ",".join(batch),
        })
        url = f"{DC_QUOTE_API}?{params}"

        last_err = None
        for attempt in range(1, max_retries + 1):
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Referer": "https://quote.eastmoney.com/",
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            })
            try:
                resp = urllib.request.urlopen(req, timeout=8)
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("data") and data["data"].get("diff"):
                    for item in data["data"]["diff"]:
                        code = item.get("f12", "")
                        merged[code] = {
                            "name": item.get("f14", ""),
                            "price": item.get("f2"),
                            "pct_change": item.get("f3"),
                        }
                last_err = None
                break
            except Exception as e:
                last_err = e
                if attempt < max_retries:
                    time.sleep(attempt * 1.5)

        if last_err:
            logger.debug(f"东财 push2 批量请求失败: {last_err}")
            # 只要有一批失败就整体降级
            return {}

    return merged


def _fetch_dc_quotes_his(secids: list[str], max_retries: int = 3) -> dict[str, dict]:
    """通过 push2his 逐只获取行情快照（盘后也能用）。

    防刷屏策略：连续失败超过阈值时自动终止，避免盘后接口不稳定导致大量日志。
    """
    merged = {}
    fail_count = 0
    MAX_CONSEC_FAILS = 10  # 盘后接口不稳定，给足够的容错空间

    # 获取最近一个交易日的 15:00 时间戳作为 ut
    now = datetime.now()
    if now.weekday() >= 5:
        from datetime import timedelta
        days_back = now.weekday() - 4
        last_trade = (now - timedelta(days=days_back)).replace(hour=15, minute=0, second=0, microsecond=0)
    elif now.hour < 15:
        from datetime import timedelta
        last_trade = now.replace(hour=15, minute=0, second=0, microsecond=0) - timedelta(days=1)
    else:
        last_trade = now.replace(hour=15, minute=0, second=0, microsecond=0)

    ut = int(last_trade.timestamp())

    for secid in secids:
        # 连续失败过多 → 提前终止，避免刷屏
        if fail_count >= MAX_CONSEC_FAILS:
            logger.warning(f"东财 push2his 连续 {fail_count} 只失败，终止剩余请求"
                           f"（已获取 {len(merged)}/{len(secids)} 只）")
            break

        params = urllib.parse.urlencode({
            "secid": secid,
            "fields": "f43,f44,f45,f46,f47,f57,f58,f170",
            "ut": ut,
            "ndays": "1",
        })
        url = f"{DC_QUOTE_BATCH_API}?{params}"

        success = False
        for attempt in range(1, max_retries + 1):
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Referer": "https://quote.eastmoney.com/",
                "Accept": "*/*",
            })
            try:
                resp = urllib.request.urlopen(req, timeout=8)
                data = json.loads(resp.read().decode("utf-8"))
                d = data.get("data", {})
                if d:
                    code = secid.split(".")[1] if "." in secid else secid
                    raw_price = d.get("f43") or 0
                    raw_pct = d.get("f170") or 0
                    merged[code] = {
                        "name": d.get("f58", ""),
                        "price": round(raw_price / 100, 2) if raw_price else None,
                        "pct_change": round(raw_pct / 100, 2) if raw_pct else None,
                    }
                success = True
                fail_count = 0  # 成功则重置连续失败计数
                break
            except Exception:
                if attempt < max_retries:
                    time.sleep(attempt * 1.5)

        if not success:
            fail_count += 1

        # 请求间隔，避免限流
        time.sleep(0.15)

    if merged:
        logger.info(f"东财 push2his 获取 {len(merged)}/{len(secids)} 只行情")
    else:
        logger.warning("东财行情接口全部失败")

    return merged


def _dc_secid_to_sina(secid: str) -> str:
    """东财 secid → 新浪代码。0.000592 → sz000592, 1.600036 → sh600036"""
    if secid.startswith("0."):
        return f"sz{secid[2:]}"
    elif secid.startswith("1."):
        return f"sh{secid[2:]}"
    return secid


def _fetch_sina_quotes(secids: list[str]) -> dict[str, dict]:
    """通过新浪行情接口批量获取行情（盘后最稳定）。

    新浪接口特点：
      - HTTP 直连，无需 WebSocket
      - 支持逗号分隔批量查询
      - 盘后/非交易时间均可用
      - 返回 GBK 编码
    """
    merged = {}
    BATCH = 50

    for i in range(0, len(secids), BATCH):
        batch = secids[i : i + BATCH]
        sina_codes = ",".join(_dc_secid_to_sina(s) for s in batch)
        url = f"{SINA_QUOTE_API}{sina_codes}"

        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://finance.sina.com.cn/",
        })
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            raw = resp.read().decode("gbk")
            # 解析新浪格式：var hq_str_sz000592="平潭发展,今开,昨收,现价,最高,最低,...";
            for line in raw.strip().split("\n"):
                if "=" not in line or not line.strip().endswith(";"):
                    continue
                # 提取代码
                prefix = line.split("=")[0].strip()
                code_part = prefix.replace("var hq_str_", "")
                # sz000592 → 000592
                code = code_part[2:] if len(code_part) > 2 else code_part

                # 提取数据
                data_str = line.split('"')[1] if '"' in line else ""
                if not data_str:
                    continue
                fields = data_str.split(",")
                if len(fields) < 10:
                    continue

                try:
                    name = fields[0]
                    price = float(fields[3]) if fields[3] else None
                    pre_close = float(fields[2]) if fields[2] else None
                    # 涨跌幅 = (现价 - 昨收) / 昨收 * 100
                    pct_change = round((price - pre_close) / pre_close * 100, 2) if price and pre_close else None
                    merged[code] = {
                        "name": name,
                        "price": price,
                        "pct_change": pct_change,
                    }
                except (ValueError, ZeroDivisionError):
                    continue
        except Exception as e:
            logger.warning(f"新浪行情请求失败: {e}")

    if merged:
        logger.info(f"新浪行情获取 {len(merged)}/{len(secids)} 只")

    return merged


def fetch_dc_hot(top_n: int = 30) -> list[dict]:
    """获取东方财富人气热股榜单。

    Returns:
        [{"rank": 1, "ts_code": "000592.SZ", "ts_name": "平潭发展",
          "price": 12.78, "pct_change": 9.98, "rank_change": 0, "source": "东财"}, ...]
    """
    rank_items = _fetch_dc_rank(top_n)
    secids = [_dc_sc_to_secid(item["sc"]) for item in rank_items]
    quotes = _fetch_dc_quotes(secids)

    result = []
    for item in rank_items:
        sc = item["sc"]
        code = sc[2:]
        q = quotes.get(code, {})
        result.append({
            "rank": item["rk"],
            "ts_code": _dc_sc_to_ts_code(sc),
            "ts_name": q.get("name", ""),
            "price": q.get("price"),
            "pct_change": q.get("pct_change"),
            "rank_change": item.get("hisRc", 0),
            "hot_value": None,
            "concepts": None,
            "source": "东财",
        })
    return result


# =====================================================================
#  同花顺
# =====================================================================

def _ths_code_to_ts_code(code: str, market: int) -> str:
    """同花顺代码 → 标准格式。market: 17=沪市, 33=深市"""
    if market == 17:
        return f"{code}.SH"
    elif market == 33:
        return f"{code}.SZ"
    return code


def fetch_ths_hot(top_n: int = 30) -> list[dict]:
    """获取同花顺人气热度榜（实时）。

    Returns:
        [{"rank": 1, "ts_code": "002580.SZ", "ts_name": "圣阳股份",
          "pct_change": 9.99, "hot_value": 1031919, "rank_change": 0,
          "concepts": ["钠离子电池", "固态电池"],
          "analyse_title": "...", "source": "同花顺"}, ...]
    """
    params = urllib.parse.urlencode({
        "stock_type": "a",
        "type": "hour",
        "list_type": "normal",
    })
    url = f"{THS_HOT_API}?{params}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://eq.10jqka.com.cn/frontend/thsTopRank/index.html",
    })

    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read().decode("utf-8"))

    if data.get("status_code") != 0 or not data.get("data"):
        raise RuntimeError(f"同花顺 API 错误: {data.get('status_msg', '未知')}")

    items = data["data"].get("stock_list", [])
    logger.info(f"同花顺人气热度榜: 获取 {len(items)} 条")

    result = []
    for item in items[:top_n]:
        tag = item.get("tag") or {}
        concepts = tag.get("concept_tag") or []
        popularity = tag.get("popularity_tag", "")
        analyse = item.get("analyse", "")
        analyse_title = item.get("analyse_title", "")

        result.append({
            "rank": item.get("order", 0),
            "ts_code": _ths_code_to_ts_code(item["code"], item.get("market", 0)),
            "ts_name": item.get("name", ""),
            "price": None,
            "pct_change": item.get("rise_and_fall"),
            "rank_change": item.get("hot_rank_chg", 0),
            "hot_value": float(item.get("rate", 0)),
            "concepts": concepts,
            "popularity_tag": popularity,
            "analyse": analyse,
            "analyse_title": analyse_title,
            "source": "同花顺",
        })
    return result


# =====================================================================
#  整合 + 输出
# =====================================================================

def fetch_hot_stocks(top_n: int = 30, source: str = "all") -> dict:
    """获取人气热股数据。

    Args:
        top_n: 每个榜单的 TOP N
        source: "all"(双榜) / "dc"(仅东财) / "ths"(仅同花顺)

    Returns:
        {"dc": [...], "ths": [...], "both": [...]}
    """
    result = {}
    ths_data = {}  # 同花顺数据索引，用于补全东财缺失行情

    # 先获取同花顺（接口稳定，盘后也能用）
    if source in ("all", "ths"):
        result["ths"] = fetch_ths_hot(top_n)
        ths_data = {item["ts_code"]: item for item in result["ths"]}

    # 东方财富
    if source in ("all", "dc"):
        result["dc"] = fetch_dc_hot(top_n)

    # 同花顺数据补全东财缺失行情（东财 push2/push2his 盘后经常不可用）
    if "dc" in result and ths_data:
        patched = 0
        for item in result["dc"]:
            if item.get("ts_name") or item.get("price"):
                continue  # 东财行情正常，无需补全
            ts_code = item["ts_code"]
            if ts_code in ths_data:
                t = ths_data[ts_code]
                if not item.get("ts_name") and t.get("ts_name"):
                    item["ts_name"] = t["ts_name"]
                if item.get("pct_change") is None and t.get("pct_change") is not None:
                    item["pct_change"] = t["pct_change"]
                if item.get("price") is None and t.get("price") is not None:
                    item["price"] = t["price"]
                patched += 1
        if patched:
            logger.info(f"用同花顺数据补全 {patched} 只东财行情")

    # 两榜交集
    if "dc" in result and "ths" in result:
        dc_codes = {item["ts_code"]: item for item in result["dc"]}
        ths_items = result["ths"]

        both = []
        for t_item in ths_items:
            code = t_item["ts_code"]
            if code in dc_codes:
                d_item = dc_codes[code]
                both.append({
                    "rank": d_item["rank"],
                    "ts_code": code,
                    "ts_name": t_item.get("ts_name") or d_item.get("ts_name", ""),
                    "price": d_item.get("price"),
                    "pct_change": d_item.get("pct_change"),
                    "dc_rank_change": d_item.get("rank_change", 0),
                    "ths_rank": t_item.get("rank", 0),
                    "ths_hot_value": t_item.get("hot_value"),
                    "concepts": t_item.get("concepts"),
                })
        result["both"] = both

    return result


def _format_rank_change(rc) -> str:
    """格式化排名变动"""
    if rc is None:
        return "  —  "
    rc = int(rc)
    if rc > 0:
        return f" ↑{rc:<3d}"
    elif rc < 0:
        return f" ↓{abs(rc):<3d}"
    return "  —  "


def _format_pct(pct) -> str:
    """格式化涨跌幅"""
    if pct is None:
        return f"{'—':>8}"
    return f"{pct:>+7.2f}%"


def _format_price(price) -> str:
    """格式化价格"""
    if price is None:
        return f"{'—':>8}"
    return f"{price:>8.2f}"


def print_table(items: list[dict], title: str, show_concepts: bool = False):
    """用美观的表格打印榜单"""
    if not items:
        print(f"\n  {title}: 无数据")
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'═' * 80}")
    print(f"  {title}    {now}")
    print(f"{'═' * 80}\n")

    if show_concepts:
        header = f"{'排名':>4}  {'股票名称':<8}  {'代码':<10}  {'涨跌幅':>8}  {'热度':>10}  {'排名变动':>8}  概念标签"
        print(header)
        print(f"{'─' * 80}")
        for item in items:
            name = item.get("ts_name", "-")[:8]
            code = item.get("ts_code", "-")
            pct = _format_pct(item.get("pct_change"))
            hot = item.get("hot_value")
            hot_str = f"{hot:>10,.0f}" if hot else f"{'—':>10}"
            rc = _format_rank_change(item.get("rank_change"))
            concepts = item.get("concepts") or []
            concepts_str = ", ".join(concepts[:3]) if concepts else "-"
            print(f"{item['rank']:>4}  {name:<8}  {code:<10}  {pct}  {hot_str}  {rc}  {concepts_str}")
    else:
        header = f"{'排名':>4}  {'股票名称':<8}  {'代码':<10}  {'现价':>8}  {'涨跌幅':>8}  {'排名变动':>8}"
        print(header)
        print(f"{'─' * 80}")
        for item in items:
            name = item.get("ts_name", "-")[:8]
            code = item.get("ts_code", "-")
            price = _format_price(item.get("price"))
            pct = _format_pct(item.get("pct_change"))
            rc = _format_rank_change(item.get("rank_change"))
            print(f"{item['rank']:>4}  {name:<8}  {code:<10}  {price}  {pct}  {rc}")

    print(f"\n  共 {len(items)} 只")


def print_both_table(items: list[dict]):
    """打印两榜交集"""
    if not items:
        print("\n  两榜交集: 无")
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'═' * 80}")
    print(f"  东财 × 同花顺 · 双榜交集    {now}")
    print(f"{'═' * 80}\n")

    header = f"{'排名':>4}  {'股票名称':<8}  {'代码':<10}  {'现价':>8}  {'涨跌幅':>8}  {'东财变动':>8}  {'同花顺热度':>10}  概念标签"
    print(header)
    print(f"{'─' * 80}")

    for item in items:
        name = item.get("ts_name", "-")[:8]
        code = item.get("ts_code", "-")
        price = _format_price(item.get("price"))
        pct = _format_pct(item.get("pct_change"))
        dc_rc = _format_rank_change(item.get("dc_rank_change"))
        ths_hot = item.get("ths_hot_value")
        ths_hot_str = f"{ths_hot:>10,.0f}" if ths_hot else f"{'—':>10}"
        concepts = item.get("concepts") or []
        concepts_str = ", ".join(concepts[:3]) if concepts else "-"
        print(f"{item['rank']:>4}  {name:<8}  {code:<10}  {price}  {pct}  {dc_rc}  {ths_hot_str}  {concepts_str}")

    print(f"\n  共 {len(items)} 只")


# =====================================================================
#  命令行入口
# =====================================================================

def main():
    parser = argparse.ArgumentParser(
        description="A股人气热股榜",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  python -m src.features.hot_stock.hot_stocks              # 双榜各 TOP 30\n"
               "  python -m src.features.hot_stock.hot_stocks -n 50        # TOP 50\n"
               "  python -m src.features.hot_stock.hot_stocks -s dc        # 仅东财\n"
               "  python -m src.features.hot_stock.hot_stocks -s ths       # 仅同花顺\n",
    )
    parser.add_argument("-n", "--top", type=int, default=30, help="TOP N（默认 30）")
    parser.add_argument("-s", "--source", choices=["all", "dc", "ths"], default="all",
                        help="数据源: all=双榜(默认), dc=仅东财, ths=仅同花顺")
    args = parser.parse_args()

    print("正在获取人气热股数据...")
    start = time.time()

    try:
        data = fetch_hot_stocks(top_n=args.top, source=args.source)
        elapsed = time.time() - start
        print(f"获取完成，耗时 {elapsed:.1f}s")

        # 东方财富
        if "dc" in data:
            print_table(data["dc"], "东方财富 · 人气热股榜")

        # 同花顺
        if "ths" in data:
            print_table(data["ths"], "同花顺 · 人气热度榜", show_concepts=True)

        # 双榜交集
        if "both" in data:
            print_both_table(data["both"])

        # 汇总
        dc_count = len(data.get("dc", []))
        ths_count = len(data.get("ths", []))
        both_count = len(data.get("both", []))
        print(f"\n{'═' * 80}")
        print(f"  东财: {dc_count} 只 | 同花顺: {ths_count} 只 | 交集: {both_count} 只")
        print(f"{'═' * 80}")

    except Exception as e:
        logger.error(f"获取失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
