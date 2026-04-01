"""
淘股宝 Web 界面

基于 Flask 的 Web 界面，提供投资分析工作流的可视化操作。
不修改任何现有代码，仅通过 API 调用对接现有模块。

启动方式:
    python -m src.web.app
    python -m src.web.app --port 5001
"""

import json
import time
import queue
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, Response
from loguru import logger

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent

app = Flask(
    __name__,
    template_folder=str(PROJECT_ROOT / "src" / "web" / "templates"),
    static_folder=str(PROJECT_ROOT / "src" / "web" / "static"),
)

# 全局任务队列，用于 SSE 推送
_task_events: dict[str, queue.Queue] = {}


# ============================================================================
# 页面路由
# ============================================================================

@app.route("/")
def index():
    """主页"""
    return render_template("index.html")


# ============================================================================
# API 路由
# ============================================================================

@app.route("/api/personas")
def api_personas():
    """获取可用的博主人格列表"""
    from src.agents.blogger_agent import _load_personas
    personas = _load_personas()
    return jsonify({"personas": list(personas.keys())})


@app.route("/api/personas/detail")
def api_personas_detail():
    """获取所有博主人格的详细信息"""
    from src.agents.blogger_agent import _load_personas
    personas = _load_personas()
    result = []
    for name, prompt in personas.items():
        # 提取角色定义作为简介
        lines = prompt.strip().split("\n")
        summary = ""
        for line in lines:
            line = line.strip()
            if line.startswith("## 角色定义"):
                continue
            if line.startswith("##"):
                break
            if line and not line.startswith("#"):
                summary = line[:80] + "..." if len(line) > 80 else line
                break
        result.append({
            "name": name,
            "prompt": prompt,
            "summary": summary,
        })
    return jsonify({"personas": result})


@app.route("/api/personas/<name>", methods=["GET"])
def api_persona_get(name):
    """获取单个博主人格"""
    from src.agents.blogger_agent import _load_personas
    personas = _load_personas()
    if name not in personas:
        return jsonify({"error": f"人格 '{name}' 不存在"}), 404
    return jsonify({
        "name": name,
        "prompt": personas[name],
    })


@app.route("/api/personas/<name>", methods=["POST"])
def api_persona_save(name):
    """保存/更新博主人格"""
    data = request.json or {}
    prompt = (data.get("prompt") or "").strip()

    if not prompt:
        return jsonify({"error": "人格 prompt 不能为空"}), 400

    # 安全检查：名称不能包含特殊字符
    import re
    if not re.match(r"^[\u4e00-\u9fa5a-zA-Z0-9_-]+$", name):
        return jsonify({"error": "人格名称只能包含中文、字母、数字、下划线和横杠"}), 400

    personas_dir = PROJECT_ROOT / "src" / "agents" / "personas"
    personas_dir.mkdir(parents=True, exist_ok=True)

    file_path = personas_dir / f"{name}.md"
    try:
        file_path.write_text(prompt, encoding="utf-8")
        # 清除 BloggerAgent 的缓存
        from src.agents.blogger_agent import BloggerAgent
        BloggerAgent.reload_personas()
        logger.info(f"Saved persona '{name}' to {file_path}")
        return jsonify({"success": True, "message": f"人格 '{name}' 已保存"})
    except Exception as e:
        logger.error(f"Failed to save persona: {e}")
        return jsonify({"error": f"保存失败: {e}"}), 500


@app.route("/api/personas/<name>", methods=["DELETE"])
def api_persona_delete(name):
    """删除博主人格"""
    personas_dir = PROJECT_ROOT / "src" / "agents" / "personas"
    file_path = personas_dir / f"{name}.md"

    if not file_path.exists():
        return jsonify({"error": f"人格 '{name}' 不存在"}), 404

    try:
        file_path.unlink()
        from src.agents.blogger_agent import BloggerAgent
        BloggerAgent.reload_personas()
        logger.info(f"Deleted persona '{name}'")
        return jsonify({"success": True, "message": f"人格 '{name}' 已删除"})
    except Exception as e:
        logger.error(f"Failed to delete persona: {e}")
        return jsonify({"error": f"删除失败: {e}"}), 500


