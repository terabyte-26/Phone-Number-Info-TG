# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
# Development
python app.py

# Production
gunicorn app:app

# Generate missing session strings (interactive — prompts for OTP/2FA)
python session_manager.py

# Listen for OTP codes on a specific account
python otp_listener.py "<account name>"
```

The app runs on `0.0.0.0:8080`.

## Environment Setup

Requires a `.env` file with:
- `MONGODB_URI` — MongoDB Atlas connection string (`mongodb+srv://user:pass@cluster.mongodb.net/`)
- `MONGODB_DB_NAME` — database name (default: `phone_info_bot`)
- `API_ID`, `API_HASH` — Telegram app credentials
- `PHONE_NUMBER` — optional default phone
- `GROQ_API_KEY_1` through `GROQ_API_KEY_10` — Groq API keys for LLM extraction

## Architecture

### Data Flow

MongoDB is the single source of truth (`database.py` is the data-access layer). Two collections:
- **`accounts`** — all accounts with `mode: "live" | "backup"`, `under_use: bool`, `last_used: datetime`. Unique index on `phone`.
- **`bot_state`** — single document (`_id: "singleton"`) tracking switch history (legacy, kept for reference).

`TelegramConfig.SESSIONS` (in `consts.py`) starts empty and is populated at startup by `_refresh_session_pool()`, which queries live accounts with non-empty `session_string`. It is refreshed after every add/edit/delete.

On first startup, if the accounts collection is empty and `all_accounts.json` exists, `database.migrate_from_json_if_empty()` auto-imports it (one-time migration).

### Request Lifecycle (`/search_phone`)

1. `db.acquire_account()` atomically finds an available live account (not `under_use`) and marks it busy (503 if all busy)
2. Initialize an in-memory Pyrogram client with the acquired account's `session_string`
3. Send a message to the target bot (`SML`, `WCB`, or `AML`)
4. Poll for a reply with 40s timeout
5. On rate-limit detection → return 429 (next request will automatically use a different account)
6. Parse reply with regex (`parse_bot_reply()`), then extract structured JSON via Groq LLM (`retry_extractor` → `get_groq_raw_response`)
7. Handle multi-page results (up to 5 pages) by clicking the "Next" inline button
8. `db.release_account()` marks account as free, return JSON array of records

Multiple requests can be served concurrently using different accounts. Stale locks (>2 min) are auto-released.

### Target Bots

```python
ENCRYPT_BOTS = {
    'SML': 'SocialMediaLeaksBOT',
    'WCB': 'whoose_contact_bot',   # Daily limit: 3
    'AML': 'ASocialMediaLeaksBot', # Monthly paid
}
```

### Account Acquisition

Each account document has `under_use` (bool) and `last_used` (datetime). `db.acquire_account()` atomically finds the least-recently-used available account via `findOneAndUpdate`. `db.release_account()` marks it free after the request completes. Accounts stuck as `under_use` for >2 minutes are auto-released (crash recovery). Multiple concurrent requests are supported using different accounts.

### LLM Extraction

`retry_extractor()` in `plugins.py` calls `get_groq_raw_response()` up to 4 times, retrying on JSON parse failure (0.5s delay). Uses `llama-3.3-70b-versatile` with a system prompt that instructs the model to output only a JSON list, parsing emoji-labeled fields from raw bot replies.

### Account Data Format

```json
{
  "name": "Account Name",
  "phone": "+15551234567",
  "password": null,
  "paid_subscription": {"sml": "2027-02-25"},
  "mode": "live",
  "session_string": "...",
  "under_use": false,
  "last_used": "2026-03-08T12:00:00Z"
}
```

`paid_subscription` is normalized on every sync to `{bot_name: "YYYY-MM-DD"}`. Legacy boolean and list formats are auto-migrated by `normalize_paid_subscriptions()`.

## Key API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/search_phone?input=<phone>&source=SML\|WCB\|AML` | GET | Main query endpoint |
| `/bots_info` | GET | Session pool status |
| `/switch_session[?index=N]` | GET | Manual session rotation |
| `/fix` | GET | Force-release processing lock |
| `/accounts/dashboard` | GET | Account management UI |
| `/accounts/add` | POST | Add account |
| `/accounts/edit/<account_id>` | POST | Edit account (MongoDB `_id` string) |
| `/accounts/delete/<account_id>` | POST | Delete account (MongoDB `_id` string) |
| `/accounts/session/start` | POST | Start interactive session generation (phone, name, password) |
| `/accounts/session/stream/<job_id>` | GET | SSE stream of terminal output |
| `/accounts/session/otp` | POST | Submit OTP code during session generation |

## Dashboard UI

- `templates/accounts_dashboard.html` — Jinja2 template with inline SVG icon macros
- `static/css/accounts_dashboard.css` — dark theme styles
- `static/js/accounts_dashboard.js` — client-side search filtering and modal logic

Subscriptions are passed from the form as a JSON string `[{name, date}, ...]` and parsed server-side. Toast alerts are triggered by flash messages.
