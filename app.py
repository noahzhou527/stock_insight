import streamlit as st
import pandas as pd
import numpy as np
import os
import importlib
import html
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# 导入自定义模块
from data_fetcher import (
    DataFetchError,
    fetch_a_share_financial_reports,
    fetch_a_share_intraday,
    fetch_a_share_valuation,
    fetch_stock_data,
    fetch_us_market_cap,
)
import a_share_universe
from analysis import (
    calculate_bbi,
    calculate_bollinger_bands,
    calculate_ma,
    calculate_macd,
    calculate_rsi,
)
from indicator_help import render_indicator_help
from market_snapshot import (
    fetch_a_share_market_snapshot,
    flatten_a_share_universe,
    rank_snapshot,
)
from news_fetcher import fetch_recent_financial_news
from visualization import plot_candlestick, plot_intraday, plot_rsi, plot_macd

# Streamlit reruns the app in the same process, so refresh the separately
# maintained stock universe before building sidebar options.
importlib.reload(a_share_universe)
A_SHARE_UNIVERSE = a_share_universe.A_SHARE_UNIVERSE


def get_ths_access_token():
    token = os.getenv("THS_ACCESS_TOKEN")
    if token:
        return token
    try:
        return st.secrets.get("THS_ACCESS_TOKEN")
    except Exception:
        return None


