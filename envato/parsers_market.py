"""Envato Market HTML parsers (Rails / Turbo server-rendered pages).

Every function takes page HTML (or a BeautifulSoup node) and returns plain
JSON-able dicts with snake_case keys, `link` for URLs, numbers as numbers,
ISO dates, and None for anything missing. Nothing here raises on a partial
page: every lookup is guarded, so a redesigned block degrades to nulls.

Surfaces (all verified 2026-09-21 on the seven marketplaces):
  item cards      the shared "shared-item_cards-*" components (list-image,
                  grid-image, grid-video, list-audio, masonry photo) on
                  search / category / popular / top-sellers / collection pages
  portfolio rows  the older ".product-list" rows on /user/<name>/portfolio
  item page       JSON-LD Product (+ AudioObject / ImageObject /
                  SoftwareApplication), header, purchase panel (licenses +
                  support prices), meta-attributes table, previews, badges
  reviews         article#review_<id> (stars, reason, body, author response)
  comments        .comment__container-redesign threads (root + replies)
  support tab     FAQ, support policy, external support link
  profile         .user-info-header + tabs, bio, featured item, badges
  user rows       ".user-list > li" (followers, following, top authors, new authors)
  category tree   the nested ".category-section" lists on /category
"""
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urljoin, urlparse

from envato.util import clean, count, iso_datetime, soup, text, to_float, to_int

from envato import refs

CURRENCY = "USD"          # Envato Market prices every item in US dollars (site notice)

_PRICE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)")
_RATED_RE = re.compile(r"Rated\s+([\d.]+)\s+out of\s+5(?:,\s*([\d.,]+[KkMm]?)\s+reviews?)?", re.I)
_AGO_RE = re.compile(r"(\d+|an?|one)\s+(second|minute|hour|day|week|month|year)s?\s+ago", re.I)
_MONTH_YEAR_RE = re.compile(r"([A-Z][a-z]+)\s+(\d{4})")
_DURATION_RE = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})$")
_ITEM_PATH_RE = re.compile(r"/item/([^/?#]+)/(?:reviews/)?(\d+)")
_USER_PATH_RE = re.compile(r"/user/([^/?#]+)")
_YES_NO = {"yes": True, "no": False}
_SITE_TITLES = {"themeforest", "codecanyon", "videohive", "audiojungle", "graphicriver", "photodune",
                "3docean", "envatomarket"}


# ---- value helpers ---------------------------------------------------------------

def price(value):
    """'$1,175' / '$46.63' / 35 -> float; junk -> None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = _PRICE_RE.search(str(value))
    if m:
        return float(m.group(1).replace(",", ""))
    return to_float(str(value).replace(",", "").strip() or None)


def money(amount):
    return {"amount": amount, "currency": CURRENCY} if amount is not None else None


def ago_to_date(value, today=None):
    """'2 months ago' -> an ESTIMATED ISO date (the site shows nothing
    more precise for reviews, comments and item creation)."""
    m = _AGO_RE.search(value or "")
    if not m:
        return None
    n = m.group(1).lower()
    n = 1 if n in ("a", "an", "one") else int(n)
    days = {"second": 0, "minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}[m.group(2).lower()]
    today = today or datetime.now(timezone.utc).date()
    return (today - timedelta(days=days * n)).isoformat()


def month_year(value):
    """'Member since March 2012' -> '2012-03'."""
    m = _MONTH_YEAR_RE.search(value or "")
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%B %Y").strftime("%Y-%m")
    except ValueError:
        return None


def long_date(value):
    """'26 August 2026' / '29 Apr 26' -> ISO date."""
    value = clean(value)
    if not value:
        return None
    for fmt in ("%d %B %Y", "%d %b %Y", "%d %b %y", "%B %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def duration_seconds(value):
    """'4:00' / '1:02:03' / '0:08' -> seconds."""
    m = _DURATION_RE.match((value or "").strip())
    if not m:
        return None
    hours, minutes, seconds = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
    return hours * 3600 + minutes * 60 + seconds


def snake(label):
    """'Compatible Browsers' -> 'compatible_browsers'; 'Tempo (BPM)' -> 'tempo_bpm'."""
    label = re.sub(r"[^\w]+", "_", (label or "").lower()).strip("_")
    return re.sub(r"_+", "_", label) or None


def absolute(href, base):
    if not href:
        return None
    href = href.strip()
    if href.startswith("//"):
        return "https:" + href
    return urljoin(base + "/", href)


def strip_query(link):
    return link.split("?")[0].split("#")[0] if link else link


def item_link_id(href):
    """'…/item/avada-…/2833226?s_rank=3' -> (slug, 2833226)."""
    m = _ITEM_PATH_RE.search(href or "")
    return (m.group(1), int(m.group(2))) if m else (None, None)


def username_from(href):
    m = _USER_PATH_RE.search(href or "")
    return m.group(1) if m else None


def stars(node):
    """Count full / half star icons (i.e.-icon-star*, b.star-rating__star--*,
    img.rating-basic__star) -> 4.5; no icons -> None."""
    if node is None:
        return None
    total, seen = 0.0, False
    for icon in node.select("i.e-icon, b[class*=star-rating__star], img.rating-basic__star"):
        classes = " ".join(icon.get("class", [])) + " " + (icon.get("src") or "")
        if "half" in classes:
            total += 0.5
            seen = True
        elif "empty" in classes or "star-none" in classes or "color-grey" in classes:
            seen = True
        elif "star" in classes:
            total += 1
            seen = True
    return total if seen else None


def lazy_src(node):
    """<img src> or the lazy-load span's data-src."""
    if node is None:
        return None
    return node.get("src") or node.get("data-src") or None


