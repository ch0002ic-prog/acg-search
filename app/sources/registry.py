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
        "hololive",
        "nijisanji",
        "vshojo",
        "vocaloid",
        "seiyuu",
        "wuthering waves",
        "blue archive",
        "nikke",
        "pokemon",
        "nendoroid",
        "figma",
        "gunpla",
        "model kit",
        "gundam",
        "street fighter",
        "tekken",
        "guilty gear",
        "fighting game",
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
    vtuber_query = quote_plus(
        '(VTuber OR "virtual youtuber" OR Hololive OR Nijisanji OR VShojo OR Vocaloid) Singapore OR SEA'
    )
    figure_query = quote_plus(
        '("anime figure" OR nendoroid OR figma OR "scale figure" OR gunpla OR "model kit") Singapore OR SEA'
    )
    fighting_game_query = quote_plus(
        '("Street Fighter 6" OR "Tekken 8" OR "Guilty Gear" OR FGC OR "fighting game tournament") Singapore OR SEA'
    )
    anisong_query = quote_plus(
        '(anisong OR "anime concert" OR "anime music" OR seiyuu OR vocaloid OR "idol live") Singapore OR SEA'
    )
    visual_novel_query = quote_plus(
        '("visual novel" OR otome OR "dating sim" OR "Type-Moon" OR "Fate/Grand Order" OR "Steins;Gate") Singapore OR SEA'
    )
    collab_cafe_query = quote_plus(
        '("collab cafe" OR "collaboration cafe" OR "anime cafe" OR "pop-up cafe" OR "character cafe") Singapore OR SEA'
    )
    gunpla_query = quote_plus(
        '(gunpla OR gundam OR "model kit" OR plamo OR "Bandai Spirits") Singapore OR SEA'
    )
    ffxiv_query = quote_plus(
        '("Final Fantasy XIV" OR FFXIV OR FF14 OR Dawntrail OR "Final Fantasy XIV Fan Festival") Singapore OR SEA'
    )
    popup_store_query = quote_plus(
        '(("pop-up store" OR "popup store" OR exhibition OR showcase) AND (anime OR manga OR gaming OR character OR merch OR gacha OR vtuber)) Singapore OR SEA'
    )
    rhythm_game_query = quote_plus(
        '(("rhythm game" OR arcade OR maimai OR chunithm OR taiko OR "Project Sekai" OR "Hatsune Miku") AND (Singapore OR SEA))'
    )
    doujin_market_query = quote_plus(
        '((doujin OR doujinshi OR "creator market" OR "artist market" OR indie creators) AND (Singapore OR SEA) AND (anime OR manga OR cosplay OR illustration OR merch))'
    )
    anime_screening_query = quote_plus(
        '((anime film OR anime movie OR screening OR theatrical release OR concert film) AND (Singapore OR SEA) AND (anime OR manga OR Japanese))'
    )
    convention_guest_query = quote_plus(
        '(("guest announcement" OR "guest reveal" OR "special guest" OR "featured guest" OR "voice actor appearance" OR "cosplay guest") AND ("anime festival asia" OR "singapore comic con" OR "comic con" OR "anime convention") AND (Singapore OR SEA))'
    )
    creator_hub_query = quote_plus(
        '(("creator hub" OR "creators hub" OR "cosplay hub" OR "creator booth" OR "artist booth" OR "fan merchandise") AND ("anime festival asia" OR "comic con" OR convention OR festival) AND (Singapore OR SEA))'
    )
    anime_exhibition_query = quote_plus(
        '((exhibition OR gallery OR showcase OR museum OR installation) AND (anime OR manga OR gaming OR character OR "pop culture") AND (Singapore OR SEA))'
    )
    tokusatsu_query = quote_plus(
        '((tokusatsu OR "Kamen Rider" OR Ultraman OR "Super Sentai" OR Godzilla) AND (event OR screening OR exhibition OR merch OR "pop-up" OR showcase) AND (Singapore OR SEA))'
    )
    vtuber_concert_query = quote_plus(
        '((VTuber OR "virtual youtuber" OR Hololive OR Nijisanji OR Vocaloid OR "virtual singer") AND (concert OR live OR festival OR screening OR stage OR meetup) AND (Singapore OR SEA))'
    )
    capsule_toy_query = quote_plus(
        '((gashapon OR "capsule toy" OR "Ichiban Kuji" OR "Tamashii Nations" OR "blind box") AND (anime OR manga OR game OR merch OR collectible) AND (Singapore OR SEA))'
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
    vtuber_keywords = [
        "vtuber",
        "virtual youtuber",
        "hololive",
        "nijisanji",
        "vshojo",
        "vocaloid",
        "seiyuu",
    ]
    figure_keywords = [
        "figure",
        "collectible",
        "nendoroid",
        "figma",
        "scale figure",
        "gunpla",
        "model kit",
        "gundam",
        "plush",
        "acrylic stand",
    ]
    fighting_game_keywords = [
        "street fighter",
        "tekken",
        "guilty gear",
        "fighting game",
        "fgc",
        "capcom cup",
        "arc world tour",
    ]
    anisong_keywords = [
        "anisong",
        "anime concert",
        "anime music",
        "seiyuu",
        "vocaloid",
        "idol live",
        "love live",
        "bang dream",
    ]
    visual_novel_keywords = [
        "visual novel",
        "otome",
        "dating sim",
        "type-moon",
        "fate/grand order",
        "fate/stay night",
        "steins;gate",
        "clannad",
        "umineko",
        "higurashi",
        "tsukihime",
    ]
    collab_cafe_keywords = [
        "collab cafe",
        "collaboration cafe",
        "anime cafe",
        "pop-up cafe",
        "popup cafe",
        "character cafe",
        "themed cafe",
    ]
    gunpla_keywords = [
        "gunpla",
        "gundam",
        "model kit",
        "plamo",
        "bandai spirits",
    ]
    ffxiv_keywords = [
        "final fantasy xiv",
        "ffxiv",
        "ff14",
        "dawntrail",
        "fan festival",
        "lodestone",
        "square enix",
    ]
    popup_store_keywords = [
        "pop-up store",
        "popup store",
        "anime pop-up",
        "themed pop-up",
        "character pop-up",
        "exhibition",
        "showcase",
        "merch",
    ]
    rhythm_game_keywords = [
        "rhythm game",
        "arcade",
        "maimai",
        "chunithm",
        "taiko",
        "project sekai",
        "hatsune miku",
        "sound voltex",
        "sdvx",
        "ongeki",
    ]
    doujin_market_keywords = [
        "doujin",
        "doujinshi",
        "creator market",
        "artist market",
        "indie creators",
        "artist alley",
        "illustration",
        "fan merch",
    ]
    anime_screening_keywords = [
        "anime film",
        "anime movie",
        "screening",
        "theatrical release",
        "concert film",
        "cinema",
        "premiere",
    ]
    convention_guest_keywords = [
        "guest announcement",
        "guest reveal",
        "special guest",
        "featured guest",
        "voice actor",
        "cosplay guest",
        "meet and greet",
        "panel",
    ]
    creator_hub_keywords = [
        "creator hub",
        "creators hub",
        "cosplay hub",
        "creator booth",
        "artist booth",
        "fan merchandise",
        "illustrator",
        "crafters",
    ]
    anime_exhibition_keywords = [
        "anime exhibition",
        "manga exhibition",
        "art exhibition",
        "showcase",
        "museum",
        "gallery",
        "pop-up exhibition",
        "installation",
    ]
    tokusatsu_keywords = [
        "tokusatsu",
        "kamen rider",
        "ultraman",
        "super sentai",
        "godzilla",
        "hero show",
        "special effects",
    ]
    vtuber_concert_keywords = [
        "vtuber",
        "virtual youtuber",
        "hololive",
        "nijisanji",
        "vocaloid",
        "virtual singer",
        "live viewing",
        "hatsune miku",
    ]
    capsule_toy_keywords = [
        "gashapon",
        "capsule toy",
        "ichiban kuji",
        "tamashii nations",
        "blind box",
        "bandai namco",
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
        CuratedSource(
            name="SEA Merch News Pages",
            feed_url="local://curated-sea-merch-watch",
            file_path=settings.root_dir / "data" / "curated_merch_articles.json",
            quality=0.79,
            source_type="curated",
            category_hints=["merch", "anime", "events"],
            region_hints=["Singapore", "SEA"],
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
            name="Honey's Anime",
            feed_url="https://honeysanime.com/feed/",
            quality=0.8,
            category_hints=["anime", "manga", "events", "games"],
            include_keywords=publisher_feed_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
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
            name="Nintendo Everything",
            feed_url="https://nintendoeverything.com/feed/",
            quality=0.77,
            category_hints=["games", "anime", "merch"],
            include_keywords=publisher_feed_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="NookGaming",
            feed_url="https://www.nookgaming.com/feed/",
            quality=0.78,
            category_hints=["games", "anime", "manga"],
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
        RssSource(
            name="RPGamer",
            feed_url="https://rpgamer.com/feed/",
            quality=0.8,
            category_hints=["games", "anime"],
            include_keywords=publisher_feed_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Niche Gamer",
            feed_url="https://nichegamer.com/feed/",
            quality=0.75,
            category_hints=["games", "anime", "merch"],
            include_keywords=publisher_feed_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Anime Corner",
            feed_url="https://animecorner.me/feed/",
            quality=0.8,
            category_hints=["anime", "manga", "events"],
            exclude_keywords=google_news_exclude_keywords,
        ),
        RssSource(
            name="Otaku USA",
            feed_url="https://otakuusamagazine.com/feed/",
            quality=0.77,
            category_hints=["anime", "manga", "games", "merch"],
            exclude_keywords=google_news_exclude_keywords,
        ),
        RssSource(
            name="Crunchyroll News",
            feed_url="https://cr-news-api-service.prd.crunchyrollsvc.com/v1/en-US/rss",
            quality=0.79,
            category_hints=["anime", "manga", "games", "events"],
            include_keywords=publisher_feed_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="DualShockers",
            feed_url="https://www.dualshockers.com/feed/",
            quality=0.75,
            category_hints=["games", "anime", "merch"],
            include_keywords=publisher_feed_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Tokyo Otaku Mode",
            feed_url="https://otakumode.com/news/feed",
            quality=0.78,
            category_hints=["merch", "anime", "events"],
            include_keywords=publisher_feed_include_keywords + figure_keywords + collab_cafe_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Anime Feminist",
            feed_url="https://www.animefeminist.com/feed/",
            quality=0.74,
            category_hints=["anime", "manga", "events"],
            include_keywords=google_news_include_keywords + visual_novel_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Final Fantasy XIV News",
            feed_url="https://na.finalfantasyxiv.com/lodestone/news/topics.xml",
            quality=0.79,
            category_hints=["games", "events"],
            exclude_keywords=google_news_exclude_keywords,
        ),
        RssSource(
            name="Geek Culture",
            feed_url="https://geekculture.co/feed/",
            quality=0.75,
            category_hints=["games", "anime", "merch", "events"],
            region_hints=["Singapore", "SEA"],
            include_keywords=publisher_feed_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Esports.gg",
            feed_url="https://esports.gg/feed/",
            quality=0.76,
            category_hints=["esports", "games"],
            region_hints=["SEA"],
            include_keywords=publisher_feed_include_keywords + ["street fighter", "tekken", "guilty gear", "fgc"],
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Operation Rainfall",
            feed_url="https://operationrainfall.com/feed/",
            quality=0.77,
            category_hints=["games", "anime", "manga"],
            include_keywords=publisher_feed_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Anime Hunch",
            feed_url="https://animehunch.com/feed/",
            quality=0.78,
            category_hints=["anime", "manga"],
            exclude_keywords=google_news_exclude_keywords,
        ),
        RssSource(
            name="Anime Trending",
            feed_url="https://anitrendz.net/news/feed/",
            quality=0.78,
            category_hints=["anime", "manga", "events"],
            exclude_keywords=google_news_exclude_keywords,
        ),
        RssSource(
            name="Rice Digital",
            feed_url="https://ricedigital.co.uk/feed/",
            quality=0.76,
            category_hints=["games", "anime", "manga", "merch"],
            include_keywords=publisher_feed_include_keywords + visual_novel_keywords + ["vtuber", "hololive"],
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="MonsterVine",
            feed_url="https://monstervine.com/feed/",
            quality=0.74,
            category_hints=["games", "anime", "merch"],
            include_keywords=publisher_feed_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="J-List Blog",
            feed_url="https://blog.jlist.com/feed/",
            quality=0.78,
            category_hints=["anime", "manga", "merch"],
            include_keywords=publisher_feed_include_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Esports Insider",
            feed_url="https://esportsinsider.com/feed",
            quality=0.77,
            category_hints=["esports", "games", "events"],
            region_hints=["SEA"],
            include_keywords=publisher_feed_include_keywords + ["counter-strike", "cs2", "street fighter", "tekken", "fgc"],
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
        RssSource(
            name="Google News SEA VTubers",
            feed_url=f"https://news.google.com/rss/search?q={vtuber_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.77,
            category_hints=["anime", "merch", "events"],
            region_hints=["Singapore", "SEA"],
            include_keywords=vtuber_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SG Figures",
            feed_url=f"https://news.google.com/rss/search?q={figure_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.76,
            category_hints=["merch", "anime", "events"],
            region_hints=["Singapore", "SEA"],
            include_keywords=figure_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SEA Fighting Games",
            feed_url=f"https://news.google.com/rss/search?q={fighting_game_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.77,
            category_hints=["esports", "games", "events"],
            region_hints=["Singapore", "SEA"],
            include_keywords=fighting_game_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SG Anisong",
            feed_url=f"https://news.google.com/rss/search?q={anisong_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.76,
            category_hints=["events", "anime", "merch"],
            region_hints=["Singapore", "SEA"],
            include_keywords=anisong_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SEA Visual Novels",
            feed_url=f"https://news.google.com/rss/search?q={visual_novel_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.77,
            category_hints=["games", "anime", "manga"],
            region_hints=["Singapore", "SEA"],
            include_keywords=visual_novel_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SG Collab Cafes",
            feed_url=f"https://news.google.com/rss/search?q={collab_cafe_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.76,
            category_hints=["events", "anime", "merch"],
            region_hints=["Singapore", "SEA"],
            include_keywords=collab_cafe_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SEA Gunpla",
            feed_url=f"https://news.google.com/rss/search?q={gunpla_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.77,
            category_hints=["merch", "anime", "games"],
            region_hints=["Singapore", "SEA"],
            include_keywords=gunpla_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SEA FFXIV",
            feed_url=f"https://news.google.com/rss/search?q={ffxiv_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.77,
            category_hints=["games", "events", "anime"],
            region_hints=["Singapore", "SEA"],
            include_keywords=ffxiv_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SG Pop-Up Stores",
            feed_url=f"https://news.google.com/rss/search?q={popup_store_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.76,
            category_hints=["events", "anime", "merch"],
            region_hints=["Singapore", "SEA"],
            include_keywords=popup_store_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SEA Rhythm Games",
            feed_url=f"https://news.google.com/rss/search?q={rhythm_game_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.77,
            category_hints=["games", "events", "anime"],
            region_hints=["Singapore", "SEA"],
            include_keywords=rhythm_game_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SG Doujin Markets",
            feed_url=f"https://news.google.com/rss/search?q={doujin_market_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.77,
            category_hints=["events", "anime", "merch"],
            region_hints=["Singapore", "SEA"],
            include_keywords=doujin_market_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SEA Anime Screenings",
            feed_url=f"https://news.google.com/rss/search?q={anime_screening_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.76,
            category_hints=["events", "anime", "manga"],
            region_hints=["Singapore", "SEA"],
            include_keywords=anime_screening_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SG Convention Guests",
            feed_url=f"https://news.google.com/rss/search?q={convention_guest_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.76,
            category_hints=["events", "anime", "merch"],
            region_hints=["Singapore", "SEA"],
            include_keywords=convention_guest_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SG Creator Hubs",
            feed_url=f"https://news.google.com/rss/search?q={creator_hub_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.76,
            category_hints=["events", "anime", "merch"],
            region_hints=["Singapore", "SEA"],
            include_keywords=creator_hub_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SEA Anime Exhibitions",
            feed_url=f"https://news.google.com/rss/search?q={anime_exhibition_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.76,
            category_hints=["events", "anime", "merch"],
            region_hints=["Singapore", "SEA"],
            include_keywords=anime_exhibition_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SEA Tokusatsu",
            feed_url=f"https://news.google.com/rss/search?q={tokusatsu_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.77,
            category_hints=["anime", "events", "merch"],
            region_hints=["Singapore", "SEA"],
            include_keywords=tokusatsu_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SEA VTuber Concerts",
            feed_url=f"https://news.google.com/rss/search?q={vtuber_concert_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.77,
            category_hints=["events", "anime", "merch"],
            region_hints=["Singapore", "SEA"],
            include_keywords=vtuber_concert_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
        RssSource(
            name="Google News SEA Capsule Toys",
            feed_url=f"https://news.google.com/rss/search?q={capsule_toy_query}&hl=en-SG&gl=SG&ceid=SG:en",
            quality=0.76,
            category_hints=["merch", "anime", "events"],
            region_hints=["Singapore", "SEA"],
            include_keywords=capsule_toy_keywords,
            exclude_keywords=google_news_exclude_keywords,
            cleanup_mismatches=True,
        ),
    ]
