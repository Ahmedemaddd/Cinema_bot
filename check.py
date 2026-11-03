import json, os, re, time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

STATE = Path("booking_state.json")
CINEMAS = {"City Centre Alexandria": "city-centre-alexandria", "City Centre Almaza": "city-centre-almaza", "Mall of Egypt": "mall-of-egypt"}
ROOT = "https://egy.voxcinemas.com/showtimes?c="
TODAY = datetime.now(ZoneInfo("Africa/Cairo")).date()
state = json.loads(STATE.read_text()) if STATE.exists() else {"keys": []}
seen = set(state.get("keys", []))
found, failures = [], []
options = webdriver.ChromeOptions()
for arg in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"):
    options.add_argument(arg)
driver = webdriver.Chrome(options=options)
driver.set_page_load_timeout(30)

def load(url):
    for _ in range(3):
        try: driver.get(url)
        except TimeoutException: pass
        try:
            WebDriverWait(driver, 15).until(lambda d: d.find_elements(By.CSS_SELECTOR, "article.movie-compare"))
            return True
        except TimeoutException: time.sleep(2)
    return False

try:
    for cinema, slug in CINEMAS.items():
        base = ROOT + slug
        if not load(base):
            failures.append(cinema)
            continue
        days = {TODAY}
        for link in driver.find_elements(By.CSS_SELECTOR, "nav.date-filter li a[href]"):
            m = re.search(r"[?&]d=(\d{8})", link.get_attribute("href") or "")
            if m:
                try:
                    d = datetime.strptime(m.group(1), "%Y%m%d").date()
                    if d >= TODAY: days.add(d)
                except ValueError: pass
        for day in sorted(days):
            url = base if day == TODAY else base + "&d=" + day.strftime("%Y%m%d")
            if not load(url):
                failures.append(cinema + " " + day.isoformat())
                continue
            for article in driver.find_elements(By.CSS_SELECTOR, "article.movie-compare"):
                title = re.sub(r"[^a-z0-9]", "", article.find_element(By.CSS_SELECTOR, "h2").text.casefold())
                if "avengersdoomsday" not in title or "infinityvision" not in title: continue
                for hall in article.find_elements(By.CSS_SELECTOR, "div.dates ol.showtimes > li"):
                    try: hall_name = hall.find_element(By.TAG_NAME, "strong").text.strip() or "Standard"
                    except Exception: hall_name = "Standard"
                    for item in hall.find_elements(By.CSS_SELECTOR, "ol > li"):
                        link = item.find_element(By.CSS_SELECTOR, "a.showtime")
                        href = link.get_attribute("href")
                        if href:
                            key = f"{slug}|{day.isoformat()}|{item.get_attribute('data-id') or href}"
                            if key not in seen: found.append((key, cinema, day.strftime("%a %d %b %Y"), hall_name, link.text.strip(), href))
            time.sleep(.3)
finally: driver.quit()

groups = defaultdict(list)
for slot in found: groups[(slot[1], slot[2])].append(slot)
for (cinema, day), slots in groups.items():
    lines = ["Avengers: Doomsday (Infinity Vision) — VOX", cinema + " | " + day]
    lines += [f"{s[3]} — {s[4]}: {s[5]}" for s in slots]
    r = requests.post("https://api.telegram.org/bot" + os.environ["TOKEN"] + "/sendMessage", data={"chat_id": os.environ["CHAT_ID"], "text": "\n".join(lines)}, timeout=30)
    r.raise_for_status()
    if not r.json().get("ok"): raise RuntimeError("Telegram rejected message")
    seen.update(s[0] for s in slots)
STATE.write_text(json.dumps({"keys": sorted(seen)}, indent=2) + "\n")
print(f"Sent {len(groups)} new notification(s)." if groups else "No new bookings.")
if failures: raise SystemExit("Could not check: " + ", ".join(failures))
