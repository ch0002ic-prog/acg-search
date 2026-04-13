from __future__ import annotations

from urllib.parse import quote_plus

from app.config import Settings
from app.sources.base import BaseSource
from app.sources.curated import CuratedSource
from app.sources.eventbrite import EventbriteSource
from app.sources.rss import RssSource


def build_sources(settings: Settings) -> list[BaseSource]:
    google_news_include_keywords = [
        "anime",
        "manga",
        "donghua",
        "webtoon",
        "cosplay",
        "doujin",
        "idol",
        "anisong",
        "ani-idol",
        "ani idol",
        "artist alley",
        "anime festival asia",
        "afa",
        "singapore comic con",
        "sgcc",
        "hoyofest",
        "hoyo fest",
        "hoyoverse",
        "genshin",
        "honkai",
        "zenless",
        "jrpg",
        "rpg",
        "atlus",
        "persona",
        "final fantasy",
        "ffxiv",
        "ff14",
        "dragon quest",
        "macross",
        "naruto",
        "one piece",
        "demon slayer",
        "shonen jump",
        "figure",
        "collectible",
        "merch",
        "merchandise",
        "pop-up",
        "popup",
        "collab",
        "cafe",
        "mlbb",
        "mobile legends",
        "valorant",
        "vct",
        "riot games",
        "esports",
        "tournament",
        "qualifier",
        "playoffs",
        "grand archive",
        "tcg",
        "otaket",
        "poppa by moe moe q",
        "moe moe q",
        "mmq",
        "idol live",
        "merch signing",
    ]
    google_news_exclude_keywords = [
        "bitcoin",
        "crypto",
        "price in singapore dollar",
        "gambling regulator",
        "casino",
        "betting",
        "insurance coverage",
        "manufacturing",
        "trust centre",
        "security worldwide",
        "distributor licenses",
        "acquisition costs",
        "retention rises",
        "envoy persona non grata",
    ]
    publisher_feed_include_keywords = google_news_include_keywords + [
        "visual novel",
        "otome",
        "vtuber",
        "virtual youtuber",
        "wuthering waves",
        "blue archive",
        "nikke",
    ]
    singapore_query = quote_plus(
        "(anime OR gaming OR esports OR manga OR cosplay) Singapore"
    )
    event_query = quote_plus(
        '"Anime Festival Asia" OR "Singapore Comic Con" OR "HoyoFest Singapore" OR "MLBB Singapore" OR "POPPA" OR "Moe Moe Q" OR "Ani-Idol"'
    )
    jrpg_query = quote_plus(
        'JRPG OR "turn-based RPG" OR Persona OR Atlus OR Falcom OR "Final Fantasy"'
    )
    anime_query = quote_plus(
        '(anime OR manga OR donghua OR webtoon) (Singapore OR SEA OR seasonal)'
    )
    esports_query = quote_plus(
        '(MLBB OR Valorant OR esports) Singapore OR SEA'
    )
    merch_query = quote_plus(
        '(anime merch OR pop-up OR collab cafe OR collectibles) Singapore'
    )
    jrpg_demo_query = quote_plus(
        'JRPG demo OR "playable demo" OR Atlus demo OR "turn-based RPG demo"'
    )
    hoyofest_query = quote_plus(
        '"HoyoFest Singapore" OR "HoYo FEST" OR "Hoyo Fest" Singapore'
    )
    artist_alley_query = quote_plus(
        '"artist alley" Singapore anime OR comic con creator booth'
    )
    anime_convention_query = quote_plus(
        '"anime convention" Singapore OR "anime festival asia" OR "singapore comic con" OR "doujin market"'
    )
    gacha_query = quote_plus(
        '("Genshin Impact" OR "Honkai Star Rail" OR "Zenless Zone Zero" OR "Wuthering Waves" OR gacha) Singapore OR SEA'
    )
    tcg_query = quote_plus(
        '("Grand Archive" OR TCG OR "trading card game" OR "Weiss Schwarz" OR "Union Arena") Singapore OR SEA'
    )
    cosplay_query = quote_plus(
        '(cosplay OR cosplayer OR "cosplay competition" OR "anime costume") Singapore OR SEA'
    )
    gacha_keywords = [
        "genshin",
        "honkai",
        "zenless",
        "hoyoverse",
        "gacha",
        "wuthering waves",
        "blue archive",
        "nikke",
    ]
    tcg_keywords = [
        "grand archive",
        "tcg",
        "trading card game",
        "card game",
        "weiss schwarz",
        "union arena",
        "one piece card game",
        "pokemon tcg",
    ]
    cosplay_keywords = [
        "cosplay",
        "cosplayer",
        "cosplay competition",
        "anime festival asia",
        "afa",
        "singapore comic con",
        "sgcc",
        "hoyofest",
        "artist alley",
    ]
    bandwagon_keywords = [
        "gaming",
        "esports",
        "valorant",
        "mlbb",
        "dota",
        "league of legends",
        "anime",
        "manga",
        "cosplay",
        "idol",
        "anisong",
        "gacha",
        "jrpg",
        "playstation",
        "nintendo",
        "xbox",
        "steam",
        "tcg",
        "boardgame",
        "board game",
        "comics",
        "merch",
    ]
    eventbrite_anime_keywords = [
        "anime",
        "manga",
        "doujin",
        "cosplay",
        "idol",
        "anisong",
        "ani-idol",
        "ani idol",
        "poppa",
        "moe moe q",
        "mmq",
        "otaku",
        "artist alley",
        "tcg",
        "comic",
        "sgcc",
        "grand archive",
    ]
    eventbrite_gaming_keywords = [
        "gaming",
        "gamedev",
        "boardgame",
        "board game",
        "tcg",
        "playtest",
        "esports",
        "mlbb",
        "valorant",
        "dungeons",
        "dragons",
        "mahjong",
        "escape room",
        "game on",
    ]

    return [
        CuratedSource(
            name="SG Source Pages",
            feed_url="local://curated-sg-search-watch",
            file_path=settings.root_dir / "data" / "curated_articles.json",
            quality=0.8,
            source_type="curated",
            category_hints=["events", "anime", "merch"],
            region_hints=["Singapore"],
        ),
        RssSource(
            name="Siliconera",
            feed_url="https://www.siliconera.com/feed",
            quality=0.82,
            category_hints=["games", "anime", "merch"],
        ),
        RssSource(
            name="Bandwagon Asia",
            feed_url="https://www.bandwagon.asia/feeds/articles",
            quality=0.67,
            category_hints=["games", "esports", "anime"],
            region_hints=["Singapore", "SEA"],
            include_keywords=bandwagon_keywords,
        ),
        RssSource(
            name="Anime Festival Asia",
            feed_url="https://animefestival.asia/feed/",
            quality=0.86,
            category_hints=["events", "anime", "merch"],
            region_hints=["Singapore"],
        ),
        RssSource(
            name="RPG Site",
            feed_url="https://www.rpgsite.net/feed",
            quality=0.81,
            category_hints=["games", "anime"],
            include_keywords=publisher_feed_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Automaton West",
            feed_url="https://automaton-media.com/en/feed/",
            quality=0.79,
            category_hints=["games", "anime", "merch"],
            include_keywords=publisher_feed_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Noisy Pixel",
            feed_url="https://noisypixel.net/feed/",
            quality=0.78,
            category_hints=["games", "anime", "merch"],
            include_keywords=publisher_feed_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Kakuchopurei",
            feed_url="https://www.kakuchopurei.com/feed/",
            quality=0.77,
            category_hints=["games", "anime", "events"],
            region_hints=["SEA"],
            include_keywords=publisher_feed_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="GamesHub",
            feed_url="https://www.gameshub.com/feed/",
            quality=0.75,
            category_hints=["games", "anime"],
            include_keywords=publisher_feed_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Final Weapon",
            feed_url="https://finalweapon.net/feed/",
            quality=0.77,
            category_hints=["games", "anime", "merch"],
            include_keywords=publisher_feed_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        EventbriteSource(
            name="Eventbrite SG Anime",
            feed_url="https://www.eventbrite.sg/d/singapore/anime/",
            quality=0.78,
            source_type="event_listing",
            category_hints=["events", "anime", "manga", "merch"],
            region_hints=["Singapore"],
            include_keywords=eventbrite_anime_keywords,
        ),
        EventbriteSource(
            name="Eventbrite SG Gaming",
            feed_url="https://www.eventbrite.sg/d/singapore/gaming/",
            quality=0.76,
            source_type="event_listing",
            category_hints=["events", "games", "esports"],
            region_hints=["Singapore"],
            include_keywords=eventbrite_gaming_keywords,
        ),
        RssSource(
            name="Google News SG ACG",
            feed_url=f"https://news.google.com/rss/search?q={singapore_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.72,
            category_hints=["events", "games", "anime"],
            region_hints=["Singapore", "SEA"],
            include_keywords=google_news_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SG Events",
            feed_url=f"https://news.google.com/rss/search?q={event_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.74,
            category_hints=["events", "merch", "esports"],
            region_hints=["Singapore"],
            include_keywords=google_news_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News JRPG",
            feed_url=f"https://news.google.com/rss/search?q={jrpg_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.76,
            category_hints=["games"],
            include_keywords=google_news_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News JRPG Demo",
            feed_url=f"https://news.google.com/rss/search?q={jrpg_demo_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.8,
            category_hints=["games"],
            include_keywords=["demo", "playable demo", "prologue demo", "trial", "jrpg"],
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News Anime And Manga",
            feed_url=f"https://news.google.com/rss/search?q={anime_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.75,
            category_hints=["anime", "manga"],
            region_hints=["Singapore", "SEA"],
            include_keywords=google_news_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SEA Esports",
            feed_url=f"https://news.google.com/rss/search?q={esports_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.76,
            category_hints=["esports", "games"],
            region_hints=["Singapore", "SEA"],
            include_keywords=google_news_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News Merch And Deals",
            feed_url=f"https://news.google.com/rss/search?q={merch_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.73,
            category_hints=["merch", "events"],
            region_hints=["Singapore"],
            include_keywords=google_news_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News HoyoFest",
            feed_url=f"https://news.google.com/rss/search?q={hoyofest_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.79,
            category_hints=["events", "gacha", "merch"],
            region_hints=["Singapore", "SEA"],
            include_keywords=["hoyo fest", "hoyofest", "artist alley"],
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News Artist Alley",
            feed_url=f"https://news.google.com/rss/search?q={artist_alley_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.78,
            category_hints=["events", "anime", "merch"],
            region_hints=["Singapore", "SEA"],
            include_keywords=["artist alley", "anime festival asia", "afa", "singapore comic con", "sgcc", "hoyo fest", "hoyofest"],
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News Anime Conventions",
            feed_url=f"https://news.google.com/rss/search?q={anime_convention_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.79,
            category_hints=["events", "anime", "merch"],
            region_hints=["Singapore", "SEA"],
            include_keywords=["anime convention", "anime conventions", "anime festival asia", "afa", "singapore comic con", "sgcc", "doujin market"],
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SEA Gacha",
            feed_url=f"https://news.google.com/rss/search?q={gacha_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.78,
            category_hints=["games", "gacha", "merch"],
            region_hints=["Singapore", "SEA"],
            include_keywords=gacha_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SEA TCG",
            feed_url=f"https://news.google.com/rss/search?q={tcg_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.77,
            category_hints=["games", "merch", "events"],
            region_hints=["Singapore", "SEA"],
            include_keywords=tcg_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SG Cosplay",
            feed_url=f"https://news.google.com/rss/search?q={cosplay_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.76,
            category_hints=["events", "anime", "merch"],
            region_hints=["Singapore", "SEA"],
            include_keywords=cosplay_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
    ]
