import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import Callable

from pymongo.errors import PyMongoError

from agentshield.types import Rule

log = logging.getLogger("agentshield.rules")


class RulesCache:
    def __init__(self, db):
        self._db = db
        self._rules: dict[str, Rule] = {}
        self._lock = threading.Lock()
        self.reload_count = 0
        self.on_change: Callable[[str], None] | None = None

    @staticmethod
    def _parse(doc: dict) -> Rule | None:
        try:
            return Rule.from_doc(doc)
        except (re.error, KeyError, TypeError) as e:
            log.error("skipping bad rule %s: %s", doc.get("rule_id"), e)
            return None

    def load(self) -> int:
        parsed = [(d["rule_id"], self._parse(d)) for d in self._db.rules.find({"status": "active"})]
        rules = {rule_id: rule for rule_id, rule in parsed if rule}
        with self._lock:
            self._rules = rules
        return len(rules)

    def upsert_doc(self, doc: dict) -> None:
        rule = self._parse(doc) if doc.get("status") == "active" else None
        if doc.get("status") == "active" and rule is None:
            return  # keep whatever version was live; one bad doc must not kill hot reload (I5)
        if rule is None and doc["rule_id"] not in self._rules:
            return  # e.g. a newly proposed rule: it was never live, nothing to remove
        with self._lock:
            if rule:
                self._rules[doc["rule_id"]] = rule
                msg = f"rule {doc['rule_id']} v{doc.get('version')} ACTIVE ({doc['entity_type']}) -> live"
            else:
                self._rules.pop(doc["rule_id"], None)
                msg = f"rule {doc['rule_id']} now {doc.get('status')} -> removed from live set"
            self.reload_count += 1
        log.info(msg)
        if self.on_change:
            self.on_change(msg)

    def rules_for(self, agent_pair: str) -> list[Rule]:
        with self._lock:
            return [r for r in self._rules.values() if r.agent_pair in ("*", agent_pair)]

    def all_active(self) -> list[Rule]:
        with self._lock:
            return list(self._rules.values())

    def start_watch(self) -> None:
        threading.Thread(target=self._watch, name="rules-watch", daemon=True).start()

    def _watch(self) -> None:
        pipeline = [{"$match": {"operationType": {"$in": ["insert", "update", "replace"]}}}]
        try:
            with self._db.rules.watch(pipeline, full_document="updateLookup") as stream:
                log.info("change stream open on rules")
                for change in stream:
                    if change.get("fullDocument"):
                        self.upsert_doc(change["fullDocument"])
        except PyMongoError as e:
            log.warning("change stream unavailable (%s); polling rules every 1s", e)
            self._poll()

    def _poll(self) -> None:
        since = datetime.now(timezone.utc)
        while True:
            time.sleep(1)
            for doc in self._db.rules.find({"updated_at": {"$gt": since}}):
                since = max(since, doc["updated_at"].replace(tzinfo=timezone.utc))
                self.upsert_doc(doc)
