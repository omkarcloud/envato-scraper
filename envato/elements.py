"""/envato/elements/* endpoints: search (per type, with every filter the site
exposes), search across all types, similar items, item details, author
portfolios, free files of the week, popular searches and the type /
category / filter catalogue.

Every Elements page is read as JSON from /data-api/page (envato/fetch.py);
the page path carries the whole query:

  /<type segment>[/<category>][/<search+words>][/<filter>-<v1>+<v2>…][/similar-to-<ID>]
    [/sort-by-popular|latest][/pg-N]

Elements shows at most 24 pages per query; the page sizes are its own
(48 for most types, 60 photos, 24 music / sound effects).
"""
from envato import fetch, refs
from envato import parsers_elements as E

MAX_PAGES = 24


def _page_seg(page):
    return f"pg-{page}" if page and page > 1 else None


def _path(*segments):
    return "/" + "/".join(s for s in segments if s)


def _filter_segments(filters):
    out = []
    for param in refs.ELEMENTS_FILTERS:
        values = filters.get(param)
        if values:
            out.append(f"{refs.ELEMENTS_FILTERS[param]}-{'+'.join(values)}")
    return out


def _empty(page, per_page=None):
    """A page past the end (404): the last real page is the one before it."""
    return {"items": [], "pagination": {"page": page, "items_per_page": per_page, "total_pages": max(page - 1, 0),
                                        "total_count": None}}


def search(type, query=None, category=None, sort=None, claim_clear=None, portfolio=None, page=1, **filters):
    """Search one Envato Elements content type with every filter the site offers; returns item cards, filter values and paging."""
    seg = refs.ELEMENTS_TYPES[type]
    segments = [seg, category, refs.elements_slug(query) if query else None]
    if claim_clear:
        segments.append("claim-clear-compatible")
    if portfolio:
        segments.append(f"portfolio-{portfolio}")
    segments += _filter_segments(filters)
    if not query:
        # browse: the bare type URL is a marketing landing for some types
        # (stock-video, music, 3d); an explicit sort always yields the grid
        segments.append(f"sort-by-{sort if sort in ('popular', 'latest') else 'popular'}")
    elif sort and sort != "relevant":
        segments.append(f"sort-by-{sort}")
    segments.append(_page_seg(page))
    path = _path(*segments)
    try:
        data = fetch.elements_page(path, label="search")
    except fetch.EnvatoNotFound:
        if page > 1:
            return {"type": type, "query": query, **_empty(page)}
        raise
    result = E.search_page(data, page, path)
    return {"type": type, "query": query, "category": category, **result}


def search_all(query):
    """Search every Envato Elements content type at once: top matches per type plus related searches."""
    data = fetch.elements_page(_path("all-items", refs.elements_slug(query)), label="search")
    return E.search_all(data)


def item_details(item):
    """Everything on an Elements item: attributes, tags, audio / video / font previews, series, related items and dates."""
    data = fetch.elements_page(f"/{item.get('slug') or 'x'}-{item['id']}", label="item",
                               missing=f"item {item['id']} not found on Envato Elements")
    return E.item_page(data)


def similar(item, page=1):
    """Items similar to one item (the item's type decides the grid)."""
    details = fetch.elements_page(f"/{item.get('slug') or 'x'}-{item['id']}", label="item",
                                  missing=f"item {item['id']} not found on Envato Elements")
    item_type = (details.get("item") or {}).get("itemType")
    seg = refs.ELEMENTS_TYPES.get(item_type)
    if not seg:
        raise fetch.EnvatoNotFound(f"item {item['id']} has no similar-items grid")
    path = _path(seg, f"similar-to-{item['id']}", _page_seg(page))
    try:
        data = fetch.elements_page(path, label="similar items")
    except fetch.EnvatoNotFound:
        if page > 1:
            return {"item": {"id": item["id"]}, **_empty(page)}
        raise
    result = E.search_page(data, page, path)
    return {"item": {"id": item["id"], "name": (details.get("item") or {}).get("title"), "type": item_type},
            "items": result["items"], "pagination": result["pagination"]}


def author_items(author, type=None, page=1):
    """An Elements author's items, optionally for one content type."""
    path = _path("user", author["username"], refs.ELEMENTS_TYPES.get(type) if type else None, _page_seg(page))
    try:
        data = fetch.elements_page(path, label="author",
                                   missing=f"author {author['username']} not found on Envato Elements")
    except fetch.EnvatoNotFound:
        if page > 1:
            return {"author": {"username": author["username"]}, **_empty(page)}
        raise
    return E.author_page(data, page)


def free_files():
    """This week's free Envato Elements files."""
    return E.free_files(fetch.elements_page("/free-files", label="free files"))


def popular_searches(type=None, letter=None):
    """Popular Envato Elements searches: per content type, or A-Z for one type."""
    if letter and not type:
        raise fetch.EnvatoBadRequest("`letter` needs a `type`")
    path = _path("popular-searches", refs.ELEMENTS_TYPES.get(type) if type else None, letter)
    if type == "music":
        path = _path("popular-searches", "music", letter)
    data = fetch.elements_page(path, label="popular searches")
    return {"type": type, "letter": letter, **E.popular_searches(data)}


def categories(type=None):
    """No type: every content type. With a type: its categories and filters
    (with the values /envato/elements/search accepts)."""
    if not type:
        data = fetch.elements_page("/fonts", label="types")
        return {"types": [{"type": refs.ELEMENTS_SEGMENT_TYPES.get((t.get("url") or "").strip("/"), t.get("id")),
                           "name": t.get("name"),
                           "link": E.link(t.get("url") or f"/{refs.ELEMENTS_TYPES.get(t.get('id'), t.get('id'))}")}
                          for t in data.get("itemTypes") or []]}
    base_path = _path(refs.ELEMENTS_TYPES[type])
    path = base_path + "/sort-by-popular"
    data = fetch.elements_page(path, label="categories")
    result = E.search_page(data, 1, path)
    cats = next((f for f in result["filters"] if f["param"] == "category"), None)
    return {"type": type, "items_count": result["pagination"]["total_count"],
            "categories": [{"name": o["label"], "value": o["value"], "link": E.link(f"{base_path}/{o['value']}")}
                           for o in (cats or {}).get("options", [])],
            "filters": [f for f in result["filters"] if f["param"] != "category"],
            "sort_options": [o for o in result["sort_options"] if o != "relevant"] + ["relevant"]}
