import os
import json
import asyncio
from pyrogram import Client

# Make sure this imports your updated TelegramConfig
from consts import TelegramConfig

ACCOUNTS_FILE = "live_accounts.json"


async def generate_missing_sessions():
    """
    Scans live_accounts.json for any accounts missing a session_string.
    Prompts the user to log in (OTP/2FA) and saves the session string directly back to the JSON.
    """
    print("\n--- 🔐 Starting Session Manager ---")

    # 1. Load the accounts
    try:
        with open(ACCOUNTS_FILE, "r") as f:
            accounts = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"❌ Error: Could not read {ACCOUNTS_FILE}. Make sure the file exists and is valid JSON.")
        return

    changes_made = False

    # 2. Iterate through each account
    for index, account in enumerate(accounts):
        phone = account.get("phone")
        name = account.get("name", f"Account_{index}")
        password = account.get("password")

        # If the session string already exists and is not empty/null, skip it
        if account.get("session_string"):
            print(f"✅ Session already exists for {name} ({phone}). Skipping...")
            continue

        print(f"\n⚠️ No session found for {name} ({phone}). Initializing login...")

        # 3. Create an in-memory Pyrogram client
        # We use in_memory=True so it doesn't create .session files on your disk
        client = Client(
            name=name,
            api_id=TelegramConfig.API_ID,
            api_hash=TelegramConfig.API_HASH,
            phone_number=phone,
            password=password,  # Pyrogram will use this if 2FA is enabled
            in_memory=True
        )

        try:
            # 4. Start the client (This will prompt you for the OTP in the terminal)
            await client.start()

            # 5. Export the session string
            session_string = await client.export_session_string()

            # 6. Save it to the dictionary
            account["session_string"] = session_string
            changes_made = True

            print(f"🎉 Successfully generated and captured session string for {name}!")

            # Stop the client safely before moving to the next one
            await client.stop()

            # 7. Write back to live_accounts.json IMMEDIATELY after each successful login
            # This ensures if the script crashes on account #5, you don't lose the sessions for #1-4
            with open(ACCOUNTS_FILE, "w") as f_out:
                json.dump(accounts, f_out, indent=4)

            print(f"💾 Saved {name}'s session to {ACCOUNTS_FILE}.")

        except Exception as e:
            print(f"❌ Failed to generate session for {name} ({phone}): {e}")
            continue

    if changes_made:
        print("\n✅ Session generation complete. All new sessions saved to live_accounts.json!")
    else:
        print("\n✅ All accounts already have valid sessions. Nothing to do.")


# Allow the file to be run directly from the terminal for manual setup
if __name__ == "__main__":
    asyncio.run(generate_missing_sessions())

