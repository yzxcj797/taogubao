"""
=================================================================
  A股涨幅排行榜（指定日期版）v1.0
  功能：基于本地缓存数据，以用户指定的日期为基准点计算涨幅排名
  特点：只读本地缓存，不发起任何网络请求

【与 gain_ranker.py 的区别】
  gain_ranker.py    → 以最新交易日为起点往前统计
  gain_ranker_date.py → 以用户指定日期为起点往前统计
  例：指定 03-25，则 3 日涨幅 = 03-23~03-25 的涨幅

【用法】
  python gain_ranker_date.py           # 交互式输入日期
  python gain_ranker_date.py 0325      # 命令行指定日期
  python gain_ranker_date.py 2026-03-25
=================================================================

【如何新增规则】只需三步：
  1. 在 CONFIG["rules"] 中新增：如 "rank_30days": {"days": 30, "top_n": 20}
  2. 在 ACTIVE_RULES 列表中注册一行
  3. 主流程无需修改

【排序规则】
  1. 按规则分组（同规则的股票放在一起）
  2. 规则内按涨幅从高到低排序
=================================================================
"""

import os
import sys
import datetime
from typing import Dict, List, Any, Optional

import pandas as pd

# =====================================================================
#  1. 配置模块
# =====================================================================

CONFIG: Dict[str, Any] = {
    # ---- 数据路径（与 stock_screener.py 共享） ----
    "data_dir": "./market_data",
    "daily_cache_file": "daily_all.csv",

    # ---- 排行设置 ----
    "top_n": 30,                  # 每个规则最多展示前 N 名
    "output_dir": "./screening_results",

    # ---- 规则配置 ----
    #   [涨幅榜] days: 计算涨幅的交易日窗口; min_days: 最少数据天数; top_n: 展示条数
    #   [连阳榜] days: 连阳天数; min_days: 同 days; top_n: 展示条数 (留空则不限)
    "rules": {
        # ---- 涨幅榜 ----
        "rank_3days": {
            "type": "gain",
            "days": 3,
            "label": "近3日涨幅榜",
            "min_days": 3,
            "top_n": 30,
        },
        "rank_4days": {
            "type": "gain",
            "days": 4,
            "label": "近4日涨幅榜",
            "min_days": 4,
            "top_n": 30,
        },
        "rank_5days": {
            "type": "gain",
            "days": 5,
            "label": "近5日涨幅榜",
            "min_days": 5,
            "top_n": 30,
        },
        "rank_6days": {
            "type": "gain",
            "days": 6,
            "label": "近6日涨幅榜",
            "min_days": 6,
            "top_n": 30,
        },
        "rank_10days": {
            "type": "gain",
            "days": 10,
            "label": "近10日涨幅榜",
            "min_days": 10,
            "top_n": 30,
        },
        # ---- 连阳榜 (含假阳线: close >= open) ----
        "yang_4days": {
            "type": "consecutive_yang",
            "days": 4,
            "label": "4连阳榜",
            "min_days": 4,
            "top_n": None,   # None = 全部命中都展示
        },
        "yang_5days": {
            "type": "consecutive_yang",
            "days": 5,
            "label": "5连阳榜",
            "min_days": 5,
            "top_n": None,
        },
        "yang_6days": {
            "type": "consecutive_yang",
            "days": 6,
            "label": "6连阳榜",
            "min_days": 6,
            "top_n": None,
        },
    },
}

# ---- 规则注册表 (Registry) ----
ACTIVE_RULES: List[Dict[str, Any]] = []


# =====================================================================
#  2. 规则函数模块
# =====================================================================

def check_rank_3days(df: pd.DataFrame, params: dict) -> Optional[dict]:
    """计算近 3 日涨幅。"""
    return _calc_period_gain(df, params)


def check_rank_4days(df: pd.DataFrame, params: dict) -> Optional[dict]:
    """计算近 4 日涨幅。"""
    return _calc_period_gain(df, params)


def check_rank_5days(df: pd.DataFrame, params: dict) -> Optional[dict]:
    """计算近 5 日涨幅。"""
    return _calc_period_gain(df, params)


def check_rank_6days(df: pd.DataFrame, params: dict) -> Optional[dict]:
    """计算近 6 日涨幅。"""
    return _calc_period_gain(df, params)


def check_rank_10days(df: pd.DataFrame, params: dict) -> Optional[dict]:
    """计算近 10 日涨幅。"""
    return _calc_period_gain(df, params)


def check_yang_4days(df: pd.DataFrame, params: dict) -> Optional[dict]:
    """筛选近 4 连阳（含假阳线）。"""
    return _calc_consecutive_yang(df, params)


