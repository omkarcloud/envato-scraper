"""Marshmallow request schemas for every /envato/* route.

Generic fields come from the shared top-level schema_fields.py; this module
adds the Envato resolvers and the per-route schemas. Every schema's load()
output is the kwargs dict its endpoint function takes.

ONE param per input (tripadvisor QueryOrLinkField convention, never a
sibling `url` / `id` pair) — refs.py lists every accepted form:
  item        Market: 2833226 | any …/item/<slug>/<id> link on the seven sites
              Elements: PQH6NYN | 3d-logo-mockup-PQH6NYN | elements.envato.com link
  author      username | profile link
  category    wordpress/ecommerce | /category/… link           (Market)
  collection  2253321 | 2253321-halloween-collection | link   (Market)

A Market link also fixes the marketplace; `site` (default themeforest) only
applies to bare ids and to site-wide listings.

Pagination follows what each storefront allows: Market search / category
grids stop at page 60, Elements at page 24; review, comment, follower and
portfolio pages go as deep as the item or author has content.
"""
from marshmallow import ValidationError, fields, missing, validate, validates_schema

from schema_fields import (BaseSchema, ChoiceField, CommaListField, Flag, PageField, QueryField,
                           RefField, StrippedString, TrueOnlyFlag)
from envato import refs

# Choice tables as literals; the publishing tooling reads enums from this file's AST.
SITES = ["themeforest", "codecanyon", "videohive", "audiojungle", "graphicriver", "photodune", "3docean"]
MARKET_SORTS = ["relevance", "best-sellers", "rating", "newest", "trending", "price-low", "price-high"]
DATE_RANGES = ["day", "week", "month", "year"]
SALES_BANDS = ["none", "low", "medium", "high", "top-sellers"]
REVIEW_SORTS = ["newest", "highest", "lowest"]
PORTFOLIO_SORTS = ["newest", "oldest", "best-match", "updated", "name", "category", "rating", "best-sellers"]
COLLECTION_SORTS = ["newest", "name", "rating"]
COLLECTION_ITEM_SORTS = ["added", "released", "name", "author", "category", "rating", "best-sellers", "price"]
RESOLUTIONS = ["720p", "1080p", "2K", "4K"]
TEMPOS = ["very-slow", "slow", "medium", "upbeat", "fast", "very-fast"]
PHOTO_SIZES = ["xxl", "xl", "l", "m"]
FRAME_RATES = ["23.98", "24", "25", "29.97", "30", "50", "59.94", "60"]
PHOTO_COLORS = ["grey", "black", "brown", "blue", "white", "orange", "green", "pink", "red", "purple", "yellow", "teal"]
FILE_FORMATS = ["obj", "fbx", "max", "c4d", "3ds", "mb", "lwo", "xsi", "blend", "e3d", "dxf", "dwg", "ma",
                "unitypackage", "3b", "lws", "lw", "ztl", "lxo", "hrc"]
LETTERS = list("abcdefghijklmnopqrstuvwxyz0123456789")
ORIENTATIONS = ["landscape", "portrait", "square"]
ELEMENTS_TYPES = ["stock-video", "video-templates", "music", "sound-effects", "graphic-templates", "graphics",
                  "3d", "presentation-templates", "photos", "fonts", "add-ons", "web-templates",
                  "cms-templates", "wordpress"]
ELEMENTS_SORTS = ["relevant", "popular", "latest"]
MARKET_MAX_PAGE = 60
ELEMENTS_MAX_PAGE = 24


# ---- id-or-link fields ---------------------------------------------------------------

class MarketItemField(RefField):
    resolver = staticmethod(refs.resolve_market_item)


class MarketAuthorField(RefField):
    resolver = staticmethod(refs.resolve_market_author)


class MarketCategoryField(RefField):
    resolver = staticmethod(refs.resolve_market_category)

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)


class MarketCollectionField(RefField):
    resolver = staticmethod(refs.resolve_market_collection)


class ElementsItemField(RefField):
    resolver = staticmethod(refs.resolve_elements_item)


class ElementsAuthorField(RefField):
    resolver = staticmethod(refs.resolve_elements_author)


