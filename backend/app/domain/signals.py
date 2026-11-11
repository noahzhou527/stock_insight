"""技术信号摘要 (B3): descriptive rules, no buy/sell advice, no composite score.

Ported from investment_insights_view.py with these changes:
- 措辞描述性，不出现"买入信号 / 卖出信号 / 建仓 / 减仓"；删除综合评分与综合建议。
- B10: 价格相对 20 日均线 uses MA20 computed on the warm-up-inclusive series.
- 波动率 is no longer counted as bullish; it is only described.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from .new_listing import NewListingState

TITLE = "技术信号摘要"
DISCLAIMER = "基于固定规则，不构成投资建议"
HIGH_VOLATILITY = 30.0


@dataclass(frozen=True)
class Signal:
    key: str
    name: str
    status: str
    description: str
    tone: str  # up / down / neutral / warn / info (the frontend maps up/down to market colours)

    def as_dict(self) -> dict:
        return asdict(self)


def _last(series: pd.Series | None) -> float | None:
    if series is None:
        return None
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.iloc[-1]) if len(values) else None


def technical_signals(close: pd.Series, ma20: pd.Series, rsi: pd.Series, rsi_period: int, macd_line: pd.Series,
                      macd_signal: pd.Series, volatility: float | None, state: NewListingState) -> list[Signal]:
    signals: list[Signal] = []
    price, ma_value = _last(close), _last(ma20)
    if not state.trend_ready or price is None or ma_value is None:
        signals.append(Signal("trend", "价格与 20 日均线", "数据不足",
                              f"上市以来仅 {state.daily_bars} 根日 K，暂不判断", "info"))
    elif price >= ma_value:
        signals.append(Signal("trend", "价格与 20 日均线", "高于均线", f"收盘价 {price:.2f} 高于 20 日均线 {ma_value:.2f}", "up"))
    else:
        signals.append(Signal("trend", "价格与 20 日均线", "低于均线", f"收盘价 {price:.2f} 低于 20 日均线 {ma_value:.2f}", "down"))

    rsi_value = _last(rsi)
    name = f"RSI({rsi_period})"
    if not state.rsi_ready or rsi_value is None:
        signals.append(Signal("rsi", name, "数据不足", "历史日 K 不足，暂不计算 RSI", "info"))
    elif rsi_value > 70:
        signals.append(Signal("rsi", name, "超买区间", f"RSI 为 {rsi_value:.1f}，高于 70（超买区间）", "warn"))
    elif rsi_value < 30:
        signals.append(Signal("rsi", name, "超卖区间", f"RSI 为 {rsi_value:.1f}，低于 30（超卖区间）", "warn"))
    else:
        signals.append(Signal("rsi", name, "中性区间", f"RSI 为 {rsi_value:.1f}，处于 30–70 之间", "neutral"))

    line, signal = _last(macd_line), _last(macd_signal)
    if not state.macd_ready or line is None or signal is None:
        signals.append(Signal("macd", "MACD", "数据不足", "历史日 K 不足，暂不计算 MACD", "info"))
    elif line >= signal:
        signals.append(Signal("macd", "MACD", "MACD 线在信号线上方", f"MACD {line:.3f}，信号线 {signal:.3f}", "up"))
    else:
        signals.append(Signal("macd", "MACD", "MACD 线在信号线下方", f"MACD {line:.3f}，信号线 {signal:.3f}", "down"))

    if not state.volatility_ready or volatility is None:
        signals.append(Signal("volatility", "年化波动率", "数据不足", "至少需要两根日 K 才能计算波动率", "info"))
    elif volatility > HIGH_VOLATILITY:
        signals.append(Signal("volatility", "年化波动率", "较高", f"年化波动率 {volatility:.1f}%，高于 {HIGH_VOLATILITY:.0f}%", "warn"))
    else:
        signals.append(Signal("volatility", "年化波动率", "一般", f"年化波动率 {volatility:.1f}%", "neutral"))
    return signals


def fundamental_signals(target: dict | None, peers: list[dict]) -> list[Signal]:
    """``target`` / ``peers`` are rows from ``peers.annual_comparison_row``."""
    signals: list[Signal] = []
    available = [p for p in peers if p.get("revenue") is not None or p.get("net_profit") is not None]
    debt = target.get("debt_ratio") if target else None
    debts = [p["debt_ratio"] for p in available if p.get("debt_ratio") is not None]
    if debt is not None and debts:
        average = sum(debts) / len(debts)
        status = "低于赛道均值" if debt <= average else "高于赛道均值"
        signals.append(Signal("debt_ratio", "资产负债率", status,
                              f"最新年报资产负债率 {debt:.1f}%，赛道平均 {average:.1f}%", "neutral"))
    else:
        signals.append(Signal("debt_ratio", "资产负债率", "数据不足", "暂缺可比的最新年报资产负债率", "info"))

    capex, ratio = (target.get("capex"), target.get("capex_ratio")) if target else (None, None)
    ratios = [p["capex_ratio"] for p in available if p.get("capex_ratio") is not None]
    if capex is not None and ratio is not None:
        median = float(pd.Series(ratios).median()) if ratios else None
        if median is None:
            status, comparison = "无可比数据", ""
        else:
            status = "不低于赛道中位数" if ratio >= median else "低于赛道中位数"
            comparison = f"，赛道中位数 {median:.1f}%"
        signals.append(Signal("capex", "资本开支", status,
                              f"最新年报资本开支 {capex / 1e8:.2f} 亿元，占营收 {ratio:.1f}%{comparison}", "neutral"))
    else:
        signals.append(Signal("capex", "资本开支", "数据不足", "暂缺最新年报资本开支数据", "info"))
    return signals
