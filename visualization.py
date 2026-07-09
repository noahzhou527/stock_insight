"""
数据可视化模块
使用 Plotly 创建交互式图表
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd


def _trading_day_rangebreaks(index: pd.Index) -> list:
    """Hide weekends and missing weekday sessions from time-series charts."""
    dates = pd.DatetimeIndex(index).normalize()
    if dates.empty:
        return [dict(bounds=["sat", "mon"])]
    business_days = pd.bdate_range(dates.min(), dates.max())
    holidays = business_days.difference(dates)
    breaks = [dict(bounds=["sat", "mon"])]
    if not holidays.empty:
        breaks.append(dict(values=holidays.strftime("%Y-%m-%d").tolist()))
    return breaks


def plot_candlestick(
    df: pd.DataFrame,
    ma_periods: list = None,
    currency: str = "USD",
    market: str = "US",
) -> go.Figure:
    """绘制共享横轴的 K 线、均线和成交量组合图。"""
    is_a_share = market.upper() == "CN"
    up_color = "#e53935" if is_a_share else "#16a085"
    down_color = "#1e9d55" if is_a_share else "#e74c3c"
    volume_colors = [
        up_color if close >= open_ else down_color
        for open_, close in zip(df["Open"], df["Close"])
    ]
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.035,
        row_heights=[0.72, 0.28],
    )

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['Open'],
        high=df['High'],
        low=df['Low'],
        close=df['Close'],
        name='K线',
        increasing_line_color=up_color,
        increasing_fillcolor=up_color,
        decreasing_line_color=down_color,
        decreasing_fillcolor=down_color,
        whiskerwidth=0.35,
    ), row=1, col=1)

    colors = ['#f39c12', '#2864dc', '#8e44ad', '#34495e', '#d35400']
    if ma_periods:
        for i, period in enumerate(ma_periods):
            col_name = f'MA_{period}'
            if col_name in df.columns:
                fig.add_trace(go.Scatter(
                    x=df.index,
                    y=df[col_name],
                    name=f'MA {period}',
                    line=dict(color=colors[i % len(colors)], width=1.6),
                    hovertemplate=f"MA {period}: %{{y:.2f}}<extra></extra>",
                ), row=1, col=1)

    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df["Volume"],
            marker_color=volume_colors,
            marker_line_width=0,
            name="成交量",
            opacity=0.82,
            hovertemplate="成交量: %{y:,.0f}<extra></extra>",
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        title=dict(text="价格走势与成交量", x=0.01, xanchor="left"),
        template='plotly_white',
        height=720,
        xaxis_rangeslider_visible=False,
        hovermode='x unified',
        bargap=0.12,
        margin=dict(l=35, r=25, t=65, b=35),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="right",
            x=1,
        ),
        font=dict(family="Arial, Microsoft YaHei, sans-serif", color="#25324a"),
        plot_bgcolor="#fbfcfe",
        paper_bgcolor="white",
    )
    rangebreaks = _trading_day_rangebreaks(df.index)
    fig.update_xaxes(
        rangebreaks=rangebreaks,
        showgrid=True,
        gridcolor="#e9edf4",
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikedash="dot",
        spikecolor="#8a94a6",
    )
    fig.update_yaxes(
        title_text=f"价格 ({currency})",
        row=1,
        col=1,
        gridcolor="#e9edf4",
        tickformat=".2f",
    )
    fig.update_yaxes(
        title_text="成交量",
        row=2,
        col=1,
        gridcolor="#eef1f6",
        tickformat="~s",
    )

    return fig


def plot_intraday(df: pd.DataFrame, market: str = "CN") -> go.Figure:
    """绘制当日分时价格、均价、昨收线与分钟成交量。"""
    is_a_share = market.upper() == "CN"
    up_color = "#e53935" if is_a_share else "#16a085"
    down_color = "#1e9d55" if is_a_share else "#e74c3c"
    pre_close = float(df.attrs.get("pre_close", df["Price"].iloc[0]))
    volume_colors = [
        up_color if price >= pre_close else down_color
        for price in df["Price"]
    ]
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.035,
        row_heights=[0.72, 0.28],
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["Price"],
            mode="lines",
            name="成交价",
            line=dict(color="#2864dc", width=2),
            hovertemplate="%{x|%H:%M}<br>价格: %{y:.2f}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["AvgPrice"],
            mode="lines",
            name="均价",
            line=dict(color="#f39c12", width=1.5),
            hovertemplate="均价: %{y:.2f}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_hline(
        y=pre_close,
        line_dash="dash",
        line_color="#8a94a6",
        annotation_text=f"昨收 {pre_close:.2f}",
        annotation_position="top left",
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df["Volume"],
            name="分钟成交量",
            marker_color=volume_colors,
            marker_line_width=0,
            opacity=0.82,
            hovertemplate="成交量: %{y:,.0f}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    fig.update_layout(
        title=dict(text="当日分时", x=0.01, xanchor="left"),
        template="plotly_white",
        height=620,
        hovermode="x unified",
        margin=dict(l=35, r=25, t=65, b=35),
        legend=dict(orientation="h", y=1.01, x=1, xanchor="right"),
        font=dict(family="Arial, Microsoft YaHei, sans-serif", color="#25324a"),
        plot_bgcolor="#fbfcfe",
        paper_bgcolor="white",
        bargap=0.08,
    )
    fig.update_xaxes(
        rangebreaks=[
            dict(
                bounds=[11.5, 13],
                pattern="hour",
            )
        ],
        tickformat="%H:%M",
        gridcolor="#e9edf4",
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikedash="dot",
        spikecolor="#8a94a6",
    )
    fig.update_yaxes(title_text="价格 (CNY)", row=1, col=1, gridcolor="#e9edf4")
    fig.update_yaxes(
        title_text="成交量",
        row=2,
        col=1,
        gridcolor="#eef1f6",
        tickformat="~s",
    )
    return fig


def plot_rsi(df: pd.DataFrame, period: int) -> go.Figure:
    """
    绘制RSI指标图
    """
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['RSI'],
        name=f'RSI ({period})',
        line=dict(color='blue', width=2)
    ))

    # 添加超买超卖线
    fig.add_hline(y=70, line_dash="dash", line_color="red",
                  annotation_text="Overbought (70)")
    fig.add_hline(y=30, line_dash="dash", line_color="green",
                  annotation_text="Oversold (30)")
    fig.add_hline(y=50, line_dash="dot", line_color="gray", opacity=0.5)

    fig.update_layout(
        title=f'Relative Strength Index (RSI) - Period: {period}',
        yaxis_title='RSI Value',
        template='plotly_white',
        height=400,
        yaxis=dict(range=[0, 100])
    )
    fig.update_xaxes(rangebreaks=_trading_day_rangebreaks(df.index))

    return fig


def plot_macd(df: pd.DataFrame) -> go.Figure:
    """
    绘制MACD指标图
    """
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.1, row_heights=[0.7, 0.3])

    # 价格
    fig.add_trace(go.Scatter(
        x=df.index, y=df['Close'],
        name='Price', line=dict(color='black', width=1)
    ), row=1, col=1)

    # MACD
    fig.add_trace(go.Scatter(
        x=df.index, y=df['MACD'],
        name='MACD', line=dict(color='blue', width=2)
    ), row=2, col=1)

    # Signal
    fig.add_trace(go.Scatter(
        x=df.index, y=df['Signal'],
        name='Signal', line=dict(color='red', width=2)
    ), row=2, col=1)

    # Histogram
    colors = ['green' if val >= 0 else 'red' for val in df['Histogram']]
    fig.add_trace(go.Bar(
        x=df.index, y=df['Histogram'],
        name='Histogram', marker_color=colors
    ), row=2, col=1)

    fig.update_layout(
        title='MACD Indicator',
        template='plotly_white',
        height=600,
        showlegend=True
    )

    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="MACD", row=2, col=1)
    fig.update_xaxes(title_text="Date", row=2, col=1)
    fig.update_xaxes(rangebreaks=_trading_day_rangebreaks(df.index))

    return fig
