"""
MongoDB data-access layer.

Required .env variables:
    MONGODB_URI      – full connection string
                       e.g. mongodb+srv://user:pass@cluster.mongodb.net/
    MONGODB_DB_NAME  – (optional) database name  default: phone_info_bot

Account documents use phone number as _id.
added_date is set once on insert and never modified.
"""

import os
import logging
from datetime import datetime, timezone, timedelta
import certifi
from pymongo import MongoClient, ReturnDocument
from pymongo.collection import Collection
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_MONGODB_URI = os.getenv("MONGODB_URI", "")
_DB_NAME     = os.getenv("MONGODB_DB_NAME", "phone_info_bot")

_client: MongoClient | None = None
_db = None


def _get_db():
    global _client, _db
    if _db is None:
        if not _MONGODB_URI:
            raise RuntimeError(
                "MONGODB_URI is not configured.\n"
                "Add it to your .env file:\n"
                "  MONGODB_URI=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/"
            )
        _client = MongoClient(_MONGODB_URI, serverSelectionTimeoutMS=5_000, tlsCAFile=certifi.where())
        _db = _client[_DB_NAME]
        logger.info(f"MongoDB connected — database: '{_DB_NAME}'")
    return _db


def _col(name: str) -> Collection:
    return _get_db()[name]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Accounts ─────────────────────────────────────────────────────────────────

def get_all_accounts() -> list[dict]:
    return list(_col("accounts").find())


def get_accounts_by_mode(mode: str) -> list[dict]:
    return list(_col("accounts").find({"mode": mode}))


def get_live_session_strings() -> list[str]:
    docs = _col("accounts").find(
        {"mode": "live", "session_string": {"$exists": True, "$ne": None, "$gt": ""}}
    )
    return [d["session_string"] for d in docs if d.get("session_string")]


def insert_account(account: dict) -> str:
    """Insert a new account. Phone number is used as _id. Returns the phone."""
    phone = account.get("phone", "").strip()
    if not phone:
        raise ValueError("Phone is required to insert an account.")

    data = {k: v for k, v in account.items() if k not in ("_id", "added_date")}
    data["_id"]        = phone
    data["added_date"] = _now()

    _col("accounts").insert_one(data)
    return phone


def replace_account(account_id: str, account: dict) -> None:
    """
    Replace an account identified by its phone (_id = account_id).

    - added_date is always preserved from the original document.
    - If the phone number changed, the old document is deleted and a new one
      is inserted so that _id stays consistent with the phone.
    """
    existing = _col("accounts").find_one({"_id": account_id})
    added_date = existing.get("added_date") if existing else _now()

    new_phone = account.get("phone", account_id).strip()
    data = {k: v for k, v in account.items() if k not in ("_id", "added_date")}
    data["added_date"] = added_date

    if new_phone != account_id:
        # Phone changed — delete old doc, insert under new _id
        _col("accounts").delete_one({"_id": account_id})
        _col("accounts").insert_one({"_id": new_phone, **data})
    else:
        _col("accounts").replace_one({"_id": account_id}, {"_id": account_id, **data})


def delete_account(account_id: str) -> None:
    _col("accounts").delete_one({"_id": account_id})


def update_session_string(phone: str, session_string: str) -> None:
    """Patch only the session_string field on the account matched by phone (_id)."""
    _col("accounts").update_one(
        {"_id": phone},
        {"$set": {"session_string": session_string}},
    )


# ── Account acquisition (under_use / last_used) ──────────────────────────────

_STALE_TIMEOUT_SECONDS = 120  # 2 minutes — auto-release stuck accounts


