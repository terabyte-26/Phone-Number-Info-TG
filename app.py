# Written by Hamza Farahat <farahat.hamza1@gmail.com>, 12/4/2025
# Contact me for more information:
# Contact Us: https://terabyte-26.com/quick-links/
# Telegram: @hamza_farahat or https://t.me/hamza_farahat
# WhatsApp: +212772177012

import os
import re
import json
import asyncio
import datetime
import threading

from pyrogram import Client
from pyrogram.storage import MemoryStorage
from flask import Flask, request, jsonify, render_template, redirect, url_for

from ai_helpers import get_groq_raw_response
from consts import TelegramConfig
from plugins import retry_extractor
from session_manager import generate_missing_sessions

import logging
from logging.handlers import RotatingFileHandler

# --- ROBUST LOGGING CONFIGURATION ---
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
log_file = 'app.log'

# Explicitly set encoding='utf-8' to handle emojis and special characters
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=5*1024*1024,
    backupCount=5,
    encoding='utf-8'
)
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)

# For the console handler, we use a 'replace' error handler
# so it doesn't crash if the terminal doesn't support an emoji
import sys
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
console_handler.setLevel(logging.INFO)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)


def startup_check():
    # Reload from consts to ensure we have the latest data
    from consts import TelegramConfig

    if not TelegramConfig.SESSIONS:
        logger.info("No valid session_string found in live_accounts.json. Starting automatic setup...")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(generate_missing_sessions())
    else:
        logger.info(f"✅ {len(TelegramConfig.SESSIONS)} Sessions loaded from live_accounts.json.")




STATE_FILE = "bot_state.json"
LIVE_ACCOUNTS_FILE = "live_accounts.json"
BACKUP_PLAN_FILE = "backup_plan_accounts.json"
ALL_ACCOUNTS_FILE = "all_accounts.json"
ALL_ACCOUNTS_BACKUP_FILE = "all_accounts_backup.json"
DEFAULT_SUBSCRIPTION_DATE = "2027-02-25"


def load_accounts(file_path: str) -> list[dict]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_accounts(file_path: str, accounts: list[dict]) -> None:
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(accounts, f, indent=4, ensure_ascii=False)


def normalize_paid_subscriptions(raw_value) -> dict[str, str]:
    subscriptions = {}

    if isinstance(raw_value, bool):
        if raw_value:
            subscriptions["sml"] = DEFAULT_SUBSCRIPTION_DATE
        return subscriptions

    if isinstance(raw_value, dict):
        for key, value in raw_value.items():
            sub_name = str(key).strip().lower()
            if not sub_name:
                continue

            if isinstance(value, bool):
                if value:
                    subscriptions[sub_name] = DEFAULT_SUBSCRIPTION_DATE
            else:
                sub_date = str(value).strip()
                if sub_date:
                    subscriptions[sub_name] = sub_date
        return subscriptions

    if isinstance(raw_value, list):
        for item in raw_value:
            if not isinstance(item, dict):
                continue
            sub_name = str(item.get("name", "")).strip().lower()
            sub_date = str(item.get("date", "")).strip()
            if sub_name and sub_date:
                subscriptions[sub_name] = sub_date
        return subscriptions

    return subscriptions


def migrate_accounts_file(file_path: str) -> list[dict]:
    accounts = load_accounts(file_path)
    changed = False

    for account in accounts:
        current = account.get("paid_subscription")
        normalized = normalize_paid_subscriptions(current)
        if current != normalized:
            account["paid_subscription"] = normalized
            changed = True

    if changed:
        save_accounts(file_path, accounts)

    return accounts


def sync_account_files(all_accs: list[dict] | None = None) -> None:
    """Rebuild all derived account files from all_accounts.json and refresh
    the in-memory session pool.

    File responsibilities:
    - live_accounts.json        → accounts with mode == 'live'   (used by the bot)
    - backup_plan_accounts.json → accounts with mode == 'backup' (standby pool)
    - all_accounts_backup.json  → full safety copy of all_accounts.json
    """
    if all_accs is None:
        all_accs = load_accounts(ALL_ACCOUNTS_FILE)

    live_accs   = [acc for acc in all_accs if acc.get("mode") == "live"]
    backup_accs = [acc for acc in all_accs if acc.get("mode") == "backup"]

    save_accounts(LIVE_ACCOUNTS_FILE,     live_accs)
    save_accounts(BACKUP_PLAN_FILE,       backup_accs)
    save_accounts(ALL_ACCOUNTS_BACKUP_FILE, all_accs)   # safety copy

    from consts import TelegramConfig
    TelegramConfig.SESSIONS = [
        acc["session_string"] for acc in live_accs if acc.get("session_string")
    ]


