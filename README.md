# 淘股宝 - 多 Agent 投资分析系统

基于淘股吧数据的多 Agent 协作投资分析系统。通过爬取淘股吧博主帖子，结合大语言模型模拟多人讨论，自动生成包含资讯汇总、博主观点、风险评估和最终决策的投资分析报告。

## 系统架构

```
用户提问
   │
   ▼
┌─────────────────────────────────────────────────────────┐
│                  InvestmentWorkflow                       │
│                   (LangGraph 编排)                       │
│                                                         │
│  ┌──────────┐   ┌──────────────┐   ┌──────────┐   ┌──────────────┐
│  │NewsAgent │──▶│BloggerPanel  │──▶│RiskAgent │──▶│DecisionAgent │
│  │ 资讯获取  │   │  博主讨论     │   │ 风险评估  │   │  最终决策     │
│  └──────────┘   └──────────────┘   └──────────┘   └──────────────┘
│       │               │                                  │
│       ▼               ▼                                  ▼
│  本地资讯/       多轮模拟讨论                       买/卖/持有/观望
│  实时数据        + 共识提取                          + 操作建议
└─────────────────────────────────────────────────────────┘
```

**工作流程：**

1. **NewsAgent** — 搜集市场资讯，生成市场摘要；支持手动输入、从帖子导入、AI 生成资讯
2. **BloggerPanel** — 多个博主人格 Agent 进行多轮讨论，提取市场共识
3. **RiskAgent** — 评估市场风险，输出风险等级（LOW/MEDIUM/HIGH）和风险警告
4. **DecisionAgent** — 综合前三步信息，做出最终投资决策和具体操作建议

## 功能特性

### 核心功能

- **多 Agent 协作投资分析** — 四步工作流自动生成投资报告
- **博主人格模拟** — 支持自定义博主人格，模拟多角度市场讨论
- **RAG 智能问答** — 基于向量数据库的知识检索增强生成
- **精品帖子爬虫** — 支持多博主批量采集，含帖子正文与评论

### 扩展功能

- **盘口雷达** — A 股日线数据筛选工具，支持 8 种涨幅排名规则
- **人气热股** — 东财 + 同花顺双榜热股实时追踪，自动取交集
- **Web 可视化界面** — 仪表盘、投资分析、资讯配置、历史报告一站式管理

## 快速开始

### 1. 安装依赖

```bash
cd 项目根目录
conda create -n taogubao python=3.10  #这一步如果卡住的话，关掉代理
conda activate taogubao
pip install -r requirements.txt --no-deps  #一定要使用--no-deps，总共依赖大小在500MB左右
```

### 2. 配置 API Key

在根目录下复制并编辑 `.env` 文件：

```bash
cp .env.example .env
```
windows环境下
```bash
copy .env.example .env
```


至少配置一个 LLM 提供商的 API Key：

```env
# 默认 LLM 提供商（可选，zhipu, deepseek, openai, qwen, minimax, kimi, openrouter）
DEFAULT_LLM_PROVIDER=zhipu

# OpenRouter（推荐，支持多种模型）
OPENROUTER_API_KEY=your_key
OPENROUTER_MODEL=z-ai/glm-4.5-air:free

# 智谱 AI
ZHIPU_API_KEY=your_key
ZHIPU_MODEL=glm-4.5-air

# 通义千问
QWEN_API_KEY=your_key
QWEN_MODEL=qwen3.5-flash

# DeepSeek
DEEPSEEK_API_KEY=your_key

# OpenAI
OPENAI_API_KEY=your_key

# MiniMax
MINIMAX_API_KEY=your_key

# Kimi (Moonshot)
KIMI_API_KEY=your_key
```

### 3. 启动 Web 界面

```bash
# 默认端口 5000
python -m src.web.app

# 指定端口
python -m src.web.app --port 5001
```

浏览器打开 `http://localhost:5000`，即可使用可视化界面。

### 4. 运行投资分析（命令行）

```bash
# 运行完整的四步投资分析流程
python -m src.cli.run_workflow
```

分析报告自动保存到 `output/analysis/` 目录。

## 支持的 LLM 提供商

| 提供商 | provider | Base URL | 环境变量 | 默认模型 |
|--------|----------|----------|---------|---------|
| OpenRouter | `openrouter` | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | z-ai/glm-4.5-air:free |
| 智谱 AI | `zhipu` | `https://open.bigmodel.cn/api/paas/v4` | `ZHIPU_API_KEY` | glm-4.5-air |
| DeepSeek | `deepseek` | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` | deepseek-chat |
| OpenAI | `openai` | `https://api.openai.com/v1` | `OPENAI_API_KEY` | gpt-4o-mini |
| 通义千问 | `qwen` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `QWEN_API_KEY` | qwen-plus |
| MiniMax | `minimax` | `https://api.minimaxi.com/v1` | `MINIMAX_API_KEY` | MiniMax-M2.7 |
| Kimi | `kimi` | `https://api.moonshot.cn/v1` | `KIMI_API_KEY` | kimi-k2.5 |