class SlugListField(CommaListField):
    """'Landscape, portrait' -> ['landscape', 'portrait'] (Elements filter slugs)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("upper", False)
        kwargs.setdefault("max_items", 8)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        items = super()._deserialize(value, attr, data, **kwargs)
        if items is None:
            return None
        out = []
        for item in items:
            slug = "-".join(item.strip().lower().split())
            if not slug or "/" in slug:
                raise ValidationError(f"'{item}' is not a valid filter value.")
            if slug not in out:
                out.append(slug)
        return out


class RequiredChoiceField(ChoiceField):
    """ChoiceField that must be present (the shared field always defaults to None)."""

    def __init__(self, choices, **kwargs):
        kwargs.setdefault("required", True)
        super().__init__(choices, load_default=missing, **kwargs)


def _site_field():
    return ChoiceField(SITES, load_default=None)


def _seconds():
    return fields.Integer(strict=False, load_default=None, validate=validate.Range(min=0, max=36000))


def _text(max_length=100):
    return StrippedString(load_default=None, validate=validate.Length(max=max_length))


# ---- Envato Market -----------------------------------------------------------------------

class MarketSearchSchema(BaseSchema):
    query = QueryField(required=False, load_default=None, max_length=100)
    site = _site_field()
    category = MarketCategoryField()
    sort = ChoiceField(MARKET_SORTS)
    date_added = ChoiceField(DATE_RANGES)
    date_updated = ChoiceField(DATE_RANGES)
    price_min = fields.Integer(strict=False, load_default=None, validate=validate.Range(min=0, max=100000))
    price_max = fields.Integer(strict=False, load_default=None, validate=validate.Range(min=0, max=100000))
    rating_min = fields.Integer(strict=False, load_default=None, validate=validate.Range(min=1, max=4))
    sales = ChoiceField(SALES_BANDS)
    on_sale = TrueOnlyFlag()
    compatible_with = _text()
    software_version = _text()
    resolution_min = ChoiceField(RESOLUTIONS)
    frame_rate = ChoiceField(FRAME_RATES)
    requires_plugins = Flag()
    has_alpha_channel = TrueOnlyFlag()
    is_looped = TrueOnlyFlag()
    min_length = _seconds()
    max_length = _seconds()
    tempo = ChoiceField(TEMPOS)
    vocals = ChoiceField(refs.MARKET_VOCALS)
    include_pro_music = Flag()
    orientation = ChoiceField(ORIENTATIONS)
    size = ChoiceField(PHOTO_SIZES)
    color = ChoiceField(PHOTO_COLORS)
    file_format = ChoiceField(FILE_FORMATS)
    min_poly_count = fields.Integer(strict=False, load_default=None, validate=validate.Range(min=0))
    max_poly_count = fields.Integer(strict=False, load_default=None, validate=validate.Range(min=1))
    page = PageField(max_page=MARKET_MAX_PAGE)

    @validates_schema
    def _ranges(self, data, **kwargs):
        for low, high in (("price_min", "price_max"), ("min_length", "max_length"),
                          ("min_poly_count", "max_poly_count")):
            if data.get(low) is not None and data.get(high) is not None and data[low] > data[high]:
                raise ValidationError(f"{low} must not exceed {high}.", low)


class MarketSuggestSchema(BaseSchema):
    query = QueryField(max_length=60)
    site = _site_field()
    category = MarketCategoryField()


class MarketSiteSchema(BaseSchema):
    site = _site_field()


class MarketPopularSchema(BaseSchema):
    site = _site_field()
    category = MarketCategoryField()


class MarketItemSchema(BaseSchema):
    item = MarketItemField()
    site = _site_field()


class MarketReviewsSchema(MarketItemSchema):
    sort = ChoiceField(REVIEW_SORTS)
    page = PageField(max_page=5000)


class MarketCommentsSchema(MarketItemSchema):
    page = PageField(max_page=5000)


class MarketAuthorSchema(BaseSchema):
    author = MarketAuthorField()
    site = _site_field()


class MarketAuthorItemsSchema(MarketAuthorSchema):
    sort = ChoiceField(PORTFOLIO_SORTS)
    page = PageField(max_page=500)


class MarketAuthorPeopleSchema(MarketAuthorSchema):
    page = PageField(max_page=1000)


class MarketTopAuthorsSchema(BaseSchema):
    site = _site_field()
    level = fields.Integer(strict=False, load_default=None, validate=validate.Range(min=1, max=16))
    page = PageField(max_page=500)


class MarketCollectionsSchema(BaseSchema):
    site = _site_field()
    sort = ChoiceField(COLLECTION_SORTS)
    page = PageField(max_page=1000)


class MarketCollectionSchema(BaseSchema):
    collection = MarketCollectionField()
    site = _site_field()
    sort = ChoiceField(COLLECTION_ITEM_SORTS)
    page = PageField(max_page=500)


# ---- Envato Elements ---------------------------------------------------------------------

class ElementsSearchSchema(BaseSchema):
    type = RequiredChoiceField(ELEMENTS_TYPES)
    query = QueryField(required=False, load_default=None, max_length=60)
    category = StrippedString(load_default=None, validate=validate.Regexp(
        r"^[a-z0-9][a-z0-9-]{0,80}$", error="Must be a category slug from /envato/elements/categories (e.g. stock-footage)."))
    sort = ChoiceField(ELEMENTS_SORTS)
    orientation = SlugListField()
    resolution = SlugListField()
    frame_rate = SlugListField()
    properties = SlugListField()
    color = SlugListField()
    number_of_people = SlugListField()
    compatible_with = SlugListField()
    color_space = SlugListField()
    mood = SlugListField()
    genre = SlugListField()
    theme = SlugListField()
    tempo = SlugListField()
    instrument = SlugListField()
    vocals = SlugListField()
    decade = SlugListField()
    spacing = SlugListField()
    optimum_size = SlugListField()
    claim_clear = TrueOnlyFlag()
    portfolio = StrippedString(load_default=None, validate=validate.Regexp(r"^[a-z0-9-]{1,40}$"))
    page = PageField(max_page=ELEMENTS_MAX_PAGE)


class ElementsQuerySchema(BaseSchema):
    query = QueryField(max_length=60)


class ElementsItemSchema(BaseSchema):
    item = ElementsItemField()


class ElementsSimilarSchema(ElementsItemSchema):
    page = PageField(max_page=ELEMENTS_MAX_PAGE)


class ElementsAuthorSchema(BaseSchema):
    author = ElementsAuthorField()
    type = ChoiceField(ELEMENTS_TYPES)
    page = PageField(max_page=ELEMENTS_MAX_PAGE)


class ElementsPopularSearchesSchema(BaseSchema):
    type = ChoiceField(ELEMENTS_TYPES)
    letter = ChoiceField(LETTERS)

    @validates_schema
    def _letter_needs_type(self, data, **kwargs):
        if data.get("letter") and not data.get("type"):
            raise ValidationError("letter needs a type.", "letter")


class ElementsCategoriesSchema(BaseSchema):
    type = ChoiceField(ELEMENTS_TYPES)


class EmptySchema(BaseSchema):
    pass
