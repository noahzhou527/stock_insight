"""
数据可视化模块
使用 Plotly 创建交互式图表
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd


def plot_candlestick(df: pd.DataFrame, ma_periods: list = None) -> go.Figure:
    """
    绘制K线图（蜡烛图）与移动平均线
    """
    fig = go.Figure()

    # K线
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['Open'],
        high=df['High'],
        low=df['Low'],
        close=df['Close'],
        name='OHLC',
        increasing_line_color='#26a69a',
        decreasing_line_color='#ef5350'
    ))

    # 移动平均线
    colors = ['orange', 'blue', 'purple', 'red']
    if ma_periods:
        for i, period in enumerate(ma_periods):
            col_name = f'MA_{period}'
            if col_name in df.columns:
                fig.add_trace(go.Scatter(
                    x=df.index,
                    y=df[col_name],
                    name=f'MA {period}',
                    line=dict(color=colors[i % len(colors)], width=1.5)
                ))

    fig.update_layout(
        title='Stock Price Chart',
        yaxis_title='Price (USD)',
        xaxis_title='Date',
        template='plotly_white',
        height=600,
        xaxis_rangeslider_visible=False,
        hovermode='x unified'
    )

    return fig


def plot_volume(df: pd.DataFrame) -> go.Figure:
    """
    绘制成交量柱状图
    """
    colors = ['#26a69a' if df['Close'].iloc[i] >= df['Open'].iloc[i]
              else '#ef5350' for i in range(len(df))]

    fig = go.Figure(data=[
        go.Bar(
            x=df.index,
            y=df['Volume'],
            marker_color=colors,
            name='Volume'
        )
    ])

    fig.update_layout(
        title='Trading Volume',
        yaxis_title='Volume',
        template='plotly_white',
        height=300,
        showlegend=False
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

    return fig