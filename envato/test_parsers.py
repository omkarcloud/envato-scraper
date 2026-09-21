"""Offline tests: refs resolvers, schemas and both parsers against captured
pages (envato/fixtures/*.gz, recorded 2026-09-21).

    python -m pytest envato/test_parsers.py -q
"""
import gzip
import json
import os

import pytest

from envato.util import soup
from schema_fields import load_query

from envato import parsers_elements as E
from envato import parsers_market as P
from envato import refs, schemas

FX = os.path.join(os.path.dirname(__file__), "fixtures")
TF = "https://themeforest.net"


def raw(name):
    with gzip.open(os.path.join(FX, name + ".gz"), "rt", encoding="utf-8") as f:
        return f.read()


def doc(name):
    return soup(raw(name))


def js(name):
    return json.loads(raw(name))


# ---- refs + schemas ------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("2833226", {"id": 2833226, "site": None}),
    ("https://themeforest.net/item/avada-responsive-multipurpose-theme/2833226", {"id": 2833226, "site": "themeforest"}),
    ("https://themeforest.net/item/avada/reviews/2833226?page=2", {"id": 2833226, "site": "themeforest"}),
    ("https://codecanyon.net/item/wpbakery/242431/comments", {"id": 242431, "site": "codecanyon"}),
    ("https://preview.themeforest.net/item/avada/full_screen_preview/2833226", {"id": 2833226, "site": "themeforest"}),
])
def test_market_item_refs(value, expected):
    assert refs.resolve_market_item(value) == expected


@pytest.mark.parametrize("value", ["avada", "https://example.com/item/x/123", "https://themeforest.net/user/x"])
def test_market_item_refs_reject(value):
    with pytest.raises(ValueError):
        refs.resolve_market_item(value)


def test_other_refs():
    assert refs.resolve_market_author("https://audiojungle.net/user/aurusaudio/portfolio") == {"username": "aurusaudio", "site": "audiojungle"}
    assert refs.resolve_market_category("/category/wordpress/ecommerce") == {"path": "wordpress/ecommerce", "site": None}
    assert refs.resolve_market_collection("2253321-halloween-collection")["id"] == 2253321
    assert refs.resolve_elements_item("PQH6NYN") == {"id": "PQH6NYN", "slug": None}
    assert refs.resolve_elements_item("https://elements.envato.com/3d-logo-mockup-PQH6NYN") == {"id": "PQH6NYN", "slug": "3d-logo-mockup"}
    assert refs.resolve_elements_author("https://elements.envato.com/user/GraphicBurger/graphics") == {"username": "GraphicBurger"}
    assert refs.elements_slug("Logo  reveal!") == "logo+reveal"


def test_schemas():
    data, err = load_query(schemas.MarketSearchSchema, {"query": "x", "vocals": "lead-vocals", "sort": "Best-Sellers"})
    assert err is None and data["vocals"] == "lead vocals" and data["sort"] == "best-sellers"
    _, err = load_query(schemas.MarketSearchSchema, {"price_min": "50", "price_max": "10"})
    assert "price_min" in err["errors"]
    _, err = load_query(schemas.ElementsSearchSchema, {"query": "logo"})
    assert "type" in err["errors"]
    data, _ = load_query(schemas.ElementsSearchSchema, {"type": "photos", "orientation": "Landscape, portrait"})
    assert data["orientation"] == ["landscape", "portrait"]
    _, err = load_query(schemas.MarketItemSchema, {"item": "2833226", "url": "x"})
    assert "url" in err["errors"]


# ---- Envato Market ---------------------------------------------------------------------

def test_search_cards_and_filters():
    d = doc("tf_search.html")
    cards = P.item_cards(d, TF)
    assert len(cards) == 30 and P.results_total(d) == 3255 and P.pages_total(d) == 60
    first = cards[0]
    assert first["id"] == 9694847 and first["author"]["username"] == "ace"
    assert first["price"] == {"amount": 35.0, "original_amount": None, "currency": "USD", "is_on_sale": False}
    assert first["rating"] == 4.74 and first["reviews_count"] == 678 and first["sales_count"] == 11400
    assert first["last_updated"] == "2023-05-24" and first["category"]["path"] == "site-templates/admin-templates"
    filters = {f["param"]: f for f in P.facets(d)}
    assert filters["sales"]["options"][0]["value"] == "none"
    assert filters["compatible_with"]["options"][0] == {"label": "Bootstrap", "value": "Bootstrap", "count": 2245, "is_selected": False}


def test_media_cards():
    audio = P.item_cards(doc("aj_search.html"), "https://audiojungle.net")[0]["audio_preview"]
    assert audio["preview_link"].endswith("preview.mp3") and audio["bpm"] == 120 and audio["track_count"] == 4
    assert audio["track_lengths_seconds"] == [240, 139, 64, 48]
    video = P.item_cards(doc("vh_search.html"), "https://videohive.net")[0]
    assert video["video_preview_link"].endswith(".mp4") and video["image"] and video["live_preview_link"] is None
    photo = P.item_cards(doc("pd_search.html"), "https://photodune.net")[0]
    assert photo["name"] and photo["is_in_elements"] is True


