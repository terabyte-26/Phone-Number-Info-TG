# Written by Hamza Farahat <farahat.hamza1@gmail.com>, 1/29/2026
# Contact me for more information:
# Contact Us: https://terabyte-26.com/quick-links/
# Telegram: @hamza_farahat or https://t.me/hamza_farahat
# WhatsApp: +212772177012

import json
import os
from pyrogram import Client
from dotenv import set_key


async def generate_missing_sessions():
    api_id = int(os.getenv("API_ID"))
    api_hash = os.getenv("API_HASH")

    # Load account info
    with open("accounts.json", "r") as f:
        accounts = json.load(f)

    session_strings = []

    for acc in accounts:
        phone = acc["phone"]
        password = acc.get("password")

        print(f"\n--- Logging into: {phone} ---")
        # We use in_memory=True so it doesn't create .session files
        app = Client(f"session_{phone}", api_id, api_hash, in_memory=True)

        await app.connect()

        # Request Code
        sent_code = await app.send_code(phone)
        code = input(f"Enter the code sent to {phone}: ")

        try:
            await app.sign_in(phone, sent_code.phone_code_hash, code)
        except Exception as e:
            # Handle 2FA if password is provided
            if "SESSION_PASSWORD_NEEDED" in str(e) and password:
                await app.check_password(password)
            else:
                raise e

        string = await app.export_session_string()
        session_strings.append(string)
        print(f"✅ Session generated for {phone}")
        await app.disconnect()

    # Save to .env for future use
    combined_strings = ",".join(session_strings)
    set_key(".env", "SESSION_STRINGS", combined_strings)
    return session_strings