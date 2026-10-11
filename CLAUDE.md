# AgentShield

Self-evolving guardrail layer for agent-to-agent traffic. Hackathon project, built Oct 11 2026.

Before doing anything, read:
1. `docs/architecture.md` — the full design, data model, and milestone build order (Section 9)
2. `docs/event-guide.md` — hackathon rules; anything that breaks them is out of scope

Key rules:
- Build milestones in order (M0 → M6). Each one works end to end before the next starts.
- All persistence goes to the MongoDB Atlas Sandbox cluster via `MONGODB_URI`.
- Synthetic data only. Never store raw PII outside the `vault` collection.
- Clean-room build: write everything from scratch, no code from other private codebases.
- Terminal UI (Rich) is the interface. No Streamlit, no dashboard-as-product.
- Secrets live in `.env` (gitignored). Never commit keys.
- Git identity is repo-local: akhilvallala0115@gmail.com. Never change global git config.
