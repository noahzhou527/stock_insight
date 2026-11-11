# Stock Insight · B 方向（FastAPI + SPA）实施方案

> 状态：**v1 执行版**（2026-11-11 复核修订）。可直接交给执行方（Opus）按阶段实施。
> 前置阅读：[frontend-upgrade-audit.md](frontend-upgrade-audit.md)（现状诊断；本文引用其编号，如 B1、§2.7）。
> 两份文档冲突时，**以本文为准**。

## 0. 已定事项（不再讨论）

| 事项 | 决定 |
|---|---|
| 方向 | B：FastAPI 后端 + 独立前端（SPA），替换 Streamlit |
| 运行环境 | 只在本机运行（Windows 11）。部署暂缓，见诊断报告 §6 |
| 数据源 | **只用免费源**。不使用 iFinD；iFinD 版已归档为 `archive/ifind`（标签 `ifind-archive-2026-11-11`），不迁移代码，只借鉴自选表的列设计 |
| 基线 | `main`（2026-11-11 起指向 public 版；`public-data` 分支与之相同） |
| 本机工具链（已核实） | Python 3.13.5、pandas 3.0、yfinance 1.5、curl_cffi 0.15、Node 24.18、npm 11、Docker 28 |

本文中原先留给"拍板"的技术选择，已在 §2 和 §11 给出默认决定，执行方**按默认执行**，不必再问；只有 §11 末尾列出的三件事需要用户确认。

---

## 1. 目标与非目标

**目标**
1. 前后端分离：FastAPI 提供 JSON API，SPA 负责全部交互与渲染。
2. 现有功能全部保留（§8 清单是验收依据），并补上 ifind 分支里自选表的增强列（用免费源实现）。
3. 数据层改为 SQLite：日线增量补齐，统一记录来源、币种、抓取时间。
4. 用 `MarketDataProvider` 接口封装多个免费源，按"主源 → 回退链"组合。
5. URL 可分享（如 `/stock/CN/300308.SZ?range=1y`），浏览器前进/后退可用，首屏不再"空跑一轮"。
6. 主题与涨跌配色由 CSS 变量（design tokens）驱动。

**非目标（本轮不做）**
- 公网部署、多用户、登录。
- 接入 LLM。现有"AI 驱动的投资分析"改为中性的"技术信号摘要"（B3）。
- 新增市场；节假日交易日历；持仓成本与收益；行情历史回放。
- SSE / WebSocket 推送、后台定时任务（见 §4.4，用轮询代替）。
- 原生移动 App（只做响应式网页）。

---

## 2. 技术选型（已定）

| 层 | 选择 | 说明 |
|---|---|---|
| 后端 | FastAPI + Pydantic v2 + uvicorn | 路由函数一律写普通 `def`（不是 `async def`）：现有取数代码全是同步的（curl_cffi、yfinance），FastAPI 会自动放进线程池 |
| 数据库 | SQLite（WAL 模式）+ SQLAlchemy 2.0 + Alembic | 每个请求一个 Session；`check_same_thread=False` |
| 依赖 | 沿用根目录 `.venv` + pip；新建 `backend/requirements.txt`，**版本全部用 `==` 锁定** | 不引入 uv，保持和现有启动方式一致 |
| 前端 | React + TypeScript + Vite（均用当前稳定版，由 lockfile 锁定） | |
| 路由 | TanStack Router | URL 查询参数有类型校验 |
| 数据请求 | TanStack Query | 缓存、过期、`refetchInterval` 轮询 |
| 客户端状态 | Zustand（很少量） | 只放纯 UI 状态 |
| 表格 | TanStack Table + TanStack Virtual | |
| K 线 / 分时 | TradingView lightweight-charts（v5，支持多窗格） | 时间轴按"根数"排列，天然没有周末和午休空档，不需要 Plotly 那套 rangebreaks |
| 其它图表 | ECharts（按需引入） | 财报柱图、同业对比、涨跌家数 |
| UI | Tailwind CSS + shadcn/ui | 组件源码进仓库，可完全自定义 |
| 测试 | pytest；Vitest + Testing Library；Playwright | |

lightweight-charts 已知限制：没有内置的"两条线之间填充"，BOLL 带先画三条线，不填充。若 P3 样张阶段发现它无法满足分时图的"价格轴 + 涨跌幅轴"双轴，则 K 线与分时整体改用 ECharts，其余不变。

---

## 3. 仓库结构

**迁移期间不移动现有文件**：根目录的 Streamlit 版保持原样、随时可运行（它继续用 `data/cache/` 的 CSV）；新代码全部放在 `backend/` 和 `frontend/`，把旧模块的逻辑**移植**过去，而不是 import 根目录模块。到 P6 才删除旧文件。

