import logging
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

    def load(self) -> int:
        rules = {d["rule_id"]: Rule.from_doc(d) for d in self._db.rules.find({"status": "active"})}
        with self._lock:
            self._rules = rules
        return len(rules)

    def upsert_doc(self, doc: dict) -> None:
        with self._lock:
            if doc.get("status") == "active":
                self._rules[doc["rule_id"]] = Rule.from_doc(doc)
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
