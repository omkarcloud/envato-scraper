"""Envato Market per-host identity mint (envato/fetch.py): every path on
the seven marketplace hosts answers a Cloudflare managed challenge to plain
curl, and cf_clearance is PER HOST (a themeforest cookie is 403 on
codecanyon), so GKE mints one identity per host: variant = the host name
("" = themeforest.net). The mint loads https://<host>/ through the sticky
US residential exit GKE sends (the one its curl session replays on) and
returns the cookies + UA once the real page shows. An exit Cloudflare does
not challenge issues no cf_clearance and curl stays 403 there: GKE's curl
replay detects that and serves the host through recipes/envato_fetch.py.
elements.envato.com is a variant too: the Elements ladder's last resort
("browser fallback") ran on the same Market browser before 2026-10-22."""
from recipes._cloudflare import CloudflareMint

MARKET_HOSTS = ("themeforest.net", "codecanyon.net", "videohive.net", "audiojungle.net",
                "graphicriver.net", "photodune.net", "3docean.net")
ELEMENTS_HOST = "elements.envato.com"
DEFAULT_HOST = MARKET_HOSTS[0]
VARIANTS = {"": f"https://{DEFAULT_HOST}/",
            **{h: f"https://{h}/" for h in MARKET_HOSTS + (ELEMENTS_HOST,)}}


class Envato(CloudflareMint):
    name = "envato"
    variants = VARIANTS
    timeout = 60                      # ENVATO_MARKET_HARVEST_TIMEOUT before 2026-10-22
    ttl_seconds = 24 * 3600           # advisory: GKE keeps a host's identity until a replay is challenged


RECIPE = Envato
