"""
数据可视化模块
使用 Plotly 创建交互式图表
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd


CHART_BG = "#0d1422"
PLOT_BG = "#0a111e"
GRID_COLOR = "#1c293b"
TEXT_COLOR = "#cbd7e6"
MUTED_COLOR = "#7f90a8"


def _apply_dark_theme(fig: go.Figure) -> go.Figure:
    """Apply the dashboard's financial-terminal theme to a Plotly figure."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=CHART_BG,
        plot_bgcolor=PLOT_BG,
        font=dict(
            family='Inter, "Microsoft YaHei", Arial, sans-serif',
            color=TEXT_COLOR,
            size=12,
        ),
        title_font=dict(color="#e8f1fc", size=18),
        legend=dict(bgcolor="rgba(13, 20, 34, 0.72)", borderwidth=0),
        hoverlabel=dict(
            bgcolor="#111b2c",
            bordercolor="#26384f",
            font=dict(color="#e6edf7"),
        ),
    )
    fig.update_xaxes(
        gridcolor=GRID_COLOR,
        linecolor="#26384f",
        tickfont=dict(color=MUTED_COLOR),
        title_font=dict(color="#9fb0c6"),
        zerolinecolor="#26384f",
    )
    fig.update_yaxes(
        gridcolor=GRID_COLOR,
        linecolor="#26384f",
        tickfont=dict(color=MUTED_COLOR),
        title_font=dict(color="#9fb0c6"),
        zerolinecolor="#26384f",
    )
    return fig


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
    show_bbi: bool = False,
    show_boll: bool = False,
    volume_metric: str = "volume",
) -> go.Figure:
    """绘制共享横轴的 K 线、均线、BBI、BOLL 和成交量/成交额组合图。"""
    is_a_share = market.upper() == "CN"
    up_color = "#e53935" if is_a_share else "#16a085"
    down_color = "#1e9d55" if is_a_share else "#e74c3c"
    volume_colors = [
        up_color if close >= open_ else down_color
        for open_, close in zip(df["Open"], df["Close"])
    ]
    show_amount = volume_metric == "amount"
    amount = (
        pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
        if "Amount" in df.columns
        else df["Close"] * df["Volume"]
    )
    volume_y = amount if show_amount else df["Volume"]
    volume_label = f"成交额（{currency}）" if show_amount else "成交量"
    volume_hover = (
        f"成交额: {currency} %{{y:,.0f}}<extra></extra>"
        if show_amount
        else "成交量: %{y:,.0f}<extra></extra>"
    )
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

    colors = ['#fbbf24', '#22d3ee', '#a78bfa', '#60a5fa', '#f472b6']
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

    if show_boll and {"BB_Upper", "BB_Middle", "BB_Lower"}.issubset(df.columns):
        boll_lines = [
            ("BB_Upper", "BOLL 上轨", "#7b61ff", None),
            ("BB_Middle", "BOLL 中轨", "#64748b", "dot"),
            ("BB_Lower", "BOLL 下轨", "#7b61ff", None),
        ]
        for column, name, color, dash in boll_lines:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df[column],
                    name=name,
                    line=dict(color=color, width=1.25, dash=dash),
                    hovertemplate=f"{name}: %{{y:.2f}}<extra></extra>",
                ),
                row=1,
                col=1,
            )

    if show_bbi and "BBI" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["BBI"],
                name="BBI",
                line=dict(color="#e11d8a", width=2),
                hovertemplate="BBI: %{y:.2f}<extra></extra>",
            ),
            row=1,
            col=1,
        )

    fig.add_trace(
        go.Bar(
            x=df.index,
            y=volume_y,
            marker_color=volume_colors,
            marker_line_width=0,
            name=volume_label,
            opacity=0.82,
            hovertemplate=volume_hover,
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        title=dict(text=f"价格走势与{volume_label}", x=0.01, xanchor="left"),
        template='plotly_dark',
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
        font=dict(family="Arial, Microsoft YaHei, sans-serif", color=TEXT_COLOR),
        plot_bgcolor=PLOT_BG,
        paper_bgcolor=CHART_BG,
    )
    rangebreaks = _trading_day_rangebreaks(df.index)
    fig.update_xaxes(
        rangebreaks=rangebreaks,
        showgrid=True,
        gridcolor=GRID_COLOR,
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikedash="dot",
        spikecolor="#64748b",
    )
    fig.update_yaxes(
        title_text=f"价格 ({currency})",
        row=1,
        col=1,
        gridcolor=GRID_COLOR,
        tickformat=".2f",
    )
    fig.update_yaxes(
        title_text=volume_label,
        row=2,
        col=1,
        gridcolor=GRID_COLOR,
        tickformat="~s",
    )

    return _apply_dark_theme(fig)


def plot_intraday(
    df: pd.DataFrame,
    market: str = "CN",
    volume_metric: str = "volume",
) -> go.Figure:
    """绘制当日分时价格、均价、昨收线与分钟成交量。"""
    market = market.upper()
    is_a_share = market == "CN"
    currency = {"CN": "CNY", "US": "USD", "KR": "KRW"}.get(market, "USD")
    currency_symbol = {"CN": "¥", "US": "$", "KR": "₩"}.get(market, "$" )
    volume_unit = "股" if market == "CN" else "股"
    up_color = "#e53935" if is_a_share else "#16a085"
    down_color = "#1e9d55" if is_a_share else "#e74c3c"
    pre_close = float(df.attrs.get("pre_close", df["Price"].iloc[0]))
    price_change_pct = (df["Price"] / pre_close - 1) * 100
    amount = (
        pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
        if "Amount" in df.columns
        else df["Price"] * df["Volume"]
    )
    is_up_day = float(df["Price"].iloc[-1]) >= pre_close
    price_color = up_color if is_up_day else down_color
    price_fill = (
        "rgba(229, 57, 53, 0.10)"
        if is_up_day and is_a_share
        else "rgba(30, 157, 85, 0.10)"
        if is_a_share
        else "rgba(22, 160, 133, 0.10)"
        if is_up_day
        else "rgba(231, 76, 60, 0.10)"
    )
    high_index = price_change_pct.idxmax()
    low_index = price_change_pct.idxmin()
    high_pct = float(price_change_pct.loc[high_index])
    low_pct = float(price_change_pct.loc[low_index])
    volume_colors = [
        up_color if price >= pre_close else down_color
        for price in df["Price"]
    ]
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.09,
        row_heights=[0.70, 0.30],
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["Price"],
            mode="lines",
            name="成交价",
            line=dict(color=price_color, width=2),
            connectgaps=True,
            fill="tozeroy",
            fillcolor=price_fill,
            customdata=price_change_pct.round(2).to_numpy(),
            hovertemplate=(
                "%{x|%H:%M}<br>"
                f"价格: {currency_symbol}%{{y:.2f}}<br>"
                "涨跌幅: %{customdata:.2f}%<extra></extra>"
            ),
        ),
        row=1,
        col=1,
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["AvgPrice"],
            mode="lines",
            name="均价",
            line=dict(color="#f39c12", width=1.5),
            connectgaps=True,
            hovertemplate="均价: ¥%{y:.2f}<extra></extra>",
        ),
        row=1,
        col=1,
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=price_change_pct,
            mode="lines",
            line=dict(width=0),
            opacity=0,
            showlegend=False,
            hoverinfo="skip",
        ),
        row=1,
        col=1,
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            x=[high_index],
            y=[df.loc[high_index, "Price"]],
            mode="markers+text",
            marker=dict(color=up_color, size=8),
            text=[f"最高 {high_pct:+.2f}%"],
            textposition="top center",
            textfont=dict(color=up_color, size=12),
            showlegend=False,
            hovertemplate=(
                f"日内最高: ¥%{{y:.2f}}<br>涨跌幅: {high_pct:+.2f}%"
                "<extra></extra>"
            ),
        ),
        row=1,
        col=1,
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=[low_index],
            y=[df.loc[low_index, "Price"]],
            mode="markers+text",
            marker=dict(color=down_color, size=8),
            text=[f"最低 {low_pct:+.2f}%"],
            textposition="bottom center",
            textfont=dict(color=down_color, size=12),
            showlegend=False,
            hovertemplate=(
                f"日内最低: ¥%{{y:.2f}}<br>涨跌幅: {low_pct:+.2f}%"
                "<extra></extra>"
            ),
        ),
        row=1,
        col=1,
        secondary_y=False,
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
            name=f"成交量（{volume_unit}）",
            marker_color=volume_colors,
            marker_line_width=0,
            opacity=0.82,
            visible=volume_metric == "volume",
            showlegend=False,
            hovertemplate=f"成交量: %{{y:,.0f}} {volume_unit}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=amount,
            name=f"成交额（{currency}）",
            marker_color=volume_colors,
            marker_line_width=0,
            opacity=0.82,
            visible=volume_metric == "amount",
            showlegend=False,
            hovertemplate=f"成交额: {currency_symbol}%{{y:,.0f}}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    price_min = min(float(df["Price"].min()), pre_close)
    price_max = max(float(df["Price"].max()), pre_close)
    price_padding = max((price_max - price_min) * 0.08, abs(pre_close) * 0.002)
    price_range = [price_min - price_padding, price_max + price_padding]
    pct_range = [
        (price_range[0] / pre_close - 1) * 100,
        (price_range[1] / pre_close - 1) * 100,
    ]
    fig.update_layout(
        title=dict(text="当日分时", x=0.01, xanchor="left"),
        template="plotly_dark",
        height=620,
        hovermode="x unified",
        margin=dict(l=35, r=25, t=95, b=35),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.08,
            x=1,
            xanchor="right",
        ),
        font=dict(family="Arial, Microsoft YaHei, sans-serif", color=TEXT_COLOR),
        plot_bgcolor=PLOT_BG,
        paper_bgcolor=CHART_BG,
        bargap=0.08,
    )
    rangebreaks = []
    if market == "CN":
        rangebreaks.append(dict(bounds=[11.5, 13], pattern="hour"))
    fig.update_xaxes(
        rangebreaks=rangebreaks,
        tickformat="%H:%M",
        gridcolor=GRID_COLOR,
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikedash="dot",
        spikecolor="#64748b",
    )
    fig.update_yaxes(
        title_text=f"价格（{currency}）",
        range=price_range,
        row=1,
        col=1,
        secondary_y=False,
        gridcolor=GRID_COLOR,
    )
    fig.update_yaxes(
        title_text="涨跌幅（%）",
        range=pct_range,
        ticksuffix="%",
        tickformat="+.2f",
        row=1,
        col=1,
        secondary_y=True,
        showgrid=False,
    )
    fig.update_yaxes(
        title_text=(f"成交额（{currency}）" if volume_metric == "amount" else "成交量"),
        row=2,
        col=1,
        gridcolor=GRID_COLOR,
        tickformat="~s",
    )
    return _apply_dark_theme(fig)


