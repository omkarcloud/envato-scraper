"""Configuration for the Envato Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT          port the API listens on (default 8000)
    ENVATO_PROXY  proxy URL for every request, e.g. http://user:pass@host:port
                  (default: none — direct). Envato Elements answers plain
                  HTTP from a clean IP. Envato Market (ThemeForest,
                  CodeCanyon, VideoHive, …) sits behind Cloudflare, so the
                  scraper opens it once in a real Chrome (patchright) and then
                  carries on over plain HTTP, or through the Chrome tab where
                  a plain-HTTP replay isn't accepted. A home IP clears in a
                  few seconds, so you very likely don't need a proxy either.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

ENVATO_PROXY = os.environ.get("ENVATO_PROXY") or None

# Envato Market: one shared Chrome, a tab per marketplace (envato/fetch.py).
ENVATO_MARKET_PROXY_COUNTRY = None     # the proxy comes from ENVATO_PROXY
ENVATO_MARKET_HARVEST_ATTEMPTS = 3     # tries to open a marketplace before giving up
ENVATO_MARKET_HARVEST_COOLDOWN = 300   # seconds to wait after a failed attempt
ENVATO_MARKET_HARVEST_TIMEOUT = 60     # seconds for Cloudflare to clear
ENVATO_MARKET_BROWSER_IDLE = 900       # close the Chrome after this many idle seconds

# Envato Elements: plain HTTP; on a Cloudflare challenge, retry through
# ENVATO_PROXY (when set) and finally through the Chrome tab.
ENVATO_ELEMENTS_PROXY_COUNTRY = "proxy" if ENVATO_PROXY else None
ENVATO_ELEMENTS_ROTATE_ATTEMPTS = 1
ENVATO_ELEMENTS_BROWSER_FALLBACK = True


def envato_proxy(country=None):
    """The proxy every request goes through (None = direct)."""
    return os.environ.get("ENVATO_PROXY") or None