# ============ 页面配置 ============
st.set_page_config(
    page_title="Stock Insight",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============ 自定义样式 ============
st.markdown("""
<style>
    :root {
        --brand: #22d3ee;
        --brand-strong: #67e8f9;
        --accent: #8b5cf6;
        --positive: #2dd4bf;
        --negative: #fb7185;
        --ink: #e6edf7;
        --muted: #8b9bb1;
        --line: #1c293b;
        --line-strong: #26384f;
        --surface: #0d1422;
        --surface-raised: #111b2c;
        --canvas: #070b14;
    }
    html, body, [class*="css"] {
        font-family: Inter, "SF Pro Display", "Microsoft YaHei", system-ui, sans-serif;
    }
    .stApp {
        background:
            radial-gradient(circle at 50% -8%, rgba(34, 211, 238, 0.10), transparent 34rem),
            radial-gradient(circle at 100% 16%, rgba(139, 92, 246, 0.07), transparent 28rem),
            var(--canvas);
        color: var(--ink);
    }
    [data-testid="stHeader"] {
        background: rgba(7, 11, 20, 0.72);
        backdrop-filter: blur(14px);
        border-bottom: 1px solid rgba(28, 41, 59, 0.55);
    }
    [data-testid="stMainBlockContainer"] {
        max-width: 1380px;
        padding-top: 2rem;
        padding-bottom: 4rem;
    }
    [data-testid="stSidebar"] {
        background: rgba(9, 15, 26, 0.97);
        border-right: 1px solid var(--line);
    }
    [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
        padding-top: 1.5rem;
    }
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: var(--ink);
        letter-spacing: -0.02em;
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] label {
        color: #a9b7ca;
    }
    .main-header {
        font-size: clamp(2rem, 4vw, 2.9rem);
        font-weight: 750;
        line-height: 1.05;
        letter-spacing: -0.04em;
        background: linear-gradient(110deg, #f3f8ff 15%, #67e8f9 58%, #a78bfa 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin: 0.25rem 0 1.35rem;
        filter: drop-shadow(0 0 24px rgba(34, 211, 238, 0.12));
    }
    .nav-label {
        color: var(--muted);
        font-size: 0.76rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin: 0 0 0.4rem 0.15rem;
    }
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: linear-gradient(145deg, rgba(17, 27, 44, 0.94), rgba(11, 18, 31, 0.96));
        border-color: var(--line) !important;
        border-radius: 1rem !important;
        box-shadow: 0 18px 48px rgba(0, 0, 0, 0.22);
    }
    div[data-testid="stSegmentedControl"] [data-baseweb="button-group"] {
        width: 100%;
        padding: 0.24rem;
        border-radius: 0.78rem;
        background: #080e19;
        border: 1px solid var(--line);
    }
    div[data-testid="stSegmentedControl"] button {
        flex: 1;
        min-height: 2.55rem;
        border: 0 !important;
        border-radius: 0.62rem !important;
        background: #0f1a2b !important;
        font-weight: 650;
        color: #8fa0b7;
    }
    div[data-testid="stSegmentedControl"] button[aria-pressed="true"],
    div[data-testid="stSegmentedControl"] button[aria-checked="true"],
    div[data-testid="stSegmentedControl"] button[data-active="true"],
    button[kind="segmented_control"][aria-pressed="true"],
    button[kind="segmented_control"][aria-checked="true"],
    button[kind="segmented_control"][data-active="true"] {
        background: #172337 !important;
        color: var(--brand-strong) !important;
        box-shadow: inset 0 0 0 1px rgba(34, 211, 238, 0.28), 0 6px 18px rgba(0, 0, 0, 0.22);
    }
    div[data-testid="stSegmentedControl"] button * {
        color: inherit !important;
    }
    button[data-variant="segmented_control"] {
        background: #0f1a2b !important;
        color: #8fa0b7 !important;
    }
    button[data-variant="segmented_control"][aria-checked="true"],
    button[data-variant="segmented_control"][data-selected="true"] {
        background: #172337 !important;
        color: var(--brand-strong) !important;
        box-shadow: inset 0 0 0 1px rgba(34, 211, 238, 0.28), 0 6px 18px rgba(0, 0, 0, 0.22);
    }
    button[data-variant="segmented_control"] * {
        color: inherit !important;
    }
    .metric-card {
        background-color: var(--surface);
        border-radius: 12px;
        padding: 1rem;
        text-align: center;
    }
    [data-testid="stMetric"] {
        min-height: 7rem;
        padding: 1.05rem 1.15rem;
        border: 1px solid var(--line);
        border-radius: 0.9rem;
        background: linear-gradient(145deg, rgba(17, 27, 44, 0.98), rgba(12, 20, 34, 0.98));
        box-shadow: 0 10px 28px rgba(0, 0, 0, 0.18);
        transition: border-color 160ms ease, transform 160ms ease;
    }
    [data-testid="stMetric"]:hover {
        border-color: var(--line-strong);
        transform: translateY(-1px);
    }
    [data-testid="stMetricLabel"] {
        color: var(--muted);
        font-weight: 600;
    }
    [data-testid="stMetricValue"] {
        color: var(--ink);
        letter-spacing: -0.035em;
    }
    [data-testid="stMetric"]:has([data-testid="stMetricDelta"]) > div {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        column-gap: 0.75rem;
        row-gap: 0.2rem;
    }
    [data-testid="stMetric"]:has([data-testid="stMetricDelta"])
        [data-testid="stMetricLabel"] {
        flex: 0 0 100%;
    }
    [data-testid="stMetric"]:has([data-testid="stMetricDelta"])
        [data-testid="stMetricValue"] {
        flex: 0 0 auto;
    }
    [data-testid="stMetric"]:has([data-testid="stMetricDelta"])
        [data-testid="stMetricDelta"] {
        margin: 0;
        white-space: nowrap;
    }
    .cn-price-direction {
        display: none;
    }
    [data-testid="stColumn"]:has(.cn-price-up) [data-testid="stMetricValue"],
    [data-testid="stColumn"]:has(.cn-price-up) [data-testid="stMetricValue"] p {
        color: #e53935 !important;
    }
    [data-testid="stColumn"]:has(.cn-price-down) [data-testid="stMetricValue"],
    [data-testid="stColumn"]:has(.cn-price-down) [data-testid="stMetricValue"] p {
        color: #1e9d55 !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.35rem;
        padding: 0.3rem;
        border-radius: 0.85rem;
        background: #080e19;
        border: 1px solid var(--line);
    }
    .stTabs [data-baseweb="tab"] {
        padding: 0.65rem 1rem;
        border-radius: 0.65rem;
        font-weight: 600;
        color: #8fa0b7;
    }
    .stTabs [aria-selected="true"] {
        background: #172337;
        color: var(--brand-strong) !important;
        box-shadow: inset 0 0 0 1px rgba(34, 211, 238, 0.22);
    }
    .stTabs [data-baseweb="tab-highlight"] {
        display: none;
    }
    .stButton > button {
        border-radius: 0.7rem;
        border-color: var(--line-strong);
        background: #111b2c;
        color: #d9e4f2;
        font-weight: 650;
    }
    .stButton > button:hover {
        border-color: var(--brand);
        color: var(--brand-strong);
        background: #152338;
    }
    [data-baseweb="select"] > div,
    [data-baseweb="input"] > div,
    [data-baseweb="textarea"] > div,
    [data-testid="stDateInput"] input,
    [data-testid="stNumberInput"] input {
        background-color: #0b1320 !important;
        border-color: var(--line-strong) !important;
        color: var(--ink) !important;
    }
    [data-baseweb="popover"],
    [data-baseweb="menu"],
    [data-baseweb="calendar"] {
        background-color: #111b2c !important;
        color: var(--ink) !important;
    }
    [data-testid="stExpander"] {
        border-color: var(--line) !important;
        background: rgba(13, 20, 34, 0.72);
        border-radius: 0.85rem;
    }
    [data-testid="stPlotlyChart"],
    [data-testid="stDataFrame"] {
        overflow: hidden;
        border: 1px solid var(--line);
        border-radius: 1rem;
        background: var(--surface);
        box-shadow: 0 14px 34px rgba(0, 0, 0, 0.18);
    }
    [data-testid="stDataFrame"] iframe {
        color-scheme: dark;
    }
    hr {
        border-color: var(--line) !important;
    }
    .indicator-summary-grid,
    .rsi-zone-grid {
        display: grid;
        gap: 0.8rem;
        margin: 0.85rem 0;
    }
    .indicator-summary-grid {
        grid-template-columns: repeat(3, minmax(0, 1fr));
    }
    .rsi-zone-grid {
        grid-template-columns: repeat(3, minmax(0, 1fr));
    }
    .indicator-summary-card,
    .rsi-zone-card {
        padding: 0.9rem 1rem;
        border: 1px solid var(--line);
        border-radius: 0.8rem;
        background: #0b1320;
    }
    .indicator-summary-card strong,
    .rsi-zone-card strong {
        display: block;
        color: var(--ink);
        font-size: 0.88rem;
        margin-bottom: 0.3rem;
    }
    .indicator-summary-card span,
    .rsi-zone-card span {
        color: var(--muted);
        font-size: 0.82rem;
        line-height: 1.55;
    }
    .rsi-zone-card {
        border-top-width: 3px;
    }
    .rsi-zone-card.oversold {
        border-top-color: var(--positive);
        background: rgba(45, 212, 191, 0.07);
    }
    .rsi-zone-card.neutral {
        border-top-color: #64748b;
    }
    .rsi-zone-card.overbought {
        border-top-color: var(--negative);
        background: rgba(251, 113, 133, 0.07);
    }
    .indicator-note {
        margin-top: 0.75rem;
        padding: 0.75rem 0.9rem;
        border-left: 3px solid var(--brand);
        border-radius: 0 0.55rem 0.55rem 0;
        background: rgba(34, 211, 238, 0.055);
        color: #9babc0;
        font-size: 0.86rem;
        line-height: 1.6;
    }
    .pe-formula-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 1rem;
        margin: 0.75rem 0 1.25rem;
    }
    .pe-formula-card {
        min-height: 9rem;
        padding: 1.1rem 0.8rem;
        border: 1px solid var(--line);
        border-radius: 0.8rem;
        background: #0b1320;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 0.8rem;
    }
    .pe-formula-title {
        color: #93a4ba;
        font-size: 0.9rem;
        font-weight: 600;
    }
    .pe-formula {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.55rem;
        color: #dce7f5;
        font-family: "Times New Roman", "Microsoft YaHei", serif;
        font-size: 1.15rem;
        line-height: 1.45;
        white-space: nowrap;
    }
    .pe-formula sub {
        font-size: 0.68em;
    }
    .pe-fraction {
        display: inline-grid;
        grid-template-rows: auto auto;
        text-align: center;
        font-family: "Microsoft YaHei", sans-serif;
        font-size: 0.95rem;
        line-height: 1.55;
    }
    .pe-fraction span:first-child {
        padding: 0 0.5rem 0.2rem;
        border-bottom: 1px solid currentColor;
    }
    .pe-fraction span:last-child {
        padding: 0.2rem 0.5rem 0;
    }
    [data-testid="stAlert"] {
        background: rgba(17, 27, 44, 0.92);
        border: 1px solid var(--line-strong);
        color: #cbd7e6;
    }
    [data-testid="stDownloadButton"] button {
        background: linear-gradient(110deg, #0891b2, #2563eb);
        border: 0;
        color: white;
    }
    a { color: var(--brand-strong); }
    .nav-context {
        margin-top: 0.85rem;
        padding-top: 0.85rem;
        border-top: 1px solid rgba(38, 56, 79, 0.72);
    }
    .ranking-header,
    .news-header {
        margin: 0.35rem 0 1.15rem;
    }
    .ranking-header h2,
    .news-header h2 {
        margin-bottom: 0.3rem;
        color: var(--ink);
        letter-spacing: -0.025em;
    }
    .ranking-header p,
    .news-header p {
        margin: 0;
        color: var(--muted);
        font-size: 0.9rem;
    }
    .news-source-badge {
        display: inline-flex;
        align-items: center;
        min-width: 4.5rem;
        justify-content: center;
        padding: 0.25rem 0.55rem;
        border: 1px solid var(--line-strong);
        border-radius: 999px;
        background: #101b2c;
        color: var(--brand-strong);
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.02em;
    }
    .news-time {
        color: var(--muted);
        font-size: 0.78rem;
        white-space: nowrap;
    }
    @media (max-width: 900px) {
        [data-testid="stMainBlockContainer"] {
            padding-top: 1rem;
        }
        .nav-context {
            margin-top: 0.65rem;
            padding-top: 0.65rem;
        }
        .pe-formula-grid {
            grid-template-columns: 1fr;
        }
        .indicator-summary-grid,
        .rsi-zone-grid {
            grid-template-columns: 1fr;
        }
        .pe-formula-card {
            min-height: 7.5rem;
        }
    }
</style>
""", unsafe_allow_html=True)


def is_a_share_trading_session() -> bool:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if now.weekday() >= 5:
        return False
    current = now.time()
    return (
        datetime.strptime("09:30", "%H:%M").time()
        <= current
        <= datetime.strptime("11:30", "%H:%M").time()
    ) or (
        datetime.strptime("13:00", "%H:%M").time()
        <= current
        <= datetime.strptime("15:00", "%H:%M").time()
    )


@st.cache_data(ttl=25, show_spinner=False)
def load_a_share_market_snapshot():
    universe_rows = flatten_a_share_universe(A_SHARE_UNIVERSE)
    return fetch_a_share_market_snapshot(universe_rows)


@st.cache_data(ttl=600, show_spinner=False)
def load_recent_financial_news(hours=72):
    return fetch_recent_financial_news(hours=hours)


RANKING_CONFIG = {
    "change_pct": ("涨幅榜", "涨跌幅", 1.0, "%.2f%%"),
    "amount": ("成交额榜", "成交额（亿元）", 1e8, "%.2f"),
    "market_cap": ("市值榜", "总市值（亿元）", 1e8, "%.2f"),
    "pe_ttm": ("市盈率榜", "PE TTM", 1.0, "%.2f"),
}


def render_ranking_table(snapshot, metric):
    title, metric_label, divisor, number_format = RANKING_CONFIG[metric]
    ranked = rank_snapshot(snapshot, metric).copy()
    ranked[metric] = pd.to_numeric(ranked[metric], errors="coerce") / divisor
    columns = ["rank", "name", "ticker", "industry", metric, "quote_time", "stale"]
    display = ranked.reindex(columns=columns).rename(
        columns={
            "rank": "排名",
            "name": "股票",
            "ticker": "代码",
            "industry": "赛道",
            metric: metric_label,
            "quote_time": "数据时间",
            "stale": "状态",
        }
    )
    display["状态"] = display["状态"].map({True: "缓存", False: "实时"}).fillna("实时")
    st.dataframe(
        display,
        width="stretch",
        height=560,
        hide_index=True,
        column_config={
            "排名": st.column_config.NumberColumn(width="small", format="%d"),
            metric_label: st.column_config.NumberColumn(format=number_format),
            "状态": st.column_config.TextColumn(width="small"),
        },
        key=f"a-share-ranking:{metric}",
    )
    st.caption(f"{title}覆盖 A_SHARE_UNIVERSE 全部 {len(display)} 只股票。")


@st.fragment(run_every="30s" if is_a_share_trading_session() else None)
def render_a_share_rankings():
    header_col, action_col = st.columns([5, 1])
    with header_col:
        st.markdown(
            """
            <div class="ranking-header">
                <h2>A股股票池排行</h2>
                <p>覆盖全部产业链标的，实时指标与最新完成日 K 估值分开计算。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with action_col:
        manually_refreshed = st.button(
            "立即刷新", key="refresh-a-share-rankings", width="stretch"
        )
    if manually_refreshed:
        load_a_share_market_snapshot.clear()

    try:
        with st.spinner("正在更新 A股股票池快照..."):
            snapshot = load_a_share_market_snapshot()
    except Exception as error:
        st.error(f"排行榜暂时无法更新：{error}")
        return

    if snapshot.empty:
        st.warning("暂时没有可用于排行榜的 A股行情。")
        return

    stale_series = snapshot.get("stale", pd.Series(False, index=snapshot.index))
    stale_count = int(stale_series.fillna(False).sum())
    quote_times = snapshot.get("quote_time")
    latest_quote_time = ""
    if quote_times is not None and quote_times.notna().any():
        latest_quote_time = str(quote_times.dropna().max())
    refresh_note = "交易时段每 30 秒刷新" if is_a_share_trading_session() else "非交易时段停止自动刷新"
    stale_note = f" · {stale_count} 只使用缓存" if stale_count else ""
    st.caption(
        f"排行榜数据来源：东方财富 · {refresh_note}"
        f"{f' · 数据时间 {latest_quote_time}' if latest_quote_time else ''}{stale_note}"
    )

    ranking_tabs = st.tabs([config[0] for config in RANKING_CONFIG.values()])
    for tab, metric in zip(ranking_tabs, RANKING_CONFIG):
        with tab:
            render_ranking_table(snapshot, metric)


def _format_news_time(value):
    if value is None:
        return "采集时间未知"
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("Asia/Shanghai")
    else:
        timestamp = timestamp.tz_convert("Asia/Shanghai")
    return timestamp.strftime("%m-%d %H:%M")


def render_news_page():
    header_col, action_col = st.columns([5, 1])
    with header_col:
        st.markdown(
            """
            <div class="news-header">
                <h2>新闻热点</h2>
                <p>最近 72 小时财经快报 · Yahoo 3 条 / 同花顺 4 条 / 抖音 3 条</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with action_col:
        manually_refreshed = st.button(
            "刷新热点", key="refresh-financial-news", width="stretch"
        )
    if manually_refreshed:
        load_recent_financial_news.clear()

    try:
        with st.spinner("正在汇总财经热点..."):
            items, source_status = load_recent_financial_news(72)
    except Exception as error:
        st.error(f"新闻热点暂时无法加载：{error}")
        return

    if not items:
        st.warning("最近 72 小时暂未读取到可显示的财经热点。")
    for item in items:
        effective_time = getattr(item, "published_at", None) or getattr(item, "observed_at", None)
        with st.container(border=True):
            source_col, title_col, time_col, link_col = st.columns([1.1, 6.8, 1.4, 1.2])
            with source_col:
                st.markdown(
                    f'<span class="news-source-badge">{html.escape(item.source)}</span>',
                    unsafe_allow_html=True,
                )
            with title_col:
                st.markdown(f"**{html.escape(item.title)}**")
            with time_col:
                st.markdown(
                    f'<span class="news-time">{_format_news_time(effective_time)}</span>',
                    unsafe_allow_html=True,
                )
            with link_col:
                st.link_button("查看原文", item.url, width="stretch")

    non_ok_status = [
        f"{source}：{status}"
        for source, status in source_status.items()
        if status and str(status).lower() not in {"ok", "正常"}
    ]
    if non_ok_status:
        st.caption(" · ".join(non_ok_status))


# ============ 标题区域 ============
st.markdown('<div class="main-header">Stock Insight</div>', unsafe_allow_html=True)

# ============ 顶部导航 ============
nav_spacer_left, nav_area, nav_spacer_right = st.columns([1, 5, 1])
market_label = None
a_share_view = None
with nav_area:
    with st.container(border=True):
        page = st.segmented_control(
            "主导航",
            ["行情分析", "指标说明", "新闻热点"],
            default="行情分析",
            key="page_navigation",
            label_visibility="collapsed",
            width="stretch",
        )
        if page == "行情分析":
            st.markdown('<div class="nav-context"></div>', unsafe_allow_html=True)
            market_nav, a_share_nav = st.columns(2, gap="large")
            with market_nav:
                st.markdown('<div class="nav-label">股票市场</div>', unsafe_allow_html=True)
                market_label = st.segmented_control(
                    "股票市场",
                    ["美股", "A股"],
                    default="美股",
                    key="market_navigation",
                    label_visibility="collapsed",
                    width="stretch",
                )
            a_share_view = "个股分析"
            if market_label == "A股":
                with a_share_nav:
                    st.markdown('<div class="nav-label">A股视图</div>', unsafe_allow_html=True)
                    a_share_view = st.segmented_control(
                        "A股视图",
                        ["个股分析", "股票池排行"],
                        default="个股分析",
                        key="a_share_view_navigation",
                        label_visibility="collapsed",
                        width="stretch",
                    )

# 非行情页面在构建侧栏及请求市场数据前完成路由。
if page == "指标说明":
    st.markdown("---")
    render_indicator_help()
    st.stop()
if page == "新闻热点":
    st.markdown("---")
    render_news_page()
    st.stop()
if market_label == "A股" and a_share_view == "股票池排行":
    st.markdown("---")
    render_a_share_rankings()
    st.stop()

# ============ 侧边栏控制面板 ============
st.sidebar.header("行情参数")

# 股票市场与标的选择
market = "CN" if market_label == "A股" else "US"
ths_access_token = get_ths_access_token()

if market == "CN":
    industry = st.sidebar.selectbox("产业链赛道", list(A_SHARE_UNIVERSE.keys()))
    a_share_options = {
        f"{name} ({code})": code
        for name, code in A_SHARE_UNIVERSE[industry]
    }
    selected_option = st.sidebar.selectbox("选择股票", list(a_share_options.keys()))
    ticker = a_share_options[selected_option]
else:
    ticker_options = {
        "Apple (AAPL)": "AAPL",
        "Microsoft (MSFT)": "MSFT",
        "Tesla (TSLA)": "TSLA",
        "Amazon (AMZN)": "AMZN",
        "Google (GOOGL)": "GOOGL",
        "Meta (META)": "META",
        "NVIDIA (NVDA)": "NVDA",
        "SpaceX (SPCX)": "SPCX",
        "Broadcom (AVGO)": "AVGO",
        "SanDisk (SNDK)": "SNDK",
        "Micron (MU)": "MU",
        "Berkshire Hathaway (BRK-B)": "BRK-B",
        "JPMorgan (JPM)": "JPM",
        "Visa (V)": "V",
        "Custom Input": "CUSTOM",
    }
    selected_option = st.sidebar.selectbox("选择股票", list(ticker_options.keys()))
    if ticker_options[selected_option] == "CUSTOM":
        ticker = st.sidebar.text_input("输入股票代码", "AAPL").upper()
    else:
        ticker = ticker_options[selected_option]

# 时间范围
col1, col2 = st.sidebar.columns(2)
with col1:
    start_date = st.date_input("开始日期", datetime.now() - timedelta(days=365))
with col2:
    end_date = st.date_input("结束日期", datetime.now())

# 技术指标参数
st.sidebar.markdown("---")
st.sidebar.subheader("技术指标设置")

ma_period_inputs = st.sidebar.multiselect(
    "移动平均线周期",
    options=[5, 10, 20, 30, 50, 60, 120],
    default=[5, 10, 20],
    accept_new_options=True,
    help="可选择预设周期，也可直接输入 1–500 之间的交易日数。",
)
ma_periods = []
for value in ma_period_inputs:
    try:
        period = int(value)
    except (TypeError, ValueError):
        continue
    if 1 <= period <= 500 and period not in ma_periods:
        ma_periods.append(period)

indicator_columns = st.sidebar.columns(2)
with indicator_columns[0]:
    show_bbi = st.toggle("BBI 线", value=False, help="多空指标：MA3、MA6、MA12、MA24 的均值")
with indicator_columns[1]:
    show_boll = st.toggle("BOLL 线", value=False, help="20 日中轨及上下 2 倍标准差轨道")

rsi_period = st.sidebar.slider("RSI周期", 7, 21, 14)


# ============ 数据获取 ============
@st.cache_data(ttl=3600, show_spinner=False)  # 缓存1小时
def load_data(ticker, start, end, market, ths_access_token):
    """缓存数据获取函数"""
    return fetch_stock_data(
        ticker,
        start,
        end,
        market=market,
        ths_access_token=ths_access_token,
    )


def indicator_warmup_start(
    display_start,
    ma_periods,
    rsi_period,
    show_bbi,
    show_boll,
):
    """Return an earlier request date so indicators are complete at the left edge."""
    required_sessions = [35, rsi_period + 1, *ma_periods]
    if show_bbi:
        required_sessions.append(24)
    if show_boll:
        required_sessions.append(20)

    # Add weekday headroom for exchange holidays and occasional missing sessions.
    warmup_sessions = max(required_sessions) + 15
    return (
        pd.Timestamp(display_start).normalize()
        - pd.offsets.BDay(warmup_sessions)
    ).date()


def trim_to_display_range(frame, display_start, display_end):
    """Keep only the user-selected range while preserving provider metadata."""
    attrs = frame.attrs.copy()
    start = pd.Timestamp(display_start)
    end = pd.Timestamp(display_end)
    trimmed = frame.loc[(frame.index >= start) & (frame.index <= end)].copy()
    trimmed.attrs.update(attrs)
    return trimmed


VALUATION_CACHE_VERSION = 4


@st.cache_data(ttl=300, show_spinner=False)
def load_valuation(ticker, cache_version=VALUATION_CACHE_VERSION):
    return fetch_a_share_valuation(ticker)


@st.cache_data(ttl=300, show_spinner=False)
def load_us_market_cap(ticker):
    return fetch_us_market_cap(ticker)


@st.cache_data(ttl=21600, show_spinner=False)
def load_financial_reports(ticker):
    return fetch_a_share_financial_reports(ticker)


@st.cache_data(ttl=25, show_spinner=False)
def load_intraday(ticker):
    return fetch_a_share_intraday(ticker)


@st.fragment(run_every="30s")
def render_intraday_panel(selected_ticker):
    session_key = f"intraday:{selected_ticker}"
    manually_refreshed = st.button(
        "立即刷新",
        key=f"refresh-intraday:{selected_ticker}",
        width="content",
    )
    if manually_refreshed:
        load_intraday.clear()
        st.session_state.pop(session_key, None)

    should_fetch = is_a_share_trading_session() or session_key not in st.session_state
    if should_fetch:
        try:
            st.session_state[session_key] = load_intraday(selected_ticker)
        except DataFetchError as error:
            if session_key not in st.session_state:
                st.warning(str(error))
                return

    intraday = st.session_state.get(session_key)
    if intraday is None or intraday.empty:
        st.info("暂时没有可显示的分时数据。")
        return

    trade_date = intraday.attrs.get("trade_date", "")
    source = intraday.attrs.get("source", "同花顺")
    refresh_note = "交易时段每 30 秒自动刷新" if is_a_share_trading_session() else "非交易时段显示最近数据"
    st.caption(f"交易日：{trade_date} · 数据来源：{source} · {refresh_note}")
    st.plotly_chart(
        plot_intraday(intraday, market="CN"),
        width="stretch",
        key=f"intraday-chart:{selected_ticker}",
    )


loading_message = st.empty()

try:
    loading_message.info(f"正在获取 {ticker} 数据...")
    calculation_start_date = indicator_warmup_start(
        start_date,
        ma_periods,
        rsi_period,
        show_bbi,
        show_boll,
    )
    indicator_history_df = load_data(
        ticker,
        calculation_start_date,
        end_date,
        market,
        ths_access_token,
    )
    df = trim_to_display_range(indicator_history_df, start_date, end_date)
    loading_message.empty()

    if df.empty:
        st.error(f"无法获取 {ticker} 的数据，请检查股票代码是否正确。")
        st.stop()

    data_source = indicator_history_df.attrs.get("source", "Yahoo Finance")
    st.success(f"成功加载 {ticker} 从 {start_date} 到 {end_date} 的数据")
    if data_source in {"同花顺", "同花顺 iFinD"}:
        st.caption("数据来源：同花顺")
    elif data_source == "同花顺本地缓存":
        st.warning("同花顺当前不可用，正在显示本地缓存数据。")
    elif data_source == "Yahoo Finance":
        st.caption("Data source: Yahoo Finance")
    elif data_source == "local cache":
        st.warning("Yahoo Finance 当前不可用，正在显示本地缓存数据。")
    elif data_source == "demo data":
        st.warning("Yahoo Finance 和备用数据源当前不可用，正在显示演示数据；请勿用于真实投资判断。")
    else:
        st.info(f"Yahoo Finance 当前不可用，已自动切换到 {data_source}。")

except DataFetchError as e:
    loading_message.empty()
    st.error(str(e))
    st.caption(f"Diagnosis: {e.category}")
    with st.expander("Technical details"):
        st.code(e.diagnostics, language="text")
    st.stop()
except Exception as e:
    loading_message.empty()
    st.error(f"数据获取失败: {str(e)}")
    st.info("提示：如果持续失败，可能是API限制，请稍后再试。")
    st.stop()

# ============ 关键指标展示 ============
st.markdown("---")

# 计算关键指标。A 股优先使用最新分时价，接口暂不可用时回退日线收盘价。
latest_price = df['Close'].iloc[-1]
prev_price = df['Close'].iloc[-2]
current_price_label = "当前价格"
if market == "CN":
    intraday_session_key = f"intraday:{ticker}"
    intraday_snapshot = st.session_state.get(intraday_session_key)
    if intraday_snapshot is None:
        try:
            intraday_snapshot = load_intraday(ticker)
            st.session_state[intraday_session_key] = intraday_snapshot
        except DataFetchError:
            intraday_snapshot = None
    if intraday_snapshot is not None and not intraday_snapshot.empty:
        latest_price = float(intraday_snapshot["Price"].iloc[-1])
        prev_price = float(intraday_snapshot.attrs.get("pre_close", prev_price))
        current_price_label = "当前价格（分时）"
    else:
        current_price_label = "当前价格（最近收盘）"

price_change = latest_price - prev_price
price_change_pct = (price_change / prev_price) * 100

high_52w = df['High'].max()
low_52w = df['Low'].min()
volume_avg = df['Volume'].mean()
volatility = df['Close'].pct_change().std() * np.sqrt(252) * 100
currency_symbol = "¥" if market == "CN" else "$"
price_change_sign = "+" if price_change >= 0 else "-"
price_delta_label = (
    f"{price_change_sign}{currency_symbol}{abs(price_change):.2f} "
    f"({price_change_pct:+.2f}%)"
)

valuation = {
    "pe_ttm": None,
    "pe_static": None,
    "pe_dynamic": None,
    "market_cap": None,
    "source": None,
}
valuation_error = None
if market == "CN":
    try:
        valuation = load_valuation(ticker, VALUATION_CACHE_VERSION)
    except Exception as error:
        valuation_error = str(error)
    market_cap = valuation.get("market_cap")
else:
    market_cap = load_us_market_cap(ticker)


def format_market_cap(value, selected_market):
    if value is None or not np.isfinite(value):
        return "暂不可用"
    if selected_market == "CN":
        if value >= 1e12:
            return f"¥{value / 1e12:.2f}万亿"
        if value >= 1e8:
            return f"¥{value / 1e8:.2f}亿"
        if value >= 1e4:
            return f"¥{value / 1e4:.2f}万"
        return f"¥{value:,.0f}"
    if value >= 1e12:
        return f"${value / 1e12:.2f}T"
    if value >= 1e9:
        return f"${value / 1e9:.2f}B"
    if value >= 1e6:
        return f"${value / 1e6:.2f}M"
    return f"${value:,.0f}"

if market == "CN":
    price_columns = st.columns(3)
    with price_columns[0]:
        direction_class = "cn-price-up" if price_change_pct >= 0 else "cn-price-down"
        st.metric(
            current_price_label,
            f"{currency_symbol}{latest_price:.2f}",
            price_delta_label,
            delta_color="inverse",
        )
        st.markdown(
            f'<span class="cn-price-direction {direction_class}"></span>',
            unsafe_allow_html=True,
        )
    with price_columns[1]:
        st.metric("52周最高", f"{currency_symbol}{high_52w:.2f}")
    with price_columns[2]:
        st.metric("52周最低", f"{currency_symbol}{low_52w:.2f}")

    secondary_columns = st.columns(3)
    with secondary_columns[0]:
        st.metric("平均成交量", f"{volume_avg / 1e6:.1f}M")
    with secondary_columns[1]:
        st.metric("年化波动率", f"{volatility:.1f}%")
    with secondary_columns[2]:
        st.metric("总市值", format_market_cap(market_cap, market))

    st.markdown("#### 估值概览")
    valuation_columns = st.columns(3)
    valuation_items = [
        ("市盈率 TTM", "pe_ttm"),
        ("静态市盈率", "pe_static"),
        ("动态市盈率", "pe_dynamic"),
    ]
    for column, (label, key) in zip(valuation_columns, valuation_items):
        value = valuation.get(key)
        with column:
            st.metric(label, f"{value:.2f} 倍" if value is not None else "亏损 / 不适用")
    if valuation_error:
        st.caption(f"公开估值数据暂不可用：{valuation_error}")
    elif valuation.get("source"):
        st.caption(
            f"估值数据来源：{valuation['source']} · {valuation.get('as_of', '')}"
        )
else:
    primary_metric_columns = st.columns(3)
    with primary_metric_columns[0]:
        st.metric(
            current_price_label,
            f"{currency_symbol}{latest_price:.2f}",
            price_delta_label,
            delta_color="normal",
        )
    with primary_metric_columns[1]:
        st.metric("52周最高", f"{currency_symbol}{high_52w:.2f}")
    with primary_metric_columns[2]:
        st.metric("52周最低", f"{currency_symbol}{low_52w:.2f}")

    secondary_metric_columns = st.columns(3)
    with secondary_metric_columns[0]:
        st.metric("平均成交量", f"{volume_avg / 1e6:.1f}M")
    with secondary_metric_columns[1]:
        st.metric("年化波动率", f"{volatility:.1f}%")
    with secondary_metric_columns[2]:
        st.metric("总市值", format_market_cap(market_cap, market))

# ============ 主内容区域 ============
tab1, tab_intraday, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "价格分析",
        "当日分时",
        "技术指标",
        "数据详情",
        "投资洞察",
        "财务报表",
    ]
)