@app.route("/api/personas/generate", methods=["POST"])
def api_persona_generate():
    """使用 LLM 生成博主人格 prompt"""
    data = request.json or {}
    persona_concept = (data.get("concept") or "").strip()

    if not persona_concept:
        return jsonify({"error": "人格概念描述不能为空"}), 400

    try:
        from src.utils.llm_client import get_llm_client
        client = get_llm_client()

        system_prompt = """你是一位专业的投资人格设计师。用户会描述一个投资者的人格特点，你需要生成一个完整的系统提示词（System Prompt），用于让 AI 模拟这个人格。

输出要求：
1. 使用 Markdown 格式
2. 包含以下部分：
   - # 人格名 - 系统提示词
   - ## 角色定义：描述这个人格的核心特征
   - ## 交互协议：描述在多人讨论中如何与其他人格互动
   - ## 认知与推演机制：描述分析问题的思维步骤
   - ## 风格与语言：描述说话风格、高频词汇
   - ## 回答要求：描述输出格式要求
3. 总字数控制在 400-600 字
4. 只输出 prompt 内容，不要输出其他解释"""

        user_prompt = f"请为以下投资人格生成系统提示词：\n\n{persona_concept}"

        response = client.chat.completions.create(
            model=client.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.8,
            max_tokens=800,
        )

        generated_prompt = response.choices[0].message.content.strip()
        logger.info(f"Generated persona prompt for concept: {persona_concept[:50]}...")
        return jsonify({"success": True, "prompt": generated_prompt})

    except Exception as e:
        logger.error(f"Failed to generate persona: {e}")
        return jsonify({"error": f"生成失败: {e}"}), 500


@app.route("/api/config")
def api_config():
    """获取当前配置（隐藏 API Key）"""
    from src.utils.config import get_config
    config = get_config()
    return jsonify({
        "default_llm_provider": config.default_llm_provider,
        "providers": {
            name: bool(config.get_api_key(name))
            for name in ["zhipu", "deepseek", "openai", "qwen", "minimax", "kimi", "openrouter"]
        },
    })


@app.route("/api/settings")
def api_settings():
    """获取 .env 文件的完整配置，用于设置页面编辑"""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return jsonify({"error": ".env 文件不存在"}), 404

    from src.utils.config import get_config
    config = get_config()

    # 构建 provider 配置列表
    providers = [
        {
            "key": "DEFAULT_LLM_PROVIDER",
            "label": "默认 LLM",
            "type": "select",
            "options": ["zhipu", "deepseek", "openai", "qwen", "minimax", "kimi"],
            "value": config.default_llm_provider,
        },
    ]

    provider_info = {
        "zhipu": {"key": "ZHIPU_API_KEY", "label": "智谱 AI", "model_key": "ZHIPU_MODEL", "default_model": "glm-4-flash"},
        "deepseek": {"key": "DEEPSEEK_API_KEY", "label": "DeepSeek", "model_key": "DEEPSEEK_MODEL", "default_model": "deepseek-chat"},
        "openai": {"key": "OPENAI_API_KEY", "label": "OpenAI", "model_key": "OPENAI_MODEL", "default_model": "gpt-4o-mini"},
        "qwen": {"key": "QWEN_API_KEY", "label": "通义千问", "model_key": "QWEN_MODEL", "default_model": "qwen-plus"},
        "minimax": {"key": "MINIMAX_API_KEY", "label": "MiniMax", "model_key": "MINIMAX_MODEL", "default_model": "MiniMax-M2.7"},
        "kimi": {"key": "KIMI_API_KEY", "label": "Kimi", "model_key": "KIMI_MODEL", "default_model": "kimi-k2.5"},
    }

    for name, info in provider_info.items():
        api_key = config.get_api_key(name)
        model_val = getattr(config, f"{name}_model", info["default_model"])

        providers.append({
            "key": info["key"],
            "label": info["label"],
            "type": "provider",
            "provider_name": name,
            "api_key": api_key or "",
            "api_key_masked": (api_key[:8] + "..." + api_key[-4:]) if api_key and len(api_key) > 12 else (api_key or ""),
            "model_key": info["model_key"],
            "model_value": model_val,
            "has_key": bool(api_key),
        })

    return jsonify({"providers": providers, "env_exists": True})


@app.route("/api/settings", methods=["POST"])
def api_settings_save():
    """保存设置到 .env 文件"""
    data = request.json or {}
    env_path = PROJECT_ROOT / ".env"

    try:
        # 读取现有 .env 文件内容
        existing_lines = []
        if env_path.exists():
            existing_lines = env_path.read_text(encoding="utf-8").splitlines()

        # 构建 key -> (新值, 是否更新) 的映射
        updates = {}
        for item in data.get("providers", []):
            if item.get("type") == "select":
                updates[item["key"]] = item["value"]
            elif item.get("type") == "provider":
                api_key_val = (item.get("api_key") or "").strip()
                model_val = (item.get("model_value") or "").strip()
                if api_key_val:
                    updates[item["key"]] = api_key_val
                if model_val:
                    updates[item["model_key"]] = model_val

        if not updates:
            return jsonify({"error": "没有需要保存的变更"}), 400

        # 更新或追加配置行
        updated_keys = set()
        new_lines = []
        for line in existing_lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                new_lines.append(line)
                continue

            if "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key in updates:
                    new_lines.append(f"{key}={updates[key]}")
                    updated_keys.add(key)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        # 追加新的 key
        for key, value in updates.items():
            if key not in updated_keys:
                new_lines.append(f"{key}={value}")

        # 确保末尾有换行
        content = "\n".join(new_lines)
        if not content.endswith("\n"):
            content += "\n"

        env_path.write_text(content, encoding="utf-8")

        # 强制更新环境变量并重置全局配置实例
        import os as _os
        for key, value in updates.items():
            _os.environ[key] = value
        # 重置全局配置缓存，下次 get_config() 会重新读取
        from src.utils import config as _cfg_mod
        _cfg_mod._config = None

        return jsonify({"success": True, "message": "配置已保存"})
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")
        return jsonify({"error": f"保存失败: {e}"}), 500