def badges(root):
    """Community badges (lazy-load spans with data-alt / data-title)."""
    out, seen = [], set()
    if root is None:
        return out
    for img in root.select(".badges .lazy-load-img, .badges img"):
        name = text(img.get("data-alt") or img.get("alt"))
        if not name or name in seen:
            continue
        seen.add(name)
        title = text(img.get("data-title") or img.get("title"))
        description = title.split(":", 1)[1].strip() if title and ":" in title else None
        out.append({"name": name, "description": description, "icon": lazy_src(img)})
    return out


def ld_json(doc):
    """All JSON-LD objects on the page, keyed by @type."""
    out = {}
    for tag in doc.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (TypeError, ValueError):
            continue
        for obj in data if isinstance(data, list) else [data]:
            if isinstance(obj, dict) and obj.get("@type"):
                out.setdefault(obj["@type"], obj)
    return out


def page_title(doc):
    return clean(doc.title) if doc.title else None


def results_total(doc):
    for node in doc.find_all(string=re.compile(r"^\s*[\d,]+\s+results?\s*$")):
        return count(node)
    return None


def pages_total(doc):
    """Highest page number linked from the pagination nav."""
    numbers = []
    for a in doc.select("nav[class*=pagination] a, .pagination a, [class*=pagination] a"):
        q = parse_qs(urlparse(a.get("href") or "").query)
        numbers.append(to_int((q.get("page") or [None])[0]))
        numbers.append(to_int(clean(a)))
    numbers = [n for n in numbers if n]
    return max(numbers) if numbers else None


# ---- item cards (search / category / popular / collections) -------------------------

def _card_price(node):
    box = node.select_one("[class*=price_component__root]")
    original = promo = None
    if box is not None:
        original = price(clean(box.select_one("[class*=originalPrice]")))
        promo = price(clean(box.select_one("[class*=promoPrice]")))
        plain = price(clean(box))
    else:
        plain = None
    current = promo if promo is not None else (plain if original is None else None)
    if current is None:
        current = to_float(node.get("data-price"))
    return {"amount": current, "original_amount": original if promo is not None else None,
            "currency": CURRENCY, "is_on_sale": promo is not None}


def _card_rating(node):
    label = None
    rating = node.select_one("[class*=stars_rating_component__starRating]")
    if rating is not None:
        label = rating.get("aria-label")
    m = _RATED_RE.search(label or "")
    if not m:
        return {"average": None, "count": None}
    return {"average": to_float(m.group(1)), "count": count(m.group(2)) if m.group(2) else None}


def _card_audio(node, base):
    player = node.select_one("[data-file]")
    if player is None:
        return None
    tracks = node.select_one("[class*=audio_tracks_info_component__root]")
    lengths = []
    if tracks is not None:
        raw = clean(tracks) or ""
        tail = raw.split("Track lengths:", 1)[1] if "Track lengths:" in raw else ""
        lengths = [duration_seconds(x.strip()) for x in tail.split(",") if duration_seconds(x.strip()) is not None]
    track_count = to_int(clean(tracks.select_one("[class*=__black]"))) if tracks is not None else None
    duration = None
    for span in node.select("[class*=timeContainer], [data-audio-player-target=duration]"):
        seconds = duration_seconds(clean(span))
        if seconds:
            duration = seconds
    return {
        "preview_link": absolute(player.get("data-file"), base),
        "waveform_link": absolute(player.get("data-waveform"), base),
        "duration_seconds": duration,
        "track_count": track_count or (len(lengths) or None),
        "track_lengths_seconds": lengths,
        "bpm": to_int(clean(node.select_one("[class*=beats_per_minute_component__bpm]"))),
    }


def item_card(node, base):
    """One shared item card -> dict (None when it has no item link)."""
    link_node = node.select_one("a[href*='/item/']")
    slug, item_id = item_link_id(link_node.get("href") if link_node else None)
    item_id = to_int(node.get("data-item-id")) or item_id
    if not item_id:
        return None
    name_node = node.select_one("[class*=item_name_component__itemNameLink]")
    img = node.select_one("img[class*=preview_image_component__image], img[class*=audio_thumbnail], "
                          "img[class*=masonry], img")
    name = clean(name_node) or (text(img.get("alt")) if img is not None else None) \
        or text(link_node.get("title") if link_node else None)
    author = category = None
    for a in node.select("[class*=author_category_component__link]"):
        href = a.get("href") or ""
        if "/user/" in href and author is None:
            author = {"username": username_from(href), "name": clean(a), "link": strip_query(absolute(href, base))}
        elif "/category/" in href and category is None:
            path = urlparse(href).path.split("/category/", 1)[1].strip("/")
            category = {"name": clean(a), "path": path, "link": absolute("/category/" + path, base)}
    if author is None:
        a = node.select_one("a[href*='/user/']")
        if a is not None:
            author = {"username": username_from(a.get("href")), "name": clean(a),
                      "link": strip_query(absolute(a.get("href"), base))}
    video = node.select_one("video")
    updated = node.select_one("[class*=lastUpdated]")
    updated_text = (clean(updated) or "").replace("Last updated:", "").strip()
    preview = node.select_one("a[href*='full_screen_preview']")
    rating = _card_rating(node)
    return {
        "id": item_id,
        "name": name,
        "link": absolute(f"/item/{slug or 'x'}/{item_id}", base) if slug else strip_query(absolute(link_node.get("href"), base)) if link_node else None,
        "author": author,
        "category": category,
        "price": _card_price(node),
        "rating": rating["average"],
        "reviews_count": rating["count"],
        "sales_count": count(clean(node.select_one("[class*=sales_component__root]"))),
        "last_updated": long_date(updated_text) if updated_text else None,
        "key_features": [clean(li) for li in node.select("[class*=key_features_component__feature]") if clean(li)],
        "image": (lazy_src(img) if img is not None else None) or (video.get("poster") if video is not None else None),
        "large_image": img.get("data-fallback") if img is not None and img.get("data-fallback") else None,
        "live_preview_link": absolute(preview.get("href"), base) if preview is not None else None,
        "video_preview_link": video.get("src") if video is not None else None,
        "audio_preview": _card_audio(node, base),
        "is_in_elements": node.has_attr("data-elements-cta-badge") or bool(node.find(string=re.compile("Get unlimited"))),
    }