# ============ Tab 1: 价格分析 ============
with tab1:
    st.subheader("K线图与成交量")
    volume_metric_label = st.segmented_control(
        "副图指标",
        ["成交量", "成交额"],
        default="成交量",
        key="price_volume_metric",
    )
    volume_metric = "amount" if volume_metric_label == "成交额" else "volume"

    # 计算移动平均线
    df_with_ma = indicator_history_df.copy()
    for period in ma_periods:
        df_with_ma[f'MA_{period}'] = calculate_ma(df_with_ma, period)
    if show_bbi:
        df_with_ma["BBI"] = calculate_bbi(df_with_ma)
    if show_boll:
        df_with_ma = calculate_bollinger_bands(df_with_ma)
    df_with_ma = trim_to_display_range(df_with_ma, start_date, end_date)

    # 绘制K线图
    fig = plot_candlestick(
        df_with_ma,
        ma_periods,
        currency="CNY" if market == "CN" else "USD",
        market=market,
        show_bbi=show_bbi,
        show_boll=show_boll,
        volume_metric=volume_metric,
    )
    st.plotly_chart(fig, width="stretch")

# ============ 当日分时 ============
with tab_intraday:
    if market == "CN":
        render_intraday_panel(ticker)
    else:
        st.info("当日分时图目前用于 A股。")

