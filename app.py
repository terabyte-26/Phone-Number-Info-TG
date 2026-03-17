# Written by Hamza Farahat <farahat.hamza1@gmail.com>, 12/4/2025
# Contact me for more information:
# Contact Us: https://terabyte-26.com/quick-links/
# Telegram: @hamza_farahat or https://t.me/hamza_farahat
# WhatsApp: +212772177012

import os
import re
import json
import time
import uuid
import asyncio
import datetime
import threading

from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired
from pyrogram.storage import MemoryStorage
from flask import Flask, request, jsonify, render_template, redirect, url_for, Response, stream_with_context, flash

from groq import RateLimitError
from ai_helpers import get_groq_raw_response, check_key_usage
from consts import TelegramConfig
from plugins import retry_extractor
import database as db

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


def _refresh_session_pool() -> None:
    """Load live account session strings from MongoDB into TelegramConfig.SESSIONS."""
    from consts import TelegramConfig
    TelegramConfig.SESSIONS = db.get_live_session_strings()


def startup_check():
    try:
        imported = db.migrate_from_json_if_empty()
        if imported:
            logger.info(f"One-time migration: imported {imported} accounts from JSON into MongoDB.")
    except Exception as exc:
        logger.warning(f"Could not run JSON migration: {exc}")

    try:
        imported = db.migrate_api_keys_from_env()
        if imported:
            logger.info(f"One-time migration: imported {imported} API keys from .env into MongoDB.")
    except Exception as exc:
        logger.warning(f"Could not run API key migration: {exc}")

    try:
        _refresh_session_pool()
        n = len(TelegramConfig.SESSIONS)
        if n:
            logger.info(f"{n} live session(s) loaded from MongoDB.")
        else:
            logger.warning(
                "No live sessions found in MongoDB. "
                "Add accounts with session strings via the dashboard."
            )
    except Exception as exc:
        logger.error(f"Failed to load sessions from MongoDB: {exc}")

    # Release any accounts stuck as under_use from a previous crash
    try:
        released = db.release_stale_accounts()
        if released:
            logger.info(f"Released {released} stale account(s) from previous run.")
    except Exception as exc:
        logger.warning(f"Could not release stale accounts: {exc}")




DEFAULT_SUBSCRIPTION_DATE = "2027-02-25"


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



# ── Interactive session generation ─────────────────────────────────────────

_session_jobs: dict[str, "SessionJob"] = {}


class SessionJob:
    def __init__(self, job_id: str, phone: str, name: str, password: str | None):
        self.job_id = job_id
        self.phone = phone
        self.name = name
        self.password = password
        self.logs: list[str] = []
        self.otp_event = threading.Event()
        self.cancel_event = threading.Event()
        self.otp_value: str | None = None
        self.otp_requests: int = 0   # increments every time OTP is needed (incl. retries)
        self.result: str | None = None
        self.error: str | None = None
        # status: 'running' | 'waiting_otp' | 'processing' | 'cancelled' | 'done' | 'error'
        self.status = "running"

    def log(self, msg: str) -> None:
        self.logs.append(msg)


