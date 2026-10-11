"""Hard metric gates before a human sees a rule (3.5, 15.2)."""
import multiprocessing as mp
import re
from dataclasses import asdict, dataclass

from agentshield.evals import evaluate, load_eval_data
from agentshield.types import Rule

ADVERSARIAL = ["a" * 10_000, "A" * 5_000 + "!", "0" * 10_000, "-".join(["AA"] * 3_400),
               "INS-" * 2_500, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa!" * 300]


def _search_all(pattern: str, ready) -> None:
    rx = re.compile(pattern)
    ready.set()  # imports done; only the search itself counts against the timeout
    for s in ADVERSARIAL:
        rx.search(s)


def check_backtracking(pattern: str, timeout: float = 1.0) -> bool:
    ctx = mp.get_context("spawn")  # fork is unsafe on macOS with pymongo threads
    ready = ctx.Event()
    proc = ctx.Process(target=_search_all, args=(pattern, ready), daemon=True)
    proc.start()
    if not ready.wait(60):
        proc.terminate()
        return False
    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        proc.join()
        return False
    return proc.exitcode == 0


@dataclass
class ValidationContext:
    eval_set: list[dict]
    corpus: list[dict]
    base_rules: list[Rule]
    ner: object
    fp_threshold: float = 0.01

    @classmethod
    def load(cls, db) -> "ValidationContext":
        from agentshield.config import get_settings
        from agentshield.ner import get_ner
        eval_set, corpus = load_eval_data(db)
        rules = [Rule.from_doc(d) for d in db.rules.find({"status": "active"})]
        return cls(eval_set, corpus, rules, get_ner(), get_settings().fp_threshold)


@dataclass
class ValidationReport:
    passed: bool
    checks: list[dict]
    metrics: dict

    @property
    def failures(self) -> list[str]:
        return [c["name"] for c in self.checks if not c["passed"]]

    def feedback_text(self) -> str:
        return "\n".join(f"- {c['name']} FAILED: {c['detail']}" for c in self.checks if not c["passed"])

    def to_dict(self) -> dict:
        return asdict(self)


def validate(candidate: dict, ctx: ValidationContext) -> ValidationReport:
    checks: list[dict] = []
    metrics: dict = {}

    def add(name: str, ok: bool, detail: str) -> bool:
        checks.append({"name": name, "passed": bool(ok), "detail": detail})
        return ok

    try:
        rx = re.compile(candidate["pattern"])
    except re.error as e:
        add("compiles", False, f"re.error: {e}")
        return ValidationReport(False, checks, metrics)
    add("compiles", True, "ok")

    if not add("no_catastrophic_backtracking", check_backtracking(candidate["pattern"]),
               "finished 10KB adversarial strings within 1s"):
        return ValidationReport(False, checks, metrics)

    pos, neg = candidate["positive_examples"], candidate["negative_examples"]
    pos_hit = [p for p in pos if rx.search(p)]
    neg_hit = [n for n in neg if rx.search(n)]
    metrics["positives"] = f"{len(pos_hit)}/{len(pos)}"
    metrics["negatives_matched"] = f"{len(neg_hit)}/{len(neg)}"
    add("positives", len(pos) >= 3 and len(pos_hit) == len(pos),
        f"matched {len(pos_hit)}/{len(pos)} (need all, at least 3); missed {[p for p in pos if p not in pos_hit]}")
    add("negatives", len(neg_hit) == 0, f"must match none; matched {neg_hit}")

    flagged = [c["text"] for c in ctx.corpus if rx.search(c["text"])]
    fp_rate = len(flagged) / len(ctx.corpus) if ctx.corpus else 0.0
    metrics["candidate_fp_rate"] = round(fp_rate, 4)
    add("clean_fp_rate", fp_rate < ctx.fp_threshold,
        f"{len(flagged)}/{len(ctx.corpus)} clean messages matched ({fp_rate:.2%}, limit {ctx.fp_threshold:.0%}); "
        f"examples: {flagged[:3]}")

    rule = Rule("CANDIDATE", 0, candidate["entity_type"], candidate["pattern"])
    before = evaluate(ctx.base_rules, ctx.ner, ctx.eval_set, [])
    after = evaluate(ctx.base_rules + [rule], ctx.ner, ctx.eval_set, [])
    metrics.update(recall_before=before["recall"], recall_after=after["recall"],
                   precision_before=before["precision"], precision_after=after["precision"],
                   entity_recall_before=before["by_entity"].get(candidate["entity_type"], {}).get("recall", 0.0),
                   entity_recall_after=after["by_entity"].get(candidate["entity_type"], {}).get("recall", 0.0))
    add("eval_delta", after["recall"] > before["recall"] and before["precision"] - after["precision"] <= 0.01,
        f"recall {before['recall']:.3f}->{after['recall']:.3f} (must rise), precision "
        f"{before['precision']:.3f}->{after['precision']:.3f} (may drop at most 0.01); "
        f"entity_type must be one of the labeled types, got {candidate['entity_type']}")

    return ValidationReport(all(c["passed"] for c in checks), checks, metrics)
