"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json. The endpoint functions live in envato/market.py (Envato
Market: ThemeForest, CodeCanyon, VideoHive, AudioJungle, GraphicRiver,
PhotoDune, 3DOcean) and envato/elements.py (Envato Elements).
"""
import json
import os

from envato import elements, market, refs

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # an item id or any item link from the 7 Market sites
    save("market_item_2833226.json", market.item_details(refs.resolve_market_item("2833226")))

    # every sidebar filter of the site, 30 items per page
    save("market_search_admin_dashboard.json", market.search(query="admin dashboard", sort="best-sellers"))

    # an Envato Elements item id, slug or link
    save("elements_item_PQH6NYN.json", elements.item_details(refs.resolve_elements_item("PQH6NYN")))
