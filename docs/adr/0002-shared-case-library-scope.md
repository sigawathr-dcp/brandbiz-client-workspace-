# 0002 — The case-study corpus is a shared `library` file scope

**Status:** Accepted (2026-08-25)
**Relates to:** D21/D22 (tenant isolation), D23 (`CLIENT_INTERNAL_ACCESS_ENABLED`), D24 (LINE Login — one workspace per LINE identity)

## Context

`POST /client/cases` scores a client's intake profile against the case-study corpus via
`rag_search.retrieve()`, which applies access rule R4 (`_scope_filter`): personal files to their
owner, `org` files to their tenant (`files.workspace_id IS NOT DISTINCT FROM <tenant>`).

The corpus was seeded by `scripts/seed_case_studies.py` as `scope="org"` rows stamped to the
`brandbiz-demo` workspace — correct for the booth era, when every attendee shared that one
workspace. D24 gives every LINE identity its **own** workspace. Under R4 none of them can see a
demo-workspace file, so retrieval returned zero chunks for every real client and the UI reported
"No case studies matched closely enough to show" — every `case_match_runs` row in production had
`match_count = 0`, and nothing had ever been scored. The weighted scorer and its 0.15 floor were
not the problem: with retrieval unblocked the same profiles score 0.24–0.76.

Two fixes were considered:

1. Un-stamp the corpus (`workspace_id = NULL`) and turn on `CLIENT_INTERNAL_ACCESS_ENABLED`, whose
   D23 widening admits the NULL pool to every tenant. Rejected: that flag also opens the whole
   internal app and internal knowledge base to client seats, and `line_plan.md` (Risks #2) records
   that it must stay **off** for a public LINE entry point. The flag is per-instance, not per-corpus.
2. Let `match_cases()` skip R4 for files attached to the workspace's agent. Rejected: it reverses
   the documented invariant that agent attachments narrow the corpus but never bypass ownership
   or scope (`rag_search._scope_filter`, `tests/unit/test_rag_search.py::TestScopeFilter`).

## Decision

- A third file scope, **`library`** (`app/models/file.py::LIBRARY_SCOPE`): the shared case corpus.
  `workspace_id` is always NULL.
- R4 gains a third, stand-alone disjunct: `files.scope = 'library'`. It is not tenant-gated and does
  not read `CLIENT_INTERNAL_ACCESS_ENABLED`. Mirrored wherever R4 is re-stated
  (`routers/files.py` list + single read, `services/agent.py::attach_file`).
- `library` is **seed-only**: `POST /files` rejects it (`routers/files.py`), so it is a read-shared,
  never a write-shared, surface. Only `scripts/seed_case_studies.py` stamps it.
- Migration `0065_case_library_scope` moves existing `case-study_*` files (and their
  `case_studies` catalog rows) to the new scope; the seeder writes it directly from now on.
- `POST /client/cases` reports `library_available: false` when retrieval saw zero chunks, and the
  Cases tab renders that as a setup fault ("The case library isn't available for this workspace
  yet") instead of the scoring outcome copy. A warning is logged server-side.

## Consequences

- Client-to-client isolation (`org`/`personal` rows) is unchanged — the new disjunct admits only
  rows explicitly seeded as library. Covered by `tests/integration/test_client_isolation.py::
  TestCaseLibraryScope` under both flag states.
- Staff see library files in the internal file browser (they always saw them in the demo tenant's
  view; now from any tenant).
- The agent-attachment step in the seeder still keys off the demo workspace's template agent, which
  every LINE workspace's agent is cloned from — the `workspace_slug` argument now only chooses that
  agent, not the files' tenant.
