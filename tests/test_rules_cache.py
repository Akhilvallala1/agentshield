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
