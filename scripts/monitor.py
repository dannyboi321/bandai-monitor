"""
Bandai TCG+ Tournament Monitor

Scrapes the One Piece Card Game tournament listings on bandai-tcg-plus.com,
filters to stores configured in config.yml, and sends a Discord notification
for any tournament not previously seen (tracked in seen.json).

IMPORTANT: The CSS selectors below are best-effort placeholders based on
common patterns for this type of site. bandai-tcg-plus.com is a JS-rendered
single page app with no public API documentation, so the selectors almost
certainly need adjustment after the first real run. See README.md for the
"debug mode" instructions to capture the real page structure and fix them.
"""

import json
import os
import sys
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.bandai-tcg-plus.com/"
SEEN_FILE = Path("seen.json")
CONFIG_FILE = Path("config.yml")
DEBUG_DUMP = Path("debug_page_dump.html")

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
DEBUG_MODE = os.environ.get("DEBUG_MODE", "false").lower() == "true"


def load_config():
    with open(CONFIG_FILE, "r") as f:
        return yaml.safe_load(f)


def load_seen():
    if SEEN_FILE.exists():
        with open(SEEN_FILE, "r") as f:
            return json.load(f)
    return {}


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(seen, f, indent=2, ensure_ascii=False)


def send_discord_notification(message: str):
    if not DISCORD_WEBHOOK_URL:
        print("No DISCORD_WEBHOOK_URL set — skipping notification. Message was:")
        print(message)
        return
    import urllib.request

    payload = json.dumps({"content": message}).encode("utf-8")
    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        print(f"Failed to send Discord notification: {e}", file=sys.stderr)


def scrape_tournaments(page, config):
    """
    Returns a list of dicts: [{"id": ..., "name": ..., "store": ...,
    "date": ..., "url": ...}, ...]

    PLACEHOLDER LOGIC — needs real selectors once we inspect the live site.
    """
    page.goto(BASE_URL, wait_until="networkidle")

    # --- Step 1: select the game title (One Piece Card Game) ---
    try:
        page.click("text=One Piece", timeout=5000)
    except Exception:
        print("Could not click 'One Piece' selector — page structure may differ.")

    # --- Step 2: navigate to event search ---
    try:
        page.click("text=Search Events", timeout=5000)
    except Exception:
        print("Could not find 'Search Events' link — page structure may differ.")

    # --- Step 3: filter by region/state (California) ---
    try:
        page.fill("input[name='area']", config.get("region", ""))
        page.keyboard.press("Enter")
        page.wait_for_load_state("networkidle")
    except Exception:
        print("Could not filter by region — page structure may differ.")

    if DEBUG_MODE:
        DEBUG_DUMP.write_text(page.content())
        print(f"Debug mode: dumped rendered HTML to {DEBUG_DUMP}")

    # --- Step 4: scrape result cards ---
    cards = page.query_selector_all(".event-card")
    results = []
    for card in cards:
        try:
            name = card.query_selector(".event-name").inner_text().strip()
            store = card.query_selector(".event-store").inner_text().strip()
            date = card.query_selector(".event-date").inner_text().strip()
            link_el = card.query_selector("a")
            href = link_el.get_attribute("href") if link_el else ""
            event_id = href.split("/")[-1] if href else f"{name}-{store}-{date}"
            results.append(
                {
                    "id": event_id,
                    "name": name,
                    "store": store,
                    "date": date,
                    "url": BASE_URL.rstrip("/") + href if href else BASE_URL,
                }
            )
        except Exception as e:
            print(f"Skipping a card due to parse error: {e}")
    return results


def main():
    config = load_config()
    wanted_stores = {s.strip().lower() for s in config.get("stores", []) if s and not str(s).startswith("#")}
    seen = load_seen()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        tournaments = scrape_tournaments(page, config)
        browser.close()

    print(f"Scraped {len(tournaments)} total tournaments before store filtering.")

    new_count = 0
    for t in tournaments:
        if wanted_stores and t["store"].strip().lower() not in wanted_stores:
            continue

        if t["id"] not in seen:
            new_count += 1
            message = (
                f"🆕 **New One Piece Tournament!**\n"
                f"**{t['name']}**\n"
                f"📍 {t['store']}\n"
                f"📅 {t['date']}\n"
                f"{t['url']}"
            )
            send_discord_notification(message)
            seen[t["id"]] = t

    save_seen(seen)
    print(f"Done. {new_count} new tournament(s) found and notified.")


if __name__ == "__main__":
    main()
