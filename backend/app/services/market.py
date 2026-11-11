"""Market overview: index cards, market breadth, index intraday (ported from services/market_overview_data.py)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Callable

from ..domain import sessions
from ..providers.base import Bars, Breadth, DataFetchError, Instrument, Intraday
from ..providers.composite import CompositeProvider, Routed
from .cache import PayloadCacheService
from .common import Meta, error_dict, meta_from_cached
from .instruments import InstrumentService
from .quotes import QuoteService
from .stock import decode_intraday, encode_intraday

INDICES = {
    "CN": (
        {"name": "上证指数", "symbol": "1A0001", "display_code": "000001", "eastmoney_secid": "1.000001"},
        {"name": "深证成指", "symbol": "399001", "display_code": "399001", "eastmoney_secid": "0.399001"},
        {"name": "创业板指", "symbol": "399006", "display_code": "399006", "eastmoney_secid": "0.399006"},
        {"name": "科创综指", "symbol": "1B0680", "display_code": "000680", "eastmoney_secid": "1.000680"},
        {"name": "北证50", "symbol": "899050", "display_code": "899050", "eastmoney_secid": "0.899050"},
    ),
    "US": (
        {"name": "道琼斯", "symbol": "^DJI", "display_code": "^DJI"},
        {"name": "纳斯达克综合", "symbol": "^IXIC", "display_code": "^IXIC"},
        {"name": "纳斯达克100", "symbol": "^NDX", "display_code": "^NDX"},
        {"name": "标普500", "symbol": "^GSPC", "display_code": "^GSPC"},
    ),
    "KR": ({"name": "韩国综合指数", "symbol": "^KS11", "display_code": "KOSPI"},),
}


def _amount(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 and number == number else None


class MarketService:
    def __init__(self, provider: CompositeProvider, cache: PayloadCacheService, quotes: QuoteService,
                 instruments: InstrumentService, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.provider = provider
        self.cache = cache
        self.quotes = quotes
        self.instruments = instruments
        self.now = now

    def _p(self, key: str):
        return None if key in self.provider.disabled else self.provider.providers.get(key)

    @staticmethod
    def config(market: str, symbol: str) -> dict:
        for item in INDICES.get(market, ()):
            if symbol in (item["symbol"], item["display_code"]):
                return item
        raise DataFetchError("not_found", f"未知指数：{market} {symbol}")

    @staticmethod
    def _intraday_is_newer(intraday: Intraday | None, daily: Bars, today: date, market: str) -> bool:
        """Use the intraday session when it is today's, or when the daily feed has not published that day yet.

        (Legacy only used intraday when dated "today", so a lagging daily feed — e.g. Yahoo ^KS11 after the
        KRX close — left the card one session behind.)
        """
        if intraday is None or not len(intraday.points):
            return False
        last_daily = daily.frame.index.max() if not daily.frame.empty else None
        return intraday.trade_date == today or (last_daily is not None and intraday.trade_date > last_daily)

    # ---------------------------------------------------------------- per-index fetch
    def _cn_daily(self, cfg: dict, today: date) -> tuple[Bars, str]:
        start = date(today.year - 1, 1, 1)
        errors = []
        ths, em = self._p("ths"), self._p("eastmoney")
        if ths:
            try:
                bars = ths.daily_bars(Instrument("CN", cfg["symbol"]), start, today)
                if not bars.empty:
                    return bars, ths.name
            except DataFetchError as error:
                errors.append(error)
        if em:
            try:
                bars = em.index_daily(cfg["eastmoney_secid"], start, today)
                if not bars.empty:
                    return bars, em.name
            except DataFetchError as error:
                errors.append(error)
        raise errors[0] if errors else DataFetchError("index_daily_empty", f"{cfg['name']} 日线暂不可用。")

    def _cn_intraday(self, cfg: dict) -> Intraday:
        errors = []
        for key, call in (("ths", lambda p: p.intraday(Instrument("CN", cfg["symbol"]))),
                          ("eastmoney", lambda p: p.index_intraday(cfg["eastmoney_secid"]))):
            provider = self._p(key)
            if provider is None:
                continue
            try:
                return call(provider)
            except DataFetchError as error:
                errors.append(error)
        raise errors[0] if errors else DataFetchError("index_intraday_unavailable", "指数分时暂不可用。")

    def _card(self, market: str, cfg: dict) -> dict:
        today = sessions.market_today(market, self.now())
        base = {k: cfg[k] for k in ("name", "symbol", "display_code")}
        try:
            if market == "CN":
                daily, source = self._cn_daily(cfg, today)
                try:
                    intraday = self._cn_intraday(cfg)
                except DataFetchError:
                    intraday = None
                use_intraday = self._intraday_is_newer(intraday, daily, today, market)
            else:
                yahoo = self._p("yahoo")
                inst = Instrument(market, cfg["symbol"])
                daily = yahoo.daily_bars(inst, date.fromordinal(today.toordinal() - 20), today)
                source = yahoo.name
                try:
                    intraday = yahoo.intraday(inst)
                except DataFetchError:
                    intraday = None
                use_intraday = self._intraday_is_newer(intraday, daily, today, market)
            frame = daily.frame
            if frame.empty:
                raise DataFetchError("index_daily_empty", f"{cfg['name']} 日线为空。")
            if use_intraday:
                completed = frame[frame.index < intraday.trade_date]
                previous = completed.iloc[-1] if not completed.empty else frame.iloc[-1]
                price = float(intraday.points["price"].iloc[-1])
                previous_close = float(intraday.pre_close) if market == "CN" else float(previous["close"])
                amount = _amount(intraday.points["amount"].sum()) if market == "CN" else None
                trade_date = intraday.trade_date
            else:
                current = frame.iloc[-1]
                previous = frame.iloc[-2] if len(frame) > 1 else current
                price, previous_close = float(current["close"]), float(previous["close"])
                amount = _amount(current["amount"]) if market == "CN" else None
                trade_date = frame.index[-1]
            previous_amount = _amount(previous["amount"]) if market == "CN" else None
            amount_change = amount - previous_amount if amount is not None and previous_amount is not None else None
            constituents = None
            if market == "CN" and self._p("eastmoney"):
                try:
                    constituents = self._p("eastmoney").index_constituents(cfg["eastmoney_secid"])
                except DataFetchError:
                    constituents = None
            return {**base, "price": price, "previous_close": previous_close, "change": price - previous_close,
                    "change_pct": (price / previous_close - 1) * 100 if previous_close else None,
                    "amount": amount, "previous_amount": previous_amount, "amount_change": amount_change,
                    "amount_change_pct": amount_change / previous_amount * 100 if amount_change is not None and previous_amount else None,
                    "trade_date": trade_date, "source": source, "constituents": constituents, "error": None}
        except DataFetchError as error:
            return {**base, "error": error_dict(error)}

    # ---------------------------------------------------------------- public
    def overview(self, market: str) -> dict:
        market = market.upper()
        if market not in INDICES:
            raise DataFetchError("not_found", f"不支持的市场：{market}")

        def fetch() -> Routed[list[dict]]:
            cards = [self._card(market, cfg) for cfg in INDICES[market]]
            if all(card["error"] for card in cards):
                raise DataFetchError(cards[0]["error"]["category"], cards[0]["error"]["message"], cards[0]["error"]["detail"])
            sources = sorted({c["source"] for c in cards if not c["error"]})
            return Routed(cards, " / ".join(sources), False)

        cached = self.cache.get(f"index_{market.lower()}", market, fetch)
        breadth = self.breadth(market) if market in {"CN", "US"} else None
        dates = [c.get("trade_date") for c in cached.value if c.get("trade_date")]
        return {"market": market, "indices": cached.value, "breadth": breadth,
                "meta": meta_from_cached(cached, market, self.now(), as_of=max(dates) if dates else None).as_dict()}

    def breadth(self, market: str) -> dict:
        try:
            cached = self.cache.get(f"breadth_{market.lower()}", market, lambda: self.provider.market_breadth(market),
                                    encode=lambda b: b.__dict__, decode=lambda d: Breadth(**d))
            b: Breadth = cached.value
            return {"up": b.up, "down": b.down, "flat": b.flat, "total": b.total, "source": b.source, "full_market": True,
                    "meta": meta_from_cached(cached, market, self.now()).as_dict()}
        except DataFetchError as error:
            if market != "CN":
                return {"error": error_dict(error), "full_market": True}
            universe = [inst for inst, _, _ in self.instruments.cn_universe()]
            rows, _, _ = self.quotes.get(universe)
            changes = [r["change_pct"] for r in rows.values() if r.get("change_pct") is not None]
            if not changes:
                return {"error": error_dict(error), "full_market": True}
            up, down = sum(c > 0 for c in changes), sum(c < 0 for c in changes)
            return {"up": up, "down": down, "flat": len(changes) - up - down, "total": len(changes),
                    "source": "本地股票池统计（非全市场）", "full_market": False,
                    "meta": Meta("东方财富", None, None, "fallback", None,
                                 f"东方财富全市场快照暂不可用，以下为本地股票池统计（非全市场）：{error.message}",
                                 [error_dict(error)]).as_dict()}

    def index_intraday(self, market: str, symbol: str) -> dict:
        market = market.upper()
        cfg = self.config(market, symbol)

        def fetch() -> Routed[Intraday]:
            if market == "CN":
                return Routed(self._cn_intraday(cfg), "同花顺/东方财富", False)
            yahoo = self._p("yahoo")
            return Routed(yahoo.intraday(Instrument(market, cfg["symbol"])), yahoo.name, False)

        cached = self.cache.get(f"index_intraday_{market.lower()}", cfg["symbol"], fetch, encode=encode_intraday, decode=decode_intraday)
        value: Intraday = cached.value
        source = value.source or cached.source
        meta = meta_from_cached(cached, market, self.now(), as_of=value.points.index[-1] if len(value.points) else None)
        meta.source = source
        return {"index": {k: cfg[k] for k in ("name", "symbol", "display_code")}, "trade_date": value.trade_date,
                "pre_close": value.pre_close,
                "points": [{"time": t, "price": float(r.price), "avg_price": float(r.avg_price), "volume": float(r.volume),
                            "amount": float(r.amount)} for t, r in value.points.iterrows()],
                "meta": meta.as_dict()}
