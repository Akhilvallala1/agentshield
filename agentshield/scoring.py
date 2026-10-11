"""Overlap + same-type matching (addendum 15.1)."""
from collections import defaultdict
from typing import Callable

from agentshield.types import Detection


def _ratio(a: int, b: int) -> float:
    return round(a / b, 4) if b else 0.0


def score(examples: list[dict], clean: list[dict], predict: Callable[[str], list[Detection]]) -> dict:
    tp = fp = fn = 0
    per = defaultdict(lambda: {"tp": 0, "fn": 0})
    for ex in examples:
        dets = list(predict(ex["text"]))
        used: set[int] = set()
        for sp in ex["spans"]:
            hit = next((i for i, d in enumerate(dets) if i not in used and d.entity_type == sp["entity_type"]
                        and d.start < sp["end"] and d.end > sp["start"]), None)
            if hit is None:
                fn += 1
                per[sp["entity_type"]]["fn"] += 1
            else:
                used.add(hit)
                tp += 1
                per[sp["entity_type"]]["tp"] += 1
        fp += len(dets) - len(used)
    flagged = 0
    for c in clean:
        dets = predict(c["text"])
        fp += len(dets)
        flagged += bool(dets)
    by_entity = {k: {**v, "recall": _ratio(v["tp"], v["tp"] + v["fn"])} for k, v in sorted(per.items())}
    return {"recall": _ratio(tp, tp + fn), "precision": _ratio(tp, tp + fp), "fp_rate": _ratio(flagged, len(clean)),
            "tp": tp, "fp": fp, "fn": fn, "by_entity": by_entity}