# ============ Tab 2: 技术指标 ============
with tab2:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("RSI (相对强弱指标)")
        history_rsi = calculate_rsi(indicator_history_df, rsi_period)
        df['RSI'] = history_rsi.reindex(df.index)
        fig_rsi = plot_rsi(df, rsi_period)
        st.plotly_chart(fig_rsi, width="stretch")

        # RSI 解读
        latest_rsi = df['RSI'].iloc[-1]
        if latest_rsi > 70:
            st.warning(f"⚠️ RSI = {latest_rsi:.1f} > 70，可能处于**超买**状态")
        elif latest_rsi < 30:
            st.success(f"✅ RSI = {latest_rsi:.1f} < 30，可能处于**超卖**状态")
        else:
            st.info(f"ℹ️ RSI = {latest_rsi:.1f}，处于中性区间")

    with col2:
        st.subheader("MACD (指数平滑异同平均线)")
        df_macd = calculate_macd(indicator_history_df)
        df_macd = trim_to_display_range(df_macd, start_date, end_date)
        fig_macd = plot_macd(df_macd)
        st.plotly_chart(fig_macd, width="stretch")

        # MACD 解读
        latest_macd = df_macd['MACD'].iloc[-1]
        latest_signal = df_macd['Signal'].iloc[-1]
        if latest_macd > latest_signal:
            st.success(f"✅ MACD ({latest_macd:.2f}) > Signal ({latest_signal:.2f})，**看涨信号**")
        else:
            st.warning(f"⚠️ MACD ({latest_macd:.2f}) < Signal ({latest_signal:.2f})，**看跌信号**")

