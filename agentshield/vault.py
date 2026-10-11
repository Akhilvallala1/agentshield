"""The only collection allowed to hold raw values. TTL-expired after 1h."""
from datetime import datetime, timedelta, timezone

from agentshield.pipeline import TOKEN_RE


def store_tokens(db, session_id: str, tokens: dict[str, tuple[str, str]], ttl_s: int = 3600) -> None:
    if not tokens:
        return
    expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_s)
    for token, (entity_type, value) in tokens.items():
        db.vault.update_one(
            {"token": token, "session_id": session_id},
            {"$set": {"entity_type": entity_type, "value": value, "expires_at": expires}},
            upsert=True,
        )


def rehydrate(db, session_id: str, text: str, allowed: set[str] | None = None) -> str:
    found = set(TOKEN_RE.findall(text))
    if allowed is not None:
        found &= allowed  # only tokens minted for this exchange; replayed tokens stay opaque (SEC5)
    if not found:
        return text
    mapping = {d["token"]: d["value"] for d in db.vault.find({"session_id": session_id, "token": {"$in": list(found)}})}
    return TOKEN_RE.sub(lambda m: mapping.get(m.group(0), m.group(0)) if m.group(0) in found else m.group(0), text)
