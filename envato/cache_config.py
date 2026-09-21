"""Cache TTL per /envato/* endpoint (cache.py, keyed on the validated params —
marshmallow fills the defaults, so `?page=1` and no `page` share a row).

Tiers follow how fast each surface moves: an item's metadata, attributes and
licenses change with an author update (days apart); sales / rating counters
tick constantly but a few hours of lag is fine; comments and reviews feeds
move faster; weekly charts refresh once a week but are cheap to keep fresh;
category trees and popular-search lists barely change. Market pages are the
expensive ones (a Cloudflare identity per marketplace), so they cache longer.
"""
from datetime import timedelta

# --- Envato Market ------------------------------------------------------------------
MARKET_SEARCH_CACHE = timedelta(hours=6)
MARKET_SUGGEST_CACHE = timedelta(days=3)
MARKET_CATEGORIES_CACHE = timedelta(days=7)
MARKET_POPULAR_CACHE = timedelta(hours=12)
MARKET_ITEM_CACHE = timedelta(hours=12)
MARKET_REVIEWS_CACHE = timedelta(hours=6)
MARKET_COMMENTS_CACHE = timedelta(hours=2)
MARKET_SUPPORT_CACHE = timedelta(days=3)
MARKET_AUTHOR_CACHE = timedelta(hours=12)
MARKET_AUTHOR_LIST_CACHE = timedelta(hours=12)     # portfolio, followers, following
MARKET_TOP_AUTHORS_CACHE = timedelta(days=1)
MARKET_COLLECTIONS_CACHE = timedelta(days=1)

# --- Envato Elements ----------------------------------------------------------------
ELEMENTS_SEARCH_CACHE = timedelta(hours=6)
ELEMENTS_ITEM_CACHE = timedelta(days=1)
ELEMENTS_SIMILAR_CACHE = timedelta(days=1)
ELEMENTS_AUTHOR_CACHE = timedelta(hours=12)
ELEMENTS_FREE_FILES_CACHE = timedelta(hours=6)
ELEMENTS_POPULAR_CACHE = timedelta(days=3)
ELEMENTS_CATEGORIES_CACHE = timedelta(days=7)
