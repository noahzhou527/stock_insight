"""Per-instrument endpoints: bars + indicators, intraday, snapshot, financials, peers, signals, CSV."""
from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from typing import Callable

import pandas as pd

from ..domain import indicators as ind
from ..domain import sessions
from ..domain.new_listing import is_new_listing_history, new_listing_state
from ..domain.peers import annual_comparison_row, ttm_net_profit
from ..domain.signals import DISCLAIMER, TITLE, fundamental_signals, technical_signals
from ..domain.snapshot import compute_snapshot, one_year_before
from ..providers.base import DataFetchError, Instrument, Intraday, ReportRow, Valuation
from ..providers.composite import CompositeProvider, Routed
from .cache import Cached, PayloadCacheService
from .common import Meta, error_dict, meta_from_cached, worst_freshness
from .daily_bars import DailyBarService
from .financials import FinancialsService
from .instruments import InstrumentService

PRICE_COLUMNS = ("open", "high", "low", "close", "amount")
AMOUNT_METRICS = {"revenue", "net_profit", "net_profit_excl", "gross_profit", "operating_income", "capex",
                  "eps_basic", "ocf_per_share"}
CUMULATIVE_NOTE = "A 股季报为累计口径（一季报、中报、三季报），未拆分单季"


def _clean(value):
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    return value


def encode_intraday(value: Intraday) -> dict:
    return {"points": [{"time": t.isoformat(), **{k: _clean(float(v)) for k, v in row.items()}}
                       for t, row in value.points.iterrows()],
            "trade_date": value.trade_date.isoformat(), "pre_close": value.pre_close, "source": value.source,
            "currency": value.currency, "name": value.name}


def decode_intraday(payload: dict) -> Intraday:
    points = pd.DataFrame(payload["points"])
    if not points.empty:
        points["time"] = pd.to_datetime(points["time"])
        points = points.set_index("time")[["price", "avg_price", "volume", "amount"]]
    return Intraday(points, date.fromisoformat(payload["trade_date"]), payload["pre_close"], payload["source"],
                    payload["currency"], payload.get("name"))


def encode_valuation(value: Valuation | None) -> dict | None:
    return None if value is None else value.__dict__.copy()


def decode_valuation(payload: dict | None) -> Valuation | None:
    return None if payload is None else Valuation(**payload)


