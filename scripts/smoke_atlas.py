"""Checks every Atlas and API capability AgentShield depends on (addendum 15.11)."""
import threading
import time

import httpx
from pymongo.operations import SearchIndexModel
from rich.console import Console

from agentshield.config import get_settings
from agentshield.db import get_db, wait_for_search_index

console = Console()


def check(name, fn):
    try:
        detail = fn()
        console.print(f"[green]PASS[/] {name}" + (f"  [dim]{detail}[/]" if detail else ""))
        return True
    except Exception as e:  # noqa: BLE001 - smoke test reports everything
        console.print(f"[red]FAIL[/] {name}: {type(e).__name__}: {e}")
        return False


def main():
    s = get_settings()
    db = get_db()
    db.drop_collection("_smoke")
    scratch = db["_smoke"]

    check("connect + ping", lambda: db.command("ping"))
    check("insert + read", lambda: scratch.insert_one({"x": 1}).inserted_id and scratch.find_one({"x": 1})["x"])

    def change_stream():
        seen = []
        with scratch.watch(max_await_time_ms=2000) as stream:
            t = threading.Timer(1.0, lambda: scratch.insert_one({"y": 2}))
            t.start()
            for change in stream:
                seen.append(change["operationType"])
                break
        return f"saw {seen}"

    check("change stream", change_stream)
    check("TTL index", lambda: scratch.create_index("expires_at", expireAfterSeconds=0))

    def vector_search():
        dim = 4
        scratch.create_search_index(SearchIndexModel(
            definition={"fields": [{"type": "vector", "path": "v", "numDimensions": dim, "similarity": "cosine"}]},
            name="smoke_vec", type="vectorSearch"))
        scratch.insert_one({"v": [0.1, 0.2, 0.3, 0.4]})
        t0 = time.monotonic()
        if not wait_for_search_index(scratch, "smoke_vec", timeout=180):
            raise TimeoutError("index never became queryable")
        res = list(scratch.aggregate([{"$vectorSearch": {"index": "smoke_vec", "path": "v",
                    "queryVector": [0.1, 0.2, 0.3, 0.4], "numCandidates": 10, "limit": 1}}]))
        return f"{len(res)} hit(s), index ready in {time.monotonic() - t0:.0f}s"

    check("vector search index", vector_search)

    def voyage():
        for base in [s.voyage_base_url, "https://api.voyageai.com/v1", "https://ai.mongodb.com/v1"]:
            r = httpx.post(f"{base.rstrip('/')}/embeddings",
                           headers={"Authorization": f"Bearer {s.voyage_api_key}"},
                           json={"input": ["hello"], "model": s.voyage_model, "input_type": "document"}, timeout=30)
            if r.status_code == 200:
                n = len(r.json()["data"][0]["embedding"])
                if n != s.embedding_dim:
                    raise ValueError(f"dim {n} != EMBEDDING_DIM {s.embedding_dim}")
                return f"works at {base} (dim {n}); set VOYAGE_BASE_URL={base} in .env if different"
        raise RuntimeError(f"Voyage key rejected at all endpoints (last status {r.status_code})")

    check("voyage embeddings", voyage)

    def openai_call():
        from openai import OpenAI
        r = OpenAI(api_key=s.llm_api_key).chat.completions.create(
            model=s.llm_model_reasoning, messages=[{"role": "user", "content": "Reply with: ok"}])
        return r.choices[0].message.content.strip()[:20]

    check("openai chat", openai_call)
    db.drop_collection("_smoke")


if __name__ == "__main__":
    main()