@app.route("/api/history")
def api_history():
    """获取历史分析报告列表"""
    analysis_dir = PROJECT_ROOT / "output" / "analysis"
    reports = []
    if analysis_dir.exists():
        for f in sorted(analysis_dir.glob("analysis_*.md"), reverse=True):
            reports.append({
                "filename": f.name,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "size_kb": round(f.stat().st_size / 1024, 1),
            })
    return jsonify({"reports": reports[:50]})


@app.route("/api/history/<filename>")
def api_history_detail(filename):
    """获取指定历史报告内容"""
    filepath = PROJECT_ROOT / "output" / "analysis" / filename
    if not filepath.exists():
        return jsonify({"error": "文件不存在"}), 404
    content = filepath.read_text(encoding="utf-8")
    return jsonify({"filename": filename, "content": content})


@app.route("/api/posts")
def api_posts():
    """获取 output/news/ 下所有 md 文件列表"""
    news_dir = PROJECT_ROOT / "output" / "news"
    posts = []
    if news_dir.exists():
        for f in sorted(news_dir.glob("*.md"), reverse=True):
            posts.append({
                "filename": f.name,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "size_kb": round(f.stat().st_size / 1024, 1),
            })
    return jsonify({"posts": posts[:100]})


@app.route("/api/posts/<filename>", methods=["GET", "DELETE"])
def api_posts_detail(filename):
    """获取或删除指定博主帖子"""
    news_dir = PROJECT_ROOT / "output" / "news"
    filepath = news_dir / filename

    if request.method == "DELETE":
        json_path = news_dir / filename.replace(".md", ".json")
        deleted = []
        for p in (filepath, json_path):
            if p.exists():
                p.unlink()
                deleted.append(p.name)
        if not deleted:
            return jsonify({"error": "文件不存在"}), 404
        return jsonify({"deleted": deleted})

    # GET
    if not filepath.exists():
        return jsonify({"error": "文件不存在"}), 404
    content = filepath.read_text(encoding="utf-8")
    return jsonify({"filename": filename, "content": content})


# ============================================================================
# 盘口雷达 API
# ============================================================================

@app.route("/api/radar/status")
def api_radar_status():
    """检查本地日K数据状态，返回最新日期等信息"""
    import pandas as pd
    market_data_dir = PROJECT_ROOT / "src" / "features" / "pankou_rador" / "market_data"
    daily_cache = market_data_dir / "daily_all.csv"

    if not daily_cache.exists():
        return jsonify({"ready": False, "message": "未找到本地数据，请先下载"})

    try:
        df = pd.read_csv(daily_cache)
        if df.empty:
            return jsonify({"ready": False, "message": "数据文件为空"})

        df["trade_date"] = pd.to_datetime(df["trade_date"])
        last_date = str(df["trade_date"].max())[:10]
        first_date = str(df["trade_date"].min())[:10]
        stock_count = df["ts_code"].nunique()
        record_count = len(df)

        # 获取可用的交易日列表
        valid_dates = sorted(df["trade_date"].unique().tolist())
        dates_list = [str(d)[:10] for d in valid_dates]

        return jsonify({
            "ready": True,
            "last_date": last_date,
            "first_date": first_date,
            "stock_count": stock_count,
            "record_count": record_count,
            "dates": dates_list,
        })
    except Exception as e:
        return jsonify({"ready": False, "message": f"读取数据失败: {e}"})


@app.route("/api/radar/download", methods=["POST"])
def api_radar_download():
    """下载/更新全A股日K数据（SSE 流式推送进度）"""
    task_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    event_queue: queue.Queue = queue.Queue()
    _task_events[task_id] = event_queue

    thread = threading.Thread(
        target=_run_radar_download,
        args=(task_id, event_queue),
        daemon=True,
    )
    thread.start()

    return jsonify({"task_id": task_id})