```text
stock-insight/
├─ backend/
│  ├─ requirements.txt
│  ├─ app/
│  │  ├─ main.py              # FastAPI 入口；存在 frontend/dist 时一并托管静态文件
│  │  ├─ config.py            # DB 路径、各源开关、回退顺序、TTL、限速（pydantic-settings）
│  │  ├─ api/                 # 路由层：参数校验 + DTO，不写业务逻辑
│  │  ├─ domain/              # 纯函数，无 I/O
│  │  │  ├─ indicators.py     # ← analysis.py
│  │  │  ├─ snapshot.py       # ← app.py 的 compute_snapshot_metrics
│  │  │  ├─ signals.py        # ← investment_insights_view.py 的规则
│  │  │  ├─ watchlist.py      # ← watchlist.py 的 normalize_ticker / summarize_watchlist
│  │  │  ├─ rankings.py       # ← market_snapshot.py 的 rank_snapshot
│  │  │  ├─ new_listing.py    # ← new_listing.py
│  │  │  └─ sessions.py       # 各市场交易时段判断（← services/market_data.py）
│  │  ├─ providers/
│  │  │  ├─ base.py           # 协议、数据类、DataFetchError
│  │  │  ├─ http.py           # 统一的会话、超时、限速、代理处理（合并三份 _clear_broken_local_proxy）
│  │  │  ├─ ths.py            # 同花顺公开页
│  │  │  ├─ eastmoney.py      # 东方财富公开接口
│  │  │  ├─ yahoo.py  stooq.py
│  │  │  └─ composite.py      # 按"市场 × 能力"路由与回退
│  │  ├─ news/                # ← news_fetcher.py
│  │  ├─ repo/                # 数据库读写
│  │  ├─ services/            # 编排：读库 → 判断是否过期 → 调 Provider → 落库 → 返回
│  │  └─ db/                  # models.py、session.py、migrations/
│  ├─ scripts/migrate_legacy_cache.py
│  └─ tests/                  # 含 fixtures/（录制的真实响应）
├─ frontend/
│  ├─ src/{routes,components,charts,api,theme,lib}/
│  └─ vite.config.ts          # 开发时把 /api 代理到 127.0.0.1:8000
├─ data/                      # stock_insight.db（新）+ cache/（旧，保留）
├─ Dockerfile                 # P6
├─ start.bat                  # P6：新的唯一启动器
└─ （根目录旧 Streamlit 文件，P6 删除）
```

- 后端只监听 `127.0.0.1`；开发时前端走 Vite 代理，生产时同源，因此不需要配置 CORS。
- 前端 TS 类型由后端 OpenAPI 生成（`openapi-typescript`），DTO 只定义一次。

---

## 4. 后端设计

### 4.1 Provider 接口

```python
class MarketDataProvider(Protocol):
    name: str                                   # "同花顺" / "东方财富" / "Yahoo" / "Stooq"
    def daily_bars(self, inst, start: date, end: date) -> Bars: ...
    def intraday(self, inst) -> Intraday: ...                # 含 trade_date、pre_close
    def quotes(self, insts: list) -> list[Quote]: ...        # 批量快照
    def valuation(self, inst) -> Valuation | None: ...
    def financial_reports(self, inst) -> list[ReportRow]: ...  # 长表
    def index_overview(self, market) -> list[IndexQuote]: ...
    def market_breadth(self, market) -> Breadth | None: ...
```
不支持的能力抛 `NotSupported`；`composite.py` 据此跳到回退链的下一个源。所有返回值都带 `source`、`currency`、`as_of`。

**路由表（全部免费，已有代码的标 ✔）**

| 能力 | A 股（沪深北） | 美股 | 韩股 |
|---|---|---|---|
| 日线 | 同花顺 ✔ → 东方财富 K 线（指数用的客户端已有，扩到个股）→ Yahoo ✔ | Yahoo ✔ → Stooq ✔ | Yahoo ✔ |
| 分时 | 同花顺 ✔ → 东方财富（同上） | Yahoo 5 分钟线 ✔ | Yahoo ✔ |
| 批量快照 | 东方财富 `ulist.np` ✔（每批最多 43 只） | 由分时/日线派生 | 同左 |
| 估值 / 财报 | 同花顺 F10 ✔ | Yahoo ✔ | Yahoo ✔ |
| 指数 | 同花顺 ✔ → 东方财富 ✔ | Yahoo ✔ | Yahoo ✔ |
| 涨跌家数 | 东方财富 `clist` ✔ → 本地股票池统计 ✔ | yfinance screener ✔ | 无 |
| 汇率 | — | — | Yahoo `KRW=X` ✔ |

**2026-11-11 实测结论（执行时请以此为准）**

