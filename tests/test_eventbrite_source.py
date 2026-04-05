from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from app.sources.eventbrite import EventbriteSource


EVENTBRITE_HTML = """
<html>
  <head></head>
  <body>
    <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "itemListElement": [
          {
            "@type": "ListItem",
            "item": {
              "@type": "Event",
              "name": "Doujin Market 2026",
              "url": "https://eventbrite.sg/e/doujin-market-2026",
              "description": "Singapore creator convention with indie artists and fan goods.",
              "startDate": "2026-05-09T10:00:00+08:00",
              "endDate": "2026-05-10T18:00:00+08:00",
              "image": "https://images.example.com/doujin.jpg",
              "location": {
                "@type": "Place",
                "name": "Suntec Singapore Convention & Exhibition Centre"
              },
              "offers": {
                "@type": "Offer",
                "url": "https://eventbrite.sg/e/doujin-market-2026/tickets",
                "availability": "https://schema.org/InStock"
              },
              "performer": [
                {"@type": "Person", "name": "LiSA"},
                {"@type": "Person", "name": "Aimer"}
              ]
            }
          }
        ]
      }
    </script>
  </body>
</html>
"""


class EventbriteSourceTests(unittest.TestCase):
    @patch("app.sources.eventbrite.httpx.get")
    def test_fetch_carries_structured_event_metadata(self, mock_get: Mock) -> None:
        mock_response = Mock()
        mock_response.text = EVENTBRITE_HTML
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        source = EventbriteSource(
            name="Eventbrite SG Anime",
            feed_url="https://example.com/eventbrite",
            source_type="event_listing",
            category_hints=["events"],
            region_hints=["Singapore"],
        )

        articles = source.fetch(limit=1)

        self.assertEqual(len(articles), 1)
        self.assertIsNotNone(articles[0].event_metadata)
        self.assertEqual(articles[0].event_metadata.date_label, "9 May 2026 to 10 May 2026")
        self.assertEqual(articles[0].event_metadata.venue, "Suntec Singapore Convention & Exhibition Centre")
        self.assertEqual(articles[0].event_metadata.ticket_status, "Tickets on sale")
        self.assertEqual(articles[0].event_metadata.ticket_url, "https://eventbrite.sg/e/doujin-market-2026/tickets")
        self.assertEqual(articles[0].event_metadata.guest_names, ["LiSA", "Aimer"])


if __name__ == "__main__":
    unittest.main()