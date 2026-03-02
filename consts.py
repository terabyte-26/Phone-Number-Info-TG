# Written by Hamza Farahat <farahat.hamza1@gmail.com>, 12/21/2025
# Contact me for more information:
# Contact Us: https://terabyte-26.com/quick-links/
# Telegram: @hamza_farahat or https://t.me/hamza_farahat
# WhatsApp: +212772177012
import json
import os
from dotenv import load_dotenv

load_dotenv()

def load_sessions_from_json() -> list[str]:
    """Reads live_accounts.json and returns a list of valid session strings."""
    try:
        with open('live_accounts.json', 'r') as f:
            accounts = json.load(f)
            # Filter out any accounts that don't have a session_string yet
            return [acc['session_string'] for acc in accounts if acc.get('session_string')]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


class TelegramConfig(object):
    API_ID: int = int(os.getenv("API_ID"))
    API_HASH: str = os.getenv("API_HASH")
    PHONE_NUMBER: str = os.getenv("PHONE_NUMBER")
    SESSIONS: list[str] = load_sessions_from_json()


class API_KEYS(object):
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY")
    GROQ_API_KEY_1: str = os.getenv("GROQ_API_KEY_1")  # blackmorelouise01@gmail.com
    GROQ_API_KEY_2: str = os.getenv("GROQ_API_KEY_2")  # farahat.hamza199@gmail.com
    GROQ_API_KEY_3: str = os.getenv("GROQ_API_KEY_3")  # potato.motato247@gmail.com
    GROQ_API_KEY_4: str = os.getenv("GROQ_API_KEY_4")  # yasemintekir81@gmail.com
    GROQ_API_KEY_5: str = os.getenv("GROQ_API_KEY_5")  # tirs.bot1@gmail.com
    GROQ_API_KEY_6: str = os.getenv("GROQ_API_KEY_6")  # tringgr4@gmail.com
    GROQ_API_KEY_7: str = os.getenv("GROQ_API_KEY_7")  # dedeknana908@gmail.com
    GROQ_API_KEY_8: str = os.getenv("GROQ_API_KEY_8")  # leokeguer@gmail.com
    GROQ_API_KEY_9: str = os.getenv("GROQ_API_KEY_9")  # bopesmuer@gmail.com
    GROQ_API_KEY_10: str = os.getenv("GROQ_API_KEY_10")  # nebavere@gmail.com

    GROQ_API_LIST: list[str] = [
        GROQ_API_KEY_1,
        GROQ_API_KEY_2,
        GROQ_API_KEY_3,
    ]


class Models(object):
    class Groq(object):
        # Google models
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
