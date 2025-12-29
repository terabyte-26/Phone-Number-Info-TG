# Written by Hamza Farahat <farahat.hamza1@gmail.com>, 12/4/2025
# Contact me for more information:
# Contact Us: https://terabyte-26.com/quick-links/
# Telegram: @hamza_farahat or https://t.me/hamza_farahat
# WhatsApp: +212772177012

import re

import time
import json
import asyncio

from pyrogram import Client
from flask import Flask, request, jsonify

from ai_helpers import get_groq_raw_response
from consts import TelegramConfig
from plugins import retry_extractor

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
@app.route('/search_phone', methods=['GET'])
async def search_phone():

    global IS_BOT_RUNNING

    # 2. Check if bot is busy before doing anything
    if IS_BOT_RUNNING:
        return jsonify({
            "status": "busy",
            "message": "The bot is currently processing another request. Please try again in a few seconds."
        }), 503

    message_text: str | None = request.args.get("input", "")
    source: str | None = request.args.get("source", "")

    if not message_text:
        return jsonify({"error": "Phone number is required"}), 400

    if not source:
        return jsonify({"error": "Bot username is required"}), 400

    bot_username: str | None = ENCRYPT_BOTS.get(source.upper())

    if not bot_username:
        return jsonify({"error": "Invalid bot source provided."}), 400

    timeout_seconds: int = 40

    # Asyncio event loop for pyrogram client

    # async with tg_bot:
    try:

        # 3. Lock the bot
        IS_BOT_RUNNING = True

        tg_bot = Client(
            "my_session",
            api_id=TelegramConfig.API_ID,
            api_hash=TelegramConfig.API_HASH,
            phone_number=TelegramConfig.PHONE_NUMBER,
        )

        # Ensure client is connected (using the global instance)
        if not tg_bot.is_connected:
            print("Starting Telegram client...")
            await tg_bot.start()

        sent = await tg_bot.send_message(bot_username, message_text)

        timeout_seconds = 40
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        found_reply = None

        # await app.answer_inline_query()
        print(f"Sent to @{source}: {message_text}")

        # deadline = time.time() + timeout_seconds
        print(f"Waiting for reply (timeout = {timeout_seconds}s)...")

        # while time.time() < deadline:
        while asyncio.get_event_loop().time() < deadline:
            async for msg in tg_bot.get_chat_history(bot_username, limit=10):
                if msg.id <= sent.id:
                    continue

                if not msg.from_user or not msg.from_user.is_bot:
                    continue

                if msg.from_user.username and msg.from_user.username.lower() != bot_username.lower():
                    continue

                if 'the number of leaks' in msg.text.lower() and 'number of results' in msg.text.lower():
                    continue

                if 'too frequent requests' in msg.text.lower():

                    await tg_bot.stop()
                    return jsonify({"error": "Too many requests sent to the bot. Please try again later."}), 429

                found_reply = msg
                break
            if found_reply: break
            await asyncio.sleep(1)
        

        if found_reply:
            # 1. IMMEDIATE CHECK FOR "NOT FOUND"
            if "no results found" in found_reply.text.lower():
                return jsonify({"phone_not_found": True, "message": "No results found."})

            all_extracted_records = []

            # 2. CALCULATE TOTAL PAGES
            total_pages = 1  # Default if only one row exists

            # Check if there are multiple rows of buttons (indicating multiple pages)
            print("buttons rows count", len(found_reply.reply_markup.inline_keyboard))
            if found_reply.reply_markup and len(found_reply.reply_markup.inline_keyboard) >= 2:
                try:
                    # Get text from Row 1 (index 0), Button 2 (index 1) -> e.g., "1/9"
                    page_text = found_reply.reply_markup.inline_keyboard[0][1].text
                    print("page_text", page_text)
                    # Split by "/" and get the second number
                    reported_total = int(page_text.split('\\')[-1])
                    print("reported_total", reported_total)

                    total_pages = min(reported_total, 5)
                except (IndexError, ValueError):
                    total_pages = 1

                print(f"Total pages detected: {total_pages}")

            # 3. NAVIGATION LOOP
            for current_page_idx in range(total_pages):
                print(f"Processing page {current_page_idx + 1}...")

                try:
                    # Use retry_extractor to get clean JSON from Groq
                    page_data = retry_extractor(get_groq_raw_response, found_reply.text, attempts=4)

                    if isinstance(page_data, list):
                        all_extracted_records.extend(page_data)
                    elif isinstance(page_data, dict):
                        all_extracted_records.append(page_data)

                    # Navigate to the next page if we aren't at the end
                    if current_page_idx < total_pages - 1:
                        # Click the 'Next' button (Row 3, Col 1 based on your click(2, 0) logic)
                        await found_reply.click(2, 0)
                        await asyncio.sleep(1)  # Wait for bot to edit message

                        # Refresh message to get new text for next loop iteration
                        found_reply = await tg_bot.get_messages(chat_id=bot_username, message_ids=found_reply.id)

                except Exception as e:
                    print(f"Error processing page {current_page_idx + 1}: {e}")
                    break

            await tg_bot.stop()
            return jsonify(all_extracted_records)

        else:
            await tg_bot.stop()
            return jsonify({"error": "No reply received from bot within timeout period."}), 504

    except Exception as e:

        try:
            await tg_bot.stop()
        except:
            pass

        return jsonify({"error": str(e)}), 500

    finally:
        print("Releasing bot lock...")
        IS_BOT_RUNNING = False


@app.route('/fix', methods=['GET'])
async def fix_bot():
    """
    Forcefully resets the bot status and attempts to disconnect any
    hanging Pyrogram sessions to clear SQLite locks.
    """
    global IS_BOT_RUNNING
    results = []

    try:
        # 1. Reset the Global Lock
        if IS_BOT_RUNNING:
            IS_BOT_RUNNING = False
            results.append("Global lock 'IS_BOT_RUNNING' has been reset to False.")
        else:
            results.append("Global lock was already False.")

        # 2. Force Stop Pyrogram Client
        # We initialize a temporary client instance to target the same session file
        temp_bot = Client(
            "my_session",
            api_id=TelegramConfig.API_ID,
            api_hash=TelegramConfig.API_HASH,
        )

        if temp_bot.is_connected:
            await temp_bot.stop()
            results.append("Active Pyrogram session forcefully stopped.")
        else:
            # Sometimes is_connected is False but the .session file is still locked.
            # Attempting a stop() anyway can help clear internal asyncio tasks.
            try:
                await temp_bot.stop()
                results.append("Pyrogram cleanup signal sent.")
            except:
                results.append("No active session detected to stop.")

        return jsonify({
            "status": "success",
            "actions_taken": results,
            "message": "System reset successfully. You can try /search_phone again."
        }), 200

    except Exception as e:
        return jsonify({
            "status": "partial_error",
            "error": str(e),
            "message": "Manual intervention may be required if the .session file is still locked."
        }), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)
