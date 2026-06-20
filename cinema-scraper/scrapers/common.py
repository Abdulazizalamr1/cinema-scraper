"""Shared helpers used by every cinema scraper.

The goal of each scraper is to return three lists of plain dicts that already
match the JSON shape the Android app expects:

    movies     -> {id, title, posterUrl, genre, durationMin}
    theaters   -> {id, name, chain, city}
    showtimes  -> {id, theaterId, movieId, time, screenType, priceSar, bookingUrl}

main.py merges the output of every scraper and de-duplicates by id.
"""

import re
import unicodedata


def slugify(text: str) -> str:
    """Turn 'Mortal Kombat 2' into 'mortal-kombat-2' for use as a stable id."""
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "unknown"


def to_24h(time_str: str):
    """Convert '1:00am' / '11:40pm' / '12:15am' -> '01:00' / '23:40' / '00:15'.

    Returns None if the string is not a recognizable clock time.
    """
    if not time_str:
        return None
    m = re.match(r"^\s*(\d{1,2})[:.](\d{2})\s*([ap])m\s*$", time_str.strip(), re.I)
    if not m:
        # Already 24h like '14:30'? Accept it.
        m24 = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", time_str.strip())
        if m24:
            h, mn = int(m24.group(1)), int(m24.group(2))
            if 0 <= h <= 23 and 0 <= mn <= 59:
                return f"{h:02d}:{mn:02d}"
        return None
    hour, minute, ampm = int(m.group(1)), int(m.group(2)), m.group(3).lower()
    if ampm == "a":
        if hour == 12:
            hour = 0
    else:  # pm
        if hour != 12:
            hour += 12
    return f"{hour:02d}:{minute:02d}"


def split_name_city(heading: str):
    """'Al Qasr Mall - Riyadh' -> ('Al Qasr Mall', 'Riyadh').

    Handles hyphen and en-dash separators. If no separator, city is None.
    """
    heading = (heading or "").strip()
    # Split on the LAST ' - ' or ' – ' (en dash), so 'The Spot, Sheikh Jaber - Riyadh' works.
    parts = re.split(r"\s+[-\u2013]\s+", heading)
    if len(parts) >= 2:
        city = parts[-1].strip()
        name = " - ".join(p.strip() for p in parts[:-1])
        return name, city
    return heading, None


# Movie meta line looks like:  "R18 English 115 min"  or  "PG12 Arabic 110 min"
META_RE = re.compile(
    r"\b(?P<rating>[A-Z]{1,3}\d{0,2}|G|PG)\b\s+"
    r"(?P<lang>[A-Za-z]+)\s+"
    r"(?P<dur>\d{2,3})\s*min",
    re.I,
)


def parse_movie_meta(text: str):
    """Pull rating, language, durationMin out of a meta blob. Missing -> None."""
    out = {"rating": None, "language": None, "durationMin": None}
    if not text:
        return out
    m = META_RE.search(text)
    if m:
        out["rating"] = m.group("rating")
        out["language"] = m.group("lang").capitalize()
        out["durationMin"] = int(m.group("dur"))
    else:
        # Fall back: just grab a duration if present.
        d = re.search(r"(\d{2,3})\s*min", text)
        if d:
            out["durationMin"] = int(d.group(1))
    return out