def item_cards(doc, base):
    """Every shared item card on a page, in page order, deduplicated."""
    out, seen = [], set()
    for node in doc.find_all(attrs={"data-item-id": True, "data-price": True}):
        card = item_card(node, base)
        if card and card["id"] not in seen:
            seen.add(card["id"])
            out.append(card)
    return out


# ---- search facets --------------------------------------------------------------------

# upstream query param -> (our param, value map upstream->public or None)
_FACET_PARAMS = {
    "sales": ("sales", {v: k for k, v in refs.MARKET_SALES_BANDS.items()}),
    "date": ("date_added", {v: k for k, v in refs.MARKET_DATE_RANGES.items()}),
    "date_updated": ("date_updated", {v: k for k, v in refs.MARKET_DATE_RANGES.items()}),
    "rating_min": ("rating_min", None),
    "compatible_with": ("compatible_with", None),
    "platform": ("software_version", None),
    "discounted_only": ("on_sale", {"1": "true"}),
    "resolution_min": ("resolution_min", None),
    "frame_rate": ("frame_rate", None),
    "requires_plugins": ("requires_plugins", {"T": "true", "F": "false"}),
    "alpha": ("has_alpha_channel", {"1": "true"}),
    "looped": ("is_looped", {"1": "true"}),
    "vocals_in_audio": ("vocals", {v: k for k, v in refs.MARKET_VOCALS.items()}),
    "tempo": ("tempo", None),
    "include_pro_affiliated": ("include_pro_music", None),
    "orientation": ("orientation", None),
    "sizes": ("size", None),
    "colors": ("color", None),
    "file_formats": ("file_format", None),
}


def _facet_option(a, count_node):
    href = a.get("href") or ""
    parsed = urlparse(href)
    query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    label = clean(a.find(string=True, recursive=False)) or clean(a)
    counted = count(clean(count_node)) if count_node is not None else None
    if counted is None:
        span = a.select_one("[class*=count]")
        counted = count(clean(span)) if span is not None else None
        if span is not None and label:
            label = clean(label.replace(clean(span) or "", "")) or label
    selected = "current" in " ".join(a.get("class", [])) or a.select_one("input[checked]") is not None
    if "/category/" in parsed.path:
        return "category", parsed.path.split("/category/", 1)[1].strip("/"), label, counted, selected
    for key, (param, mapping) in _FACET_PARAMS.items():
        if key in query:
            value = query[key]
            return param, (mapping.get(value, value) if mapping else value), label, counted, selected
    return None, None, label, counted, selected


def facets(doc):
    """Sidebar filters -> [{name, param, options: [{label, value, count, is_selected}]}].
    `param` / `value` are what /envato/market/search accepts; "all"
    options (no filter) are dropped. Range filters (price, length,
    polygons) have no options and are left out."""
    out = []
    for block in doc.find_all(attrs={"data-filter-title": True}):
        name = block.get("data-filter-title")
        options, param_name = [], None
        for a in block.find_all("a", href=True):
            count_node = a.find_next_sibling(class_=re.compile("count"))
            param, value, label, counted, selected = _facet_option(a, count_node)
            if param is None or value in (None, ""):
                continue
            param_name = param_name or param
            options.append({"label": label, "value": value, "count": counted, "is_selected": selected})
        if options:
            out.append({"name": name, "param": param_name, "options": options})
    return out


# ---- portfolio rows (older product-list markup) -------------------------------------------

_ATTR_SPLIT_RE = re.compile(r",\s+(?=[A-Z][\w .()/&'-]{1,40}:\s)")


def portfolio_attributes(value):
    """'Gutenberg Optimized: Yes, Compatible With: Elementor, WooCommerce 9.x.x'
    -> {"gutenberg_optimized": True, "compatible_with": ["Elementor", …]}."""
    out = {}
    for part in _ATTR_SPLIT_RE.split(value or ""):
        if ":" not in part:
            continue
        key, raw = part.split(":", 1)
        out[snake(key)] = attribute_value(raw)
    return out


def attribute_value(raw):
    raw = clean(raw)
    if raw is None:
        return None
    if raw.lower() in _YES_NO:
        return _YES_NO[raw.lower()]
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts if len(parts) > 1 else raw


def portfolio_row(node, base):
    heading = node.select_one(".product-list__heading a")
    slug, item_id = item_link_id(heading.get("href") if heading else None)
    if not item_id:
        return None
    img = node.select_one(".item-thumbnail__image img")
    preview = node.select_one(".item-thumbnail__preview a")
    author = node.select_one(".product-list__info-author a")
    crumbs = [clean(b) for b in node.select(".meta-categories b") if clean(b)]
    category_block = node.select_one(".product-list__column-category p")
    attrs_text = None
    if category_block is not None:
        parts = [clean(s) for s in category_block.find_all(string=True, recursive=False) if clean(s)]
        attrs_text = parts[-1] if parts else None
    sales = node.select_one(".product-list__info-sale")
    return {
        "id": item_id,
        "name": clean(heading),
        "link": absolute(f"/item/{slug}/{item_id}", base),
        "author": {"username": username_from(author.get("href")), "name": clean(author),
                   "link": strip_query(absolute(author.get("href"), base))} if author is not None else None,
        "category": {"name": crumbs[-1], "breadcrumbs": crumbs} if crumbs else None,
        "price": money(price(clean(node.select_one(".product-list__price")))),
        "sales_count": count(clean(sales)) if sales is not None else None,
        "attributes": portfolio_attributes(attrs_text) if attrs_text and ":" in attrs_text else {},
        "image": img.get("src") if img is not None else None,
        "large_image": img.get("data-preview-url") if img is not None else None,
        "live_preview_link": preview.get("href") if preview is not None else None,
    }


