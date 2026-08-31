"""
数据可视化模块
使用 Plotly 创建交互式图表
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import re

from formatters import chart_unit, format_amount, format_volume


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


def _financial_amount_to_number(value) -> float | None:
    """Convert F10 financial amounts such as ``382.40亿`` into yuan."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.fullmatch(r"\s*(-?[\d,.]+)\s*(万亿|亿|万|元)?\s*", str(value))
    if not match:
        return None
    try:
        number = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    multiplier = {"万亿": 1e12, "亿": 1e8, "万": 1e4, "元": 1.0, None: 1.0}[match.group(2)]
    return number * multiplier


def plot_financial_report_bars(
    reports: pd.DataFrame,
    title: str,
    unit_scale: float = 1e8,
    unit_label: str = "亿元",
) -> go.Figure:
    """Plot revenue and net-profit changes across a small set of report periods."""
    columns = ["报告期", "营业总收入", "净利润"]
    frame = reports.reindex(columns=columns).copy()
    frame["营业总收入"] = frame["营业总收入"].map(_financial_amount_to_number)
    frame["净利润"] = frame["净利润"].map(_financial_amount_to_number)
    frame = frame.dropna(subset=["报告期"], how="any").iloc[::-1]

    fig = go.Figure()
    for column, label, color in (
        ("营业总收入", "营业总收入", "#22d3ee"),
        ("净利润", "净利润", "#8b5cf6"),
    ):
        values = frame[column] / unit_scale
        fig.add_trace(
            go.Bar(
                x=frame["报告期"],
                y=values,
                name=label,
                marker_color=color,
                opacity=0.9,
                hovertemplate=f"报告期：%{{x}}<br>{label}：%{{y:.2f}}{unit_label}<extra></extra>",
            )
        )

    fig.update_layout(
        title=dict(text=title, x=0.01, xanchor="left"),
        barmode="group",
        bargap=0.28,
        bargroupgap=0.08,
        height=330,
        margin=dict(l=35, r=20, t=58, b=35),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_yaxes(title_text=unit_label, rangemode="tozero")
    return _apply_dark_theme(fig)


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


def _intraday_axis_config(index: pd.Index, market: str) -> dict:
    """Return a full regular-session axis so partial days keep their true width."""
    trade_day = pd.Timestamp(index[-1]).normalize()
    market = market.upper()
    sessions = {
        "CN": ((9, 30), (15, 0), [(9, 30), (10, 30), (13, 0), (14, 0), (15, 0)]),
        "US": ((9, 30), (16, 0), [(9, 30), (11, 0), (12, 30), (14, 0), (16, 0)]),
        "KR": ((9, 0), (15, 30), [(9, 0), (10, 30), (12, 0), (13, 30), (15, 30)]),
    }
    session_start, session_end, tick_times = sessions.get(market, sessions["US"])

    def at(hour_minute: tuple[int, int]) -> pd.Timestamp:
        hour, minute = hour_minute
        return trade_day + pd.Timedelta(hours=hour, minutes=minute)

    tick_text = [f"{hour:02d}:{minute:02d}" for hour, minute in tick_times]
    if market == "CN":
        tick_text[2] = "11:30 / 13:00"
    return {
        "range": [at(session_start), at(session_end)],
        "tickvals": [at(value) for value in tick_times],
        "ticktext": tick_text,
        "rangebreaks": [dict(bounds=[11.5, 13], pattern="hour")] if market == "CN" else [],
    }


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
    metric = "amount" if show_amount else "volume"
    scale, unit = chart_unit(metric, market)
    volume_y = (amount if show_amount else df["Volume"]) / scale
    volume_label = f"成交额（{unit}）" if show_amount else f"成交量（{unit}）"
    volume_hover = "成交额：%{customdata}<extra></extra>" if show_amount else "成交量：%{customdata}<extra></extra>"
    volume_customdata = (
        amount.map(lambda value: format_amount(value, market)).to_numpy()
        if show_amount
        else df["Volume"].map(lambda value: format_volume(value, market)).to_numpy()
    )
    latest_close = float(pd.to_numeric(df["Close"], errors="coerce").iloc[-1])
    close_prices = pd.to_numeric(df["Close"], errors="coerce")
    forward_returns = (latest_close / close_prices - 1) * 100
    forward_return_hover = [
        f"<span style='color:{'#e53935' if value >= 0 else '#1e9d55'}'>至最新交易日：{value:+.2f}%</span>"
        if pd.notna(value) else "至最新交易日：—"
        for value in forward_returns
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
        customdata=forward_return_hover,
        hovertemplate=(
            "开盘：%{open:.2f}<br>"
            "最高：%{high:.2f}<br>"
            "最低：%{low:.2f}<br>"
            "收盘：%{close:.2f}<br>%{customdata}<extra></extra>"
        ),
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

    high_prices = pd.to_numeric(df["High"], errors="coerce")
    low_prices = pd.to_numeric(df["Low"], errors="coerce")
    price_axis_range = None
    if high_prices.notna().any() and low_prices.notna().any():
        overlay_columns = ["High", "Low"]
        if ma_periods:
            overlay_columns.extend(f"MA_{period}" for period in ma_periods if f"MA_{period}" in df.columns)
        if show_boll:
            overlay_columns.extend(
                column for column in ("BB_Upper", "BB_Middle", "BB_Lower") if column in df.columns
            )
        if show_bbi and "BBI" in df.columns:
            overlay_columns.append("BBI")
        plotted_prices = pd.concat(
            [pd.to_numeric(df[column], errors="coerce") for column in overlay_columns],
            ignore_index=True,
        ).dropna()
        price_floor, price_ceiling = float(plotted_prices.min()), float(plotted_prices.max())
        price_span = max(price_ceiling - price_floor, max(abs(price_ceiling), 1.0) * 0.02)
        label_padding = price_span * 0.075
        price_axis_range = [price_floor - label_padding, price_ceiling + label_padding]

        high_date, low_date = high_prices.idxmax(), low_prices.idxmin()
        extrema = (
            ("最高", high_date, float(high_prices.loc[high_date]), price_ceiling + label_padding * 0.55),
            ("最低", low_date, float(low_prices.loc[low_date]), price_floor - label_padding * 0.55),
        )
        inward_steps = max(1, min(8, len(df) // 20))
        for label, date, price, label_y in extrema:
            date_position = df.index.get_indexer([date])[0]
            label_position = (
                min(date_position + inward_steps, len(df) - 1)
                if date_position < len(df) / 2
                else max(date_position - inward_steps, 0)
            )
            fig.add_annotation(
                x=date,
                y=price,
                ax=df.index[label_position],
                ay=label_y,
                xref="x",
                yref="y",
                axref="x",
                ayref="y",
                text=f"<b>{label}</b> {price:,.2f}",
                showarrow=True,
                arrowhead=0,
                arrowwidth=1.15,
                arrowcolor="#f8fafc",
                bgcolor="rgba(7, 11, 20, 0.84)",
                bordercolor="rgba(226, 232, 240, 0.42)",
                borderwidth=1,
                borderpad=4,
                font=dict(color="#f8fafc", size=12),
            )

    fig.add_trace(
        go.Bar(
            x=df.index,
            y=volume_y,
            marker_color=volume_colors,
            marker_line_width=0,
            name=volume_label,
            opacity=0.82,
            customdata=volume_customdata,
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
        range=price_axis_range,
    )
    fig.update_yaxes(
        title_text=volume_label,
        row=2,
        col=1,
        gridcolor=GRID_COLOR,
        tickformat=".2f",
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
    up_color = "#e53935" if is_a_share else "#16a085"
    down_color = "#1e9d55" if is_a_share else "#e74c3c"
    pre_close = float(df.attrs.get("pre_close", df["Price"].iloc[0]))
    price_change_pct = (df["Price"] / pre_close - 1) * 100
    amount = (
        pd.to_numeric(df["Amount"], errors="coerce").fillna(0)
        if "Amount" in df.columns
        else df["Price"] * df["Volume"]
    )
    price_color = "#35a7ff"
    price_fill = "rgba(53, 167, 255, 0.08)"
    high_index = price_change_pct.idxmax()
    low_index = price_change_pct.idxmin()
    high_pct = float(price_change_pct.loc[high_index])
    low_pct = float(price_change_pct.loc[low_index])
    previous_prices = df["Price"].shift(1).fillna(pre_close)
    volume_colors = [
        up_color if price >= previous else down_color
        for price, previous in zip(df["Price"], previous_prices)
    ]
    volume_scale, volume_chart_unit = chart_unit("volume", market)
    amount_scale, amount_chart_unit = chart_unit("amount", market)
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
            hovertemplate=f"均价: {currency_symbol}%{{y:.2f}}<extra></extra>",
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
            cliponaxis=False,
            showlegend=False,
            hovertemplate=(
                f"日内最高: {currency_symbol}%{{y:.2f}}<br>涨跌幅: {high_pct:+.2f}%"
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
            cliponaxis=False,
            showlegend=False,
            hovertemplate=(
                f"日内最低: {currency_symbol}%{{y:.2f}}<br>涨跌幅: {low_pct:+.2f}%"
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
            y=df["Volume"] / volume_scale,
            name=f"成交量（{volume_chart_unit}）",
            marker_color=volume_colors,
            marker_line_width=0,
            opacity=0.82,
            visible=volume_metric == "volume",
            showlegend=False,
            customdata=df["Volume"].map(lambda value: format_volume(value, market)).to_numpy(),
            hovertemplate="成交量：%{customdata}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=amount / amount_scale,
            name=f"成交额（{amount_chart_unit}）",
            marker_color=volume_colors,
            marker_line_width=0,
            opacity=0.82,
            visible=volume_metric == "amount",
            showlegend=False,
            customdata=amount.map(lambda value: format_amount(value, market)).to_numpy(),
            hovertemplate="成交额：%{customdata}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    max_deviation = max(
        abs(float(df["Price"].min()) - pre_close),
        abs(float(df["Price"].max()) - pre_close),
    )
    price_span = max(max_deviation * 1.08, abs(pre_close) * 0.002)
    price_range = [pre_close - price_span, pre_close + price_span]
    pct_range = [
        (price_range[0] / pre_close - 1) * 100,
        (price_range[1] / pre_close - 1) * 100,
    ]
    fig.update_layout(
        title=dict(text="当日分时", x=0.01, xanchor="left"),
        template="plotly_dark",
        height=620,
        hovermode="x unified",
        margin=dict(l=35, r=25, t=115, b=45),
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
    intraday_axis = _intraday_axis_config(df.index, market)
    fig.update_xaxes(
        range=intraday_axis["range"],
        rangebreaks=intraday_axis["rangebreaks"],
        tickmode="array",
        tickvals=intraday_axis["tickvals"],
        ticktext=intraday_axis["ticktext"],
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
        title_text=(f"成交额（{amount_chart_unit}）" if volume_metric == "amount" else f"成交量（{volume_chart_unit}）"),
        row=2,
        col=1,
        gridcolor=GRID_COLOR,
        tickformat=".2f",
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
        height=600,
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
