import argparse

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agentshield.config import get_settings
from agentshield.db import get_db
from demo_agents.fixtures import GOLDEN_MESSAGE, GOLDEN_SESSION

console = Console()


def send(message: str, session: str, via_intake: bool) -> None:
    if via_intake:
        from demo_agents.intake import summarize
        message = summarize(message)
    console.print(Panel(message, title="Intake sends (synthetic)", border_style="blue"))
    r = httpx.post(f"{get_settings().gateway_url}/a2a/forward", timeout=90, json={
        "from_agent": "intake", "to_agent": "claims", "message": message, "session_id": session}).json()
    t = Table("entity", "layer", "rule", title=f"detections ({r['latency_ms']} ms inline)")
    for d in r["detections"]:
        t.add_row(d["entity_type"], d["layer"], f"{d['rule_id'] or ''} v{d['rule_version'] or ''}".strip(" v"))
    console.print(t)
    style = "red" if r["blocked"] else "green"
    console.print(Panel(r["delivered_message"], title="Claims Agent receives", border_style=style))
    if r["reply"]:
        console.print(Panel(r["reply"], title="Reply to Intake (re-hydrated)", border_style="magenta"))


def lineage() -> None:
    db = get_db()
    t = Table("rule", "v", "gen", "entity", "status", "from incident", "approved by", "eval gen", title="rule lineage")
    for r in db.rules.find().sort("rule_id", 1):
        ev = db.evals.find_one({"triggered_by_rule": r["rule_id"]})
        t.add_row(r["rule_id"], str(r["version"]), str(r.get("generation") or "-"), r["entity_type"], r["status"],
                  r["source_incident_id"], r.get("approved_by") or "-", str(ev["generation"]) if ev else "-")
    console.print(t)


def main():
    ap = argparse.ArgumentParser(prog="demo")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send")
    s.add_argument("--message", default=GOLDEN_MESSAGE)
    s.add_argument("--session", default=GOLDEN_SESSION)
    s.add_argument("--via-intake", action="store_true", help="let the Intake LLM summarize first")
    sub.add_parser("audit")
    p = sub.add_parser("propose")
    p.add_argument("--incident")
    sub.add_parser("evals")
    sub.add_parser("lineage")
    args = ap.parse_args()

    if args.cmd == "send":
        send(args.message, args.session, args.via_intake)
    elif args.cmd == "audit":
        from agentshield.learning.auditor import audit_pending
        new = audit_pending(get_db())
        console.print(f"{len(new)} new incident(s): {new}")
    elif args.cmd == "propose":
        from agentshield.learning.synthesizer import _print_attempt, propose_rule
        db = get_db()
        ids = [args.incident] if args.incident else [i["incident_id"] for i in db.incidents.find(
            {"resolution.status": "open", "seeded": {"$ne": True}}).sort("ts", 1)]
        for incident_id in ids:
            console.print(f"[bold]{incident_id}[/]")
            result = propose_rule(db, incident_id, on_attempt=_print_attempt)
            console.print(f"  → {result['status']} {result.get('rule_id', '')}")
    elif args.cmd == "evals":
        from agentshield.evals import print_eval_table, run_generation
        print_eval_table(console, *run_generation(get_db()))
    elif args.cmd == "lineage":
        lineage()


if __name__ == "__main__":
    main()