def test_item_page():
    item = P.item_page(raw("tf_item.html"), TF, "themeforest")
    assert item["id"] == 9694847 and item["rating"] == 4.74 and item["sales_count"] == 11429
    regular, extended = item["licenses"]
    assert regular["price"] == 35.0 and regular["support_extension_price"] == 19.38 and extended["price"] == 1000.0
    assert item["attributes"]["compatible_browsers"][0] == "IE10" and item["attributes"]["high_resolution"] is True
    assert item["purchase_includes"][-1] == "6 months support from ace"
    assert item["author"]["badges"][0]["name"] and item["media"]["live_preview_link"]
    assert item["last_updated"] == "2023-05-24"
    aj = P.item_page(raw("aj_item.html"), "https://audiojungle.net", "audiojungle")
    assert aj["media"]["audio_preview"]["duration_seconds"] == 512 and aj["attributes"]["tempo_bpm"] == "120"
    assert aj["created_estimated"] <= aj["last_updated"]
    assert P.item_page(raw("vh_item.html"), "https://videohive.net", "videohive")["media"]["video_preview_link"]
    assert P.item_page(raw("3d_item.html"), "https://3docean.net", "3docean")["media"]["screenshots"]


def test_reviews_comments_support():
    reviews = P.reviews_page(raw("tf_reviews_lowest.html"), TF)
    assert reviews["total"] == 26594 and len(reviews["reviews"]) == 20
    first = reviews["reviews"][0]
    assert first["rating"] == 1.0 and first["reason"] and first["author_response"]["text"]
    assert reviews["item_name"].startswith("Avada | Website Builder")
    comments = P.comments_page(raw("tf_comments.html"), TF)
    assert comments["total"] == 39396 and comments["comments"][0]["is_buyer"] is True
    assert comments["comments"][0]["replies"][0]["is_author"] is True
    support = P.support_page(raw("tf_support.html"), TF)
    assert support["is_supported"] and support["supported_by"] == "ThemeFusion" and support["faq"]


def test_profile_and_lists():
    tf = P.profile(raw("tf_user.html"), TF, "themeforest")
    assert tf["country"] == "United States" and tf["member_since"] == "2012-03" and tf["rating"] == 4.78
    ancora = P.profile(raw("tf_user_multi.html"), TF, "themeforest")
    assert ancora["followers_count"] == 1733 and ancora["following_count"] == 87 and ancora["featured_item"]["id"]
    rows = P.portfolio_rows(doc("tf_portfolio.html"), TF)
    assert len(rows) == 30 and rows[0]["attributes"]["gutenberg_optimized"] is True
    followers = P.user_rows(doc("tf_followers.html"), TF)
    assert len(followers) == 30 and followers[0]["member_since"] == "2022-07"
    top = P.user_rows(doc("tf_authors_top.html"), TF)
    assert top[0]["rank"] == 1 and top[0]["sales_count"] > 1_000_000


def test_categories_and_collections():
    tree = P.category_tree(raw("tf_categories.html"), TF)
    assert tree[0]["path"] == "site-templates" and tree[0]["subcategories"][0]["subcategories"]
    rows = P.collection_rows(doc("tf_collections.html"), TF)
    assert rows[0]["items_count"] and rows[0]["owner"]["link"].startswith("https://audiojungle.net/")
    page = P.collection_page(raw("gr_collection.html"), "https://graphicriver.net")
    assert page["owner"]["name"] == "JoshuaSprague" and len(page["items"]) == 20
    assert page["items"][0]["site"] == "videohive"


# ---- Envato Elements ---------------------------------------------------------------------

def test_elements_items():
    video = E.item_page(js("el_item_video.json"))
    assert video["id"] == "DAGBT24" and video["media"]["video"]["preview_540p_link"]
    assert video["attributes"]["video_resolution"]["width"] == 1920 and video["file_size_bytes"] == 25396510
    music = E.item_page(js("el_item_music.json"))
    assert music["media"]["audio"]["main_track"]["mp3_link"] and music["published_at"] == "2026-08-24T11:15:28Z"
    assert music["updated_at"] == "2026-08-25T13:50:00"
    font = E.item_page(js("el_item_font.json"))
    assert font["media"]["font"]["default_style"] and font["tags"]


def test_elements_search():
    path = "/photos/logo/orientation-landscape/sort-by-popular/pg-2"
    page = E.search_page(js("el_search_photos.json"), 2, path)
    assert len(page["items"]) == 60 and page["pagination"]["total_pages"] == 24
    orientation = next(f for f in page["filters"] if f["param"] == "orientation")
    assert [(o["value"], o["is_selected"]) for o in orientation["options"]] == [
        ("landscape", True), ("portrait", False), ("square", False)]
    people = next(f for f in page["filters"] if f["param"] == "number_of_people")
    assert people["options"][0]["value"] == "no-people"
    music = E.search_page(js("el_search_music.json"), 1, "/royalty-free-music/logo")
    assert music["items"][0]["audio_preview"]["preview_link"]
    assert {f["param"] for f in music["filters"]} >= {"mood", "genre", "tempo", "vocals"}
    everything = E.search_all(js("el_search_all.json"))
    assert len(everything["groups"]) >= 10 and everything["groups"][0]["items"]


def test_elements_misc():
    author = E.author_page(js("el_author.json"), 1)
    assert author["items"] and author["item_types"] and author["author"]["link"].endswith("/user/fabstudio")
    assert E.free_files(js("el_free_files.json"))["items"]
    assert E.popular_searches(js("el_popular.json"))["groups"][0]["searches"]
    assert E.popular_searches(js("el_popular_type.json"))["groups"][0]["letter"] == "A"


def test_partial_input_never_crashes():
    assert P.item_page("<html></html>", TF, "themeforest")["id"] is None
    assert P.reviews_page("", TF)["reviews"] == []
    assert P.comments_page("", TF)["comments"] == []
    assert P.profile("", TF, "themeforest") is None
    assert E.item_page({})["id"] is None
    assert E.search_page({}, 1)["items"] == []
    assert E.item_card({"id": "X", "video": "oops", "musicVariants": []})["id"] == "X"