# ============ Tab 3: 数据详情 ============
with tab3:
    st.subheader("原始数据")

    # 数据筛选
    col1, col2 = st.columns([1, 3])
    with col1:
        rows_to_show = st.slider("显示行数", 10, min(100, len(df)), 20)

    # 显示数据
    display_df = df.tail(rows_to_show).copy()
    display_df.index = display_df.index.strftime('%Y-%m-%d')
    display_df = display_df.round(2)

    st.dataframe(display_df, width="stretch")

    # 下载按钮
    csv = df.to_csv().encode('utf-8')
    st.download_button(
        label="下载完整数据 (CSV)",
        data=csv,
        file_name=f"{ticker}_stock_data.csv",
        mime="text/csv"
    )

    # 数据统计
    st.subheader("数据统计摘要")
    st.write(df.describe().round(2))

# ============ Tab 4: 投资洞察 ============
with tab4:
    st.subheader("AI 驱动的投资分析")

    # 简单规则引擎（模拟"AI分析"）
    signals = []

    # 价格趋势
    if df['Close'].iloc[-1] > df['Close'].iloc[-20:].mean():
        signals.append(("价格趋势", "看涨", "当前价格高于20日均线", "green"))
    else:
        signals.append(("价格趋势", "看跌", "当前价格低于20日均线", "red"))

    # RSI
    if df['RSI'].iloc[-1] < 30:
        signals.append(("RSI指标", "超卖", "RSI低于30，可能存在反弹机会", "green"))
    elif df['RSI'].iloc[-1] > 70:
        signals.append(("RSI指标", "超买", "RSI高于70，可能存在回调风险", "red"))
    else:
        signals.append(("RSI指标", "中性", "RSI处于正常区间", "gray"))

    # MACD
    if df_macd['MACD'].iloc[-1] > df_macd['Signal'].iloc[-1]:
        signals.append(("MACD指标", "金叉", "MACD上穿Signal线，买入信号", "green"))
    else:
        signals.append(("MACD指标", "死叉", "MACD下穿Signal线，卖出信号", "red"))

    # 波动率
    if volatility > 30:
        signals.append(("波动率", "高风险", f"年化波动率达{volatility:.1f}%，需注意风险", "orange"))
    else:
        signals.append(("波动率", "正常", f"年化波动率为{volatility:.1f}%", "green"))

    # 显示信号
    for name, status, desc, color in signals:
        with st.container():
            col1, col2, col3 = st.columns([2, 2, 6])
            col1.markdown(f"**{name}**")
            col2.markdown(f":{color}[{status}]")
            col3.markdown(f"*{desc}*")
            st.markdown("---")

    # 综合评分
    bullish_count = sum(1 for _, status, _, _ in signals if status in ["看涨", "超卖", "金叉", "正常"])
    total_signals = len(signals)
    score = (bullish_count / total_signals) * 100

    st.subheader("综合评分")
    progress_color = "green" if score > 60 else "orange" if score > 40 else "red"
    st.progress(score / 100, text=f"看涨评分: {score:.0f}/100")

    if score > 60:
        st.success("综合建议：技术指标偏向看涨，可考虑适量建仓")
    elif score > 40:
        st.warning("综合建议：信号混合，建议观望或轻仓操作")
    else:
        st.error("综合建议：技术指标偏向看跌，建议谨慎或减仓")

