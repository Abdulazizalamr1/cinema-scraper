"""VOX Cinemas KSA scraper.

VOX serves the whole showtimes table as server-rendered HTML, so we only need
an HTTP GET + BeautifulSoup. No headless browser required.

Page:    https://ksa.voxcinemas.com/showtimes
Date:    add ?d=YYYYMMDD for a specific day (today if omitted)

Parsing strategy (deliberately NOT based on CSS class names, which change):
we walk the document in order and key off stable, observed signals:

  * poster image  -> <img src="...assets.voxcinemas.com/heroes/...">
  * movie info    -> <a href="/movies/<slug>">  + nearby "RATING LANG NN min" text
  * theater       -> a heading whose text is "Name - City" and is NOT a movie
  * booking link  -> <a href="/booking/<cinemaCode>-<sessionId>">  (gives stable ids)

If VOX changes their markup, the only thing you may need to adjust is which
tag the movie/theater *titles* live in (see TITLE_TAGS below). Everything else
keys off href/src patterns that are far more stable.
"""

import re
import datetime as dt
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .common import slugify, to_24h, split_name_city, parse_movie_meta

BASE = "https://ksa.voxcinemas.com"
SHOWTIMES_URL = BASE + "/showtimes"
CHAIN = "VOX"

HEADERS = {
    # Identify politely. Use a real-ish UA so we get the normal HTML.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 CinemaSyncBot/1.0"
    ),
    "Accept-Language": "en",
}

# Tags that movie + theater titles tend to live in. We scan all of them and
# decide movie-vs-theater by context (a movie has a poster + /movies/ link).
TITLE_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]

BOOKING_RE = re.compile(r"/booking/(\d{3,5})-(\d+)")
TIME_RE = re.compile(r"^\s*\d{1,2}[:.]\d{2}\s*[ap]m\s*$", re.I)


