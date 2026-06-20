"""Cinema showtimes API.

Exposes GET /api/data returning:
    { "movies": [...], "theaters": [...], "showtimes": [...] }

in exactly the shape the Android app expects. Each cinema chain is a small
scraper module that returns (movies, theaters, showtimes); this file merges
them, de-duplicates by id, caches the result for a few minutes, and serves it.

Run locally:   uvicorn main:app --reload --port 8000
Then open:     http://127.0.0.1:8000/api/data
"""

import time
import datetime as dt
import logging
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from scrapers import vox
# When you add more chains, import them here and append to SCRAPERS below.
# from scrapers import muvi, reel

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cinema-api")

app = FastAPI(title="KSA Cinema Showtimes API", version="1.0")

# Allow the Android app (and a browser) to call this from anywhere.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"],
)

# Each entry: (name, scrape_callable). scrape() returns (movies, theaters, showtimes).
SCRAPERS = [
    ("VOX", vox.scrape),
    # ("MUVI", muvi.scrape),
    # ("REEL", reel.scrape),
]

# --- tiny in-memory cache (per date) ---------------------------------------
_CACHE: dict[str, tuple[float, dict]] = {}
CACHE_TTL_SECONDS = 15 * 60     # refresh at most every 15 minutes


def _collect(date: Optional[dt.date]) -> dict:
    movies, theaters, showtimes = {}, {}, []
    for name, scrape in SCRAPERS:
        try:
            m, t, s = scrape(date) if date else scrape()
            for x in m:
                movies.setdefault(x["id"], x)
            for x in t:
                theaters.setdefault(x["id"], x)
            showtimes.extend(s)
            log.info("%s: %d movies, %d theaters, %d showtimes",
                     name, len(m), len(t), len(s))
        except Exception as e:
            # One chain failing must not break the whole feed.
            log.exception("scraper %s failed: %s", name, e)
    return {
        "movies": list(movies.values()),
        "theaters": list(theaters.values()),
        "showtimes": showtimes,
    }


@app.get("/api/data")
def api_data(date: Optional[str] = Query(None, description="YYYY-MM-DD; defaults to today")):
    day = None
    if date:
        try:
            day = dt.datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            day = None
    key = day.isoformat() if day else "today"

    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    data = _collect(day)
    # Only cache non-empty results so a transient outage doesn't get pinned.
    if data["showtimes"]:
        _CACHE[key] = (now, data)
    return data


@app.get("/")
def root():
    return {
        "status": "ok",
        "endpoints": ["/api/data", "/api/data?date=YYYY-MM-DD"],
        "chains": [name for name, _ in SCRAPERS],
    }


@app.get("/health")
def health():
    return {"status": "ok"}
