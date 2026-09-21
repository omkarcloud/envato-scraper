"""Envato transport: two storefronts, two ladders (validated 2026-09-21).

ENVATO MARKET — themeforest.net, codecanyon.net, videohive.net,
audiojungle.net, graphicriver.net, photodune.net, 3docean.net
  Rails/Turbo server-rendered HTML (no JSON state on any page) plus one JSON
  route, /storefront/search_suggestions. EVERY path on these hosts — pages,
  feeds, robots.txt, the JSON route — answers a Cloudflare managed challenge
  (403 + `cf-mitigated: challenge`) to plain curl on every egress tried:
  direct, US / IN residential and datacenter proxies. A HEADED patchright
  Chrome clears it without a click (2-4 s from a home IP, ~14 s through a US
  residential exit); headless never clears. The browser's cf_clearance + __cf_bm
  cookies and its user-agent then replay over curl_cffi from the same exit,
  for every path of that host. cf_clearance is bound to a HOST (the
  themeforest cookie is 403 on codecanyon), so identities are kept per host:
  minted lazily on the host's first request, shared by every worker thread,
  re-minted when a replay is challenged again. A failed mint backs off for
  config.ENVATO_MARKET_HARVEST_COOLDOWN seconds instead of relaunching
  Chrome per request.

ENVATO ELEMENTS — elements.envato.com
  A React app whose every page is hydrated from one JSON route:
  /data-api/page/<route>?path=<page path> (the route name is ignored; `path`
  picks the page). ~120-260 KB of JSON against a 1.4 MB HTML page, open to
  plain curl_cffi. Cloudflare challenges requests in bursts (not
  path-scoped; residential exits vary between clean, challenged and dead),
  so: direct first, then the last good residential exit and fresh ones
  (config.ENVATO_ELEMENTS_PROXY_COUNTRY) up to
  config.ENVATO_ELEMENTS_ROTATE_ATTEMPTS, one more round after a backoff,
  and finally the shared browser's elements.envato.com tab (the Market
  machinery below) when config.ENVATO_ELEMENTS_BROWSER_FALLBACK is on.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  EnvatoUpstreamError  transport failure / 5xx                — retried
  EnvatoBlocked        challenge that survived a fresh identity / exits
  EnvatoBadRequest     upstream rejected the params            — never retried
  EnvatoNotFound       404 / unknown item or author            — never retried
"""
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlencode, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError

IMPERSONATE = "chrome"
TIMEOUT = 40
FANOUT_WORKERS = 8
ELEMENTS = "https://elements.envato.com"
DATA_API = ELEMENTS + "/data-api/page/page"

CF_MARKERS = ("just a moment", "cf-chl", "challenge-platform", "cf_chl_opt",
              "performing security verification", "attention required! | cloudflare")
HARVEST_POLL = 0.5
HARVEST_SETTLE = 1.5
CLICK_EVERY = 10
MAX_CLICKS = 3
HARVEST_SEED = "/"

HTML_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
}
JSON_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
}


class EnvatoUpstreamError(UpstreamError):
    """Transport failure or 5xx — retryable."""


class EnvatoBlocked(EnvatoUpstreamError, Blocked):
    """Cloudflare challenge that a fresh identity / exit could not clear."""


class EnvatoBadRequest(BadRequest):
    """Upstream rejected the params — never retried."""


class EnvatoNotFound(NotFound):
    """Unknown item / author / page — never retried."""


def dump_debug(name, text):
    """Write a raw response to $ENVATO_DEBUG_DIR/<name>.html."""
    dbg = os.environ.get("ENVATO_DEBUG_DIR", "")
    if dbg and text:
        try:
            os.makedirs(dbg, exist_ok=True)
            with open(os.path.join(dbg, name + ".html"), "w") as f:
                f.write(text)
        except OSError:
            pass