def portfolio_rows(doc, base):
    rows = [portfolio_row(n, base) for n in doc.select(".product-list__columns-container")]
    return [r for r in rows if r]


# ---- item page ----------------------------------------------------------------------------

def _licenses(doc):
    out = []
    descriptions = {}
    for item in doc.select(".license-selector__item"):
        descriptions[item.get("data-license")] = (clean(item.select_one(".license-selector__description")),
                                                  item.get("data-name"))
    for tag in doc.select("price.js-purchase-license-prices, .js-purchase-license-prices"):
        key = tag.get("data-license")
        description, name = descriptions.get(key, (None, None))
        out.append({
            "type": key,
            "name": name or (f"{key.title()} License" if key else None),
            "description": description,
            "price": price(tag.get("data-price-prepaid")),
            "price_with_extended_support": price(tag.get("data-price-prepaid-upgrade")),
            "support_upgrade_price": price(tag.get("data-support-upgrade-price")),
            "support_upgrade_saving": price(tag.get("data-support-upgrade-saving")),
            "support_extension_price": price(tag.get("data-support-extension-price")),
            "support_extension_saving": price(tag.get("data-support-extension-saving")),
            "support_renewal_price": price(tag.get("data-support-renewal-price")),
            "currency": CURRENCY,
        })
    return out


def _attributes(doc, base):
    out = {}
    for row in doc.select(".meta-attributes__table tr"):
        name = row.select_one(".meta-attributes__attr-name")
        detail = row.select_one(".meta-attributes__attr-detail")
        if detail is None:                     # the Tags cell carries no class
            cells = row.find_all("td")
            detail = cells[1] if len(cells) > 1 else None
        key = snake(clean(name))
        if not key or detail is None:
            continue
        stamp = detail.select_one("time[datetime]")
        if stamp is not None:
            out[key] = (iso_datetime(stamp.get("datetime")) or "")[:10] or long_date(clean(stamp))
            continue
        links = [clean(a) for a in detail.find_all("a") if clean(a)]
        out[key] = links if len(links) > 1 else attribute_value(clean(detail)) if not links else \
            (links if key == "tags" else attribute_value(links[0]))
    return out


def _nav_counts(doc):
    reviews = comments = None
    for a in doc.select("a[href*='/reviews/'], a[href$='/comments']"):
        label = clean(a) or ""
        if "/reviews/" in a.get("href", "") and reviews is None:
            m = re.search(r"([\d.,]+[KkMm]?)\s*$", label)
            reviews = count(m.group(1)) if m else None
        elif a.get("href", "").endswith("/comments") and comments is None:
            m = re.search(r"([\d.,]+[KkMm]?)\s*$", label)
            comments = count(m.group(1)) if m else None
    return reviews, comments


def _previews(doc, base, ld):
    box = doc.select_one(".item-preview")
    out = {"image": None, "thumbnail": None, "live_preview_link": None, "screenshots_link": None,
           "screenshots": [], "video_preview_link": None, "audio_preview": None}
    product = ld.get("Product") or {}
    out["thumbnail"] = product.get("image")
    if box is not None:
        img = box.select_one("img")
        out["image"] = img.get("src") if img is not None else None
        live = box.select_one("a[href*='full_screen_preview']")
        out["live_preview_link"] = absolute(live.get("href"), base) if live is not None else None
        gallery = box.select_one("a[href*='/screenshots/']")
        out["screenshots_link"] = absolute(gallery.get("href"), base) if gallery is not None else None
        out["screenshots"] = [a.get("href") for a in box.select(".item-preview-image__gallery a.is-hidden, "
                                                                "[class*=item-preview-image__gallery] a.is-hidden")
                              if a.get("href")]
        video = box.select_one("a.js-video-player, [class*=video-player][href$='.mp4']")
        out["video_preview_link"] = video.get("href") if video is not None else None
        player = box.select_one(".waveform-player[data-file]")
        if player is not None:
            out["audio_preview"] = {"preview_link": player.get("data-file"),
                                    "waveform_link": player.get("data-waveform"),
                                    "duration_seconds": duration_seconds(player.get("data-duration"))}
    image_obj = ld.get("ImageObject") or {}
    if not out["image"] and image_obj.get("contentUrl"):
        out["image"] = image_obj.get("contentUrl")
    return out


def _more_by_author(doc, base):
    out = []
    for span in doc.select(".related-by-author .item-thumbnail__image .lazy-load-img, "
                           ".related-by-author .item-thumbnail__image img"):
        item_id = to_int(span.get("data-data-item-id") or span.get("data-item-id"))
        link = span.find_parent("a")
        slug, parsed_id = item_link_id(link.get("href") if link else None)
        item_id = item_id or parsed_id
        if not item_id:
            continue
        category = text(span.get("data-data-item-category") or span.get("data-item-category"))
        out.append({
            "id": item_id,
            "name": text(span.get("data-data-item-name") or span.get("data-item-name") or span.get("data-title")),
            "link": absolute(f"/item/{slug or 'x'}/{item_id}", base),
            "price": money(price(span.get("data-data-item-cost") or span.get("data-item-cost"))),
            "category": [c.strip() for c in category.split("/")] if category else [],
            "image": lazy_src(span),
            "large_image": text(span.get("data-data-preview-url") or span.get("data-preview-url")),
        })
    return out


