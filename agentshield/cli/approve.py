from datetime import datetime, timezone

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from agentshield.config import get_settings
from agentshield.embeddings import embed
from agentshield.evals import print_eval_table, run_generation
from agentshield.learning.retirement import approve_retirement, reject_retirement
from agentshield.learning.validator import ValidationContext, validate
from agentshield.pipeline import merged_action  # noqa: F401  re-exported for the approval flow

console = Console()
CHOICE_PROMPT = escape("[a]pprove  [r]eject  [e]dit  [s]kip")  # unescaped, Rich reads [s] as strikethrough


def safe(text) -> str:
    """Untrusted (traffic- or LLM-derived) text, escaped so it cannot inject Rich markup (SEC13)."""
    return escape(str(text if text is not None else ""))


def render(db, rule: dict) -> None:
    inc = db.incidents.find_one({"incident_id": rule["source_incident_id"]}) or {}
    m = rule["validation"]["metrics"]
    body = Table.grid(padding=(0, 2))
    body.add_row("Incident", safe(f"{inc.get('incident_id')}  {inc.get('agent_pair')}  conf {inc.get('auditor_confidence')}"))
    body.add_row("Excerpt", safe(inc.get("excerpt_redacted", "")))
    body.add_row("Similar", safe(", ".join(rule.get("similar_incidents", []))))
    body.add_row("Entity", safe(rule["entity_type"]))
    body.add_row("Pattern", f"[bold cyan]{safe(rule['pattern'])}[/]")
    body.add_row("Rationale", safe(rule.get("rationale", "")))
    body.add_row("Tests", f"positives {m['positives']}, negatives matched {m['negatives_matched']}, "
                          f"clean FP {m['candidate_fp_rate']:.2%} on {db.corpus_clean.estimated_document_count()} msgs")
    body.add_row("Eval Δ", f"recall {m['recall_before']:.3f} → [green]{m['recall_after']:.3f}[/]   "
                           f"{rule['entity_type']} {m['entity_recall_before']:.2f} → [green]{m['entity_recall_after']:.2f}[/]   "
                           f"precision {m['precision_before']:.3f} → {m['precision_after']:.3f}")
    body.add_row("Attempts", str(len(rule.get("attempts", []))))
    pair = inc.get("agent_pair", rule["playbook_suggestion"]["agent_pair"])
    body.add_row("Playbook", safe(f"{pair}: {rule['entity_type']} → {rule['playbook_suggestion']['action']} "
                                  "(never weakens an existing action)"))
    console.print(Panel(body, title=f"Proposed rule {rule['rule_id']}", border_style="yellow"))


def approve_rule(db, rule_id: str, approver: str) -> tuple[dict, dict | None]:
    rule = db.rules.find_one({"rule_id": rule_id})
    top = db.rules.find_one({"status": "active"}, sort=[("generation", -1)])
    generation = (top or {}).get("generation", 0) + 1
    now = datetime.now(timezone.utc)
    db.rules.update_one({"rule_id": rule_id}, {"$set": {"status": "active", "approved_by": approver,
                                                         "generation": generation, "updated_at": now},
                                                "$inc": {"version": 1}})
    db.incidents.update_one({"incident_id": rule["source_incident_id"]},
                            {"$set": {"resolution": {"status": "rule_active", "rule_id": rule_id}}})
    # SEC12: the pair comes from the source incident, not the LLM, and the action can only tighten.
    incident = db.incidents.find_one({"incident_id": rule["source_incident_id"]}) or {}
    pair = incident.get("agent_pair", rule["playbook_suggestion"]["agent_pair"])
    existing = (db.playbooks.find_one({"agent_pair": pair}) or {}).get("actions", {}).get(rule["entity_type"])
    action = merged_action(existing, rule["playbook_suggestion"]["action"])
    db.playbooks.update_one({"agent_pair": pair},
                            {"$set": {f"actions.{rule['entity_type']}": action,
                                      "updated_from_incident": rule["source_incident_id"]},
                             "$inc": {"version": 1}}, upsert=True)
    term = rule["taxonomy_term"]
    db.taxonomy.update_one({"domain": term["domain"], "term": term["term"]},
                           {"$set": {"definition": term["definition"], "source_rule_id": rule_id,
                                     "embedding": embed([f"{term['term']}: {term['definition']}"])[0]}},
                           upsert=True)
    return run_generation(db, triggered_by=rule_id)


