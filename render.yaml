# KSA Cinema Showtimes API

A small backend that scrapes Saudi cinema showtimes and serves them as JSON in
exactly the shape your Android app's **Live Sync** feature expects:

```json
{ "movies": [...], "theaters": [...], "showtimes": [...] }
```

Currently implemented: **VOX Cinemas KSA** (fully working).
Template included for **Muvi** and any other chain.

---

## How it works

- `main.py` — FastAPI server. Exposes `GET /api/data`. Merges every scraper,
  de-duplicates, caches for 15 min, and returns the JSON.
- `scrapers/vox.py` — VOX scraper. VOX renders showtimes as plain HTML, so this
  is a simple HTTP GET + BeautifulSoup. **No headless browser needed.**
- `scrapers/common.py` — shared helpers (time conversion, name/city split, etc.).
- `scrapers/muvi.py` — stub/template for the next chain.

---

## 1. Run it locally

```bash
# from inside the cinema-scraper folder
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open <http://127.0.0.1:8000/api/data> in your browser. You should see live VOX
data. Add a date with `?date=2026-06-21`.

If `movies`/`showtimes` come back empty, see **Troubleshooting** below.

---

## 2. Deploy to Render (free)

1. Put this folder in a GitHub repo (`git init`, commit, push).
2. Go to <https://render.com> → **New** → **Web Service** → connect the repo.
3. Render reads `render.yaml` automatically. If asked manually, set:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Plan:** Free
4. Deploy. You'll get a URL like `https://ksa-cinema-scraper.onrender.com`.
5. Your endpoint is `https://ksa-cinema-scraper.onrender.com/api/data`.

> Note: Render's free tier sleeps after ~15 min idle, so the first request
> after a nap takes ~30s to wake. Fine for a personal app; upgrade if you want
> it always-on.

---

## 3. Point the Android app at it

1. Open the app → **Settings** (top-right).
2. Paste your URL into **Web Scraper API Endpoint**:
   `https://ksa-cinema-scraper.onrender.com/api/data`
3. Tap **Save & Sync**.

---

## 4. Add another cinema chain

Each chain is one file returning `(movies, theaters, showtimes)` in the app's
shape. To add Muvi:

1. Implement `scrapers/muvi.py` (the file explains how to find Muvi's JSON API
   via Chrome DevTools → Network → Fetch/XHR).
2. In `main.py`, uncomment the import and add it to `SCRAPERS`:
   ```python
   from scrapers import muvi
   SCRAPERS = [("VOX", vox.scrape), ("MUVI", muvi.scrape)]
   ```

The merge/cache/serve logic handles the rest. If one chain errors, the others
still serve.

---

## Troubleshooting

**Empty VOX results after deploy.** VOX may have tweaked their markup. The
parser keys off stable signals (`/booking/`, `/movies/`, `heroes/` images), but
the movie/theater *titles* are read from heading tags. To confirm:

1. Open <https://ksa.voxcinemas.com/showtimes> in Chrome → right-click a movie
   title → **Inspect**. Note the tag (e.g. `h2`, `h3`).
2. If they've changed, edit `TITLE_TAGS` in `scrapers/vox.py`.

**`priceSar` and `genre` are null.** These aren't on the public listing page
(price only appears inside the booking flow). The app falls back to defaults, so
this is expected. You can enrich later by fetching each `/movies/<slug>` page.

**Be a good citizen.** The 15-min cache (`CACHE_TTL_SECONDS` in `main.py`) keeps
request volume low. Don't lower it aggressively. Check the site's Terms of Use
before scraping at higher frequency or for anything beyond personal use.
