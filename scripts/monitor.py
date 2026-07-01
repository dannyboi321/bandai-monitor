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
    """Closes the News popup modal using JavaScript."""
    try:
        page.wait_for_selector(".modal", timeout=3000)
    except Exception:
        return

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
    """Logs into Bandai Namco ID."""
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
        page.wait_for_selector("text=Later", timeout=8000)
        page.click("text=Later")
        page.wait_for_load_state("networkidle")
    except Exception:
        pass

    print("Login flow completed.")


def scrape_tournaments(page, config):
    """
    Flow: Others > Store Search > Filter by Favorite Stores > Search >
    click 'Search for events at this store' for each favorited store >
    scrape event cards using real class names confirmed via DevTools.
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

    # --- Step 4: Others > Store Search ---
    try:
        page.click("text=Others", timeout=5000)
        page.wait_for_load_state("networkidle")
        page.click("text=Store Search", timeout=5000)
        page.wait_for_load_state("networkidle")
    except Exception as e:
        print(f"Could not navigate to Store Search: {e}")
    if DEBUG_MODE:
        page.screenshot(path="debug_4_store_search.png")

    # --- Step 5: Filter by Favorite Stores and Search ---
    try:
        page.check("input[type='checkbox']", timeout=3000)
    except Exception:
        try:
            page.click("label:has-text('Filter by Favorite Stores')", timeout=5000)
        except Exception as e:
            print(f"Could not check Favorite Stores filter: {e}")

    try:
        page.click("button:has-text('Search')", timeout=5000)
        page.wait_for_load_state("networkidle")
    except Exception as e:
        print(f"Could not click Search: {e}")
    if DEBUG_MODE:
        page.screenshot(path="debug_5_after_store_search.png")

    # --- Step 6: For each store click "Search for events at this store" ---
    results = []
    try:
        buttons = page.query_selector_all("text=Search for events at this store")
        count = len(buttons)
        print(f"Found {count} favorite store(s).")

        for i in range(count):
            btns = page.query_selector_all("text=Search for events at this store")
            if i >= len(btns):
                break
            btns[i].click()
            page.wait_for_load_state("networkidle")
            if DEBUG_MODE:
                page.screenshot(path=f"debug_store_{i}_events.png")

            # Real class names confirmed via DevTools inspection
            cards = page.query_selector_all("li.event-item")
            print(f"  Store {i}: found {len(cards)} event card(s).")

            for card in cards:
                try:
                    name_el = card.query_selector(".event-name-link")
                    name = name_el.inner_text().strip() if name_el else "Unknown"
                    store_el = card.query_selector("a[href*='organizer']")
                    store = store_el.inner_text().strip() if store_el else "Unknown"
                    date_el = card.query_selector(".event-date")
                    date = date_el.inner_text().strip() if date_el else "Unknown"
                    link_el = card.query_selector("a[href*='/event/']")
                    href = link_el.get_attribute("href") if link_el else ""
                    event_id = href.split("/event/")[-1].split("?")[0] if href else f"{name}-{date}"
                    results.append({
                        "id": event_id,
                        "name": name,
                        "store": store,
                        "date": date,
                        "url": "https://www.bandai-tcg-plus.com" + href if href and href.startswith("/") else href or BASE_URL,
                    })
                except Exception as e:
                    print(f"  Skipping card: {e}")

            page.go_back()
            page.wait_for_load_state("networkidle")

    except Exception as e:
        print(f"Error scraping store events: {e}")

    if DEBUG_MODE:
        DEBUG_DUMP.write_text(page.content(), encoding="utf-8")
        print(f"Debug mode: dumped rendered HTML to {DEBUG_DUMP}")

    return results


def main():
    config = load_config()
    seen = load_seen()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        tournaments = scrape_tournaments(page, config)
        browser.close()

    print(f"Scraped {len(tournaments)} total tournaments.")

    new_count = 0
    for t in tournaments:
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
