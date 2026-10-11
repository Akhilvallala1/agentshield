from agentshield.scoring import score
from agentshield.types import Detection

EX = [{"text": "Maria has INS-AZ-4471-K", "spans": [
    {"start": 0, "end": 5, "entity_type": "PERSON"},
    {"start": 10, "end": 23, "entity_type": "INSURANCE_POLICY_NUMBER"}]}]
CLEAN = [{"text": "SKU-AZ-4471 restock"}, {"text": "nothing here"}]


def test_overlap_counts_as_hit_and_type_must_match():
    def predict(t):
        if t.startswith("Maria"):
            return [Detection("PERSON", 0, 4, "L2"), Detection("PHONE", 10, 23, "L2")]
        return []
    m = score(EX, CLEAN, predict)
    assert m["tp"] == 1 and m["fn"] == 1 and m["fp"] == 1
    assert m["by_entity"]["PERSON"]["recall"] == 1.0
    assert m["by_entity"]["INSURANCE_POLICY_NUMBER"]["recall"] == 0.0
    assert m["recall"] == 0.5 and m["precision"] == 0.5


def test_clean_corpus_fp_rate():
    def predict(t):
        return [Detection("X", 0, 3, "L1")] if t.startswith("SKU") else []
    m = score([], CLEAN, predict)
    assert m["fp_rate"] == 0.5 and m["fp"] == 1


def test_each_span_counted_once():
    def predict(t):
        return [Detection("PERSON", 0, 5, "L2"), Detection("PERSON", 1, 4, "L2")]
    m = score([{"text": "Maria x", "spans": [{"start": 0, "end": 5, "entity_type": "PERSON"}]}], [], predict)
    assert m["tp"] == 1 and m["fp"] == 1