class StockService:
    def __init__(self, provider: CompositeProvider, cache: PayloadCacheService, bars: DailyBarService,
                 financials: FinancialsService, instruments: InstrumentService, fx: Callable[[], Cached],
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.provider = provider
        self.cache = cache
        self.bars_service = bars
        self.financials_service = financials
        self.instruments = instruments
        self.fx = fx
        self.now = now

    # ------------------------------------------------------------------ helpers
    def _rate(self, inst: Instrument, currency: str | None) -> tuple[float, dict | None]:
        target = (currency or inst.currency).upper()
        if target == inst.currency:
            return 1.0, None
        if inst.currency == "KRW" and target == "USD":
            cached = self.fx()
            return cached.value, {"from": "KRW", "to": "USD", "rate": cached.value, "source": cached.source,
                                  "fetched_at": cached.fetched_at, "note": "全区间按当前参考汇率统一换算"}
        raise DataFetchError("unsupported_currency", f"暂不支持把 {inst.currency} 换算为 {target}。")

    def intraday_cached(self, inst: Instrument) -> Cached:
        return self.cache.get("intraday", inst.id, lambda: self.provider.intraday(inst),
                              encode=encode_intraday, decode=decode_intraday)

    def _intraday_routed(self, inst: Instrument) -> Routed[Intraday]:
        cached = self.intraday_cached(inst)
        return Routed(cached.value, cached.source or "", cached.fallback)

    def _history(self, inst: Instrument, start: date, end: date):
        result = self.bars_service.get(inst, start, end, intraday=self._intraday_routed)
        if result.name:
            self.instruments.update_name(inst, result.name)
        return result

    # ------------------------------------------------------------------ bars
    def bars(self, inst: Instrument, start: date, end: date, params: ind.IndicatorParams, currency: str | None = None) -> dict:
        rate, fx = self._rate(inst, currency)
        warm = ind.warmup_start(start, params)
        result = self._history(inst, warm, end)
        frame = result.frame.copy()
        for column in PRICE_COLUMNS:
            frame[column] = frame[column].astype(float) * rate
        computed = ind.compute(frame["close"].astype(float), params)
        display_mask = (frame.index >= start) & (frame.index <= end)
        display = frame[display_mask]
        state = new_listing_state(frame["close"], params.rsi)
        first_bar = frame.index.min() if not frame.empty else None
        meta = result.meta
        return {
            "instrument": self.instruments.info(inst),
            "bars": [
                {"date": d, **{c: _clean(float(r[c])) if r[c] is not None else None for c in ("open", "high", "low", "close", "volume", "amount")},
                 "amount_estimated": bool(r["amount_estimated"]), "provisional": bool(r["provisional"]), "source": r["source"]}
                for d, r in display.iterrows()
            ],
            "indicators": {name: [_clean(float(v)) for v in series[display_mask]] for name, series in computed.items()},
            "new_listing": {**state.as_dict(), "is_new_listing": is_new_listing_history(first_bar, warm)},
            "fx": fx,
            "meta": Meta(meta.source, meta.as_of, meta.fetched_at, meta.freshness, fx["to"] if fx else meta.currency,
                         meta.note, meta.errors).as_dict(),
        }

    def bars_csv(self, inst: Instrument, start: date, end: date, currency: str | None = None) -> str:
        data = self.bars(inst, start, end, ind.IndicatorParams(ma=(), rsi=0, macd=False), currency)
        frame = pd.DataFrame(data["bars"])
        if frame.empty:
            return "日期,开盘,最高,最低,收盘,成交量(股),成交额,成交额为估算,盘中合成,来源\n"
        frame = frame.rename(columns={"date": "日期", "open": "开盘", "high": "最高", "low": "最低", "close": "收盘",
                                      "volume": "成交量(股)", "amount": "成交额", "amount_estimated": "成交额为估算",
                                      "provisional": "盘中合成", "source": "来源"})
        buffer = io.StringIO()
        frame.to_csv(buffer, index=False)
        return buffer.getvalue()

    # ------------------------------------------------------------------ intraday
    def intraday(self, inst: Instrument, currency: str | None = None) -> dict:
        rate, fx = self._rate(inst, currency)
        cached = self.intraday_cached(inst)
        value: Intraday = cached.value
        self.instruments.update_name(inst, value.name)
        points = [{"time": t, "price": _clean(row.price * rate), "avg_price": _clean(row.avg_price * rate),
                   "volume": _clean(row.volume), "amount": _clean(row.amount * rate)} for t, row in value.points.iterrows()]
        meta = meta_from_cached(cached, inst.market, self.now(), currency=fx["to"] if fx else value.currency,
                                as_of=value.points.index[-1] if len(value.points) else None)
        if value.trade_date < sessions.market_today(inst.market, self.now()):
            meta.freshness = "cached" if cached.stale else "closed"
        return {"points": points, "pre_close": value.pre_close * rate, "trade_date": value.trade_date, "name": value.name,
                "fx": fx, "meta": meta.as_dict()}

    # ------------------------------------------------------------------ valuation
    def valuation_cached(self, inst: Instrument) -> Cached:
        return self.cache.get("valuation", inst.id, lambda: self.provider.valuation(inst),
                              encode=encode_valuation, decode=decode_valuation)

    # ------------------------------------------------------------------ snapshot
    def snapshot(self, inst: Instrument, start: date, end: date, rsi_period: int = 14, currency: str | None = None) -> dict:
        rate, fx = self._rate(inst, currency)
        today = sessions.market_today(inst.market, self.now())
        year_start = one_year_before(min(end, today))
        result = self._history(inst, min(start, year_start), end)
        frame = result.frame.copy()
        for column in PRICE_COLUMNS:
            frame[column] = frame[column].astype(float) * rate
        display = frame[(frame.index >= start) & (frame.index <= end)]
        last_year = frame[frame.index >= year_start]
        state = new_listing_state(frame["close"], rsi_period)

        notes, freshness = [], [result.meta.freshness]
        intraday_price = intraday_pre_close = None
        if end >= today:
            try:
                cached = self.intraday_cached(inst)
                value: Intraday = cached.value
                if len(value.points):
                    intraday_price = float(value.points["price"].iloc[-1]) * rate
                    intraday_pre_close = value.pre_close * rate
                if cached.stale:
                    freshness.append("cached")
                    notes.append(f"分时为本地缓存（{cached.error.message if cached.error else '上游不可用'}）")
            except DataFetchError as error:
                notes.append(f"分时暂不可用：{error.message}")
        metrics = compute_snapshot(display, last_year, state, intraday_price, intraday_pre_close)

        valuation, valuation_meta = None, None
        try:
            cached = self.valuation_cached(inst)
            if cached.value is not None:
                v: Valuation = cached.value
                valuation = {"pe_ttm": v.pe_ttm, "pe_static": v.pe_static, "pe_dynamic": v.pe_dynamic,
                             "market_cap": v.market_cap * rate if v.market_cap else None,
                             "ttm_net_profit": v.ttm_net_profit * rate if v.ttm_net_profit else None, "source": v.source}
            valuation_meta = meta_from_cached(cached, inst.market, self.now()).as_dict()
        except DataFetchError as error:
            valuation_meta = {"freshness": "cached", "errors": [error_dict(error)], "note": f"估值暂不可用：{error.message}"}

        meta = result.meta
        return {
            "instrument": self.instruments.info(inst),
            "metrics": metrics.as_dict(),
            "valuation": valuation,
            "valuation_meta": valuation_meta,
            "new_listing": {**state.as_dict(), "is_new_listing": is_new_listing_history(frame.index.min() if not frame.empty else None, min(start, year_start))},
            "fx": fx,
            "meta": Meta(meta.source, meta.as_of, meta.fetched_at, worst_freshness(*freshness),
                         fx["to"] if fx else meta.currency, "；".join(filter(None, [meta.note, *notes])) or None,
                         meta.errors).as_dict(),
        }

    # ------------------------------------------------------------------ financials
    def financials(self, inst: Instrument, currency: str | None = None) -> dict:
        rate, fx = self._rate(inst, currency)
        result = self.financials_service.get(inst)
        annual = sorted({r.period_end for r in result.rows if r.report_type == "annual"}, reverse=True)[:4]
        quarterly = sorted({r.period_end for r in result.rows if r.report_type != "annual"}, reverse=True)[:4]
        keep = set(annual) | set(quarterly)
        rows = [
            {"period_end": r.period_end, "report_type": r.report_type, "metric": r.metric,
             "value": (r.value * rate if r.value is not None and r.metric in AMOUNT_METRICS else r.value),
             "currency": (fx["to"] if fx and r.currency else r.currency)}
            for r in sorted(result.rows, key=lambda r: (r.period_end, r.report_type, r.metric), reverse=True)
            if r.period_end in keep
        ]
        ttm = ttm_net_profit(result.rows) if inst.market == "CN" else None
        meta = Meta(result.source, max(keep) if keep else None, result.fetched_at, "cached" if result.stale else "closed",
                    fx["to"] if fx else inst.currency, CUMULATIVE_NOTE if inst.market == "CN" else None,
                    [error_dict(result.error)] if result.error else [])
        return {"rows": rows, "annual_periods": annual, "quarterly_periods": quarterly,
                "ttm_net_profit": ttm * rate if ttm is not None else None, "fx": fx, "meta": meta.as_dict()}

    # ------------------------------------------------------------------ peers
    def peers(self, inst: Instrument) -> dict:
        group = self.instruments.peer_group(inst)
        if group is None:
            return {"supported": False, "message": "暂只支持股票池内 A 股的同赛道对比", "group": None, "rows": [], "target": None,
                    "meta": Meta(None, None, None, "closed").as_dict()}
        name, members, names = group

        def load(member: Instrument) -> tuple[dict, bool]:
            stock = {"id": member.id, "symbol": member.symbol, "name": names.get(member.id)}
            try:
                result = self.financials_service.get(member)
                return annual_comparison_row(stock, result.rows), result.stale
            except DataFetchError:
                return annual_comparison_row(stock, []), True

        with ThreadPoolExecutor(max_workers=4) as pool:
            loaded = list(pool.map(load, members))
        rows = [row for row, _ in loaded]
        any_stale = any(stale for _, stale in loaded)
        target = next((r for r in rows if r["id"] == inst.id), None)
        note = "最新年报口径；净利率 = 净利润 ÷ 营收，作为产品表现的代理指标；资本开支为“购建固定资产、无形资产和其他长期资产支付的现金”"
        return {"supported": True, "message": None, "group": name, "rows": rows, "target": target,
                "meta": Meta("同花顺 F10", max((r["period_end"] for r in rows if r["period_end"]), default=None), None,
                             "cached" if any_stale else "closed", "CNY", note).as_dict()}

    # ------------------------------------------------------------------ signals
    def signals(self, inst: Instrument, rsi_period: int = 14) -> dict:
        today = sessions.market_today(inst.market, self.now())
        params = ind.IndicatorParams(ma=(20,), rsi=rsi_period, macd=True)
        start = one_year_before(today)
        result = self._history(inst, ind.warmup_start(start, params), today)
        close = result.frame["close"].astype(float)
        state = new_listing_state(close, rsi_period)
        computed = ind.compute(close, params)
        display_close = close[close.index >= start]
        volatility = ind.annualized_volatility(display_close) if state.volatility_ready else None
        signals = technical_signals(close, computed["ma20"], computed[f"rsi{rsi_period}"], rsi_period,
                                    computed["macd"], computed["macd_signal"], volatility, state)
        peer_note = None
        if inst.market == "CN":
            peers = self.peers(inst)
            signals += fundamental_signals(peers["target"], peers["rows"]) if peers["supported"] else fundamental_signals(None, [])
            if not peers["supported"]:
                peer_note = peers["message"]
        else:
            peer_note = "资产负债率与资本开支对比暂只支持股票池内 A 股"
        meta = result.meta
        return {"title": TITLE, "disclaimer": DISCLAIMER, "signals": [s.as_dict() for s in signals],
                "fundamentals_supported": inst.market == "CN" and peer_note is None,
                "meta": Meta(meta.source, meta.as_of, meta.fetched_at, meta.freshness, meta.currency,
                             "；".join(filter(None, [meta.note, peer_note])) or None, meta.errors).as_dict()}
