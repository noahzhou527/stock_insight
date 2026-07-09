import streamlit as st
import pandas as pd
import numpy as np
import os
import importlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# 导入自定义模块
from data_fetcher import (
    DataFetchError,
    fetch_a_share_financial_reports,
    fetch_a_share_intraday,
    fetch_a_share_valuation,
    fetch_stock_data,
)
import a_share_universe
from analysis import calculate_ma, calculate_rsi, calculate_macd
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
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 20px;
        font-weight: 600;
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
        border: 1px solid #e1e5eb;
        border-radius: 0.8rem;
        background: #fafbfc;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 0.8rem;
    }
    .pe-formula-title {
        color: #5c6675;
        font-size: 0.9rem;
        font-weight: 600;
    }
    .pe-formula {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.55rem;
        color: #2f3542;
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
    @media (max-width: 900px) {
        .pe-formula-grid {
            grid-template-columns: 1fr;
        }
        .pe-formula-card {
            min-height: 7.5rem;
        }
    }
</style>
""", unsafe_allow_html=True)

# ============ 标题区域 ============
st.markdown('<div class="main-header">Stock Insight</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Interactive Financial Data Analysis Dashboard</div>', unsafe_allow_html=True)

# ============ 侧边栏控制面板 ============
st.sidebar.header("分析参数设置")

# 股票市场与标的选择
market_label = st.sidebar.radio(
    "股票市场",
    ["美股", "中国 A 股"],
    horizontal=True,
)
market = "CN" if market_label == "中国 A 股" else "US"
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

ma_periods = st.sidebar.multiselect(
    "移动平均线周期",
    options=[5, 10, 20, 50, 100, 200],
    default=[20, 50]
)

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


@st.cache_data(ttl=3600, show_spinner=False)
def load_valuation(ticker):
    return fetch_a_share_valuation(ticker)


@st.cache_data(ttl=21600, show_spinner=False)
def load_financial_reports(ticker):
    return fetch_a_share_financial_reports(ticker)


@st.cache_data(ttl=25, show_spinner=False)
def load_intraday(ticker):
    return fetch_a_share_intraday(ticker)


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
    df = load_data(ticker, start_date, end_date, market, ths_access_token)
    loading_message.empty()

    if df.empty:
        st.error(f"无法获取 {ticker} 的数据，请检查股票代码是否正确。")
        st.stop()

    data_source = df.attrs.get("source", "Yahoo Finance")
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

# 计算关键指标
latest_price = df['Close'].iloc[-1]
prev_price = df['Close'].iloc[-2]
price_change = latest_price - prev_price
price_change_pct = (price_change / prev_price) * 100

high_52w = df['High'].max()
low_52w = df['Low'].min()
volume_avg = df['Volume'].mean()
volatility = df['Close'].pct_change().std() * np.sqrt(252) * 100
currency_symbol = "¥" if market == "CN" else "$"

valuation = {
    "pe_ttm": None,
    "pe_static": None,
    "pe_dynamic": None,
    "source": None,
}
valuation_error = None
if market == "CN":
    try:
        valuation = load_valuation(ticker)
    except Exception as error:
        valuation_error = str(error)

if market == "CN":
    price_columns = st.columns(3)
    with price_columns[0]:
        st.metric(
            "当前价格",
            f"{currency_symbol}{latest_price:.2f}",
            f"{price_change_pct:.2f}%",
        )
    with price_columns[1]:
        st.metric("52周最高", f"{currency_symbol}{high_52w:.2f}")
    with price_columns[2]:
        st.metric("52周最低", f"{currency_symbol}{low_52w:.2f}")

    secondary_columns = st.columns(2)
    with secondary_columns[0]:
        st.metric("平均成交量", f"{volume_avg / 1e6:.1f}M")
    with secondary_columns[1]:
        st.metric("年化波动率", f"{volatility:.1f}%")

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
    metric_columns = st.columns(5)
    with metric_columns[0]:
        st.metric(
            "当前价格",
            f"{currency_symbol}{latest_price:.2f}",
            f"{price_change_pct:.2f}%",
        )
    with metric_columns[1]:
        st.metric("52周最高", f"{currency_symbol}{high_52w:.2f}")
    with metric_columns[2]:
        st.metric("52周最低", f"{currency_symbol}{low_52w:.2f}")
    with metric_columns[3]:
        st.metric("平均成交量", f"{volume_avg / 1e6:.1f}M")
    with metric_columns[4]:
        st.metric("年化波动率", f"{volatility:.1f}%")

# ============ 主内容区域 ============
tab1, tab_intraday, tab2, tab3, tab4, tab5, tab_help = st.tabs(
    [
        "价格分析",
        "当日分时",
        "技术指标",
        "数据详情",
        "投资洞察",
        "财务报表",
        "指标说明",
    ]
)

# ============ Tab 1: 价格分析 ============
with tab1:
    st.subheader("K线图与成交量")

    # 计算移动平均线
    df_with_ma = df.copy()
    for period in ma_periods:
        df_with_ma[f'MA_{period}'] = calculate_ma(df_with_ma, period)

    # 绘制K线图
    fig = plot_candlestick(
        df_with_ma,
        ma_periods,
        currency="CNY" if market == "CN" else "USD",
        market=market,
    )
    st.plotly_chart(fig, width="stretch")

# ============ 当日分时 ============
with tab_intraday:
    if market == "CN":
        render_intraday_panel(ticker)
    else:
        st.info("当日分时图目前用于中国 A 股。")

# ============ Tab 2: 技术指标 ============
with tab2:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("RSI (相对强弱指标)")
        df['RSI'] = calculate_rsi(df, rsi_period)
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
        df_macd = calculate_macd(df)
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
        st.info("财务报表视图目前用于中国 A 股。")
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
                st.dataframe(
                    annual_reports,
                    width="stretch",
                    hide_index=True,
                )

            st.markdown("#### 最新财年已披露季报")
            if quarter_reports.empty:
                st.info("最新财年尚未披露季报。")
            else:
                st.dataframe(
                    quarter_reports,
                    width="stretch",
                    hide_index=True,
                )
        except DataFetchError as error:
            st.warning(str(error))

# ============ 指标说明 ============
with tab_help:
    st.subheader("指标说明与计算方法")
    st.caption("以下内容用于理解数据口径，不构成投资建议。")

    with st.expander("价格、52 周高低点与成交量", expanded=True):
        st.markdown(
            """
            - **当前价格**：所选日期范围内最后一个交易日的收盘价。
            - **52 周最高/最低**：当前页面所加载区间内的最高价和最低价；
              默认选择一年时可近似理解为 52 周区间。
            - **成交量**：交易期内成交的股票数量。放量上涨、放量下跌需要结合
              趋势位置判断，成交量本身不直接代表买入或卖出信号。
            """
        )

    with st.expander("移动平均线（MA）"):
        st.latex(r"MA_n = \frac{P_1 + P_2 + \cdots + P_n}{n}")
        st.markdown(
            """
            MA 是最近 n 个交易日收盘价的算术平均值，用于平滑短期波动和观察趋势。
            短期均线上穿长期均线通常称为“金叉”，反之称为“死叉”，但震荡行情中
            容易产生反复的滞后信号。
            """
        )

    with st.expander("RSI（相对强弱指标）"):
        st.latex(r"RSI = 100 - \frac{100}{1 + RS}")
        st.markdown(
            """
            RS 为指定周期内平均上涨幅度与平均下跌幅度之比。RSI 高于 70 常被视为
            超买，低于 30 常被视为超卖；强趋势中 RSI 可能长时间停留在极端区间。
            """
        )

    with st.expander("MACD（指数平滑异同平均线）"):
        st.latex(r"MACD = EMA_{12} - EMA_{26}")
        st.latex(r"Signal = EMA_9(MACD)")
        st.markdown(
            """
            MACD 衡量短期与长期指数移动平均线的差异。MACD 上穿 Signal 常被称为
            金叉，下穿称为死叉。它适合观察趋势和动量，但同样具有滞后性。
            """
        )

    with st.expander("年化波动率"):
        st.latex(r"\sigma_{annual} = Std(日收益率) \times \sqrt{252}")
        st.markdown(
            """
            年化波动率描述价格变化幅度，不区分上涨和下跌。数值越高通常意味着价格
            不确定性越大；它不是收益率，也不能单独用于判断股票是否值得投资。
            """
        )

    with st.expander("市盈率 TTM、静态市盈率与动态市盈率", expanded=True):
        st.markdown(
            """
            <div class="pe-formula-grid">
                <div class="pe-formula-card">
                    <div class="pe-formula-title">TTM 市盈率</div>
                    <div class="pe-formula">
                        <span>PE<sub>TTM</sub></span><span>=</span>
                        <span class="pe-fraction">
                            <span>当前总市值</span>
                            <span>最近四个季度净利润</span>
                        </span>
                    </div>
                </div>
                <div class="pe-formula-card">
                    <div class="pe-formula-title">静态市盈率</div>
                    <div class="pe-formula">
                        <span>PE<sub>静态</sub></span><span>=</span>
                        <span class="pe-fraction">
                            <span>当前总市值</span>
                            <span>最近完整财年净利润</span>
                        </span>
                    </div>
                </div>
                <div class="pe-formula-card">
                    <div class="pe-formula-title">动态市盈率</div>
                    <div class="pe-formula">
                        <span>PE<sub>动态</sub></span><span>=</span>
                        <span class="pe-fraction">
                            <span>当前总市值</span>
                            <span>当前报告期年化净利润</span>
                        </span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            - **TTM 市盈率**使用滚动十二个月利润，通常最接近公司当前盈利状态。
            - **静态市盈率**使用最近完整年报利润，口径稳定但可能滞后。
            - **动态市盈率**把当前累计利润年化：一季报 ×4、中报 ×2、
              三季报 ×4/3；季节性明显的企业可能失真。
            - 市盈率应优先与同一行业、相近商业模式和相近成长阶段的公司比较。
              净利润为零或亏损时，市盈率没有经济意义，页面显示“亏损 / 不适用”。
            """
        )

# ============ 页脚 ============
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.9rem;">
    <p>Stock Insight | Personal market analysis dashboard | Data: Tonghuashun & Yahoo Finance</p>
</div>
""", unsafe_allow_html=True)
