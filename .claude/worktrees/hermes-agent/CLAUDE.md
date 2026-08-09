# Claude Code Instructions

This is the **Company AI Gateway** project. Always read `PLAN.md` before starting work.

## Source of truth

- **`PLAN.md`** — the implementation plan. Read it first. Section numbers in PLAN.md are stable references.
- **Decisions in PLAN.md Section 2 are final.** Do not propose changes to D1–D20 unless the user explicitly asks.
- **PLAN.md Section 11 (Out of Scope)** lists things you must NOT build, even if they seem helpful.

## Reference files (in `/reference/`)

- `schema.sql` — baseline DB schema. Used as input for Task 1.2 (convert to Alembic migration). Not deployed directly.
- `docker-compose.yml` — starting point for Task 1.1. Copy to root and adjust as needed.
- `policy_engine.py` — reference implementation for Task 2.2. Copy to `backend/app/services/policy_engine.py` and adapt to actual ORM models.

## How to work on a task

1. Open PLAN.md, find the task by number (e.g. Task 1.4)
2. Read its scope, files touched, and acceptance criteria
3. Cross-check against:
   - Section 7 (Critical Implementation Patterns) — must follow
   - Section 8 (Gotchas) — known traps for that area
4. Implement
5. Run tests if they exist; otherwise write a minimal one
6. Verify acceptance criteria
7. Mark the task checkbox (`☐` → `☑`) in PLAN.md and commit

## Coding conventions

- Python 3.12, type hints everywhere
- Async SQLAlchemy 2.0 style (no legacy `Query` API)
- Pydantic v2 for validation
- One responsibility per file in `app/services/`
- Tests live next to source under `backend/tests/{unit,integration}/`
- Never commit secrets; use `.env.example` as the contract

## Agent skills

### Issue tracker

Issues live in GitHub Issues (`Decomplica-Tech/Brandbiz-ai-gateway`), using the `gh` CLI. External PRs are not treated as a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

Default label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Communication style

- Be direct. Skip pleasantries.
- When stuck or unsure about a decision, stop and ask — don't guess.
- When finishing a task, give a one-paragraph summary + the diff stats. No long explanations of code that's already in the diff.

## After finishing each task

After marking a task checkbox (☐ → ☑) in PLAN.md, always run `/progress` to append an entry to `PROGRESS.md` before ending the response.

## Things to never do

- Never write plaintext message content to the database (PLAN.md Section 7.1)
- Never hardcode an LLM provider outside `app/llm/<provider>.py` (Section 7.2)
- Never modify or delete `audit_log` rows (Section 7.3)
- Never bypass `PolicyEngine.decide()` before an LLM call
- Never store keys, tokens, or passwords in git