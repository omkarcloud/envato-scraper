"""Envato reference parsing: ONE param per input that auto-detects its forms
(tripadvisor QueryOrLinkField convention — never a sibling `url` / `id`
pair), plus the site / type / sort vocabularies the routes share.

Parsing is offline. Each resolver returns a small JSON-able dict (unused keys
None, so validated params stay a stable response-cache key).

  Envato Market
    item        2833226 | https://themeforest.net/item/avada-responsive-multipurpose-theme/2833226
                | …/item/<slug>/reviews/2833226 | …/item/<slug>/2833226/comments
                | https://preview.themeforest.net/item/<slug>/full_screen_preview/2833226
                (a link also fixes the marketplace; a bare id uses `site`)
    author      themefusion | https://themeforest.net/user/themefusion[/portfolio]
    category    wordpress | wordpress/ecommerce | https://themeforest.net/category/wordpress/ecommerce
    collection  2253321 | 2253321-halloween-collection | https://graphicriver.net/collections/2253321-halloween-collection
  Envato Elements
    item        PQH6NYN | 3d-logo-mockup-PQH6NYN | https://elements.envato.com/3d-logo-mockup-PQH6NYN
                | https://app.envato.com/… links carrying the same <slug>-<ID> tail
    author      GraphicBurger | https://elements.envato.com/user/GraphicBurger[/graphic-templates]

Market item links on any of the seven marketplaces are accepted; query
strings and fragments are ignored.
"""
import re
from urllib.parse import unquote, urlparse

# ---- Envato Market ------------------------------------------------------------
# public name -> host. Order = the order shown on the site's own switcher.
MARKET_SITES = {
    "themeforest": "themeforest.net",
    "codecanyon": "codecanyon.net",
    "videohive": "videohive.net",
    "audiojungle": "audiojungle.net",
    "graphicriver": "graphicriver.net",
    "photodune": "photodune.net",
    "3docean": "3docean.net",
}
MARKET_HOSTS = {host: name for name, host in MARKET_SITES.items()}
DEFAULT_SITE = "themeforest"

# Search / category sort: public value -> upstream `sort`.
MARKET_SORTS = {
    "relevance": "relevance",
    "best-sellers": "sales",
    "rating": "rating",
    "newest": "date",
    "trending": "trending",
    "price-low": "price-asc",
    "price-high": "price-desc",
}
MARKET_DATE_RANGES = {"day": "this-day", "week": "this-week", "month": "this-month", "year": "this-year"}
# Sales bands shown in the search sidebar ("sales=rank-N").
MARKET_SALES_BANDS = {"none": "rank-0", "low": "rank-1", "medium": "rank-2", "high": "rank-3", "top-sellers": "rank-4"}
# AudioJungle vocals filter: public value -> upstream `vocals_in_audio`.
MARKET_VOCALS = {
    "background-vocals": "background vocals/harmonies",
    "vocal-samples": "vocal samples",
    "instrumental-included": "instrumental version included",
    "lead-vocals": "lead vocals",
}
MARKET_REVIEW_SORTS = {"newest": "date_descending", "highest": "ratings_descending", "lowest": "ratings_ascending"}
# Author portfolio: public value -> (order_by, direction).
PORTFOLIO_SORTS = {
    "newest": ("sortable_at", "desc"), "oldest": ("sortable_at", "asc"),
    "best-match": ("relevance", "desc"), "updated": ("updated_at", "desc"),
    "name": ("name", "asc"), "category": ("category", "asc"),
    "rating": ("rating", "desc"), "best-sellers": ("sales", "desc"),
}
COLLECTION_SORTS = {"newest": "created_at", "name": "name", "rating": "popularity"}

