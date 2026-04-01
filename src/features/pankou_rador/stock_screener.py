"""
=================================================================
  A股市场数据下载器 v4.0
  数据源：finance-data-retrieval API (东方财富/Tushare)
  功能：全量下载 / 增量更新全市场日线数据，保存为本地 CSV
=================================================================

【数据策略】
  - 首次运行：全量下载所有股票的近期数据，保存为本地 CSV。
  - 后续运行：增量更新（只拉缺失的交易日）。
  - 筛选功能已迁移至 gain_ranker.py，本脚本仅负责数据管理。
=================================================================
"""

import os
import json
import time
import datetime
import warnings
import urllib.request
from typing import Dict, List, Optional

import pandas as pd
from tqdm import tqdm

warnings.filterwarnings("ignore")

# =====================================================================
#  0. 数据源：finance-data API 客户端
# =====================================================================

API_URL = "https://www.codebuddy.cn/v2/tool/financedata"


def _api_call(api_name: str, params: dict, fields: str = "", timeout: int = 30) -> dict:
    """
    调用 finance-data-retrieval API。
    返回解析后的 JSON 响应 dict。
    """
    payload = {"api_name": api_name, "params": params, "fields": fields or ""}

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API_URL, data=data, headers={"Content-Type": "application/json"})

    for attempt in range(1, 4):
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            if attempt < 3:
                time.sleep(2 ** attempt)
            else:
                raise


def _api_to_dataframe(response: dict) -> pd.DataFrame:
    """将 API 返回的 fields + items 转为 DataFrame。"""
    if response["code"] != 0:
        raise RuntimeError(f"API 错误: {response.get('msg', 'unknown')}")
    fields = response["data"]["fields"]
    items = response["data"]["items"]
    if not items:
        return pd.DataFrame(columns=fields)
    return pd.DataFrame(items, columns=fields)


# =====================================================================
#  1. 配置模块
# =====================================================================

CONFIG: Dict = {
    # ---- 数据存储设置 ----
    "data_dir": "./market_data",
    "daily_cache_file": "daily_all.csv",      # 全市场日线合并文件
    "stock_list_file": "stock_list.csv",       # 股票列表缓存
    "cache_keep_days": 60,                     # 保留最近 N 个交易日

    # ---- 网络设置 ----
    "api_batch_size": 50,                      # 每次请求批量拉取的股票数
    "request_delay": 0.1,                      # 请求间隔秒数

    # ---- 下载窗口 ----
    "download_days": 70,                       # 首次下载的自然日天数（≈交易日）
}


# =====================================================================
#  2. 工具函数模块
# =====================================================================

def _ensure_dirs():
    """确保所有必要目录存在。"""
    os.makedirs(CONFIG["data_dir"], exist_ok=True)


def _daily_cache_path() -> str:
    return os.path.join(CONFIG["data_dir"], CONFIG["daily_cache_file"])


def _stock_list_path() -> str:
    return os.path.join(CONFIG["data_dir"], CONFIG["stock_list_file"])


# ---- 股票列表管理 ----

def fetch_stock_list(use_cache: bool = True) -> pd.DataFrame:
    """
    获取全市场 A 股列表（在市股票）。
    优先使用本地缓存，缓存不存在或过期时从 API 获取。
    """
    cache_path = _stock_list_path()

    # 尝试加载缓存
    if use_cache and os.path.exists(cache_path):
        try:
            cached = pd.read_csv(cache_path)
            if not cached.empty and "ts_code" in cached.columns:
                file_mtime = os.path.getmtime(cache_path)
                file_date = datetime.datetime.fromtimestamp(file_mtime).date()
                if file_date == datetime.datetime.now().date():
                    print(f"[信息] 使用今日缓存的股票列表: {len(cached)} 只")
                    return cached
        except Exception:
            pass

    # 从 API 获取
    print("[信息] 正在从 API 获取全市场股票列表...")
    try:
        resp = _api_call("stock_basic", {"list_status": "L"}, fields="ts_code,name,symbol")
        df = _api_to_dataframe(resp)
        if not df.empty:
            df.to_csv(cache_path, index=False, encoding="utf-8-sig")
            print(f"[信息] 获取到 {len(df)} 只股票，已缓存")
            return df
    except Exception as e:
        print(f"[错误] 获取股票列表失败: {e}")

    # 降级：尝试加载过期的缓存
    if os.path.exists(cache_path):
        try:
            cached = pd.read_csv(cache_path)
            if not cached.empty:
                print(f"[警告] API 获取失败，使用过期缓存: {len(cached)} 只")
                return cached
        except Exception:
            pass

    return pd.DataFrame()


