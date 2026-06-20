"""
KSA Cinema Showtimes API  —  SINGLE-FILE version.

Everything (helpers + VOX scraper + web server) is in this one file on purpose,
so there are no folders to get wrong when uploading. Just this file plus
requirements.txt and you're done.

Endpoints:
    /            -> status + version (quick check the right build is live)
    /api/data    -> the JSON your Android app reads
    /api/debug   -> diagnostics: shows what VOX actually returns
    /health      -> {"status":"ok"}

Run locally:  uvicorn main:app --host 0.0.0.0 --port 8000
"""

import re
import time
import logging
import datetime as dt
import unicodedata
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

VERSION = "v3-single"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cinema-api")

# ===========================================================================
#  Helpers
# ===========================================================================

def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "unknown"


def to_24h(time_str: str):
    if not time_str:
        return None
    m = re.match(r"^\s*(\d{1,2})[:.](\d{2})\s*([ap])m\s*$", time_str.strip(), re.I)
    if not m:
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
    else:
        if hour != 12:
            hour += 12
    return f"{hour:02d}:{minute:02d}"


def split_name_city(heading: str):
    heading = (heading or "").strip()
    parts = re.split(r"\s+[-\u2013]\s+", heading)
    if len(parts) >= 2:
        city = parts[-1].strip()
        name = " - ".join(p.strip() for p in parts[:-1])
        return name, city
    return heading, None


META_RE = re.compile(
    r"\b(?P<rating>[A-Z]{1,3}\d{0,2}|G|PG)\b\s+"
    r"(?P<lang>[A-Za-z]+)\s+(?P<dur>\d{2,3})\s*min",
    re.I,
)


def parse_movie_meta(text: str):
    out = {"rating": None, "language": None, "durationMin": None}
    if not text:
        return out
    m = META_RE.search(text)
    if m:
        out["rating"] = m.group("rating")
        out["language"] = m.group("lang").capitalize()
        out["durationMin"] = int(m.group("dur"))
    else:
        d = re.search(r"(\d{2,3})\s*min", text)
        if d:
            out["durationMin"] = int(d.group(1))
    return out


# ===========================================================================
#  VOX Cinemas KSA scraper
# ===========================================================================

VOX_BASE = "https://ksa.voxcinemas.com"
VOX_SHOWTIMES = VOX_BASE + "/showtimes"
VOX_CHAIN = "VOX"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

TITLE_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]
BOOKING_RE = re.compile(r"/booking/(\d{3,5})-(\d+)")
TIME_RE = re.compile(r"^\s*\d{1,2}[:.]\d{2}\s*[ap]m\s*$", re.I)
SCREEN_WORDS = {
    "standard", "imax", "gold", "vip", "max", "premier", "premium", "kids",
    "theatre", "theater", "outdoor", "4dx", "dolby", "screenx",
}


