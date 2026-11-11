# Stock Insight 前端升级 · 现状诊断与改造概要

> 审阅范围：`public-data` 分支（原名 `codex/public-data`，HEAD `a913fd6`），约 10k 行（Python 7.1k / CSS 1.9k / JS 84）。
> 目的：记录现状与问题，作为实施方案的依据。所有结论都附了文件位置，便于核对。
> **状态（2026-11-11 复核）**：方向已定为 B（FastAPI + SPA）、只用免费数据源、短期只在本机运行。实施以 [plan-b-draft.md](plan-b-draft.md) 为准；本文 §4.2 的表结构草图、§4.3 与 §5 的路线已被该文档取代，保留仅供了解来龙去脉。

---

## 0. 一句话结论

功能已经很全，但**整个前端是一个 943 行、自上而下执行的 Streamlit 脚本**，靠 `st.stop()` 路由、靠 50+ 个拼字符串的 `session_state` key 管状态、靠 204 处 `!important` + Streamlit 内部 `data-testid` 选择器做皮肤。继续堆功能的边际成本已经很高。
"数据库"其实不存在：持久化是 `data/cache/` 下的一堆 CSV/JSON，**而且日线缓存每次被整文件覆盖，与 README 声称的"保留历史、增量补齐"不符**。
结论：**先做数据层（SQLite + Provider 接口），再用 FastAPI + SPA 重建界面**（已定，见实施方案）。

---

## 1. 项目结构速览

| 层 | 文件 | 说明 |
|---|---|---|
| 入口/路由/页面 | `app.py`(943) | 顶部导航、个股页全部逻辑、6 个 Tab、指标计算、刷新逻辑全在这里 |
| 侧栏 | `sidebar.py`, `watchlist.py`(344) | 股票选择、日期、指标参数；自选股的增删、总览表格也在 watchlist |
| 其它页面 | `market_overviews.py`(453), `indicator_help.py`, `investment_insights_view.py`, `financial_reports_view.py` | 市场总览、股票池排行、新闻、指标说明、投资洞察、财报 |
| 图表 | `visualization.py`(845) | Plotly：K 线、分时、指数分时、RSI、MACD、财报柱图 |
| 样式 | `assets/dashboard.css`(1007), `light.css`(529), `market_overview.css`(357), `styles.py` | 暗色为基础，浅色时额外注入 light.css 覆盖 |
| 浏览器记忆 | `browser_state.py` + `assets/browser_state.js` | localStorage 存 UI 偏好、Tab、滚动位置 |
| 数据获取 | `data_fetcher.py`(1301), `market_snapshot.py`(585), `news_fetcher.py`(918), `services/*.py`, `financial_rankings.py` | 同花顺/Yahoo/Stooq/东方财富/抖音；`st.cache_data` + 文件缓存 |
| 配置/股票池 | `app_config.py`, `a_share_universe.py` | 股票池写死在 Python dict 里 |
| 测试 | `tests/`(5 个模块, 32 用例) | **当前 1 个失败**（见 §2.8） |

两个版本分支 `codex/public-data` 与 `codex/ifind`（2026-11-11 已改名为 `public-data` 与 `archive/ifind`） 在 24 个文件上相差 **+1640/−766 行**（`watchlist.py` 差 526 行，ifind 多了 `ifind_data.py`、`services/watchlist_data.py`）。后已决定不使用 iFinD：iFinD 版归档为 `archive/ifind`（标签 `ifind-archive-2026-11-11`），`main` 改为指向 public 版。

---

## 2. 前端：逻辑层问题

### 2.1 单脚本 + 全局变量闭包，依赖顺序脆弱
- `app.py` 是模块级顺序执行代码。`compute_snapshot_metrics()`（`app.py:404`）读取全局的 `df / market / ticker / krw_usd_rate / display_market`；`render_intraday_panel()`（`app.py:231`）引用 `snapshot_placeholder`，而它在 `app.py:696` 才定义——只是"恰好调用时已存在"。
- 价格 Tab 的"立即刷新"（`app.py:754-781`）会**重新给全局 `df`、`indicator_history_df`、`df_macd`、`snapshot_metrics` 赋值**，后面的 Tab 才读到新值。任何调整 Tab 顺序的改动都会悄悄出错。

