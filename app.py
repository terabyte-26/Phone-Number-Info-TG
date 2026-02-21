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

from pyrogram import Client
from pyrogram.storage import MemoryStorage
from flask import Flask, request, jsonify

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
    # Only run if SESSION_STRINGS is empty or missing in .env
    if not os.getenv("SESSION_STRINGS"):
        logger.info("No sessions found. Starting automatic setup...")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(generate_missing_sessions())
    else:
        logger.info("✅ Sessions loaded from environment.")




STATE_FILE = "bot_state.json"


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


ENCRYPT_BOTS: dict[str: str]= {
    'SML': 'SocialMediaLeaksBOT',
    'WCB': 'whoose_contact_bot ',   # Daily limit 3
    'AML': 'ASocialMediaLeaksBot ', # Monthly fee (paid)
}

IS_BOT_RUNNING: bool = False


# Flask route to handle GET requests
# app.py

@app.route('/search_phone', methods=['GET'])
async def search_phone():
    global IS_BOT_RUNNING

    # 1. Check if bot is busy
    if IS_BOT_RUNNING:
        return jsonify({
            "status": "busy",
            "message": "The bot is currently processing another request. Please try again in a few seconds."
        }), 503

    state = get_bot_state()
    current_session = TelegramConfig.SESSIONS[state["active_index"]]

    # 2. Validate Inputs
    message_text = request.args.get("input", "")
    source = request.args.get("source", "")

    if not message_text:
        return jsonify({"error": "Phone number is required"}), 400
    if not source:
        return jsonify({"error": "Bot username is required"}), 400

    bot_username = ENCRYPT_BOTS.get(source.upper())
    if not bot_username:
        return jsonify({"error": "Invalid bot source provided."}), 400

    # 3. Initialize Bot
    tg_bot = None

    try:
        IS_BOT_RUNNING = True

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

        logger.info("Releasing bot lock...")
        IS_BOT_RUNNING = False


@app.route('/fix', methods=['GET'])
def fix_bot():
    """
    Resets the internal busy lock.
    (No need to stop Pyrogram here as the main route handles cleanup safely now).
    """
    global IS_BOT_RUNNING
    IS_BOT_RUNNING = False
    return jsonify({
        "status": "success",
        "message": "Bot lock has been forcibly released."
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
            "is_processing_request": IS_BOT_RUNNING
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
    if IS_BOT_RUNNING:
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