# ---- Envato Elements ------------------------------------------------------------
# public type -> the URL segment Elements uses (music lives under
# /royalty-free-music; every other type's segment is its own id).
ELEMENTS_TYPES = {
    "stock-video": "stock-video",
    "video-templates": "video-templates",
    "music": "royalty-free-music",
    "sound-effects": "sound-effects",
    "graphic-templates": "graphic-templates",
    "graphics": "graphics",
    "3d": "3d",
    "presentation-templates": "presentation-templates",
    "photos": "photos",
    "fonts": "fonts",
    "add-ons": "add-ons",
    "web-templates": "web-templates",
    "cms-templates": "cms-templates",
    "wordpress": "wordpress",
}
ELEMENTS_SEGMENT_TYPES = {seg: t for t, seg in ELEMENTS_TYPES.items()}
ELEMENTS_SORTS = ["relevant", "popular", "latest"]

# Filter params -> Elements path-segment prefix. Values are the slugs the
# site shows in each type's `refinements` block (the search response
# returns them under `filters`, so callers can discover valid values).
ELEMENTS_FILTERS = {
    "orientation": "orientation",
    "resolution": "resolution",
    "frame_rate": "frame-rate",
    "properties": "properties",
    "color": "color",
    "number_of_people": "number-of-people",
    "compatible_with": "compatible-with",
    "color_space": "color-space",
    "mood": "mood",
    "genre": "genre",
    "theme": "theme",
    "tempo": "tempo",
    "instrument": "instrument",
    "vocals": "vocals",
    "decade": "decade",
    "spacing": "spacing",
    "optimum_size": "optimum-size",
}

_MARKET_ITEM_ID_RE = re.compile(r"^\d{3,12}$")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,60}$")
_CATEGORY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*(/[a-z0-9][a-z0-9_-]*){0,4}$")
_ELEMENTS_ID_RE = re.compile(r"^[A-Z0-9]{5,10}$")
_ELEMENTS_TAIL_RE = re.compile(r"(?:^|-)([A-Z0-9]{5,10})$")
_COLLECTION_RE = re.compile(r"^(\d{3,12})(?:-([a-z0-9-]+))?$")


def _parse_link(value):
    """(host, path segments) for an http(s) link, or (None, None)."""
    if not value.startswith(("http://", "https://", "//")):
        if re.match(r"^[a-z0-9.-]+\.(net|com)/", value, re.I):
            value = "https://" + value
        else:
            return None, None
    url = value if not value.startswith("//") else "https:" + value
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    segs = [unquote(s) for s in parsed.path.split("/") if s]
    return host, segs


def _market_site(host):
    """themeforest.net / preview.themeforest.net -> 'themeforest'."""
    for suffix, name in MARKET_HOSTS.items():
        if host == suffix or host.endswith("." + suffix):
            return name
    return None


def resolve_market_item(value):
    """-> {"id": int, "site": name | None}."""
    host, segs = _parse_link(value)
    if host is None:
        if _MARKET_ITEM_ID_RE.match(value):
            return {"id": int(value), "site": None}
        raise ValueError("Must be an Envato Market item id (e.g. 2833226) or an item link "
                         "(e.g. https://themeforest.net/item/avada-responsive-multipurpose-theme/2833226).")
    site = _market_site(host)
    if site is None:
        raise ValueError("Must be a link on an Envato Market site (themeforest.net, codecanyon.net, "
                         "videohive.net, audiojungle.net, graphicriver.net, photodune.net, 3docean.net).")
    if segs and segs[0] == "item":
        for seg in reversed(segs[1:]):
            if _MARKET_ITEM_ID_RE.match(seg):
                return {"id": int(seg), "site": site}
    raise ValueError("That link is not an Envato Market item page (…/item/<slug>/<id>).")


def resolve_market_author(value):
    """-> {"username": str, "site": name | None}."""
    host, segs = _parse_link(value)
    if host is None:
        name = value.lstrip("@")
        if _USERNAME_RE.match(name):
            return {"username": name, "site": None}
        raise ValueError("Must be an Envato author username (e.g. themefusion) or a profile link.")
    site = _market_site(host)
    if site is None:
        raise ValueError("Must be a profile link on an Envato Market site (e.g. https://themeforest.net/user/themefusion).")
    if len(segs) >= 2 and segs[0] == "user" and _USERNAME_RE.match(segs[1]):
        return {"username": segs[1], "site": site}
    raise ValueError("That link is not an Envato Market profile (…/user/<username>).")


