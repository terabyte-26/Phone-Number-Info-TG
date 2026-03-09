# Written by Hamza Farahat <farahat.hamza1@gmail.com>, 12/21/2025
# Contact me for more information:
# Contact Us: https://terabyte-26.com/quick-links/
# Telegram: @hamza_farahat or https://t.me/hamza_farahat
# WhatsApp: +212772177012

import logging
import random

from google import genai
from groq import Groq, Stream
from groq.types.chat import ChatCompletion, ChatCompletionChunk
from consts import API_KEYS, Models, Roles, Prompts

logger = logging.getLogger(__name__)


# ── Gemini (primary) ─────────────────────────────────────────────────────────

def get_gemini_response(message: str) -> str:
    """Call Google Gemini Flash to extract structured data."""
    client = genai.Client(api_key=API_KEYS.GEMINI_API_KEY)
    response = client.models.generate_content(
        model=Models.Gemini.FLASH_2_0,
        contents=Prompts.PROMPT_EXTRACTOR + message,
    )
    return response.text


# ── Groq (fallback) ──────────────────────────────────────────────────────────

def get_random_groq_api_key() -> str:
    return random.choice(API_KEYS.GROQ_API_LIST)


def get_groq_proposal(message: str) -> str:
    api_key: str = get_random_groq_api_key()
    client: Groq = Groq(api_key=api_key)

    chat_completion: ChatCompletion | Stream[ChatCompletionChunk] = client.chat.completions.create(
        messages=[
            {
                "role": Roles.USER,
                "content": Prompts.PROMPT_EXTRACTOR + message
            }
        ],
        model=Models.Groq.LLAMA_3_3_70,
    )

    return chat_completion.choices[0].message.content


# ── Unified caller: Gemini first, Groq fallback ─────────────────────────────

def get_groq_raw_response(message: str) -> str:
    """Try Gemini first, fall back to Groq if Gemini fails."""
    if API_KEYS.GEMINI_API_KEY:
        try:
            return get_gemini_response(message)
        except Exception as e:
            logger.warning(f"Gemini failed, falling back to Groq: {e}")

    return get_groq_proposal(message)
