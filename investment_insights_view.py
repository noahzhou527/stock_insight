"""Investment insight view renderer."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import visualization
from financial_rankings import fetch_peer_comparison


def render_investment_insights(
    ticker: str,
    market: str,
    df: pd.DataFrame,
    df_macd: pd.DataFrame,
    new_listing: dict,
    volatility: float,
    a_share_universe: dict,
) -> None:
    st.subheader("AI 驱动的投资分析")

    peer_group = next(
        (
            (group, [{"name": name, "ticker": peer_ticker} for name, peer_ticker in stocks])
            for group, stocks in a_share_universe.items()
            if any(peer_ticker == ticker for _, peer_ticker in stocks)
        ),
        None,
    )
    peer_comparison = pd.DataFrame()
    available_peers = pd.DataFrame()
    target_fundamentals = None
    if market == "CN" and peer_group is not None:
        _, peers = peer_group
        with st.spinner("正在读取同赛道财报..."):
            peer_comparison = fetch_peer_comparison(peers)
        available_peers = peer_comparison.dropna(subset=["营收", "净利润"], how="all").copy()
        target_rows = peer_comparison[peer_comparison["ticker"] == ticker]
        if not target_rows.empty:
            target_fundamentals = target_rows.iloc[0]
    
    # 简单规则引擎（模拟"AI分析"）
    signals = []
    
    # 价格趋势
    if not new_listing["trend_ready"]:
        signals.append(("历史数据", "待观察", f"上市以来仅 {new_listing['daily_bars']} 根日 K，暂不生成技术信号", "blue"))
    elif df['Close'].iloc[-1] > df['Close'].iloc[-20:].mean():
        signals.append(("价格趋势", "看涨", "当前价格高于20日均线", "green"))
    else:
        signals.append(("价格趋势", "看跌", "当前价格低于20日均线", "red"))
    
    # RSI
    if not new_listing["rsi_ready"]:
        signals.append(("RSI指标", "待观察", "历史日 K 不足，暂不生成 RSI 信号", "blue"))
    elif df['RSI'].iloc[-1] < 30:
        signals.append(("RSI指标", "超卖", "RSI低于30，可能存在反弹机会", "green"))
    elif df['RSI'].iloc[-1] > 70:
        signals.append(("RSI指标", "超买", "RSI高于70，可能存在回调风险", "red"))
    else:
        signals.append(("RSI指标", "中性", "RSI处于正常区间", "gray"))
    
    # MACD
    if not new_listing["macd_ready"]:
        signals.append(("MACD指标", "待观察", "历史日 K 不足，暂不生成 MACD 信号", "blue"))
    elif df_macd['MACD'].iloc[-1] > df_macd['Signal'].iloc[-1]:
        signals.append(("MACD指标", "金叉", "MACD上穿Signal线，买入信号", "green"))
    else:
        signals.append(("MACD指标", "死叉", "MACD下穿Signal线，卖出信号", "red"))
    
    # 波动率
    if not new_listing["volatility_ready"]:
        signals.append(("波动率", "待观察", "至少需要两根日 K 才能计算波动率", "blue"))
    elif volatility > 30:
        signals.append(("波动率", "高风险", f"年化波动率达{volatility:.1f}%，需注意风险", "orange"))
    else:
        signals.append(("波动率", "正常", f"年化波动率为{volatility:.1f}%", "green"))

    technical_signals = signals.copy()
    debt_ratio = target_fundamentals.get("资产负债率") if target_fundamentals is not None else None
    peer_debt_average = available_peers["资产负债率"].mean() if not available_peers.empty else None
    if pd.notna(debt_ratio) and pd.notna(peer_debt_average):
        lower_debt = debt_ratio <= peer_debt_average
        signals.append((
            "负债率",
            "低于赛道" if lower_debt else "高于赛道",
            f"最新年报资产负债率为{debt_ratio:.1f}%，赛道平均值为{peer_debt_average:.1f}%",
            "green" if lower_debt else "orange",
        ))
    else:
        signals.append(("负债率", "待观察", "暂缺可比的最新年报资产负债率", "blue"))

    investment_spending = target_fundamentals.get("投资支出") if target_fundamentals is not None else None
    investment_ratio = target_fundamentals.get("投资支出占营收") if target_fundamentals is not None else None
    peer_investment_median = available_peers["投资支出占营收"].median() if not available_peers.empty else None
    if pd.notna(investment_spending) and pd.notna(investment_ratio):
        status = "投入较高" if pd.notna(peer_investment_median) and investment_ratio >= peer_investment_median else "投入稳健"
        comparison = f"，赛道中位数{peer_investment_median:.1f}%" if pd.notna(peer_investment_median) else ""
        signals.append((
            "投资支出",
            status,
            f"最新年报资本性支出{investment_spending / 1e8:.2f}亿元，占营收{investment_ratio:.1f}%{comparison}",
            "blue",
        ))
    else:
        signals.append(("投资支出", "待观察", "暂缺最新年报资本性支出数据", "blue"))
    
    # 显示信号
    for name, status, desc, color in signals:
        with st.container():
            col1, col2, col3 = st.columns([2, 2, 6])
            col1.markdown(f"**{name}**")
            col2.markdown(f":{color}[{status}]")
            col3.markdown(f"*{desc}*")
            st.markdown("---")
    
    # 综合评分
    st.subheader("综合评分")
    if not new_listing["trend_ready"]:
        st.info("新股历史数据不足，暂不提供综合技术评分。")
    else:
        bullish_count = sum(1 for _, status, _, _ in technical_signals if status in ["看涨", "超卖", "金叉", "正常"])
        score = (bullish_count / len(technical_signals)) * 100
        st.progress(score / 100, text=f"看涨评分: {score:.0f}/100")
        if score > 60:
            st.success("综合建议：技术指标偏向看涨，可考虑适量建仓")
        elif score > 40:
            st.warning("综合建议：信号混合，建议观望或轻仓操作")
        else:
            st.error("综合建议：技术指标偏向看跌，建议谨慎或减仓")
    
    st.subheader("同赛道对比")
    if market != "CN" or peer_group is None:
        st.info("简单版目前支持 A 股股票池内的同赛道对比。")
    else:
        group_name, _ = peer_group
        st.caption(f"赛道：{group_name} · 最新年报口径 · 产品表现暂以净利率作为代理指标")
        if available_peers.empty:
            st.info("暂时没有可用于对比的同赛道年报数据。")
        else:
            available_peers["营收（亿元）"] = available_peers["营收"] / 1e8
            available_peers["净利润（亿元）"] = available_peers["净利润"] / 1e8
            available_peers["投资支出（亿元）"] = available_peers["投资支出"] / 1e8
            chart_choice = st.segmented_control(
                "对比指标",
                ["营收与净利润", "产品表现代理", "资产负债率"],
                default="营收与净利润",
                label_visibility="collapsed",
            )

            if chart_choice == "营收与净利润":
                financial_peers = available_peers.sort_values("营收（亿元）", ascending=False)
                financial_figure = go.Figure()
                for column, color in (("营收（亿元）", "#22d3ee"), ("净利润（亿元）", "#8b5cf6")):
                    financial_figure.add_bar(
                        x=financial_peers["name"],
                        y=financial_peers[column],
                        name=column,
                        marker_color=color,
                        hovertemplate=f"%{{x}}<br>{column}：%{{y:.2f}}<extra></extra>",
                    )
                financial_figure.update_layout(
                    title_text="",
                    barmode="group",
                    height=380,
                    margin=dict(l=20, r=15, t=20, b=35),
                    legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
                )
                financial_figure.update_yaxes(title_text="亿元")
                st.plotly_chart(
                    visualization._apply_dark_theme(financial_figure),
                    width="stretch",
                    config={"displayModeBar": False},
                )
            else:
                column = "产品表现代理" if chart_choice == "产品表现代理" else "资产负债率"
                label = "净利率（%）" if chart_choice == "产品表现代理" else "资产负债率（%）"
                color = "#7dd3fc" if chart_choice == "产品表现代理" else "#f59e0b"
                metric_peers = available_peers.dropna(subset=[column]).sort_values(column, ascending=False)
                metric_figure = go.Figure(go.Bar(
                    x=metric_peers["name"],
                    y=metric_peers[column],
                    marker_color=color,
                    hovertemplate=f"%{{x}}<br>{label}：%{{y:.2f}}%<extra></extra>",
                ))
                metric_figure.update_layout(
                    title_text="",
                    height=380,
                    margin=dict(l=20, r=15, t=20, b=35),
                    showlegend=False,
                )
                metric_figure.update_yaxes(title_text=label)
                st.plotly_chart(
                    visualization._apply_dark_theme(metric_figure),
                    width="stretch",
                    config={"displayModeBar": False},
                )
            if chart_choice == "产品表现代理":
                st.caption("代理指标：净利润 ÷ 营收；用于简单横向观察，不代表具体产品参数。")
    
            st.dataframe(
                available_peers.sort_values("营收（亿元）", ascending=False)[
                    ["name", "ticker", "报告期", "营收（亿元）", "净利润（亿元）", "产品表现代理", "资产负债率", "投资支出（亿元）", "投资支出占营收"]
                ]
                .rename(columns={
                    "name": "公司",
                    "ticker": "代码",
                    "产品表现代理": "净利率（%）",
                    "资产负债率": "资产负债率（%）",
                    "投资支出占营收": "投资支出占营收（%）",
                }),
                width="stretch",
                hide_index=True,
                column_config={
                    "营收（亿元）": st.column_config.NumberColumn(format="%.2f"),
                    "净利润（亿元）": st.column_config.NumberColumn(format="%.2f"),
                    "净利率（%）": st.column_config.NumberColumn(format="%.2f%%"),
                    "资产负债率（%）": st.column_config.NumberColumn(format="%.2f%%"),
                    "投资支出（亿元）": st.column_config.NumberColumn(format="%.2f"),
                    "投资支出占营收（%）": st.column_config.NumberColumn(format="%.2f%%"),
                },
            )
            st.caption("投资支出采用“购建固定资产、无形资产和其他长期资产支付的现金”口径。")
