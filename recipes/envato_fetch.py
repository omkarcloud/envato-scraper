"""Envato Market browser mode (envato/fetch.py): a host whose exit was not
challenged has no cf_clearance to replay, so its pages are in-page fetches
from a kept browser sitting on that host. In-page fetch is same-origin
only, so there is one browser per (host, proxy session): the lease key
is "<host>@p<port>" and each browser parks on ITS host's robots.txt. GKE
passes variant = the host name; the referrer is that host's home page."""
from urllib.parse import urlsplit

from recipes._cloudflare import CloudflareInPage
from recipes.envato import DEFAULT_HOST, VARIANTS


def _origin(url):
    p = urlsplit(url or "")
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else None


class EnvatoFetch(CloudflareInPage):
    name = "envato-fetch"
    variants = VARIANTS
    max_browsers = 16                 # the share: eight hosts (seven marketplaces + elements) x
                                      # config.INPAGE_BROWSER_SLOTS (2) browsers each; the pod offers
                                      # share x BROWSER_BURST_FACTOR sessions per host (envato/fetch.py)
    park_url = "per-host"             # truthy so the worker parks; park_page picks the host's robots.txt

    def referrer_for(self, url):
        return (_origin(url) or self.variants[""].rstrip("/")) + "/"

    def park_page(self, driver, url):
        current = _origin(driver.call(lambda page: page.url))
        if current:
            super().park_page(driver, current + "/robots.txt")

    def fetch(self, proxy, variant="", session=None, url=None, urls=None,
              method="GET", headers=None, body=None):
        session = session or f"{variant or DEFAULT_HOST}@{self.key_for(proxy, None)}"
        return super().fetch(proxy, variant, session, url, urls, method, headers, body)


RECIPE = EnvatoFetch