def looks_blocked(resp):
    """A Cloudflare interstitial rather than a real page / 404."""
    if any(k.lower() == "cf-mitigated" for k in resp.headers.keys()):
        return True
    if resp.status_code not in (403, 429, 503):
        return False
    low = (resp.text or "")[:6000].lower()
    return any(m in low for m in CF_MARKERS)


def _new_session(proxy):
    from curl_cffi import requests as curl_requests
    sess = curl_requests.Session(impersonate=IMPERSONATE)
    if proxy:
        sess.proxies = {"http": proxy, "https": proxy}
    return sess


def _close(sess):
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


# ======================================================================================
# Envato Market: one shared headed Chrome, one tab per marketplace host
# ======================================================================================
# Cloudflare treats the seven hosts independently, and by exit IP:
#   * a CHALLENGED exit shows a Turnstile page; clicking it earns a
#     cf_clearance whose cookies + UA replay over curl_cffi from the same exit
#     ("curl" mode: parallel, ~1 s per page);
#   * an UNCHALLENGED exit shows the real page straight away but issues no
#     cf_clearance, and curl_cffi (any fingerprint, with or without the
#     browser's cookies and UA) is still 403 there — while the same page's
#     own fetch() answers 200. Those hosts are served by an in-page fetch()
#     from their tab ("browser" mode, serialised on the browser's thread).
# Both happen on the same host from different exits (verified 2026-09-21), so
# the mode is decided per host at mint time by a curl replay of the page the
# tab just loaded. The Chrome is launched on the first Market request and
# closed after config.ENVATO_MARKET_BROWSER_IDLE seconds without one.

class _Identity:
    __slots__ = ("host", "mode", "cookies", "ua", "proxy", "version")

    def __init__(self, host, mode, cookies, ua, proxy, version):
        self.host, self.mode, self.cookies, self.ua = host, mode, cookies, ua
        self.proxy, self.version = proxy, version


class _Resp:
    """curl-response lookalike for an in-page fetch result."""

    def __init__(self, status_code, text, headers, url):
        self.status_code, self.text, self.headers, self.url = status_code, text, headers or {}, url

    def json(self):
        return json.loads(self.text)