def run_session_generation(job: SessionJob) -> None:
    """Runs in a dedicated thread with its own asyncio event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_generate_session_async(job))
    finally:
        loop.close()


async def _generate_session_async(job: SessionJob) -> None:
    client = Client(
        name=job.name or job.phone,
        api_id=TelegramConfig.API_ID,
        api_hash=TelegramConfig.API_HASH,
        in_memory=True,
    )

    async def wait_for_otp() -> bool:
        """Wait for OTP or cancel. Returns True if OTP received, False if cancelled/timed out."""
        deadline = time.time() + 180
        while time.time() < deadline:
            if job.cancel_event.is_set():
                return False
            if job.otp_event.is_set():
                return True
            await asyncio.sleep(0.3)
        return False

    try:
        job.log("Connecting to Telegram…")
        await client.connect()

        job.log(f"Sending verification code to {job.phone}…")
        sent_code = await client.send_code(job.phone)
        job.log("Code sent. Enter the OTP below.")

        signed_in = False
        while not signed_in:
            # Signal the UI to show the OTP input
            job.otp_requests += 1
            job.status = "waiting_otp"

            got = await wait_for_otp()

            if not got:
                if job.cancel_event.is_set():
                    job.log("Cancelled.")
                    job.status = "cancelled"
                else:
                    job.log("Timed out waiting for OTP (3 min limit).")
                    job.status = "error"
                    job.error = "OTP timeout"
                return

            otp = job.otp_value
            job.otp_event.clear()
            job.otp_value = None
            job.status = "processing"
            job.log("Signing in…")

            try:
                await client.sign_in(
                    phone_number=job.phone,
                    phone_code_hash=sent_code.phone_code_hash,
                    phone_code=otp,
                )
                signed_in = True

            except PhoneCodeInvalid:
                job.log("Incorrect code — please try again.")

            except PhoneCodeExpired:
                job.log("Code expired. Requesting a new code…")
                sent_code = await client.send_code(job.phone)
                job.log("New code sent.")

            except SessionPasswordNeeded:
                if not job.password:
                    raise Exception("2FA is enabled but no password was provided.")
                job.log("Two-factor authentication required. Verifying password…")
                await client.check_password(job.password)
                job.log("2FA verified.")
                signed_in = True

        session_string = await client.export_session_string()
        job.log("Session string exported successfully.")
        job.result = session_string
        job.status = "done"

    except Exception as exc:
        job.log(f"Error: {exc}")
        job.error = str(exc)
        job.status = "error"
    finally:
        if client.is_connected:
            await client.disconnect()


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(32))


# ── Session generation routes ───────────────────────────────────────────────

@app.route("/accounts/session/start", methods=["POST"])
def start_session_generation():
    phone    = (request.form.get("phone")    or "").strip()
    name     = (request.form.get("name")     or "").strip()
    password = (request.form.get("password") or "").strip() or None

    if not phone:
        return jsonify({"error": "Phone is required"}), 400

    job_id = str(uuid.uuid4())
    job = SessionJob(job_id, phone, name, password)
    _session_jobs[job_id] = job

    threading.Thread(target=run_session_generation, args=(job,), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/accounts/session/stream/<job_id>")
def session_stream(job_id: str):
    def generate():
        job = _session_jobs.get(job_id)
        if not job:
            yield f"data: {json.dumps({'type': 'error', 'msg': 'Job not found'})}\n\n"
            return

        sent_idx = 0
        last_otp_request = 0  # tracks which OTP request we've already prompted for

        def flush_logs():
            nonlocal sent_idx
            while sent_idx < len(job.logs):
                yield f"data: {json.dumps({'type': 'log', 'msg': job.logs[sent_idx]})}\n\n"
                sent_idx += 1

        while True:
            yield from flush_logs()

            # Prompt for OTP whenever the backend increments otp_requests (incl. retries)
            if job.otp_requests > last_otp_request:
                yield f"data: {json.dumps({'type': 'waiting_otp'})}\n\n"
                last_otp_request = job.otp_requests

            if job.status == "done":
                yield from flush_logs()
                yield f"data: {json.dumps({'type': 'done', 'session': job.result})}\n\n"
                return

            if job.status in ("error", "cancelled"):
                yield from flush_logs()
                yield f"data: {json.dumps({'type': job.status, 'msg': job.error or ''})}\n\n"
                return

            time.sleep(0.3)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/accounts/session/otp", methods=["POST"])
def submit_session_otp():
    job_id = (request.form.get("job_id") or "").strip()
    otp    = (request.form.get("otp")    or "").strip()

    job = _session_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    job.otp_value = otp
    job.otp_event.set()
    return jsonify({"status": "ok"})


@app.route("/accounts/session/cancel", methods=["POST"])
def cancel_session():
    job_id = (request.form.get("job_id") or "").strip()
    job = _session_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    job.cancel_event.set()
    return jsonify({"status": "ok"})


@app.route("/accounts/session/revoke", methods=["POST"])
def revoke_session():
    """Log out from Telegram using the stored session string, then clear it in MongoDB."""
    phone = (request.form.get("phone") or "").strip()
    if not phone:
        return jsonify({"error": "Phone is required"}), 400

    # Look up the account
    accounts = db.get_all_accounts()
    account = next((a for a in accounts if a.get("phone") == phone), None)
    if not account:
        return jsonify({"error": "Account not found"}), 404

    session_string = account.get("session_string")
    if not session_string:
        return jsonify({"error": "No session string to revoke"}), 400

    def do_revoke():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_revoke_session_async(session_string))
        finally:
            loop.close()

    try:
        result = do_revoke()
    except Exception as exc:
        logger.error(f"Session revoke failed for {phone}: {exc}")
        return jsonify({"error": f"Revoke failed: {exc}"}), 500

    # Clear session_string in MongoDB regardless of log_out result
    db.update_session_string(phone, "")
    _refresh_session_pool()
    logger.info(f"Session revoked and cleared for {phone}")

    return jsonify({"status": "ok", "detail": result})


async def _revoke_session_async(session_string: str) -> str:
    client = Client(
        name="revoke_temp",
        api_id=TelegramConfig.API_ID,
        api_hash=TelegramConfig.API_HASH,
        session_string=session_string,
        in_memory=True,
        no_updates=True,
    )
    try:
        await client.start()
        await client.log_out()
        return "Logged out from Telegram successfully"
    except Exception as exc:
        # Even if log_out fails (e.g. session already invalid), we still clear it
        logger.warning(f"log_out call failed: {exc}")
        return f"Session cleared locally (Telegram log_out failed: {exc})"
    finally:
        if client.is_connected:
            await client.disconnect()


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
    from flask import get_flashed_messages
    all_accounts  = db.get_all_accounts()
    live_accounts = [acc for acc in all_accounts if acc.get("mode") == "live"]
    flashes = get_flashed_messages(with_categories=True)
    return render_template(
        "accounts_dashboard.html",
        all_accounts=all_accounts,
        live_accounts=live_accounts,
        default_subscription_date=DEFAULT_SUBSCRIPTION_DATE,
        flashes=flashes,
    )


@app.route('/accounts/add', methods=['POST'])
def add_account():
    account, error = account_from_form(request.form)
    if error:
        flash(error, "error")
        return redirect(url_for("accounts_dashboard"))

    db.insert_account(account)
    _refresh_session_pool()
    flash("Account added successfully.", "success")
    return redirect(url_for("accounts_dashboard"))


@app.route('/accounts/edit/<account_id>', methods=['POST'])
def edit_account(account_id: str):
    account, error = account_from_form(request.form)
    if error:
        flash(error, "error")
        return redirect(url_for("accounts_dashboard"))

    try:
        db.replace_account(account_id, account)
    except Exception:
        flash("Account not found.", "error")
        return redirect(url_for("accounts_dashboard"))

    _refresh_session_pool()
    flash("Account updated successfully.", "success")
    return redirect(url_for("accounts_dashboard"))


@app.route('/accounts/delete/<account_id>', methods=['POST'])
def delete_account(account_id: str):
    try:
        db.delete_account(account_id)
    except Exception:
        flash("Account not found.", "error")
        return redirect(url_for("accounts_dashboard"))

    _refresh_session_pool()
    flash("Account deleted successfully.", "success")
    return redirect(url_for("accounts_dashboard"))


# ── API Keys Dashboard ────────────────────────────────────────────────────────

@app.route('/api-keys/dashboard', methods=['GET'])
def api_keys_dashboard():
    from flask import get_flashed_messages
    all_keys = db.get_all_api_keys()
    gemini_keys = [k for k in all_keys if k["provider"] == "gemini"]
    groq_keys = [k for k in all_keys if k["provider"] == "groq"]
    enabled_keys = [k for k in all_keys if k.get("enabled", True)]
    flashes = get_flashed_messages(with_categories=True)
    return render_template(
        "api_keys_dashboard.html",
        all_keys=all_keys,
        gemini_keys=gemini_keys,
        groq_keys=groq_keys,
        enabled_keys=enabled_keys,
        flashes=flashes,
    )


@app.route('/api-keys/add', methods=['POST'])
def add_api_key():
    provider = request.form.get("provider", "").strip().lower()
    label = request.form.get("label", "").strip()
    key = request.form.get("key", "").strip()

    if provider not in ("groq", "gemini"):
        flash("Invalid provider.", "error")
        return redirect(url_for("api_keys_dashboard"))
    if not key:
        flash("API key is required.", "error")
        return redirect(url_for("api_keys_dashboard"))

    db.insert_api_key({"provider": provider, "label": label, "key": key, "enabled": True})
    flash(f"{provider.capitalize()} key added successfully.", "success")
    return redirect(url_for("api_keys_dashboard"))


@app.route('/api-keys/edit/<key_id>', methods=['POST'])
def edit_api_key(key_id: str):
    provider = request.form.get("provider", "").strip().lower()
    label = request.form.get("label", "").strip()
    key = request.form.get("key", "").strip()

    if provider not in ("groq", "gemini"):
        flash("Invalid provider.", "error")
        return redirect(url_for("api_keys_dashboard"))
    if not key:
        flash("API key is required.", "error")
        return redirect(url_for("api_keys_dashboard"))

    db.update_api_key(key_id, {"provider": provider, "label": label, "key": key})
    flash("API key updated successfully.", "success")
    return redirect(url_for("api_keys_dashboard"))


@app.route('/api-keys/delete/<key_id>', methods=['POST'])
def delete_api_key(key_id: str):
    db.delete_api_key(key_id)
    flash("API key deleted.", "success")
    return redirect(url_for("api_keys_dashboard"))


@app.route('/api-keys/toggle/<key_id>', methods=['POST'])
def toggle_api_key(key_id: str):
    new_enabled = db.toggle_api_key(key_id)
    return jsonify({"status": "ok", "enabled": new_enabled})


@app.route('/api-keys/usage', methods=['GET'])
def api_keys_usage():
    """Stream live usage/quota checks in parallel via SSE."""
    import json as _json
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from queue import Queue

    def check_one(k):
        usage = check_key_usage(k["provider"], k["key"])
        usage["id"] = str(k["_id"])
        usage["provider"] = k["provider"]
        usage["label"] = k.get("label", "")
        return usage

    def generate():
        keys = db.get_all_api_keys()
        with ThreadPoolExecutor(max_workers=min(len(keys), 10)) as pool:
            futures = {pool.submit(check_one, k): k for k in keys}
            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception as e:
                    k = futures[future]
                    result = {"id": str(k["_id"]), "provider": k["provider"], "status": "error", "error": str(e)}
                yield f"data: {_json.dumps(result)}\n\n"
        yield "data: {\"done\": true}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


ENCRYPT_BOTS: dict[str: str]= {
    'SML': 'SocialMediaLeaksBOT',
    'WCB': 'whoose_contact_bot ',   # Daily limit 3
    'AML': 'ASocialMediaLeaksBot ', # Monthly fee (paid)
}


@app.route('/search_phone', methods=['GET'])
async def search_phone():
    # 1. Validate inputs
    message_text = request.args.get("input", "")
    source = request.args.get("source", "")
    use_backup = request.args.get("bkp", "0") == "1"

    if not message_text:
        return jsonify({"error": "Phone number is required"}), 400
    if not source:
        return jsonify({"error": "Bot username is required"}), 400

    bot_username = ENCRYPT_BOTS.get(source.upper())
    if not bot_username:
        return jsonify({"error": "Invalid bot source provided."}), 400

    # 2. Acquire an available account that has a subscription for this bot
    account_mode = "backup" if use_backup else "live"
    account = db.acquire_account(bot_source=source.lower(), mode=account_mode)
    if not account:
        logger.info(f"No available account with {source.upper()} subscription for '{message_text}'.")
        return jsonify({
            "status": "busy",
            "message": f"No available account with {source.upper()} subscription. All are busy or none configured."
        }), 503

    account_phone = account["_id"]
    current_session = account["session_string"]
    account_name = account.get("name", account_phone)

    # 3. Initialize Bot
    tg_bot = None

    try:
        tg_bot = Client(
            name=f"bot_{account_phone}",
            api_id=TelegramConfig.API_ID,
            api_hash=TelegramConfig.API_HASH,
            session_string=current_session,
            in_memory=True,
            no_updates=True,
        )

        await tg_bot.start()
        logger.info(f"Search: {message_text} via @{bot_username} (account: {account_name})")

        # 4. Send Message
        sent = await tg_bot.send_message(bot_username, message_text)

        # 5. Wait for Reply (Polling Loop)
        timeout_seconds = 40
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        found_reply = None

        while asyncio.get_event_loop().time() < deadline:
            async for msg in tg_bot.get_chat_history(bot_username, limit=10):
                if msg.id <= sent.id:
                    continue

                text = msg.text.lower() if msg.text else ""

                if "too many requests" in text or "tokens recover" in text or 'too frequent requests' in text:
                    logger.warning(f"Rate limit hit on account {account_name} ({account_phone})")
                    return jsonify({
                        "status": "rate_limited",
                        "message": "This account hit a rate limit. Please retry — another account will be used."
                    }), 429

                # Validation: Must be from the bot we messaged
                if not msg.from_user or not msg.from_user.is_bot:
                    continue
                if msg.from_user.username and msg.from_user.username.lower() != bot_username.lower():
                    continue

                # Ignore "Processing" status messages
                if 'the number of leaks' in text and 'number of results' in text:
                    continue

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
                    reported_total = int(page_text.split('\\')[-1])
                    total_pages = min(reported_total, 5)
                except (IndexError, ValueError):
                    total_pages = 1

            # Extraction Loop
            for current_page_idx in range(total_pages):
                logger.info(f"Processing page {current_page_idx + 1}/{total_pages} for {message_text}")

                try:
                    page_data = retry_extractor(get_groq_raw_response, found_reply.text, attempts=4)

                    if isinstance(page_data, list):
                        all_extracted_records.extend(page_data)
                    elif isinstance(page_data, dict):
                        all_extracted_records.append(page_data)

                    if current_page_idx < total_pages - 1:
                        await found_reply.click(2, 0)
                        await asyncio.sleep(1.5)
                        found_reply = await tg_bot.get_messages(chat_id=bot_username, message_ids=found_reply.id)

                except RateLimitError as e:
                    logger.warning(f"Groq API rate limit hit: {e}")
                    return jsonify({
                        "status": "groq_rate_limited",
                        "message": "AI extraction service is temporarily rate-limited. Please try again in a few minutes."
                    }), 429

                except Exception as e:
                    logger.exception(f"Error processing page {current_page_idx + 1}")
                    break

            return jsonify(all_extracted_records)

        else:
            return jsonify({"error": "No reply received from bot within timeout period."}), 504

    except RateLimitError as e:
        logger.warning(f"Groq API rate limit hit: {e}")
        return jsonify({
            "status": "groq_rate_limited",
            "message": "AI extraction service is temporarily rate-limited. Please try again in a few minutes."
        }), 429

    except Exception as e:
        logger.exception(f"Critical error in search_phone (account: {account_name})")
        return jsonify({"error": str(e)}), 500

    finally:
        if tg_bot and tg_bot.is_connected:
            await tg_bot.stop()

        db.release_account(account_phone)
        logger.info(f"Account {account_name} released.")


@app.route('/fix', methods=['GET'])
def fix_bot():
    """
    Release all accounts stuck as under_use (e.g. after a crash).
    Safe to call at any time.
    """
    released = db.release_stale_accounts()
    busy = db.get_busy_accounts()

    if released > 0:
        logger.warning(f"Force-released {released} stale account(s) via /fix endpoint.")

    return jsonify({
        "status": "success",
        "released_stale": released,
        "still_busy": [{"phone": a["_id"], "name": a.get("name", ""), "last_used": str(a.get("last_used", ""))} for a in busy],
    })


@app.route('/bots_info', methods=['GET'])
def bots_info():
    """
    Returns status of all live accounts and the target bots.
    """
    live_accounts = db.get_accounts_by_mode("live")
    busy_count = sum(1 for a in live_accounts if a.get("under_use"))
    with_session = [a for a in live_accounts if a.get("session_string")]

    return jsonify({
        "accounts": {
            "total_live": len(live_accounts),
            "with_session": len(with_session),
            "currently_busy": busy_count,
            "available": len(with_session) - busy_count,
            "busy_details": [
                {
                    "phone": a["_id"],
                    "name": a.get("name", ""),
                    "last_used": str(a.get("last_used", "")),
                }
                for a in live_accounts if a.get("under_use")
            ],
        },
        "target_bots": ENCRYPT_BOTS,
    })


@app.route('/switch_session', methods=['GET'])
def switch_session():
    """
    Legacy endpoint kept for compatibility.
    With DB-based account acquisition, session switching is automatic.
    """
    return jsonify({
        "status": "info",
        "message": "Session switching is now automatic. "
                   "Accounts are acquired on demand and released after each request.",
    })


if __name__ == "__main__":
    startup_check()
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
