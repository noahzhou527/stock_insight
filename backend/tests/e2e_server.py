"""Backend for the Playwright smoke tests: the real app and SPA, but with the deterministic fake upstreams
from ``fakes.py``, a throw-away database and a clock pinned to an after-close Wednesday (no polling).

    .venv\\Scripts\\python -m backend.tests.e2e_server --port 8765

Needs ``frontend/dist`` (``npm run e2e`` builds it first). Never touches the network or ``data/``.
"""
from __future__ import annotations

import argparse
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import uvicorn

from backend.app.config import REPO_ROOT, Settings
from backend.app.main import create_app
from backend.app.news.fetcher import NewsItem
from backend.app.providers.composite import CompositeProvider
from backend.app.seed import seed_if_empty
from backend.app.services.container import Container
from backend.tests.fakes import SH, FakeEastmoney, FakeThs, FakeYahoo, Switch

TODAY = date(2026, 11, 11)  # Wednesday
NOW = datetime(2026, 11, 11, 16, 0, tzinfo=SH)


def fake_news(history, themes, now, hours):
    items = [NewsItem("A股收盘上涨（测试新闻）", "https://news.10jqka.com.cn/e2e.shtml", "同花顺", now - timedelta(hours=1), now),
             NewsItem("Fed holds rates (test item)", "https://finance.yahoo.com/e2e", "Yahoo", now - timedelta(hours=2), now)]
    return items, items, {"Yahoo": "RSS · 1/3 条", "同花顺": "7×24 · 1/4 条", "抖音": "不可用 · 0/3 条（测试）"}, ()


def build_app(db_dir: Path):
    switch = Switch()
    provider = CompositeProvider({"ths": FakeThs(switch, TODAY), "eastmoney": FakeEastmoney(switch, TODAY),
                                  "yahoo": FakeYahoo(switch, TODAY)})
    settings = Settings(db_path=db_dir / "e2e.db", frontend_dist=REPO_ROOT / "frontend" / "dist")
    container = Container(settings, provider, lambda: NOW, fake_news)
    with container.session_factory() as session:
        seed_if_empty(session)  # the built-in stock pool, same as a fresh install
    return create_app(settings, container)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not (REPO_ROOT / "frontend" / "dist" / "index.html").exists():
        raise SystemExit("frontend/dist 不存在：先运行 npm run build")
    with tempfile.TemporaryDirectory(prefix="stock-insight-e2e-") as tmp:
        app = build_app(Path(tmp))
        try:
            uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
        finally:
            app.state.container.close()


if __name__ == "__main__":
    main()