class _MarketBrowser:
    """The shared headed Chrome. Every playwright call runs on the driver's
    owner thread through driver.call(); tab Page objects never leave it."""

    def __init__(self):
        self.lock = threading.RLock()
        self.driver = None
        self.proxy = None
        self.generation = 0
        self.tabs = {}              # host -> playwright Page (owner-thread only)
        self.last_used = 0.0
        self._reaper = None

    # ---- lifecycle ---------------------------------------------------------------
    def _launch(self):
        from chrome_manager import create_scope
        from patchright_driver import PatchrightDriver
        self._close_locked()
        proxy = config.envato_proxy(config.ENVATO_MARKET_PROXY_COUNTRY)
        print(f"envato: launching the Market browser "
              f"(proxy={'direct' if not proxy else proxy.rsplit('@', 1)[-1]})")
        with create_scope():
            self.driver = PatchrightDriver(proxy_url=proxy, headless=False)
        self.proxy = proxy
        self.generation += 1
        self.tabs = {}
        if self._reaper is None:
            self._reaper = threading.Thread(target=self._reap, name="envato-browser-reaper", daemon=True)
            self._reaper.start()

    def _close_locked(self):
        driver, self.driver, self.tabs = self.driver, None, {}
        if driver is not None:
            try:
                driver.close()
            except Exception:
                pass

    def restart(self, generation):
        """Relaunch on a fresh exit unless another thread already did."""
        with self.lock:
            if self.generation == generation:
                self._close_locked()

    def _reap(self):
        while True:
            time.sleep(30)
            with self.lock:
                if self.driver is not None and time.time() - self.last_used > config.ENVATO_MARKET_BROWSER_IDLE:
                    print("envato: closing the idle Market browser")
                    self._close_locked()
                    _drop_browser_identities()

    def _driver(self):
        with self.lock:
            if self.driver is None:
                self._launch()
            self.last_used = time.time()
            return self.driver, self.generation

    # ---- tabs --------------------------------------------------------------------
    def open_host(self, host):
        """Load https://<host>/ in the host's tab until the real page shows
        (clicking a Turnstile checkbox when one appears). Returns (cookies,
        ua, proxy, generation). Raises RuntimeError when it never clears."""
        from envato.util import click_turnstile as _click_turnstile

        driver, generation = self._driver()
        base = f"https://{host}"
        tabs = self.tabs

        def goto(page):
            tab = tabs.get(host)
            if tab is None or tab.is_closed():
                tab = page if not tabs and page.url in ("about:blank", "") else page.context.new_page()
                tabs[host] = tab
            tab.goto(base + HARVEST_SEED, referer="https://www.google.com/",
                     wait_until="domcontentloaded", timeout=60000)

        def state(page):
            tab = tabs[host]
            return tab.title() or "", tab.url

        def click(page):
            return _click_turnstile(tabs[host])

        started = time.monotonic()
        driver.call(goto)
        clicks, last_click = 0, None
        while True:
            title, _ = driver.call(state)
            low = title.lower()
            if low and not any(m in low for m in CF_MARKERS):
                time.sleep(HARVEST_SETTLE)
                break
            elapsed = time.monotonic() - started
            if elapsed > config.ENVATO_MARKET_HARVEST_TIMEOUT:
                raise RuntimeError(f"Cloudflare challenge on {host} did not clear (clicks={clicks})")
            due = (last_click is None and elapsed >= 4) or \
                  (last_click is not None and time.monotonic() - last_click >= CLICK_EVERY)
            if due and clicks < MAX_CLICKS and driver.call(click):
                clicks += 1
                last_click = time.monotonic()
            time.sleep(HARVEST_POLL)
        ua = driver.evaluate("navigator.userAgent")
        cookies = {c["name"]: c["value"] for c in driver.call(lambda page: page.context.cookies(base))}
        print(f"envato: {host} tab ready in {time.monotonic() - started:.0f}s "
              f"(clicks={clicks}, cf_clearance={'cf_clearance' in cookies})")
        return cookies, ua, self.proxy, generation

    def fetch(self, host, url, headers, generation):
        """In-page fetch() from the host's tab -> _Resp (status 0 = transport error)."""
        from patchright_driver import _FETCH_JS, FETCH_TIMEOUT_MS
        with self.lock:
            if self.driver is None or self.generation != generation:
                raise _StaleBrowser()
            driver = self.driver
            self.last_used = time.time()
        tabs = self.tabs

        def op(page):
            tab = tabs.get(host)
            if tab is None or tab.is_closed():
                return None
            return tab.evaluate(_FETCH_JS, {"url": url, "method": "GET", "headers": headers,
                                            "body": None, "referrer": None,
                                            "timeoutMs": FETCH_TIMEOUT_MS})
        res = driver.call(op)
        if res is None:
            raise _StaleBrowser()
        if not res.get("ok"):
            raise EnvatoUpstreamError(f"in-page fetch failed: {res.get('error')}")
        return _Resp(int(res.get("status") or 0), res.get("body") or "", res.get("headers"), res.get("url") or url)


class _StaleBrowser(Exception):
    """The browser (or the host's tab) this identity used is gone."""


_browser = _MarketBrowser()
_identities = {}               # host -> _Identity
_host_locks = {}               # host -> Lock (one mint per host at a time)
_failed_until = {}             # host -> epoch seconds
_versions = {}                 # host -> int (bumps on every mint)
_registry_lock = threading.Lock()
_local = threading.local()     # per-thread curl sessions keyed by host


def _host_lock(host):
    with _registry_lock:
        return _host_locks.setdefault(host, threading.Lock())