def _breadcrumbs(doc, base):
    out = []
    for a in doc.select("nav.breadcrumbs a"):
        href = a.get("href") or ""
        label = clean(a)
        if not label or href in ("/", "") or label in ("Home", "Files"):
            continue
        out.append({"name": label, "link": absolute(href, base)})
    return out


def item_page(markup, base, site):
    doc = soup(markup)
    ld = ld_json(doc)
    product = ld.get("Product") or {}
    offer = product.get("offers") or {}
    aggregate = product.get("aggregateRating") or (ld.get("SoftwareApplication") or {}).get("aggregateRating") or {}
    canonical = doc.find("link", rel="canonical")
    link = canonical.get("href") if canonical is not None else product.get("url")
    slug, item_id = item_link_id(link)
    header = doc.select_one(".item-header")
    author_link = doc.select_one(".item-header__author-details a, a[rel=author]")
    author_box = None
    for box in doc.select(".sidebar-right .box"):
        if box.select_one("a.avatar"):
            author_box = box
            break
    avatar = author_box.select_one("a.avatar .lazy-load-img, a.avatar img") if author_box is not None else None
    author_name = clean(author_link) or (product.get("brand") or {}).get("name")
    username = username_from(author_link.get("href")) if author_link is not None else None
    description_node = doc.select_one(".js-item-description .user-html, .item-description .user-html, "
                                      "[itemprop=description] .user-html, .user-html")
    attributes = _attributes(doc, base)
    tags = attributes.pop("tags", None)
    created_relative = attributes.pop("created", None)
    last_update = attributes.pop("last_update", None)
    reviews_count, comments_count = _nav_counts(doc)
    rating_block = doc.select_one(".rating-detailed-small")
    rating_value = to_float(aggregate.get("ratingValue"))
    if rating_value is None and rating_block is not None:
        m = re.search(r"([\d.]+)\s+stars", clean(rating_block) or "")
        rating_value = to_float(m.group(1)) if m else None
    highlights = [clean(x) for x in doc.select(".item-header__envato-highlighted strong") if clean(x)]
    includes = [clean(li.find(string=True, recursive=False)) or clean(li)
                for li in doc.select(".purchase-form__support li")]
    includes = [re.sub(r"\s*More Info$", "", re.sub(r"^Included:\s*", "", x)) for x in includes if x]
    sales_node = doc.select_one(".item-header__sales-count strong")
    published = ld.get("AudioObject") or ld.get("ImageObject") or ld.get("SoftwareApplication") or {}
    last_updated = last_update or (iso_datetime(published.get("datePublished")) or "")[:10] or None
    created_relative = created_relative if isinstance(created_relative, str) else None
    created_estimated = ago_to_date(created_relative)
    if created_estimated and last_updated and created_estimated > last_updated:
        created_estimated = last_updated          # "10 years ago" rounds past the first release
    return {
        "id": item_id or to_int(product.get("sku")),
        "name": clean(product.get("name")) or (clean(header.select_one("h1")) if header is not None else None),
        "link": link,
        "site": site,
        "slug": slug,
        "description": clean(product.get("description")) or clean(description_node),
        "description_html": description_node.decode_contents().strip() if description_node is not None else None,
        "category": {
            "name": text(product.get("category")),
            "breadcrumbs": _breadcrumbs(doc, base),
        },
        "tags": tags if isinstance(tags, list) else ([tags] if tags else []),
        "highlights": highlights,
        "price": money(price(offer.get("price")) or price(clean(doc.select_one(".js-purchase-price")))),
        "licenses": _licenses(doc),
        "purchase_includes": includes,
        "rating": rating_value,
        "reviews_count": to_int(aggregate.get("reviewCount") or aggregate.get("ratingCount")) or reviews_count,
        "comments_count": comments_count,
        "sales_count": count(clean(sales_node)) if sales_node is not None else None,
        "is_in_stock": (offer.get("availability") or "").endswith("InStock") if offer else None,
        "attributes": attributes,
        "media": _previews(doc, base, ld),
        "author": {
            "username": username,
            "name": author_name,
            "link": absolute(f"/user/{username}", base) if username else None,
            "avatar": lazy_src(avatar),
            "badges": badges(author_box),
        },
        "more_by_author": _more_by_author(doc, base),
        "last_updated": last_updated,
        "created_relative": created_relative,
        "created_estimated": created_estimated,
    }


# ---- reviews ------------------------------------------------------------------------------

def _own(node, selector, container="article"):
    """node.select(selector) minus matches that belong to a nested
    container (the reviews page leaves <article> tags unclosed, so each
    review parses as a child of the one before it)."""
    return [el for el in node.select(selector) if el.find_parent(container) is node]


def review(node, base):
    rid = to_int((node.get("id") or "").replace("review_", ""))
    header = _own(node, ".review-header")
    header = header[0] if header else None
    if header is None:
        return None
    star_box = header.select_one(".rating-basic__star-rating")
    reason = header.select_one(".review-header__rating strong")
    reviewer = header.select_one(".review-header__reviewer a[href*='/user/']")
    date_node = header.select_one(".review-header__date a")
    body = None
    response = None
    for box in _own(node, "div.e-box"):
        if box.find_parent("header") is not None:
            continue
        if box.select_one(".media"):
            media_body = box.select_one(".media__body")
            paragraphs = [p for p in (media_body.find_all("p") if media_body else [])
                          if clean(p) != "Author response"]
            avatar = box.select_one(".media__item .lazy-load-img, .media__item img")
            response = {
                "author": text(avatar.get("data-alt") or avatar.get("alt")) if avatar is not None else None,
                "author_avatar": lazy_src(avatar),
                "text": "\n".join(p.get_text("\n", strip=True) for p in paragraphs) or None,
            }
        else:
            body = "\n".join(p.get_text("\n", strip=True) for p in box.find_all("p")) or clean(box)
    relative = clean(date_node)
    return {
        "id": rid,
        "rating": stars(star_box),
        "reason": clean(reason),
        "text": body,
        "reviewer": {"username": username_from(reviewer.get("href")), "name": clean(reviewer),
                     "link": absolute(f"/user/{username_from(reviewer.get('href'))}", base)} if reviewer is not None else None,
        "author_response": response,
        "link": absolute(date_node.get("href"), base) if date_node is not None else None,
        "date_relative": relative,
        "date_estimated": ago_to_date(relative),
    }


