from __future__ import annotations

import html
import importlib

import pandas as pd
import streamlit as st
import visualization

from config.app_config import configure_page
from market_snapshot import fetch_a_share_market_snapshot, flatten_a_share_universe, rank_snapshot
from news_fetcher import fetch_recent_financial_news
from services.market_data import is_a_share_trading_session
from services.market_overview_data import fetch_market_breadth, fetch_market_indices
# Streamlit caches imported helper modules across page reruns. Reload the chart
# module so this standalone page always uses the current index-chart renderer.
visualization = importlib.reload(visualization)


RANKING_CONFIG = {
    "change_pct": ("涨幅榜", "涨跌幅", 1.0, "%.2f%%"),
    "amount": ("成交额榜", "成交额（亿元）", 1e8, "%.2f"),
    "market_cap": ("市值榜", "总市值（亿元）", 1e8, "%.2f"),
    "pe_ttm": ("市盈率榜", "PE TTM", 1.0, "%.2f"),
}

MARKET_OVERVIEW_CACHE_VERSION = 2


@st.cache_data(ttl=25, show_spinner=False)
def load_a_share_market_snapshot(a_share_universe):
    return fetch_a_share_market_snapshot(flatten_a_share_universe(a_share_universe))


@st.cache_data(ttl=600, show_spinner=False)
def load_recent_financial_news(hours=72):
    return fetch_recent_financial_news(hours=hours)


@st.cache_data(ttl=30, show_spinner=False)
def load_cn_market_overview():
    indices = fetch_market_indices("CN")
    try:
        breadth = fetch_market_breadth("CN")
    except Exception as error:
        breadth = {"error": f"市场广度暂时不可用：{error}"}
    return indices, breadth


@st.cache_data(ttl=600, show_spinner=False)
def load_us_market_overview(cache_version=MARKET_OVERVIEW_CACHE_VERSION):
    indices = fetch_market_indices("US")
    try:
        breadth = fetch_market_breadth("US")
    except Exception as error:
        breadth = {"error": f"市场广度暂时不可用：{error}"}
    return indices, breadth


def _format_amount(value: float | None, market: str) -> str:
    if value is None or not pd.notna(value):
        return "暂不可用" if market == "CN" else "指数未提供"
    if market == "CN":
        return f"¥{value / 1e8:.2f}亿" if value >= 1e8 else f"¥{value:,.0f}"
    return f"${value:,.0f}"


def _index_card_html(item: dict, market: str) -> str:
    name = html.escape(str(item["name"]))
    code = html.escape(str(item.get("display_code", item["symbol"])))
    if "error" in item:
        return (
            '<div class="index-card index-card-error">'
            f'<div class="index-card-head"><strong>{name}</strong><span>{code}</span></div>'
            f'<div class="index-error">{html.escape(str(item["error"]))}</div></div>'
        )

    is_up = item["change"] >= 0
    direction_class = "index-up" if is_up else "index-down"
    arrow = "▲" if is_up else "▼"
    amount_label = _format_amount(item.get("amount"), market)
    if market == "CN" and item.get("amount_change") is not None:
        amount_delta = (
            f"{item['amount_change'] / 1e8:+.2f}亿 "
            f"({item['amount_change_pct']:+.2f}%)"
        )
    elif market == "CN":
        amount_delta = "暂不可用"
    else:
        amount_delta = "不使用 ETF 成交额代理"

    return (
        f'<div class="index-card {direction_class}">'
        f'<div class="index-card-head"><strong>{name}</strong><span>{code}</span></div>'
        f'<div class="index-price">{item["price"]:,.2f}</div>'
        f'<div class="index-change">{arrow} {item["change"]:+.2f}&nbsp;&nbsp;{item["change_pct"]:+.2f}%</div>'
        '<div class="index-details">'
        f'<div><small>成交额</small><b>{amount_label}</b></div>'
        f'<div><small>较上一交易日</small><b>{amount_delta}</b></div>'
        '</div>'
        f'<div class="index-meta">{html.escape(str(item["trade_date"]))}<span>·</span>{html.escape(str(item["source"]))}</div>'
        '</div>'
    )