@app.route("/api/radar/stream/<task_id>")
def api_radar_stream(task_id):
    """SSE 流式端点，推送盘口雷达任务进度"""
    event_queue = _task_events.get(task_id)
    if not event_queue:
        return jsonify({"error": "任务不存在"}), 404

    def generate():
        while True:
            try:
                msg = event_queue.get(timeout=300)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                if msg.get("type") == "done" or msg.get("type") == "error":
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        _task_events.pop(task_id, None)

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@app.route("/api/radar/screen", methods=["POST"])
def api_radar_screen():
    """使用 gain_ranker_date.py 规则筛选股票（SSE 流式推送进度）"""
    data = request.json or {}
    end_date = data.get("end_date", "")

    if not end_date:
        return jsonify({"error": "请指定日期"}), 400

    task_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    event_queue: queue.Queue = queue.Queue()
    _task_events[task_id] = event_queue

    thread = threading.Thread(
        target=_run_radar_screen,
        args=(task_id, event_queue, end_date),
        daemon=True,
    )
    thread.start()

    return jsonify({"task_id": task_id})


# ============================================================================
# 盘口雷达后台任务
# ============================================================================

def _run_radar_download(task_id: str, event_queue: queue.Queue):
    """后台线程：下载/更新日K数据"""
    try:
        import sys
        import io
        from src.features.pankou_rador.stock_screener import (
            _ensure_dirs, ensure_data_fresh, fetch_stock_list
        )
        import pandas as pd

        event_queue.put({"type": "log", "message": "开始下载/更新日K数据..."})
        _ensure_dirs()

        # 获取股票列表
        event_queue.put({"type": "log", "message": "正在获取股票列表..."})
        stock_list = fetch_stock_list()
        if stock_list.empty:
            event_queue.put({"type": "error", "message": "无法获取股票列表"})
            return

        event_queue.put({"type": "log", "message": f"股票列表: {len(stock_list)} 只"})

        # 执行数据下载/更新
        event_queue.put({"type": "log", "message": "正在下载日K数据（首次可能需要数分钟）..."})
        df = ensure_data_fresh()

        if df is None or df.empty:
            event_queue.put({"type": "error", "message": "数据下载失败"})
            return

        last_date = str(df["trade_date"].max())[:10]
        stock_count = df["ts_code"].nunique()
        record_count = len(df)

        event_queue.put({"type": "log", "message": f"数据就绪: {stock_count} 只股票, {record_count} 条记录, 最新 {last_date}"})

        # 获取可用日期列表
        valid_dates = sorted(df["trade_date"].unique().tolist())
        dates_list = [str(d)[:10] for d in valid_dates]

        event_queue.put({
            "type": "done",
            "message": "数据更新完成",
            "last_date": last_date,
            "stock_count": stock_count,
            "record_count": record_count,
            "dates": dates_list,
        })

    except Exception as e:
        logger.exception(f"Radar download failed for task {task_id}")
        event_queue.put({"type": "error", "message": str(e)})


def _run_radar_screen(task_id: str, event_queue: queue.Queue, end_date: str):
    """后台线程：执行涨幅筛选"""
    try:
        import pandas as pd
        from src.features.pankou_rador.gain_ranker_date import (
            CONFIG, ACTIVE_RULES, load_local_data, parse_end_date, get_valid_dates,
            _calc_period_gain, _calc_consecutive_yang,
        )

        event_queue.put({"type": "log", "message": f"正在加载数据..."})

        # 加载数据
        df = load_local_data()
        if df is None:
            event_queue.put({"type": "error", "message": "本地数据不存在，请先下载数据"})
            return

        valid_dates = get_valid_dates(df)
        event_queue.put({"type": "log", "message": f"数据范围: {valid_dates[0]} ~ {valid_dates[-1]}"})

        # 解析日期
        parsed_date = parse_end_date(end_date)
        if parsed_date is None:
            event_queue.put({"type": "error", "message": f"无法解析日期: {end_date}"})
            return

        # 检查是否为交易日，否则取最近的
        if parsed_date not in valid_dates:
            earlier = [d for d in valid_dates if d <= parsed_date]
            if not earlier:
                event_queue.put({"type": "error", "message": f"日期早于数据起始日"})
                return
            actual_date = earlier[-1]
            event_queue.put({"type": "log", "message": f"{parsed_date} 非交易日，使用 {actual_date}"})
        else:
            actual_date = parsed_date

        # 截取数据
        end_ts = pd.Timestamp(actual_date)
        df = df[df["trade_date"] <= end_ts].reset_index(drop=True)

        all_codes = df["ts_code"].unique()
        name_map = df.drop_duplicates("ts_code").set_index("ts_code")["name"].to_dict()

        event_queue.put({"type": "log", "message": f"基准日 {actual_date}, {len(all_codes)} 只股票"})

        # 预拆分：用 groupby 一次性拆分所有股票的 DataFrame，避免 8×N 次全表扫描
        event_queue.put({"type": "log", "message": "正在预处理数据..."})
        stock_dfs = {}
        for code, stock_df in df.groupby("ts_code"):
            stock_dfs[code] = stock_df.reset_index(drop=True)
        event_queue.put({"type": "log", "message": f"数据预处理完成（{len(stock_dfs)} 只）"})

        # 遍历规则计算
        all_rule_results = []

        for rule_entry in ACTIVE_RULES:
            rule_func = rule_entry["func"]
            config_key = rule_entry["config_key"]
            rule_params = CONFIG["rules"].get(config_key, {})
            rule_label = rule_params.get("label", rule_entry["name"])
            rule_type = rule_params.get("type", "gain")
            top_n = rule_params.get("top_n", CONFIG.get("top_n", 30))

            event_queue.put({"type": "log", "message": f"正在计算: {rule_label}..."})

            hits = []
            for code in all_codes:
                try:
                    stock_df = stock_dfs.get(code)
                    if stock_df is None or stock_df.empty:
                        continue
                    result = rule_func(stock_df, rule_params)
                    if result is not None:
                        name = name_map.get(code, "未知")
                        hits.append({
                            "code": code,
                            "name": name,
                            "gain": result["gain"],
                            "start_date": result["start_date"],
                            "end_date": result["end_date"],
                            "start_price": result["start_price"],
                            "end_price": result["end_price"],
                        })
                except Exception:
                    continue

            hits.sort(key=lambda x: x["gain"], reverse=True)
            if top_n is not None:
                hits = hits[:top_n]

            all_rule_results.append({
                "label": rule_label,
                "type": rule_type,
                "hits": hits,
            })

            event_queue.put({
                "type": "rule_done",
                "rule": rule_label,
                "count": len(hits),
            })

        event_queue.put({
            "type": "done",
            "message": f"筛选完成（基准日: {actual_date}）",
            "results": all_rule_results,
            "base_date": actual_date,
        })

    except Exception as e:
        logger.exception(f"Radar screen failed for task {task_id}")
        event_queue.put({"type": "error", "message": str(e)})


