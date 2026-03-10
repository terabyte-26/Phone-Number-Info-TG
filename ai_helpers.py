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


def _parse_tpd_reset_seconds(reset_str: str) -> float:
    """Parse Groq reset string like '3m33.408s' into seconds."""
    import re
    total = 0.0
    m = re.search(r'(\d+)m', reset_str)
    if m:
        total += int(m.group(1)) * 60
    s = re.search(r'([\d.]+)s', reset_str)
    if s:
        total += float(s.group(1))
    return total


def check_groq_usage(api_key: str) -> dict:
    """
    Check Groq token usage.

    Strategy:
      1. If this key hit a 429 today and the reset time hasn't passed yet,
         return stored TPD data (no probe call needed).
      2. If the reset time has passed, do a probe call to verify the key
         is available again — if it succeeds, clear the rate-limited status.
      3. For keys without stored 429 data, probe and read per-minute headers.
    """
    import datetime
    TPD_LIMIT = 100_000  # Groq free tier TPD for llama-3.3-70b-versatile
    TPM_LIMIT = 12_000   # Groq free tier TPM for llama-3.3-70b-versatile

    now = datetime.datetime.utcnow()
    today = now.strftime("%Y-%m-%d")
    key_doc = db.get_api_key_by_value(api_key, "groq")

    # Check if key was marked rate-limited today
    if key_doc and key_doc.get("tpd_status") == "rate_limited" and key_doc.get("daily_tokens_date") == today:
        # Check if the reset time has passed
        updated_at = key_doc.get("tpd_updated_at")
        reset_str = key_doc.get("tpd_reset", "")
        reset_secs = _parse_tpd_reset_seconds(reset_str) if reset_str else 0

        if updated_at and reset_secs > 0:
            elapsed = (now - updated_at).total_seconds()
            if elapsed >= reset_secs:
                # Reset time has passed — probe to check if key is recharged
                logger.info(f"Groq key {api_key[:8]}... reset time elapsed, probing...")
            else:
                # Still within reset window — return stored data
                used = key_doc.get("daily_tokens_used", 0)
                limit = key_doc.get("tpd_limit", TPD_LIMIT)
                remaining_secs = int(reset_secs - elapsed)
                mins, secs = divmod(remaining_secs, 60)
                return {
                    "status": "rate_limited",
                    "limit_tokens": limit,
                    "remaining_tokens": max(0, limit - used),
                    "used_tokens": used,
                    "reset_tokens": f"{mins}m{secs}s" if mins else f"{secs}s",
                }
        elif not reset_secs:
            # No reset time info — still return stored data
            used = key_doc.get("daily_tokens_used", 0)
            limit = key_doc.get("tpd_limit", TPD_LIMIT)
            return {
                "status": "rate_limited",
                "limit_tokens": limit,
                "remaining_tokens": max(0, limit - used),
                "used_tokens": used,
                "reset_tokens": "",
            }

    # Probe call — either key is not rate-limited, or reset time has passed
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

        # Key is working again — clear rate-limited status
        if key_doc and key_doc.get("tpd_status") == "rate_limited":
            db.clear_api_key_tpd(api_key, "groq")
            logger.info(f"Groq key {api_key[:8]}... is available again, cleared rate-limit status")

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
    """Call Groq LLM using a key from the DB. Rotates through keys on 429."""
    import datetime

    keys = db.get_enabled_api_keys("groq")
    if not keys:
        raise RuntimeError("No enabled Groq API keys available.")

    # Filter out keys known to be exhausted today, unless reset time has passed
    now = datetime.datetime.utcnow()
    today = now.strftime("%Y-%m-%d")

    available = []
    recharged = []
    for k in keys:
        if k.get("tpd_status") != "rate_limited" or k.get("daily_tokens_date") != today:
            available.append(k)
        else:
            # Check if reset time has passed — key may be recharged
            updated_at = k.get("tpd_updated_at")
            reset_str = k.get("tpd_reset", "")
            reset_secs = _parse_tpd_reset_seconds(reset_str) if reset_str else 0
            if updated_at and reset_secs > 0 and (now - updated_at).total_seconds() >= reset_secs:
                recharged.append(k)

    # Add recharged keys back (try them after known-good keys)
    available.extend(recharged)

    # If all keys are exhausted, fall back to full list (let it 429 naturally)
    if not available:
        available = keys

    random.shuffle(available)
    last_error = None

    for key_doc in available:
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
            # Clear rate-limited status if this key was previously exhausted
            if key_doc.get("tpd_status") == "rate_limited":
                db.clear_api_key_tpd(api_key, "groq")
                logger.info(f"Groq key {api_key[:8]}... recharged, cleared rate-limit status")
            return chat_completion.choices[0].message.content
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "rate_limit" in error_msg.lower():
                # Store TPD data and try next key
                tpd = _parse_groq_429(error_msg)
                if "used_tokens" in tpd:
                    db.update_api_key_tpd(
                        api_key, "groq",
                        used=tpd["used_tokens"],
                        limit=tpd.get("limit_tokens", 100_000),
                        reset=tpd.get("reset_tokens"),
                    )
                db.record_api_key_usage(api_key, "groq", error=error_msg)
                logger.warning(f"Groq key {api_key[:8]}... rate-limited, trying next key")
                last_error = e
                continue
            # Non-429 error — don't retry
            db.record_api_key_usage(api_key, "groq", error=error_msg)
            raise

    # All keys exhausted
    logger.warning("All Groq API keys are rate-limited")
    raise last_error


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