def _render_breadth(breadth: dict, market: str) -> None:
    st.markdown('<div class="section-title"><h3>市场涨跌家数</h3></div>', unsafe_allow_html=True)
    if "error" in breadth:
        st.warning(breadth["error"])
        return
    up, flat, down, total = (int(breadth.get(key, 0)) for key in ("up", "flat", "down", "total"))
    up_pct = up / total * 100 if total else 0
    flat_pct = flat / total * 100 if total else 0
    down_pct = down / total * 100 if total else 0
    market_class = "market-cn" if market == "CN" else "market-us"
    st.markdown(
        f"""
        <div class="breadth-panel {market_class}">
          <div class="breadth-summary">
            <div class="breadth-stat stat-up"><small>上涨</small><strong>{up:,}</strong><span>{up_pct:.1f}%</span></div>
            <div class="breadth-stat stat-flat"><small>平盘</small><strong>{flat:,}</strong><span>{flat_pct:.1f}%</span></div>
            <div class="breadth-stat stat-down"><small>下跌</small><strong>{down:,}</strong><span>{down_pct:.1f}%</span></div>
            <div class="breadth-stat stat-total"><small>合计</small><strong>{total:,}</strong><span>全市场</span></div>
          </div>
          <div class="breadth-bar" aria-label="上涨 {up_pct:.1f}%，平盘 {flat_pct:.1f}%，下跌 {down_pct:.1f}%">
            <span class="bar-up" style="width:{up_pct:.4f}%"></span>
            <span class="bar-flat" style="width:{flat_pct:.4f}%"></span>
            <span class="bar-down" style="width:{down_pct:.4f}%"></span>
          </div>
          <div class="breadth-source">统计口径：{html.escape(str(breadth.get('source', '暂不可用')))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_market_overview(market: str) -> None:
    """Render the market-specific index dashboard without blocking partial data."""
    market_name = "A股" if market == "CN" else "美股"
    hero_col, action_col = st.columns([5, 1])
    with hero_col:
        st.markdown(
            f'<div class="overview-hero"><h1>{market_name}市场概览</h1><p>核心指数、成交额变化与全市场涨跌结构</p></div>',
            unsafe_allow_html=True,
        )
    if action_col.button("刷新数据", key=f"refresh-market-overview:{market}", width="stretch"):
        (load_cn_market_overview if market == "CN" else load_us_market_overview).clear()
    loader = load_cn_market_overview if market == "CN" else load_us_market_overview
    try:
        with st.spinner(f"正在更新{market_name}指数与市场广度..."):
            indices, breadth = loader()
    except Exception as error:
        indices, breadth = [], {"error": f"市场广度暂时不可用：{error}"}

    st.markdown('<div class="section-title"><h3>核心指数</h3></div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="index-grid {"market-cn" if market == "CN" else "market-us"}">' + "".join(_index_card_html(item, market) for item in indices) + "</div>",
        unsafe_allow_html=True,
    )

    _render_breadth(breadth, market)
    available = [item for item in indices if "error" not in item and item.get("intraday") is not None and not item["intraday"].empty]
    st.markdown('<div class="section-title"><h3>指数分时</h3></div>', unsafe_allow_html=True)
    if not available:
        st.info("当前没有可展示的指数分时数据。")
        return
    selector_col, date_col = st.columns([2, 3])
    selection = selector_col.selectbox("选择指数", [item["name"] for item in available], key=f"market-overview-index:{market}")
    selected = next(item for item in available if item["name"] == selection)
    intraday = selected["intraday"].copy()
    if market == "US" and not intraday.empty:
        latest_session = pd.Timestamp(intraday.index[-1]).date()
        intraday = intraday[pd.Index(intraday.index.date) == latest_session].copy()
    if "Price" not in intraday.columns:
        intraday["Price"] = intraday["Close"]
    date_col.markdown(
        f'<div class="trade-date"><small>显示交易日</small><strong>{pd.Timestamp(intraday.index[-1]).strftime("%Y-%m-%d")}</strong><span>{"当日" if market == "CN" and is_a_share_trading_session() else "最近可用交易日"}</span></div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        visualization.plot_index_intraday(
            intraday,
            selected["name"],
            selected["previous_close"],
            market=market,
        ),
        width="stretch",
        key=f"market-index-chart:{market}:{selected['symbol']}",
    )


def render_market_overview_page() -> None:
    """Standalone Streamlit page served at /market_overviews."""
    configure_page()
    st.markdown(
        """
        <style>
        :root { --surface:#0e1727; --surface-2:#111d30; --line:#223149; --ink:#edf5ff; --muted:#8291a8; --cyan:#22d3ee; }
        .stApp { background: radial-gradient(circle at 55% -15%, rgba(34,211,238,.08), transparent 34rem), #070b14; color: var(--ink); }
        [data-testid="stMainBlockContainer"] { max-width: 1440px; padding-top: 3rem; padding-bottom: 5rem; }
        .main-header { color: var(--ink); font-size: 2rem; font-weight: 760; letter-spacing: -.035em; margin: 0 0 1.35rem; }
        .overview-hero span, .section-title span { color: var(--cyan); font-size:.7rem; font-weight:800; letter-spacing:.14em; }
        .overview-hero h1 { color:var(--ink); font-size:2rem; letter-spacing:-.035em; margin:0 0 .15rem; }
        .overview-hero p { color:var(--muted); margin:0; font-size:.88rem; }
        .section-title { margin:2rem 0 .85rem; }
        .section-title h3 { color:var(--ink); font-size:1.28rem; margin:0; letter-spacing:-.02em; }
        .index-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:1rem; }
        .index-card { position:relative; min-height:15.4rem; padding:1.25rem; overflow:hidden; border:1px solid var(--line); border-radius:1rem; background:linear-gradient(145deg,rgba(17,29,48,.97),rgba(10,18,31,.98)); box-shadow:0 16px 40px rgba(0,0,0,.18); }
        .index-card::before { content:""; position:absolute; inset:0 auto auto 0; width:100%; height:2px; background:var(--accent,#64748b); }
        .market-cn .index-up { --accent:#fb7185; } .market-cn .index-down { --accent:#2dd4bf; }
        .market-us .index-up { --accent:#2dd4bf; } .market-us .index-down { --accent:#fb7185; }
        .index-card-head { display:flex; justify-content:space-between; align-items:center; gap:.8rem; }
        .index-card-head strong { color:var(--ink); font-size:1.08rem; }
        .index-card-head span { padding:.2rem .48rem; color:#67e8f9; background:rgba(34,211,238,.08); border:1px solid rgba(34,211,238,.18); border-radius:.42rem; font:600 .74rem ui-monospace,monospace; }
        .index-price { margin:.85rem 0 .15rem; color:var(--ink); font-size:2rem; font-weight:680; letter-spacing:-.045em; }
        .index-change { display:inline-flex; padding:.25rem .55rem; color:var(--accent); background:color-mix(in srgb,var(--accent) 12%,transparent); border-radius:999px; font-size:.82rem; font-weight:700; }
        .index-details { display:grid; grid-template-columns:1fr 1fr; gap:.65rem; margin:1rem 0; }
        .index-details div { padding:.65rem .72rem; border:1px solid rgba(34,49,73,.78); border-radius:.68rem; background:rgba(6,12,22,.42); }
        .index-details small { display:block; color:var(--muted); font-size:.69rem; margin-bottom:.22rem; }
        .index-details b { display:block; overflow:hidden; color:#cdd9e8; font-size:.78rem; font-weight:650; text-overflow:ellipsis; white-space:nowrap; }
        .index-meta { display:flex; gap:.4rem; position:absolute; left:1.25rem; right:1.25rem; bottom:1rem; color:#6f8098; font-size:.7rem; }
        .index-card-error { min-height:8rem; } .index-error { color:#fb7185; margin-top:1.2rem; font-size:.82rem; }
        .breadth-panel { padding:1.1rem 1.2rem; border:1px solid var(--line); border-radius:1rem; background:linear-gradient(145deg,rgba(17,29,48,.95),rgba(10,18,31,.98)); }
        .breadth-summary { display:grid; grid-template-columns:repeat(4,1fr); gap:.7rem; }
        .breadth-stat { padding:.65rem .8rem; border-right:1px solid var(--line); }
        .breadth-stat:last-child { border-right:0; }
        .breadth-stat small,.breadth-stat span { display:block; color:var(--muted); font-size:.7rem; }
        .breadth-stat strong { display:block; color:var(--ink); font-size:1.55rem; line-height:1.25; letter-spacing:-.035em; }
        .market-cn .stat-up strong,.market-cn .stat-up span,.market-us .stat-down strong,.market-us .stat-down span { color:#fb7185; }
        .market-cn .stat-down strong,.market-cn .stat-down span,.market-us .stat-up strong,.market-us .stat-up span { color:#2dd4bf; }
        .breadth-bar { display:flex; height:.48rem; margin:1rem 0 .7rem; overflow:hidden; border-radius:999px; background:#1e293b; }
        .market-cn .bar-up,.market-us .bar-down { background:#fb7185; } .market-cn .bar-down,.market-us .bar-up { background:#2dd4bf; } .bar-flat { background:#64748b; }
        .breadth-source { color:#718198; font-size:.7rem; }
        .trade-date { display:flex; align-items:center; justify-content:flex-end; gap:.55rem; min-height:4.2rem; padding-top:1.35rem; }
        .trade-date small { color:var(--muted); } .trade-date strong { color:var(--ink); } .trade-date span { padding:.2rem .48rem; color:#67e8f9; background:rgba(34,211,238,.08); border-radius:999px; font-size:.7rem; }
        [data-testid="stPlotlyChart"] { overflow:hidden; border:1px solid var(--line); border-radius:1rem; box-shadow:0 16px 42px rgba(0,0,0,.18); }
        div[data-testid="stSegmentedControl"] [data-baseweb="button-group"] { padding:.25rem; background:#0b1423; border:1px solid var(--line); border-radius:.8rem; }
        .stButton>button { margin-top:.55rem; border-color:var(--line); border-radius:.7rem; background:var(--surface); color:#dbe8f7; }
        @media(max-width:1000px){ .index-grid{grid-template-columns:repeat(2,minmax(0,1fr));} }
        @media(max-width:680px){ .index-grid,.breadth-summary{grid-template-columns:1fr;} .breadth-stat{border-right:0;border-bottom:1px solid var(--line);} .index-details{grid-template-columns:1fr;} }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="main-header">Stock Insight · 市场概览</div>', unsafe_allow_html=True)
    market_label = st.segmented_control(
        "市场",
        ["A股", "美股"],
        default="A股",
        key="market-overview-page-market",
        width="stretch",
    )
    render_market_overview("CN" if market_label == "A股" else "US")


if __name__ == "__main__":
    render_market_overview_page()


def _render_ranking_table(snapshot, metric):
    title, metric_label, divisor, number_format = RANKING_CONFIG[metric]
    ranked = rank_snapshot(snapshot, metric).copy()
    ranked[metric] = pd.to_numeric(ranked[metric], errors="coerce") / divisor
    display = ranked.reindex(columns=["rank", "name", "ticker", "industry", metric, "quote_time", "stale"]).rename(
        columns={"rank": "排名", "name": "股票", "ticker": "代码", "industry": "赛道", metric: metric_label, "quote_time": "数据时间", "stale": "状态"}
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
    st.caption(f"{title}覆盖股票池全部 {len(display)} 只股票。")


@st.fragment(run_every="30s" if is_a_share_trading_session() else None)
def render_a_share_rankings(a_share_universe):
    header, action = st.columns([5, 1])
    with header:
        st.markdown("## A股股票池排行\n覆盖全部产业链标的，实时指标与最新完成日 K 估值分开计算。")
    with action:
        refreshed = st.button("立即刷新", key="refresh-a-share-rankings", width="stretch")
    if refreshed:
        load_a_share_market_snapshot.clear()
    try:
        with st.spinner("正在更新 A股股票池快照..."):
            snapshot = load_a_share_market_snapshot(a_share_universe)
    except Exception as error:
        st.error(f"排行榜暂时无法更新：{error}")
        return
    if snapshot.empty:
        st.warning("暂时没有可用于排行榜的 A股行情。")
        return
    quote_times = snapshot.get("quote_time")
    latest = str(quote_times.dropna().max()) if quote_times is not None and quote_times.notna().any() else ""
    stale_count = int(snapshot.get("stale", pd.Series(False, index=snapshot.index)).fillna(False).sum())
    st.caption(f"数据来源：东方财富 · {'交易时段每 30 秒刷新' if is_a_share_trading_session() else '非交易时段停止自动刷新'}{f' · 数据时间 {latest}' if latest else ''}{f' · {stale_count} 只使用缓存' if stale_count else ''}")
    tabs = st.tabs([config[0] for config in RANKING_CONFIG.values()])
    for tab, metric in zip(tabs, RANKING_CONFIG):
        with tab:
            _render_ranking_table(snapshot, metric)


def _format_news_time(value):
    if value is None:
        return "采集时间未知"
    timestamp = pd.Timestamp(value)
    timestamp = timestamp.tz_localize("Asia/Shanghai") if timestamp.tzinfo is None else timestamp.tz_convert("Asia/Shanghai")
    return timestamp.strftime("%m-%d %H:%M")


def render_news_page():
    header, action = st.columns([5, 1])
    with header:
        st.markdown("## 新闻热点\n最近 72 小时财经快报，覆盖 Yahoo、同花顺和抖音热点。")
    with action:
        refreshed = st.button("刷新热点", key="refresh-financial-news", width="stretch")
    if refreshed:
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
            source, title, published, link = st.columns([1.1, 6.8, 1.4, 1.2])
            source.markdown(f"**{html.escape(item.source)}**")
            title.markdown(f"**{html.escape(item.title)}**")
            published.caption(_format_news_time(effective_time))
            link.link_button("查看原文", item.url, width="stretch")
    errors = [f"{source}：{status}" for source, status in source_status.items() if status and str(status).lower() not in {"ok", "正常"}]
    if errors:
        st.caption(" · ".join(errors))
