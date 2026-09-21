"""Small value / HTML helpers shared by the Envato modules. Kept inside the
package (not imported from another site's package) so envato/ stands alone —
the open-source kit ships it verbatim."""
import html as html_lib
import random
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

_COUNT_RE = re.compile(r"([\d.,]+)\s*([KkMm]?)")


def to_int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def to_float(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def text(value):
    """Trimmed string or None ('' / whitespace -> None)."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def iso_datetime(value):
    """'2023-05-17T14:41:20.302Z' -> '2023-05-17T14:41:20Z' (UTC); junk -> None."""
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


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


def click_turnstile(page):
    """Real mouse click on a Cloudflare Turnstile checkbox: the widget
    iframe's bounding box, x at 1/9 of the width (the checkbox), y at the
    middle. Returns True when a challenge frame was found and clicked."""
    for frame in page.frames:
        if not frame.url.startswith("https://challenges.cloudflare.com"):
            continue
        try:
            box = frame.frame_element().bounding_box()
        except Exception:
            box = None
        if not box or box.get("width", 0) < 50:
            continue
        x = box["x"] + box["width"] / 9 + random.uniform(-5, 5)
        y = box["y"] + box["height"] / 2 + random.uniform(-5, 5)
        page.mouse.move(x, y, steps=random.randint(10, 25))
        page.wait_for_timeout(random.randint(100, 300))
        page.mouse.down()
        page.wait_for_timeout(random.randint(50, 150))
        page.mouse.up()
        return True
    return False