def check_yang_5days(df: pd.DataFrame, params: dict) -> Optional[dict]:
    """筛选近 5 连阳（含假阳线）。"""
    return _calc_consecutive_yang(df, params)


def check_yang_6days(df: pd.DataFrame, params: dict) -> Optional[dict]:
    """筛选近 6 连阳（含假阳线）。"""
    return _calc_consecutive_yang(df, params)


def _calc_period_gain(df: pd.DataFrame, params: dict) -> Optional[dict]:
    """
    通用涨幅计算函数。
    涨幅 = (基准日收盘价 / N天前收盘价) - 1
    例如 3 日涨幅 = (基准日收盘 / 往前第3天收盘) - 1

    df 已被截取到 <= end_date，所以最后一天就是基准日。
    返回 None 表示该股票不符合参与条件（数据不足）。
    """
    days = params["days"]
    # 需要至少 days+1 条数据：前 N 天的 close + 基准日的 close
    min_days = params.get("min_days", days) + 1

    if len(df) < min_days:
        return None

    # 取最后 days+1 行：用倒数第 days+1 行的 close 作为起始价
    window = df.iloc[-(days + 1):]
    start_price = window["close"].iloc[0]   # N天前的收盘价
    end_price = window["close"].iloc[-1]     # 基准日的收盘价

    if start_price <= 0:
        return None

    gain = (end_price / start_price) - 1

    return {
        "rule_name": params["label"],
        "days": days,
        "gain": gain,
        "start_date": str(window["trade_date"].iloc[0])[:10],
        "end_date": str(window["trade_date"].iloc[-1])[:10],
        "start_price": round(start_price, 2),
        "end_price": round(end_price, 2),
    }


def _calc_consecutive_yang(df: pd.DataFrame, params: dict) -> Optional[dict]:
    """
    通用连阳筛选函数。
    检查基准日之前最近 N 个交易日是否全部为阳线（close >= open，含假阳线）。
    df 已被截取到 <= end_date，所以最后 N 天就是基准日之前的 N 个交易日。
    命中的同时计算该区间的涨幅。
    返回 None 表示不满足连阳条件或数据不足。
    """
    days = params["days"]
    min_days = params.get("min_days", days)

    if len(df) < min_days:
        return None

    window = df.iloc[-days:]
    # 假阳线判定: close >= open
    is_yang = window["close"] >= window["open"]
    if not is_yang.all():
        return None

    start_price = window["close"].iloc[0]
    end_price = window["close"].iloc[-1]

    if start_price <= 0:
        return None

    gain = (end_price / start_price) - 1

    return {
        "rule_name": params["label"],
        "days": days,
        "gain": gain,
        "start_date": str(window["trade_date"].iloc[0])[:10],
        "end_date": str(window["trade_date"].iloc[-1])[:10],
        "start_price": round(start_price, 2),
        "end_price": round(end_price, 2),
    }


# ---- 注册所有规则 ----
ACTIVE_RULES = [
    {"func": check_rank_3days,   "name": "近3日涨幅榜", "config_key": "rank_3days"},
    {"func": check_rank_4days,   "name": "近4日涨幅榜", "config_key": "rank_4days"},
    {"func": check_rank_5days,   "name": "近5日涨幅榜", "config_key": "rank_5days"},
    {"func": check_rank_6days,   "name": "近6日涨幅榜", "config_key": "rank_6days"},
    {"func": check_rank_10days,  "name": "近10日涨幅榜", "config_key": "rank_10days"},
    {"func": check_yang_4days,   "name": "4连阳榜",     "config_key": "yang_4days"},
    {"func": check_yang_5days,   "name": "5连阳榜",     "config_key": "yang_5days"},
    {"func": check_yang_6days,   "name": "6连阳榜",     "config_key": "yang_6days"},
]


# =====================================================================
#  3. 工具函数模块
# =====================================================================

def load_local_data() -> Optional[pd.DataFrame]:
    """
    加载本地日线缓存数据。
    仅读取，不发起任何网络请求。
    """
    path = os.path.join(CONFIG["data_dir"], CONFIG["daily_cache_file"])
    if not os.path.exists(path):
        print(f"[错误] 本地数据文件不存在: {path}")
        print("[提示] 请先运行 stock_screener.py 下载全市场数据")
        return None

    try:
        df = pd.read_csv(path)
        if df.empty:
            print("[错误] 本地数据文件为空")
            return None

        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df = df.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
        return df
    except Exception as e:
        print(f"[错误] 读取本地数据失败: {e}")
        return None


