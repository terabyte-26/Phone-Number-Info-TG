# Written by Hamza Farahat <farahat.hamza1@gmail.com>, 12/4/2025
# Contact me for more information:
# Contact Us: https://terabyte-26.com/quick-links/
# Telegram: @hamza_farahat or https://t.me/hamza_farahat
# WhatsApp: +212772177012

import asyncio
import json
import time
from flask import Flask, request, jsonify
from pyrogram import Client
import re

app = Flask(__name__)


# Define your parsing function
def parse_bot_reply(text: str) -> dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    result = {}
    telephones = []
    i = 0
    n = len(lines)

    # Company and description
    if i < n:
        company_line = lines[i]
        company = re.sub(r'^[^\w]*', '', company_line).strip()
        if company:
            result["company"] = company
        i += 1

    # Parsing labels and values
    field_map = {
        "Email": "email",
        "Telephone": "telephones",
        "Last activity": "last_activity",
        "The date of registration": "registration_date",
        "Adres": "address",
        "Postal code": "postal_code",
        "Full name": "full_name",
        "Type of document": "document_type",
        "Passport number": "passport_number",
        "Type": "type",
        "Region": "region",
        "Status": "status",
        "Location": "location",
    }

    for j in range(i, n):
        line = lines[j]
        m = re.match(r'^[^\w]*([^:]+):\s*(.*)$', line)
        if not m:
            continue
        raw_label = m.group(1).strip()
        value = m.group(2).strip()

        key = field_map.get(raw_label)
        if key is None:
            result[raw_label] = value
        elif key == "telephones":
            telephones.append(value)
        else:
            result[key] = value

    if telephones:
        result["telephones"] = telephones

    return result


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


# Flask route to handle GET requests
@app.route('/search_phone', methods=['GET'])
def search_phone():

    message_text: str | None = request.args.get("phone_number", "")
    bot_username: str | None = request.args.get("bot_username", "")

    if not message_text:
        return jsonify({"error": "Phone number is required"}), 400

    if not bot_username:
        return jsonify({"error": "Bot username is required"}), 400

    timeout_seconds = 30
    poll_interval = 1.5

    # Asyncio event loop for pyrogram client
    async def main():
        api_id = 25243470
        api_hash = "059f256e00aac153ef3c35a9559c3efa"
        phone_number = "+447300823591"  # Your phone number

        app = Client(
            "userbot_session",
            api_id=api_id,
            api_hash=api_hash,
            phone_number=phone_number,
        )

        async with app:
            sent = await app.send_message(bot_username, message_text)
            print(f"Sent to @{bot_username}: {message_text}")

            deadline = time.time() + timeout_seconds
            print(f"Waiting for reply (timeout = {timeout_seconds}s)...")

            while time.time() < deadline:
                found_reply = None
                async for msg in app.get_chat_history(bot_username, limit=10):
                    if msg.id <= sent.id:
                        continue

                    if not msg.from_user or not msg.from_user.is_bot:
                        continue

                    if msg.from_user.username and msg.from_user.username.lower() != bot_username.lower():
                        continue

                    try:
                        if 'email' not in msg.text.lower() and 'telephone' not in msg.text.lower():
                            continue
                    except:
                        break

                    found_reply = msg
                    break

                if found_reply:
                    parsed = parse_bot_reply(found_reply.text)
                    return jsonify(parsed)

                await asyncio.sleep(poll_interval)

            return jsonify({"error": "Timeout: no reply received from the bot."})

    return asyncio.run(main())

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