def _drop_browser_identities():
    with _registry_lock:
        for host in [h for h, i in _identities.items() if i.mode == "browser"]:
            _identities.pop(host, None)


def _curl_validates(host, cookies, ua, proxy):
    sess = _new_session(proxy)
    try:
        resp = sess.get(f"https://{host}{HARVEST_SEED}", headers={**HTML_HEADERS, "user-agent": ua},
                        cookies=cookies, timeout=TIMEOUT)
    except Exception as e:
        print(f"envato: {host} curl validation failed: {type(e).__name__}: {e}")
        return False
    finally:
        _close(sess)
    return resp.status_code == 200 and not looks_blocked(resp)


def _mint(host):
    """Open the host's tab (fresh exit on failure) and pick its mode."""
    last = None
    for attempt in range(1, config.ENVATO_MARKET_HARVEST_ATTEMPTS + 1):
        generation = _browser.generation
        try:
            _, generation = _browser._driver()     # the browser this attempt runs on (launched if needed)
            cookies, ua, proxy, generation = _browser.open_host(host)
        except Exception as e:
            last = e
            print(f"envato: {host} mint attempt {attempt}/{config.ENVATO_MARKET_HARVEST_ATTEMPTS} "
                  f"failed: {type(e).__name__}: {str(e).splitlines()[0][:160]}")
            _browser.restart(generation)            # next attempt on a fresh exit
            continue
        mode = "curl" if _curl_validates(host, cookies, ua, proxy) else "browser"
        print(f"envato: {host} served over {mode}")
        with _registry_lock:
            _versions[host] = _versions.get(host, 0) + 1
            return _Identity(host, mode, cookies, ua, proxy, generation if mode == "browser" else _versions[host])
    _failed_until[host] = time.time() + config.ENVATO_MARKET_HARVEST_COOLDOWN
    raise EnvatoBlocked(f"Cloudflare challenge on {host}; the browser could not open it ({last})")


def _identity(host):
    """The shared identity for `host`, minting one if needed."""
    ident = _identities.get(host)
    if ident is not None:
        return ident
    with _host_lock(host):
        ident = _identities.get(host)
        if ident is not None:
            return ident
        if time.time() < _failed_until.get(host, 0):
            raise EnvatoBlocked(f"Cloudflare challenge on {host}; a recent identity mint failed, "
                                f"retrying after the cooldown")
        ident = _mint(host)
        with _registry_lock:
            _identities[host] = ident
        return ident


def _invalidate(ident):
    with _registry_lock:
        if _identities.get(ident.host) is ident:
            _identities.pop(ident.host, None)


def _market_session(ident):
    sessions = getattr(_local, "market", None)
    if sessions is None:
        sessions = _local.market = {}
    entry = sessions.get(ident.host)
    if entry is not None and entry[0] is not ident:
        _close(entry[1])
        entry = None
    if entry is None:
        entry = (ident, _new_session(ident.proxy))
        sessions[ident.host] = entry
    return entry[1]


def _drop_market_session(host):
    sessions = getattr(_local, "market", None) or {}
    entry = sessions.pop(host, None)
    if entry is not None:
        _close(entry[1])


def with_query(url, params):
    """url + an encoded query string. Built here because curl_cffi, handed
    `params`, re-parses the URL and rejects a percent-encoded path
    ("/search/admin%20dashboard") as malformed."""
    if not params:
        return url
    return url + ("&" if "?" in url else "?") + urlencode(params, doseq=True, quote_via=quote)


