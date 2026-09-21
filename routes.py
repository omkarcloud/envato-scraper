"""The 24 Envato endpoints. Every path is served with and without the
`/envato` prefix, so code generated against the hosted API (paths like
/market/items/details) runs unchanged against this server.

Params are validated by the same marshmallow schemas the hosted API uses
(envato/schemas.py), so defaults, enums and error messages are identical:
unknown params are rejected, and ONE param per input accepts an id or a
pasted link (a Market item link also picks its marketplace). List endpoints
page with `page` and return count / per_page / current_page / total_pages /
next / previous first, exactly like the hosted API.
"""
import json
from urllib.parse import urlencode

from bottle import request, response, route

from schema_fields import load_query
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from envato import elements, market, schemas

PREFIX = "/envato"


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The request query as unicode strings (bottle 0.12's .get() hands back
    latin-1 decoded bytes, so a UTF-8 "Amélie" would arrive as "AmÃ©lie")."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def _page_link(params, page):
    if not page:
        return None
    query = {k: v for k, v in params.items() if v not in (None, "")}
    query["page"] = page
    return f"{request.urlparts.scheme}://{request.urlparts.netloc}{request.path}?{urlencode(query)}"


def paginate(result, params):
    """Lift the scraper's `pagination` block into the flat shape the hosted
    API returns: count / per_page / current_page / total_pages / next /
    previous first, then the data."""
    pagination = result.pop("pagination", None) or {}
    page = int(pagination.get("page") or params.get("page") or 1)
    total_pages = int(pagination.get("total_pages") or 0)
    out = {
        "count": pagination.get("total_count"),
        "per_page": pagination.get("items_per_page"),
        "current_page": page,
        "total_pages": total_pages,
        "next": _page_link(params, page + 1 if page < total_pages else None),
        "previous": _page_link(params, page - 1 if page > 1 else None),
    }
    out.update(result)
    return out


def call(path, schema, impl, paginated=False):
    """Validate the query with the endpoint's schema, run it, and map every
    failure the way the hosted API does: bad params -> 400, missing entity
    -> 404, upstream failure or block -> 502, anything else -> 500."""
    params = query_dict()
    data, error = load_query(schema, params)
    if error:
        return json_response(error, 400)
    try:
        result = impl(**data)
    except ValueError as e:
        return json_response({"error": str(e)}, 400)
    except BadRequest as e:
        return json_response({"error": f"envato rejected the request: {e}"}, 400)
    except NotFound as e:
        return json_response({"error": str(e) or "not found"}, 404)
    except Blocked as e:
        return json_response({"error": f"envato blocked the request, retry later: {e}"}, 502)
    except UpstreamError as e:
        return json_response({"error": f"envato {path} failed: {e}"}, 502)
    except Exception as e:
        return json_response({"error": f"envato {path} failed: {type(e).__name__}: {e}"}, 500)
    return json_response(paginate(result, params) if paginated else result)


P = True   # paginated (page)

# (public path, request schema, endpoint function, paginated) — the order of the docs.
ENDPOINTS = [
    ("/market/items/details", schemas.MarketItemSchema, market.item_details, False),
    ("/market/suggestions", schemas.MarketSuggestSchema, market.suggest, False),
    ("/market/search", schemas.MarketSearchSchema, market.search, P),
    ("/market/popular", schemas.MarketPopularSchema, market.popular, False),
    ("/market/categories", schemas.MarketSiteSchema, market.categories, False),
    ("/market/items/reviews", schemas.MarketReviewsSchema, market.item_reviews, P),
    ("/market/items/comments", schemas.MarketCommentsSchema, market.item_comments, P),
    ("/market/items/support", schemas.MarketItemSchema, market.item_support, False),
    ("/market/authors/details", schemas.MarketAuthorSchema, market.author_details, False),
    ("/market/authors/items", schemas.MarketAuthorItemsSchema, market.author_items, P),
    ("/market/authors/followers", schemas.MarketAuthorPeopleSchema, market.author_followers, P),
    ("/market/authors/following", schemas.MarketAuthorPeopleSchema, market.author_following, P),
    ("/market/authors/top", schemas.MarketTopAuthorsSchema, market.top_authors, P),
    ("/market/authors/new", schemas.MarketSiteSchema, market.new_authors, False),
    ("/market/collections", schemas.MarketCollectionsSchema, market.collections, P),
    ("/market/collections/details", schemas.MarketCollectionSchema, market.collection_details, P),
    ("/elements/items/details", schemas.ElementsItemSchema, elements.item_details, False),
    ("/elements/search-all", schemas.ElementsQuerySchema, elements.search_all, False),
    ("/elements/search", schemas.ElementsSearchSchema, elements.search, P),
    ("/elements/items/similar", schemas.ElementsSimilarSchema, elements.similar, P),
    ("/elements/categories", schemas.ElementsCategoriesSchema, elements.categories, False),
    ("/elements/popular-searches", schemas.ElementsPopularSearchesSchema, elements.popular_searches, False),
    ("/elements/authors/items", schemas.ElementsAuthorSchema, elements.author_items, P),
    ("/elements/free-files", schemas.EmptySchema, elements.free_files, False),
]


def mount(path, schema, impl, paginated):
    """Serve one endpoint at /path and /envato/path."""
    def handler():
        return call(path, schema, impl, paginated)
    handler.__name__ = "envato_" + path.strip("/").replace("/", "_").replace("-", "_")
    route(path, method="GET")(handler)
    route(PREFIX + path, method="GET")(handler)


for _path, _schema, _impl, _paginated in ENDPOINTS:
    mount(_path, _schema, _impl, _paginated)


@route("/", method="GET")
@route("/health", method="GET")
def health():
    return json_response({"status": "ok", "endpoints": [p for p, *_ in ENDPOINTS]})