### 2.2 路由靠 `st.stop()`，状态靠"自赋值续命"
- 页面路由：`segmented_control` + 一串 `if page == ...: render(); st.stop()`（`app.py:152-179`）。没有 URL 路由，无法分享/收藏某只股票的链接，浏览器后退无效。
- `app.py:76-83` 和 `browser_state.py:73-75` 用 `st.session_state[k] = st.session_state[k]` 防止条件控件的状态被 Streamlit 回收——典型的框架对抗代码。
- 状态 key 大量字符串拼接：`intraday:{market}:{ticker}`、`intraday-price-stale:...`、`intraday-refreshed-at:...`、`price-page-refreshed-at:{ticker}`、`kr-display-currency:{ticker}`、`a-share-ranking-sort:{metric}`……没有集中定义，也从不清理（换过 100 只股票就有几百个 key 残留在会话里）。

### 2.3 首屏多跑一轮 + 骨架屏补丁
- `sync_browser_state()`（`browser_state.py:60`）首次加载必须 `st.stop()` 等 JS 回传 localStorage，再 `st.rerun()`。于是又加了 `render_boot_skeleton()` 来遮盖空白屏（`app.py:69`、`styles.py:47`）。这是"Streamlit 没有同步读客户端存储"导致的连锁补丁。

### 2.4 每次重跑都 `importlib.reload` 模块
- `app.py:51-53`、`market_overviews.py:20-21` 每次 rerun 都 reload `a_share_universe / visualization / market_overviews / market_overview_data`。这是开发期热更新的 hack，生产中浪费时间，并让 `@st.fragment(run_every=...)` 的装饰器参数在 reload 时才被重新求值（`market_overviews.py:386`）——**一旦去掉 reload，排行页的自动刷新开关会定格在进程启动那一刻的交易时段状态**。

### 2.5 所有 Tab 都在每次重跑时完整计算
- `st.tabs` 是"全部渲染、前端切换"。个股页 6 个 Tab：即使用户只看 K 线，**投资洞察 Tab 也会对整个同赛道调用 `fetch_peer_comparison`，财报 Tab 也会拉财报**（`app.py:922-935`）。
- 股票池排行：4 个排行榜 Tab × ~45 行 × 7 列按钮/markdown 全部渲染，外加"最新季度净利润"对整池拉财报（`market_overviews.py:408-415`），且该 fragment 每 30 秒整体重跑。
- 改造方向：只渲染当前视图（segmented_control/路由驱动），或在 SPA 中按需请求。

### 2.6 用 `st.columns` 逐行拼表格
- 自选总览（`watchlist.py:296-318`）和排行榜（`market_overviews.py:317-359`）每行都是一组 `st.columns` + `st.button`，N 行 × 8 列个 widget；每次点击股票名都触发整页 rerun。还需要内联 `<style>` 强行 `min-width / flex-grow !important` 来对齐（`watchlist.py:282-294`, `market_overviews.py:303-316`）。
- 应改为真正的数据表：`st.dataframe(on_select=...)` + `column_config`，或 SPA 中用虚拟化表格（AG Grid / TanStack Table）。

### 2.7 取数逻辑混在 UI 里，刷新逻辑重复两套
- `compute_snapshot_metrics()` 在 UI 函数内部调 `load_intraday`、`load_valuation`、`load_us_market_cap`。
- 价格页"立即刷新"和分时 Tab"立即刷新"是两套实现，都要同步更新顶部快照卡片；还有 `intraday-price-stale` 旗标防止"新日线 + 旧分时"混用。
- `load_historical_data.clear()` / `load_intraday.clear()`（`app.py:725-726`）**清的是全部股票的缓存**，不是当前这只。
- 韩元→美元换算靠启发式判断分时是否已经是美元（`app.py:450-455`，`rtol=0.12` 比较汇率），很脆弱；币种应当是数据自带的元信息，而不是猜。