1. **北交所可以用免费源**。用 920190 实测：东方财富 K 线、东方财富分时、同花顺日线（`/v6/line/hs_920190/01/2026.js`）、同花顺分时都返回了有效数据。现有代码里"北交所必须配置 iFinD"的限制（`data_fetcher.py:445-451`）直接去掉，北交所走和沪深相同的路由。东方财富的 secid 规则：上海为 `1.代码`，深圳和北京为 `0.代码`（`market_snapshot.py:163`）。
2. **成交量单位不一致**：同一天同一只股票，东方财富返回 15037（单位是"手"），同花顺返回 1503733（单位是"股"）。**库里统一存"股"**，东方财富的 A 股成交量入库前乘以 100。
3. **现有日线都是前复权价**：同花顺 URL 中的 `01`、东方财富的 `fqt=1`、yfinance `history()` 的默认 `auto_adjust=True` 都是复权口径。这直接影响增量缓存的设计，见 §5.2。P1 需用一只近期除权除息的股票核实这一点，并把结论写进代码注释。
4. 同花顺日线的"当天那一根"在盘中和刚收盘时会滞后或不完整（实测收盘后 920190 当天收盘价与东方财富不一致）。所以当天的 K 线**一律由分时合成**，不信任日线接口的当天行，见 §5.2。
5. 同花顺不复权接口（`/00/`）的当天行是残缺的，不要使用。
6. **（P0 录样本时补测）Stooq 已不可直接取数**：`/q/d/l/` 返回 JS 工作量证明式的人机校验页，而不是 CSV。不绕过校验，Stooq 回退在 P1 视为不可用：美股日线回退链暂时只有 Yahoo，`providers/stooq.py` 保留接口但默认关闭，响应里出现校验页时归类为 `provider_blocked`。
7. **（P0 补测）东方财富 push2 / push2his 在 HTTP/2 下会 TLS 握手失败**（curl 35），改用 HTTP/1.1 + `Connection: close` 可用（与旧 `market_snapshot.py` 的做法一致），`providers/http.py` 对东方财富统一这样设置。短时间连续请求约二十次后，本机 IP 被临时拒绝连接（curl 56，日线、分时都受影响），限速和退避必须真的生效。东方财富分时的金样本因此没录成，P1 补录（`python -m backend.scripts.record_fixtures em_trends_300308`）。
8. **（P1 核实）复权口径**：用 600519 对比同花顺 `/01/` 与 `/00/`，两者之比在每个除息日跳变、最近一次除息后恰为 1.0，确认 `/01/` 是前复权；它是"减分红"的加法式调整，Yahoo 的 `adjclose` 则是按比例调整（AAPL 实测），两者在除息日前的历史有细小差异。§5.2 的重叠校验因此也承担"换源即全量重抓"的作用，库里同一只股票不会混用两种口径。另：收盘 30 分钟后同花顺日线的当天行与分时一致，且成交额与东方财富结算值相同（分时合计偏高约 1.4%、分钟最高价偏低），所以 §5.2 第 5 步"结算后入库日线行"是对的。

**其它规则**
- 每个源有独立的限速（默认最少间隔 0.3 秒）和超时（20 秒）；连续失败后按 30 秒 → 2 分钟 → 10 分钟退避，由 `fetch_log` 判断。
- 演示数据（`_generate_demo_data`）只在显式设置 `DEMO_MODE=1` 时启用，**绝不静默回退**。
- 不引入 AKShare。
- 汇率换算在服务端做：请求带 `currency=USD` 时，后端用当前参考汇率统一换算价格、成交额、市值、财报金额，并在返回里注明汇率（与现有行为一致：全区间按同一个当前汇率换算）。删除 `app.py:442-462` 的"猜测分时是否已是美元"的启发式。

### 4.2 缓存与新鲜度

取代 `st.cache_data` 的是"读穿式缓存"：service 先查库里上次抓取时间，没过期就直接返回库里的数据；过期才调 Provider，成功后落库。

| 资源 | 存放 | 过期时间（沿用现值） |
|---|---|---|
| 日线 | `daily_bars` 表 | 见 §5.2 |
| 分时、批量快照 | `payload_cache` | 25 秒 |
| A 股指数概览 | `payload_cache` | 30 秒 |
| 美股/韩股指数概览、新闻 | `payload_cache` / `news_items` | 10 分钟 |
| 估值、美股市值 | `payload_cache` | 5 分钟 |
| 汇率、交易日历 | `payload_cache` | 1 小时 |
| 财报、同业对比、季度净利润排行 | `financial_reports` 表 | 12 小时 |

- **抓取失败时返回旧数据**：只要库里有上一次成功的结果，就返回它，并把 `freshness` 标成 `cached`，同时附上错误信息。
- 同一个（资源，键）同时只允许一个线程去抓上游（进程内的锁字典），其它请求等它的结果，避免重复请求把数据源打爆。
- 每个响应的 `meta` 字段统一为：`{source, as_of, fetched_at, freshness, currency, note}`。`freshness` 取值：

| 值 | 含义 | 前端徽标 |
|---|---|---|
| `live` | 交易时段内的最新数据 | 实时 |
| `closed` | 非交易时段的最新数据 | 已收盘 |
| `provisional` | 含分时合成的当天 K 线 | 盘中合成 |
| `fallback` | 主源失败，来自回退源 | 备用源：XX |
| `cached` | 上游失败，来自本地旧数据 | 缓存（时间） |
| `demo` | 演示数据 | 演示数据，勿用于决策 |

### 4.3 API

路径里的标的写成 `{market}/{symbol}`，如 `/api/instruments/CN/300308.SZ/bars`（`^GSPC`、`BRK-B` 这类符号按 URL 编码）。