def resolve_market_category(value):
    """-> {"path": 'wordpress/ecommerce', "site": name | None}."""
    host, segs = _parse_link(value)
    if host is None:
        path = value.strip("/").lower()
        if path.startswith("category/"):
            path = path[len("category/"):]
        if _CATEGORY_RE.match(path):
            return {"path": path, "site": None}
        raise ValueError("Must be a category path (e.g. wordpress or wordpress/ecommerce) or a /category/ link.")
    site = _market_site(host)
    if site is None:
        raise ValueError("Must be a category link on an Envato Market site.")
    if len(segs) >= 2 and segs[0] == "category":
        path = "/".join(segs[1:]).lower()
        if _CATEGORY_RE.match(path):
            return {"path": path, "site": site}
    raise ValueError("That link is not an Envato Market category (…/category/<path>).")


def resolve_market_collection(value):
    """-> {"id": int, "slug": str | None, "site": name | None}."""
    host, segs = _parse_link(value)
    if host is None:
        m = _COLLECTION_RE.match(value.lower())
        if m:
            return {"id": int(m.group(1)), "slug": m.group(2), "site": None}
        raise ValueError("Must be a collection id (e.g. 2253321) or a /collections/ link.")
    site = _market_site(host)
    if site is None:
        raise ValueError("Must be a collection link on an Envato Market site.")
    if len(segs) >= 2 and segs[0] == "collections":
        m = _COLLECTION_RE.match(segs[1].lower())
        if m:
            return {"id": int(m.group(1)), "slug": m.group(2), "site": site}
    raise ValueError("That link is not an Envato Market collection (…/collections/<id>-<slug>).")


def resolve_elements_item(value):
    """-> {"id": 'PQH6NYN', "slug": str | None}."""
    host, segs = _parse_link(value)
    if host is None:
        if _ELEMENTS_ID_RE.match(value):
            return {"id": value, "slug": None}
        m = _ELEMENTS_TAIL_RE.search(value)
        if m and re.match(r"^[a-z0-9-]+-[A-Z0-9]{5,10}$", value):
            return {"id": m.group(1), "slug": value[: -len(m.group(1)) - 1] or None}
        raise ValueError("Must be an Envato Elements item id (e.g. PQH6NYN), a slug like "
                         "3d-logo-mockup-PQH6NYN or an elements.envato.com item link.")
    if not (host == "envato.com" or host.endswith(".envato.com")):
        raise ValueError("Must be an Envato Elements item link (https://elements.envato.com/<slug>-<ID>).")
    for seg in reversed(segs):
        m = _ELEMENTS_TAIL_RE.search(seg)
        if m:
            slug = seg[: -len(m.group(1)) - 1] or None
            return {"id": m.group(1), "slug": slug}
    raise ValueError("That link is not an Envato Elements item page (…/<slug>-<ID>).")


def resolve_elements_author(value):
    """-> {"username": str}."""
    host, segs = _parse_link(value)
    if host is None:
        name = value.lstrip("@")
        if _USERNAME_RE.match(name):
            return {"username": name}
        raise ValueError("Must be an Envato Elements author username (e.g. GraphicBurger) or a profile link.")
    if not (host == "envato.com" or host.endswith(".envato.com")):
        raise ValueError("Must be an Envato Elements profile link (https://elements.envato.com/user/<username>).")
    if len(segs) >= 2 and segs[0] == "user" and _USERNAME_RE.match(segs[1]):
        return {"username": segs[1]}
    raise ValueError("That link is not an Envato Elements profile (…/user/<username>).")


def market_base(site):
    return f"https://{MARKET_SITES[site or DEFAULT_SITE]}"


def elements_slug(text):
    """Free text -> an Elements search segment ('logo reveal' -> 'logo+reveal')."""
    words = re.sub(r"[^\w\s'-]+", " ", text.lower()).split()
    return "+".join(words)
