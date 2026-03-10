# Written by Hamza Farahat <farahat.hamza1@gmail.com>, 12/21/2025
# Contact me for more information:
# Contact Us: https://terabyte-26.com/quick-links/
# Telegram: @hamza_farahat or https://t.me/hamza_farahat
# WhatsApp: +212772177012
import os
from dotenv import load_dotenv

load_dotenv()


class TelegramConfig(object):
    API_ID: int = int(os.getenv("API_ID"))
    API_HASH: str = os.getenv("API_HASH")
    PHONE_NUMBER: str = os.getenv("PHONE_NUMBER")
    # Populated at startup from MongoDB via app._refresh_session_pool()
    SESSIONS: list[str] = []


# API keys are now stored in MongoDB — managed via /api-keys/dashboard
# On first startup, keys from .env (GROQ_API_KEY_1..10, GEMINI_API_KEY) are
# auto-migrated into the api_keys collection by database.migrate_api_keys_from_env()


class Models(object):
    class Gemini(object):
        FLASH_2_0: str = "gemini-2.0-flash"

    class Groq(object):
        LLAMA_3_3_70: str = "llama-3.3-70b-versatile"
        LLAMA_3_1_8: str = "llama-3.1-8b-instant"


class Roles(object):
    USER: str = "user"
    SYSTEM: str = "system"


class Prompts(object):
    PROMPT_EXTRACTOR: str = """
You are a high-precision data extraction engine. Your task is to parse unstructured security breach notifications into a valid JSON list of objects.

### Rules:
1. Output MUST be a valid JSON list of dictionaries.
2. Each dictionary represents a single person/entry found after the description.
3. Use the emoji-labeled text as keys (remove the emoji and the colon). 
4. If a field is repeated (like "Location" or "Email"), include it in the dictionary.
5. Do NOT include the introductory paragraph text in the dictionaries.
6. Provide ONLY the JSON. No preamble, no markdown code blocks, no explanation.

### Input Format Example:
[Source Name]
[Description Paragraph]
📩Email: user@example.com
👤Name: John Doe

### Output Format Example:
[
  {"Email": "user@example.com", "Name": "John Doe"}
]

### Message to Process:
""".strip()
