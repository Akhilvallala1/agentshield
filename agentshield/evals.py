import hashlib
from datetime import datetime, timezone

from rich.console import Console
from rich.table import Table

from agentshield.ner import get_ner
from agentshield.pipeline import detect
from agentshield.scoring import score
from agentshield.types import Rule


def evaluate(rules: list[Rule], ner, eval_set: list[dict], corpus: list[dict]) -> dict:
    return score(eval_set, corpus, lambda text: detect(text, rules, ner))


def load_eval_data(db) -> tuple[list[dict], list[dict]]:
    return list(db.eval_set.find({}, {"_id": 0})), list(db.corpus_clean.find({}, {"_id": 0}))


def run_generation(db, triggered_by: str | None = None) -> tuple[dict, dict | None]:
    rules = [Rule.from_doc(d) for d in db.rules.find({"status": "active"})]
    eval_set, corpus = load_eval_data(db)
    metrics = evaluate(rules, get_ner(), eval_set, corpus)
    previous = db.evals.find_one(sort=[("generation", -1)])
    generation = previous["generation"] + 1 if previous else 0
    rule_set_hash = hashlib.sha256("|".join(sorted(f"{r.rule_id}:{r.version}:{r.pattern}" for r in rules))
                                   .encode()).hexdigest()[:12]
    doc = {"generation": generation, "ts": datetime.now(timezone.utc), "rule_set_hash": rule_set_hash,
           "active_rules": [r.rule_id for r in rules], "triggered_by_rule": triggered_by, **metrics}
    db.evals.insert_one(doc)
    return doc, previous


def _delta(cur: float, prev: float | None) -> str:
    if prev is None:
        return ""
    d = round((cur - prev) * 100, 1)
    return f"[green]+{d}[/]" if d > 0 else (f"[red]{d}[/]" if d < 0 else "[dim]0[/]")


def print_eval_table(console: Console, current: dict, previous: dict | None) -> None:
    gen = current["generation"]
    t = Table(title=f"AgentShield evals, generation {gen}" + (f" (vs {gen - 1})" if previous else ""))
    t.add_column("Entity")
    if previous:
        t.add_column(f"Recall g{gen - 1}", justify="right")
    t.add_column(f"Recall g{gen}", justify="right")
    t.add_column("Δ pts", justify="right")
    for ent, m in current["by_entity"].items():
        prev = previous["by_entity"].get(ent, {}).get("recall") if previous else None
        row = [ent] + ([f"{prev:.2f}" if prev is not None else "-"] if previous else [])
        t.add_row(*row, f"{m['recall']:.2f}", _delta(m["recall"], prev))
    console.print(t)
    p = previous or {}
    console.print(
        f"overall recall [bold]{current['recall']:.3f}[/] {_delta(current['recall'], p.get('recall'))}   "
        f"precision [bold]{current['precision']:.3f}[/] {_delta(current['precision'], p.get('precision'))}   "
        f"clean FP rate [bold]{current['fp_rate']:.3%}[/]   rules: {current['active_rules']}")