def vox_fetch_html(date: Optional[dt.date] = None, timeout: int = 25) -> str:
    params = {"d": date.strftime("%Y%m%d")} if date else {}
    with requests.Session() as s:
        s.headers.update(HEADERS)
        try:
            s.get(VOX_BASE + "/", timeout=timeout, allow_redirects=True)
        except Exception:
            pass
        resp = s.get(VOX_SHOWTIMES, params=params, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp.text


def vox_diagnose(date: Optional[dt.date] = None, timeout: int = 25) -> dict:
    params = {"d": date.strftime("%Y%m%d")} if date else {}
    info: dict = {"chain": VOX_CHAIN}
    try:
        with requests.Session() as s:
            s.headers.update(HEADERS)
            try:
                s.get(VOX_BASE + "/", timeout=timeout, allow_redirects=True)
            except Exception:
                pass
            resp = s.get(VOX_SHOWTIMES, params=params, timeout=timeout, allow_redirects=True)
        html = resp.text or ""
        low = html.lower()
        info.update({
            "status_code": resp.status_code,
            "final_url": str(resp.url),
            "html_length": len(html),
            "found_booking_links": html.count("/booking/"),
            "found_movie_links": html.count("/movies/"),
            "found_poster_images": low.count("heroes/"),
            "looks_blocked": any(k in low for k in [
                "captcha", "are you a robot", "just a moment", "cloudflare",
                "access denied", "incapsula", "request unsuccessful",
                "enable javascript", "perimeterx", "px-captcha",
            ]),
            "snippet": " ".join(html.split())[:600],
        })
    except Exception as e:
        info["error"] = f"{type(e).__name__}: {e}"
    return info


def _is_screen_label(text: str) -> bool:
    low = text.lower()
    if low in SCREEN_WORDS:
        return True
    if len(text) <= 24 and not any(c.isdigit() for c in text) and text[0].isupper():
        return True
    return False


def _has_movie_link(el) -> bool:
    nxt = el.find_next("a", href=True)
    return bool(nxt and "/movies/" in nxt.get("href", ""))


def vox_parse(html: str):
    soup = BeautifulSoup(html, "html.parser")
    movies, theaters, showtimes = {}, {}, []
    current_movie = current_theater = None
    current_screen = "Standard"
    pending_poster = None
    pending_title = None
    seen_booking = set()

    for el in soup.find_all(TITLE_TAGS + ["img", "a", "strong", "b", "div", "span"]):
        if el.name == "img":
            src = el.get("src") or el.get("data-src") or ""
            if "heroes/" in src:
                pending_poster = src if src.startswith("http") else urljoin(VOX_BASE, src)
            continue

        if el.name == "a":
            href = el.get("href", "")
            mb = BOOKING_RE.search(href)
            if mb:
                cinema_code, session_id = mb.group(1), mb.group(2)
                booking_id = f"{cinema_code}-{session_id}"
                if booking_id in seen_booking:
                    continue
                seen_booking.add(booking_id)
                time24 = to_24h(el.get_text(strip=True))
                booking_url = href if href.startswith("http") else urljoin(VOX_BASE, href)
                tid = f"{VOX_CHAIN}-{cinema_code}"
                if current_theater is not None:
                    if current_theater["id"] != tid:
                        theaters.pop(current_theater["id"], None)
                        current_theater["id"] = tid
                    theaters[tid] = current_theater
                else:
                    theaters[tid] = {"id": tid, "name": f"VOX {cinema_code}",
                                     "chain": VOX_CHAIN, "city": None}
                if current_movie is not None:
                    showtimes.append({
                        "id": f"{VOX_CHAIN}-{booking_id}", "theaterId": tid,
                        "movieId": current_movie["id"], "time": time24,
                        "screenType": current_screen, "priceSar": None,
                        "bookingUrl": booking_url,
                    })
                continue

            if "/movies/" in href:
                slug = href.rstrip("/").split("/movies/")[-1].split("?")[0]
                mid = f"{VOX_CHAIN}-{slugify(slug)}"
                title = pending_title or slug.replace("-", " ").title()
                meta_text = el.parent.get_text(" ", strip=True) if el.parent else ""
                meta = parse_movie_meta(meta_text)
                if mid not in movies:
                    movies[mid] = {"id": mid, "title": title, "posterUrl": pending_poster,
                                   "genre": None, "durationMin": meta["durationMin"]}
                current_movie = movies[mid]
                current_theater = None
                current_screen = "Standard"
                pending_poster = None
                continue
            continue

        if el.name in TITLE_TAGS:
            text = el.get_text(" ", strip=True)
            if not text:
                continue
            meta = parse_movie_meta(text)
            if meta["durationMin"] is not None or _has_movie_link(el):
                pending_title = text
            else:
                name, city = split_name_city(text)
                tid = f"{VOX_CHAIN}-tmp-{slugify(text)}"
                current_theater = {"id": tid, "name": name, "chain": VOX_CHAIN, "city": city}
                theaters[tid] = current_theater
                current_screen = "Standard"
            continue

        if el.name in ("strong", "b", "div", "span"):
            text = el.get_text(" ", strip=True)
            if not text or len(text) > 40 or TIME_RE.match(text):
                continue
            if current_theater is not None and _is_screen_label(text):
                current_screen = text.split("\n")[0].strip()
            continue

    return list(movies.values()), list(theaters.values()), showtimes


def vox_scrape(date: Optional[dt.date] = None):
    return vox_parse(vox_fetch_html(date))


# ===========================================================================
#  Web server
# ===========================================================================

app = FastAPI(title="KSA Cinema Showtimes API", version=VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["GET"], allow_headers=["*"])

SCRAPERS = [("VOX", vox_scrape)]

_CACHE: dict = {}
CACHE_TTL_SECONDS = 15 * 60


def _collect(date: Optional[dt.date]) -> dict:
    movies, theaters, showtimes = {}, {}, []
    for name, scrape in SCRAPERS:
        try:
            m, t, s = scrape(date)
            for x in m:
                movies.setdefault(x["id"], x)
            for x in t:
                theaters.setdefault(x["id"], x)
            showtimes.extend(s)
            log.info("%s: %d movies, %d theaters, %d showtimes", name, len(m), len(t), len(s))
        except Exception as e:
            log.exception("scraper %s failed: %s", name, e)
    return {"movies": list(movies.values()),
            "theaters": list(theaters.values()),
            "showtimes": showtimes}


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
    if data["showtimes"]:
        _CACHE[key] = (now, data)
    return data


@app.get("/api/debug")
def api_debug():
    return {"version": VERSION, "VOX": vox_diagnose()}


@app.get("/")
def root():
    return {"status": "ok", "version": VERSION,
            "endpoints": ["/api/data", "/api/debug"],
            "chains": [name for name, _ in SCRAPERS]}


@app.get("/health")
def health():
    return {"status": "ok", "version": VERSION}
