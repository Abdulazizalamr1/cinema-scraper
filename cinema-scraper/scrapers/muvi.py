"""Muvi Cinemas scraper — STUB / template.

Muvi (muvicinemas.com) is a React/Next.js site, so unlike VOX the showtimes
are NOT in the initial HTML. You have two options:

OPTION A (preferred): find Muvi's internal JSON API.
  1. Open https://www.muvicinemas.com in Chrome.
  2. DevTools (F12) -> Network tab -> filter "Fetch/XHR".
  3. Pick a city/date and watch which request returns the showtimes JSON.
     It will be something like /api/.../sessions or a GraphQL endpoint.
  4. Copy that request URL + any headers, and call it with `requests` below.
     This is fast and needs no browser.

OPTION B (fallback): render the page with Playwright, then parse the DOM.
  Only needed if no clean JSON endpoint exists. Heavier to host.

Until you wire one of these up, scrape() returns empty lists so the API keeps
working with the chains that ARE implemented.
"""

import datetime as dt
# import requests
# from .common import slugify, to_24h, split_name_city

CHAIN = "MUVI"


def scrape(date: dt.date | None = None):
    """Return (movies, theaters, showtimes). Empty until implemented.

    Example skeleton once you've found the JSON endpoint:

        url = "https://www.muvicinemas.com/api/v1/sessions"
        params = {"city": "riyadh", "date": (date or dt.date.today()).isoformat()}
        data = requests.get(url, params=params, timeout=25,
                            headers={"User-Agent": "CinemaSyncBot/1.0"}).json()
        movies, theaters, showtimes = [], [], []
        for item in data["sessions"]:
            mid = f"{CHAIN}-{item['movieId']}"
            tid = f"{CHAIN}-{item['cinemaId']}"
            ... # map fields into the app's shape, using to_24h() etc.
        return movies, theaters, showtimes
    """
    return [], [], []