# ============================================================================
# 帖子爬虫 API
# ============================================================================

# 人气热股内存缓存
_hot_stocks_cache = {"data": None, "ts": 0}
_HOT_STOCKS_TTL = 300  # 缓存有效期 5 分钟


@app.route("/api/hot_stocks")
def api_hot_stocks():
    """获取人气热股数据（东财 + 同花顺双榜），带 5 分钟内存缓存"""
    import time
    # 强制刷新参数
    force = request.args.get("force", "").lower() in ("1", "true")

    if not force and _hot_stocks_cache["data"] and (time.time() - _hot_stocks_cache["ts"]) < _HOT_STOCKS_TTL:
        resp = _hot_stocks_cache["data"]
        resp["cached"] = True
        return jsonify(resp)

    try:
        from src.features.hot_stock.hot_stocks import fetch_hot_stocks
        data = fetch_hot_stocks(top_n=100, source="all")
        resp = {
            "success": True,
            "dc": data.get("dc", []),
            "ths": data.get("ths", []),
            "both": data.get("both", []),
            "cached": False,
        }
        _hot_stocks_cache["data"] = resp
        _hot_stocks_cache["ts"] = time.time()
        return jsonify(resp)
    except Exception as e:
        logger.error(f"Failed to fetch hot stocks: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/crawl/start", methods=["POST"])
def api_crawl_start():
    """启动帖子抓取任务（SSE 流式推送进度）"""
    data = request.json or {}
    bloggers = data.get("bloggers", [])
    start_date = data.get("start_date", "")
    end_date = data.get("end_date", "")
    max_posts = int(data.get("max_posts", 100))
    max_comments = int(data.get("max_comments", 0))

    if not bloggers:
        return jsonify({"error": "请选择至少一个博主"}), 400
    if not start_date or not end_date:
        return jsonify({"error": "请指定日期范围"}), 400

    task_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    event_queue: queue.Queue = queue.Queue()
    _task_events[task_id] = event_queue

    thread = threading.Thread(
        target=_run_crawl,
        args=(task_id, event_queue, bloggers, start_date, end_date, max_posts, max_comments),
        daemon=True,
    )
    thread.start()

    return jsonify({"task_id": task_id})


@app.route("/api/crawl/stream/<task_id>")
def api_crawl_stream(task_id):
    """SSE 流式端点，推送爬虫进度"""
    event_queue = _task_events.get(task_id)
    if not event_queue:
        return jsonify({"error": "任务不存在"}), 404

    def generate():
        while True:
            try:
                msg = event_queue.get(timeout=300)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                if msg.get("type") == "done" or msg.get("type") == "error":
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        _task_events.pop(task_id, None)

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