def reviews_page(markup, base):
    doc = soup(markup)
    items = [review(a, base) for a in doc.select("article[id^=review_]")]
    aggregate = doc.select_one(".reviews-controls__aggregate")
    total = count(clean(aggregate.select_one("strong"))) if aggregate is not None else None
    detailed = doc.select_one(".rating-detailed-small")
    m = re.search(r"([\d.]+)\s+stars", clean(detailed) or "") if detailed is not None else None
    return {
        "reviews": [r for r in items if r],
        "total": total,
        "rating": to_float(m.group(1)) if m else None,
        "total_pages": pages_total(doc),
        "item_name": _item_name_from_title(page_title(doc), "Reviews for "),
    }


def _item_name_from_title(title, prefix):
    """'Reviews for Avada | Website Builder … (Page 2) | ThemeForest' -> 'Avada | Website Builder …'."""
    if not title:
        return None
    head, _, tail = title.rpartition(" | ")
    if head and tail.replace(" ", "").lower() in _SITE_TITLES:
        title = head
    title = re.sub(r"\s*\(Page \d+\)\s*$", "", title).strip()
    return title[len(prefix):].strip() if title.startswith(prefix) else title


# ---- comments -----------------------------------------------------------------------------

def _comment(node, base):
    info = node.select_one(".comment__info")
    if info is None:
        return None
    cid = to_int((info.get("id") or "").replace("comment_", ""))
    user = info.select_one("a[href*='/user/']")
    label = info.select_one(".e-text-label")
    date_node = info.select_one(".comment__date")
    avatar = info.select_one(".media__item img, .media__item .lazy-load-img")
    body = node.select_one(".js-comment__body")
    relative = clean(date_node)
    role = clean(label)
    username = username_from(user.get("href")) if user is not None else None
    return {
        "id": cid,
        "text": body.get_text("\n", strip=True) if body is not None else None,
        "html": body.decode_contents().strip() if body is not None else None,
        "user": {"username": username, "name": clean(user),
                 "link": absolute(f"/user/{username}", base) if username else None,
                 "avatar": lazy_src(avatar)},
        "user_label": role,
        "is_author": bool(role and role.lower().startswith("author")),
        "is_buyer": bool(role and role.lower() == "purchased"),
        "link": absolute(date_node.get("href"), base) if date_node is not None else None,
        "date_relative": relative,
        "date_estimated": ago_to_date(relative),
    }


def comments_page(markup, base):
    doc = soup(markup)
    threads = []
    for container in doc.select(".comment__container-redesign"):
        root = container.select_one(".comment__item")
        first = _comment(root, base) if root is not None else None
        if first is None:
            continue
        first["replies"] = [c for c in (_comment(r, base) for r in container.select(".comment__item-response")) if c]
        first["replies_count"] = len(first["replies"])
        threads.append(first)
    total = None
    for heading in doc.select("h2, h3, .t-heading"):
        m = re.search(r"([\d,]+)\s+comments? found", clean(heading) or "")
        if m:
            total = count(m.group(1))
            break
    return {"comments": threads, "total": total, "total_pages": pages_total(doc),
            "item_name": _item_name_from_title(page_title(doc), "Discussion on ")}


# ---- support tab ----------------------------------------------------------------------------

def support_page(markup, base):
    doc = soup(markup)
    supporter = None
    is_supported = False
    for h in doc.select(".author-summary__infoflex h3"):
        label = clean(h) or ""
        if "supports this item" in label:
            supporter = label.replace("supports this item", "").strip() or None
            is_supported = True
        elif "does not support" in label:
            supporter = label.split(" does not support")[0].strip() or None
    status = doc.select_one(".author-summary__infoflex .e-text-label")
    faq = []
    for art in doc.select("article.faq__item"):
        q = art.select_one(".faq__question")
        a = art.select_one(".faq__answer .user-html") or art.select_one(".faq__answer")
        faq.append({"question": clean(q), "answer": a.get_text("\n", strip=True) if a is not None else None,
                    "answer_html": a.decode_contents().strip() if a is not None else None})
    includes, excludes, note, support_link, policy_link = [], [], None, None, None
    contact = None
    for h in doc.find_all(["h3", "h2"]):
        if "Contact the author" in (clean(h) or ""):
            contact = h.find_parent("div")
            break
    if contact is not None:
        first_p = contact.find("p")
        note = clean(first_p)
        for li in contact.select("li.-icon-ok"):
            includes.append(clean(li))
        for li in contact.select("li.-icon-cancel"):
            excludes.append(clean(li))
        cta = contact.select_one(".item-support__cta a, a.js-support-contact__button")
        support_link = cta.get("href") if cta is not None else None
        policy = contact.select_one("a[href*='support_policy']")
        policy_link = absolute(policy.get("href"), base) if policy is not None else None
    return {
        "is_supported": is_supported,
        "status": clean(status),
        "supported_by": supporter,
        "support_note": note,
        "support_includes": [x for x in includes if x],
        "support_excludes": [x for x in excludes if x],
        "support_link": support_link,
        "support_policy_link": policy_link,
        "faq": faq,
        "item_name": _item_name_from_title(page_title(doc), "Support for "),
    }


