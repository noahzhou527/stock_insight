import unittest
from datetime import datetime, timezone

from news_fetcher import (
    _parse_douyin_payload,
    _parse_tonghuashun_html,
    _parse_yahoo_rss,
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
            {
                "status_code": 0,
                "word_list": [
                    {"word": "A股收盘大涨"},
                    {"word": "现货黄金价格上涨"},
                    {"word": "我国商业航天燃料实现多元化突破"},
                    {"word": "一人一句致敬比利时黄金一代"},
                    {"word": "夏日旅行攻略"},
                ],
            },
            self.now,
            market_themes=("商业航天", "黄金概念"),
        )
        self.assertEqual(
            [item.title for item in douyin_items],
            ["A股收盘大涨", "现货黄金价格上涨", "我国商业航天燃料实现多元化突破"],
        )
        self.assertIsNone(douyin_items[0].published_at)
        self.assertEqual(douyin_items[0].observed_at, self.now)
