from datetime import datetime, timezone

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from agentshield.config import get_settings
from agentshield.embeddings import embed
from agentshield.evals import print_eval_table, run_generation
from agentshield.learning.validator import ValidationContext, validate

console = Console()


def render(db, rule: dict) -> None:
    inc = db.incidents.find_one({"incident_id": rule["source_incident_id"]}) or {}
    m = rule["validation"]["metrics"]
    body = Table.grid(padding=(0, 2))
    body.add_row("Incident", f"{inc.get('incident_id')}  {inc.get('agent_pair')}  conf {inc.get('auditor_confidence')}")
    body.add_row("Excerpt", inc.get("excerpt_redacted", ""))
    body.add_row("Similar", ", ".join(rule.get("similar_incidents", [])))
    body.add_row("Entity", rule["entity_type"])
    body.add_row("Pattern", f"[bold cyan]{rule['pattern']}[/]")
    body.add_row("Rationale", rule.get("rationale", ""))
    body.add_row("Tests", f"positives {m['positives']}, negatives matched {m['negatives_matched']}, "
                          f"clean FP {m['candidate_fp_rate']:.2%} on {db.corpus_clean.estimated_document_count()} msgs")
    body.add_row("Eval Δ", f"recall {m['recall_before']:.3f} → [green]{m['recall_after']:.3f}[/]   "
                           f"{rule['entity_type']} {m['entity_recall_before']:.2f} → [green]{m['entity_recall_after']:.2f}[/]   "
                           f"precision {m['precision_before']:.3f} → {m['precision_after']:.3f}")
    body.add_row("Attempts", str(len(rule.get("attempts", []))))
    body.add_row("Playbook", f"{rule['playbook_suggestion']['agent_pair']}: {rule['entity_type']} → "
                             f"{rule['playbook_suggestion']['action']}")
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
    pb = rule["playbook_suggestion"]
    db.playbooks.update_one({"agent_pair": pb["agent_pair"]},
                            {"$set": {f"actions.{rule['entity_type']}": pb["action"],
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


def main():
    from agentshield.db import get_db
    db, approver = get_db(), get_settings().approver
    proposed = list(db.rules.find({"status": "proposed"}).sort("created_at", 1))
    if not proposed:
        console.print("no proposed rules")
        return
    for rule in proposed:
        while True:
            render(db, rule)
            choice = Prompt.ask("[a]pprove  [r]eject  [e]dit  [s]kip", choices=["a", "r", "e", "s"], default="a")
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