# ---- profile ----------------------------------------------------------------------------------

def profile(markup, base, site):
    doc = soup(markup)
    header = doc.select_one(".user-info-header")
    if header is None:
        return None
    name_node = header.select_one("h1")
    link = header.select_one(".user-info-header__content a[href*='/user/']")
    username = username_from(link.get("href")) if link is not None else None
    details = clean(header.select_one(".user-info-header__content")) or ""
    level = clean(header.select_one(".user-info-header__author-level strong"))
    country = None
    for p in header.select(".user-info-header__content p"):
        line = clean(p) or ""
        if "Member since" in line and "," in line:
            country = line.split(",", 1)[0].strip() or None
            break
    rating_box = header.select_one(".rating-detailed")
    rating_text = clean(rating_box) or ""
    rm = re.search(r"([\d.]+)\s+stars", rating_text)
    cm = re.search(r"\(([\d,]+)\s+ratings?\)", rating_text)
    sales = None
    for article in header.select(".user-info-header__stats-article"):
        if "Sales" in (clean(article.select_one(".user-info-header__stats-label")) or ""):
            sales = count(clean(article.select_one(".user-info-header__stats-content")))
    followers = following = None
    for a in doc.select("[class*=user-info-header__tabs] a"):
        label = clean(a) or ""
        badge = count(clean(a.select_one(".e-text-label")))
        if label.startswith("Followers"):
            followers = badge
        elif label.startswith("Following"):
            following = badge
    avatar = header.select_one(".user-info-header__user-profile-image-placeholder, .user-info-header__user-details img")
    bio = doc.select_one(".user-bio .user-html, .user-html")
    cover = doc.select_one(".content-s .item-preview img")
    featured = None
    ff = doc.select_one(".featured-file")
    if ff is not None:
        a = ff.select_one(".featured-file__details a")
        span = ff.select_one(".lazy-load-img, img")
        slug, item_id = item_link_id(a.get("href") if a else None)
        purchases = re.search(r"([\d,]+)\s+purchases", clean(ff) or "")
        featured = {
            "id": item_id,
            "name": clean(a),
            "link": absolute(f"/item/{slug}/{item_id}", base) if item_id else None,
            "price": money(price(span.get("data-data-item-cost") if span is not None else None)),
            "sales_count": count(purchases.group(1)) if purchases else None,
            "image": lazy_src(span),
        }
    collections = []
    for a in doc.select("a[href*='/collections/']"):
        cid = re.search(r"/collections/(\d+)", a.get("href", ""))
        name = clean(a)
        if cid and name and all(c["id"] != int(cid.group(1)) for c in collections):
            collections.append({"id": int(cid.group(1)), "name": name, "link": strip_query(absolute(a.get("href"), base))})
    social = []
    if bio is not None:
        for a in bio.find_all("a", href=True):
            href = a["href"]
            host = (urlparse(href).hostname or "")
            if href.startswith("http") and not any(host.endswith(h) for h in refs.MARKET_HOSTS) and href not in social:
                social.append(href)
    return {
        "username": username,
        "name": clean(name_node),
        "link": absolute(f"/user/{username}", base) if username else None,
        "site": site,
        "author_level": level,
        "country": country,
        "member_since": month_year(details),
        "avatar": lazy_src(avatar),
        "cover_image": cover.get("src") if cover is not None else None,
        "bio": bio.get_text("\n", strip=True) if bio is not None else None,
        "bio_html": bio.decode_contents().strip() if bio is not None else None,
        "external_links": social,
        "rating": to_float(rm.group(1)) if rm else None,
        "ratings_count": count(cm.group(1)) if cm else None,
        "sales_count": sales,
        "followers_count": followers,
        "following_count": following,
        "badges": badges(doc.select_one(".user-info__badges") or doc),
        "featured_item": featured,
        "public_collections": collections,
        "portfolio_link": absolute(f"/user/{username}/portfolio", base) if username else None,
    }


# ---- user rows (followers / following / top authors / new authors) -------------------------------

def user_row(node, base):
    name_link = node.select_one(".user-info__username a")
    if name_link is None:
        return None
    raw = clean(name_link) or ""
    rank = None
    m = re.match(r"^(\d+)\.\s+(.*)$", raw)
    if m:
        rank, raw = int(m.group(1)), m.group(2)
    username = username_from(name_link.get("href"))
    meta = node.select_one("small.meta.is-hidden-phone") or node.select_one("small.meta")
    meta_text = clean(meta) or ""
    items = re.search(r"([\d,]+)\s+Items?", meta_text)
    followers = re.search(r"([\d,]+)\s+Followers?", meta_text)
    sale_info = node.select_one(".sale-info") or node
    rating_node = sale_info.select_one(".rating-basic")
    ratings = re.search(r"([\d,]+)\s+ratings?", clean(rating_node) or "") if rating_node is not None else None
    avatar = node.select_one("a.avatar .lazy-load-img, a.avatar img")
    return {
        "rank": rank,
        "username": username,
        "name": raw or username,
        "link": absolute(f"/user/{username}", base) if username else None,
        "avatar": lazy_src(avatar),
        "items_count": count(items.group(1)) if items else None,
        "followers_count": count(followers.group(1)) if followers else None,
        "sales_count": count(clean(sale_info.select_one(".sale-count"))),
        "rating": stars(rating_node.select_one(".rating-basic__stars")) if rating_node is not None else None,
        "ratings_count": count(ratings.group(1)) if ratings else None,
        "member_since": month_year(meta_text),
        "is_available_for_freelance": "Available for freelance work" in meta_text,
        "badges": badges(node.select_one(".user-info__badges") or node),
    }


