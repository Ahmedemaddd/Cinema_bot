import json
import os
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

MOVIE_URL = "https://egy.voxcinemas.com/movies/avengers-doomsday-infinity-vision"
STATE_FILE = Path("booking_state.json")
CINEMAS = {
    "City Centre Alexandria",
    "City Centre Almaza",
    "Mall of Egypt",
}

response = requests.get(
    MOVIE_URL,
    timeout=30,
    headers={"User-Agent": "Mozilla/5.0 (compatible; VOXBookingChecker/1.0)"},
)
response.raise_for_status()
soup = BeautifulSoup(response.text, "html.parser")

# Collect actual booking links under each cinema heading.
bookings = {}
for heading in soup.find_all(["h2", "h3"]):
    cinema = " ".join(heading.stripped_strings)
    if cinema not in CINEMAS:
        continue

    cinema_bookings = {}
    for item in heading.find_all_next(["h2", "h3", "a"]):
        if item.name in ("h2", "h3"):
            break
        href = item.get("href", "")
        if "/booking/" in href:
            showtime = " ".join(item.stripped_strings)
            cinema_bookings[urljoin(MOVIE_URL, href)] = showtime

    if cinema_bookings:
        bookings[cinema] = cinema_bookings

state = {"seen_bookings": {}}
if STATE_FILE.exists():
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
seen = state.get("seen_bookings", {})
new_bookings = {}
for cinema, showtimes in bookings.items():
    known_links = set(seen.get(cinema, []))
    fresh = {link: time for link, time in showtimes.items() if link not in known_links}
    if fresh:
        new_bookings[cinema] = fresh

if new_bookings:
    lines = ["Avengers: Doomsday booking is available on VOX Cinemas Egypt:", ""]
    for cinema, showtimes in new_bookings.items():
        lines.append(cinema + ":")
        for link, time in showtimes.items():
            lines.append("- " + time + ": " + link)
    telegram = requests.post(
        "https://api.telegram.org/bot" + os.environ["TOKEN"] + "/sendMessage",
        data={"chat_id": os.environ["CHAT_ID"], "text": "\n".join(lines)},
        timeout=30,
    )
    telegram.raise_for_status()
    print("New booking links found; Telegram notification sent.")
else:
    print("No new booking links found.")

# Keep every link ever seen so a link that disappears and returns does not spam you.
for cinema, showtimes in bookings.items():
    old_links = set(seen.get(cinema, []))
    old_links.update(showtimes)
    seen[cinema] = sorted(old_links)
STATE_FILE.write_text(
    json.dumps({"seen_bookings": seen}, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