### 2.8 已发现的具体缺陷
| # | 位置 | 问题 |
|---|---|---|
| B1 | `app.py:467-468, 618-620` | **"52周最高/最低"其实是所选日期区间内的最高/最低**（`df['High'].max()`）。用户把区间改成 3 个月，标签仍写 52 周。"平均成交量"同理是区间均值。 |
| B2 | `tests/test_business_rules.py:131` | 测试失败：`a913fd6` 改成"未手动选择日期时每次重置为默认值"，测试仍直接写 `display_start` 不带 `_manual` 标记。行为与测试需二选一修正。 |
| B3 | `investment_insights_view.py:21,126-131` | 标题写"AI 驱动的投资分析"，实为 4 条硬规则；并输出"可考虑适量建仓 / 建议减仓"等**买卖建议文案**，且把"波动率正常"计为看涨。建议改名为"技术信号摘要"，去掉操作建议，评分口径公开。 |
| B4 | `styles.py:94-103` | 浅色主题下 `render_dataframe` 从 `st.dataframe` 换成 `st.table`——**换个主题，表格就从可排序/可滚动变成静态表**，交互不一致。 |
| B5 | `financial_reports_view.py:19-89` | 整个函数体多缩进一级（8 空格），try 块包了 70 行；年报/季报表直接用 `st.table`，不走主题化。 |
| B6 | `.gitignore` | `data/cache/*.json` 不覆盖子目录，`data/cache/financial_reports/` 一直显示为 untracked；`watchlist-overview.jpg` 也是。 |
| B7 | `data/cache/watchlist-view.json` | ifind 分支写的文件，public 分支无代码读取——两分支共享缓存目录的副作用。 |
| B8 | 多处 | 错误文案中英混杂（`DataFetchError` 的 Yahoo 分支全英文，`app.py:390` "Technical details"）。 |
| B9 | `data_fetcher.py:445-451` | 北交所被硬性要求配置 iFinD 凭证，**其实没有必要**：2026-11-11 用 920190 实测，同花顺公开日线/分时与东方财富 K 线/分时都能返回北交所数据。 |
| B10 | `investment_insights_view.py:49` | "当前价格高于 20 日均线"用的是 `df['Close'].iloc[-20:].mean()`，而 `df` 已裁到显示区间；区间不足 20 根时算出来的不是 20 日均线。 |

---

## 3. 前端：排版/视觉问题

1. **纵向空间浪费**：每次进入个股页依次是 Hero 标题 → "工作区导航"卡 → 市场/视图两组切换 → 绿色"成功加载 XXX 从…到…"横幅（`app.py:366`）→ 快照标题 → 3 张价格卡 → 4 张次级卡 → 估值标题 → 3 张估值卡 → 才到 Tab。K 线图在 1080p 屏幕上基本在首屏以下。成功横幅不应常驻。
2. **信息层级扁平**：价格、52 周区间、成交、波动、市值、PE 全是同权重的 `st.metric` 卡片；当前价/涨跌应是绝对主角（参考行情软件的报价头），其余收进一行紧凑的属性条。
3. **导航层级不清**：一级（行情分析/市场总览/指标说明/新闻热点）+ 二级（美股/A股/韩股）+ 三级（个股分析/我的自选/股票池排行）+ 侧栏选股 + 页内 6 个 Tab，共 5 层。"指标说明"作为一级页面不合理，应变为图表旁的 tooltip/抽屉。
4. **A股与美/韩股快照区几乎是复制粘贴**（`app.py:603-692`），只差估值区和涨跌色方向——排版改一处要改两处。
5. **样式系统**：
   - 204 处 `!important`，大量依赖 `data-testid="stMetric" / stSidebar / stSegmentedControl / stSelectboxVirtualDropdown...` 等 Streamlit 内部 DOM。**Streamlit 每次升级都可能大面积失效**（`requirements.txt` 里是 `streamlit>=1.59.0`，未锁版本，风险更大）。
   - 暗/亮两套 CSS 是"覆盖式"而不是 CSS 变量（design tokens），light.css 529 行基本是在把 dashboard.css 反着写一遍。
   - Python 里还散落 85 处硬编码色值（如 `#e53935` / `#1e9d55` 在 watchlist、rankings、visualization 各写一遍），A 股红涨绿跌 vs 美股绿涨红跌的逻辑也分散在多处（`delta_color="inverse"` + `cn-price-direction` 标记 span 的 CSS hack，`app.py:606-616`）。
