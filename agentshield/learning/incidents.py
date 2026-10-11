import hashlib
import re

from pymongo.errors import OperationFailure

from agentshield.db import INCIDENTS_VEC

PREFIX_RE = re.compile(r"^(?:[A-Z]{2,4}(?=[^A-Za-z])|0x)")


def shape_of(value: str) -> str:
    m = PREFIX_RE.match(value)
    keep = m.group(0) if m else ""
    rest = value[len(keep):]
    mapped = "".join("A" if c.isupper() else "a" if c.islower() else "0" if c.isdigit() else c for c in rest)
    return keep + mapped


def span_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(set(spans)):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def redact_excerpt(text: str, spans: list[tuple[int, int]], focus: tuple[int, int], window: int = 80) -> str:
    # Overlapping spans are merged first so no raw characters survive between them (I3).
    parts, pos, focus_lo, focus_hi = [], 0, 0, 0
    for start, end in _merge(list(spans) + [focus]):
        parts.append(text[pos:start])
        at = sum(len(p) for p in parts)
        repl = f"<<SHAPE:{shape_of(text[start:end])}>>"
        parts.append(repl)
        if start <= focus[0] < end:
            focus_lo, focus_hi = at, at + len(repl)
        pos = end
    parts.append(text[pos:])
    out = "".join(parts)
    lo, hi = max(0, focus_lo - window), min(len(out), focus_hi + window)
    return ("…" if lo > 0 else "") + out[lo:hi] + ("…" if hi < len(out) else "")


def similar_incidents(db, embedding: list[float], exclude_id: str, entity_type: str, k: int = 3) -> list[dict]:
    try:
        return list(db.incidents.aggregate([
            {"$vectorSearch": {"index": INCIDENTS_VEC, "path": "embedding", "queryVector": embedding,
                               "numCandidates": 50, "limit": k + 1}},
            {"$set": {"score": {"$meta": "vectorSearchScore"}}},
            {"$match": {"incident_id": {"$ne": exclude_id}}},
            {"$unset": ["embedding", "_id"]},
            {"$limit": k},
        ]))
    except OperationFailure:
        # Fallback (15.11): same entity type, newest first.
        return list(db.incidents.find({"entity_type_guess": entity_type, "incident_id": {"$ne": exclude_id}},
                                      {"embedding": 0, "_id": 0}).sort("ts", -1).limit(k))
