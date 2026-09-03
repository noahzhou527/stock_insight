"""Standalone market overview page and shared market renderers."""

from __future__ import annotations

import html
import importlib

import pandas as pd
import streamlit as st
import visualization
import services.market_overview_data as market_overview_data

from styles import load_styles
from financial_rankings import fetch_latest_quarter_net_profit_ranking
from market_snapshot import fetch_a_share_market_snapshot, flatten_a_share_universe, rank_snapshot
from news_fetcher import fetch_recent_financial_news
from services.market_data import is_a_share_trading_session
# Streamlit caches imported helper modules across page reruns. Reload the chart
# module so this standalone page always uses the current index-chart renderer.
visualization = importlib.reload(visualization)
market_overview_data = importlib.reload(market_overview_data)
fetch_market_breadth = market_overview_data.fetch_market_breadth
fetch_market_indices = market_overview_data.fetch_market_indices


RANKING_CONFIG = {
    "change_pct": ("涨幅榜", "涨跌幅", 1.0, "%.2f%%"),
    "amount": ("成交额榜", "成交额（亿元）", 1e8, "%.2f"),
    "market_cap": ("市值榜", "总市值（亿元）", 1e8, "%.2f"),
    "pe_ttm": ("市盈率榜", "PE TTM", 1.0, "%.2f"),
}

MARKET_OVERVIEW_CACHE_VERSION = 4


@st.cache_data(ttl=25, show_spinner=False)
def load_a_share_market_snapshot(a_share_universe):
    return fetch_a_share_market_snapshot(flatten_a_share_universe(a_share_universe))


@st.cache_data(ttl=21600, show_spinner=False)
def load_a_share_latest_quarter_profit_ranking(a_share_universe, cache_version=1):
    return fetch_latest_quarter_net_profit_ranking(flatten_a_share_universe(a_share_universe))


@st.cache_data(ttl=600, show_spinner=False)
def load_recent_financial_news(hours=72):
    return fetch_recent_financial_news(hours=hours)


@st.cache_data(ttl=30, show_spinner=False)
def load_cn_market_overview(cache_version=MARKET_OVERVIEW_CACHE_VERSION):
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


