"""/envato/market/* endpoints: search, suggestions, categories, charts, item
details / reviews / comments / support, authors (profile, portfolio,
followers, following, top and new authors) and public collections, for the
seven Envato Market sites.

Every function takes the validated kwargs of its schema (envato/schemas.py)
and returns a JSON-able dict. Paged endpoints return a `pagination` block
({page, items_per_page, total_pages, total_count}) that route_glue lifts into
the gateway shape (count / per_page / current_page / total_pages / next /
previous).
"""
from urllib.parse import quote

from envato.util import soup

from envato import fetch, refs
from envato import parsers_market as P

SEARCH_PAGE_SIZE = 30         # search / category / popular grids
LIST_PAGE_SIZE = 30           # portfolio rows, followers, top authors
REVIEW_PAGE_SIZE = 20
COMMENT_PAGE_SIZE = 20
COLLECTION_PAGE_SIZE = 20


def _site(site, ref=None):
    """A link-derived marketplace wins over the `site` param."""
    return (ref or {}).get("site") or site or refs.DEFAULT_SITE


def _base(site):
    return refs.market_base(site)


def _pagination(page, per_page, total_pages, total_count=None, has_items=True):
    """A page past the end renders pagination links relative to itself, so
    an empty page trusts the result count (or the page before it) instead."""
    if not has_items:
        if total_count and per_page:
            total_pages = -(-int(total_count) // per_page)
        else:
            total_pages = max(page - 1, 0)
        return {"page": page, "items_per_page": per_page, "total_pages": total_pages, "total_count": total_count}
    if total_pages is None:
        total_pages = page
    return {"page": page, "items_per_page": per_page, "total_pages": max(total_pages, page), "total_count": total_count}


def _page_html(url, params, page, *, label, missing=None):
    """A paged listing: a page past the end (404) becomes an empty page."""
    resp = fetch.market_request(url, params, label=label, missing=missing, not_found_ok=page > 1)
    if resp.status_code == 404:
        return None
    return resp.text


def _mmss(seconds):
    return f"{seconds // 60}:{seconds % 60:02d}" if seconds is not None else None


# ---- search / browse -------------------------------------------------------------------

def search(query=None, site=None, category=None, sort=None, date_added=None, date_updated=None,
           price_min=None, price_max=None, rating_min=None, sales=None, on_sale=None,
           compatible_with=None, software_version=None, resolution_min=None, frame_rate=None,
           requires_plugins=None, has_alpha_channel=None, is_looped=None, min_length=None,
           max_length=None, tempo=None, vocals=None, include_pro_music=None, orientation=None,
           size=None, color=None, file_format=None, min_poly_count=None, max_poly_count=None, page=1):
    """Search any Envato Market site by keyword and/or category with every sidebar filter; returns item cards, filter values with counts and paging."""
    site = _site(site, category)
    base = _base(site)
    params = {
        "sort": refs.MARKET_SORTS.get(sort) if sort else None,
        "date": refs.MARKET_DATE_RANGES.get(date_added) if date_added else None,
        "date_updated": refs.MARKET_DATE_RANGES.get(date_updated) if date_updated else None,
        "price_min": int(price_min) if price_min is not None else None,
        "price_max": int(price_max) if price_max is not None else None,
        "rating_min": rating_min,
        "sales": refs.MARKET_SALES_BANDS.get(sales) if sales else None,
        "discounted_only": 1 if on_sale else None,
        "compatible_with": compatible_with,
        "platform": software_version,
        "resolution_min": {"2k": "2K", "4k": "4K"}.get(resolution_min, resolution_min),  # schema lower-cases
        "frame_rate": frame_rate,
        "requires_plugins": {True: "T", False: "F"}.get(requires_plugins),
        "alpha": 1 if has_alpha_channel else None,
        "looped": 1 if is_looped else None,
        "length_min": _mmss(min_length),
        "length_max": _mmss(max_length),
        "tempo": tempo,
        "vocals_in_audio": vocals,          # already mapped to the upstream value by the schema
        "include_pro_affiliated": {True: "true", False: "false"}.get(include_pro_music),
        "orientation": orientation,
        "sizes": size,
        "colors": color,
        "file_formats": file_format,
        "poly_count": (f"{min_poly_count or 0}-{max_poly_count}" if max_poly_count else
                       str(min_poly_count) if min_poly_count else None),
        "page": page if page > 1 else None,
    }
    if category:
        url = f"{base}/category/{category['path']}"
        params["term"] = query
    elif query:
        url = f"{base}/search/{quote(query, safe='')}"
    else:
        url = f"{base}/category/all"
    markup = _page_html(url, params, page, label="search", missing="category not found on this marketplace")
    if markup is None:
        return {"site": site, "items": [], "filters": [], "pagination": _pagination(page, SEARCH_PAGE_SIZE, page - 1, None, False)}
    doc = soup(markup)
    items = P.item_cards(doc, base)
    return {
        "site": site,
        "items": items,
        "filters": P.facets(doc),
        "pagination": _pagination(page, SEARCH_PAGE_SIZE, P.pages_total(doc) or (page if items else 0),
                                  P.results_total(doc), bool(items)),
    }


def suggest(query, site=None, category=None):
    """Search suggestions for a partial query, ranked by popularity, with the category each suggestion belongs to."""
    site = _site(site, category)
    data = fetch.market_json(f"{_base(site)}/storefront/search_suggestions",
                             {"query": query, "revision": 1, "category": category["path"] if category else None},
                             label="search suggestions")
    out = []
    for row in data if isinstance(data, list) else []:
        if not isinstance(row, dict) or not row.get("term"):
            continue
        path = row.get("category_path")
        out.append({"query": row.get("term"), "popularity": row.get("popularity"),
                    "category": {"name": row.get("category_name"), "path": path,
                                 "link": f"{_base(site)}/category/{path}"} if path else None})
    return {"site": site, "suggestions": out}


def categories(site=None):
    """The marketplace's full category tree with item counts per category and subcategory."""
    site = _site(site)
    base = _base(site)
    tree = P.category_tree(fetch.market_html(f"{base}/category", label="categories"), base)
    return {"site": site, "categories": tree}


def popular(site=None, category=None):
    """Weekly best sellers: the whole marketplace, or one category."""
    site = _site(site, category)
    base = _base(site)
    if category:
        markup = fetch.market_html(f"{base}/popular_item/by_category", {"category": category["path"]},
                                   label="popular items", missing="category not found on this marketplace")
    else:
        markup = fetch.market_html(f"{base}/top-sellers", label="top sellers")
    doc = soup(markup)
    items = P.item_cards(doc, base)
    for rank, item in enumerate(items, 1):
        item["rank"] = rank
    return {"site": site, "category": category["path"] if category else None,
            "title": P.page_title(doc), "items": items}


# ---- items --------------------------------------------------------------------------------

def _item_url(item, site, tail=""):
    return f"{_base(site)}/item/x/{tail}{item['id']}" if tail == "reviews/" else f"{_base(site)}/item/x/{item['id']}{tail}"


def item_details(item, site=None):
    """Everything on an item page: prices for every license, support prices, sales, rating, attributes, previews, author and badges."""
    site = _site(site, item)
    base = _base(site)
    markup = fetch.market_html(_item_url(item, site), label="item",
                               missing=f"item {item['id']} not found on {refs.MARKET_SITES[site]}")
    return P.item_page(markup, base, site)


def item_reviews(item, site=None, sort=None, page=1):
    """An item's buyer reviews: stars, reason, text, reviewer and the author's response, sortable by date or rating."""
    site = _site(site, item)
    base = _base(site)
    params = {"reviews_controls[sort]": refs.MARKET_REVIEW_SORTS.get(sort) if sort else None,
              "page": page if page > 1 else None}
    markup = _page_html(_item_url(item, site, "reviews/"), params, page, label="reviews",
                        missing=f"item {item['id']} not found on {refs.MARKET_SITES[site]}")
    data = P.reviews_page(markup, base) if markup else {"reviews": [], "total": None, "rating": None,
                                                         "total_pages": None, "item_name": None}
    return {
        "item": {"id": item["id"], "name": data["item_name"], "link": f"{base}/item/x/{item['id']}"},
        "rating": data["rating"],
        "reviews": data["reviews"],
        "pagination": _pagination(page, REVIEW_PAGE_SIZE, data["total_pages"] or (page if data["reviews"] else 0),
                                  data["total"], bool(data["reviews"])),
    }


def item_comments(item, site=None, page=1):
    """An item's comment threads: text, buyer and author labels, and every reply."""
    site = _site(site, item)
    base = _base(site)
    markup = _page_html(_item_url(item, site, "/comments"), {"page": page if page > 1 else None}, page,
                        label="comments", missing=f"item {item['id']} not found on {refs.MARKET_SITES[site]}")
    data = P.comments_page(markup, base) if markup else {"comments": [], "total": None, "total_pages": None,
                                                          "item_name": None}
    return {
        "item": {"id": item["id"], "name": data["item_name"], "link": f"{base}/item/x/{item['id']}"},
        "comments": data["comments"],
        "pagination": _pagination(page, COMMENT_PAGE_SIZE, data["total_pages"] or (page if data["comments"] else 0),
                                  data["total"], bool(data["comments"])),
    }


def item_support(item, site=None):
    """An item's support policy: who supports it, what support includes and excludes, the support link and the FAQ."""
    site = _site(site, item)
    base = _base(site)
    markup = fetch.market_html(_item_url(item, site, "/support"), label="support",
                               missing=f"item {item['id']} not found on {refs.MARKET_SITES[site]}")
    data = P.support_page(markup, base)
    name = data.pop("item_name", None)
    return {"item": {"id": item["id"], "name": name, "link": f"{base}/item/x/{item['id']}"}, **data}


# ---- authors -------------------------------------------------------------------------------

def _author_url(author, site, tail=""):
    return f"{_base(site)}/user/{quote(author['username'], safe='')}{tail}"


def author_details(author, site=None):
    """An author's profile: level, country, member since, rating, sales, followers, badges, bio, featured item and collections."""
    site = _site(site, author)
    markup = fetch.market_html(_author_url(author, site), label="author",
                               missing=f"author {author['username']} not found on {refs.MARKET_SITES[site]}")
    data = P.profile(markup, _base(site), site)
    if data is None:
        raise fetch.EnvatoNotFound(f"author {author['username']} not found on {refs.MARKET_SITES[site]}")
    return data


def author_items(author, site=None, sort=None, page=1):
    """An author's portfolio with price, sales, category and attributes per item, sortable."""
    site = _site(site, author)
    base = _base(site)
    order_by, direction = refs.PORTFOLIO_SORTS.get(sort or "newest")
    params = {"order_by": order_by, "direction": direction, "view": "list", "page": page if page > 1 else None}
    markup = _page_html(_author_url(author, site, "/portfolio"), params, page, label="portfolio",
                        missing=f"author {author['username']} not found on {refs.MARKET_SITES[site]}")
    doc = soup(markup or "")
    items = P.portfolio_rows(doc, base)
    if not items and markup and page == 1:
        # a one-item author's /portfolio redirects to the profile page:
        # serve its featured item as the portfolio
        profile = P.profile(markup, base, site)
        if profile and profile.get("featured_item"):
            items = [profile["featured_item"]]
    return {
        "author": {"username": author["username"], "link": _author_url(author, site)},
        "site": site,
        "items": items,
        "pagination": _pagination(page, LIST_PAGE_SIZE, P.pages_total(doc) or (page if items else 0), None, bool(items)),
    }


def _people(author, site, tail, page):
    base = _base(site)
    markup = _page_html(_author_url(author, site, tail), {"page": page if page > 1 else None}, page,
                        label=tail.strip("/"), missing=f"author {author['username']} not found on {refs.MARKET_SITES[site]}")
    doc = soup(markup or "")
    users = P.user_rows(doc, base)
    for user in users:
        user.pop("rank", None)
    count = None
    header = P.profile(markup, base, site) if markup else None
    if header:
        count = header["followers_count"] if tail == "/followers" else header["following_count"]
    return {"author": {"username": author["username"], "link": _author_url(author, site)}, "site": site,
            "users": users,
            "pagination": _pagination(page, LIST_PAGE_SIZE, P.pages_total(doc) or (page if users else 0), count, bool(users))}


def author_followers(author, site=None, page=1):
    """People following an author, with their items, sales, rating, followers and badges."""
    return _people(author, _site(site, author), "/followers", page)


def author_following(author, site=None, page=1):
    """Authors an author follows, with their items, sales, rating, followers and badges."""
    return _people(author, _site(site, author), "/following", page)


def top_authors(site=None, level=None, page=1):
    """The marketplace's all-time top authors by sales, filterable by author level."""
    site = _site(site)
    base = _base(site)
    markup = _page_html(f"{base}/authors/top", {"level": level, "page": page if page > 1 else None}, page,
                        label="top authors")
    doc = soup(markup or "")
    users = P.user_rows(doc, base)
    return {"site": site, "level": level, "authors": users,
            "pagination": _pagination(page, LIST_PAGE_SIZE, P.pages_total(doc) or (page if users else 0), None, bool(users))}


def new_authors(site=None):
    """The top new authors of the month on a marketplace."""
    site = _site(site)
    base = _base(site)
    doc = soup(fetch.market_html(f"{base}/page/top_new_sellers", label="top new authors"))
    month = None
    for h in doc.find_all("h2"):
        label = P.clean(h) or ""
        if label.startswith("Top New Authors For"):
            month = P.month_year(label)
            break
    return {"site": site, "month": month, "authors": P.user_rows(doc, base)}


# ---- collections ------------------------------------------------------------------------------

def collections(site=None, sort=None, page=1):
    """Public collections curated by the community, with owner, item count and rating."""
    site = _site(site)
    base = _base(site)
    params = {"sort_by": refs.COLLECTION_SORTS.get(sort) if sort else None, "page": page if page > 1 else None}
    markup = _page_html(f"{base}/collections", params, page, label="collections")
    doc = soup(markup or "")
    rows = P.collection_rows(doc, base)
    return {"collections": rows,
            "pagination": _pagination(page, COLLECTION_PAGE_SIZE, P.pages_total(doc) or (page if rows else 0), None, bool(rows))}


COLLECTION_ITEM_SORTS = {"added": "bookmarks.created_at", "released": "sortable_at", "name": "name",
                         "author": "username", "category": "category", "rating": "average_rating",
                         "best-sellers": "sales_count", "price": "cost"}


def collection_details(collection, site=None, sort=None, page=1):
    """A public collection's items with price, sales, rating and previews, plus its owner."""
    site = _site(site, collection)
    base = _base(site)
    slug = f"{collection['id']}-{collection['slug']}" if collection.get("slug") else str(collection["id"])
    params = {"sort_by": COLLECTION_ITEM_SORTS.get(sort) if sort else None,
              "order": "asc" if sort in ("name", "author", "category", "price") else ("desc" if sort else None),
              "page": page if page > 1 else None}
    markup = _page_html(f"{base}/collections/{slug}", params, page, label="collection",
                        missing=f"collection {collection['id']} not found")
    data = P.collection_page(markup, base) if markup else {"name": None, "description": None, "owner": None,
                                                           "image": None, "items": [], "total_pages": None}
    items = data.pop("items")
    total_pages = data.pop("total_pages")
    return {"collection": {"id": collection["id"], **data, "link": f"{base}/collections/{slug}"},
            "items": items,
            "pagination": _pagination(page, COLLECTION_PAGE_SIZE, total_pages or (page if items else 0), None, bool(items))}