def _market_once(url, params, headers, allow_redirects):
    """One GET with the host's identity -> response. A challenge (or a dead
    tab) re-mints the identity once."""
    host = urlparse(url).hostname
    url = with_query(url, params)
    for _ in range(2):
        ident = _identity(host)
        try:
            if ident.mode == "browser":
                resp = _browser.fetch(host, url, headers, ident.version)
            else:
                resp = _market_session(ident).get(
                    url, headers={**headers, "user-agent": ident.ua}, cookies=ident.cookies,
                    timeout=TIMEOUT, allow_redirects=allow_redirects)
        except _StaleBrowser:
            _invalidate(ident)
            continue
        except EnvatoUpstreamError:
            raise
        except Exception as e:
            # A transport error usually means the sticky exit died ("CONNECT
            # tunnel failed"): drop the identity so the retry re-opens the
            # host's tab — on a dead exit that fails too, and _mint then
            # relaunches Chrome on a fresh one.
            _drop_market_session(host)
            _invalidate(ident)
            raise EnvatoUpstreamError(f"request failed: {type(e).__name__}: {e}")
        if not looks_blocked(resp):
            return resp
        dump_debug(f"blocked_{host}", resp.text)
        _invalidate(ident)
        _drop_market_session(host)
    raise EnvatoBlocked(f"Cloudflare challenge on {url} even with a fresh identity")


def market_request(url, params=None, *, as_json=False, label=None, allow_redirects=True,
                   missing=None, not_found_ok=False):
    """GET an Envato Market URL -> the curl response. 404 raises
    EnvatoNotFound (or returns the response with not_found_ok); 5xx and
    transport errors retry with backoff."""
    label = label or url
    params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
    headers = dict(JSON_HEADERS if as_json else HTML_HEADERS)
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            resp = _market_once(url, params, headers, allow_redirects)
        except EnvatoBlocked:
            raise
        except EnvatoUpstreamError as e:
            last = e
        else:
            if resp.status_code == 404:
                if not_found_ok:
                    return resp
                raise EnvatoNotFound(missing or f"{label}: not found on Envato Market")
            if resp.status_code in (400, 406, 422):
                raise EnvatoBadRequest(f"Envato rejected {label} (HTTP {resp.status_code})")
            if resp.status_code < 400:
                return resp
            last = EnvatoUpstreamError(f"HTTP {resp.status_code} on {label}")
        if attempt < config.MAX_RETRIES:
            time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


def market_html(url, params=None, **kwargs):
    return market_request(url, params, **kwargs).text


def market_json(url, params=None, **kwargs):
    resp = market_request(url, params, as_json=True, **kwargs)
    try:
        return resp.json()
    except Exception:
        dump_debug("nonjson_market", resp.text)
        raise EnvatoUpstreamError(f"{kwargs.get('label') or url} returned a non-JSON body")


# ======================================================================================
# Envato Elements: /data-api/page JSON
# ======================================================================================

def _elements_session(proxy):
    key = proxy or "direct"
    sessions = getattr(_local, "elements", None)
    if sessions is None:
        sessions = _local.elements = {}
    sess = sessions.get(key)
    if sess is None:
        # every rotation is a fresh sticky exit: keep direct + the current one
        for other in [k for k in sessions if k not in ("direct", key)]:
            _close(sessions.pop(other))
        sess = sessions[key] = _new_session(proxy)
    return sess


def _drop_elements_session(proxy):
    sessions = getattr(_local, "elements", None) or {}
    _close(sessions.pop(proxy or "direct", None))


_elements_exit = {"proxy": None}     # the last residential exit that passed
_elements_lock = threading.Lock()


def _elements_once(path, proxy):
    """One data-api call -> response, or None when Cloudflare challenged it."""
    try:
        resp = _elements_session(proxy).get(
            with_query(DATA_API, {"path": path}), headers={**JSON_HEADERS, "referer": ELEMENTS + path},
            timeout=TIMEOUT)
    except Exception as e:
        _drop_elements_session(proxy)
        raise EnvatoUpstreamError(f"request failed: {type(e).__name__}: {e}")
    if looks_blocked(resp):
        dump_debug("blocked_elements", resp.text)
        return None
    return resp


