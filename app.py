import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 导入自定义模块
from data_fetcher import DataFetchError, fetch_stock_data, get_sp500_tickers
from analysis import calculate_ma, calculate_rsi, calculate_macd
from visualization import plot_candlestick, plot_volume, plot_rsi, plot_macd

# ============ 页面配置 ============
st.set_page_config(
    page_title="StockInsight Pro",
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
</style>
""", unsafe_allow_html=True)

# ============ 标题区域 ============
st.markdown('<div class="main-header">StockInsight Pro</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Interactive Financial Data Analysis Dashboard</div>', unsafe_allow_html=True)

# ============ 侧边栏控制面板 ============
st.sidebar.header("分析参数设置")

# 股票选择
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
    "Custom Input": "CUSTOM"
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
def load_data(ticker, start, end):
    """缓存数据获取函数"""
    return fetch_stock_data(ticker, start, end)


loading_message = st.empty()

try:
    loading_message.info(f"正在获取 {ticker} 数据...")
    df = load_data(ticker, start_date, end_date)
    loading_message.empty()

    if df.empty:
        st.error(f"无法获取 {ticker} 的数据，请检查股票代码是否正确。")
        st.stop()

    data_source = df.attrs.get("source", "Yahoo Finance")
    st.success(f"成功加载 {ticker} 从 {start_date} 到 {end_date} 的数据")
    if data_source == "Yahoo Finance":
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

# 显示指标卡片
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric(
        label="当前价格",
        value=f"${latest_price:.2f}",
        delta=f"{price_change_pct:.2f}%"
    )

with col2:
    st.metric("52周最高", f"${high_52w:.2f}")

with col3:
    st.metric("52周最低", f"${low_52w:.2f}")

with col4:
    st.metric("平均成交量", f"{volume_avg / 1e6:.1f}M")

with col5:
    volatility = df['Close'].pct_change().std() * np.sqrt(252) * 100
    st.metric("年化波动率", f"{volatility:.1f}%")

# ============ 主内容区域 ============
tab1, tab2, tab3, tab4 = st.tabs(["价格分析", "技术指标", "数据详情", "投资洞察"])

# ============ Tab 1: 价格分析 ============
with tab1:
    st.subheader("K线图与成交量")

    # 计算移动平均线
    df_with_ma = df.copy()
    for period in ma_periods:
        df_with_ma[f'MA_{period}'] = calculate_ma(df_with_ma, period)

    # 绘制K线图
    fig = plot_candlestick(df_with_ma, ma_periods)
    st.plotly_chart(fig, use_container_width=True)

    # 成交量图
    st.subheader("成交量分析")
    fig_volume = plot_volume(df)
    st.plotly_chart(fig_volume, use_container_width=True)

# ============ Tab 2: 技术指标 ============
with tab2:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("RSI (相对强弱指标)")
        df['RSI'] = calculate_rsi(df, rsi_period)
        fig_rsi = plot_rsi(df, rsi_period)
        st.plotly_chart(fig_rsi, use_container_width=True)

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
        st.plotly_chart(fig_macd, use_container_width=True)

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

    st.dataframe(display_df, use_container_width=True)

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

# ============ 页脚 ============
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.9rem;">
    <p>StockInsight Pro | Personal market analysis dashboard | Data source: Yahoo Finance</p>
</div>
""", unsafe_allow_html=True)
