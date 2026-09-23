import streamlit as st
import pandas as pd
import numpy as np
import importlib
from types import SimpleNamespace
import visualization
import market_overviews

# 导入自定义模块
from data_fetcher import DataFetchError
import a_share_universe
from analysis import (
    calculate_bbi,
    calculate_bollinger_bands,
    calculate_ma,
    calculate_macd,
    calculate_rsi,
)
from indicator_help import render_indicator_help
from formatters import (
    format_amount,
    format_statistics,
    format_volume,
)
from new_listing import (
    get_new_listing_state,
)
from visualization import plot_candlestick, plot_intraday, plot_rsi, plot_macd
from app_config import VALUATION_CACHE_VERSION, configure_page, get_ths_access_token
from sidebar import render_sidebar
from styles import load_styles, render_boot_skeleton, render_dataframe
from services.market_data import (
    indicator_warmup_start,
    is_market_trading_session,
    load_data,
    load_chart_sessions,
    load_historical_data,
    load_intraday,
    load_krw_usd_rate,
    load_us_market_cap,
    load_valuation,
    trim_to_display_range,
)
from investment_insights_view import render_investment_insights
from financial_reports_view import render_financial_reports
from browser_state import sync_browser_state, save_browser_state

# Streamlit reruns the app in the same process, so refresh the separately
# maintained stock universe before building sidebar options.
importlib.reload(a_share_universe)
importlib.reload(visualization)
importlib.reload(market_overviews)
A_SHARE_UNIVERSE = a_share_universe.A_SHARE_UNIVERSE


# ============ 页面配置 ============
configure_page()
# 旧版 ?theme= 只控制 CSS，已由 Streamlit 顶栏的原生主题取代。
# 清掉旧参数，避免地址显示 dark 而用户实际选中 Light。
if "theme" in st.query_params:
    del st.query_params["theme"]
# 样式先于浏览器状态同步注入，让等待记忆的骨架也使用当前原生主题。
load_styles("dashboard.css")

# 同步记忆会 st.stop() 空转一轮。那一轮必须先铺一层骨架：不铺的话页面只剩
# 工具栏 + 主题底色，用户刷新时会看到一整屏空白页。
# 内容渲染出来后，骨架会被同位置的元素顶掉（它只在记忆未就绪时存在）。
if not st.session_state.get("_browser_state_ready"):
    render_boot_skeleton()

sync_browser_state()

# Keep conditional widgets alive across routes and early stops. Streamlit otherwise
# deletes their state when the sidebar/navigation is absent for one run.
for control_key in (
    "market_navigation", "market_view_navigation", "a_share_industry",
    "a_share_ticker", "a_share_watchlist_ticker", "kr_ticker", "us_ticker",
    "us_custom_ticker", "display_start", "display_end", "ma_periods",
    "show_bbi", "show_boll", "rsi_period",
):
    if control_key in st.session_state:
        st.session_state[control_key] = st.session_state[control_key]