def _run_crawl(task_id, event_queue, bloggers, start_date, end_date, max_posts, max_comments):
    """后台线程：执行帖子抓取"""
    try:
        import os
        from datetime import datetime as dt
        from src.crawler.taoguba_crawler import TaogubaCrawler
        from src.crawler.storage import DateTimeEncoder

        output_dir = PROJECT_ROOT / "output" / "news"
        output_dir.mkdir(parents=True, exist_ok=True)

        names = ", ".join(b["username"] for b in bloggers)
        event_queue.put({"type": "log", "message": f"开始抓取 {len(bloggers)} 个博主: {names}"})
        event_queue.put({"type": "log", "message": f"日期范围: {start_date} ~ {end_date}, 帖数上限: {max_posts}, 评论上限: {max_comments}"})

        start_dt = dt.strptime(start_date, "%Y-%m-%d")
        end_dt = dt.strptime(end_date, "%Y-%m-%d")

        crawler = TaogubaCrawler(
            output_dir=str(output_dir),
            max_comments=max_comments,
            enable_vector_store=False,
            fast_mode=True,  # 启用快速模式
        )

        total_posts = 0
        total_comments = 0
        success_list = []
        failed_list = []

        for idx, b in enumerate(bloggers, 1):
            username = b["username"]
            user_id = b["user_id"]

            event_queue.put({"type": "log", "message": f"[{idx}/{len(bloggers)}] 正在抓取: {username}..."})

            try:
                result = crawler.crawl_blogger(
                    username=username,
                    user_id=user_id,
                    days=7,
                    start_date=start_dt,
                    end_date=end_dt,
                    max_posts=max_posts,
                    max_comments=max_comments,
                )

                total_posts += result.total_posts
                total_comments += result.total_comments
                success_list.append(username)
                event_queue.put({"type": "log", "message": f"  {username}: {result.total_posts} 篇帖子, {result.total_comments} 条评论"})

            except Exception as e:
                failed_list.append(username)
                event_queue.put({"type": "log", "message": f"  {username} 失败: {str(e)}"})
                logger.warning(f"Crawl failed for {username}: {e}")

        event_queue.put({"type": "done", "message": f"抓取完成! 成功 {len(success_list)} 个博主, {total_posts} 篇帖子, {total_comments} 条评论"})

    except Exception as e:
        logger.exception(f"Crawl failed for task {task_id}")
        event_queue.put({"type": "error", "message": str(e)})


# ============================================================================
# 资讯配置 API（投资分析 - 资讯管理）
# ============================================================================

@app.route("/api/news_input")
def api_news_input_list():
    """获取 output/news_input/ 下所有 txt 文件列表"""
    news_input_dir = PROJECT_ROOT / "output" / "news_input"
    files = []
    if news_input_dir.exists():
        for f in sorted(news_input_dir.glob("*.txt"), reverse=True):
            files.append({
                "filename": f.name,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "size_kb": round(f.stat().st_size / 1024, 1),
                "size_chars": f.stat().st_size,
            })
    return jsonify({"files": files})


@app.route("/api/news_input/<filename>", methods=["GET", "DELETE"])
def api_news_input_detail(filename):
    """获取或删除指定资讯文件"""
    news_input_dir = PROJECT_ROOT / "output" / "news_input"
    filepath = news_input_dir / filename

    if request.method == "DELETE":
        if not filepath.exists():
            return jsonify({"error": "文件不存在"}), 404
        filepath.unlink()
        return jsonify({"deleted": filename})

    # GET
    if not filepath.exists():
        return jsonify({"error": "文件不存在"}), 404
    content = filepath.read_text(encoding="utf-8")
    return jsonify({"filename": filename, "content": content})


@app.route("/api/news_input/save", methods=["POST"])
def api_news_input_save():
    """保存用户输入的文本为 txt 文件到 news_input/"""
    data = request.json or {}
    content = data.get("content", "").strip()
    filename = data.get("filename", "").strip()

    if not content:
        return jsonify({"error": "内容不能为空"}), 400

    news_input_dir = PROJECT_ROOT / "output" / "news_input"
    news_input_dir.mkdir(parents=True, exist_ok=True)

    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"news_input_{timestamp}.txt"
    elif not filename.endswith(".txt"):
        filename += ".txt"

    filepath = news_input_dir / filename
    # 安全检查：防止路径穿越
    if not filepath.resolve().parent == news_input_dir.resolve():
        return jsonify({"error": "非法文件名"}), 400

    filepath.write_text(content, encoding="utf-8")
    return jsonify({"saved": filename})


