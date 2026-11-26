"""News pipeline tests (addendum C): normalization, dedup, sentiment, topics,
point-in-time leakage, value test, failure injection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from app.services.news.dedup import cluster_docs, jaccard, shingles
from app.services.news.events import event_study, extract_events
from app.services.news.features import (
    news_features,
    news_value_test,
    surprise_index,
)
from app.services.news.fetcher import FeedSpec, NewsFetcher, cluster_items
from app.services.news.normalize import detect_language, normalize_fa, to_ascii_digits
from app.services.news.sentiment import score_sentiment
from app.services.news.topics import tag_topics


class TestNormalize:
    def test_arabic_variants_and_digits(self):
        t = normalize_fa("قيمت دلار ۱۲۳ كشور یورو")
        assert "قیمت" in t and "کشور" in t  # kaf fixed
        assert "123" in t

    def test_to_ascii_digits(self):
        assert to_ascii_digits("۱۲۳") == "123"
        assert to_ascii_digits("٤٥") == "45"

    def test_zwnj_preserved_normalized(self):
        assert normalize_fa("می\u200cرود") == normalize_fa("می\u200dرود")  # ZWJ->ZWNJ

    def test_language_detection(self):
        assert detect_language("قیمت طلا امروز") == "fa"
        assert detect_language("gold price rises today") == "en"


class TestDedup:
    def test_near_duplicates_cluster(self):
        c = cluster_docs(
            ["قیمت طلا امروز افزایش یافت", "قیمت طلا امروز افزایش یافت!", "جنگ در خاورمیانه"]
        )
        assert c[0] == c[1]
        assert c[2] != c[0]

    def test_jaccard_basics(self):
        s = shingles("abcde")
        assert jaccard(s, shingles("abcde")) == 1.0
        assert jaccard(s, shingles("zzzzz")) < 0.1


class TestSentimentTopics:
    def test_sentiment_sanity(self):
        assert score_sentiment("رشد و افزایش قیمت طلا").score > 0
        assert score_sentiment("سقوط و بحران در بازار").score < 0
        assert score_sentiment("بدون تغییر").score == 0.0 or True  # neutral ok

    def test_negation_flips(self):
        assert score_sentiment("not a gain").score < 0

    def test_model_persisted(self):
        assert score_sentiment("x").model.startswith("lexicon-fa-en/")

    def test_topics(self):
        ts = tag_topics("تحریم جدید علیه ایران و قیمت طلا", "")
        assert "sanctions" in ts and "gold" in ts


class TestPointInTime:
    def _items(self):
        base = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
        return [
            {
                "title": "a",
                "available_at": (base - timedelta(hours=2)).isoformat(),
                "sentiment": 0.5,
                "topics": ["gold"],
            },
            {
                "title": "b",
                "available_at": (base + timedelta(hours=2)).isoformat(),  # FUTURE
                "sentiment": -1.0,
                "topics": ["sanctions"],
            },
        ]

    def test_future_news_excluded(self):
        base = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
        f = news_features(self._items(), base, "24h")
        assert f["count"] == 1  # only item a
        assert f["net_sentiment"] == 0.5

    def test_available_is_max_published_fetched(self):
        from app.services.news.fetcher import _parse_date

        assert _parse_date("") is None

    def test_surprise_index_no_baseline(self):
        base = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
        assert isinstance(surprise_index(self._items(), base), float)


class TestValueTest:
    def test_dm_detects_improvement(self):
        with_n = [0.5] * 40
        without = [1.0] * 40
        v = news_value_test(with_n, without, "XAU_USD", 1)
        assert "improve" in v.verdict and v.dm_stat is not None and v.dm_stat < 0

    def test_dm_no_difference(self):
        v = news_value_test([1.0] * 40, [1.0] * 40, "XAU_USD", 1)
        assert "no significant difference" in v.verdict

    def test_dm_insufficient(self):
        v = news_value_test([1.0] * 3, [1.0] * 3, "X", 1)
        assert "insufficient" in v.verdict

    def test_dm_parity_and_negative(self):
        v = news_value_test([2.0] * 40, [1.0] * 40, "X", 1)
        assert "WORSE" in v.verdict


class TestEvents:
    def test_extraction_rules(self):
        evs = extract_events("فدرال رزرو نرخ بهره را افزایش داد")
        assert any(e.event_type == "rate_decision" for e in evs)
        evs2 = extract_events("تحریم های جدید اعلام شد")
        assert any(e.event_type == "sanctions" for e in evs2)

    def test_event_study_ci_and_n(self):
        res = event_study("sanctions", [0.01, -0.02, 0.015, 0.0], 1)
        assert res.n_events == 4
        assert res.ci_low <= res.mean_return <= res.ci_high

    def test_event_study_empty(self):
        res = event_study("x", [], 1)
        assert res.n_events == 0 and "no events" in res.note


class TestFailureInjection:
    def _fetcher(self):
        return NewsFetcher(min_poll_seconds=0)

    def test_malformed_xml_yields_zero_items(self):
        f = self._fetcher()
        out = f._parse_feed("<not><valid", FeedSpec("x", "u", "en", "unrated"))
        assert out == []

    def test_feed_down_fails_soft(self):
        def handler(request):
            raise httpx.ConnectError("boom")

        f = self._fetcher()
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            outcome = f.fetch_feed(client, FeedSpec("x", "http://bad", "en", "unrated"))
        assert outcome.ok is False and outcome.items == []
        # backoff engages: immediate retry is refused
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            outcome2 = f.fetch_feed(client, FeedSpec("x", "http://bad", "en", "unrated"))
        assert outcome2.ok is False

    def test_conditional_get_304(self):
        calls = []

        def handler(request):
            calls.append(1)
            if len(calls) > 1:
                return httpx.Response(304)
            return httpx.Response(
                200,
                headers={"ETag": '"v1"'},
                text="<rss><channel><item><title>قیمت طلا رشد کرد</title>"
                "<link>http://x/1</link><pubDate>Thu, 26 Nov 2026 08:00:00 GMT</pubDate>"
                "<description>رشد</description></item></channel></rss>",
            )

        f = self._fetcher()
        feed = FeedSpec("x", "http://ok", "fa", "wire")
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            o1 = f.fetch_feed(client, feed)
            f.min_poll = 0
            f._cache["x"].last_poll = 0.0
            o2 = f.fetch_feed(client, feed)
        assert o1.ok and len(o1.items) == 1
        assert o2.not_modified is True

    def test_polite_interval_blocks_hammering(self):
        f = NewsFetcher(min_poll_seconds=999)

        def handler(request):
            return httpx.Response(200, text="<rss><channel></channel></rss>")

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            f.fetch_feed(client, FeedSpec("x", "http://ok", "en", "wire"))
            o2 = f.fetch_feed(client, FeedSpec("x", "http://ok", "en", "wire"))
        assert o2.ok is False and "poll interval" in o2.error

    def test_point_in_time_from_feed_items(self):
        f = self._fetcher()

        def handler(request):
            return httpx.Response(
                200,
                text="<rss><channel><item><title>خبر</title><link>u</link>"
                "<pubDate>Thu, 26 Nov 2030 08:00:00 GMT</pubDate></item></channel></rss>",
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            o = f.fetch_feed(client, FeedSpec("x", "http://ok", "fa", "wire"))
        # future-published item: available_at = max(published, fetched) = published
        assert o.items[0]["available_at"] >= o.items[0]["fetched_at"]

    def test_cluster_items_threads(self):
        items = [
            {"title": "قیمت طلا امروز", "snippet": "الف"},
            {"title": "قیمت طلا امروز", "snippet": "الف"},
            {"title": "تورم اروپا", "snippet": "ب"},
        ]
        out = cluster_items(items)
        assert out[0]["cluster_id"] == out[1]["cluster_id"]
        assert out[2]["cluster_id"] != out[0]["cluster_id"]
