# AgentShield public demo API

A small stateless service behind the "Run on the real engine" toggle on
[akhilvallala1.github.io](https://akhilvallala1.github.io).

It runs only the inline fast path, the same `agentshield.pipeline` and `agentshield.ner`
code the gateway uses:

- **L1:** learned regex rules. Ships with the adjuster-badge rule that was still active at the
  end of the recorded demo run. The policy-number rule from that run was retired for firing on
  product codes, so it is not included.
- **L2:** Presidio with spaCy `en_core_web_sm`.
- **Policy:** the `intake->claims` playbook. SSNs block the whole message, cards are masked, and
  names, emails, phones and badges are tokenized.

What it deliberately does not do:

- No LLM auditor, no synthesizer, no MongoDB. Public traffic can never create or retire a rule.
- No logging of request bodies (`--no-access-log`), and the NER cache is off, so raw text is not
  kept in memory between requests.
- Token-to-value mappings are never returned, only spans and the redacted text.

Limits: 2,000 characters per message, 20 requests per minute per IP, 300 per minute overall,
CORS locked to the portfolio site, max 2 instances.

## API

```
POST /redact   {"text": "..."}
-> {"output": "...", "blocked": false, "blocked_types": [], "latency_ms": 12.3,
    "detections": [{"entity_type": "PERSON", "start": 12, "end": 26, "layer": "L2", "rule_id": null}]}
GET  /healthz
```

## Run locally

```
pip install fastapi uvicorn presidio-analyzer spacy && python -m spacy download en_core_web_sm
ALLOWED_ORIGINS=http://localhost:8000 uvicorn demo_api.app:app --port 8080
pytest tests/test_demo_api.py
```

## Deploy to Cloud Run

```
gcloud auth login
PROJECT_ID=your-project ./demo_api/deploy.sh
```

Runs with 1 GiB, 1 vCPU, min 1 instance (no cold starts), max 2. Expect roughly $10 to $15 a month
for the idle minimum instance. Set `--min-instances 0` in `deploy.sh` to pay only per request,
at the cost of a cold start of several seconds.