6. **移动端/窄屏**：表格靠 `min-width: 880px` + 横向滚动，侧栏控件占据大量空间；没有响应式布局方案。
7. **数据时效表达分散**：每个模块各自一行 caption 写"数据来源 · 截至 · 本地快照抓取于 · 每 30 秒刷新"，格式不统一。建议统一成一个"数据状态徽标"组件（来源 / 截至时间 / 是否缓存 / 是否实时）。

---

## 4. 后端与"数据库"

### 4.1 现状
没有数据库，持久化全部是 `data/cache/` 下的文件（当前共 1.3 MB）：

| 文件 | 内容 | 写入方式 | 问题 |
|---|---|---|---|
| `{TICKER}.csv` ×20 | 日线 OHLCV+Amount | `df.to_csv` **整文件覆盖**（`data_fetcher.py:227-229`），非原子写 | ① 只存本次请求区间，**选短区间会把长历史覆盖掉**，违背 README 的保留策略；② 只在抓取失败时作为兜底读取，**不是增量缓存**——A 股每次都按年把整段历史重新抓一遍（`data_fetcher.py:456-462`）；③ 无 source/复权口径/市场字段，同花顺与 Yahoo 回退的数据混写同一文件 |
| `a_share_market_snapshot.csv` | 股票池实时快照 | 原子写 + RLock | 只存最新一份，无历史 |
| `financial_reports/*.json` | 财报（宽表、中文列名） | 直接 `write_text`，非原子 | TTL/清理依赖文件 mtime；中文列名作为 schema |
| `news_history.json` | 新闻历史 | 原子写 | 单文档不断合并，无索引 |
| `watchlist.json` | 自选股 `{items:[{ticker,name}]}` | 原子写 | 无分组、无加入时间、无备注；两分支共用 |
| `watchlist-view.json`, `ifind/` | ifind 分支产物 | — | 见 B7 |
| 浏览器 localStorage | UI 偏好 | JS | 与服务端偏好重复概念 |

**2026-11-11 复核时补充的三个事实**（影响数据库设计）：
- **现有日线都是前复权价**：同花顺 URL 里的 `01`（`data_fetcher.py:328`）、东方财富的 `fqt=1`（`services/market_overview_data.py:94`）、yfinance `history()` 默认的 `auto_adjust=True`。前复权价在每次除权除息后会整体改变，所以增量存储必须检测口径变化并全量重抓（实施方案 §5.2）。
- **成交量单位不一致**：同花顺返回"股"，东方财富返回"手"（同一天 920190：1503733 对 15037）。
- **同花顺日线的当天那一行不可靠**：盘中和刚收盘时滞后或不完整，现有代码因此用分时合成当天 K 线（`services/market_data.py:63-155`），新版要保留这个做法。

另有两层缓存叠加：`st.cache_data`（进程内存，TTL 25s~6h 不等）+ 文件缓存；"缓存版本号"散落在 `VALUATION_CACHE_VERSION=5`、`MARKET_OVERVIEW_CACHE_VERSION=4`、`load_financial_reports(cache_version=2)`、`load_a_share_latest_quarter_profit_ranking(cache_version=1)`。

### 4.2 要不要上数据库？——要，但用 SQLite 就够
不是因为数据量（1.3 MB），而是为了：**增量补齐历史**、**统一元数据（来源/币种/抓取时间）**、**取代散落的 TTL 与版本号**、**让两个数据源版本共用同一套存储与 UI**。

最初的 schema 草图如下（**已被实施方案 §5.1 取代**，那里去掉了 `quote_snapshots`/`valuations`/`adj_type`，增加了 `bars_meta` 与 `payload_cache`）：

