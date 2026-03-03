# Written by Hamza Farahat <farahat.hamza1@gmail.com>
# Contact: https://terabyte-26.com/quick-links/

import re
import sys
import json
import asyncio
import logging

from dotenv import load_dotenv
from pyrogram import Client, filters

load_dotenv()

import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

ALL_ACCOUNTS_FILE = "all_accounts.json"

# Patterns ordered from most specific to most generic.
# Each pattern captures the OTP digits in group 1.
OTP_PATTERNS = [
    # Keyword before digits: "code: 12345", "OTP 4321", "verification code 987654"
    re.compile(r"(?i)(?:code|otp|verification|login|confirm|authenticate)[^\d]{0,30}(\d{4,8})"),
    # Digits before keyword: "12345 is your code", "654321 – your verification"
    re.compile(r"(?i)(\d{4,8})[^\d]{0,20}(?:is\s+your|your)\s+(?:code|otp|verification|login)"),
    # Entire message (or line) is just a number – Telegram itself sends these
    re.compile(r"(?m)^\s*(\d{4,8})\s*$"),
]


def load_account_by_name(name: str) -> dict | None:
    try:
        with open(ALL_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            accounts = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Could not load {ALL_ACCOUNTS_FILE}: {e}")
        return None

    for acc in accounts:
        if acc.get("name", "").strip().lower() == name.strip().lower():
            return acc

    return None


def extract_otp(text: str) -> str | None:
    for pattern in OTP_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


async def run_otp_listener(account_name: str) -> None:
    account = load_account_by_name(account_name)
    if not account:
        logger.error(f"No account named '{account_name}' found in {ALL_ACCOUNTS_FILE}.")
        return

    session_string = account.get("session_string")
    if not session_string:
        logger.error(f"Account '{account_name}' has no session_string – cannot connect.")
        return

    api_id = int(os.getenv("API_ID"))
    api_hash = os.getenv("API_HASH")

    logger.info(f"Account  : {account['name']} ({account.get('phone', 'unknown')})")
    logger.info("Starting Pyrogram client …")

    stop_event = asyncio.Event()

    client = Client(
        name=account_name,
        api_id=api_id,
        api_hash=api_hash,
        session_string=session_string,
        in_memory=True,
    )

    @client.on_message(filters.incoming & filters.private)
    async def on_message(_, message):
        text = (message.text or message.caption or "").strip()
        if not text:
            return

        sender_id = message.from_user.id if message.from_user else "unknown"
        logger.info(f"Message from {sender_id}: {text[:120]!r}")

        otp = extract_otp(text)
        if otp:
            logger.info("=" * 50)
            logger.info(f"OTP DETECTED  : {otp}")
            logger.info(f"Full message  : {text}")
            logger.info("=" * 50)
            stop_event.set()

    async with client:
        logger.info("Listening for incoming private messages … (press Ctrl+C to abort)")
        await stop_event.wait()

    logger.info("OTP captured. Script finished.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python otp_listener.py <account name>")
        print('       (wrap multi-word names in quotes, e.g. "Kalipora Kay")')
        sys.exit(1)

    name_arg = " ".join(sys.argv[1:])
    asyncio.run(run_otp_listener(name_arg))