def _elements_fetch(path):
    """Direct, then the last good exit, then fresh exits."""
    resp = _elements_once(path, None)
    if resp is not None:
        return resp
    country = config.ENVATO_ELEMENTS_PROXY_COUNTRY
    with _elements_lock:
        candidates = [_elements_exit["proxy"]] if _elements_exit["proxy"] else []
    candidates += [None] * config.ENVATO_ELEMENTS_ROTATE_ATTEMPTS
    if not country:
        candidates = []                   # no proxy pool: straight to the browser fallback
    for proxy in candidates:
        proxy = proxy or config.envato_proxy(country)
        try:
            resp = _elements_once(path, proxy)
        except EnvatoUpstreamError:
            continue
        if resp is not None:
            with _elements_lock:
                _elements_exit["proxy"] = proxy
            return resp
        _drop_elements_session(proxy)
    if not config.ENVATO_ELEMENTS_BROWSER_FALLBACK:
        raise EnvatoBlocked(f"Cloudflare challenge on Elements {path} on every exit tried")
    # last resort: the shared browser opens an elements.envato.com tab and the
    # call is replayed with its clearance (or run as an in-page fetch)
    return _market_once(DATA_API, {"path": path}, {**JSON_HEADERS, "referer": ELEMENTS + path}, True)


def elements_page(path, *, label=None, missing=None):
    """GET the Elements page data for `path` -> its `data` object (the
    {"status": "success", "data": {...}} wrapper some routes add is removed).
    404 / notFound raise EnvatoNotFound."""
    label = label or path
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            resp = _elements_fetch(path)
        except EnvatoBlocked as e:
            if attempt >= 2:
                raise
            last = e                          # challenges come in bursts: one more round
        except EnvatoUpstreamError as e:
            last = e
        else:
            if resp.status_code == 404:
                raise EnvatoNotFound(missing or f"{label}: not found on Envato Elements")
            if resp.status_code < 500:
                try:
                    body = resp.json()
                except Exception:
                    dump_debug("nonjson_elements", resp.text)
                    last = EnvatoUpstreamError(f"{label} returned a non-JSON body")
                else:
                    return _unwrap(body, label, missing)
            else:
                last = EnvatoUpstreamError(f"HTTP {resp.status_code} on {label}")
        if attempt < config.MAX_RETRIES:
            time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


def _unwrap(body, label, missing):
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        if isinstance(body, dict) and body.get("error"):
            raise EnvatoUpstreamError(f"{label}: {body.get('error')}")
        raise EnvatoUpstreamError(f"{label} returned no page data")
    if data.get("status") == "recovery":
        # an unknown item / page renders a "you may like" recovery grid
        raise EnvatoNotFound(missing or f"{label}: not found on Envato Elements")
    if data.get("serverError"):
        raise EnvatoUpstreamError(f"{label}: Envato Elements server error")
    if isinstance(data.get("data"), dict) and "status" in data:
        if data.get("status") not in ("success", None):
            raise EnvatoNotFound(missing or f"{label}: not found on Envato Elements")
        data = data["data"]
    if data.get("notFound"):
        raise EnvatoNotFound(missing or f"{label}: not found on Envato Elements")
    return data


# ======================================================================================
# parallel fan-out
# ======================================================================================

def run_parallel(fns, workers=FANOUT_WORKERS):
    """Run zero-arg callables in parallel; results align with `fns`."""
    if not fns:
        return []
    if len(fns) == 1:
        return [fns[0]()]
    with ThreadPoolExecutor(max_workers=min(workers, len(fns))) as ex:
        futures = [ex.submit(fn) for fn in fns]
        return [f.result() for f in futures]


if __name__ == "__main__":
    # Smoke test: python envato/fetch.py [market-url | elements-path]
    target = sys.argv[1] if len(sys.argv) > 1 else "/fonts"
    if target.startswith("http"):
        print(market_html(target)[:500])
    else:
        print(json.dumps(elements_page(target), ensure_ascii=False)[:500])
