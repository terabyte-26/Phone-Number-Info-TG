# Written by Hamza Farahat <farahat.hamza1@gmail.com>, 12/21/2025
# Contact me for more information:
# Contact Us: https://terabyte-26.com/quick-links/
# Telegram: @hamza_farahat or https://t.me/hamza_farahat
# WhatsApp: +212772177012

import json
import random

from groq import Groq, Stream
from consts import API_KEYS, Models, Roles, Prompts
from groq.types.chat import ChatCompletion, ChatCompletionChunk


def get_random_groq_api_key() -> str:
    return random.choice(API_KEYS.GROQ_API_LIST)


def get_groq_proposal(message: str):

    api_key: str = get_random_groq_api_key()

    client: Groq = Groq(
        api_key=api_key,
    )

    chat_completion:  ChatCompletion | Stream[ChatCompletionChunk] = client.chat.completions.create(
        messages=[
            {
                "role": Roles.USER,
                "content": Prompts.PROMPT_EXTRACTOR + message
            }
        ],
        model=Models.Groq.LLAMA_3_3_70,
    )

    return chat_completion.choices[0].message.content


def get_groq_raw_response(message: str) -> str:
    """Wrapper for retry_extractor to call Groq and return raw string."""
    return get_groq_proposal(message)
