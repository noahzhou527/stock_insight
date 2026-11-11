"""A 股 stock-pool rankings: live quotes + valuation normalised to the latest completed close."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable

from ..domain.peers import latest_quarter_profit
from ..domain.rankings import RANK_METRICS, adjust_valuation_to_close, rank_rows
from ..providers.base import DataFetchError
from .common import Meta, error_dict, session_freshness
from .financials import FinancialsService
from .instruments import InstrumentService
from .quotes import QuoteService


class RankingsService:
    def __init__(self, instruments: InstrumentService, quotes: QuoteService, financials: FinancialsService,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.instruments = instruments
        self.quotes = quotes
        self.financials = financials
        self.now = now

    def rankings(self, metric: str = "change_pct") -> dict:
        if metric not in RANK_METRICS:
            raise ValueError(f"metric 只能是 {', '.join(RANK_METRICS)}")
        universe = self.instruments.cn_universe()
        rows_by_id, error, source = self.quotes.get([inst for inst, _, _ in universe])
        fetch_financials = metric == "quarter_profit"

        def profit(inst):
            try:
                return latest_quarter_profit(self.financials.get(inst, fetch=fetch_financials).rows)
            except DataFetchError:
                return latest_quarter_profit([])

        with ThreadPoolExecutor(max_workers=4 if fetch_financials else 1) as pool:
            profits = list(pool.map(profit, [inst for inst, _, _ in universe]))

        rows = []
        for (inst, name, group), quarter in zip(universe, profits):
            quote = rows_by_id.get(inst.id, {})
            completed = self.quotes.completed_close(quote) if quote else None
            rows.append({
                "id": inst.id, "symbol": inst.symbol, "name": name or quote.get("name"), "group": group,
                "price": quote.get("price"), "change_pct": quote.get("change_pct"), "amount": quote.get("amount"),
                "market_cap": adjust_valuation_to_close(quote.get("market_cap"), quote.get("price"), completed),
                "pe_ttm": adjust_valuation_to_close(quote.get("pe_ttm"), quote.get("price"), completed),
                "quote_time": quote.get("quote_time"), "trade_date": quote.get("trade_date"),
                "status": quote.get("status", "missing"), "stale": quote.get("stale", True),
                "quarter_profit": quarter["net_profit"], "quarter_profit_yoy": quarter["net_profit_yoy"],
                "quarter_period": quarter["period_end"],
            })
        QuoteService.mark_old_dates(rows)
        stale = error is not None or any(r["stale"] for r in rows)
        note = "总市值与 PE 按最近一个已完成交易日的收盘价折算；季度净利润为累计口径"
        if error:
            note = f"行情接口暂不可用，显示本地缓存：{error.message}；{note}"
        dates = [r["trade_date"] for r in rows if r["trade_date"]]
        return {"metric": metric, "rows": rank_rows(rows, metric),
                "meta": Meta(source, max(dates) if dates else None, None,
                             "cached" if stale else session_freshness("CN", self.now()), "CNY", note,
                             [error_dict(error)] if error else []).as_dict()}