def reject_rule(db, rule_id: str, approver: str) -> None:
    rule = db.rules.find_one({"rule_id": rule_id})
    db.rules.update_one({"rule_id": rule_id}, {"$set": {"status": "retired", "rejected_by": approver,
                                                         "updated_at": datetime.now(timezone.utc)}})
    db.incidents.update_one({"incident_id": rule["source_incident_id"]},
                            {"$set": {"resolution": {"status": "open", "rule_id": None}}})


def edit_rule(db, rule_id: str, new_pattern: str):
    rule = db.rules.find_one({"rule_id": rule_id})
    report = validate({**rule, "pattern": new_pattern}, ValidationContext.load(db))
    if report.passed:
        db.rules.update_one({"rule_id": rule_id}, {"$set": {"pattern": new_pattern, "validation": report.to_dict(),
                                                             "updated_at": datetime.now(timezone.utc)}})
    return report


def render_retirement(rule: dict) -> None:
    r = rule["retirement"]
    body = Table.grid(padding=(0, 2))
    body.add_row("Rule", safe(f"{rule['rule_id']} v{rule['version']}  {rule['entity_type']}  (live now)"))
    body.add_row("Pattern", f"[bold cyan]{safe(rule['pattern'])}[/]")
    body.add_row("Live health", f"{r['hits']} hits, [red]{r['fp']} judged false positives ({r['fp_rate']:.0%})[/] "
                                f"from {r['sources']} sessions")
    for i, sample in enumerate(r.get("samples", [])[:3]):
        body.add_row("Sample" if i == 0 else "", safe(sample))
    body.add_row("If approved", "rule → shadow, removed from the live gateway, refinement incident "
                                f"{safe(r['incident_id'])} stays open")
    console.print(Panel(body, title=f"Proposed retirement {rule['rule_id']}", border_style="red"))


def review_retirements(db, approver: str) -> None:
    for rule in db.rules.find({"status": "active", "retirement.status": "proposed"}).sort("rule_id", 1):
        render_retirement(rule)
        choice = Prompt.ask(CHOICE_PROMPT, choices=["a", "r", "e", "s"], default="a")
        if choice == "a":
            current, previous = approve_retirement(db, rule["rule_id"], approver)
            console.print(f"[red]retired {rule['rule_id']}[/] by {approver}; gateway removes it via change stream")
            print_eval_table(console, current, previous)
        elif choice == "r":
            reject_retirement(db, rule["rule_id"], approver)
            console.print(f"[green]kept {rule['rule_id']}[/]; live counters reset")


def main():
    from agentshield.db import get_db
    db, approver = get_db(), get_settings().approver
    proposed = list(db.rules.find({"status": "proposed"}).sort("created_at", 1))
    retirements = db.rules.count_documents({"status": "active", "retirement.status": "proposed"})
    if not proposed and not retirements:
        console.print("no proposed rules or retirements")
        return
    review_retirements(db, approver)
    for rule in proposed:
        while True:
            render(db, rule)
            choice = Prompt.ask(CHOICE_PROMPT, choices=["a", "r", "e", "s"], default="a")
            if choice == "a":
                current, previous = approve_rule(db, rule["rule_id"], approver)
                console.print(f"[green]approved {rule['rule_id']}[/] by {approver}; gateway reloads via change stream")
                print_eval_table(console, current, previous)
                break
            if choice == "r":
                reject_rule(db, rule["rule_id"], approver)
                console.print(f"[red]rejected {rule['rule_id']}[/]")
                break
            if choice == "e":
                report = edit_rule(db, rule["rule_id"], Prompt.ask("new pattern", default=rule["pattern"]))
                if not report.passed:
                    console.print(f"[red]edit failed validation[/]\n{report.feedback_text()}")
                rule = db.rules.find_one({"rule_id": rule["rule_id"]})
                continue
            break


if __name__ == "__main__":
    main()
