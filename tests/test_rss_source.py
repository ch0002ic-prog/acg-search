from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest.mock import patch

import httpx

from app.sources.rss import GOOGLE_NEWS_URL_CACHE, RssSource


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.com")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("request failed", request=request, response=response)


class FakeClient:
    def __init__(
        self,
        responses: dict[tuple[str, str], FakeResponse] | None = None,
        errors: dict[tuple[str, str], Exception] | None = None,
    ) -> None:
        self.responses = responses or {}
        self.errors = errors or {}
        self.calls: list[tuple[str, str]] = []

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def get(self, url: str, *args, **kwargs) -> FakeResponse:
        self.calls.append(("GET", url))
        if ("GET", url) in self.errors:
            raise self.errors[("GET", url)]
        return self.responses[("GET", url)]

    def post(self, url: str, *args, **kwargs) -> FakeResponse:
        self.calls.append(("POST", url))
        if ("POST", url) in self.errors:
            raise self.errors[("POST", url)]
        return self.responses[("POST", url)]


class FakeClientFactory:
    def __init__(self, clients: list[FakeClient]) -> None:
        self.clients = list(clients)
        self.calls: list[dict[str, object]] = []

    def __call__(self, *args, **kwargs) -> FakeClient:
        self.calls.append(dict(kwargs))
        if not self.clients:
            raise AssertionError("Unexpected extra client creation")
        return self.clients.pop(0)


class RssSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        GOOGLE_NEWS_URL_CACHE.clear()

    def _build_google_news_feed(self, wrapper_url: str) -> str:
        return f"""
        <rss version="2.0">
          <channel>
            <item>
              <title>Anime Festival Asia Singapore 2025 Is Back</title>
              <link>{wrapper_url}</link>
              <description><![CDATA[Anime Festival Asia returns to Singapore.]]></description>
              <pubDate>Tue, 08 Apr 2025 12:00:00 GMT</pubDate>
              <source url="https://www.timeout.com">Time Out</source>
            </item>
          </channel>
        </rss>
        """

    def _build_simple_feed(self, article_url: str = "https://example.com/story") -> str:
        return f"""
        <rss version="2.0">
          <channel>
            <item>
              <title>Sample Story</title>
              <link>{article_url}</link>
              <description><![CDATA[Sample summary.]]></description>
              <pubDate>Tue, 08 Apr 2025 12:00:00 GMT</pubDate>
            </item>
          </channel>
        </rss>
        """

    def test_fetch_decodes_google_news_wrapper_urls(self) -> None:
        feed_url = "https://news.google.com/rss/search?q=afa&hl=en-SG&gl=SG&ceid=SG:en"
        wrapper_url = "https://news.google.com/rss/articles/CBMiVkFVX3lxTE4zaGU2bTY2ZGkzdTRkSkJ0cFpsTGlDUjkxU2FBRURaTWU0c3QzVWZ1MHZZNkZ5Vzk1ZVBnTDFHY2R6ZmdCUkpUTUJsS1pqQTlCRzlzbHV3?oc=5"
        article_page_url = "https://news.google.com/articles/CBMiVkFVX3lxTE4zaGU2bTY2ZGkzdTRkSkJ0cFpsTGlDUjkxU2FBRURaTWU0c3QzVWZ1MHZZNkZ5Vzk1ZVBnTDFHY2R6ZmdCUkpUTUJsS1pqQTlCRzlzbHV3"
        decoded_url = "https://www.timeout.com/singapore/things-to-do/anime-festival-asia-singapore-2025"
        client = FakeClient(
            {
                ("GET", feed_url): FakeResponse(self._build_google_news_feed(wrapper_url)),
                ("GET", article_page_url): FakeResponse('<c-wiz><div jscontroller="abc" data-n-a-sg="sig-token" data-n-a-ts="1744113600"></div></c-wiz>'),
                (
                    "POST",
                    "https://news.google.com/_/DotsSplashUi/data/batchexecute?rpcids=Fbv4je",
                ): FakeResponse(
                    ')]}\'\n\n[["wrb.fr","Fbv4je","[\\"garturlres\\",\\"'
                    + decoded_url
                    + '\\",1]",null,null,null,""]]'
                ),
            }
        )

        source = RssSource(name="Google News SG Events", feed_url=feed_url)
        with patch("app.sources.rss.httpx.Client", return_value=client):
            articles = source.fetch(limit=3)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].url, decoded_url)
        self.assertEqual(articles[0].published_at, datetime(2025, 4, 8, 12, 0, tzinfo=timezone.utc))

    def test_fetch_falls_back_to_wrapper_when_decode_params_are_missing(self) -> None:
        feed_url = "https://news.google.com/rss/search?q=afa&hl=en-SG&gl=SG&ceid=SG:en"
        wrapper_url = "https://news.google.com/rss/articles/CBMiVkFVX3lxTE4zaGU2bTY2ZGkzdTRkSkJ0cFpsTGlDUjkxU2FBRURaTWU0c3QzVWZ1MHZZNkZ5Vzk1ZVBnTDFHY2R6ZmdCUkpUTUJsS1pqQTlCRzlzbHV3?oc=5"
        article_page_url = "https://news.google.com/articles/CBMiVkFVX3lxTE4zaGU2bTY2ZGkzdTRkSkJ0cFpsTGlDUjkxU2FBRURaTWU0c3QzVWZ1MHZZNkZ5Vzk1ZVBnTDFHY2R6ZmdCUkpUTUJsS1pqQTlCRzlzbHV3"
        client = FakeClient(
            {
                ("GET", feed_url): FakeResponse(self._build_google_news_feed(wrapper_url)),
                ("GET", article_page_url): FakeResponse("<html><body>missing attrs</body></html>"),
                ("GET", "https://news.google.com/rss/articles/CBMiVkFVX3lxTE4zaGU2bTY2ZGkzdTRkSkJ0cFpsTGlDUjkxU2FBRURaTWU0c3QzVWZ1MHZZNkZ5Vzk1ZVBnTDFHY2R6ZmdCUkpUTUJsS1pqQTlCRzlzbHV3"): FakeResponse("<html><body>still missing attrs</body></html>"),
            }
        )

        source = RssSource(name="Google News SG Events", feed_url=feed_url)
        with patch("app.sources.rss.httpx.Client", return_value=client):
            articles = source.fetch(limit=3)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].url, wrapper_url)

    def test_fetch_retries_timeout_up_to_max_attempts_and_uses_source_timeout(self) -> None:
        feed_url = "https://example.com/feed.xml"
        timeout_error = httpx.ReadTimeout("timed out", request=httpx.Request("GET", feed_url))
        factory = FakeClientFactory(
            [
                FakeClient(errors={("GET", feed_url): timeout_error}),
                FakeClient(responses={("GET", feed_url): FakeResponse(self._build_simple_feed())}),
            ]
        )

        source = RssSource(name="Retry Feed", feed_url=feed_url, request_timeout_seconds=20.0, max_attempts=3)
        with patch("app.sources.rss.httpx.Client", side_effect=factory):
            articles = source.fetch(limit=3)

        self.assertEqual(len(articles), 1)
        self.assertEqual(len(factory.calls), 2)
        self.assertEqual(factory.calls[0]["timeout"], 20.0)
        self.assertTrue(all(call["timeout"] == 20.0 for call in factory.calls))

    def test_fetch_stops_after_three_attempts_on_repeated_timeout(self) -> None:
        feed_url = "https://example.com/feed.xml"
        factory = FakeClientFactory(
            [
                FakeClient(errors={("GET", feed_url): httpx.ReadTimeout("timed out", request=httpx.Request("GET", feed_url))}),
                FakeClient(errors={("GET", feed_url): httpx.ReadTimeout("timed out", request=httpx.Request("GET", feed_url))}),
                FakeClient(errors={("GET", feed_url): httpx.ReadTimeout("timed out", request=httpx.Request("GET", feed_url))}),
            ]
        )

        source = RssSource(name="Retry Feed", feed_url=feed_url, request_timeout_seconds=20.0, max_attempts=3)
        with patch("app.sources.rss.httpx.Client", side_effect=factory):
            with self.assertRaises(httpx.ReadTimeout):
                source.fetch(limit=3)

        self.assertEqual(len(factory.calls), 3)


if __name__ == "__main__":
    unittest.main()