```sql
instruments(id PK, market, symbol, exchange, name, industry, currency, list_date, is_active)
universe_groups(id PK, name, sort_order)                -- 取代 a_share_universe.py
universe_members(group_id, instrument_id, sort_order)

daily_bars(instrument_id, trade_date, open, high, low, close, volume, amount,
           adj_type, source, fetched_at,
           PRIMARY KEY(instrument_id, trade_date, adj_type))
quote_snapshots(instrument_id, ts, price, prev_close, change_pct, amount,
                market_cap, pe_ttm, source)             -- 可只保留最近 N 天
valuations(instrument_id, as_of, pe_ttm, pe_static, pe_dynamic, market_cap,
           ttm_net_profit, source, fetched_at)
financial_reports(instrument_id, period_end, report_type, metric, value,
                  currency, source, fetched_at,
                  PRIMARY KEY(instrument_id, period_end, report_type, metric))  -- 长表，英文 metric 代码
news_items(id PK = hash(url), source, title, url, published_at, observed_at, tags)

watchlists(id PK, name, sort_order)
watchlist_items(watchlist_id, instrument_id, added_at, note, sort_order)
user_prefs(key PK, value_json)                          -- 服务端偏好，localStorage 只做缓存

fetch_log(provider, resource, key, fetched_at, status, error)  -- 统一 TTL / 失败退避 / 数据状态徽标
```

要点：
- 日线读取流程变为：查 `max(trade_date)` → 只向 Provider 请求缺口 → upsert。区间切换不再触发重新抓取。
- 当日分时合成日线（`services/market_data.py:63-114`）只在内存叠加，不入库，收盘后由正式日线覆盖。
- 财报改长表后，前端格式化与中英文标签放到展示层映射，不再把中文列名当 schema。
- 迁移脚本：一次性把现有 CSV/JSON 导入（README 明确要求保留缓存历史）。

### 4.3 Provider 抽象，合并两个分支

> 2026-11-11 更新：已决定**不使用 iFinD**（API 太贵），只用免费数据源；以 public 版（现 `main`）为基线，iFinD 版已归档为 `archive/ifind`、不迁移。具体见 [plan-b-draft.md](plan-b-draft.md) §4.1。
- 定义 `MarketDataProvider` 接口（`daily_bars / intraday / quotes / valuation / financial_reports / index_*`），同花顺、东方财富、Yahoo、Stooq 各一个实现，按"市场 × 能力"组合主源与回退链。
- 现有启动器会执行 `git switch` 切分支，有本地改动时直接失败；新版改为单一启动器，不再切分支。
- 顺手消除重复：`_clear_broken_local_proxy` 在 `data_fetcher.py`、`market_snapshot.py`、`news_fetcher.py` 各有一份。

---

## 5. 改造路线（最初的讨论稿；已定为 B，细节见实施方案）

### 关键决策：UI 框架
| | A. 留在 Streamlit，结构化重构 | B. FastAPI + SPA（React/Vue + TradingView lightweight-charts 或 ECharts） |
|---|---|---|
| 工作量 | 中 | 大 |
| 能解决 | 代码结构、状态集中、样式 tokens、懒渲染（用视图切换代替 tabs）、表格改 `st.dataframe` | 以上全部 + URL 路由、无整页 rerun、真正的实时推送（SSE/WebSocket）、不再依赖 Streamlit 内部 DOM、首屏无"空跑一轮"、移动端适配 |
| 解决不了 | CSS 依赖内部 DOM、rerun 模型、首屏两段加载、表格交互上限 | — |
| 复用 | 全部 | `data_fetcher`、`services`、`analysis`、`news_fetcher` 等纯 Python 层可原样复用为 API；`visualization.py` 需重写为前端图表 |

我的倾向：**用户说的是"彻底升级"，目前的痛点（§2.2/2.3/2.6/3.5）大多是 Streamlit 模型本身造成的，选 B**。但无论选哪条，阶段 1 都不浪费。