def ensure_unified_accounts() -> list[dict]:
    """One-time-safe migration that makes all_accounts.json the single source of
    truth, then returns the up-to-date list.

    What it does:
    1. Merges accounts present only in live_accounts.json or backup_plan_accounts.json
       into all_accounts.json with the correct mode stamp.
    2. Stamps a ``mode`` field ('live' | 'backup') on any account that lacks one,
       using live_accounts.json / backup_plan_accounts.json as the hint.
    3. Normalises ``paid_subscription`` on every account.
    """
    all_accs    = load_accounts(ALL_ACCOUNTS_FILE)
    live_accs   = load_accounts(LIVE_ACCOUNTS_FILE)
    backup_accs = load_accounts(BACKUP_PLAN_FILE)

    live_phones   = {acc.get("phone") for acc in live_accs   if acc.get("phone")}
    backup_phones = {acc.get("phone") for acc in backup_accs if acc.get("phone")}
    all_phones    = {acc.get("phone") for acc in all_accs    if acc.get("phone")}

    changed = False

    # 1a. Pull in accounts that exist only in live_accounts.json
    for acc in live_accs:
        phone = acc.get("phone")
        if phone and phone not in all_phones:
            entry = dict(acc)
            entry["mode"] = "live"
            all_accs.append(entry)
            all_phones.add(phone)
            changed = True

    # 1b. Pull in accounts that exist only in backup_plan_accounts.json
    for acc in backup_accs:
        phone = acc.get("phone")
        if phone and phone not in all_phones:
            entry = dict(acc)
            entry["mode"] = "backup"
            all_accs.append(entry)
            all_phones.add(phone)
            changed = True

    # 2 & 3. Stamp mode + normalise subscriptions
    for acc in all_accs:
        if "mode" not in acc:
            phone = acc.get("phone")
            if phone in live_phones:
                acc["mode"] = "live"
            elif phone in backup_phones:
                acc["mode"] = "backup"
            else:
                acc["mode"] = "backup"
            changed = True
        current = acc.get("paid_subscription")
        normalised = normalize_paid_subscriptions(current)
        if current != normalised:
            acc["paid_subscription"] = normalised
            changed = True

    if changed:
        save_accounts(ALL_ACCOUNTS_FILE, all_accs)

    return all_accs


def account_from_form(form) -> tuple[dict | None, str | None]:
    name = (form.get("name") or "").strip()
    phone = (form.get("phone") or "").strip()
    password = (form.get("password") or "").strip() or None
    session_string = (form.get("session_string") or "").strip() or None
    subscriptions_raw = (form.get("subscriptions_json") or "").strip()
    mode = (form.get("mode") or "backup").strip().lower()
    if mode not in ("live", "backup"):
        mode = "backup"

    if not name:
        return None, "Name is required."
    if not phone:
        return None, "Phone is required."

    subscriptions = {}
    if subscriptions_raw:
        try:
            parsed_subscriptions = json.loads(subscriptions_raw)
            if not isinstance(parsed_subscriptions, list):
                return None, "Subscriptions payload is invalid."
            for item in parsed_subscriptions:
                if not isinstance(item, dict):
                    continue
                sub_name = str(item.get("name", "")).strip().lower()
                sub_date = str(item.get("date", "")).strip()
                if sub_name and sub_date:
                    subscriptions[sub_name] = sub_date
        except json.JSONDecodeError:
            return None, "Subscriptions payload is invalid."

    # Backward compatibility for legacy checkbox posts.
    if form.get("paid_sml") == "on" and "sml" not in subscriptions:
        subscriptions["sml"] = DEFAULT_SUBSCRIPTION_DATE

    account = {
        "name": name,
        "phone": phone,
        "password": password,
        "paid_subscription": subscriptions,
        "mode": mode,
    }
    if session_string:
        account["session_string"] = session_string

    return account, None


def get_bot_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"active_index": 0, "last_switch_time": None, "switch_history": []}


