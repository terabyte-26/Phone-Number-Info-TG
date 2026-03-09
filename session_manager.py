import asyncio
from pyrogram import Client

from consts import TelegramConfig
import database as db


async def generate_missing_sessions():
    """
    Scans MongoDB for live accounts missing a session_string.
    Prompts the user to log in (OTP/2FA) and saves the session string back to MongoDB.
    """
    print("\n--- 🔐 Starting Session Manager ---")

    accounts = db.get_accounts_by_mode("live")
    if not accounts:
        print("❌ No live accounts found in MongoDB.")
        return

    changes_made = False

    for account in accounts:
        phone    = account.get("phone")
        name     = account.get("name", phone)
        password = account.get("password")

        if account.get("session_string"):
            print(f"✅ Session already exists for {name} ({phone}). Skipping...")
            continue

        print(f"\n⚠️  No session for {name} ({phone}). Initialising login...")

        client = Client(
            name=name,
            api_id=TelegramConfig.API_ID,
            api_hash=TelegramConfig.API_HASH,
            phone_number=phone,
            password=password,
            in_memory=True,
        )

        try:
            await client.start()
            session_string = await client.export_session_string()
            await client.stop()

            db.update_session_string(phone, session_string)
            changes_made = True
            print(f"🎉 Session generated for {name} and saved to MongoDB.")

        except Exception as exc:
            print(f"❌ Failed for {name} ({phone}): {exc}")

    if changes_made:
        print("\n✅ Session generation complete. Sessions saved to MongoDB.")
    else:
        print("\n✅ All live accounts already have valid sessions.")


# Allow the file to be run directly from the terminal for manual setup
if __name__ == "__main__":
    asyncio.run(generate_missing_sessions())