模型可通过 `.env` 中的 `ZHIPU_MODEL`、`QWEN_MODEL`、`OPENROUTER_MODEL` 等变量自定义。

### OpenRouter 推荐配置

OpenRouter 是一个统一的 LLM 网关，支持多种模型：

```env
DEFAULT_LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_key
OPENROUTER_MODEL=z-ai/glm-4.5-air:free  # 智谱 GLM-4.5-Air 免费
```

常用模型：
- `z-ai/glm-4.5-air:free` — 智谱 GLM-4.5-Air（免费）
- `anthropic/claude-3.5-sonnet` — Claude 3.5 Sonnet
- `openai/gpt-4-turbo` — GPT-4 Turbo

## Web 界面功能

### 仪表盘
- 系统状态检测（LLM 配置、盘口雷达数据、历史分析）
- Agent 协作架构可视化
- TOP 5 人气热股概览

### 投资分析 Tab
- 投资问题输入
- 博主选择（模拟数字人格讨论，默认 2 个博主）
- 讨论轮数配置（默认 1 轮）
- 分析流程可视化（含博主讨论实时进度）
- 实时 SSE 流式输出
- 折叠卡片式结果展示

### 资讯配置 Tab
- **手动输入** — 粘贴资讯文本保存
- **从帖子导入** — 将爬虫数据导入资讯库
- **管理文件** — 查看/删除资讯文件
- **AI 生成** — 调用 LLM 生成主题资讯

### 精品帖子 Tab
- 帖子列表折叠卡片展示（博主名 + 抓取时间）
- 抓取帖子配置（博主、日期范围、帖数/评论数）
- 懒加载帖子内容
- 同一博主多次抓取可清晰区分

### 盘口雷达 Tab
- 数据状态检测与下载
- 日期选择与 8 种涨幅规则筛选
- 结果表格展示与 CSV 导出

### 人气热股 Tab
- 东财热股榜（TOP 30）
- 同花顺热股榜（TOP 30，含热度值、概念标签）
- 双榜交集（东财 × 同花顺）

## CLI 工具一览

| 命令 | 说明 |
|------|------|
| `python -m src.web.app` | 启动 Web 界面 |
| `python -m src.cli.run_workflow` | 运行完整投资分析工作流 |
| `python -m src.cli.crawl_multi` | 批量爬取多个博主帖子 |
| `python -m src.cli.crawl_only` | 爬取单个博主帖子 |
| `python -m src.cli.extract_news_txt` | 从 JSON 提取帖子为 txt |
| `python -m src.cli.extract_opinions` | 提取博主观点为纯文本 |
| `python -m src.cli.index_to_vector` | 将帖子导入向量数据库 |
| `python -m src.cli.rag_chat` | RAG + LLM 交互式问答 |
| `python -m src.cli.view_vector_db` | 查看向量数据库内容 |
| `python -m src.cli.clear_vector_db` | 清空向量数据库 |
| `python -m src.features.pankou_rador.stock_screener` | 下载全 A 股日线数据 |
| `python -m src.features.pankou_rador.gain_ranker` | 涨幅排行榜（最新交易日） |
| `python -m src.features.pankou_rador.gain_ranker_date` | 涨幅排行榜（指定日期） |
| `python -m src.features.hot_stock.hot_stocks` | 人气热股榜单获取 |

## 项目结构

