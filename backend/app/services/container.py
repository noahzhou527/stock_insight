"""Wires settings → engine → providers → services. One instance per FastAPI app."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from ..config import Settings, get_settings
from ..db.session import make_engine, make_session_factory, upgrade
from ..providers.base import DataFetchError
from ..providers.composite import CompositeProvider, Routed, build_default
from ..repo import fetch_log
from .cache import Cached, PayloadCacheService
from .daily_bars import DailyBarService
from .financials import FinancialsService
from .instruments import InstrumentService
from .market import MarketService
from .news import NewsService
from .quotes import QuoteService
from .rankings import RankingsService
from .stock import StockService
from .system import HealthService, PrefsService, RefreshService
from .watchlist import WatchlistService


class Container:
    def __init__(self, settings: Settings | None = None, provider: CompositeProvider | None = None,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc), news_collect: Callable | None = None):
        self.settings = settings or get_settings()
        self.now = now
        self.engine = make_engine(self.settings.db_path)
        upgrade(self.engine)
        self.session_factory = make_session_factory(self.engine)
        with self.session_factory() as session:
            fetch_log.prune(session)
            session.commit()
        self.provider = provider or build_default(self.settings)

        self.cache = PayloadCacheService(self.session_factory, now)
        self.instruments = InstrumentService(self.session_factory)
        self.daily_bars = DailyBarService(self.session_factory, self.provider, now)
        self.financials = FinancialsService(self.session_factory, self.provider, self.cache, now)
        self.quotes = QuoteService(self.cache, self.provider, now)
        self.stock = StockService(self.provider, self.cache, self.daily_bars, self.financials, self.instruments, self.fx_rate, now)
        self.watchlist = WatchlistService(self.session_factory, self.quotes, now)
        self.rankings = RankingsService(self.instruments, self.quotes, self.financials, now)
        self.market = MarketService(self.provider, self.cache, self.quotes, self.instruments, now)
        self.news = NewsService(self.session_factory, self.cache, now, **({"collect": news_collect} if news_collect else {}))
        self.prefs = PrefsService(self.session_factory)
        self.refresh = RefreshService(self.session_factory, self.cache, self.financials, self.news)
        self.health = HealthService(self.session_factory, self.provider)

    def fx_rate(self) -> Cached:
        """USD per 1 KRW, cached 1 hour."""
        def fetch() -> Routed[float]:
            yahoo = self.provider.providers.get("yahoo")
            if yahoo is None or "yahoo" in self.provider.disabled:
                raise DataFetchError("fx_unavailable", "汇率数据源不可用。")
            return Routed(yahoo.krw_usd_rate(), yahoo.name, False)

        return self.cache.get("fx", "KRW_USD", fetch)

    def close(self) -> None:
        self.engine.dispose()