# ============ Tab 5: 财务报表 ============
with tab5:
    st.subheader("年度与季度财务报告")
    if market != "CN":
        st.info("财务报表视图目前用于 A股。")
    else:
        try:
            financial_reports = load_financial_reports(ticker)
            annual_reports = financial_reports[
                financial_reports["报告类型"] == "年报"
            ]
            quarter_reports = financial_reports[
                financial_reports["报告类型"] != "年报"
            ]

            st.caption("数据来源：同花顺 F10；季报指标为报告期累计口径。")
            st.markdown("#### 上一财年年报")
            if annual_reports.empty:
                st.info("暂未读取到上一财年年报。")
            else:
                st.table(
                    annual_reports,
                    width="stretch",
                    hide_index=True,
                )

            st.markdown("#### 最新财年已披露季报")
            if quarter_reports.empty:
                st.info("最新财年尚未披露季报。")
            else:
                st.table(
                    quarter_reports,
                    width="stretch",
                    hide_index=True,
                )
        except DataFetchError as error:
            st.warning(str(error))

# ============ 页脚 ============
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.9rem;">
    <p>Stock Insight | Personal market analysis dashboard | Data: Tonghuashun, Yahoo Finance, Eastmoney & Douyin</p>
</div>
""", unsafe_allow_html=True)
