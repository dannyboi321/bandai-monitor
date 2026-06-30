# Bandai TCG+ One Piece Tournament Monitor

Checks bandai-tcg-plus.com every ~10 minutes for new One Piece Card Game
tournaments at your chosen California stores, and pings you on Discord the
moment a new one appears.

## ⚠️ Before this works: selectors need fixing

`scripts/monitor.py` was written without being able to inspect the live,
rendered version of bandai-tcg-plus.com (it's a JS app, and I could only see
the empty page shell from here). The CSS selectors in `scrape_tournaments()`
are placeholders based on common patterns — **they will very likely need
adjustment.** This is normal for scraping a site without a public API.

### How to fix the selectors (step 1: get real page data)

1. Clone this repo locally.
2. Install dependencies:
   ```
   pip install -r requirements.txt
   playwright install --with-deps chromium
   ```
3. Run the debug helper:
   ```
   python scripts/list_stores.py
   ```
4. This will likely fail or return nothing useful on the first try — that's
   expected. Open `debug_page_dump.html` (created automatically) in a text
   editor or browser to see the real rendered HTML.
5. Share that file's relevant section with Claude (or inspect it yourself)
   to find the real selectors for: the game-title selector, the
   region/state filter, and the event result cards (name, store, date,
   link). Update `scripts/monitor.py` accordingly.
6. Re-run `python scripts/list_stores.py` until it prints real tournament
   names and store names. Copy the exact store names it prints into
   `config.yml`.

Alternative: if at any point you can open browser DevTools → Network tab on
bandai-tcg-plus.com while performing a search, and copy the JSON API request
URL/response, share that — it lets us swap to a much simpler and faster
direct API call instead of browser automation.

## Setup once selectors are working

1. **Create a Discord webhook** (if you don't already have a server/channel
   for this):
   - In Discord: Server Settings → Integrations → Webhooks → New Webhook.
   - Copy the Webhook URL.
2. **Add it as a GitHub secret:**
   - In your repo: Settings → Secrets and variables → Actions → New
     repository secret.
   - Name: `DISCORD_WEBHOOK_URL`, Value: (paste the URL).
3. **Edit `config.yml`** with your real store names (from step above).
4. **Enable the workflow:** push this repo to GitHub, go to the Actions tab,
   and enable workflows if prompted. You can also trigger a manual test run
   anytime via Actions → "Bandai TCG+ Tournament Check" → "Run workflow".
5. Done — it will now run automatically every 10 minutes.

## Notes on timing

GitHub's free `cron` scheduler is "best effort," not exact — during high
platform load, runs can occasionally be delayed by several minutes. For
tournaments that fill in 10-15 minutes, this is a small but real risk. If
this becomes a problem, the fix is moving the script to a cheap VPS
(~$5/month) with a real system cron job, which has no such delay. The
script itself doesn't need to change for that move.

## Files

- `config.yml` — your filters (game, region, store allow-list)
- `scripts/monitor.py` — the main check-and-notify script
- `scripts/list_stores.py` — debug helper to find real store names/selectors
- `.github/workflows/check.yml` — the schedule definition
- `seen.json` — auto-updated memory of tournaments already notified about