def user_rows(doc, base):
    rows = [user_row(li, base) for li in doc.select("ul.user-list > li")]
    return [r for r in rows if r]


# ---- category tree -------------------------------------------------------------------------------

def _category_node(li, base):
    a = li.find("a", recursive=False)
    if a is None:
        return None
    href = a.get("href") or ""
    path = href.split("/category/", 1)[1].strip("/") if "/category/" in href else None
    small = li.find("small", recursive=False)
    child_list = li.find("ul", recursive=False)
    children = [c for c in (_category_node(x, base) for x in child_list.find_all("li", recursive=False))
                if c] if child_list is not None else []
    return {"name": clean(a), "path": path, "link": absolute(href, base),
            "items_count": count((clean(small) or "").strip("()")) if small is not None else None,
            "subcategories": children}


def category_tree(markup, base):
    doc = soup(markup)
    out = []
    for section in doc.select(".category-section"):
        for ul in section.find_all("ul", recursive=False):
            for li in ul.find_all("li", recursive=False):
                node = _category_node(li, base)
                if node:
                    out.append(node)
    return out


# ---- collections ------------------------------------------------------------------------------------

def collection_rows(doc, base):
    out = []
    for node in doc.select(".collection-summary"):
        a = node.select_one(".collection-summary__title a")
        if a is None:
            continue
        href = a.get("href") or ""
        m = re.search(r"/collections/(\d+)(?:-([^/?#]+))?", href)
        owner = node.select_one(".collection-summary__info a[href*='/user/']")
        host = urlparse(href).hostname
        meta = node.select_one(".collection-summary__meta")
        items = re.search(r"([\d,]+)\s+Items?", clean(meta) or "") if meta is not None else None
        rating_node = meta.select_one(".rating-basic") if meta is not None else None
        ratings = re.search(r"([\d,]+)\s+ratings?", clean(rating_node) or "") if rating_node is not None else None
        img = node.select_one(".collection-summary__image img")
        desc = node.select_one(".collection-summary__info p")
        out.append({
            "id": int(m.group(1)) if m else None,
            "name": clean(a),
            "link": strip_query(href) if href.startswith("http") else absolute(strip_query(href), base),
            "site": refs.MARKET_HOSTS.get(host.replace("www.", "")) if host else None,
            "description": clean(desc),
            "owner": {"username": username_from(owner.get("href")), "name": clean(owner),
                      "link": absolute(f"/user/{username_from(owner.get('href'))}",
                                       f"https://{host}" if host else base)} if owner is not None else None,
            "items_count": count(items.group(1)) if items else None,
            "rating": stars(rating_node.select_one(".rating-basic__stars")) if rating_node is not None else None,
            "ratings_count": count(ratings.group(1)) if ratings else None,
            "image": img.get("src") if img is not None else None,
        })
    return out


def collection_page(markup, base):
    doc = soup(markup)
    info = doc.select_one(".collection__info")
    heading = None
    for h in doc.find_all("h1"):
        if clean(h) and "subscription" not in clean(h).lower():
            heading = clean(h)
            break
    owner = None
    side = doc.select_one(".sidebar-right")
    a = (side.select_one(".user-info a[rel=author]") or side.select_one(".user-info a[href*='/user/']")) \
        if side is not None else None
    if a is not None:
        username = username_from(a.get("href"))
        avatar = side.select_one("a.avatar .lazy-load-img, a.avatar img")
        owner = {"username": username, "name": clean(a) or username,
                 "link": absolute(f"/user/{username}", base), "avatar": lazy_src(avatar)}
    cover = side.select_one("img.img-border--full") if side is not None else None
    return {"name": heading, "description": clean(info), "owner": owner,
            "image": cover.get("src") if cover is not None else None,
            "items": list_items(doc, base), "total_pages": pages_total(doc)}


def list_items(doc, base):
    """The older "ul.item-list > li" rows (collections): thumbnail img with
    data-item-* attributes, author, rating stars, sales and price. Items can
    belong to any marketplace, so links keep their own host."""
    out, seen = [], set()
    for li in doc.select("ul.item-list > li"):
        img = li.select_one(".item-thumbnail img, .item-thumbnail .lazy-load-img")
        a = li.select_one(".item-thumbnail a[href*='/item/']") or li.select_one("a[href*='/item/']")
        href = a.get("href") if a is not None else None
        slug, item_id = item_link_id(href)
        item_id = to_int(li.get("data-item-id")) or item_id
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        get = (lambda k: (img.get(f"data-{k}") or img.get(f"data-data-{k}")) if img is not None else None)
        host_base = f"https://{urlparse(href).hostname}" if href and href.startswith("http") else base
        category = text(get("item-category"))
        author = li.select_one("a.author, a[href*='/user/']")
        username = username_from(author.get("href")) if author is not None else text(get("item-author"))
        rating_node = li.select_one(".rating-basic__stars")
        heading = li.select_one(".item-info h3 a")
        out.append({
            "id": item_id,
            "name": clean(heading) or text(get("item-name")),
            "link": absolute(f"/item/{slug}/{item_id}", host_base) if slug else None,
            "site": refs.MARKET_HOSTS.get(urlparse(host_base).hostname),
            "author": {"username": username, "name": clean(author) or username,
                       "link": absolute(f"/user/{username}", host_base)} if username else None,
            "category": {"name": category.split("/")[-1].strip(),
                         "breadcrumbs": [c.strip() for c in category.split("/")]} if category else None,
            "price": money(price(clean(li.select_one(".price"))) or price(get("item-cost"))),
            "rating": stars(rating_node),
            "sales_count": count(clean(li.select_one(".sale-count"))),
            "image": lazy_src(img),
            "large_image": text(get("preview-url")),
            "video_preview_link": text(get("video-file-url")),
        })
    return out
