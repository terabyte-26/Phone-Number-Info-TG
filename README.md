# Phone Number Info TG

Flask + Pyrogram service for querying Telegram leak-check bots, plus a web dashboard to manage account pools (`live_accounts.json` and `all_accounts.json`).

Author: Hamza Farahat (<farahat.hamza1@gmail.com>)
Contact: https://terabyte-26.com/quick-links/ | Telegram: @hamza_farahat

## What This System Does

This project has two main parts:

1. API service
- Sends a phone query to a selected Telegram bot (`SML`, `WCB`, `AML`)
- Uses the currently active Telegram client session from `live_accounts.json`
- Extracts structured data from bot replies and returns JSON

2. Account dashboard
- Lets you manage live/all accounts in a dark web UI
- Add account via modal
- List rows by `name` + `phone`
- Open account details in a modal (eye button)
- Edit/delete account
- Manage paid subscriptions as `name -> date`
- Search filter by name or phone

---

## Table of Contents

- Architecture
- Repository Layout
- Requirements
- Setup
- Run
- Account Files and Data Format
- Dashboard Usage
- API Endpoints
- Session Rotation Logic
- Troubleshooting
- Security Notes

---

## Architecture

High-level flow for `/search_phone`:

1. Read bot state (`bot_state.json`) to know active session index
2. Get `TelegramConfig.SESSIONS` (loaded from `live_accounts.json`)
3. Validate request (`input`, `source`)
4. Send message to target Telegram bot via Pyrogram
5. Wait/poll for reply
6. Handle limits/errors
7. Parse/extract records with Groq + retry helper
8. Return JSON

If a rate-limit style message is detected, the service auto-switches to the next client session.

---

## Repository Layout

- `app.py` - Main Flask app (API + dashboard routes)
- `consts.py` - Environment config and session loading
- `session_manager.py` - Generates missing session strings for accounts
- `ai_helpers.py` - LLM extraction helper
- `plugins.py` - Retry/extraction helpers
- `templates/accounts_dashboard.html` - Dashboard page
- `static/css/accounts_dashboard.css` - Dashboard styles
- `static/js/accounts_dashboard.js` - Dashboard behavior
- `live_accounts.json` - Active session pool
- `all_accounts.json` - Full account inventory
- `bot_state.json` - Current active session index + switch history
- `app.log` - Rotating runtime logs

---

## Requirements

- Python 3.10+
- Telegram API credentials (`API_ID`, `API_HASH`)
- Valid Telegram accounts for your bot-calling pool
- Dependencies in `requirements.txt`

Install:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## Setup

Create a `.env` in project root:

```env
API_ID=123456
API_HASH=your_api_hash_here
PHONE_NUMBER=optional_default_phone
GROQ_API_KEY=optional
GROQ_API_KEY_1=optional
GROQ_API_KEY_2=optional
GROQ_API_KEY_3=optional
```

Notes:
- `API_ID` and `API_HASH` are required.
- `GROQ_API_KEY*` are used by extraction helpers.

---

## Run

Development run:

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

Default bind in current code:
- Host: `0.0.0.0`
- Port: `8080`

Open:
- API info: `http://127.0.0.1:8080/`
- Dashboard: `http://127.0.0.1:8080/accounts/dashboard`

---

## Account Files and Data Format

### `live_accounts.json`
Used for active Pyrogram session pool.

### `all_accounts.json`
Inventory/reference list for all accounts.

Each account object:

```json
{
  "name": "Account Name",
  "phone": "+15551234567",
  "password": null,
  "paid_subscription": {
    "sml": "2027-02-25",
    "another_plan": "2026-12-01"
  },
  "session_string": "...optional..."
}
```

Notes:
- `paid_subscription` is normalized as `{ subscription_name: "YYYY-MM-DD" }`.
- Legacy boolean subscription values are auto-migrated in dashboard route.
- `session_string` is required for an account to be usable for API requests.

---

## Dashboard Usage

Route: `GET /accounts/dashboard`

Features:

1. Search filter
- Filter rows by name or phone (live, client-side)

2. Add account
- Use `Add Account` button
- Modal form posts to `POST /accounts/add`
- Choose target: `live` or `all`

3. View/edit account details
- Click eye icon in row
- Details modal opens with full fields
- Save posts to `POST /accounts/edit/<target>/<index>`
- Delete posts to `POST /accounts/delete/<target>/<index>`

4. Subscriptions
- Add multiple subscriptions with name + date
- Stored in `paid_subscription` map

Behavior detail:
- Any change to `live_accounts.json` refreshes in-memory `TelegramConfig.SESSIONS`.

---

## API Endpoints

### `GET /`
Simple app info.

### `GET /search_phone`
Query params:
- `input` (required): phone/text to send
- `source` (required): one of `SML`, `WCB`, `AML`

Possible responses:
- `200`: list of extracted records
- `400`: invalid/missing input
- `429`: rate-limited / switched session
- `503`: bot currently busy
- `504`: timeout waiting for bot reply
- `500`: internal error

Example:

```powershell
curl "http://127.0.0.1:8080/search_phone?input=%2B447300823591&source=SML"
```

### `GET /bots_info`
Returns:
- active client session index
- total sessions
- switch history count
- available target bot map
- current processing lock state

### `GET /switch_session`
Switch active client session.

- Auto next: `/switch_session`
- Specific index: `/switch_session?index=2`

### `GET /fix`
Force-releases bot processing lock.

### Dashboard form routes
- `POST /accounts/add`
- `POST /accounts/edit/<target>/<int:index>`
- `POST /accounts/delete/<target>/<int:index>`

---

## Session Rotation Logic

State file: `bot_state.json`

Contains:
- `active_index`
- `last_switch_time`
- `switch_history[]`

When a limit message is detected during `/search_phone`, system:
1. Calls `switch_bot()`
2. Moves to next session index
3. Stores history in `bot_state.json`

Manual switching is available through `/switch_session`.

---

## Generating Missing Sessions

If `TelegramConfig.SESSIONS` is empty on startup, `startup_check()` runs `generate_missing_sessions()`.

You can run manually:

```powershell
.\.venv\Scripts\Activate.ps1
python session_manager.py
```

What it does:
- Reads `live_accounts.json`
- For accounts missing `session_string`, prompts Telegram login
- Exports session string and writes it back to `live_accounts.json`

---

## Troubleshooting

1. `No module named pyrogram`
- Install dependencies in your venv:
```powershell
pip install -r requirements.txt
```

2. `API_ID`/`API_HASH` errors
- Verify `.env` values and restart app.

3. Empty sessions / index errors
- Ensure at least one `live_accounts.json` entry has a valid `session_string`.
- Run `python session_manager.py` if needed.

4. Bot always busy (`503`)
- Use `/fix` once to release stale lock.

5. Dashboard updates but API still old behavior
- Live-account edits should refresh sessions automatically.
- If needed, restart app to clear stale runtime state.

---

## Security Notes

- Treat `session_string`, `.env`, and account JSON files as secrets.
- Do not commit real credentials/session values in public repos.
- This tool can process sensitive phone data; ensure legal basis and consent.
- Add auth/rate-limiting before exposing publicly.

---

## Recommended Next Improvements

1. Add authentication for dashboard and API routes.
2. Add tests for account migration and dashboard CRUD.
3. Add validation for subscription date format on backend.
4. Add API key protection and request rate-limiting.