def acquire_account(bot_source: str | None = None, skip_phones: list[str] | None = None) -> dict | None:
    """
    Atomically find an available live account with a session string,
    mark it as under_use=True and stamp last_used=now.

    bot_source: e.g. "sml", "wcb", "aml" — only accounts with an active
                paid_subscription for this bot will be considered.
    skip_phones: list of phone numbers to exclude (e.g. rate-limited accounts).

    Accounts stuck as under_use for longer than _STALE_TIMEOUT_SECONDS
    are considered available (crash recovery).

    Returns the full account document, or None if all accounts are busy.
    """
    now = _now()
    stale_cutoff = now - timedelta(seconds=_STALE_TIMEOUT_SECONDS)

    query = {
        "mode": "live",
        "session_string": {"$exists": True, "$ne": None, "$gt": ""},
        "$or": [
            {"under_use": {"$ne": True}},
            {"last_used": {"$lt": stale_cutoff}},
            {"last_used": {"$exists": False}},
        ],
    }

    if bot_source:
        sub_key = f"paid_subscription.{bot_source.lower()}"
        query[sub_key] = {"$exists": True, "$nin": [None, ""]}

    if skip_phones:
        query["_id"] = {"$nin": skip_phones}

    doc = _col("accounts").find_one_and_update(
        query,
        {"$set": {"under_use": True, "last_used": now}},
        return_document=ReturnDocument.AFTER,
        sort=[("last_used", 1)],  # prefer least-recently-used
    )
    return doc


def release_account(phone: str) -> None:
    """Mark an account as no longer in use."""
    _col("accounts").update_one(
        {"_id": phone},
        {"$set": {"under_use": False, "last_used": _now()}},
    )


def release_stale_accounts() -> int:
    """Release all accounts stuck as under_use beyond the stale timeout. Returns count released."""
    stale_cutoff = _now() - timedelta(seconds=_STALE_TIMEOUT_SECONDS)
    result = _col("accounts").update_many(
        {
            "under_use": True,
            "$or": [
                {"last_used": {"$lt": stale_cutoff}},
                {"last_used": {"$exists": False}},
            ],
        },
        {"$set": {"under_use": False}},
    )
    return result.modified_count


def get_busy_accounts() -> list[dict]:
    """Return all accounts currently marked as under_use."""
    return list(_col("accounts").find({"under_use": True}))


# ── Bot state ─────────────────────────────────────────────────────────────────

_STATE_ID = "singleton"


def load_bot_state() -> dict:
    doc = _col("bot_state").find_one({"_id": _STATE_ID})
    if doc is None:
        return {"active_index": 0, "last_switch_time": None, "switch_history": []}
    doc.pop("_id", None)
    return doc


def save_bot_state(state: dict) -> None:
    data = {k: v for k, v in state.items() if k != "_id"}
    _col("bot_state").replace_one(
        {"_id": _STATE_ID},
        {"_id": _STATE_ID, **data},
        upsert=True,
    )


# ── API Keys ─────────────────────────────────────────────────────────────────

def get_all_api_keys() -> list[dict]:
    """Return all API key documents, sorted by provider then label."""
    return list(_col("api_keys").find().sort([("provider", 1), ("label", 1)]))


def get_enabled_api_keys(provider: str) -> list[dict]:
    """Return enabled key documents for a provider (groq or gemini)."""
    return list(_col("api_keys").find({
        "provider": provider.lower(),
        "enabled": True,
    }).sort("last_used", 1))


def insert_api_key(data: dict) -> str:
    """Insert a new API key. Returns the inserted _id as string."""
    from bson import ObjectId
    doc = {
        "provider": data["provider"].lower(),
        "label": data.get("label", "").strip(),
        "key": data["key"].strip(),
        "enabled": data.get("enabled", True),
        "added_date": _now(),
        "last_used": None,
        "use_count": 0,
        "last_error": None,
    }
    result = _col("api_keys").insert_one(doc)
    return str(result.inserted_id)


def update_api_key(key_id: str, data: dict) -> None:
    """Update an API key's label, key value, or enabled status."""
    from bson import ObjectId
    update_fields = {}
    for field in ("label", "key", "enabled", "provider"):
        if field in data:
            update_fields[field] = data[field]
    if update_fields:
        _col("api_keys").update_one(
            {"_id": ObjectId(key_id)},
            {"$set": update_fields},
        )