| 方法 & 路径 | 用途 | 说明 |
|---|---|---|
| `GET /api/instruments/search?q=` | 统一搜索 | 先在本地 `instruments` 表按名称/代码模糊匹配；匹配不到时按代码规则解析（`300308`、`300308.SZ`、`SZ300308`、`AAPL`、`005930.KS`，规则移植自 `normalize_ticker`），返回一个"未验证"候选。**不做远程名称搜索** |
| `GET /api/universe` | 股票池分组 | 取代 `a_share_universe.py` |
| `GET /api/instruments/{m}/{s}` | 标的信息 | 首次成功取数后自动建档，名称用数据源返回的名称更新 |
| `GET .../bars` | 日线 + 指标 | 参数 `start,end,ma=5,10,20,bbi,boll,rsi=14,macd,currency`；返回 `bars[]`、`indicators{}`、`meta`。指标**在服务端算**，预热区间由后端自动多取（规则同 `indicator_warmup_start`），只返回显示区间 |
| `GET .../bars.csv` | 导出 CSV | |
| `GET .../intraday` | 当日分时 | `points[]`（时间、价格、均价、量、额）、`pre_close`、`trade_date` |
| `GET .../snapshot` | 报价头与属性条 | 当前价、涨跌额/幅、**区间**最高/最低（按请求的 start/end）、**52 周**最高/最低（固定取近一年，修 B1）、区间均量、区间单日最大成交额及日期、年化波动率、市值、PE 三项、TTM 净利润、新股状态 |
| `GET .../financials` | 财报 | 长表；近 4 个财年 + 近 4 个季度 |
| `GET .../peers` | 同赛道对比 | 仅股票池内的 A 股 |
| `GET .../signals` | 技术信号摘要 | 见下方"信号改写规则" |
| `GET/POST/DELETE /api/watchlist/items` | 自选增删 | v1 只有一个默认自选列表、只支持 A 股（与现状一致） |
| `GET /api/watchlist/quotes` | 自选行情 + 汇总 | 见 §8 |
| `GET /api/rankings?metric=` | 股票池排行 | `change_pct / amount / market_cap / pe_ttm / quarter_profit`；一次返回整池（约 45 行），排序在前端做 |
| `GET /api/market/{market}/overview` | 指数卡片 + 涨跌家数 | |
| `GET /api/market/{market}/indices/{symbol}/intraday` | 指数分时 | |
| `GET /api/market/sessions` | 各市场是否在交易时段 | 前端据此决定是否轮询 |
| `GET /api/news?hours=72` | 新闻 | 含各来源状态 |
| `GET/PUT /api/prefs` | 用户偏好 | 主题、默认指标、自选列配置与排序 |
| `POST /api/refresh` | 手动刷新 | body 指定目标（某只股票 / 自选 / 排行 / 某市场概览 / 新闻），**只让该目标的缓存过期**（修 §2.7） |
| `GET /api/health` | 数据源状态 | 每个源最近一次成功/失败时间与错误 |

错误响应统一为 `{"error": {"category", "message", "detail"}}`，`message` 全部中文（修 B8）。

**信号改写规则（B3）**
- 标题改为"技术信号摘要"，并注明"基于固定规则，不构成投资建议"。
- 保留六条信号：价格相对 20 日均线、RSI、MACD、波动率、资产负债率对比赛道均值、资本开支对比赛道中位数。
- 措辞改为描述性："RSI 高于 70（超买区间）"，不再出现"买入信号 / 卖出信号 / 建仓 / 减仓"。
- 删除"综合评分"和"综合建议"。
- 顺带修一个口径问题：现在"价格趋势"用的是 `df['Close'].iloc[-20:].mean()`，在显示区间不足 20 根时并不是 20 日均线；改为用含预热区间的完整序列算 MA20。

### 4.4 实时刷新：用轮询，不做推送

单用户本机应用，轮询足够，也简单得多：
- 前端用 TanStack Query 的 `refetchInterval: 30_000`，**仅当**该市场处于交易时段（`/api/market/sessions`）且页面可见时启用。
- 后端不需要调度器：轮询请求打到读穿式缓存上，25 秒内的重复请求不会触发上游抓取。
- 交易时段判断沿用现有规则（工作日 + 固定时段，不含节假日）。节假日时上游数据不变，页面会显示"已收盘"加上一个交易日的日期，可接受。

---

## 5. 数据库

### 5.1 表结构（以此为准，取代诊断报告 §4.2 的草图）

```sql
instruments(
  id TEXT PRIMARY KEY,            -- "CN:300308.SZ" / "US:AAPL" / "KR:005930.KS"
  market TEXT, symbol TEXT, name TEXT, currency TEXT,
  created_at, name_updated_at)

universe_groups(id INTEGER PK, name TEXT UNIQUE, sort_order)
universe_members(group_id, instrument_id, sort_order, PRIMARY KEY(group_id, instrument_id))

daily_bars(
  instrument_id, trade_date DATE,
  open, high, low, close,
  volume REAL,                    -- 单位：股
  amount REAL, amount_estimated BOOLEAN,   -- 源未提供时用 close × volume 估算
  source TEXT, fetched_at,
  PRIMARY KEY(instrument_id, trade_date))

bars_meta(
  instrument_id PRIMARY KEY,
  adj TEXT,                       -- 目前恒为 "qfq"（前复权）
  covered_start DATE, covered_end DATE,   -- 已向上游确认过的日期范围
  last_checked_at, last_full_refresh_at, source)

financial_reports(
  instrument_id, period_end DATE, report_type TEXT,   -- annual / q1 / h1 / q3 / quarterly
  metric TEXT, value REAL, currency TEXT, source TEXT, fetched_at,
  PRIMARY KEY(instrument_id, period_end, report_type, metric))

payload_cache(
  resource TEXT, key TEXT, payload_json TEXT, source TEXT, fetched_at,
  PRIMARY KEY(resource, key))     -- 分时、快照、估值、指数概览、涨跌家数、汇率等"只留最新一份"的数据

news_items(id TEXT PRIMARY KEY, source, title, url, published_at, observed_at)

watchlists(id INTEGER PK, name, sort_order)           -- v1 只有一行"默认"
watchlist_items(watchlist_id, instrument_id, added_at, sort_order,
                PRIMARY KEY(watchlist_id, instrument_id))

user_prefs(key TEXT PRIMARY KEY, value_json TEXT)

fetch_log(id INTEGER PK, provider, resource, key, started_at, duration_ms,
          status, error_category, error_message)      -- 只追加；保留 30 天
```