# ============ 标题区域 ============
st.markdown(
    """
    <div class="app-hero">
        <div class="app-eyebrow">INVESTMENT WORKBENCH</div>
        <div class="app-hero-row">
            <div>
                <h1>Stock Insight</h1>
                <p>把行情、技术指标与基本面研究放在同一张工作台。</p>
            </div>
            <div class="app-hero-badge"><span></span> Live market workspace</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ============ 顶部导航 ============
market_label = None
a_share_view = None
with st.container(key="top_navigation"):
    st.markdown(
        '<div class="top-nav-heading"><span>工作区导航</span><span>市场 · 视图 · 分析模块</span></div>',
        unsafe_allow_html=True,
    )
    page = st.segmented_control(
        "主导航",
        ["行情分析", "市场总览", "指标说明", "新闻热点"],
        default="行情分析",
        key="page_navigation",
        label_visibility="collapsed",
        width="stretch",
    )
    if page == "行情分析":
        st.markdown('<div class="nav-context"></div>', unsafe_allow_html=True)
        market_nav, a_share_nav = st.columns([4, 5], gap="medium")
        with market_nav:
            st.markdown('<div class="nav-label">股票市场</div>', unsafe_allow_html=True)
            market_label = st.segmented_control(
                "股票市场",
                ["美股", "A股", "韩股"],
                default="A股",
                key="market_navigation",
                label_visibility="collapsed",
                width="stretch",
            )
        with a_share_nav:
            view_label = {"A股": "A股视图", "美股": "美股视图", "韩股": "韩股视图"}[market_label]
            view_options = ["个股分析", "我的自选", "股票池排行"] if market_label == "A股" else ["个股分析"]
            if (
                "market_view_navigation" not in st.session_state
                or st.session_state["market_view_navigation"] not in view_options
            ):
                st.session_state["market_view_navigation"] = "个股分析"
            st.markdown(f'<div class="nav-label">{view_label}</div>', unsafe_allow_html=True)
            a_share_view = st.segmented_control(
                view_label,
                view_options,
                key="market_view_navigation",
                label_visibility="collapsed",
                width="stretch",
            )

# 非行情页面在构建侧栏及请求市场数据前完成路由。
if page == "市场总览":
    save_browser_state()
    st.markdown("---")
    market_overviews.render_market_overview_page()
    st.stop()
if page == "指标说明":
    save_browser_state()
    st.markdown("---")
    render_indicator_help()
    st.stop()
if page == "新闻热点":
    save_browser_state()
    st.markdown("---")
    market_overviews.render_news_page()
    st.stop()
if market_label == "A股" and a_share_view == "股票池排行":
    save_browser_state()
    st.markdown("---")
    market_overviews.render_a_share_rankings(A_SHARE_UNIVERSE)
    st.stop()

# ============ 侧边栏控制面板 ============
market = {"A股": "CN", "美股": "US", "韩股": "KR"}[market_label]
ths_access_token = get_ths_access_token()
controls = render_sidebar(
    market,
    A_SHARE_UNIVERSE,
    a_share_watchlist=market_label == "A股" and a_share_view == "我的自选",
)
ticker = controls.ticker
start_date = controls.start_date
end_date = controls.end_date
ma_periods = controls.ma_periods
show_bbi = controls.show_bbi
show_boll = controls.show_boll
rsi_period = controls.rsi_period
save_browser_state()

if ticker is None:
    st.markdown("---")
    st.info("暂无自选股。")
    st.stop()


def fetch_intraday_snapshot(selected_ticker: str, selected_market: str):
    """抓取分时快照并记录抓取时刻，失败时返回异常供调用方提示。"""
    session_key = f"intraday:{selected_market}:{selected_ticker}"
    try:
        st.session_state[session_key] = load_intraday(selected_ticker, selected_market)
    except DataFetchError as error:
        return error
    st.session_state.pop(f"intraday-price-stale:{selected_market}:{selected_ticker}", None)
    st.session_state[f"intraday-refreshed-at:{selected_market}:{selected_ticker}"] = (
        pd.Timestamp.now().strftime("%H:%M:%S")
    )
    return None


def convert_krw_frame_to_usd(frame: pd.DataFrame, rate: float) -> pd.DataFrame:
    """Convert display-only Korean price and amount fields while preserving metadata."""
    result = frame.copy()
    for column in ("Open", "High", "Low", "Close", "Price", "AvgPrice", "Amount"):
        if column in result:
            result[column] = pd.to_numeric(result[column], errors="coerce") * rate
    result.attrs.update(frame.attrs)
    for attr in ("pre_close",):
        if result.attrs.get(attr) is not None:
            result.attrs[attr] = float(result.attrs[attr]) * rate
    return result


@st.fragment(run_every="30s" if is_market_trading_session(market) else None)
def render_intraday_panel(selected_ticker, selected_market, display_market=None):
    session_key = f"intraday:{selected_market}:{selected_ticker}"
    stamp_key = f"intraday-refreshed-at:{selected_market}:{selected_ticker}"
    display_market = display_market or selected_market

    metric_col, meta_col = st.columns([4, 7], vertical_alignment="top")
    with metric_col:
        volume_metric_label = st.segmented_control(
            "副图指标",
            ["成交量", "成交额"],
            default="成交量",
            key=f"intraday-volume-metric:{selected_market}:{selected_ticker}",
        )
    with meta_col:
        with st.container(key="intraday_refresh_btn"):
            manually_refreshed = st.button(
                "立即刷新",
                key=f"refresh-intraday:{selected_market}:{selected_ticker}",
                width="content",
            )

    # 保留旧快照直到新数据抓取成功；手动刷新和定时刷新每轮最多抓取一次。
    if manually_refreshed:
        load_intraday.clear()
    should_fetch = manually_refreshed or is_market_trading_session(selected_market) or session_key not in st.session_state
    if should_fetch:
        error = None
        if manually_refreshed:
            with st.spinner("正在刷新当日分时数据…"):
                error = fetch_intraday_snapshot(selected_ticker, selected_market)
        else:
            error = fetch_intraday_snapshot(selected_ticker, selected_market)
        if error is not None:
            if session_key in st.session_state:
                st.warning(f"刷新失败，仍显示上一次抓取的分时数据：{error}")
            else:
                st.warning(str(error))
        elif manually_refreshed:
            st.toast("当日分时已更新", icon="✅")

    live_metrics = compute_snapshot_metrics()
    render_snapshot_panel(snapshot_placeholder, live_metrics)
    intraday = st.session_state.get(session_key)
    if intraday is None or intraday.empty:
        st.info("暂时没有可显示的分时数据。")
        return

    if selected_market == "KR" and display_market == "US":
        intraday = convert_krw_frame_to_usd(intraday, live_metrics.intraday_currency_rate)

    st.plotly_chart(
        plot_intraday(
            intraday,
            market=display_market,
            volume_metric="amount" if volume_metric_label == "成交额" else "volume",
        ),
        width="stretch",
        key=f"intraday-chart:{selected_market}:{selected_ticker}",
    )

    try:
        bar_time = pd.Timestamp(intraday.index[-1]).strftime("%H:%M")
    except (TypeError, ValueError, IndexError):
        bar_time = "—"
    in_session = is_market_trading_session(selected_market)
    auto_hint = "交易时段每 30 秒自动刷新" if in_session else "非交易时段已停止自动刷新，可点「立即刷新」手动抓取"
    refreshed_at = st.session_state.get(stamp_key, "—")
    st.caption(f"分时数据截至 {bar_time} · 本地快照抓取于 {refreshed_at} · {auto_hint}")


loading_message = st.empty()


def data_source_label(source):
    """标题行角标用的数据来源文案；异常来源返回 None，那种情况仍走横幅提示。"""
    if source in {"同花顺", "同花顺 iFinD"}:
        return "数据来源：同花顺"
    if source == "Yahoo Finance":
        return "Data source: Yahoo Finance"
    return None


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
    live_name = indicator_history_df.attrs.get("symbol_name")
    if market == "CN" and live_name:
        a_share_live_names = dict(st.session_state.get("a_share_live_names", {}))
        if a_share_live_names.get(ticker) != live_name:
            a_share_live_names[ticker] = live_name
            st.session_state["a_share_live_names"] = a_share_live_names
            st.rerun()
    display_market = market
    krw_usd_rate = 1.0
    if market == "KR":
        currency_choice = st.segmented_control(
            "韩股显示币种",
            ["韩元", "美元"],
            default="韩元",
            key=f"kr-display-currency:{ticker}",
        )
        if currency_choice == "美元":
            try:
                krw_usd_rate = load_krw_usd_rate()
            except DataFetchError as error:
                st.warning(f"美元换算暂不可用，当前仍按韩元显示：{error}")
            else:
                display_market = "US"
                indicator_history_df = convert_krw_frame_to_usd(indicator_history_df, krw_usd_rate)
                df = convert_krw_frame_to_usd(df, krw_usd_rate)
                st.caption(f"已切换为美元显示 · 参考汇率：1 美元 = {1 / krw_usd_rate:,.2f} 韩元")

    with st.container(key="data_load_success"):
        st.success(f"成功加载 {ticker} 从 {start_date} 到 {end_date} 的数据")
    # 正常来源的出处并入「市场快照」标题行显示（见 render_snapshot_panel），
    # 这里只保留异常来源的横幅——缓存 / 演示数据是需要显眼警示的情况。
    if data_source == "同花顺本地缓存":
        st.warning("同花顺当前不可用，正在显示本地缓存数据。")
    elif data_source == "local cache":
        st.warning("Yahoo Finance 当前不可用，正在显示本地缓存数据。")
    elif data_source == "demo data":
        st.warning("Yahoo Finance 和备用数据源当前不可用，正在显示演示数据；请勿用于真实投资判断。")
    elif data_source_label(data_source) is None:
        st.info(f"Yahoo Finance 当前不可用，已自动切换到 {data_source}。")
    if indicator_history_df.attrs.get("includes_intraday_daily_bar"):
        st.markdown(
            '<div class="settlement-note-right">'
            '当日成交额由分时明细合成，可能因行情更新时点、精度与正式结算值略有偏差；'
            '盘后成交不重复累加，下一交易日以正式日线校准。'
            '</div>',
            unsafe_allow_html=True,
        )

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
# 用自带样式的分隔线替代 st.markdown("---")：默认 hr 上下各留近 1.5rem，
# 在顶部导航与「市场快照」之间堆出一段空白。
st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

def compute_snapshot_metrics():
    """从当前 df 与分时快照派生整套关键指标。

    抽成函数是为了让「立即刷新」能重算并就地重绘页面顶部的指标区，
    否则刷新只更新图表，数字卡片要等下一次交互重跑才同步。
    """
    new_listing = get_new_listing_state(df, rsi_period)
    # 从当前（刷新后可能的）日线 attrs 取来源，映射成标题行角标文案。
    source_label = data_source_label(indicator_history_df.attrs.get("source") or data_source)

    # A 股优先使用最新分时价，接口暂不可用时回退日线收盘价。
    latest_price = df['Close'].iloc[-1]
    intraday_currency_rate = krw_usd_rate
    has_previous_price = new_listing["previous_close"] is not None
    prev_price = new_listing["previous_close"] if has_previous_price else latest_price
    current_price_label = "当前价格"
    intraday_snapshot = None
    if market in {"CN", "US", "KR"}:
        intraday_session_key = f"intraday:{market}:{ticker}"
        price_stale = st.session_state.get(f"intraday-price-stale:{market}:{ticker}", False)
        if not price_stale:
            intraday_snapshot = st.session_state.get(intraday_session_key)
        if intraday_snapshot is None and not price_stale:
            try:
                intraday_snapshot = load_intraday(ticker, market)
                st.session_state[intraday_session_key] = intraday_snapshot
            except DataFetchError:
                intraday_snapshot = None
        if intraday_snapshot is not None and not intraday_snapshot.empty:
            latest_price = float(intraday_snapshot["Price"].iloc[-1])
            intraday_pre_close = intraday_snapshot.attrs.get("pre_close")
            if intraday_pre_close is not None and np.isfinite(intraday_pre_close) and intraday_pre_close > 0:
                prev_price = float(intraday_pre_close)
                has_previous_price = True
            current_price_label = "当前价格（分时）"
        else:
            current_price_label = "当前价格（最近收盘）"

    if market == "KR" and display_market == "US":
        # Some cached Yahoo intraday snapshots are already denominated in USD while
        # the corresponding daily bars remain in KRW.  Detect that representation
        # from the latest daily close and never convert the same quote twice.
        # df 上面已按美元口径换算过，这里还原回韩元原始口径再比对。
        raw_daily_close = float(pd.to_numeric(df["Close"], errors="coerce").dropna().iloc[-1])
        if krw_usd_rate:
            raw_daily_close /= krw_usd_rate
        intraday_is_already_usd = (
            intraday_snapshot is not None
            and not intraday_snapshot.empty
            and raw_daily_close > 0
            and np.isclose(latest_price / raw_daily_close, krw_usd_rate, rtol=0.12)
        )
        if intraday_snapshot is None or intraday_snapshot.empty:
            pass  # Daily prices and the new-listing reference were converted above.
        elif intraday_is_already_usd:
            intraday_currency_rate = 1.0
        else:
            latest_price *= krw_usd_rate
            prev_price *= krw_usd_rate

    price_change = latest_price - prev_price if has_previous_price else 0.0
    price_change_pct = (price_change / prev_price) * 100 if has_previous_price and prev_price else 0.0

    high_52w = df['High'].max()
    low_52w = df['Low'].min()
    volume_avg = df['Volume'].mean()
    daily_amount = (
        pd.to_numeric(df["Amount"], errors="coerce")
        if "Amount" in df.columns
        else pd.Series(np.nan, index=df.index)
    )
    max_daily_amount = daily_amount.max()
    max_daily_amount_date = (
        pd.Timestamp(daily_amount.idxmax()).strftime("%Y-%m-%d")
        if daily_amount.notna().any()
        else ""
    )
    volatility = df['Close'].pct_change().std() * np.sqrt(252) * 100
    volatility_label = f"{volatility:.1f}%" if new_listing["volatility_ready"] and np.isfinite(volatility) else "数据不足"
    currency_symbol = "¥" if display_market == "CN" else "₩" if display_market == "KR" else "$"
    if has_previous_price:
        price_change_sign = "+" if price_change >= 0 else "-"
        price_delta_label = (
            f"{price_change_sign}{currency_symbol}{abs(price_change):.2f} "
            f"({price_change_pct:+.2f}%)"
        )
    else:
        price_delta_label = "首日上市，暂无前收盘价"

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
        if market == "KR" and display_market == "US" and market_cap is not None:
            market_cap *= krw_usd_rate

    return SimpleNamespace(
        new_listing=new_listing,
        source_label=source_label,
        intraday_currency_rate=intraday_currency_rate,
        latest_price=latest_price,
        price_change_pct=price_change_pct,
        current_price_label=current_price_label,
        currency_symbol=currency_symbol,
        price_delta_label=price_delta_label,
        high_52w=high_52w,
        low_52w=low_52w,
        volume_avg=volume_avg,
        max_daily_amount=max_daily_amount,
        max_daily_amount_date=max_daily_amount_date,
        volatility=volatility,
        volatility_label=volatility_label,
        market_cap=market_cap,
        valuation=valuation,
        valuation_error=valuation_error,
    )


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
    if selected_market == "KR":
        if value >= 1e12:
            return f"₩{value / 1e12:.2f}万亿"
        if value >= 1e8:
            return f"₩{value / 1e8:.2f}亿"
        return f"₩{value:,.0f}"
    if value >= 1e12:
        return f"${value / 1e12:.2f}T"
    if value >= 1e9:
        return f"${value / 1e9:.2f}B"
    if value >= 1e6:
        return f"${value / 1e6:.2f}M"
    return f"${value:,.0f}"


def data_detail_column_config(index_label: str):
    """Keep the two data-detail tables compact and consistently right-aligned."""
    return {
        "_index": st.column_config.TextColumn(index_label, width=120, alignment="right"),
        "开盘价": st.column_config.NumberColumn(width=110, alignment="right"),
        "最高价": st.column_config.NumberColumn(width=110, alignment="right"),
        "最低价": st.column_config.NumberColumn(width=110, alignment="right"),
        "收盘价": st.column_config.NumberColumn(width=110, alignment="right"),
        "成交量": st.column_config.TextColumn(width=155, alignment="right"),
        "成交额": st.column_config.TextColumn(width=155, alignment="right"),
        "RSI（相对强弱指标）": st.column_config.NumberColumn(width=190, alignment="right"),
    }


def render_max_daily_amount_card(value: str, date: str):
    st.markdown(
        f'''<div class="compact-amount-card">
            <div class="compact-amount-label">区间单日最大成交额</div>
            <div class="compact-amount-value"><span class="compact-amount-number">{value}</span><span class="compact-amount-date">（{date}）</span></div>
        </div>''',
        unsafe_allow_html=True,
    )

def render_snapshot_panel(target, metrics):
    """把市场快照与估值概览画进 target（st.empty 占位符）。

    分时片段首次运行和后续刷新都写入同一占位符，避免指标与分时图不同步。
    """
    with target.container():
        source_badge = (
            f'<span class="metric-section-source">{metrics.source_label}</span>'
            if metrics.source_label
            else ""
        )
        st.markdown(
            '<div class="metric-section-heading">'
            '<div class="metric-section-title"><strong>市场快照</strong>'
            '<span>价格 · 成交 · 波动 · 规模</span></div>'
            f'{source_badge}'
            '</div>',
            unsafe_allow_html=True,
        )

        if market == "CN":
            price_columns = st.columns(3)
            with price_columns[0]:
                direction_class = "cn-price-up" if metrics.price_change_pct >= 0 else "cn-price-down"
                st.metric(
                    metrics.current_price_label,
                    f"{metrics.currency_symbol}{metrics.latest_price:.2f}",
                    metrics.price_delta_label,
                    delta_color="inverse",
                )
                st.markdown(
                    f'<span class="cn-price-direction {direction_class}"></span>',
                    unsafe_allow_html=True,
                )
            with price_columns[1]:
                st.metric("52周最高", f"{metrics.currency_symbol}{metrics.high_52w:.2f}")
            with price_columns[2]:
                st.metric("52周最低", f"{metrics.currency_symbol}{metrics.low_52w:.2f}")

            secondary_columns = st.columns(4)
            with secondary_columns[0]:
                st.metric("平均成交量", format_volume(metrics.volume_avg, display_market))
                st.markdown('<span class="secondary-metric-marker"></span>', unsafe_allow_html=True)
            with secondary_columns[1]:
                render_max_daily_amount_card(
                    format_amount(metrics.max_daily_amount, display_market),
                    metrics.max_daily_amount_date,
                )
            with secondary_columns[2]:
                st.metric("年化波动率", metrics.volatility_label)
                st.markdown('<span class="secondary-metric-marker"></span>', unsafe_allow_html=True)
            with secondary_columns[3]:
                st.metric("总市值", format_market_cap(metrics.market_cap, display_market))
                st.markdown('<span class="secondary-metric-marker"></span>', unsafe_allow_html=True)

            st.markdown("#### 估值概览")
            valuation_columns = st.columns(3)
            valuation_items = [
                ("市盈率 TTM", "pe_ttm"),
                ("静态市盈率", "pe_static"),
                ("动态市盈率", "pe_dynamic"),
            ]
            for column, (label, key) in zip(valuation_columns, valuation_items):
                value = metrics.valuation.get(key)
                with column:
                    st.metric(label, f"{value:.2f} 倍" if value is not None else "亏损 / 不适用")
            if metrics.valuation_error:
                st.caption(f"公开估值数据暂不可用：{metrics.valuation_error}")
            elif metrics.valuation.get("source"):
                valuation_source_note, valuation_profit_note = st.columns([1.45, 1], gap="large")
                with valuation_source_note:
                    st.caption(
                        f"估值数据来源：{metrics.valuation['source']} · {metrics.valuation.get('as_of', '')}"
                    )
                if metrics.valuation.get("ttm_net_profit") is not None:
                    with valuation_profit_note:
                        st.markdown(
                            '<div class="valuation-note-right">TTM 净利润（最近四个季度）：'
                            f"{format_amount(metrics.valuation['ttm_net_profit'], market)}</div>",
                            unsafe_allow_html=True,
                        )
        else:
            primary_metric_columns = st.columns(3)
            with primary_metric_columns[0]:
                st.metric(
                    metrics.current_price_label,
                    f"{metrics.currency_symbol}{metrics.latest_price:.2f}",
                    metrics.price_delta_label,
                    delta_color="normal",
                )
            with primary_metric_columns[1]:
                st.metric("52周最高", f"{metrics.currency_symbol}{metrics.high_52w:.2f}")
            with primary_metric_columns[2]:
                st.metric("52周最低", f"{metrics.currency_symbol}{metrics.low_52w:.2f}")

            secondary_metric_columns = st.columns(4)
            with secondary_metric_columns[0]:
                st.metric("平均成交量", format_volume(metrics.volume_avg, display_market))
                st.markdown('<span class="secondary-metric-marker"></span>', unsafe_allow_html=True)
            with secondary_metric_columns[1]:
                render_max_daily_amount_card(
                    format_amount(metrics.max_daily_amount, display_market),
                    metrics.max_daily_amount_date,
                )
            with secondary_metric_columns[2]:
                st.metric("年化波动率", metrics.volatility_label)
                st.markdown('<span class="secondary-metric-marker"></span>', unsafe_allow_html=True)
            with secondary_metric_columns[3]:
                st.metric("总市值", format_market_cap(metrics.market_cap, display_market))
                st.markdown('<span class="secondary-metric-marker"></span>', unsafe_allow_html=True)


# 分时片段负责首次绘制及后续更新；价格页刷新仍在当前整页运行里重算指标。
snapshot_placeholder = st.empty()
snapshot_metrics = compute_snapshot_metrics()
new_listing = snapshot_metrics.new_listing

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

history_rsi = calculate_rsi(indicator_history_df, rsi_period)
df['RSI'] = history_rsi.reindex(df.index)
df_macd = trim_to_display_range(calculate_macd(indicator_history_df), start_date, end_date)

# ============ Tab 1: 价格分析 ============
price_refresh_stamp_key = f"price-page-refreshed-at:{ticker}"
if price_refresh_stamp_key not in st.session_state:
    # 未手动刷新时的基线时点，避免说明行留空。
    st.session_state[price_refresh_stamp_key] = pd.Timestamp.now().strftime("%H:%M:%S")


def reload_daily_frames():
    """清掉日线与分时缓存后重抓，并按当前币种口径重建派生 DataFrame。"""
    load_historical_data.clear()
    load_intraday.clear()
    fresh_history = load_data(ticker, calculation_start_date, end_date, market, ths_access_token)
    fresh_df = trim_to_display_range(fresh_history, start_date, end_date)
    if market == "KR" and display_market == "US":
        fresh_history = convert_krw_frame_to_usd(fresh_history, krw_usd_rate)
        fresh_df = convert_krw_frame_to_usd(fresh_df, krw_usd_rate)
    return fresh_history, fresh_df


with tab1:
    st.subheader("K线图与成交量")
    metric_col, refresh_col = st.columns([5, 1], vertical_alignment="center")
    with metric_col:
        volume_metric_label = st.segmented_control(
            "副图指标",
            ["成交量", "成交额"],
            default="成交量",
            key="price_volume_metric",
        )
    with refresh_col:
        with st.container(key="price_refresh_btn"):
            refresh_price_page = st.button(
                "立即刷新",
                key=f"refresh-price-page:{ticker}",
                width="content",
            )

    # 就地重取：日线、分时与顶部指标区一起刷新，当轮立即可见，不走整页 rerun。
    if refresh_price_page:
        daily_error = None
        fresh_frames = None
        with st.spinner("正在刷新日线与分时数据…"):
            try:
                fresh_frames = reload_daily_frames()
            except DataFetchError as error:
                daily_error = error
            intraday_error = fetch_intraday_snapshot(ticker, market)
        if daily_error is not None:
            st.warning(f"刷新失败，仍显示上一次抓取的日线数据：{daily_error}")
        elif fresh_frames[1].empty:
            st.warning("刷新后没有取到新的日线数据，仍显示上一次的结果。")
        else:
            indicator_history_df, df = fresh_frames
            if intraday_error is not None:
                # Keep the old intraday chart, but never use its quote with fresh daily bars.
                st.session_state[f"intraday-price-stale:{market}:{ticker}"] = True
            df['RSI'] = calculate_rsi(indicator_history_df, rsi_period).reindex(df.index)
            df_macd = trim_to_display_range(calculate_macd(indicator_history_df), start_date, end_date)
            # 分时片段稍后会把新指标绘制到顶部占位符。
            snapshot_metrics = compute_snapshot_metrics()
            new_listing = snapshot_metrics.new_listing
            st.session_state[price_refresh_stamp_key] = pd.Timestamp.now().strftime("%H:%M:%S")
            if intraday_error is not None:
                st.toast("日线已更新，分时暂不可用；当前价格使用最近收盘价", icon="⚠️")
            else:
                st.toast("日线与分时数据已更新", icon="✅")
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
    chart_df = df_with_ma
    display_sessions = None
    if pd.Timestamp(indicator_history_df.index.min()) > pd.Timestamp(start_date):
        try:
            calendar = load_chart_sessions(start_date, end_date, market)
            display_sessions = len(calendar.union(pd.DatetimeIndex(chart_df.index).normalize()))
        except Exception:
            st.caption("交易日历暂不可用，当前按已有日 K 自适应显示。")
    fig = plot_candlestick(
        chart_df,
        ma_periods,
        currency="CNY" if display_market == "CN" else "KRW" if display_market == "KR" else "USD",
        market=display_market,
        show_bbi=show_bbi,
        show_boll=show_boll,
        volume_metric=volume_metric,
        display_sessions=display_sessions,
    )
    st.plotly_chart(fig, width="stretch")
    try:
        latest_bar_date = pd.Timestamp(indicator_history_df.index[-1]).strftime("%Y-%m-%d")
    except (TypeError, ValueError, IndexError):
        latest_bar_date = "—"
    st.caption(
        f"日线最新一根 {latest_bar_date} · 本地快照时点 "
        f"{st.session_state.get(price_refresh_stamp_key, '—')} · 点「立即刷新」重抓日线与分时"
    )

# ============ 当日分时 ============
with tab_intraday:
    render_intraday_panel(ticker, market, display_market)

# ============ Tab 2: 技术指标 ============
with tab2:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("RSI (相对强弱指标)")
        fig_rsi = plot_rsi(df, rsi_period)
        st.plotly_chart(fig_rsi, width="stretch")

        # RSI 解读
        latest_rsi = df['RSI'].iloc[-1]
        if not new_listing["rsi_ready"]:
            st.info(f"历史日 K 不足 {rsi_period + 1} 根，暂无法计算 RSI。")
        elif latest_rsi > 70:
            st.warning(f"⚠️ RSI = {latest_rsi:.1f} > 70，可能处于**超买**状态")
        elif latest_rsi < 30:
            st.success(f"✅ RSI = {latest_rsi:.1f} < 30，可能处于**超卖**状态")
        else:
            st.info(f"ℹ️ RSI = {latest_rsi:.1f}，处于中性区间")

    with col2:
        st.subheader("MACD (指数平滑异同平均线)")
        fig_macd = plot_macd(df_macd)
        st.plotly_chart(fig_macd, width="stretch")

        # MACD 解读
        latest_macd = df_macd['MACD'].iloc[-1]
        latest_signal = df_macd['Signal'].iloc[-1]
        if not new_listing["macd_ready"]:
            st.info("历史日 K 不足 26 根，暂不解读 MACD 信号。")
        elif latest_macd > latest_signal:
            st.success(f"✅ MACD ({latest_macd:.2f}) > Signal ({latest_signal:.2f})，**看涨信号**")
        else:
            st.warning(f"⚠️ MACD ({latest_macd:.2f}) < Signal ({latest_signal:.2f})，**看跌信号**")

# ============ Tab 3: 数据详情 ============
with tab3:
    st.subheader("原始数据")

    # 数据筛选
    col1, col2 = st.columns([1, 3])
    with col1:
        max_rows = min(100, len(df))
        rows_to_show = (
            st.slider("显示行数", 1, max_rows, min(20, max_rows))
            if new_listing["show_rows_slider"]
            else max_rows
        )

    # 显示数据
    display_df = df.tail(rows_to_show).copy()
    display_df.index = display_df.index.strftime('%Y-%m-%d')
    display_df = display_df.round(2)
    if "Volume" in display_df:
        display_df["Volume"] = display_df["Volume"].map(lambda value: format_volume(value, display_market))
    if "Amount" in display_df:
        display_df["Amount"] = display_df["Amount"].map(lambda value: format_amount(value, display_market))
    display_df.index.name = "日期"
    display_df = display_df.rename(
        columns={
            "Open": "开盘价",
            "High": "最高价",
            "Low": "最低价",
            "Close": "收盘价",
            "Volume": "成交量",
            "Amount": "成交额",
            "RSI": "RSI（相对强弱指标）",
        }
    )

    render_dataframe(
        display_df,
        width="stretch",
        column_config=data_detail_column_config("日期"),
    )

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
    st.caption(f"共 {len(df)} 个交易日")
    render_dataframe(
        format_statistics(df, display_market),
        width="stretch",
        column_config=data_detail_column_config("统计项"),
    )

# ============ Tab 4: 投资洞察 ============
with tab4:
    render_investment_insights(
        ticker,
        market,
        df,
        df_macd,
        new_listing,
        snapshot_metrics.volatility,
        A_SHARE_UNIVERSE,
    )

# ============ Tab 5: 财务报表 ============
with tab5:
    render_financial_reports(ticker, market, display_market, krw_usd_rate)

# ============ 页脚 ============
st.markdown("---")
st.markdown("""
<div class="app-footer">
    <p>Stock Insight | Personal market analysis dashboard | Data: Tonghuashun, Yahoo Finance, Eastmoney & Douyin</p>
</div>
""", unsafe_allow_html=True)