def fetch_html(date: dt.date | None = None, timeout: int = 25) -> str:
    params = {}
    if date:
        params["d"] = date.strftime("%Y%m%d")
    resp = requests.get(SHOWTIMES_URL, params=params, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def parse(html: str):
    """Return (movies, theaters, showtimes) lists in the app's JSON shape."""
    soup = BeautifulSoup(html, "html.parser")

    movies = {}      # movieId -> movie dict
    theaters = {}    # theaterId -> theater dict
    showtimes = []   # list of showtime dicts

    current_movie = None
    current_theater = None
    current_screen = "Standard"
    pending_poster = None

    # Build an in-document-order stream of the elements we care about.
    interesting = soup.find_all(TITLE_TAGS + ["img", "a", "strong", "b", "div", "span"])

    # We only want leaf-ish text nodes for screen types; track seen booking ids
    # to avoid double counting nested wrappers.
    seen_booking = set()

    for el in interesting:
        # --- poster image -------------------------------------------------
        if el.name == "img":
            src = el.get("src") or el.get("data-src") or ""
            if "heroes/" in src or "/heroes" in src:
                pending_poster = src if src.startswith("http") else urljoin(BASE, src)
            continue

        # --- links: either a movie-info link or a booking link ------------
        if el.name == "a":
            href = el.get("href", "")

            # Booking link => this is a showtime under the current movie/theater.
            mb = BOOKING_RE.search(href)
            if mb:
                cinema_code, session_id = mb.group(1), mb.group(2)
                booking_id = f"{cinema_code}-{session_id}"
                if booking_id in seen_booking:
                    continue
                seen_booking.add(booking_id)

                time24 = to_24h(el.get_text(strip=True))
                booking_url = href if href.startswith("http") else urljoin(BASE, href)

                # Make sure the theater that owns this booking is registered,
                # using the cinema_code from the URL as a rock-solid id.
                tid = f"{CHAIN}-{cinema_code}"
                if current_theater is not None:
                    # upgrade the placeholder id to the real cinema code
                    if current_theater["id"] != tid:
                        theaters.pop(current_theater["id"], None)
                        current_theater["id"] = tid
                    theaters[tid] = current_theater
                else:
                    theaters[tid] = {
                        "id": tid, "name": f"VOX {cinema_code}",
                        "chain": CHAIN, "city": None,
                    }

                if current_movie is not None:
                    showtimes.append({
                        "id": f"{CHAIN}-{booking_id}",
                        "theaterId": tid,
                        "movieId": current_movie["id"],
                        "time": time24,
                        "screenType": current_screen,
                        "priceSar": None,           # not exposed before checkout
                        "bookingUrl": booking_url,
                    })
                continue

            # Movie info link => establishes the current movie.
            if "/movies/" in href:
                slug = href.rstrip("/").split("/movies/")[-1].split("?")[0]
                mid = f"{CHAIN}-{slugify(slug)}"
                # Title = nearest preceding heading text we recorded.
                title = getattr(parse, "_pending_title", None) or slug.replace("-", " ").title()
                # The "RATING LANG NN min" line is in the link's own container.
                meta_text = el.parent.get_text(" ", strip=True) if el.parent else ""
                meta = parse_movie_meta(meta_text)
                if meta["durationMin"] is None:
                    meta = parse_movie_meta(getattr(parse, "_pending_meta", "") or "")
                if mid not in movies:
                    movies[mid] = {
                        "id": mid,
                        "title": title,
                        "posterUrl": pending_poster,
                        "genre": None,             # not on listing page
                        "durationMin": meta["durationMin"],
                        # bonus fields the app ignores but you may find useful:
                        "rating": meta["rating"],
                        "language": meta["language"],
                    }
                current_movie = movies[mid]
                current_theater = None
                current_screen = "Standard"
                pending_poster = None
                continue
            continue

        # --- headings: movie title OR theater name ------------------------
        if el.name in TITLE_TAGS:
            text = el.get_text(" ", strip=True)
            if not text:
                continue

            # Does the surrounding text carry a movie meta line? If a sibling
            # contains "/movies/" we treat this heading as a movie title and
            # stash it for the upcoming /movies/ link.
            block_text = text
            # Look a little ahead for the meta ("RATING LANG NN min")
            meta = parse_movie_meta(_nearby_text(el))
            looks_like_movie = meta["durationMin"] is not None or _has_movie_link(el)

            if looks_like_movie:
                parse._pending_title = text
                parse._pending_meta = _nearby_text(el)
                # current_movie gets set when we hit the /movies/ link.
            else:
                # Treat as a theater heading.
                name, city = split_name_city(text)
                # Temporary id; upgraded to real cinema code when a booking link appears.
                tid = f"{CHAIN}-tmp-{slugify(text)}"
                current_theater = {"id": tid, "name": name, "chain": CHAIN, "city": city}
                theaters[tid] = current_theater
                current_screen = "Standard"
            continue

        # --- screen-type label (Standard / IMAX / VIP / Avant Garde ...) ---
        if el.name in ("strong", "b", "div", "span"):
            text = el.get_text(" ", strip=True)
            if not text or len(text) > 40:
                continue
            if TIME_RE.match(text):
                continue
            # A screen-type label sits inside a theater block, is short, and is
            # not itself a time or a heading we already used.
            if current_theater is not None and _is_screen_label(text):
                current_screen = text.split("\n")[0].strip()
            continue

    # clean transient attrs
    for attr in ("_pending_title", "_pending_meta"):
        if hasattr(parse, attr):
            delattr(parse, attr)

    # Drop the bonus fields the app doesn't expect (keep output clean / on-spec).
    movies_out = []
    for m in movies.values():
        movies_out.append({
            "id": m["id"], "title": m["title"], "posterUrl": m["posterUrl"],
            "genre": m["genre"], "durationMin": m["durationMin"],
        })

    return movies_out, list(theaters.values()), showtimes


# --- small heuristics -------------------------------------------------------

SCREEN_WORDS = {
    "standard", "imax", "gold", "vip", "max", "premier", "premium", "kids",
    "theatre", "theater", "outdoor", "4dx", "dolby", "screenx",
}


def _is_screen_label(text: str) -> bool:
    low = text.lower()
    if low in SCREEN_WORDS:
        return True
    # VOX 'Via Riyadh' uses bespoke names (Avant Garde, Tuwaiq, Oasis...).
    # Accept short Title-Case labels with no digits as screen types.
    if len(text) <= 24 and not any(c.isdigit() for c in text) and text[0].isupper():
        return True
    return False


def _nearby_text(el) -> str:
    """Concatenate this element + its next couple of siblings' text, to find
    the 'RATING LANG NN min' meta line that follows a movie title."""
    chunks = [el.get_text(" ", strip=True)]
    sib = el
    for _ in range(4):
        sib = sib.find_next(string=False) if hasattr(sib, "find_next") else None
        if sib is None:
            break
        try:
            chunks.append(sib.get_text(" ", strip=True))
        except Exception:
            pass
    return " ".join(chunks)


def _has_movie_link(el) -> bool:
    nxt = el.find_next("a", href=True)
    return bool(nxt and "/movies/" in nxt.get("href", ""))


def scrape(date: dt.date | None = None):
    """Public entrypoint: fetch + parse one day for VOX."""
    html = fetch_html(date)
    return parse(html)
