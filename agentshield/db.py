import time
from functools import lru_cache

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.operations import SearchIndexModel

from agentshield.config import get_settings

INCIDENTS_VEC = "incidents_vec"
TAXONOMY_VEC = "taxonomy_vec"


@lru_cache
def get_db() -> Database:
    s = get_settings()
    client = MongoClient(s.resolved_mongodb_uri(), serverSelectionTimeoutMS=10_000, appname="agentshield")
    return client[s.mongodb_db]


def next_id(db: Database, name: str, prefix: str) -> str:
    doc = db.counters.find_one_and_update(
        {"_id": name}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER
    )
    return f"{prefix}-{doc['seq']:04d}"


def ensure_indexes(db: Database, dim: int) -> None:
    db.rules.create_index([("status", ASCENDING), ("scope.agent_pair", ASCENDING)])
    db.rules.create_index("rule_id", unique=True)
    db.traces.create_index([("audited", ASCENDING), ("ts", DESCENDING)])
    db.vault.create_index("expires_at", expireAfterSeconds=0)
    db.vault.create_index([("token", ASCENDING), ("session_id", ASCENDING)])
    db.incidents.create_index("incident_id", unique=True)
    db.incidents.create_index("span_sha256")
    db.evals.create_index("generation")
    db.playbooks.create_index("agent_pair", unique=True)
    db.taxonomy.create_index([("domain", ASCENDING), ("term", ASCENDING)], unique=True)
    _ensure_vector_index(db.incidents, INCIDENTS_VEC, dim, ["agent_pair", "entity_type_guess"])
    _ensure_vector_index(db.taxonomy, TAXONOMY_VEC, dim, ["domain"])


def _ensure_vector_index(coll: Collection, name: str, dim: int, filters: list[str]) -> None:
    if coll.name not in coll.database.list_collection_names():
        coll.database.create_collection(coll.name)
    if any(ix["name"] == name for ix in coll.list_search_indexes()):
        return
    fields = [{"type": "vector", "path": "embedding", "numDimensions": dim, "similarity": "cosine"}]
    fields += [{"type": "filter", "path": f} for f in filters]
    coll.create_search_index(SearchIndexModel(definition={"fields": fields}, name=name, type="vectorSearch"))


def wait_for_search_index(coll: Collection, name: str, timeout: float = 180) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for ix in coll.list_search_indexes(name):
            if ix.get("queryable"):
                return True
        time.sleep(3)
    return False
