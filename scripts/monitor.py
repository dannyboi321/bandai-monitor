"""
Bandai TCG+ Tournament Monitor

Scrapes the One Piece Card Game tournament listings on bandai-tcg-plus.com,
filters to stores configured in config.yml, and sends a Discord notification
for any tournament not previously seen (tracked in seen.json).
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

BANDAI_EMAIL = os.environ.get("BANDAI_EMAIL")
BANDAI_PASSWORD = os.environ.get("BANDAI_PASSWORD")


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


def dismiss_cookie_banner(page):
    """Dismisses the OneTrust cookie consent banner."""
    try:
        page.click("#onetrust-accept-btn-handler", timeout=8000)
        page.wait_for_timeout(500)
    except Exception:
        print("No cookie consent banner found — may already be dismissed.")


def handle_language_select(page):
    """Handles the 'Select Language' popup that appears on first visit."""
    try:
        page.wait_for_selector("text=Select Language", timeout=8000)
    except Exception:
        print("No 'Select Language' popup appeared — may already be set.")
        return

    try:
        page.select_option("select#wpModal-country", label="United States of America")
    except Exception as e:
        print(f"Could not set Region: {e}")

    try:
        page.wait_for_function(
            "document.querySelector('#wpModal-gemeTitle') && "
            "!document.querySelector('#wpModal-gemeTitle').disabled",
            timeout=15000,
        )
        page.select_option("select#wpModal-gemeTitle", label="ONE PIECE CARD GAME (English)")
    except Exception as e:
        print(f"Could not set Game Title: {e}")

    try:
        page.check("input#agreeMessageCheckbox")
    except Exception as e:
        print(f"Could not check accept checkbox: {e}")

    try:
        page.click("text=Selection")
        page.wait_for_load_state("networkidle")
    except Exception as e:
        print(f"Could not click Selection button: {e}")


def close_news_popup(page):
    """Closes the 'News' popup modal if it appears.
    Uses JavaScript to forcibly remove it since clicking outside/Escape
    has proven unreliable in headless mode."""
    try:
        page.wait_for_selector(".modal", timeout=3000)
    except Exception:
        return  # no modal visible, nothing to do

    # First try clicking any button inside the modal (e.g. a close/OK button)
    try:
        page.evaluate("""
            const modal = document.querySelector('.modal');
            if (modal) {
                const buttons = modal.querySelectorAll('button, [role=button], .btn');
                if (buttons.length > 0) {
                    buttons[buttons.length - 1].click();
                }
            }
        """)
        page.wait_for_timeout(500)
        if not page.is_visible(".modal"):
            return
    except Exception:
        pass

    # Fallback: forcibly remove the modal via JavaScript
    try:
        page.evaluate("""
            const modal = document.querySelector('.modal');
            if (modal) modal.remove();
            const overlay = document.querySelector('.modalOverlay, .overlay, .backdrop');
            if (overlay) overlay.remove();
            document.body.style.overflow = 'auto';
        """)
        page.wait_for_timeout(300)
    except Exception:
        pass


def login(page):
    """
    Logs into Bandai Namco ID. Full flow based on the real site:
    1. Click 'Login' in the header
    2. Click 'Log In w/ Bandai Namco ID' in the modal
    3. Fill email/password on the bandainamcoid.com page, submit
    4. Skip the optional passkey prompt if it appears
    """
    if not BANDAI_EMAIL or not BANDAI_PASSWORD:
        print("No BANDAI_EMAIL/BANDAI_PASSWORD set — skipping login.")
        return

    try:
        page.click("text=Login", timeout=5000)
    except Exception:
        print("Could not find 'Login' button — page structure may differ.")
        return

    try:
        page.click("text=Log In w/ Bandai Namco ID", timeout=5000)
        page.wait_for_load_state("networkidle")
    except Exception as e:
        print(f"Could not click 'Log In w/ Bandai Namco ID': {e}")
        return

    try:
        page.fill("input[type='email'], input[name='email']", BANDAI_EMAIL)
        page.fill("input[type='password'], input[name='password']", BANDAI_PASSWORD)
        page.keyboard.press("Enter")
        page.wait_for_load_state("networkidle")
    except Exception as e:
        print(f"Login form fill/submit failed: {e}")
        return

    try:
        page.click("text=Later", timeout=4000)
        page.wait_for_load_state("networkidle")
    except Exception:
        pass

    print("Login flow completed.")


def scrape_tournaments(page, config):
    """
    Returns a list of dicts: [{"id": ..., "name": ..., "store": ...,
    "date": ..., "url": ...}, ...]
    """
    page.goto(BASE_URL, wait_until="networkidle")

    dismiss_cookie_banner(page)
    if DEBUG_MODE:
        page.screenshot(path="debug_0_after_cookie_dismiss.png")

    handle_language_select(page)
    if DEBUG_MODE:
        page.screenshot(path="debug_1_after_language.png")

    close_news_popup(page)
    if DEBUG_MODE:
        page.screenshot(path="debug_2_after_news_close.png")

    login(page)
    if DEBUG_MODE:
        page.screenshot(path="debug_3_after_login.png")

    try:
        page.click("text=Event Search", timeout=5000)
        page.wait_for_load_state("networkidle")
    except Exception:
        print("Could not find 'Event Search' link — page structure may differ.")
    if DEBUG_MODE:
        page.screenshot(path="debug_4_after_event_search_click.png")

    try:
        page.fill("input[name='area']", config.get("region", ""))
        page.keyboard.press("Enter")
        page.wait_for_load_state("networkidle")
    except Exception:
        print("Could not filter by region — page structure may differ (expected for now).")

    if DEBUG_MODE:
        DEBUG_DUMP.write_text(page.content(), encoding="utf-8")
        print(f"Debug mode: dumped rendered HTML to {DEBUG_DUMP}")

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