def delete_api_key(key_id: str) -> None:
    from bson import ObjectId
    _col("api_keys").delete_one({"_id": ObjectId(key_id)})


def toggle_api_key(key_id: str) -> bool:
    """Toggle enabled status. Returns new enabled value."""
    from bson import ObjectId
    doc = _col("api_keys").find_one({"_id": ObjectId(key_id)})
    if not doc:
        return False
    new_enabled = not doc.get("enabled", True)
    _col("api_keys").update_one(
        {"_id": ObjectId(key_id)},
        {"$set": {"enabled": new_enabled}},
    )
    return new_enabled


def get_api_key_by_value(key_value: str, provider: str) -> dict | None:
    """Find an API key document by its key value and provider."""
    return _col("api_keys").find_one({"key": key_value, "provider": provider})


def record_api_key_usage(key_value: str, provider: str, error: str | None = None,
                         tokens_used: int = 0) -> None:
    """Increment use_count and stamp last_used for the key. Track daily token usage."""
    now = _now()
    today = now.strftime("%Y-%m-%d")
    col = _col("api_keys")
    filt = {"key": key_value, "provider": provider}

    # Try atomic increment if date matches today
    result = col.update_one(
        {**filt, "daily_tokens_date": today},
        {
            "$inc": {"use_count": 1, "daily_tokens_used": tokens_used},
            "$set": {"last_used": now, "last_error": error},
        },
    )

    # Date changed (or field missing) — reset daily counter
    if result.matched_count == 0:
        col.update_one(
            filt,
            {
                "$inc": {"use_count": 1},
                "$set": {
                    "last_used": now,
                    "last_error": error,
                    "daily_tokens_used": tokens_used,
                    "daily_tokens_date": today,
                },
            },
        )


def migrate_api_keys_from_env() -> int:
    """One-time migration: import API keys from environment variables if collection is empty."""
    if _col("api_keys").count_documents({}) > 0:
        return 0

    now = _now()
    docs = []
    seen = set()

    # Groq keys
    for i in range(1, 11):
        key = os.getenv(f"GROQ_API_KEY_{i}", "")
        if key and key not in seen:
            seen.add(key)
            docs.append({
                "provider": "groq",
                "label": f"Groq Key {i}",
                "key": key,
                "enabled": True,
                "added_date": now,
                "last_used": None,
                "use_count": 0,
                "last_error": None,
            })

    # Gemini key
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key and gemini_key not in seen:
        docs.append({
            "provider": "gemini",
            "label": "Gemini Key 1",
            "key": gemini_key,
            "enabled": True,
            "added_date": now,
            "last_used": None,
            "use_count": 0,
            "last_error": None,
        })

    if not docs:
        return 0

    result = _col("api_keys").insert_many(docs)
    n = len(result.inserted_ids)
    logger.info(f"Migrated {n} API keys from environment into MongoDB.")
    return n


# ── One-time JSON → MongoDB migration ────────────────────────────────────────

def migrate_from_json_if_empty(json_path: str = "all_accounts.json") -> int:
    """
    If the accounts collection is empty and the legacy JSON file exists,
    import all accounts automatically (one-time operation).
    Sets _id = phone and stamps added_date = now for each imported account.
    Returns the number of documents imported (0 if skipped).
    """
    import json as _json

    if _col("accounts").count_documents({}) > 0:
        return 0  # already populated — skip

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            accounts = _json.load(f)
    except (FileNotFoundError, ValueError):
        return 0

    if not accounts:
        return 0

    now = _now()
    docs = []
    seen_phones = set()
    for acc in accounts:
        phone = acc.get("phone", "").strip()
        if not phone or phone in seen_phones:
            continue
        seen_phones.add(phone)
        data = {k: v for k, v in acc.items() if k not in ("_id", "added_date")}
        data["_id"]        = phone
        data["added_date"] = now
        docs.append(data)

    if not docs:
        return 0

    result = _col("accounts").insert_many(docs)
    n = len(result.inserted_ids)
    logger.info(f"Migrated {n} accounts from '{json_path}' into MongoDB.")
    return n