财报 `metric` 用英文代码，中文标签在前端映射：

| metric | 同花顺字段 | Yahoo 字段 |
|---|---|---|
| `revenue` | 营业总收入 | TotalRevenue |
| `revenue_yoy` | 营业总收入同比增长率 | — |
| `net_profit` | 净利润 | NetIncome |
| `net_profit_yoy` | 净利润同比增长率 | — |
| `net_profit_excl` | 扣非净利润 | — |
| `gross_margin` | 销售毛利率 | — |
| `gross_profit` | — | GrossProfit |
| `operating_income` | — | OperatingIncome |
| `eps_basic` | 基本每股收益 | BasicEPS |
| `ocf_per_share` | 每股经营现金流 | — |
| `roe` | 净资产收益率 | — |
| `debt_ratio` | 资产负债率 | — |
| `capex` | 购建固定资产等支付的现金（`_cash.json`） | — |

同花顺的金额是带"亿/万"的字符串，入库前统一换成"元"的数值（移植 `_financial_amount_to_yuan`）；A 股季报是累计口径，`report_type` 用 `q1/h1/q3` 表达，不做单季拆分。

### 5.2 日线增量算法（本方案最容易出错的部分）

对某只股票请求区间 `[start, end]`（已含指标预热）：

1. **取锁**：按 `instrument_id` 加进程内锁。
2. **头部缺口**：若 `bars_meta` 不存在，或 `start < covered_start`，向上游请求缺失的那一段并入库，然后把 `covered_start` 更新为 `start`——**即使上游在那一段没有返回任何数据**（说明还没上市），这样不会每次都重复请求。
3. **尾部刷新**：若 `covered_end` 早于"最近一个已收盘的交易日"，且距 `last_checked_at` 超过 5 分钟，则向上游请求 `[covered_end − 10 个自然日, 今天]`。
4. **复权一致性检查**：把新取回的数据与库中**重叠日期**的收盘价比较。只要有一天相对偏差超过 0.1%，就说明发生了除权除息、历史前复权价已整体变化 → 在一个事务里**删除该股票全部日线，按 `[covered_start, 今天]` 重新抓取**，并记录 `last_full_refresh_at`。
5. **当天这一根不入库**：`trade_date` 等于该市场"今天"的行，在该市场收盘后 30 分钟之前一律丢弃。当天的 K 线由分时合成后叠加在返回结果上（移植 `_intraday_daily_bar` / `merge_intraday_daily_bar`），并把 `freshness` 标为 `provisional`。
6. **上游失败**：库里有数据就返回库里的（`freshness=cached`）；库里没有才报错。
7. 同花顺只能按年取数，所以对同花顺而言缺口的粒度是"年"，取回后只入库需要的日期即可。

验收用例（P1 必须有对应的单元测试，用假 Provider）：
- 第二次请求同一区间，上游调用次数为 0。
- 把区间从 3 个月扩到 1 年，只请求早的那 9 个月。
- 先请求 1 年再请求 3 个月，库里的 1 年数据仍在（对应诊断报告 §4.1 的覆盖问题）。
- 重叠日期收盘价变化 5% → 触发全量重抓，库里不存在新旧口径混合的数据。
- 未上市区间不会重复请求。
- 盘中请求不会把当天的行写进库。

### 5.3 旧数据迁移

`scripts/migrate_legacy_cache.py`，可重复执行，**只读不删**（README 的缓存保留政策）：

| 旧文件 | 处理 |
|---|---|
| `data/cache/{TICKER}.csv` | 导入 `daily_bars`；文件名规则 `300308_SZ.csv` → `CN:300308.SZ`、`005930_KS.csv` → `KR:005930.KS`、其余 → `US:`；`covered_start/end` 取文件里的首尾日期；`source` 记为 `legacy-cache` |
| `a_share_universe.py` | 导入 `universe_groups / universe_members / instruments` |
| `app_config.py` 的美股、韩股清单 | 导入 `instruments`（"SpaceX (SPCX)"这类无法取数的条目保留，由界面按取数失败处理） |
| `watchlist.json` | 导入默认自选列表 |
| `financial_reports/*.json` | 不导入（12 小时就过期，重新抓即可） |
| `news_history.json`、快照 CSV、`watchlist-view.json`、`ifind/` | 不导入 |

数据库文件为 `data/stock_insight.db`；`.gitignore` 增加 `data/*.db*` 与 `data/cache/**`（保留 `.gitkeep`，顺带修 B6）。

---

## 6. 前端设计

### 6.1 页面与路由

```text
/                          → 跳到上次访问的页面（默认 /stock/CN/300308.SZ）
/stock/:market/:symbol     个股。查询参数：range=1m|3m|6m|1y|ytd|custom、start、end、
                           ma=5,10,20、bbi、boll、rsi=14、sub=volume|amount|rsi|macd、
                           chart=kline|intraday、cur=KRW|USD、tab=signals|financials|peers|data
/watchlist                 自选
/market/:market            市场概览（CN / US / KR）
/rankings                  A 股股票池排行。查询参数：metric、sort、dir
/news                      新闻
```

- 导航从 5 层减到 2 层：顶栏（个股 / 自选 / 市场 / 排行 / 新闻）+ 全局搜索（Ctrl+K）。
- 左侧栏（可折叠）：股票池分组、美股与韩股常用清单、自选列表，点击即跳转个股页。
- "指标说明"不再是页面：`indicator_help.py` 的文案移植成各指标名旁的 ⓘ 弹层。
- 默认日期区间是"近一年"，用 `range=1y` 表达，每次打开自动对应到今天；只有用户选了自定义日期才写入 `start/end`。这样就不需要现有的 `display_start_manual` 标记了。

