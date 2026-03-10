# Written by Hamza Farahat <farahat.hamza1@gmail.com>, 12/21/2025
# Contact me for more information:
# Contact Us: https://terabyte-26.com/quick-links/
# Telegram: @hamza_farahat or https://t.me/hamza_farahat
# WhatsApp: +212772177012

import logging
import random

from google import genai
from groq import Groq
from consts import Models, Prompts
import database as db

logger = logging.getLogger(__name__)


# ── Usage checker — queries the actual provider APIs ─────────────────────────

def _parse_groq_429(error_msg: str) -> dict:
    """Extract daily token usage from a Groq 429 error message."""
    import re
    result = {"status": "rate_limited"}
    # Parse: Limit 100000, Used 99960, Requested 833
    m = re.search(r'Limit (\d+),\s*Used (\d+)', error_msg)
    if m:
        limit = int(m.group(1))
        used = int(m.group(2))
        result["limit_tokens"] = limit
        result["remaining_tokens"] = max(0, limit - used)
        result["used_tokens"] = used
    # Parse: Please try again in 11m25.15s
    m2 = re.search(r'try again in ([^.]+\.[^\s]*s|[^.]+s)', error_msg)
    if m2:
        result["reset_tokens"] = m2.group(1)
    return result


def check_groq_usage(api_key: str) -> dict:
    """
    Check Groq token usage.

    Strategy:
      1. If this key hit a 429 today (TPD data stored in MongoDB), return that
         — no need to waste tokens on a probe call.
      2. Otherwise, make a minimal probe call and read per-minute headers (TPM).
      3. If the probe itself 429s, parse and store the TPD data.
    """
    import datetime
    TPD_LIMIT = 100_000  # Groq free tier TPD for llama-3.3-70b-versatile
    TPM_LIMIT = 12_000   # Groq free tier TPM for llama-3.3-70b-versatile

    # Check if we already have TPD data from a real 429 today
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    key_doc = db.get_api_key_by_value(api_key, "groq")
    if key_doc and key_doc.get("tpd_status") == "rate_limited" and key_doc.get("daily_tokens_date") == today:
        used = key_doc.get("daily_tokens_used", 0)
        limit = key_doc.get("tpd_limit", TPD_LIMIT)
        return {
            "status": "rate_limited",
            "limit_tokens": limit,
            "remaining_tokens": max(0, limit - used),
            "used_tokens": used,
            "reset_tokens": key_doc.get("tpd_reset", ""),
        }

    # No stored 429 — make a probe call and read per-minute headers
    try:
        client = Groq(api_key=api_key)
        raw_response = client.chat.completions.with_raw_response.create(
            messages=[{"role": "user", "content": "say ok"}],
            model=Models.Groq.LLAMA_3_3_70,
            max_tokens=2,
        )
        headers = raw_response.headers
        limit = int(headers.get("x-ratelimit-limit-tokens", TPM_LIMIT))
        remaining = int(headers.get("x-ratelimit-remaining-tokens", limit))
        reset = headers.get("x-ratelimit-reset-tokens", "")
        used = limit - remaining

        # Also show tracked daily usage if available
        tracked = key_doc.get("daily_tokens_used", 0) if key_doc and key_doc.get("daily_tokens_date") == today else 0

        return {
            "status": "active",
            "limit_tokens": limit,
            "remaining_tokens": remaining,
            "used_tokens": used,
            "reset_tokens": reset,
            "daily_tokens_used": tracked,
            "daily_tokens_limit": TPD_LIMIT,
        }
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "rate_limit" in error_msg.lower():
            result = _parse_groq_429(error_msg)
            # Store TPD data so dashboard shows it without another probe
            if "used_tokens" in result:
                db.update_api_key_tpd(
                    api_key, "groq",
                    used=result["used_tokens"],
                    limit=result.get("limit_tokens", TPD_LIMIT),
                    reset=result.get("reset_tokens"),
                )
            if "limit_tokens" not in result:
                result["limit_tokens"] = TPD_LIMIT
                result["remaining_tokens"] = 0
                result["used_tokens"] = TPD_LIMIT
            return result
        if "401" in error_msg or "invalid" in error_msg.lower():
            return {"status": "invalid", "error": "Invalid API key"}
        return {"status": "error", "error": error_msg}


