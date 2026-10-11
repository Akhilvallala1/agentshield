from agentshield.rules_cache import RulesCache


def doc(rule_id, status="active", pair="*", version=1):
    return {"rule_id": rule_id, "version": version, "entity_type": "X", "pattern": r"\bX\d\b",
            "status": status, "scope": {"agent_pair": pair}}


def test_upsert_and_scope():
    c = RulesCache(db=None)
    c.upsert_doc(doc("R-1"))
    c.upsert_doc(doc("R-2", pair="intake->claims"))
    c.upsert_doc(doc("R-3", pair="billing->claims"))
    assert {r.rule_id for r in c.rules_for("intake->claims")} == {"R-1", "R-2"}
    assert len(c.all_active()) == 3


def test_non_active_status_removes_rule_and_counts_reloads():
    c = RulesCache(db=None)
    events = []
    c.on_change = events.append
    c.upsert_doc(doc("R-1"))
    c.upsert_doc(doc("R-1", status="shadow"))
    assert c.all_active() == []
    assert c.reload_count == 2 and len(events) == 2


def test_version_update_replaces_rule():
    c = RulesCache(db=None)
    c.upsert_doc(doc("R-1", version=1))
    c.upsert_doc(doc("R-1", version=2))
    assert [r.version for r in c.all_active()] == [2]


def test_proposed_rule_that_was_never_live_is_silent():
    c = RulesCache(db=None)
    events = []
    c.on_change = events.append
    c.upsert_doc(doc("R-9", status="proposed"))
    assert events == [] and c.reload_count == 0


def test_watch_reopens_after_stream_ends():
    import pytest

    class Stop(Exception):
        pass

    class Stream(list):
        def __enter__(self):
            return iter(self)

        def __exit__(self, *a):
            return False

    class Rules:
        def __init__(self):
            self.opened = 0

        def watch(self, *a, **k):
            self.opened += 1
            if self.opened == 1:
                return Stream([{"operationType": "invalidate"}])  # e.g. collection dropped by a reset
            raise Stop

        def find(self, q):
            return [doc("R-1")]

    class DB:
        rules = Rules()

    c = RulesCache(DB())
    with pytest.raises(Stop):
        c._watch()
    assert DB.rules.opened == 2 and [r.rule_id for r in c.all_active()] == ["R-1"]