def parse_end_date(raw: str) -> Optional[str]:
    """
    解析用户输入的日期，返回标准格式字符串 (YYYY-MM-DD)。
    支持: 0325, 3-25, 2026-03-25 等格式。
    """
    raw = raw.strip().replace("/", "-").replace(".", "-")

    # 尝试补全年份
    candidates = [raw]
    if len(raw) <= 5 and "-" in raw:
        # "3-25" -> "2026-3-25"
        candidates.append(f"{datetime.datetime.now().year}-{raw}")
    elif len(raw) == 4 and "-" not in raw:
        # "0325" -> "2026-0325"
        candidates.append(f"{datetime.datetime.now().year}{raw}")
        candidates.append(f"{datetime.datetime.now().year}-{raw[:2]}-{raw[2:]}")

    for c in candidates:
        for fmt in ("%Y-%m-%d", "%Y%m%d", "%m-%d"):
            try:
                dt = datetime.datetime.strptime(c, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
    return None


def get_valid_dates(df: pd.DataFrame) -> List[str]:
    """返回本地缓存中所有交易日（排序去重）。"""
    dates = sorted(df["trade_date"].unique().tolist())
    return [str(d)[:10] for d in dates]


# =====================================================================
#  4. 主程序模块
# =====================================================================

def main():
    # ---- 解析命令行日期参数 ----
    raw_date = sys.argv[1] if len(sys.argv) > 1 else ""

    print("=" * 60)
    print("  A股涨幅排行榜（指定日期版）v1.0")
    print("  数据源: 本地缓存 (只读模式)")
    print("=" * 60)
    print()

    # ---- 加载数据 ----
    df = load_local_data()
    if df is None:
        return

    valid_dates = get_valid_dates(df)
    print(f"[信息] 本地数据覆盖: {valid_dates[0]} ~ {valid_dates[-1]}")
    print(f"[信息] 共 {len(valid_dates)} 个交易日")

    # ---- 确定基准日期 ----
    end_date = None

    if raw_date:
        end_date = parse_end_date(raw_date)
        if end_date is None:
            print(f"[错误] 无法解析日期: {raw_date}")
            print("[提示] 支持格式: 0325, 3-25, 2026-03-25")
            return
        # 检查是否为交易日
        if end_date not in valid_dates:
            # 找最近的交易日（含当天之前）
            earlier = [d for d in valid_dates if d <= end_date]
            if not earlier:
                print(f"[错误] 日期 {end_date} 早于数据起始日 {valid_dates[0]}")
                return
            end_date = earlier[-1]
            print(f"[提示] {raw_date} 非交易日，使用最近的交易日: {end_date}")
        else:
            print(f"[信息] 基准日期: {end_date}")
    else:
        # 交互式输入
        print()
        print(f"  可用交易日范围: {valid_dates[-10] if len(valid_dates) > 10 else valid_dates[0]} ~ {valid_dates[-1]}")
        while True:
            raw = input("  请输入基准日期 (格式如 0325, 3-25, 2026-03-25，留空使用最新): ").strip()
            if not raw:
                end_date = valid_dates[-1]
                print(f"  使用最新交易日: {end_date}")
                break
            parsed = parse_end_date(raw)
            if parsed is None:
                print(f"  [错误] 无法解析，请重新输入")
                continue
            if parsed not in valid_dates:
                earlier = [d for d in valid_dates if d <= parsed]
                if not earlier:
                    print(f"  [错误] 早于数据起始日 {valid_dates[0]}")
                    continue
                end_date = earlier[-1]
                print(f"  [提示] {raw} 非交易日，使用最近的交易日: {end_date}")
                break
            end_date = parsed
            break

    print()

    # ---- 截取数据到基准日期 ----
    end_ts = pd.Timestamp(end_date)
    df = df[df["trade_date"] <= end_ts].reset_index(drop=True)

    all_codes = df["ts_code"].unique()
    name_map = df.drop_duplicates("ts_code").set_index("ts_code")["name"].to_dict()

    print(f"[信息] 以 {end_date} 为基准日，共 {len(all_codes)} 只股票，{len(df)} 条日线记录")
    print(f"[信息] 已注册 {len(ACTIVE_RULES)} 个排名规则: "
          f"{', '.join(r['name'] for r in ACTIVE_RULES)}")
    print()

    # ---- 预拆分：用 groupby 一次性拆分所有股票的 DataFrame ----
    print("[信息] 正在预处理数据（按股票分组）...")
    stock_dfs: Dict[str, pd.DataFrame] = {}
    for code, stock_df in df.groupby("ts_code"):
        stock_dfs[code] = stock_df.reset_index(drop=True)
    print(f"[信息] 预处理完成（{len(stock_dfs)} 只股票）")
    print()

    # ---- 遍历规则，计算涨幅 ----
    rule_results: Dict[str, List[tuple]] = {}

    for rule_entry in ACTIVE_RULES:
        rule_func = rule_entry["func"]
        config_key = rule_entry["config_key"]
        rule_params = CONFIG["rules"].get(config_key, {})
        rule_label = rule_params.get("label", rule_entry["name"])
        top_n = rule_params.get("top_n", CONFIG["top_n"])

        print(f"[信息] 正在计算: {rule_label} ...")
        hits = []

        for code in all_codes:
            try:
                stock_df = stock_dfs.get(code)
                if stock_df is None or stock_df.empty:
                    continue

                result = rule_func(stock_df, rule_params)
                if result is not None:
                    name = name_map.get(code, "未知")
                    hits.append((code, name, result["gain"], result))
            except Exception:
                continue

        # 按涨幅降序排序
        hits.sort(key=lambda x: x[2], reverse=True)
        # top_n=None 表示不限数量（展示所有命中）
        if top_n is not None:
            hits = hits[:top_n]
        rule_results[rule_label] = hits

        print(f"       完成，共命中 {len(hits)} 只"
              f"{f'（前 {top_n} 名）' if top_n else ''}")

    print()

    # ---- 输出结果 ----
    print("=" * 60)
    print(f"  涨幅排行榜结果（基准日: {end_date}）")
    print("=" * 60)

    # 构建汇总数据
    all_rows = []
    for idx, rule_entry in enumerate(ACTIVE_RULES):
        rule_label = CONFIG["rules"][rule_entry["config_key"]].get("label", rule_entry["name"])
        hits = rule_results.get(rule_label, [])
        # 不同规则之间插入两行空行
        if idx > 0:
            all_rows.append({col: "" for col in ["排名", "规则", "代码", "名称", "区间涨幅", "涨幅(数值)", "区间", "起始价", "终止价", "天数"]})
            all_rows.append({col: "" for col in ["排名", "规则", "代码", "名称", "区间涨幅", "涨幅(数值)", "区间", "起始价", "终止价", "天数"]})
        for rank, (code, name, gain, details) in enumerate(hits, 1):
            all_rows.append({
                "排名": rank,
                "规则": rule_label,
                "代码": code,
                "名称": name,
                "区间涨幅": f"{gain:.2%}",
                "涨幅(数值)": gain,
                "区间": f"{details['start_date']} ~ {details['end_date']}",
                "起始价": details["start_price"],
                "终止价": details["end_price"],
                "天数": details["days"],
            })

    if all_rows:
        result_df = pd.DataFrame(all_rows)

        # 打印到控制台（按规则分组展示，规则间两行空行分隔）
        for idx, rule_entry in enumerate(ACTIVE_RULES):
            config_key = rule_entry["config_key"]
            rule_label = CONFIG["rules"][config_key].get("label", rule_entry["name"])
            is_gain = CONFIG["rules"][config_key].get("type") == "gain"
            subset = result_df[result_df["规则"] == rule_label]

            if idx > 0:
                print("\n")
            count_tag = f"TOP {len(subset)}" if is_gain else f"共 {len(subset)} 只"
            print(f"  ── {rule_label} ({count_tag}) ──")
            print(f"  {'排名':>4}  {'代码':<12} {'名称':<10} {'区间涨幅':>8}  {'起始价':>7}  {'终止价':>7}  {'区间'}")
            print(f"  {'----':>4}  {'----':<12} {'----':<10} {'--------':>8}  {'-------':>7}  {'-------':>7}  {'----'}")
            for _, row in subset.iterrows():
                print(f"  {int(row['排名']):>4}  {row['代码']:<12} {row['名称']:<10} {row['区间涨幅']:>8}  "
                      f"{row['起始价']:>7.2f}  {row['终止价']:>7.2f}  {row['区间']}")

        # 保存 CSV
        os.makedirs(CONFIG["output_dir"], exist_ok=True)
        date_compact = end_date.replace("-", "")
        output_path = os.path.join(CONFIG["output_dir"], f"rank_gain_{date_compact}.csv")

        # 导出时去掉辅助排序列
        export_df = result_df.drop(columns=["涨幅(数值)"])
        export_df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print()
        print(f"[信息] 结果已保存至: {output_path}")
    else:
        print("[信息] 无符合条件的股票")

    print()
    print("=" * 60)
    print(f"[信息] 排行榜生成完成（基准日: {end_date}）。")


if __name__ == "__main__":
    main()