# ---- 全市场日线数据管理 ----

def _load_daily_cache() -> Optional[pd.DataFrame]:
    """加载本地全市场日线缓存。"""
    path = _daily_cache_path()
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path)
        if df is not None and not df.empty:
            df["trade_date"] = pd.to_datetime(df["trade_date"])
            return df
    except Exception:
        pass
    return None


def _save_daily_cache(df: pd.DataFrame):
    """保存全市场日线数据，裁剪到保留天数。"""
    if df is not None and not df.empty:
        keep = CONFIG["cache_keep_days"]
        df = df.sort_values(["ts_code", "trade_date"])
        df = df.groupby("ts_code").tail(keep).reset_index(drop=True)
    df.to_csv(_daily_cache_path(), index=False, encoding="utf-8-sig")


def _fetch_daily_batch(codes: List[str], start_date: str, end_date: str) -> pd.DataFrame:
    """
    批量获取多只股票的历史日线。
    API 的 ts_code 参数支持逗号分隔的多值。
    
    快速失败策略：连续 N 批次返回空数据时提前终止（可能是非交易日）
    """
    batch_size = CONFIG["api_batch_size"]
    all_frames = []
    total_batches = (len(codes) + batch_size - 1) // batch_size
    empty_batch_count = 0  # 连续空批次计数
    max_empty_batches = 3  # 连续 3 批次为空则终止

    for i in tqdm(range(0, len(codes), batch_size), desc="增量更新进度", total=total_batches):
        batch = codes[i:i + batch_size]
        ts_codes = ",".join(batch)
        try:
            resp = _api_call("daily", {
                "ts_code": ts_codes,
                "start_date": start_date.replace("-", ""),
                "end_date": end_date.replace("-", ""),
            })
            df = _api_to_dataframe(resp)
            
            if not df.empty:
                all_frames.append(df)
                empty_batch_count = 0  # 有数据时重置计数
            else:
                empty_batch_count += 1
                if empty_batch_count >= max_empty_batches:
                    print(f"\n[信息] 连续 {max_empty_batches} 批次返回空数据，可能是非交易日或盘中未收盘，提前终止")
                    break
            
            time.sleep(CONFIG["request_delay"])
        except Exception as e:
            print(f"\n    [警告] 批次 {i//batch_size + 1} 获取失败: {e}")
            time.sleep(1)

    if all_frames:
        return pd.concat(all_frames, ignore_index=True)
    return pd.DataFrame()