def plot_index_intraday(
    frame: pd.DataFrame,
    name: str,
    previous_close: float,
    market: str = "CN",
) -> go.Figure:
    """Render a traditional market-terminal intraday chart around prior close."""
    prices = pd.to_numeric(frame["Price"], errors="coerce")
    plotted_values = [prices]
    average_prices = None
    if "AvgPrice" in frame.columns:
        average_prices = pd.to_numeric(frame["AvgPrice"], errors="coerce")
        if average_prices.notna().any():
            plotted_values.append(average_prices)
    deviation = max((series - previous_close).abs().max() for series in plotted_values)
    price_padding = max(float(deviation) * 1.15, abs(previous_close) * 0.0015)
    price_range = [previous_close - price_padding, previous_close + price_padding]
    tick_count = 7
    price_ticks = [
        price_range[0] + (price_range[1] - price_range[0]) * index / (tick_count - 1)
        for index in range(tick_count)
    ]
    percentage_ticks = [
        f"{(price / previous_close - 1) * 100:+.2f}%" for price in price_ticks
    ]
    price_tick_labels = [f"{price:,.2f}" for price in price_ticks]
    high, low = float(prices.max()), float(prices.min())
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=frame.index,
            y=prices,
            mode="lines",
            name=name,
            line=dict(color="#1677ff", width=2),
            connectgaps=True,
            customdata=((prices / previous_close - 1) * 100).round(2).to_numpy(),
            hovertemplate="%{x|%H:%M}<br>点位：%{y:.2f}<br>涨跌幅：%{customdata:+.2f}%<extra></extra>",
        ),
    )
    fig.add_trace(
        go.Scatter(
            x=frame.index,
            y=prices,
            yaxis="y2",
            mode="lines",
            line=dict(width=0),
            opacity=0,
            hoverinfo="skip",
            showlegend=False,
        )
    )
    if average_prices is not None and average_prices.notna().any():
        fig.add_trace(
            go.Scatter(
                x=frame.index,
                y=average_prices,
                mode="lines",
                name="均价",
                line=dict(color="#f5c542", width=1.8),
                connectgaps=True,
                hovertemplate="%{x|%H:%M}<br>均价：%{y:.2f}<extra></extra>",
            )
        )
    fig.add_hline(y=high, line_dash="dash", line_color="#d0d0d0", line_width=1, annotation_text=f"最高 {high:.2f}", annotation_font_color="#e53935", annotation_position="top left")
    fig.add_hline(y=previous_close, line_dash="dash", line_color="#8a94a6", line_width=1.5, annotation_text=f"昨收 {previous_close:.2f} · 0%", annotation_position="top left")
    fig.add_hline(y=low, line_dash="dash", line_color="#d0d0d0", line_width=1, annotation_text=f"最低 {low:.2f}", annotation_font_color="#1e9d55", annotation_position="bottom left")
    fig.update_layout(
        title=dict(text=f"{name} 分时", x=0.01),
        height=430,
        margin=dict(l=35, r=80, t=75, b=35),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.10, x=1, xanchor="right"),
        yaxis2=dict(
            title="涨跌幅",
            overlaying="y",
            side="right",
            range=price_range,
            tickmode="array",
            tickvals=price_ticks,
            ticktext=percentage_ticks,
            showgrid=False,
            zeroline=False,
        ),
        yaxis=dict(
            title="指数点位",
            range=price_range,
            tickmode="array",
            tickvals=price_ticks,
            ticktext=price_tick_labels,
        ),
    )
    fig.update_xaxes(
        tickformat="%H:%M",
        rangebreaks=[dict(bounds=[11.5, 13], pattern="hour")] if market == "CN" else [],
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikedash="dot",
        spikecolor="#64748b",
    )
    return _apply_dark_theme(fig)


