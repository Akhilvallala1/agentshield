import argparse
import time
from datetime import datetime, timezone

from rich.console import Console

from agentshield.db import next_id
from agentshield.embeddings import embed
from agentshield.learning.incidents import redact_excerpt, shape_of, span_hash
from agentshield.llm import complete_json
from agentshield.pipeline import TOKEN_RE
from agentshield.prompts import load_prompt

console = Console()

AUDIT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings"],
    "properties": {"findings": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["span", "entity_type", "reasoning", "confidence"],
        "properties": {"span": {"type": "string"}, "entity_type": {"type": "string"},
                       "reasoning": {"type": "string"}, "confidence": {"type": "number"}}}}},
}


def audit_text(text: str, llm=complete_json) -> list[dict]:
    result = llm(load_prompt("auditor"), f"Message:\n{text}", AUDIT_SCHEMA, "audit_findings")
    verified = []
    for f in result.get("findings", []):
        span = f["span"].strip()
        start = text.find(span) if span else -1
        if start < 0 or TOKEN_RE.fullmatch(span):
            continue  # hallucinated or already-protected span: never becomes an incident
        verified.append({**f, "span": span, "start": start, "end": start + len(span)})
    return verified


def audit_pending(db, limit: int = 20, min_confidence: float = 0.7, llm=complete_json, embed_fn=embed) -> list[str]:
    created = []
    for trace in db.traces.find({"audited": False, "blocked": False}).sort("ts", 1).limit(limit):
        text = trace["payload_redacted"]
        findings = [f for f in audit_text(text, llm) if f["confidence"] >= min_confidence]
        spans = [(f["start"], f["end"]) for f in findings]
        for f in findings:
            digest = span_hash(f["span"])
            if db.incidents.find_one({"span_sha256": digest, "resolution.status": {"$in": ["open", "rule_proposed"]}}):
                continue
            excerpt = redact_excerpt(text, spans, focus=(f["start"], f["end"]))
            incident_id = next_id(db, "incident", "I")
            db.incidents.insert_one({
                "incident_id": incident_id, "ts": datetime.now(timezone.utc), "agent_pair": trace["agent_pair"],
                "direction": trace["direction"], "trace_request_id": trace["request_id"],
                "entity_type_guess": f["entity_type"], "shape": shape_of(f["span"]), "span_sha256": digest,
                "excerpt_redacted": excerpt, "missed_by": ["L1", "L2"], "auditor_confidence": f["confidence"],
                "auditor_reasoning": f["reasoning"], "resolution": {"status": "open", "rule_id": None},
                "embedding": embed_fn([f"{f['entity_type']}: {excerpt}"])[0],
            })
            created.append(incident_id)
            console.print(f"[red]incident {incident_id}[/] {f['entity_type']} shape={shape_of(f['span'])} "
                          f"conf={f['confidence']:.2f}  [dim]{excerpt}[/]")
        db.traces.update_one({"_id": trace["_id"]}, {"$set": {"audited": True, "audit_findings": len(findings)}})
    db.traces.update_many({"audited": False, "blocked": True}, {"$set": {"audited": True, "audit_findings": 0}})
    return created


def main():
    from agentshield.db import get_db
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", action="store_true", help="poll for unaudited traces every 5s")
    args = ap.parse_args()
    db = get_db()
    while True:
        new = audit_pending(db)
        console.print(f"audited; {len(new)} new incident(s)")
        if not args.watch:
            break
        time.sleep(5)


if __name__ == "__main__":
    main()
