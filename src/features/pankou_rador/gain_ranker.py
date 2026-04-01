"""
=================================================================
  A股涨幅排行榜 v1.0
  功能：基于本地缓存数据，按不同时间窗口计算涨幅并排名
  特点：只读本地缓存，不发起任何网络请求
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
#   新增规则？在此追加一行即可，主流程自动遍历
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
    涨幅 = (今天收盘价 / N天前收盘价) - 1
    例如 3 日涨幅 = (最近一日收盘 / 往前第3天收盘) - 1
    
    返回 None 表示该股票不符合参与条件（数据不足）。
    """
    days = params["days"]
    # 需要至少 days+1 条数据：前 N 天的 close + 今天的 close
    min_days = params.get("min_days", days) + 1

    if len(df) < min_days:
        return None

    # 取最后 days+1 行：用倒数第 days+1 行的 close 作为起始价
    window = df.iloc[-(days + 1):]
    start_price = window["close"].iloc[0]   # N天前的收盘价
    end_price = window["close"].iloc[-1]     # 今天的收盘价

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
    检查最近 N 个交易日是否全部为阳线（close >= open，含假阳线）。
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


def check_data_freshness(df: pd.DataFrame) -> bool:
    """
    检查本地数据的时效性。
    如果最新数据日期不是最近 2 个自然日内的，发出提醒。
    """
    last_date = df["trade_date"].max()
    today = pd.Timestamp(datetime.datetime.now().strftime("%Y-%m-%d"))
    gap = (today - last_date).days

    print(f"[信息] 本地数据最新日期: {last_date.strftime('%Y-%m-%d')}")
    print(f"[信息] 当前日期:         {today.strftime('%Y-%m-%d')}")

    if gap > 2:
        print()
        print(f"  ╔══════════════════════════════════════════════════════╗")
        print(f"  ║  !! 注意：本地数据距今已 {gap} 天，可能不是最新 !!   ║")
        print(f"  ║  建议先运行 stock_screener.py 更新数据             ║")
        print(f"  ╚══════════════════════════════════════════════════════╝")
        print()
        return False

    if gap >= 1:
        print(f"[提示] 本地数据距今 {gap} 天（可能是周末或非交易日）")
    else:
        print(f"[信息] 本地数据已是最新")
    return True


# =====================================================================
#  4. 主程序模块
# =====================================================================

def main():
    print("=" * 60)
    print("  A股涨幅排行榜 v1.0")
    print("  数据源: 本地缓存 (只读模式)")
    print("=" * 60)
    print()

    # ---- 加载数据 ----
    df = load_local_data()
    if df is None:
        return

    # ---- 检查时效性 ----
    check_data_freshness(df)

    all_codes = df["ts_code"].unique()
    # 构建名称映射
    name_map = df.drop_duplicates("ts_code").set_index("ts_code")["name"].to_dict()

    print(f"[信息] 共 {len(all_codes)} 只股票，{len(df)} 条日线记录")
    print(f"[信息] 已注册 {len(ACTIVE_RULES)} 个排名规则: "
          f"{', '.join(r['name'] for r in ACTIVE_RULES)}")
    print()

    # ---- 遍历规则，计算涨幅 ----
    #   结果结构: {rule_name: [(code, name, gain, details_dict), ...]}
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
                stock_df = df[df["ts_code"] == code].reset_index(drop=True)
                if stock_df.empty:
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
    print("  涨幅排行榜结果")
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
                "涨幅(数值)": gain,  # 用于排序验证
                "区间": f"{details['start_date']} ~ {details['end_date']}",
                "起始价": details["start_price"],
                "终止价": details["end_price"],
                "天数": details["days"],
            })

    if all_rows:
        result_df = pd.DataFrame(all_rows)

        # 打印到控制台（按规则分组展示，规则间两行空行分隔）
        for idx, rule_entry in enumerate(ACTIVE_RULES):
            rule_label = CONFIG["rules"][rule_entry["config_key"]].get("label", rule_entry["name"])
            subset = result_df[result_df["规则"] == rule_label]

            if idx > 0:
                print("\n")
            print(f"  ── {rule_label} (TOP {len(subset)}) ──")
            print(f"  {'排名':>4}  {'代码':<12} {'名称':<10} {'区间涨幅':>8}  {'起始价':>7}  {'终止价':>7}  {'区间'}")
            print(f"  {'----':>4}  {'----':<12} {'----':<10} {'--------':>8}  {'-------':>7}  {'-------':>7}  {'----'}")
            for _, row in subset.iterrows():
                print(f"  {int(row['排名']):>4}  {row['代码']:<12} {row['名称']:<10} {row['区间涨幅']:>8}  "
                      f"{row['起始价']:>7.2f}  {row['终止价']:>7.2f}  {row['区间']}")

        # 保存 CSV
        os.makedirs(CONFIG["output_dir"], exist_ok=True)
        today_str = datetime.datetime.now().strftime("%Y%m%d")
        output_path = os.path.join(CONFIG["output_dir"], f"rank_gain_{today_str}.csv")

        # 导出时去掉辅助排序列
        export_df = result_df.drop(columns=["涨幅(数值)"])
        export_df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print()
        print(f"[信息] 结果已保存至: {output_path}")
    else:
        print("[信息] 无符合条件的股票")

    print()
    print("=" * 60)
    print("[信息] 排行榜生成完成。")


if __name__ == "__main__":
    main()
