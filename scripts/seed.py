import argparse
import hashlib
from datetime import datetime, timezone

from rich.console import Console

from agentshield.config import get_settings
from agentshield.db import INCIDENTS_VEC, TAXONOMY_VEC, ensure_indexes, get_db, next_id, wait_for_search_index
from agentshield.embeddings import embed
from agentshield.synth_data import (AGENT_PROFILES, DEFAULT_PLAYBOOKS, HISTORICAL_INCIDENTS, SEED_TAXONOMY,
                                    make_corpus_clean, make_eval_set)

console = Console()
RESET = ["eval_set", "corpus_clean", "playbooks", "agent_profiles", "taxonomy", "incidents",
         "rules", "traces", "vault", "evals", "counters"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="drop all AgentShield collections first")
    args = ap.parse_args()
    s, db = get_settings(), get_db()
    now = datetime.now(timezone.utc)

    if args.reset:
        for name in RESET:
            db.drop_collection(name)
        console.print("[yellow]dropped existing collections[/]")

    ensure_indexes(db, s.embedding_dim)

    db.eval_set.delete_many({})
    db.eval_set.insert_many(make_eval_set(300))
    db.corpus_clean.delete_many({})
    db.corpus_clean.insert_many(make_corpus_clean(500))

    for pb in DEFAULT_PLAYBOOKS:
        db.playbooks.replace_one({"agent_pair": pb["agent_pair"]}, {**pb, "updated_from_incident": None}, upsert=True)
    for prof in AGENT_PROFILES:
        db.agent_profiles.replace_one({"agent_id": prof["agent_id"]}, prof, upsert=True)

    tax_vecs = embed([f"{t['term']}: {t['definition']}" for t in SEED_TAXONOMY])
    for t, v in zip(SEED_TAXONOMY, tax_vecs):
        db.taxonomy.replace_one({"domain": t["domain"], "term": t["term"]}, {**t, "embedding": v}, upsert=True)

    if db.incidents.count_documents({"seeded": True}) == 0:
        vecs = embed([f"{h['entity_type_guess']}: {h['excerpt_redacted']}" for h in HISTORICAL_INCIDENTS])
        for h, v in zip(HISTORICAL_INCIDENTS, vecs):
            db.incidents.insert_one({
                **h, "incident_id": next_id(db, "incident", "I"), "ts": now, "direction": "request",
                "span_sha256": hashlib.sha256(h["shape"].encode()).hexdigest(), "missed_by": ["L1", "L2"],
                "auditor_confidence": 0.9, "embedding": v, "seeded": True})

    console.print("waiting for vector indexes to be queryable...")
    ok = wait_for_search_index(db.incidents, INCIDENTS_VEC) and wait_for_search_index(db.taxonomy, TAXONOMY_VEC)
    console.print(f"[green]seeded[/]: eval_set={db.eval_set.count_documents({})} "
                  f"corpus_clean={db.corpus_clean.count_documents({})} "
                  f"incidents={db.incidents.count_documents({})} vector_indexes_ready={ok}")


if __name__ == "__main__":
    main()
