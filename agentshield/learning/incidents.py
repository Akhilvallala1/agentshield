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


def redact_excerpt(text: str, spans: list[tuple[int, int]], focus: tuple[int, int], window: int = 80) -> str:
    out, focus_start, focus_end = text, focus[0], focus[1]
    for start, end in sorted(set(spans), reverse=True):
        repl = f"<<SHAPE:{shape_of(text[start:end])}>>"
        out = out[:start] + repl + out[end:]
        shift = len(repl) - (end - start)
        if start < focus[0]:
            focus_start += shift
            focus_end += shift
        elif (start, end) == focus:
            focus_end = focus_start + len(repl)
    lo, hi = max(0, focus_start - window), min(len(out), focus_end + window)
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