### 6.2 个股页（桌面端）

```text
┌ 顶栏：Stock Insight · 个股 自选 市场 排行 新闻 ·········· [搜索 Ctrl+K] [主题] ┐
├ 侧栏 ┬ 报价头：中际旭创 300308.SZ · CPO   ¥542.00  +71.00 (+15.07%)   [☆ 自选] │
│ 股票池│          [同花顺 · 15:00 · 已收盘]                    韩股时：[₩ | $]    │
│ 美股  ├ 属性条：区间高/低 · 52周高/低 · 区间均量 · 最大成交额(日期) · 波动率 ·    │
│ 韩股  │          总市值 · PE(TTM/静/动) · TTM净利润                              │
│ 自选  ├ 工具条：[K线|分时]  [1M 3M 6M 1Y YTD 自定义]  MA▾  BBI  BOLL             │
│      │          副图[量|额|RSI|MACD]                                   [刷新]   │
│      ├ 主图（约占视口高度 55%）+ 副图                                            │
│      ├ [技术信号] [财务报表] [同业对比] [数据明细]   ← 只渲染当前页签，按需请求   │
└──────┴─────────────────────────────────────────────────────────────────────────┘
```

- 目标：1080p 屏幕上，不滚动就能看到报价头、属性条和完整主图。
- RSI、MACD 是副图的选项，不再单独占一个页签；它们的文字解读并入"技术信号"。
- 只有异常状态才出现醒目提示条：缓存数据、备用数据源、演示数据、当日成交额为分时合成。常驻的"成功加载…"横幅删除。
- 新股：K 线不足时，属性条与信号按 `new_listing` 的规则显示"数据不足"；首日也要能看到 K 线。
- 各区块各自处理加载中、空数据、出错三种状态；某一块失败不影响其它块。

### 6.3 自选、排行、市场、新闻

- **自选**：顶部一行汇总（总数、等权涨跌幅、涨/跌/平、有效样本、领涨、领跌、相对沪深 300），下面是数据表。添加框支持多种代码写法；删除后出现"撤销"提示条。
- **排行**：一个表格 + 指标切换；点表头排序；无效 PE 永远排在最后。
- **市场**：指数卡片网格、涨跌家数比例条、指数分时（可选指数）。
- **新闻**：列表，来源标签 + 时间 + 外链；底部显示各来源状态。

### 6.4 通用组件

`QuoteHeader`、`AttributeBar`、`DataStatusBadge`、`ChangeText`（按市场惯例着色）、`KlineChart`、`IntradayChart`、`BarChart`、`DataTable`（排序、行点击、虚拟滚动、列显隐、迷你走势列）、`SearchCommand`、`RangePicker`、`InfoTip`、`EmptyState`、`ErrorState`（含可展开的技术详情）、`UndoToast`、`BreadthBar`、`IndexCard`。

### 6.5 设计规范

- **气质**：专业行情终端——信息密度高、对齐严格、装饰少。不要大号 Hero 标题、渐变卡片、每个数字一张卡。
- **tokens**（`theme/tokens.css`，暗/亮两套只换变量值）：背景 3 级、文字 3 级、边框 2 级、强调色 1 个（沿用现有青色 `#22d3ee`）、语义色（涨、跌、警告、错误）。沿用现有主色：暗色背景 `#070b14`、亮色背景 `#f4f6f8`。
- **涨跌色**：`--color-up / --color-down`。A 股和韩股红涨绿跌（`#e53935` / `#1e9d55`），美股绿涨红跌；由标的所属市场决定，通过根节点的 `data-market` 属性切换。
- **字体**：系统字体栈，不加载外部字体（本机离线也要正常）。所有数字用等宽数字（`tabular-nums`），表格数字右对齐。
- **字号**：正文 13–14px；报价头的价格 28–32px，是页面上唯一的大字；属性条 12px 标签 + 14px 数值。
- **间距**：4px 基准栅格；表格行高 32–36px。
- **数字格式**集中在 `lib/format.ts`，规则与 `formatters.py` 一致：A 股与韩股用"万 / 亿 / 万亿"，美股用 K / M / B / T；空值显示"—"。用同一组用例在前后端各测一遍。
- **响应式**：≥1280px 侧栏常驻；768–1279px 侧栏变抽屉；<768px 单列，报价头吸顶，属性条横向滚动，表格固定首列。
- **主题**：默认跟随系统，可手动切换并存入偏好；为避免首屏闪烁，在 `index.html` 里用一小段内联脚本先读 localStorage 设置主题。
- **可访问性**：涨跌不只靠颜色区分（同时有 +/− 号）；交互元素都能用键盘操作；图表有文字摘要。

### 6.6 状态与偏好

- 页面状态都在 URL 里。
- 偏好存后端 `/api/prefs`：主题、默认均线与指标、副图类型、自选列与排序、侧栏是否折叠、上次访问的页面。localStorage 只缓存主题，用来防止首屏闪烁。
- 不再保存滚动位置和页签状态（页签已经在 URL 里）。

---