def fetch_all_daily_full(stock_list: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    """全量下载所有股票的日线数据。"""
    all_codes = stock_list["ts_code"].tolist()
    total_batches = (len(all_codes) + CONFIG["api_batch_size"] - 1) // CONFIG["api_batch_size"]
    print(f"[信息] 将分 {total_batches} 批下载 {len(all_codes)} 只股票的数据")
    print(f"[信息] 日期范围: {start_date} ~ {end_date}")

    all_frames = []
    batch_size = CONFIG["api_batch_size"]

    for i in tqdm(range(0, len(all_codes), batch_size), desc="下载进度",
                  total=total_batches):
        batch = all_codes[i:i + batch_size]
        ts_codes = ",".join(batch)
        try:
            resp = _api_call("daily", {
                "ts_code": ts_codes,
                "start_date": start_date.replace("-", ""),
                "end_date": end_date.replace("-", ""),
            })
            df = _api_to_dataframe(resp)
            if not df.empty:
                all_frames.append(df)
            time.sleep(CONFIG["request_delay"])
        except Exception as e:
            print(f"    [警告] 批次获取失败: {e}")
            time.sleep(1)

    if all_frames:
        result = pd.concat(all_frames, ignore_index=True)
        result["trade_date"] = pd.to_datetime(result["trade_date"], format="%Y%m%d")
        result = result.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
        print(f"[信息] 下载完成，共 {len(result)} 条记录")
        return result
    return pd.DataFrame()


def ensure_data_fresh() -> pd.DataFrame:
    """
    核心数据管理：冷启动全量下载，热启动增量更新。
    """
    # 1. 获取股票列表
    stock_list = fetch_stock_list()
    if stock_list.empty:
        print("[错误] 无法获取股票列表")
        return pd.DataFrame()

    # 2. 加载或下载日线数据
    cached_df = _load_daily_cache()

    if cached_df is None or cached_df.empty:
        # ---- 冷启动 ----
        print()
        print("[信息] ====== 冷启动：首次运行，全量下载全市场日线数据 ======")
        print("[信息] 此过程只需执行一次，后续将使用本地缓存")
        print()

        end_date = datetime.datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.datetime.now() - pd.Timedelta(days=CONFIG["download_days"])).strftime("%Y-%m-%d")

        df = fetch_all_daily_full(stock_list, start_date, end_date)
        if not df.empty:
            name_map = stock_list.set_index("ts_code")["name"].to_dict()
            df["name"] = df["ts_code"].map(name_map)
            _save_daily_cache(df)
            return df
        return pd.DataFrame()

    # ---- 热更新 ----
    last_cached = cached_df["trade_date"].max()
    today = pd.Timestamp(datetime.datetime.now().strftime("%Y-%m-%d"))
    days_gap = (today - last_cached).days

    # 只要不是今天的数据，就尝试增量更新
    # 原来的 days_gap <= 1 会跳过周末后的首个交易日，导致数据缺失
    if days_gap == 0:
        print(f"[信息] 本地日线数据已是最新 (截至 {last_cached.strftime('%Y-%m-%d')})")
        return cached_df

    print(f"[信息] 本地数据截至 {last_cached.strftime('%Y-%m-%d')}，距今 {days_gap} 天，增量更新...")

    start_date = (last_cached + pd.Timedelta(days=1)).strftime("%Y%m%d")
    end_date = today.strftime("%Y%m%d")

    existing_codes = cached_df["ts_code"].unique().tolist()
    print(f"[信息] 需要检查 {len(existing_codes)} 只股票的增量数据...")
    new_df = _fetch_daily_batch(existing_codes, start_date, end_date)

    if not new_df.empty:
        new_df["trade_date"] = pd.to_datetime(new_df["trade_date"], format="%Y%m%d")
        if "name" in cached_df.columns:
            name_map = cached_df.drop_duplicates("ts_code").set_index("ts_code")["name"].to_dict()
            new_df["name"] = new_df["ts_code"].map(name_map)
        merged = pd.concat([cached_df, new_df], ignore_index=True)
        merged = merged.drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
        merged = merged.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
        _save_daily_cache(merged)
        print(f"[信息] 增量更新完成，新增 {len(new_df)} 条记录")
        return merged

    print("[信息] 无新数据（可能非交易日），使用现有缓存")
    return cached_df


# =====================================================================
#  3. 主程序
# =====================================================================

def main():
    print("=" * 60)
    print("  A股市场数据下载器 v4.0")
    print("  数据源: finance-data API")
    print("=" * 60)
    print()

    _ensure_dirs()

    # ---- 准备数据 ----
    all_daily = ensure_data_fresh()

    if all_daily is None or all_daily.empty:
        print("[错误] 无可用数据，程序退出。")
        return

    all_codes = all_daily["ts_code"].unique()
    print(f"[信息] 共 {len(all_codes)} 只股票，{len(all_daily)} 条日线记录")
    print()

    cache_path = _daily_cache_path()
    print(f"[信息] 数据已就绪: {cache_path}")
    print()
    print("=" * 60)
    print("[信息] 数据准备完成。可运行 gain_ranker.py 进行筛选。")


if __name__ == "__main__":
    main()