def plot_rsi(df: pd.DataFrame, period: int) -> go.Figure:
    """
    绘制RSI指标图
    """
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['RSI'],
        name=f'RSI ({period})',
        line=dict(color='#22d3ee', width=2)
    ))

    # 添加超买超卖线
    fig.add_hline(y=70, line_dash="dash", line_color="#fb7185",
                  annotation_text="Overbought (70)")
    fig.add_hline(y=30, line_dash="dash", line_color="#2dd4bf",
                  annotation_text="Oversold (30)")
    fig.add_hline(y=50, line_dash="dot", line_color="gray", opacity=0.5)

    fig.update_layout(
        title=f'Relative Strength Index (RSI) - Period: {period}',
        yaxis_title='RSI Value',
        template='plotly_dark',
        height=400,
        yaxis=dict(range=[0, 100])
    )
    fig.update_xaxes(rangebreaks=_trading_day_rangebreaks(df.index))

    return _apply_dark_theme(fig)


def plot_macd(df: pd.DataFrame) -> go.Figure:
    """
    绘制MACD指标图
    """
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.1, row_heights=[0.7, 0.3])

    # 价格
    fig.add_trace(go.Scatter(
        x=df.index, y=df['Close'],
        name='Price', line=dict(color='#cbd7e6', width=1.4)
    ), row=1, col=1)

    # MACD
    fig.add_trace(go.Scatter(
        x=df.index, y=df['MACD'],
        name='MACD', line=dict(color='#22d3ee', width=2)
    ), row=2, col=1)

    # Signal
    fig.add_trace(go.Scatter(
        x=df.index, y=df['Signal'],
        name='Signal', line=dict(color='#fbbf24', width=2)
    ), row=2, col=1)

    # Histogram
    colors = ['#2dd4bf' if val >= 0 else '#fb7185' for val in df['Histogram']]
    fig.add_trace(go.Bar(
        x=df.index, y=df['Histogram'],
        name='Histogram', marker_color=colors
    ), row=2, col=1)

    fig.update_layout(
        title='MACD Indicator',
        template='plotly_dark',
        height=600,
        showlegend=True
    )

    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="MACD", row=2, col=1)
    fig.update_xaxes(title_text="Date", row=2, col=1)
    fig.update_xaxes(rangebreaks=_trading_day_rangebreaks(df.index))

    return _apply_dark_theme(fig)
