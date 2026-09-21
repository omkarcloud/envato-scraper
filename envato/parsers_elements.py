"""Envato Elements normalizers: the /data-api/page JSON -> API responses.

The page data is the React app's own view model, so it carries presentation
fields next to the data. Kept: identity, author, type / categories / tags,
dates, every item attribute (snake_cased), cover + preview images, the video
preview (watermarked and the public unwatermarked 540p renders), audio
previews (main track + variants + stems with durations), font styles,
series / pack / related / more-from-author cards, breadcrumbs, the
subscription price shown on the page. Dropped as noise: displayType,
blurredBackgroundSrc, isIndexable, preventIndexing, nofollowTags,
itemTypeNameEn / itemTypeSlug / categoryNames (duplicates), openGraphImageUrl
(empty or equal to coverImageUrls.og1200x630), seoContent / seoItemDetail /
pageMeta (SEO copy), analytics / marketingComponentData / layoutProps /
flash-sale banners (tracking and promos), previewFrameImages /
indexingFrameImages (bare S3 keys with no public host), user / workspace
state (always anonymous here).
"""
import re
from datetime import datetime

from envato.util import iso_datetime, text, to_float, to_int

from envato import refs

SITE = "https://elements.envato.com"

_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def snake_key(key):
    """'videoLengthTotalSeconds' -> 'video_length_total_seconds'."""
    return _CAMEL_RE.sub("_", str(key)).replace("-", "_").lower()