def check_gemini_usage(api_key: str) -> dict:
    """Check Gemini key validity and rate limit by making a minimal API call."""
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=Models.Gemini.FLASH_2_0,
            contents="hi",
            config={"max_output_tokens": 1},
        )
        return {"status": "active"}
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            return {"status": "rate_limited", "error": error_msg}
        if "400" in error_msg or "API_KEY_INVALID" in error_msg:
            return {"status": "invalid", "error": "Invalid API key"}
        return {"status": "error", "error": error_msg}


def check_key_usage(provider: str, api_key: str) -> dict:
    """Check usage/quota for any provider key."""
    if provider == "groq":
        return check_groq_usage(api_key)
    elif provider == "gemini":
        return check_gemini_usage(api_key)
    return {"status": "unknown", "error": "Unknown provider"}


# ── Gemini (primary) ─────────────────────────────────────────────────────────

def get_gemini_response(message: str) -> str:
    """Call Google Gemini Flash to extract structured data using a key from the DB."""
    keys = db.get_enabled_api_keys("gemini")
    if not keys:
        raise RuntimeError("No enabled Gemini API keys available.")

    key_doc = random.choice(keys)
    api_key = key_doc["key"]

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=Models.Gemini.FLASH_2_0,
            contents=Prompts.PROMPT_EXTRACTOR + message,
        )
        tokens = getattr(response, "usage_metadata", None)
        total = (tokens.total_token_count if tokens else 0) or 0
        db.record_api_key_usage(api_key, "gemini", tokens_used=total)
        return response.text
    except Exception as e:
        db.record_api_key_usage(api_key, "gemini", error=str(e))
        raise


# ── Groq (fallback) ──────────────────────────────────────────────────────────

def get_groq_proposal(message: str) -> str:
    """Call Groq LLM using a key from the DB."""
    keys = db.get_enabled_api_keys("groq")
    if not keys:
        raise RuntimeError("No enabled Groq API keys available.")

    key_doc = random.choice(keys)
    api_key = key_doc["key"]

    try:
        client = Groq(api_key=api_key)
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": Prompts.PROMPT_EXTRACTOR + message
                }
            ],
            model=Models.Groq.LLAMA_3_3_70,
        )
        tokens = getattr(chat_completion.usage, "total_tokens", 0) if chat_completion.usage else 0
        db.record_api_key_usage(api_key, "groq", tokens_used=tokens)
        return chat_completion.choices[0].message.content
    except Exception as e:
        error_msg = str(e)
        # Parse and store TPD data from 429 errors for the dashboard
        if "429" in error_msg or "rate_limit" in error_msg.lower():
            tpd = _parse_groq_429(error_msg)
            if "used_tokens" in tpd:
                db.update_api_key_tpd(
                    api_key, "groq",
                    used=tpd["used_tokens"],
                    limit=tpd.get("limit_tokens", 100_000),
                    reset=tpd.get("reset_tokens"),
                )
        db.record_api_key_usage(api_key, "groq", error=error_msg)
        raise


# ── Unified caller: Gemini first, Groq fallback ─────────────────────────────

def get_groq_raw_response(message: str) -> str:
    """Try Gemini first, fall back to Groq if Gemini fails."""
    gemini_keys = db.get_enabled_api_keys("gemini")
    if gemini_keys:
        try:
            return get_gemini_response(message)
        except Exception as e:
            logger.warning(f"Gemini failed, falling back to Groq: {e}")

    return get_groq_proposal(message)
