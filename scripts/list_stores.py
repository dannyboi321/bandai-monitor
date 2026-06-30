"""
Debug helper: dumps the rendered HTML of the event search page so you (or
Claude) can inspect the real DOM structure and fix the selectors in
monitor.py. Also attempts to print any store names it can find, to help you
fill in config.yml with exact matches.

Run manually with: DEBUG_MODE=true python scripts/list_stores.py
This script is the same as monitor.py but always dumps debug output and
never sends notifications, regardless of config.
"""

import os

os.environ["DEBUG_MODE"] = "true"
os.environ["DISCORD_WEBHOOK_URL"] = ""  # force-disable notifications

from monitor import load_config, scrape_tournaments  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402


def main():
    config = load_config()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        tournaments = scrape_tournaments(page, config)
        browser.close()

    print(f"\nFound {len(tournaments)} tournament(s):\n")
    stores = set()
    for t in tournaments:
        print(f"- {t['name']} | {t['store']} | {t['date']}")
        stores.add(t["store"])

    print("\nUnique store names found (copy exact spelling into config.yml):")
    for s in sorted(stores):
        print(f'  - "{s}"')


if __name__ == "__main__":
    main()