def switch_bot(target_index=None):
    state = get_bot_state()
    # Safely default to 0 if active_index isn't found
    old_index = state.get("active_index", 0)

    # Dynamically determine the total number of Pyrogram sessions available
    from consts import TelegramConfig
    total_sessions = len(TelegramConfig.SESSIONS)

    if target_index is not None:
        new_index = int(target_index)
    else:
        # Cycle through all available indexes: 0 -> 1 -> 2 -> 0 -> 1 ...
        new_index = (old_index + 1) % total_sessions

    now = datetime.datetime.now().isoformat()
    state["active_index"] = new_index
    state["last_switch_time"] = now

    # Ensure switch_history key exists to prevent KeyError
    if "switch_history" not in state:
        state["switch_history"] = []

    state["switch_history"].append({
        "from_bot": old_index,
        "to_bot": new_index,
        "timestamp": now
    })

    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)

    logger.warning(f"🔄 SWITCH TRIGGERED: Bot {old_index} -> Bot {new_index}")
    return new_index


app = Flask(__name__)


# Define your parsing function
def parse_bot_reply(text: str) -> list[dict]:
    """
    Parses bot replies into a list of dictionaries.
    Handles multiple records in one message and captures the source header.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    records = []
    current_record = {}
    current_source = None  # Tracks headers like 'PureIncubation.com'

    # Regex to find "Label: Value" lines
    # Captures the label (Group 1) and value (Group 2), ignoring leading emojis
    field_pattern = re.compile(r'^[^\w]*([^:]+):\s*(.*)$')

    for line in lines:
        match = field_pattern.match(line)

        # Heuristic: Valid keys are usually short (< 50 chars).
        # If a line matches the pattern but the "key" is a long sentence, it's likely description text.
        is_valid_field = False
        if match and len(match.group(1)) < 50:
            is_valid_field = True

        if is_valid_field:
            # --- It is a Field (e.g., "Email: example@com") ---
            raw_label = match.group(1).strip()
            value = match.group(2).strip()

            # Clean key: "The name of the company" -> "the_name_of_the_company"
            clean_key = re.sub(r'[^\w\s]', '', raw_label).strip().lower().replace(' ', '_')

            # CRITICAL: If this key already exists in the current_record,
            # it means we have started a NEW record block (e.g. a second "email").
            if clean_key in current_record:
                if current_source:
                    current_record["source_header"] = current_source
                records.append(current_record)
                current_record = {}  # Reset for the new record

            current_record[clean_key] = value

        else:
            # --- It is NOT a Field (Header or Description) ---

            # Heuristic: Short non-field lines are likely Headers/Sources.
            # Long non-field lines are likely description paragraphs (ignore them).
            if len(line) < 60:
                # If we hit a new Header but have pending data, save the previous record first.
                if current_record:
                    if current_source:
                        current_record["source_header"] = current_source
                    records.append(current_record)
                    current_record = {}

                # Update the current source context (e.g. "🐣PureIncubation.com")
                current_source = line

            # Note: We intentionally ignore long description lines here to keep the dict clean.

    # Append the last collected record after the loop finishes
    if current_record:
        if current_source:
            current_record["source_header"] = current_source
        records.append(current_record)

    return records


# Simple Home Route
@app.route('/')
def home():
    app_info = {
        "app_name": "Phone Search Bot",
        "description": "This app retrieves phone number information via a bot.",
        "version": "1.0",
        "status": "Running",
    }
    return jsonify(app_info)


@app.route('/accounts/dashboard', methods=['GET'])
def accounts_dashboard():
    all_accounts = ensure_unified_accounts()
    sync_account_files(all_accounts)
    live_accounts = [acc for acc in all_accounts if acc.get("mode") == "live"]
    return render_template(
        "accounts_dashboard.html",
        all_accounts=all_accounts,
        live_accounts=live_accounts,
        default_subscription_date=DEFAULT_SUBSCRIPTION_DATE,
        message=request.args.get("message"),
        error=request.args.get("error"),
    )


@app.route('/accounts/add', methods=['POST'])
def add_account():
    account, error = account_from_form(request.form)
    if error:
        return redirect(url_for("accounts_dashboard", error=error))

    all_accs = load_accounts(ALL_ACCOUNTS_FILE)
    all_accs.append(account)
    save_accounts(ALL_ACCOUNTS_FILE, all_accs)
    sync_account_files(all_accs)

    return redirect(url_for("accounts_dashboard", message="Account added successfully."))


@app.route('/accounts/edit/<int:index>', methods=['POST'])
def edit_account(index: int):
    all_accs = load_accounts(ALL_ACCOUNTS_FILE)
    if index < 0 or index >= len(all_accs):
        return redirect(url_for("accounts_dashboard", error="Invalid account index."))

    account, error = account_from_form(request.form)
    if error:
        return redirect(url_for("accounts_dashboard", error=error))

    all_accs[index] = account
    save_accounts(ALL_ACCOUNTS_FILE, all_accs)
    sync_account_files(all_accs)

    return redirect(url_for("accounts_dashboard", message="Account updated successfully."))


@app.route('/accounts/delete/<int:index>', methods=['POST'])
def delete_account(index: int):
    all_accs = load_accounts(ALL_ACCOUNTS_FILE)
    if index < 0 or index >= len(all_accs):
        return redirect(url_for("accounts_dashboard", error="Invalid account index."))

    all_accs.pop(index)
    save_accounts(ALL_ACCOUNTS_FILE, all_accs)
    sync_account_files(all_accs)

    return redirect(url_for("accounts_dashboard", message="Account deleted successfully."))


ENCRYPT_BOTS: dict[str: str]= {
    'SML': 'SocialMediaLeaksBOT',
    'WCB': 'whoose_contact_bot ',   # Daily limit 3
    'AML': 'ASocialMediaLeaksBot ', # Monthly fee (paid)
}

# Threading lock — only one request is served at a time.
# Any concurrent request gets an immediate "busy" response; no queuing, no waiting.
_bot_lock = threading.Lock()


# Flask route to handle GET requests
# app.py

@app.route('/search_phone', methods=['GET'])
async def search_phone():
    # 1. Validate inputs BEFORE acquiring the lock so bad requests fail fast
    message_text = request.args.get("input", "")
    source = request.args.get("source", "")

    if not message_text:
        return jsonify({"error": "Phone number is required"}), 400
    if not source:
        return jsonify({"error": "Bot username is required"}), 400

    bot_username = ENCRYPT_BOTS.get(source.upper())
    if not bot_username:
        return jsonify({"error": "Invalid bot source provided."}), 400

    # 2. Try to acquire the lock without blocking — if already taken, respond busy immediately
    if not _bot_lock.acquire(blocking=False):
        logger.info(f"Bot busy — rejecting request for '{message_text}' immediately.")
        return jsonify({
            "status": "busy",
            "message": "The bot is currently processing another request. Please try again in a few seconds."
        }), 503

    state = get_bot_state()
    current_session = TelegramConfig.SESSIONS[state["active_index"]]

    # 3. Initialize Bot
    tg_bot = None

    try:

        # Initialize Client with Memory Storage (Fixes "Database Locked")
        tg_bot = Client(
            name=f"bot_instance_{state['active_index']}",
            api_id=TelegramConfig.API_ID,
            api_hash=TelegramConfig.API_HASH,
            session_string=current_session,
            in_memory=True,
            no_updates=True,
        )

        await tg_bot.start()
        logger.info(f"🚀 Starting search: {message_text} via @{bot_username}")

        # 4. Send Message
        sent = await tg_bot.send_message(bot_username, message_text)

        # 5. Wait for Reply (Polling Loop)
        timeout_seconds = 40
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        found_reply = None

        while asyncio.get_event_loop().time() < deadline:
            # Check last 10 messages for a new reply
            async for msg in tg_bot.get_chat_history(bot_username, limit=10):
                # Ignore old messages (older than our sent message)


                if msg.id <= sent.id: continue

                text = msg.text.lower() if msg.text else ""

                if "too many requests" in text or "tokens recover" in text or 'too frequent requests' in text:
                    logger.error(f"❌ Rate limit hit on account index {state['active_index']}")
                    switch_bot()
                    return jsonify({
                        "status": "switched",
                        "message": "Primary bot limit reached. Switching to secondary. Please retry your request."
                    }), 429

                # Validation: Must be from the bot we messaged
                if not msg.from_user or not msg.from_user.is_bot:
                    continue
                if msg.from_user.username and msg.from_user.username.lower() != bot_username.lower():
                    continue

                # Ignore "Processing" status messages
                if 'the number of leaks' in text and 'number of results' in text:
                    continue

                # Handle Rate Limits
                if 'too frequent requests' in text:
                    return jsonify({"error": "Too many requests sent to the bot. Please try again later."}), 429

                found_reply = msg
                break

            if found_reply:
                break

            await asyncio.sleep(1)

        # 6. Process the Reply
        if found_reply:
            if "no results found" in found_reply.text.lower():
                return jsonify({"phone_not_found": True, "message": "No results found."})

            all_extracted_records = []

            # Calculate Pages (Multi-page logic)
            total_pages = 1
            if found_reply.reply_markup and len(found_reply.reply_markup.inline_keyboard) >= 2:
                try:
                    page_text = found_reply.reply_markup.inline_keyboard[0][1].text
                    reported_total = int(page_text.split('\\')[-1])  # Handles "1\9" format
                    total_pages = min(reported_total, 5)  # Cap at 5 pages
                except (IndexError, ValueError):
                    total_pages = 1

            # Extraction Loop
            for current_page_idx in range(total_pages):
                logger.info(f"Processing page {current_page_idx + 1}/{total_pages} for {message_text}")

                try:
                    # Extract Data using Groq/Regex
                    page_data = retry_extractor(get_groq_raw_response, found_reply.text, attempts=4)

                    if isinstance(page_data, list):
                        all_extracted_records.extend(page_data)
                    elif isinstance(page_data, dict):
                        all_extracted_records.append(page_data)

                    # Navigate to Next Page
                    if current_page_idx < total_pages - 1:
                        await found_reply.click(2, 0)  # Click "Next"
                        await asyncio.sleep(1.5)  # Wait for edit

                        # Refresh message object
                        found_reply = await tg_bot.get_messages(chat_id=bot_username, message_ids=found_reply.id)

                except Exception as e:
                    logger.exception(f"Error processing page {current_page_idx + 1}")
                    break

            return jsonify(all_extracted_records)

        else:
            return jsonify({"error": "No reply received from bot within timeout period."}), 504

    except Exception as e:
        logger.exception("🔥 Critical error in search_phone route")
        return jsonify({"error": str(e)}), 500

    finally:
        # 7. Safe Cleanup
        if tg_bot and tg_bot.is_connected:
            await tg_bot.stop()

        logger.info("Bot lock released.")
        _bot_lock.release()


@app.route('/fix', methods=['GET'])
def fix_bot():
    """
    Forcibly releases the bot lock if it is currently held (e.g. after a crash).
    Safe to call at any time — returns whether the lock was actually released.
    """
    if _bot_lock.locked():
        _bot_lock.release()
        logger.warning("Bot lock forcibly released via /fix endpoint.")
        return jsonify({
            "status": "success",
            "message": "Bot lock was held and has been forcibly released."
        })

    return jsonify({
        "status": "success",
        "message": "Bot was not locked — nothing to release."
    })


@app.route('/bots_info', methods=['GET'])
def bots_info():
    """
    Returns details about the active Pyrogram session (sender)
    and the available target bots (receivers).
    """
    state = get_bot_state()
    total_sessions = len(TelegramConfig.SESSIONS)

    return jsonify({
        "client_sessions": {
            "active_index": state["active_index"],
            "total_available": total_sessions,
            "last_switch_time": state.get("last_switch_time"),
            "switch_history_count": len(state.get("switch_history", []))
        },
        "target_bots_available": ENCRYPT_BOTS,
        "system_status": {
            "is_processing_request": _bot_lock.locked()
        }
    })


@app.route('/switch_session', methods=['GET'])
def switch_session():
    """
    Switches the active Pyrogram session.
    Pass ?index=X to switch to a specific session index.
    If no index is passed, it toggles to the next one automatically.
    """
    # Prevent switching if the bot is currently in the middle of a request
    if _bot_lock.locked():
        return jsonify({
            "error": "Cannot switch sessions while the bot is actively processing a search."
        }), 409

    target = request.args.get('index')
    total_sessions = len(TelegramConfig.SESSIONS)

    try:
        if target is not None:
            target_idx = int(target)
            if target_idx < 0 or target_idx >= total_sessions:
                return jsonify({
                    "error": f"Invalid index. Must be between 0 and {total_sessions - 1}"
                }), 400
            new_index = switch_bot(target_index=target_idx)
        else:
            new_index = switch_bot()  # Default toggle behavior

        return jsonify({
            "status": "success",
            "message": f"Successfully switched to client session index {new_index}",
            "active_index": new_index
        })
    except ValueError:
        return jsonify({"error": "Index parameter must be a valid integer."}), 400


if __name__ == "__main__":
    startup_check()
    app.run(debug=True, host="0.0.0.0", port=8080)