def snake_keys(value):
    if isinstance(value, dict):
        return {snake_key(k): snake_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [snake_keys(v) for v in value]
    return value


def link(path):
    if not path:
        return None
    if path.startswith("http"):
        return path
    return SITE + path if path.startswith("/") else f"{SITE}/{path}"


def largest(srcset):
    """'u1 316w, u2 710w' -> u2 (the widest rendition)."""
    best, best_w = None, -1
    for part in (srcset or "").split(","):
        bits = part.strip().rsplit(" ", 1)
        if len(bits) != 2 or not bits[1].endswith("w"):
            continue
        width = to_int(bits[1][:-1]) or 0
        if width > best_w:
            best, best_w = bits[0], width
    return best


def elements_datetime(value):
    """'August 25, 2026 13:50' / ISO -> ISO datetime string."""
    if not value or not isinstance(value, str):
        return None
    iso = iso_datetime(value)
    if iso:
        return iso
    for fmt in ("%B %d, %Y %H:%M", "%B %d, %Y"):
        try:
            return datetime.strptime(value.strip(), fmt).strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
    return None


def _username(author_url, fallback=None):
    m = re.search(r"/user/([^/?#]+)", author_url or "")
    return m.group(1) if m else fallback


def author(item):
    name = text(item.get("author"))
    username = _username(item.get("authorUrl"), name)
    if not name and not username:
        return None
    return {"id": text(item.get("authorId")), "username": username, "name": name,
            "link": link(f"/user/{username}") if username else None}


def _audio_track(track):
    if not isinstance(track, dict):
        return None
    sources = track.get("audioSourceUrl") if isinstance(track.get("audioSourceUrl"), dict) else {}
    return {
        "id": text(track.get("id")),
        "name": text(track.get("title")),
        "duration_seconds": to_float(track.get("duration")),
        "mp3_link": sources.get("mp3") or (track.get("audioSourceUrl") if isinstance(track.get("audioSourceUrl"), str) else None),
        "m4a_link": sources.get("m4a"),
        "waveform_link": text(track.get("waveformUrl")),
    }


def audio(item):
    """Audio previews for music and sound effects (None for other types)."""
    variants = item.get("musicVariants") if isinstance(item.get("musicVariants"), dict) else {}
    sfx = item.get("sfxAudioSourceUrl") if isinstance(item.get("sfxAudioSourceUrl"), dict) else {}
    preview = item.get("audioSourceUrl") or sfx.get("mp3")
    if not preview and not variants:
        return None
    durations = [d for d in (item.get("trackDurations") or []) if isinstance(d, (int, float)) and d]
    main = _audio_track(variants.get("mainTrack"))
    return {
        "preview_link": preview,
        "waveform_link": text(item.get("waveformUrl") or item.get("sfxWaveformUrl")),
        "duration_seconds": (main or {}).get("duration_seconds") or (durations[0] if durations else None),
        "track_durations_seconds": durations,
        "clip_durations_seconds": [d for d in (item.get("audioClipDurations") or []) if isinstance(d, (int, float))],
        "bpm": to_int(item.get("bpm")),
        "main_track": main,
        "variant_tracks": [t for t in (_audio_track(v) for v in (variants.get("variantTracks") or [])) if t],
        "stems": [t for t in (_audio_track(v) for v in (variants.get("variantStems") or [])) if t],
    }


def video(item):
    data = item.get("video") if isinstance(item.get("video"), dict) else None
    if not data:
        return None
    hd = data.get("unwatermarkedVideos") if isinstance(data.get("unwatermarkedVideos"), dict) else {}
    return {
        "preview_link": text(data.get("standard")),
        "preview_540p_link": text(hd.get("highBitrate")),
        "preview_540p_low_bitrate_link": text(hd.get("lowBitrate")),
        "preview_alpha_link": text(hd.get("lowBitrateAlpha")),
        "tutorial_link": text(data.get("tutorialVideo")) if isinstance(data.get("tutorialVideo"), str) else None,
        "author_short_preview_link": text(data.get("authorShortenedPreviewVideo"))
        if isinstance(data.get("authorShortenedPreviewVideo"), str) else None,
    }


def item_card(item):
    """A grid card (search, browse, related, author, free files)."""
    if not isinstance(item, dict) or not item.get("id"):
        return None
    item_type = text(item.get("itemType"))
    return {
        "id": item.get("id"),
        "uuid": text(item.get("itemUuid")),
        "name": text(item.get("title")),
        "link": link(item.get("itemUrl")),
        "type": item_type,
        "type_name": text(item.get("itemTypeName")),
        "author": author(item),
        "categories": [c for c in (item.get("categories") or []) if c],
        "image": text(item.get("fallbackSrc")) or largest(item.get("imageSrcSet")),
        "large_image": largest(item.get("imageSrcSet")),
        "aspect_ratio": to_float(item.get("aspectRatio")),
        "video_preview_link": (item.get("video") or {}).get("standard") if isinstance(item.get("video"), dict) else None,
        "audio_preview": audio(item),
        "is_new": bool(item.get("isNew")),
        "is_part_of_pack": bool(item.get("partOfPack")),
        "is_claim_clear_compatible": item.get("claimClearCompatible"),
        "similar_items_link": link(item.get("similarItemsUrl")),
    }


def item_cards(items):
    return [c for c in (item_card(i) for i in (items or [])) if c]


def _attributes(item, attribute_list):
    """itemAttributes (raw values, snake_cased) + any itemAttributeList entry
    missing from it (label values only)."""
    out = snake_keys(item.get("itemAttributes") or {})
    for entry in attribute_list or []:
        key = snake_key(entry.get("key") or "")
        if not key or key in out:
            continue
        values = [o.get("label") for o in entry.get("options") or [] if o.get("label")]
        out[key] = values if len(values) != 1 else values[0]
    return out


def _crumbs(crumbs):
    return [{"name": c.get("label"), "link": link(c.get("url"))}
            for c in crumbs or [] if isinstance(c, dict) and c.get("url") not in ("/", None)]


def _tags(tags, item):
    labels = [t.get("label") for t in tags or [] if isinstance(t, dict) and t.get("label")]
    return labels or [t for t in (item.get("tags") or []) if isinstance(t, str)]


def item_page(data):
    item = data.get("item") or {}
    item_type = text(item.get("itemType"))
    cover = item.get("coverImageUrls") if isinstance(item.get("coverImageUrls"), dict) else {}
    previews = [largest(s) for s in item.get("previewImageSrcSets") or [] if largest(s)]
    if not previews:
        previews = [p for p in item.get("previewImageFallbackSrcs") or [] if p]
    font = item.get("fontPreview") if isinstance(item.get("fontPreview"), dict) else None
    pack = data.get("pack") if isinstance(data.get("pack"), dict) else None
    monthly = data.get("standardAnnualMonthlyEquivalentPrice")
    return {
        "id": item.get("id"),
        "uuid": text(item.get("itemUuid")),
        "name": text(item.get("title")),
        "slug": text(item.get("slug")),
        "link": link(item.get("itemUrl")),
        "type": item_type,
        "type_name": text(item.get("itemTypeName")),
        "description": text(item.get("description")),
        "description_html": text(data.get("descriptionHtml")),
        "author": author(item),
        "categories": [c for c in item.get("categories") or [] if c],
        "subcategories": [c for c in item.get("subcategories") or [] if c],
        "tags": _tags(data.get("tags"), item),
        "breadcrumbs": _crumbs(data.get("crumbs")),
        "attributes": _attributes(item, data.get("itemAttributeList")),
        "file_size_bytes": to_int(item.get("fileSizeBytes")),
        "bit_rate": text(item.get("bitRate")),
        "resolution": snake_keys(item.get("resolution")) if isinstance(item.get("resolution"), dict) else None,
        "download_formats": item.get("downloadFormats") or [],
        "media": {
            "image": cover.get("w1370") or cover.get("og1200x800") or text(item.get("fallbackSrc")) or (previews[0] if previews else None),
            "cover_images": snake_keys(cover) if cover else {},
            "preview_images": previews,
            "video": video(item),
            "audio": audio(item),
            "font": {
                "styles_count": to_int(font.get("totalStyleCount")),
                "variable_styles_count": to_int(font.get("variableStyleCount")),
                "default_style": text(font.get("defaultStyleName")),
                "axes": font.get("axisNames") or [],
                "styles": [v.get("styleName") for v in font.get("variants") or [] if v.get("styleName")],
            } if font else None,
        },
        "is_free": bool(item.get("isCurrentlyFree")),
        "is_new": bool(item.get("isNew")),
        "is_content_id_registered": item.get("contentIdRegistered"),
        "is_claim_clear_compatible": item.get("claimClearCompatible"),
        "pack": {"id": pack.get("id"), "name": text(pack.get("title") or pack.get("name")),
                 "link": link(pack.get("url") or pack.get("itemUrl"))} if pack else None,
        "series_items": item_cards(data.get("moreItemsFromThisSeries")),
        "series_items_count": to_int(data.get("totalItemsFromThisSeries")),
        "more_from_author": item_cards(data.get("moreFromAuthor")),
        "related_items": item_cards(data.get("relatedItems")),
        "related_items_count": to_int(data.get("totalRelatedItems")),
        "related_items_link": link(data.get("seeRelatedItemsUrl")),
        "subscription_price": {"amount": to_float(monthly), "currency": text(data.get("currency")) or "USD",
                               "period": "month", "billed": "annually"} if monthly else None,
        "published_at": elements_datetime(item.get("publishedAt")),
        "updated_at": elements_datetime(item.get("updatedAt")),
    }


# ---- search / browse ------------------------------------------------------------------------

# refinement block id -> our filter param (see refs.ELEMENTS_FILTERS for the
# path-segment prefix each param maps to)
_BLOCK_PARAMS = {
    "numberOfPeople": "number_of_people", "colors": "color", "orientation": "orientation",
    "resolution": "resolution", "frameRate": "frame_rate", "properties": "properties",
    "mood": "mood", "genre": "genre", "theme": "theme", "tempo": "tempo",
    "instrument": "instrument", "vocalsInAudio": "vocals", "decade": "decade",
    "spacing": "spacing", "optimumSize": "optimum_size", "colorSpace": "color_space",
}


def _segment_tokens(path, prefix):
    for seg in (path or "").split("/"):
        if seg.startswith(prefix + "-"):
            return set(seg[len(prefix) + 1:].split("+"))
    return set()


def _block_param(block_id):
    if block_id in _BLOCK_PARAMS:
        return _BLOCK_PARAMS[block_id]
    if (block_id or "").endswith("ApplicationsSupported"):
        return "compatible_with"
    return None


def filters(refinements, current_path=""):
    """Elements `refinements` -> [{name, param, type, options: [{label, value,
    is_selected}]}]; `param` / `value` are what /envato/elements/search
    takes. Each option link is diffed against the current page path, so an
    already-applied filter (present in every option's link) is ignored."""
    out = []
    for block in (refinements or {}).get("data") or []:
        block_id = block.get("id")
        name = block.get("title") or block.get("label")
        if block.get("type") == "range":
            out.append({"name": name, "param": "min_length/max_length", "type": "range",
                        "steps_seconds": block.get("steps") or [], "options": []})
            continue
        options = block.get("checkboxItems") or block.get("data") or []
        param = _block_param(block_id)
        prefix = refs.ELEMENTS_FILTERS.get(param) if param else None
        if block_id == "categories":
            param = "category"
        elif block_id == "claimClear":
            param = "claim_clear"
        elif block_id == "portfolio":
            param, prefix = "portfolio", "portfolio"
        current = _segment_tokens(current_path, prefix) if prefix else set()
        parsed = []
        for opt in options:
            url = opt.get("url") or ""
            selected = bool(opt.get("selected"))
            value = None
            if block_id == "categories":
                segs = [x for x in url.split("/") if x]
                value = segs[1] if len(segs) > 1 else None
            elif block_id == "claimClear":
                value = "true"
            elif prefix:
                added = _segment_tokens(url, prefix) - current
                removed = current - _segment_tokens(url, prefix)
                if added:
                    value = sorted(added)[0]
                elif removed:
                    value, selected = sorted(removed)[0], True
            parsed.append({"label": opt.get("label"), "value": value, "is_selected": selected})
        if parsed and param:
            out.append({"name": name, "param": param, "type": block.get("type"), "options": parsed})
    return out


def pagination_block(data, page):
    pag = data.get("pagination") or {}
    analytics = data.get("analytics") or {}
    per_page = to_int(pag.get("perPage") or analytics.get("perPage"))
    total_pages = to_int(pag.get("totalPages")) or (1 if data.get("items") else 0)
    return {"page": to_int(pag.get("currentPage")) or page, "items_per_page": per_page,
            "total_pages": total_pages,
            "total_count": to_int(analytics.get("totalItems") or analytics.get("numberOfResults"))}


def search_page(data, page, current_path=""):
    sort = data.get("sortBy") if isinstance(data.get("sortBy"), dict) else {}
    related = []
    for group in data.get("relatedSearchTermTagsByType") or []:
        for term in group.get("relatedSearchTerms") or []:
            if term.get("label") and term["label"] not in related:
                related.append(term["label"])
    return {
        "items": item_cards(data.get("items")),
        "sort": sort.get("sortValue"),
        "sort_options": [o.get("id") for o in sort.get("sortOptions") or [] if o.get("id")],
        "filters": filters(data.get("refinements"), current_path),
        "related_searches": [t.get("label") for t in data.get("searchTermTags") or [] if t.get("label")],
        "related_searches_other_types": related,
        "pagination": pagination_block(data, page),
    }


def search_all(data):
    groups = []
    for g in data.get("itemGroups") or []:
        seg = (g.get("url") or "").strip("/").split("/")[0]
        groups.append({
            "type": refs.ELEMENTS_SEGMENT_TYPES.get(seg, g.get("id")),
            "type_name": g.get("name"),
            "items_count": to_int(g.get("itemsCount")),
            "link": link(g.get("url")),
            "items": item_cards(g.get("items")),
        })
    related = []
    for group in data.get("relatedSearchTermTagsByType") or []:
        terms = [t.get("label") for t in group.get("relatedSearchTerms") or [] if t.get("label")]
        if terms:
            related.append({"type": (group.get("itemType") or {}).get("id"), "searches": terms})
    return {"query": data.get("searchTerms"), "total_count": to_int(data.get("totalItemsCount")),
            "groups": groups, "related_searches": related}


def author_page(data, page):
    tabs = [{"type": t.get("id"), "type_name": t.get("name"), "link": link(t.get("url"))}
            for t in data.get("itemTypeTabs") or []]
    active = data.get("activeItemType") or {}
    pag = data.get("pagination") or {}
    analytics = data.get("analytics") or {}
    return {
        "author": {"username": data.get("contributorUsername"), "name": data.get("contributorUsername"),
                   "link": link(f"/user/{data.get('contributorUsername')}")},
        "type": active.get("id"),
        "item_types": tabs,
        "items": item_cards(data.get("items")),
        "pagination": {"page": to_int(pag.get("currentPage")) or page,
                       "items_per_page": to_int(analytics.get("perPage")),
                       "total_pages": to_int(pag.get("totalPages")) or 1,
                       "total_count": None},
    }


def free_files(data):
    return {"items": item_cards(data.get("items")), "subscription_price": {
        "amount": to_float(data.get("standardAnnualMonthlyEquivalentPrice")), "currency": text(data.get("currency")) or "USD",
        "period": "month", "billed": "annually"} if data.get("standardAnnualMonthlyEquivalentPrice") else None}


def popular_searches(data):
    if data.get("searchesData") is not None:
        return {"groups": [{
            "type": g.get("slug"), "type_name": g.get("itemType"), "link": link(g.get("url")),
            "searches": [{"query": s.get("usefulSearchTerm"), "link": link(s.get("url"))}
                         for s in g.get("usefulSearches") or [] if s.get("usefulSearchTerm")],
        } for g in data.get("searchesData") or []]}
    rows = data.get("searches") or []
    if rows and isinstance(rows[0], dict) and "searchTerm" in rows[0]:
        # one letter's page: a flat list of searches
        letter = data.get("letter")
        return {"type_name": data.get("itemTypeName"), "groups": [{
            "letter": letter.upper() if isinstance(letter, str) else None,
            "link": link(f"/popular-searches/{data.get('itemTypeSlug')}/{letter}") if letter else None,
            "searches": [{"query": s.get("searchTerm"), "link": link(s.get("url"))}
                         for s in rows if s.get("searchTerm")],
        }]}
    return {"type_name": data.get("itemTypeName"), "groups": [{
        "letter": g.get("letter"), "link": link(g.get("url")),
        "searches": [{"query": s.get("searchTerm"), "link": link(s.get("url"))}
                     for s in g.get("searches") or [] if s.get("searchTerm")],
    } for g in data.get("searches") or []]}
