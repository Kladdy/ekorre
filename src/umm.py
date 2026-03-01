from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import pytz
import requests
from bs4 import BeautifulSoup
from xml.etree import ElementTree


STOCKHOLM_TZ = pytz.timezone("Europe/Stockholm")


@dataclass(frozen=True)
class UmmEvent:
    unit_label: str  # e.g. F1, F2, F3, R3, R4
    start: datetime
    stop: datetime
    unavailable_mw: float | None
    status: str | None
    title: str | None
    link: str | None


_UNIT_NAME_PATTERNS: list[tuple[str, str]] = [
    ("F1", r"forsmark\s*block\s*1"),
    ("F2", r"forsmark\s*block\s*2"),
    ("F3", r"forsmark\s*block\s*3"),
    ("R3", r"ringhals\s*block\s*3"),
    ("R4", r"ringhals\s*block\s*4"),
]


def _parse_umm_datetime(value: str) -> datetime:
    """Parse UMM datetime strings like '27.04.2025 22:00'.

    Nord Pool UMM uses local time formatting in the HTML payload. We interpret it
    as Europe/Stockholm and return a tz-aware datetime.
    """

    dt = datetime.strptime(value.strip(), "%d.%m.%Y %H:%M")
    return STOCKHOLM_TZ.localize(dt)


def _parse_mw(value: str) -> float | None:
    v = (value or "").strip()
    if not v:
        return None
    # Example: '1172 MW'
    v = v.replace("MW", "").strip()
    try:
        return float(v)
    except ValueError:
        return None


def _looks_cancelled(status: str | None) -> bool:
    if not status:
        return False
    s = status.strip().lower()
    return s in {"dismissed", "cancelled", "canceled"}


def _unit_label_from_unit_name(unit_name: str) -> str | None:
    import re

    name = (unit_name or "").strip().lower()
    for label, pattern in _UNIT_NAME_PATTERNS:
        if re.search(pattern, name):
            return label
    return None


def _extract_event_from_description_html(description_html: str) -> Iterable[UmmEvent]:
    """Extract one or more UmmEvent from the item description.

    Notes:
    - A single UMM message can list multiple production units.
    - We only care about the nuclear blocks (Forsmark Block1-3, Ringhals block 3-4).
    """

    soup = BeautifulSoup(description_html or "", "html.parser")

    # First table contains metadata incl. Status
    status: str | None = None
    first_table = soup.find("table")
    if first_table:
        for tr in first_table.find_all("tr"):
            th = tr.find("th")
            td = tr.find("td")
            if not th or not td:
                continue
            if th.get_text(strip=True).lower() == "status:":
                status = td.get_text(strip=True)

    if _looks_cancelled(status):
        return []

    # Find the "Production Units" table (the one after the h3)
    prod_h3 = soup.find(lambda tag: tag.name == "h3" and "production units" in tag.get_text(" ", strip=True).lower())
    prod_table = None
    if prod_h3:
        prod_table = prod_h3.find_next("table")

    if not prod_table:
        return []

    rows = prod_table.find_all("tr")
    if len(rows) < 2:
        return []

    # Header indices
    header = [th.get_text(" ", strip=True).lower() for th in rows[0].find_all(["th", "td"])]

    def idx(col: str) -> int | None:
        try:
            return header.index(col)
        except ValueError:
            return None

    i_unit = idx("unit name")
    i_unavail = idx("unavailable capacity")
    i_from = idx("from")
    i_to = idx("to")

    if i_unit is None:
        return []

    events: list[UmmEvent] = []
    for r in rows[1:]:
        cols = [c.get_text(" ", strip=True) for c in r.find_all(["td", "th"])]
        if len(cols) <= i_unit:
            continue

        unit_name = cols[i_unit]
        unit_label = _unit_label_from_unit_name(unit_name)
        if not unit_label:
            continue

        start = _parse_umm_datetime(cols[i_from]) if (i_from is not None and len(cols) > i_from and cols[i_from]) else None
        stop = _parse_umm_datetime(cols[i_to]) if (i_to is not None and len(cols) > i_to and cols[i_to]) else None
        unavailable_mw = _parse_mw(cols[i_unavail]) if (i_unavail is not None and len(cols) > i_unavail) else None

        if not start or not stop:
            continue

        events.append(
            UmmEvent(
                unit_label=unit_label,
                start=start,
                stop=stop,
                unavailable_mw=unavailable_mw,
                status=status,
                title=None,
                link=None,
            )
        )

    return events


def fetch_umm_events(
    *,
    event_start_utc: datetime,
    event_stop_utc: datetime,
    limit: int = 500,
) -> list[UmmEvent]:
    """Fetch Nord Pool UMM RSS feed and extract unavailability events.

    We fetch for Swedish nuclear producers (Forsmark/Ringhals) and filter out
    cancelled/dismissed messages.
    """

    assert event_start_utc.tzinfo is not None
    assert event_stop_utc.tzinfo is not None

    def to_iso_z(dt: datetime, *, end: bool = False) -> str:
        # Nord Pool examples use millisecond precision and trailing Z.
        # Use .000Z for start and .999Z for end for inclusive-ish filtering.
        dt_utc = dt.astimezone(pytz.UTC)
        base = dt_utc.strftime("%Y-%m-%dT%H:%M:%S")
        return f"{base}.{'999' if end else '000'}Z"

    url = (
        "https://ummrss.nordpoolgroup.com/messages/"
        "?areas=10Y1001A1001A46L"
        "&companies=N02101"
        "&companies=N01256"
        "&fuelTypes=14"
        f"&eventStartDate={requests.utils.quote(to_iso_z(event_start_utc, end=False))}"
        f"&eventStopDate={requests.utils.quote(to_iso_z(event_stop_utc, end=True))}"
        f"&limit={limit}"
    )

    resp = requests.get(url, timeout=20)
    resp.raise_for_status()

    # RSS XML
    root = ElementTree.fromstring(resp.content)

    events: list[UmmEvent] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip() or None
        link = (item.findtext("link") or "").strip() or None
        description = item.findtext("description") or ""

        for ev in _extract_event_from_description_html(description):
            # Carry title/link onto each extracted unit row
            events.append(
                UmmEvent(
                    unit_label=ev.unit_label,
                    start=ev.start,
                    stop=ev.stop,
                    unavailable_mw=ev.unavailable_mw,
                    status=ev.status,
                    title=title,
                    link=link,
                )
            )

    # Sort for stable output
    events.sort(key=lambda e: (e.unit_label, e.start))
    return events