## 7. 实施阶段

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| **P0 准备** | 从 `main` 建分支 `feat/spa`；搭 `backend/`、`frontend/` 骨架；修 B2（让现有 32 个测试全绿，作为基线）；**录制金样本**：对同花顺日线/分时/F10 估值/财报/现金流、东方财富快照/K 线/分时/涨跌家数、Yahoo 日线/分时/财报、Stooq 各录一份真实响应存入 `backend/tests/fixtures/` | 旧测试 32/32 通过；`uvicorn` 与 `npm run dev` 都能启动；`/api/health` 返回 200 |
| **P1 数据层** | 数据库模型与迁移；`providers/`（从旧代码移植四个源，解析逻辑用金样本测试）；东方财富个股 K 线与分时；去掉北交所限制；§5.2 增量算法；§5.3 迁移脚本；复权口径核实 | §5.2 的 6 个验收用例通过；迁移脚本跑完后库里的行数与旧 CSV 一致；920190 能取到日线和分时；关掉同花顺后 A 股日线仍可用（来源显示东方财富，成交量量级一致） |
| **P2 领域与 API** | `domain/` 纯函数及单测；§4.2 读穿式缓存；§4.3 全部接口；`/api/health` | OpenAPI 文档完整；旧测试中的业务规则用例全部移植并通过（见下）；断网时已缓存的股票仍能返回数据且标 `cached` |
| **▶ 检查点 A** | 请用户在 Swagger UI（`/docs`）里看几只股票的数据 | 用户确认后再继续 |
| **P3 前端骨架与样张** | tokens、顶栏、侧栏、搜索、`DataTable`、`DataStatusBadge`、API 类型生成；个股页用**真实接口**做到"报价头 + 属性条 + K 线 + 分时"可用；图表库验证（双轴、午休、新股） | 暗/亮主题切换无闪烁；搜索能解析 §4.3 列出的所有代码写法；1080p 下个股页首屏完整显示主图 |
| **▶ 检查点 B** | 请用户看样张，确认视觉方向和信息布局 | 用户确认后再继续；这是改视觉方向成本最低的时点 |
| **P4 个股页完成** | 指标与副图、技术信号、财报、同业对比、数据明细与 CSV、币种切换、新股状态、各种异常提示 | §8"个股"全部勾上；B1、B3 已修 |
| **P5 其余页面** | 自选、排行、市场、新闻；交易时段轮询 | §8 全部勾上；交易时段内数据每 30 秒更新，非交易时段不发请求 |
| **P6 收尾** | 新 `start.bat`；Dockerfile；Playwright 冒烟用例（每个页面能打开、能搜索并打开一只股票、能加删自选）；更新 README；删除根目录旧 Streamlit 代码、`assets/`、`.streamlit/`、旧启动器、`THS_ACCESS_TOKEN` 相关逻辑 | 全新克隆后双击 `start.bat` 即可使用；`docker build` 成功；全部测试通过 |

**旧测试的去向**
- `test_data_fetcher.py`、`test_market_data.py`、`test_news_fetcher.py` → 移植到 `backend/tests/`，对象换成新模块。
- `test_business_rules.py` 中的纯规则（代码规范化、自选汇总、排行排序、新股状态、格式化）→ 移植；其中依赖 Streamlit `AppTest` 的界面流程用例 → 改写为 API 测试或 Playwright 用例。
- `test_visualization.py`（Plotly 图表）→ 不移植；图表行为由 P3 的验证和 Playwright 截图覆盖。

**`start.bat` 的行为**：确保 `.venv` 存在并安装 `backend/requirements.txt` → 若 `frontend/dist` 不存在则执行 `npm ci && npm run build`（没装 Node 时给出明确提示）→ 首次运行执行数据库迁移与旧缓存导入 → 启动 uvicorn（`127.0.0.1:8000`）→ 打开浏览器。**不再执行 `git switch`**。

---

## 8. 功能对照清单（验收依据）

**个股**
- [ ] 美股、A 股（沪深北）、韩股日线，回退链按 §4.1
- [ ] 任意代码输入：A 股多种写法、美股任意代码、韩股 `.KS/.KQ`（侧栏仍只列现有的 5 只韩股）
- [ ] K 线 + MA（5/10/20/30/50/60/120 多选）+ BBI + BOLL；左边缘的指标值正确（有预热）
- [ ] 副图：成交量 / 成交额 / RSI（周期 7–21）/ MACD
- [ ] 无周末与停牌空档；新股首日 K 线可见
- [ ] 分时：价格、均价、昨收线、涨跌幅刻度、量/额副图；A 股午休不留空档
- [ ] 当天 K 线由分时合成，并提示"当日成交额由分时合成，可能与结算值略有偏差"
- [ ] 韩股韩元/美元切换：价格、图表、市值、财报金额与每股收益都换算，并显示参考汇率
- [ ] 报价头与属性条：按 §4.3 `snapshot` 的全部字段
- [ ] A 股估值：PE TTM / 静态 / 动态（亏损显示"亏损 / 不适用"）、TTM 净利润、来源与时间
- [ ] 技术信号摘要（§4.3 改写规则）
- [ ] 同业对比：营收与净利润 / 净利率 / 资产负债率三种图 + 明细表；非股票池 A 股及美股、韩股显示"暂不支持"
- [ ] 财报：近 4 个财年 + 近 4 个季度的表格；A 股有年报图和季度图（季度图用年报补齐第四季度）；注明季报为累计口径
- [ ] 数据明细表（最近 N 行）+ 统计摘要 + CSV 导出
- [ ] 加入 / 移出自选
- [ ] 数据源失败时：显示错误类别与可展开的技术详情；有缓存则显示缓存并标注

