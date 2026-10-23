# 🎨 Envato Scraper

Envato Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Envato data for free.

## ✨ What Can I Get?

- 🛒 **Full details on 29M+ Envato Market items** — every license price, sales, rating, tags, attributes & previews across ThemeForest, CodeCanyon, VideoHive, AudioJungle, GraphicRiver, PhotoDune and 3DOcean
- ✍️ **Every review & comment** — 26K+ reviews on Avada alone: stars, reason, full text and the author's reply
- 👤 **Any author's business** — total sales, rating, level, badges, full portfolio, followers & top-author rankings
- 🎞️ **Millions of Envato Elements assets** — photos, stock video, music, fonts & templates with previews, attributes and every filter

## 🎥 Example: A Full ThemeForest Item

```json
{
  "id": 2833226,
  "name": "Avada | Website Builder For WordPress & eCommerce",
  "link": "https://themeforest.net/item/avada-responsive-multipurpose-theme/2833226",
  "site": "themeforest",
  "category": { "name": "Business", "breadcrumbs": [{ "name": "WordPress", "link": "https://themeforest.net/category/wordpress" }] },
  "tags": ["blog", "business", "corporate", "ecommerce", "portfolio", "woocommerce"],
  "highlights": ["Recently Updated", "Well Documented"],
  "price": { "amount": 69.0, "currency": "USD" },
  "licenses": [
    { "type": "regular", "name": "Regular License", "price": 69.0, "support_extension_price": 35.63, "currency": "USD" },
    { "type": "extended", "name": "Extended License", "price": 2950.0, "support_extension_price": 1468.75, "currency": "USD" }
  ],
  "rating": 4.78,
  "reviews_count": 26594,
  "comments_count": 39400,
  "sales_count": 1071700,
  "attributes": {
    "compatible_with": ["Gravity Forms", "WooCommerce 9.x.x", "WPML"],
    "software_version": ["WordPress 7.0.x", "WordPress 6.9.x"],
    "layout": "Responsive"
  },
  "media": { "live_preview_link": "https://preview.themeforest.net/item/avada-responsive-multipurpose-theme/full_screen_preview/2833226" },
  "author": {
    "username": "themefusion",
    "name": "ThemeFusion",
    "badges": [{ "name": "Milestone Member", "description": "Part of the $1 billion community earnings milestone" }]
  },
  "last_updated": "2026-08-25"
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Envato Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/envato-scraper
cd envato-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/market/items/details?item=2833226"
```

```json
{
  "id": 2833226,
  "name": "Avada | Website Builder For WordPress & eCommerce",
  "link": "https://themeforest.net/item/avada-responsive-multipurpose-theme/2833226",
  "site": "themeforest",
  "tags": ["blog", "business", "clean", "corporate", "creative", "ecommerce"],
  "price": { "amount": 69.0, "currency": "USD" },
  "rating": 4.78,
  "reviews_count": 26594,
  "comments_count": 39400,
  "sales_count": 1071703,
  "author": {
    "username": "themefusion",
    "name": "ThemeFusion",
    "link": "https://themeforest.net/user/themefusion"
  },
  "last_updated": "2026-08-25"
}
```

All 24 endpoints are now live at `http://localhost:8000`.

Envato Market sits behind Cloudflare, so the first Market call opens it once in Chrome (a few seconds). Every call after that is fast. Have [Google Chrome](https://www.google.com/chrome/) installed, or use the included `Dockerfile`.

## 📚 Endpoints

24 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Market Item Details | `/market/items/details` | Every license price, sales, rating, attributes and previews in one call |
| Market Search Suggestions | `/market/suggestions` | Popular search completions with search volume |
| Market Search | `/market/search` | 30 items per page with every filter, plus filter counts |
| Market Best Sellers | `/market/popular` | This week's best sellers, site-wide or per category |
| Market Categories | `/market/categories` | Full category tree with item counts |
| Market Item Reviews / Comments | `/market/items/reviews`, `/market/items/comments` | Buyer reviews with author replies, comment threads |
| Market Item Support | `/market/items/support` | Support policy, support link and FAQ |
| Market Author Details / Items | `/market/authors/details`, `/market/authors/items` | Sales, rating, badges and the full portfolio |
| Market Author Followers / Following | `/market/authors/followers`, `/market/authors/following` | Their network with sales and ratings |
| Market Top Authors / Top New Authors | `/market/authors/top`, `/market/authors/new` | All-time and this month's top sellers |
| Market Collections / Collection Details | `/market/collections`, `/market/collections/details` | Community collections and every item in them |
| Elements Item Details | `/elements/items/details` | Attributes, tags, audio, video and font previews |
| Elements Search All Types / Search | `/elements/search-all`, `/elements/search` | Every content type at once, or one type with every filter |
| Elements Similar Items | `/elements/items/similar` | Lookalikes of any Elements item |
| Elements Categories / Popular Searches | `/elements/categories`, `/elements/popular-searches` | Types, categories, filter values and trending searches |
| Elements Author Items / Free Files | `/elements/authors/items`, `/elements/free-files` | An author's items and this week's free files |


## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-envato-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-envato-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-envato-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/market/items/details",
    params={"item": "2833226"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Envato Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20Envato%20Scraper%20API.)

[![Ask Us by Email about Envato Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Envato%20Scraper%20API&body=I%20need%20help%20using%20the%20Envato%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/envato-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/envato-scraper)