@app.route("/api/news_input/import_from_news", methods=["POST"])
def api_news_input_import():
    """将 output/news/ 下的 txt 文件复制到 output/news_input/"""
    news_dir = PROJECT_ROOT / "output" / "news"
    news_input_dir = PROJECT_ROOT / "output" / "news_input"
    news_input_dir.mkdir(parents=True, exist_ok=True)

    data = request.json or {}
    filenames = data.get("filenames", [])

    if not filenames:
        return jsonify({"error": "请选择要导入的文件"}), 400

    imported = []
    errors = []
    for fname in filenames:
        src = news_dir / fname
        if not src.exists():
            errors.append(f"{fname}: 文件不存在")
            continue
        # 只处理 txt 文件
        if not fname.endswith(".txt"):
            errors.append(f"{fname}: 仅支持 txt 文件")
            continue
        dst = news_input_dir / fname
        # 如果目标已存在，添加时间戳避免覆盖
        if dst.exists():
            stem = dst.stem
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dst = news_input_dir / f"{stem}_{ts}.txt"
        try:
            import shutil
            shutil.copy2(str(src), str(dst))
            imported.append(dst.name)
        except Exception as e:
            errors.append(f"{fname}: 复制失败 ({e})")

    return jsonify({"imported": imported, "errors": errors})


@app.route("/api/news/generate", methods=["POST"])
def api_news_generate():
    """使用 LLM 生成市场资讯，返回生成结果供用户复制"""
    data = request.json or {}
    topic = (data.get("topic") or "").strip()

    try:
        from src.agents.news_agent import NewsAgent
        agent = NewsAgent()

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        if topic:
            prompt = f"""请基于当前时间 ({now_str})，针对以下主题搜集和整理市场资讯：

主题：{topic}

请提供：
1. 最新市场动态（新闻、公告）
2. 相关板块/个股表现
3. 宏观经济影响因素
4. 市场情绪概况

请以结构化格式输出，便于后续分析使用。"""
        else:
            prompt = f"""请基于当前时间 ({now_str})，搜集和整理最新的 A 股市场资讯。

请提供：
1. 今日大盘表现（上证指数、深证成指、创业板指）
2. 热门板块和概念
3. 重要个股新闻和公告
4. 北向资金动态
5. 宏观经济和政策面信息
6. 市场情绪概况

请以结构化格式输出，便于后续投资分析使用。"""

        result = agent.chat(prompt)
        return jsonify({"content": result, "error": None})
    except Exception as e:
        logger.error(f"News generation failed: {e}")
        return jsonify({"content": "", "error": str(e)}), 500


@app.route("/api/news/news_txt_list")
def api_news_txt_list():
    """获取 output/news/ 下所有 txt 文件列表（用于导入选择）"""
    news_dir = PROJECT_ROOT / "output" / "news"
    files = []
    if news_dir.exists():
        for f in sorted(news_dir.glob("*.txt"), reverse=True):
            files.append({
                "filename": f.name,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "size_kb": round(f.stat().st_size / 1024, 1),
            })
    return jsonify({"files": files})


@app.route("/api/analysis/run", methods=["POST"])
def api_analysis_run():
    """启动投资分析（SSE 流式推送）"""
    data = request.json or {}
    query = data.get("query", "").strip()
    blogger_names = data.get("bloggers", [])
    discussion_rounds = int(data.get("rounds", 1))
    llm_provider = data.get("llm_provider", "")

    if not query:
        return jsonify({"error": "请输入投资问题"}), 400

    task_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    event_queue: queue.Queue = queue.Queue()
    _task_events[task_id] = event_queue

    # 在后台线程中运行工作流
    thread = threading.Thread(
        target=_run_workflow_background,
        args=(task_id, event_queue, query, blogger_names, discussion_rounds, llm_provider),
        daemon=True,
    )
    thread.start()

    return jsonify({"task_id": task_id})


@app.route("/api/analysis/stream/<task_id>")
def api_analysis_stream(task_id):
    """SSE 流式端点，推送工作流进度"""
    event_queue = _task_events.get(task_id)
    if not event_queue:
        return jsonify({"error": "任务不存在"}), 404

    def generate():
        while True:
            try:
                msg = event_queue.get(timeout=120)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                if msg.get("type") == "done" or msg.get("type") == "error":
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        # 清理
        _task_events.pop(task_id, None)

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


# ============================================================================
# 后台工作流执行
# ============================================================================