**自选（A 股）**
- [ ] 添加（多种代码写法、重复检测、格式错误提示）、移除、撤销移除
- [ ] 汇总：总数、等权平均涨跌幅、涨/跌/平、有效样本数、领涨、领跌、相对沪深 300；缓存与无效行情不计入统计
- [ ] 表格列：名称/代码、最新价、涨跌幅、涨跌额、成交额、行情时间、状态（最新 / 缓存 / 旧日期 / 缺失）
- [ ] 可选列：开、高、低、振幅、换手率（东方财富快照字段）、5 日 / 20 日涨幅（用库里日线算）、分时迷你走势、停牌标记
- [ ] 搜索、排序（加入顺序 / 涨幅 / 跌幅 / 价格 / 成交额 + 点表头）
- [ ] 点击进入个股；返回时搜索词与排序还在
- [ ] 标题随日期变化："当日表现"或"最近交易日 · 日期"

**排行（A 股股票池）**
- [ ] 涨幅、成交额、总市值、PE TTM、最新季度净利润及同比
- [ ] 点表头升降序；无效 PE 排最后；显示数据时间与"缓存"状态
- [ ] 点击进入个股

**市场**
- [ ] A 股 5 个指数、美股 4 个、KOSPI：点位、涨跌、成交额及较上一交易日变化（A 股）、成分股涨跌数（A 股）、日期与来源
- [ ] 涨跌家数与比例条（A 股全市场、美股）；回退到本地股票池统计时明确标注"非全市场"
- [ ] 指数分时：可选指数；美股与韩股只显示最近一个交易日
- [ ] 单个指数失败只影响它自己的卡片

**新闻**
- [ ] Yahoo + 同花顺 + 抖音热点，近 72 小时，去重，按时间排序，外链；显示各来源状态

**全局**
- [ ] 暗/亮主题；涨跌色按市场惯例
- [ ] 每块数据都有状态徽标（§4.2）
- [ ] 指标说明弹层
- [ ] 交易时段自动刷新 + 手动刷新（只刷新当前目标）

---

## 9. 风险与应对

| 风险 | 应对 |
|---|---|
| 免费接口变更、限流或封 IP | Provider 隔离；每种能力至少两个源；限速与退避；库里旧数据兜底；`/api/health` 可见 |
| 移植 `data_fetcher.py`（1301 行）时解析行为走样 | P0 先录金样本，新旧解析器对同一份样本输出一致才算通过 |
| 前复权数据增量存储导致新旧口径混合 | §5.2 第 4 步的重叠检查 + 全量重抓；有专门的测试 |
| 不同源的单位、口径不一致（手/股、当天行不完整） | §4.1 的实测结论写进 Provider 的单测 |
| lightweight-charts 满足不了某项图表需求 | P3 先验证；不行就 K 线与分时改用 ECharts |
| 视觉方向做完才发现不合意 | 检查点 B 在只完成样张时就让用户确认 |
| 公开接口的使用条款 | 仅个人本机、低频使用；不批量抓取、不转售 |

---

## 10. 执行守则（给执行方）

1. 在 `feat/spa` 分支上工作。**不要推送、不要删除任何分支、不要改动 `main`**，除非用户明确要求。`archive/ifind` 是归档分支，不要在上面提交。
2. **永远不要删除或清空 `data/cache/`**（README 的缓存保留政策）。
3. 每个阶段结束时提交一次，提交信息写明阶段号；阶段验收标准没全过就不要进入下一阶段，如实说明哪条没过。
4. 在检查点 A、B 停下来等用户确认。
5. 需要联网的测试单独标记（如 `@pytest.mark.network`），默认测试套件不联网，用金样本。
6. P6 之前不修改、不移动根目录的旧 Streamlit 文件（P0 修 B2 的那个测试除外）。
7. 实现中发现本文与实际情况不符（例如某接口字段变了），以实际为准并在提交信息或文档里记一笔，不要硬套方案。
8. 所有面向用户的文案用中文。

---

## 11. 默认决定与待确认事项

**已按默认决定（执行方直接照做；用户不同意可随时改）**

| 问题 | 默认决定 |
|---|---|
| 前端框架与组件 | React + TypeScript；Tailwind + shadcn/ui；lightweight-charts + ECharts |
| 指标在哪算 | 服务端 |
| 复权 | 只提供前复权（与现状一致），不做切换 |
| 实时方式 | 30 秒轮询，不做推送 |
| 自选 | 单个列表、仅 A 股、无持仓；表结构预留多列表 |
| 韩股 / 美股代码 | 搜索框接受任意合法代码；侧栏清单不变 |
| 节假日日历 | 不做 |
| 涨跌配色 | 跟随市场惯例，不做全局开关 |
| AKShare | 不引入 |
| 行情历史回放 | 不做；快照只保留最新一份 |
| `THS_ACCESS_TOKEN` 相关代码 | P6 随旧代码一并删除 |

**需要用户确认的三件事**（都不阻塞 P0–P2）
1. **检查点 A、B 的确认**（流程内）。
2. **P6 是否真的删除旧 Streamlit 代码**——删除后只能从 git 历史找回。
3. **分支收尾**：新版完成后 `feat/spa` 如何合入 `main`（直接合并还是走 PR）；`public-data` 分支是否还需要保留。
