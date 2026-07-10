import unittest
from datetime import datetime, timedelta, timezone

from news_fetcher import (
    NewsItem,
    _parse_douyin_payload,
    _parse_tonghuashun_html,
    _parse_yahoo_rss,
    _select_for_display,
)


class NewsFetcherTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc)

    def test_yahoo_rss_keeps_original_title_and_time(self):
        fixture = b"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel><item>
          <title>Markets rally after inflation report</title>
          <link>https://finance.yahoo.com/news/example</link>
          <pubDate>Fri, 10 Jul 2026 07:00:00 GMT</pubDate>
        </item></channel></rss>"""
        items = _parse_yahoo_rss(fixture, self.now)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Markets rally after inflation report")
        self.assertEqual(items[0].source, "Yahoo")

    def test_tonghuashun_and_douyin_parsers(self):
        ths_fixture = """
        <div class="arc-title">07月10日 15:20
          <a href="https://news.10jqka.com.cn/20260710/c700000000.shtml"
             title="央行发布最新金融数据">央行发布最新金融数据</a>
        </div>"""
        ths_items = _parse_tonghuashun_html(
            ths_fixture, "https://news.10jqka.com.cn/", self.now
        )
        self.assertEqual(len(ths_items), 1)
        self.assertEqual(ths_items[0].source, "同花顺")

        douyin_items = _parse_douyin_payload(
            {"status_code": 0, "word_list": [{"word": "A股收盘大涨"}, {"word": "夏日旅行攻略"}]},
            self.now,
        )
        self.assertEqual([item.title for item in douyin_items], ["A股收盘大涨"])
        self.assertIsNone(douyin_items[0].published_at)
        self.assertEqual(douyin_items[0].observed_at, self.now)

    def test_fixed_source_quotas_and_global_order(self):
        items = []
        for source, total in (("Yahoo", 5), ("同花顺", 6), ("抖音", 4)):
            for index in range(total):
                stamp = self.now - timedelta(minutes=index + len(items))
                items.append(
                    NewsItem(
                        title=f"{source}-{index}",
                        url=f"https://example.com/{source}/{index}",
                        source=source,
                        published_at=None if source == "抖音" else stamp,
                        observed_at=stamp,
                    )
                )
        selected = _select_for_display(items, 72, self.now)
        self.assertEqual(len(selected), 10)
        self.assertEqual(sum(item.source == "Yahoo" for item in selected), 3)
        self.assertEqual(sum(item.source == "同花顺" for item in selected), 4)
        self.assertEqual(sum(item.source == "抖音" for item in selected), 3)
        self.assertEqual(selected, sorted(selected, key=lambda item: item.effective_time, reverse=True))


if __name__ == "__main__":
    unittest.main()
