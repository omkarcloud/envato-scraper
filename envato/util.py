"""Small value / HTML helpers shared by the Envato modules. Kept inside the
package or taken from scraper_utils, never imported from another site's
package: the open-source kit ships both verbatim."""
import html as html_lib
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from scraper_utils.values import num as to_float, to_int
from scraper_utils.text import stripped as text
from scraper_utils.dates import iso_utc as iso_datetime

_COUNT_RE = re.compile(r"([\d.,]+)\s*([KkMm]?)")


def soup(markup):
    return BeautifulSoup(markup or "", "lxml")


def clean(node):
    """A node / string -> whitespace-collapsed text or None."""
    if node is None:
        return None
    value = node.get_text() if hasattr(node, "get_text") else str(node)
    value = " ".join(html_lib.unescape(value).replace("\xa0", " ").split())
    return value or None


def count(value):
    """'1,234' -> 1234; '13.8K' -> 13800; '2.9M' -> 2900000; junk -> None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    m = _COUNT_RE.search(str(value).replace("\xa0", " "))
    if not m:
        return None
    number, suffix = m.group(1).replace(",", ""), m.group(2).lower()
    try:
        amount = float(number)
    except ValueError:
        return None
    if suffix == "k":
        amount *= 1000
    elif suffix == "m":
        amount *= 1_000_000
    return int(round(amount))