def _run_workflow_background(
    task_id: str,
    event_queue: queue.Queue,
    query: str,
    blogger_names: list,
    discussion_rounds: int,
    llm_provider: str,
):
    """在后台线程中执行工作流，通过 event_queue 推送进度"""
    step_labels = ["资讯获取", "博主讨论", "风险评估", "最终决策"]
    step_icons = ["newspaper", "comments", "shield-alert", "gavel"]

    try:
        # 推送：工作流开始
        event_queue.put({
            "type": "start",
            "query": query,
            "bloggers": blogger_names,
            "rounds": discussion_rounds,
            "steps": step_labels,
        })

        # 定义博主讨论进度回调
        def blogger_progress_callback(current: int, total: int, blogger_name: str):
            event_queue.put({
                "type": "blogger_progress",
                "current": current,
                "total": total,
                "blogger_name": blogger_name,
            })

        # 初始化工作流
        from src.agents.investment_workflow import InvestmentWorkflow
        workflow = InvestmentWorkflow(
            blogger_names=blogger_names,
            discussion_rounds=discussion_rounds,
            llm_provider=llm_provider or None,
            progress_callback=blogger_progress_callback,
        )

        # 逐步执行，推送进度
        start_time = datetime.now()

        for i, (label, state) in enumerate(
            zip(step_labels, workflow.run_stream(query)), 1
        ):
            event_queue.put({
                "type": "step_done",
                "step_index": i - 1,
                "step_label": label,
                "step_icon": step_icons[i - 1],
                "duration": round((datetime.now() - start_time).total_seconds(), 1),
            })

            # 推送各步骤的数据
            if i == 1:
                # 资讯获取
                summary = getattr(state, "market_summary", "") or ""
                raw_content = getattr(state, "raw_news_content", "") or ""
                # 优先用 raw_news_content（本地文件原文），其次用 market_summary（LLM 生成）
                news_text = raw_content or summary
                is_llm_generated = bool(summary and not raw_content)
                logger.info(f"News data pushed: summary={len(summary)}chars, raw={len(raw_content)}chars, is_llm={is_llm_generated}")
                event_queue.put({
                    "type": "step_data",
                    "step": "news",
                    "data": {
                        "summary": news_text or "（无资讯内容）",
                        "is_llm_generated": is_llm_generated,
                    },
                })
            elif i == 2:
                # 博主讨论
                discussions = []
                for d in state.blogger_discussions:
                    discussions.append({
                        "round": d.get("round", ""),
                        "speaker": d.get("speaker", ""),
                        "content": d.get("content", ""),
                    })
                event_queue.put({
                    "type": "step_data",
                    "step": "bloggers",
                    "data": {
                        "discussions": discussions,
                        "consensus": state.blogger_consensus or "",
                    },
                })
            elif i == 3:
                # 风险评估
                event_queue.put({
                    "type": "step_data",
                    "step": "risk",
                    "data": {
                        "level": state.risk_level or "medium",
                        "assessment": state.risk_assessment or "",
                        "warnings": state.risk_warnings or [],
                    },
                })
            elif i == 4:
                # 最终决策
                event_queue.put({
                    "type": "step_data",
                    "step": "decision",
                    "data": {
                        "answer": state.final_answer or "（无决策）",
                    },
                })

        total_time = round((datetime.now() - start_time).total_seconds(), 1)

        # 推送：工作流完成
        event_queue.put({
            "type": "done",
            "total_time": total_time,
        })

        # 保存报告
        _save_report(query, blogger_names, discussion_rounds, state, total_time)

    except Exception as e:
        logger.exception(f"Workflow failed for task {task_id}")
        event_queue.put({
            "type": "error",
            "message": str(e),
        })


def _save_report(query, blogger_names, discussion_rounds, state, total_time):
    """保存分析报告到 output/analysis/"""
    output_dir = PROJECT_ROOT / "output" / "analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_query = query[:30].replace(" ", "_").replace("/", "_")
    filename = f"analysis_{safe_query}_{timestamp}.md"

    lines = []
    lines.append("# 投资分析报告")
    lines.append("")
    lines.append(f"**问题**: {query}")
    lines.append(f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**博主**: {', '.join(blogger_names)}")
    lines.append(f"**讨论轮数**: {discussion_rounds}")
    lines.append(f"**风险等级**: {(state.risk_level or 'medium').upper()}")
    lines.append(f"**耗时**: {total_time}s")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 市场资讯")
    lines.append("")
    lines.append(state.market_summary or "（无）")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 博主讨论记录")
    lines.append("")
    for d in state.blogger_discussions:
        lines.append(f"### 第{d.get('round', '?')}轮 · {d.get('speaker', '?')}")
        lines.append("")
        lines.append(d.get("content", ""))
        lines.append("")
    if state.blogger_consensus:
        lines.append("### 共识")
        lines.append("")
        lines.append(state.blogger_consensus)
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 风险评估")
    lines.append("")
    lines.append(state.risk_assessment or "（无）")
    lines.append("")
    if state.risk_warnings:
        lines.append("**风险警告:**")
        for w in state.risk_warnings:
            lines.append(f"- {w}")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 最终决策")
    lines.append("")
    lines.append(state.final_answer or "（无）")
    lines.append("")

    filepath = output_dir / filename
    filepath.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Report saved: {filepath}")


# ============================================================================
# 启动入口
# ============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="淘股宝 Web 界面")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=5000, help="监听端口")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    args = parser.parse_args()

    print()
    print("=" * 50)
    print("  淘股宝 Web 界面")
    print(f"  http://localhost:{args.port}")
    print("=" * 50)
    print()

    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
