"""Validate the VOX parser against an HTML fixture that mirrors the real,
observed page structure (poster img -> movie h2 + /movies/ link + meta ->
theater h3 -> screen-type label -> /booking/ time links)."""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from scrapers import vox

FIXTURE = """
<html><body>
  <section class="movie">
    <img src="https://assets.voxcinemas.com/heroes/B_HO00013102_1776659285169.jpg"/>
    <h2>Mortal Kombat 2</h2>
    <p>R18 English 115 min <a href="https://ksa.voxcinemas.com/movies/mortal-kombat-2">Info</a></p>

    <div class="cinema">
      <h3>Al Qasr Mall - Riyadh</h3>
      <div class="session">
        <strong>Standard</strong>
        <a href="https://ksa.voxcinemas.com/booking/0041-264342">1:00am</a>
        <a href="https://ksa.voxcinemas.com/booking/0041-264780">2:00am</a>
        <a href="https://ksa.voxcinemas.com/booking/0041-264343">3:30am</a>
      </div>
    </div>

    <div class="cinema">
      <h3>Century Corner - Riyadh</h3>
      <div class="session">
        <strong>IMAX</strong>
        <a href="https://ksa.voxcinemas.com/booking/0106-68500">12:15am</a>
        <a href="https://ksa.voxcinemas.com/booking/0106-68501">2:45am</a>
      </div>
    </div>

    <div class="cinema">
      <h3>Via Riyadh</h3>
      <div class="session">
        <strong>Interstellar</strong>
        <a href="https://ksa.voxcinemas.com/booking/0101-39250">11:40pm</a>
      </div>
    </div>
  </section>

  <section class="movie">
    <img src="https://assets.voxcinemas.com/heroes/B_HO00012735_1774844175845.jpg"/>
    <h2>The Devil Wears Prada 2</h2>
    <p>PG15 English 120 min <a href="https://ksa.voxcinemas.com/movies/the-devil-wears-prada-2">Info</a></p>
    <div class="cinema">
      <h3>The Spot, Sheikh Jaber - Riyadh</h3>
      <div class="session">
        <strong>Premium</strong>
        <a href="https://ksa.voxcinemas.com/booking/0058-72627">12:15am</a>
      </div>
    </div>
  </section>
</body></html>
"""

movies, theaters, showtimes = vox.parse(FIXTURE)

print("=== MOVIES ===")
for m in movies:
    print(m)
print("\n=== THEATERS ===")
for t in theaters:
    print(t)
print("\n=== SHOWTIMES ===")
for s in showtimes:
    print(s)

# --- assertions ---
titles = {m["title"] for m in movies}
assert "Mortal Kombat 2" in titles, "missing MK2"
assert "The Devil Wears Prada 2" in titles, "missing Prada"
mk2 = next(m for m in movies if m["title"] == "Mortal Kombat 2")
assert mk2["durationMin"] == 115, f"bad duration {mk2['durationMin']}"
assert mk2["posterUrl"].endswith("1776659285169.jpg"), "poster not linked to movie"

tids = {t["id"] for t in theaters}
assert "VOX-0041" in tids, "cinema code id not derived"
assert "VOX-0106" in tids
qasr = next(t for t in theaters if t["id"] == "VOX-0041")
assert qasr["name"] == "Al Qasr Mall" and qasr["city"] == "Riyadh", qasr
spot = next(t for t in theaters if t["id"] == "VOX-0058")
assert spot["name"] == "The Spot, Sheikh Jaber" and spot["city"] == "Riyadh", spot

# time conversion + linkage
s1 = next(s for s in showtimes if s["id"] == "VOX-0041-264342")
assert s1["time"] == "01:00", s1["time"]
assert s1["movieId"] == mk2["id"]
assert s1["theaterId"] == "VOX-0041"
assert s1["screenType"] == "Standard"
late = next(s for s in showtimes if s["id"] == "VOX-0101-39250")
assert late["time"] == "23:40", late["time"]          # 11:40pm
assert late["screenType"] == "Interstellar"           # bespoke Via Riyadh screen
imax = next(s for s in showtimes if s["id"] == "VOX-0106-68500")
assert imax["time"] == "00:15" and imax["screenType"] == "IMAX", imax

print("\nALL ASSERTIONS PASSED  ✓")
print(f"movies={len(movies)} theaters={len(theaters)} showtimes={len(showtimes)}")
