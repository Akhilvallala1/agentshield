import argparse
import json
from datetime import datetime, timezone

from rich.console import Console

from agentshield.db import next_id
from agentshield.learning.incidents import similar_incidents
from agentshield.learning.validator import ValidationContext, validate
from agentshield.llm import complete_json
from agentshield.prompts import load_prompt

console = Console()

SYNTH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["kind", "entity_type", "pattern", "rationale", "positive_examples", "negative_examples",
                 "taxonomy_term", "playbook_suggestion"],
    "properties": {
        "kind": {"type": "string", "enum": ["regex", "not_regexable"]},
        "entity_type": {"type": "string"},
        "pattern": {"type": "string"},
        "rationale": {"type": "string"},
        "positive_examples": {"type": "array", "items": {"type": "string"}},
        "negative_examples": {"type": "array", "items": {"type": "string"}},
        "taxonomy_term": {"type": "object", "additionalProperties": False,
                          "required": ["domain", "term", "definition"],
                          "properties": {"domain": {"type": "string"}, "term": {"type": "string"},
                                         "definition": {"type": "string"}}},
        "playbook_suggestion": {"type": "object", "additionalProperties": False,
                                "required": ["agent_pair", "action"],
                                "properties": {"agent_pair": {"type": "string"},
                                               "action": {"type": "string",
                                                          "enum": ["allow", "mask", "tokenize", "generalize", "block"]}}},
    },
}

INCIDENT_FIELDS = ["incident_id", "agent_pair", "entity_type_guess", "shape", "excerpt_redacted"]


def build_user_prompt(incident: dict, similar: list[dict], taxonomy: list[dict], feedback: str | None) -> str:
    payload = {
        "incident": {k: incident.get(k) for k in INCIDENT_FIELDS},
        "similar_past_incidents": [{k: s.get(k) for k in INCIDENT_FIELDS + ["score"]} for s in similar],
        "taxonomy": [{"term": t["term"], "definition": t["definition"]} for t in taxonomy],
    }
    text = json.dumps(payload, indent=2, default=str)
    if feedback:
        text += f"\n\nYour previous attempt failed validation:\n{feedback}"
    return text


def synthesize(incident: dict, similar: list[dict], taxonomy: list[dict], feedback: str | None = None,
               llm=complete_json) -> dict:
    return llm(load_prompt("synthesizer"), build_user_prompt(incident, similar, taxonomy, feedback),
               SYNTH_SCHEMA, "rule_candidate")


def propose_rule(db, incident_id: str, max_attempts: int = 3, llm=complete_json, on_attempt=None) -> dict:
    incident = db.incidents.find_one({"incident_id": incident_id})
    similar = similar_incidents(db, incident["embedding"], incident_id, incident["entity_type_guess"])
    taxonomy = list(db.taxonomy.find({"domain": "insurance"}, {"embedding": 0, "_id": 0}))
    ctx = ValidationContext.load(db)
    attempts, feedback = [], None
    for n in range(1, max_attempts + 1):
        cand = synthesize(incident, similar, taxonomy, feedback, llm)
        if cand["kind"] == "not_regexable":
            db.incidents.update_one({"incident_id": incident_id}, {"$set": {"resolution.status": "needs_human"}})
            return {"status": "not_regexable", "attempts": attempts}
        report = validate(cand, ctx)
        attempt = {"attempt": n, "pattern": cand["pattern"], "passed": report.passed,
                   "failures": report.failures, "metrics": report.metrics}
        attempts.append(attempt)
        if on_attempt:
            on_attempt(attempt, report)
        if report.passed:
            now = datetime.now(timezone.utc)
            rule_id = next_id(db, "rule", "R")
            db.rules.insert_one({
                "rule_id": rule_id, "version": 1, "entity_type": cand["entity_type"], "kind": "regex",
                "pattern": cand["pattern"], "status": "proposed",
                "scope": {"domain": "insurance", "agent_pair": "*"},
                "source_incident_id": incident_id, "parent_rule_id": None, "generation": None,
                "created_by": "synthesizer", "approved_by": None, "stats": {"live_hits": 0, "live_fp": 0},
                "rationale": cand["rationale"], "positive_examples": cand["positive_examples"],
                "negative_examples": cand["negative_examples"], "taxonomy_term": cand["taxonomy_term"],
                "playbook_suggestion": cand["playbook_suggestion"], "similar_incidents": [s["incident_id"] for s in similar],
                "validation": report.to_dict(), "attempts": attempts, "created_at": now, "updated_at": now,
            })
            db.incidents.update_one({"incident_id": incident_id},
                                    {"$set": {"resolution": {"status": "rule_proposed", "rule_id": rule_id}}})
            return {"status": "proposed", "rule_id": rule_id, "attempts": attempts}
        feedback = report.feedback_text()
    db.incidents.update_one({"incident_id": incident_id}, {"$set": {"synthesis_attempts": attempts}})
    return {"status": "failed", "attempts": attempts}


def _print_attempt(attempt: dict, report) -> None:
    mark = "[green]PASS[/]" if attempt["passed"] else "[red]FAIL[/]"
    console.print(f"  attempt {attempt['attempt']}: {mark} [cyan]{attempt['pattern']}[/] {attempt['metrics']}")
    if not attempt["passed"]:
        console.print(f"[dim]{report.feedback_text()}[/]")


def main():
    from agentshield.db import get_db
    ap = argparse.ArgumentParser()
    ap.add_argument("--incident")
    args = ap.parse_args()
    db = get_db()
    incident_id = args.incident or (db.incidents.find_one(
        {"resolution.status": "open", "seeded": {"$ne": True}}, sort=[("ts", -1)]) or {}).get("incident_id")
    if not incident_id:
        console.print("no open incidents")
        return
    console.print(f"synthesizing rule for [bold]{incident_id}[/]")
    result = propose_rule(db, incident_id, on_attempt=_print_attempt)
    console.print(result["status"], result.get("rule_id", ""))


if __name__ == "__main__":
    main()
