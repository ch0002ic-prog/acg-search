from __future__ import annotations

from datetime import datetime, timezone
import unittest

from app.services.event_metadata import infer_event_metadata


class EventMetadataTests(unittest.TestCase):
    def test_event_listing_extracts_structured_date_and_venue(self) -> None:
        metadata = infer_event_metadata(
            title="Anime Drawing Workshop Singapore",
            summary="Venue: Suntec Singapore Convention & Exhibition Centre. Ends: 2026-11-23T18:00:00+08:00. Registration open now.",
            source_type="event_listing",
            published_at=datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc),
        )

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata.event_type, "workshop")
        self.assertEqual(metadata.venue, "Suntec Singapore Convention & Exhibition Centre")
        self.assertEqual(metadata.date_label, "23 Nov 2026")
        self.assertEqual(metadata.ticket_status, "Registration open")

    def test_event_story_extracts_guest_and_merch_signals(self) -> None:
        metadata = infer_event_metadata(
            title="AFA Singapore featuring LiSA and Aimer with exclusive merch booth announced",
            summary="Creator alley plans and tickets on sale now are now live for fans.",
            source_type="rss",
        )

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata.event_type, "festival")
        self.assertEqual(metadata.ticket_status, "Tickets on sale")
        self.assertEqual(metadata.guest_status, "Named guests mentioned")
        self.assertEqual(metadata.guest_names, ["LiSA", "Aimer"])
        self.assertEqual(metadata.merch_status, "Merch or booth updates mentioned")

    def test_bandwagon_source_extracts_ticket_window_and_venue_alias(self) -> None:
        metadata = infer_event_metadata(
            title="Bandwagon guide to Anime Festival Asia Singapore 2026",
            summary="Early bird sales open 14 Nov 2026 at Suntec Convention Centre featuring LiSA and Aimer.",
            source_type="rss",
            source_name="Bandwagon Asia",
        )

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata.event_type, "festival")
        self.assertEqual(metadata.date_label, "14 Nov 2026")
        self.assertEqual(metadata.venue, "Suntec Singapore Convention & Exhibition Centre")
        self.assertEqual(metadata.ticket_status, "Ticket window announced")
        self.assertEqual(metadata.guest_names, ["LiSA", "Aimer"])

    def test_afa_source_extracts_guest_colon_pattern_and_ticket_guide(self) -> None:
        metadata = infer_event_metadata(
            title="Anime Festival Asia Singapore guest lineup update",
            summary="Guests: LiSA, Aimer. Ticket guide for AFA Singapore is now live at Suntec Convention & Exhibition Centre.",
            source_type="rss",
            source_name="Anime Festival Asia",
        )

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata.event_type, "festival")
        self.assertEqual(metadata.venue, "Suntec Singapore Convention & Exhibition Centre")
        self.assertEqual(metadata.ticket_status, "Ticket guide available")
        self.assertEqual(metadata.guest_status, "Named guests mentioned")
        self.assertEqual(metadata.guest_names, ["LiSA", "Aimer"])


if __name__ == "__main__":
    unittest.main()