"""Live endpoint smoke tests: one call per /envato/* route against a running
service, with example values proven to return data (2026-09-21). The listing
tooling (derive_facts.py) reads each route's FIRST call from this file's AST
as its working example, so the values stay literals.

Skipped unless ENVATO_BASE points at a running service:

    ONLY_SCRAPER=envato python run.py            # or any bottle runner
    ENVATO_BASE=http://127.0.0.1:6002 python -m pytest envato/test_endpoints.py -q
"""
import os

import pytest

BASE = os.environ.get("ENVATO_BASE", "").rstrip("/")

pytestmark = pytest.mark.skipif(not BASE, reason="set ENVATO_BASE to run live endpoint tests")


def call(path, **params):
    from curl_cffi import requests
    resp = requests.get(BASE + path, params=params, timeout=240)
    assert resp.status_code == 200, f"{path} {params} -> {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    assert body, f"{path} returned an empty body"
    return body


def test_market_discovery():
    page = call("/envato/market/search", query="admin dashboard", sort="best-sellers")
    assert page["items"][0]["price"]["amount"] and page["filters"] and page["total_pages"] > 1
    assert call("/envato/market/search", query="booking", site="codecanyon", compatible_with="WooCommerce")["items"]
    assert call("/envato/market/search", category="wordpress/ecommerce", sort="rating", page=2)["items"]
    assert call("/envato/market/search", query="corporate", site="audiojungle", tempo="upbeat")["items"][0]["audio_preview"]
    assert call("/envato/market/search", query="logo reveal", site="videohive", resolution_min="4K")["items"]
    assert call("/envato/market/suggestions", query="admin")["suggestions"][0]["query"]
    assert call("/envato/market/categories", site="themeforest")["categories"][0]["subcategories"]
    assert call("/envato/market/popular", category="wordpress")["items"][0]["rank"] == 1
    assert call("/envato/market/popular", site="codecanyon")["items"]


def test_market_items():
    item = call("/envato/market/items/details", item="2833226")
    assert item["licenses"][0]["price"] and item["sales_count"] and item["author"]["username"]
    assert call("/envato/market/items/details",
                item="https://audiojungle.net/item/uplifting-and-inspiring-corporate/15357044")["media"]["audio_preview"]
    reviews = call("/envato/market/items/reviews", item="2833226", sort="lowest")
    assert reviews["reviews"][0]["rating"] and reviews["count"] > 1000
    assert call("/envato/market/items/comments", item="2833226")["comments"][0]["text"]
    assert call("/envato/market/items/support", item="2833226")["faq"]


def test_market_authors():
    author = call("/envato/market/authors/details", author="ancorathemes")
    assert author["sales_count"] and author["followers_count"] and author["badges"]
    assert call("/envato/market/authors/items", author="ancorathemes", sort="best-sellers")["items"][0]["sales_count"]
    assert call("/envato/market/authors/followers", author="themefusion")["users"]
    assert call("/envato/market/authors/following", author="ancorathemes")["users"]
    assert call("/envato/market/authors/top", site="themeforest")["authors"][0]["rank"] == 1
    assert "authors" in call("/envato/market/authors/new", site="themeforest")


def test_market_collections():
    assert call("/envato/market/collections")["collections"][0]["items_count"]
    assert call("/envato/market/collections/details",
                collection="https://graphicriver.net/collections/2253321-halloween-collection")["items"]


def test_elements():
    page = call("/envato/elements/search", type="photos", query="logo", orientation="landscape")
    assert page["items"][0]["image"] and page["filters"] and page["total_pages"] == 24
    assert call("/envato/elements/search", type="music", query="logo", mood="upbeat", sort="latest")["items"][0]["audio_preview"]
    assert call("/envato/elements/search", type="fonts")["items"]
    assert len(call("/envato/elements/search-all", query="logo")["groups"]) > 5
    item = call("/envato/elements/items/details", item="PQH6NYN")
    assert item["attributes"] and item["tags"] and item["media"]["image"]
    assert call("/envato/elements/items/details", item="https://elements.envato.com/upbeat-rock-logo-7GJENLA")["media"]["audio"]
    assert call("/envato/elements/items/similar", item="WN8QY3M")["items"]
    assert call("/envato/elements/authors/items", author="fabstudio")["items"]
    assert call("/envato/elements/free-files")["items"]
    assert call("/envato/elements/popular-searches", type="photos")["groups"][0]["searches"]
    assert call("/envato/elements/popular-searches")["groups"]
    assert call("/envato/elements/popular-searches", type="photos", letter="a")["groups"][0]["searches"]
    assert call("/envato/elements/categories")["types"]
    assert call("/envato/elements/categories", type="stock-video")["categories"]