```
tgb5/
├── .env                          # 环境变量配置（API Key 等）
├── requirements.txt              # Python 依赖
├── src/
│   ├── agents/                   # Agent 模块
│   │   ├── investment_workflow.py    # LangGraph 工作流编排
│   │   ├── base_agent.py             # Agent 基类（LLM 调用）
│   │   ├── blogger_agent.py          # 博主人格 Agent
│   │   ├── blogger_panel.py          # 博主讨论组
│   │   ├── news_agent.py             # 资讯获取 Agent
│   │   ├── risk_agent.py             # 风险评估 Agent
│   │   ├── decision_agent.py         # 最终决策 Agent
│   │   ├── agent_state.py            # Agent 间共享状态
│   │   └── personas/                 # 博主人格配置（.md 文件）
│   ├── crawler/                  # 爬虫模块
│   │   ├── taoguba_crawler.py        # 淘股吧爬虫核心
│   │   ├── models.py                 # 数据模型
│   │   └── storage.py                # 数据存储
│   ├── vector/                   # 向量数据库模块
│   │   └── vector_store.py           # ChromaDB 向量存储
│   ├── rag/                      # RAG 模块
│   │   └── rag_llm.py                # RAG + LLM 系统
│   ├── cli/                      # 命令行工具
│   │   └── ...                       # 各类 CLI 入口
│   ├── web/                      # Web 界面
│   │   ├── app.py                    # Flask 后端（API + SSE）
│   │   ├── templates/index.html      # 前端页面
│   │   └── static/                   # 静态资源（CSS/JS）
│   ├── features/                 # 功能模块
│   │   ├── pankou_rador/             # 盘口雷达
│   │   │   ├── stock_screener.py         # 日线数据下载器
│   │   │   ├── gain_ranker.py            # 涨幅排行榜
│   │   │   ├── gain_ranker_date.py       # 指定日期排行榜
│   │   │   └── market_data/              # 本地 CSV 缓存
│   │   └── hot_stock/                # 人气热股
│   │       └── hot_stocks.py             # 东财/同花顺热榜爬虫
│   └── utils/
│       ├── config.py                 # 配置管理
│       └── llm_client.py             # LLM 客户端工具
├── output/                      # 输出目录
│   ├── news/                     # 爬虫原始数据（JSON + MD）
│   ├── news_input/               # 资讯文本（供 NewsAgent 使用）
│   ├── analysis/                 # 投资分析报告
│   └── view/                     # 提取的观点文本
├── vector_db/                   # ChromaDB 向量数据库
└── logs/                        # 日志文件
```

## 博主人格系统

博主人格通过 `src/agents/personas/` 目录下的 Markdown 文件配置。每个文件对应一个博主，文件名即博主名称，文件内容作为该博主的 System Prompt。

当前已配置的博主：jl韭菜抄家、延边刺客、短狙作手、只核大学生、小宝。

添加新博主：
1. 在 `personas/` 目录下创建 `.md` 文件
2. 编写博主人格描述作为 System Prompt
3. 在 Web 界面或 `run_workflow.py` 中选择该博主

## 盘口雷达

独立的 A 股日线数据筛选工具，用于快速扫描全市场股票并按涨幅、连阳等指标排名。

### 数据准备

```bash
# 首次运行：全量下载（约 70 个自然日）
python -m src.features.pankou_rador.stock_screener

# 后续运行：自动增量更新
python -m src.features.pankou_rador.stock_screener
```

数据缓存到 `src/features/pankou_rador/market_data/`，后续筛选只读本地缓存。

### 涨幅排行榜

```bash
# 以最新交易日为基准
python -m src.features.pankou_rador.gain_ranker

# 以指定日期为基准
python -m src.features.pankou_rador.gain_ranker_date 0325
python -m src.features.pankou_rador.gain_ranker_date 2026-03-25
```

内置 8 个排名规则：

| 规则 | 说明 |
|------|------|
| 近 3/4/5/6/10 日涨幅榜 | 按区间涨幅从高到低排名，每榜 TOP 30 |
| 4/5/6 连阳榜 | 连续 N 日收阳线（close>=open），不限数量 |

结果输出到控制台并保存 CSV 至 `screening_results/`。

## 人气热股

实时追踪东财 + 同花顺热股榜，自动取双榜交集。

```bash
# 获取 TOP 30 热股（默认）
python -m src.features.hot_stock.hot_stocks

# 指定 TOP 数量
python -m src.features.hot_stock.hot_stocks -n 50

# 指定数据源
python -m src.features.hot_stock.hot_stocks -s dc      # 仅东财
python -m src.features.hot_stock.hot_stocks -s ths     # 仅同花顺
```

**数据源说明：**
- 东财榜：Playwright 拦截 + 新浪行情三级降级（push2 → push2his → 新浪）
- 同花顺榜：HTTP 直连 API，含热度值、概念标签、排名变动

## RAG 检索与问答

### 向量化存储

```bash
# 导入 output/ 下所有 JSON
python -m src.cli.index_to_vector

# 导入指定文件
python -m src.cli.index_to_vector --file output/jl韭菜抄家_20260326.json
```

### 交互式问答

```bash
python -m src.cli.rag_chat              # 默认提供商
python -m src.cli.rag_chat --llm qwen   # 指定通义千问
```

## 技术栈

- **Scrapling** — 自适应网页抓取框架
- **LangGraph** — 多 Agent 工作流编排
- **ChromaDB** — 向量数据库
- **Sentence-Transformers** — 多语言文本嵌入
- **OpenAI SDK** — 统一 LLM 调用接口
- **Flask** — Web 后端 + SSE 流式推送
- **Pydantic** — 数据模型验证
- **Loguru** — 日志记录

## 注意事项

- 请遵守目标网站的 robots.txt 和相关法律法规
- 建议保持默认的请求间隔（1-3 秒），避免对目标网站造成压力
- 投资分析报告仅供参考，不构成投资建议