@st.cache_data(ttl=600, show_spinner=False)
def load_kr_market_overview(cache_version=MARKET_OVERVIEW_CACHE_VERSION):
    return fetch_market_indices("KR")


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
    constituent = item.get("constituent_breadth")
    breadth_detail = (
        f'涨 <span class="constituent-up">{constituent["up"]}</span> '
        f'平 {constituent["flat"]} '
        f'跌 <span class="constituent-down">{constituent["down"]}</span>'
        if constituent else "暂不可用"
    )
    breadth_summary = (
        '<div class="index-breadth-summary">'
        '<small>成分股涨跌</small>'
        f'<b>{breadth_detail}</b>'
        '</div>'
        if market == "CN" else ""
    )

    return (
        f'<div class="index-card {direction_class}">'
        f'<div class="index-card-head"><strong>{name}</strong><span>{code}</span></div>'
        '<div class="index-quote-row">'
        '<div class="index-quote-left">'
        f'<div class="index-price">{item["price"]:,.2f}</div>'
        f'<div class="index-change">{arrow} {item["change"]:+.2f}&nbsp;&nbsp;{item["change_pct"]:+.2f}%</div>'
        '</div>'
        f'{breadth_summary}'
        '</div>'
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
    if breadth.get("fallback") == "watchlist":
        st.caption("东方财富全市场快照暂时不可用，以下为本地股票池统计（非全市场）。")
    elif breadth.get("stale"):
        st.caption("东方财富最新快照暂时不可用，以下为最近一次成功统计。")
    up, flat, down, total = (int(breadth.get(key, 0)) for key in ("up", "flat", "down", "total"))
    up_pct = up / total * 100 if total else 0
    flat_pct = flat / total * 100 if total else 0
    down_pct = down / total * 100 if total else 0
    market_class = "market-cn" if market in {"CN", "KR"} else "market-us"
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
    market_name = {"CN": "A股", "US": "美股", "KR": "韩股 KOSPI"}[market]
    overview_description = "核心指数与指数分时走势" if market == "KR" else "核心指数、成交额变化与全市场涨跌结构"
    hero_col, action_col = st.columns([5, 1])
    with hero_col:
        st.markdown(
            f'<div class="overview-hero"><span class="overview-eyebrow">MARKET PULSE</span><h1>{market_name}市场概览</h1><p>{overview_description}</p></div>',
            unsafe_allow_html=True,
        )
    if action_col.button("刷新数据", key=f"refresh-market-overview:{market}", width="stretch"):
        (load_cn_market_overview if market == "CN" else load_us_market_overview if market == "US" else load_kr_market_overview).clear()
    loader = load_cn_market_overview if market == "CN" else load_us_market_overview if market == "US" else load_kr_market_overview
    try:
        with st.spinner(f"正在更新{market_name}指数数据..."):
            loaded = loader(MARKET_OVERVIEW_CACHE_VERSION) if market == "CN" else loader()
            indices, breadth = loaded if market in {"CN", "US"} else (loaded, None)
    except Exception as error:
        indices, breadth = [], None if market == "KR" else {"error": f"市场广度暂时不可用：{error}"}

    st.markdown('<div class="section-title"><h3>核心指数</h3></div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="index-grid {"market-cn" if market in {"CN", "KR"} else "market-us"}">' + "".join(_index_card_html(item, market) for item in indices) + "</div>",
        unsafe_allow_html=True,
    )

    if breadth is not None:
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
    if market in {"US", "KR"} and not intraday.empty:
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
    """Render the market overview inside the main application."""
    load_styles("market_overview.css")
    st.markdown(
        '<div class="overview-brand"><strong>Stock Insight</strong><span>Market Overview</span></div>',
        unsafe_allow_html=True,
    )
    market_label = st.segmented_control(
        "市场",
        ["A股", "美股", "韩股 KOSPI"],
        default="A股",
        key="market-overview-page-market",
        width="stretch",
    )
    render_market_overview({"A股": "CN", "美股": "US", "韩股 KOSPI": "KR"}[market_label])
def _toggle_ranking_sort(metric: str, source_column: str) -> None:
    sort_key = f"a-share-ranking-sort:{metric}"
    current = st.session_state.get(sort_key)
    is_same_column = current and current["column"] == source_column
    st.session_state[sort_key] = {
        "column": source_column,
        "ascending": not current["ascending"] if is_same_column else True,
    }


def _render_ranking_table(snapshot, metric):
    title, metric_label, divisor, number_format = RANKING_CONFIG[metric]
    ranked = rank_snapshot(snapshot, metric).copy()
    sort_key = f"a-share-ranking-sort:{metric}"
    sort_state = st.session_state.get(sort_key)
    if sort_state:
        sort_column = sort_state["column"]
        if metric == "pe_ttm" and sort_column == "pe_ttm":
            pe_values = pd.to_numeric(ranked["pe_ttm"], errors="coerce")
            ranked = (
                ranked.assign(
                    _invalid_pe=pe_values.isna() | (pe_values <= 0),
                    _pe_sort_value=pe_values.where(pe_values > 0),
                )
                .sort_values(
                    by=["_invalid_pe", "_pe_sort_value"],
                    ascending=[True, sort_state["ascending"]],
                    kind="mergesort",
                    na_position="last",
                )
                .drop(columns=["_invalid_pe", "_pe_sort_value"])
            )
        else:
            ranked = ranked.sort_values(
                by=sort_column,
                ascending=sort_state["ascending"],
                kind="mergesort",
                na_position="last",
            )
    ranked[metric] = pd.to_numeric(ranked[metric], errors="coerce") / divisor
    display = ranked.reindex(columns=["rank", "name", "price", "industry", metric, "quote_time", "stale"]).rename(
        columns={"rank": "排名", "name": "股票", "price": "现价", "industry": "赛道", metric: metric_label, "quote_time": "数据时间", "stale": "状态"}
    )
    display["状态"] = display["状态"].map({True: "缓存", False: "实时"}).fillna("实时")
    column_widths = [0.65, 1.25, 1.15, 1.2, 1.1, 1.65, 0.7]
    headers = [
        ("rank", "排名"),
        ("name", "股票"),
        ("price", "现价"),
        ("industry", "赛道"),
        (metric, metric_label),
        ("quote_time", "数据时间"),
        ("stale", "状态"),
    ]
    st.markdown(
        """
        <style>
        [class*="st-key-a-share-ranking-table-"] { overflow-x: auto; }
        [class*="st-key-a-share-ranking-table-"] [data-testid="stHorizontalBlock"] { min-width: 780px; flex-wrap: nowrap; }
        [class*="st-key-a-share-ranking-table-"] [data-testid="stMarkdownContainer"] p { margin: 0; white-space: nowrap; }
        [class*="st-key-a-share-ranking-table-"] .stButton > button { min-height: 0; padding: .15rem 0; white-space: nowrap; }
        .ranking-price-up { color: #e53935; }
        .ranking-price-down { color: #1e9d55; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.container(height=560, border=True, key=f"a-share-ranking-table-{metric}"):
        header_columns = st.columns(column_widths, gap="small")
        for column, (source_column, label) in zip(header_columns, headers):
            is_active = sort_state and sort_state["column"] == source_column
            sort_arrow = " ↑" if is_active and sort_state["ascending"] else " ↓" if is_active else ""
            column.button(
                f"{label}{sort_arrow}",
                key=f"a-share-ranking-sort-button:{metric}:{source_column}",
                type="tertiary",
                on_click=_toggle_ranking_sort,
                args=(metric, source_column),
            )

        for row_index, row in enumerate(display.itertuples(index=False)):
            rank, name, price, industry, metric_value, quote_time, status = row
            ticker = str(ranked.iloc[row_index]["ticker"])
            formatted_metric = "—" if pd.isna(metric_value) else number_format % float(metric_value)
            formatted_price = "—" if pd.isna(price) else f"¥{float(price):.2f}"
            change_pct = pd.to_numeric(ranked.iloc[row_index].get("change_pct"), errors="coerce")
            price_class = (
                "ranking-price-up"
                if change_pct >= 0
                else "ranking-price-down" if change_pct < 0 else ""
            )
            columns = st.columns(column_widths, gap="small")
            columns[0].markdown(str(int(rank)) if pd.notna(rank) else "")
            selected = columns[1].button(
                str(name),
                key=f"a-share-ranking-stock:{metric}:{ticker}",
                type="tertiary",
            )
            if selected:
                st.session_state["pending_a_share_ticker"] = str(ticker)
                st.session_state["market_view_navigation"] = "个股分析"
                st.rerun(scope="app")
            columns[2].markdown(
                f'<span class="{price_class}">{formatted_price}</span>',
                unsafe_allow_html=True,
            )
            columns[3].markdown(str(industry))
            columns[4].markdown(formatted_metric)
            columns[5].markdown(str(quote_time))
            columns[6].markdown(str(status))
    st.caption(f"{title}覆盖股票池全部 {len(display)} 只股票。")


def _render_financial_ranking_table(financial_ranking):
    """Render the financial ranking with the same card-style rows as live rankings."""
    headers = ["排名", "股票", "赛道", "报告期", "最新季度净利润（亿元）", "净利润同比"]
    widths = [0.65, 1.25, 1.2, 1.2, 1.55, 1.15]
    with st.container(height=560, border=True, key="a-share-ranking-table-quarter-profit"):
        for column, label in zip(st.columns(widths, gap="small"), headers):
            column.markdown(f"**{label}**")
        for row in financial_ranking.itertuples(index=False):
            columns = st.columns(widths, gap="small")
            columns[0].markdown(str(row.排名))
            if columns[1].button(str(row.name), key=f"a-share-ranking-quarter-profit:{row.ticker}", type="tertiary"):
                st.session_state["pending_a_share_ticker"] = str(row.ticker)
                st.session_state["market_view_navigation"] = "个股分析"
                st.rerun(scope="app")
            columns[2].markdown(str(row.industry))
            columns[3].markdown(str(row.报告期 or "—"))
            profit = pd.to_numeric(row.最新季度净利润, errors="coerce")
            growth = pd.to_numeric(row.净利润同比, errors="coerce")
            columns[4].markdown("—" if pd.isna(profit) else f"{profit / 1e8:.2f}")
            color = "#e53935" if growth >= 0 else "#1e9d55"
            columns[5].markdown("—" if pd.isna(growth) else f"<span style='color:{color}'>{growth:+.2f}%</span>", unsafe_allow_html=True)


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
    tabs = st.tabs([*[config[0] for config in RANKING_CONFIG.values()], "最新季度净利润"])
    for tab, metric in zip(tabs, RANKING_CONFIG):
        with tab:
            _render_ranking_table(snapshot, metric)
    with tabs[-1]:
        with st.spinner("正在读取最新季度财报（优先使用本地缓存）..."):
            financial_ranking = load_a_share_latest_quarter_profit_ranking(a_share_universe)
        _render_financial_ranking_table(financial_ranking)
        st.caption("财报缓存 12 小时内复用；连续 30 天未访问的财报缓存会自动删除。")


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