### 阶段划分
1. **阶段 1：数据层（与 UI 无关，先做）**
   SQLite + schema + 迁移脚本；Provider 接口与两个实现；增量日线；`fetch_log` 统一 TTL；股票池入库；修 B1/B2/B6。
2. **阶段 2：领域/服务层**
   把 `compute_snapshot_metrics`、指标计算、自选汇总、排行、投资信号抽成纯函数服务（输入 instrument + 参数，输出 DTO），带单测。B 路线下即为 FastAPI 路由。
3. **阶段 3：UI 重建**
   - 信息架构：一级 = 个股 / 自选 / 市场（含排行与新闻）；市场切换放进搜索框（统一代码搜索，支持 `300308`、`AAPL`、`005930.KS`）；"指标说明"降级为 tooltip。
   - 个股页布局：报价头（价格+涨跌+数据状态徽标+加自选）→ 紧凑属性条（区间高低/成交/波动/市值/PE）→ 主图（K 线 / 分时切换，指标叠加在图上配置）→ 下方按需加载的分区（技术指标、财报、同业对比、数据明细）。
   - 设计 tokens：颜色/间距/字号用 CSS 变量，暗/亮只换变量值；涨跌色由"市场惯例"一个开关控制。
   - 表格：统一一个可排序、可点击、支持虚拟滚动的数据表组件。
   - 实时：交易时段统一一个刷新调度（SSE 或 30s 轮询），各组件订阅，不再各自 `run_every`。
4. **阶段 4：合并分支、清理**
   合并两个版本分支；启动器改为参数化；锁定依赖版本；补端到端测试。

### 当时的开放问题（均已在实施方案 §11 给出决定）
1. UI 走 A 还是 B？（若 B：React 还是 Vue；是否保留 Streamlit 版作为过渡）
2. ~~是否仍需部署到 Streamlit Community Cloud？~~ → 已定：短期只本机运行，部署方案见 §6（暂缓）。
3. "投资洞察"保留到什么程度——仅技术信号摘要，还是要接入真正的 LLM 分析？
4. 自选股是否需要多分组、持仓成本/收益？（影响 `watchlist_items` 字段）
5. 是否需要保存分时/快照历史用于回放？（影响 `quote_snapshots` 保留策略与体积）

---

## 6. 部署方案（暂缓，短期不实施）

> 2026-11-11 决定：短期只在本机运行，以下仅作备忘。实施 B 方向时只需保证"单个 Docker 镜像可运行"，不为任何平台做专门适配。

**打包形态**：前端构建成静态文件，由 FastAPI 一并托管 → 一个进程、一个 Docker 镜像；本机、内网穿透、云服务器用同一个镜像。

| 方案 | 成本 | 适用 | 注意 |
|---|---|---|---|
| 本机运行（双击启动器） | 免费 | 只有自己用（**当前选择**） | — |
| 本机 + Tailscale / Cloudflare Tunnel | 免费 | 手机或外出访问自己电脑 | 电脑需开机；数据留在本地 |
| 香港轻量云服务器 | 约几十元/月 | 7×24 在线 | 国内源与 Yahoo 一般都可达；无需 ICP 备案 |
| 内地云服务器 | 约几十元/月 | 以 A 股为主 | 绑域名走 80/443 需备案；Yahoo 可能不稳 |
| Render / Railway / Fly.io 等 | 免费额度～几美元/月 | 想要 git push 自动部署 | 免费档常休眠、无持久盘；国内源可能慢或被拦 |
| 前端 Vercel/Cloudflare Pages + 后端另托管 | 前端免费 | 追求前端加载速度 | 需处理 CORS |

**约束**（选平台时必须满足）：
1. SQLite 需要持久化磁盘——不能用无服务器函数或临时文件系统。
2. 需要常驻进程——交易时段的定时刷新与 SSE 推送。
3. 数据源对 IP 敏感——Yahoo 常限制云厂商共享 IP，国内源可能不友好海外机房，上线前需实测。
4. 一旦上公网必须加登录——目前无任何鉴权，自选股等数据需保护。

**届时推荐路径**：本机 Docker → 需要外部访问时加 Tailscale → 需要常驻再上香港轻量服务器。
