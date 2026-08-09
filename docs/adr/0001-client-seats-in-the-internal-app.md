# 0001 — Client seats in the internal app (D23)

**Status:** Accepted
**Decision:** D23 (PLAN.md §2), amending D22

## Context

D21/D22 (Phase 5) built a bounded, tenant-isolated client-facing surface: `/client/*` and the
น้องภูมิ funnel. A client-workspace seat (`users.workspace_id` set) was walled off from the rest
of the gateway by two mechanisms — `require_internal` (403s any workspace-scoped user on ten
internal routers, applied at `include_router()` level in `main.py`) and `workspace_visibility_filter`
(narrows the "shared" read branch of `files`/`skills`/`agents` to same-tenant rows only).

The owner decided client-workspace seats — including anonymous seats minted by redeeming a
`/try/<token>` invite at an event booth, with no account and no verified identity — should be able
to use the full internal AI gateway app: the same features, and the same data, as internal staff.

## Decision

- **`CLIENT_INTERNAL_ACCESS_ENABLED`** (`settings.client_internal_access_enabled`), default `False`
  in code. One reversible switch; flipping it and restarting `backend-api`/`frontend-chat` is the
  entire deploy footprint.
- **`require_internal`** (`app/deps.py`) admits client seats when the flag is on; otherwise
  identical to the pre-D23 wall. Two ops/machine surfaces are carved out onto a new hard
  `require_staff` (and `require_staff_principal`, which accepts `gw_…` service keys) that never
  reads the flag: `hermes` (host telemetry + job logs — unscoped by user, not a product feature) and
  `automations` (outbound n8n side effects — real Gmail label writes, no UI). `require_client`
  (dead code, zero call sites) is removed.
- **`workspace_visibility_filter`** widens, when the flag is on, from `column IS NOT DISTINCT FROM
  workspace_ref` to `column IS NULL OR column IS NOT DISTINCT FROM workspace_ref` — the shared
  internal pool becomes readable by every tenant, while two different client workspaces still never
  match each other. For an internal user (`workspace_ref IS NULL`) both disjuncts collapse to the
  same clause, so this is a no-op for staff in both flag states.
- **Write-path stamping + private-by-default.** Every booth attendee shares one workspace
  (`redeem_invite` mints into `invite.workspace_id`), so workspace-grained read-widening alone does
  not separate attendee A from attendee B. `POST /files`, `create_skill`, and `create_agent` now
  stamp `workspace_id = user.workspace_id` (a no-op for staff — NULL either way) and force a client
  seat's `scope`/`visibility` to `"personal"` even when `"public"`/`"org"` was requested (coerced,
  not rejected — the agent-create DTO defaults to `"public"`). **Client-to-client isolation is the
  one invariant this decision does not relax.**
- `require_admin` additionally rejects any `workspace_id`-set user, closing off the possibility of a
  client seat ever holding `role="ADMIN"` (e.g. via an operator mis-click on `PATCH
  /admin/users/{id}`, which resolves its target by id alone). Cannot affect a real admin — every
  staff row has `workspace_id IS NULL`.

## Consequences — accepted, unmitigated

These were evaluated and accepted by the owner as the cost of "same features, same data as staff."
They are recorded here so a future reader does not mistake them for oversights:

- **Staff email addresses become visible** to client seats via the agent-list creator enrichment
  (`routers/agents.py`), which has no tenant filter.
- **The internal knowledge base — including synced Obsidian vault notes — is readable** by anyone
  holding a redeemed invite, with no verification of who they are. Real exposure is bounded today
  (the corpus is mostly scraped public case studies) but grows as genuine internal documents are
  uploaded.
- **Shared-pool reads are isolated per *workspace*, and the event's workspace is shared by every
  attendee.** Write-path private-by-default (above) prevents attendee-to-attendee leakage of what
  they *create*; it does not create per-attendee read partitions of the shared pool — every
  attendee reads the same internal corpus and each other's absence of writes, which is the intended
  shape, not a gap.
- **`conversations`, `messages`, `agent_tasks`, and `studio_generations` carry no `workspace_id`
  column at all.** A client seat's content is user-scoped (never leaks to another user) but is
  indistinguishable from staff content for retention, `/reveal`, and audit-log purposes. Adding a
  column and a migration was judged out of proportion to this decision; revisit if retention policy
  ever needs to treat client content differently from staff content.
- **A client seat's น้องภูมิ intake conversation surfaces in the internal `/chat` sidebar** once the
  flag is on, and can be continued there — without the persona's system prompt, since that's
  injected by `/client/chat`, not `/chat`. Cosmetic, not a data leak (still the same user's own
  conversation).

## Alternatives considered

- **A flag list, one per router**, instead of one flag with two hard carve-outs. Rejected: the owner
  made one decision, not ten — a flag per router is configurable in a dimension nobody asked for,
  and is more states to reason about mid-event.
- **A new, separate visibility-filter helper, editing all 5 call sites individually** instead of
  making the existing `workspace_visibility_filter` flag-aware in one place. Rejected: strictly
  larger diff, and reopens "did we widen every call site?" as a live question — exactly the bug
  class the existing `test_workspace_visibility.py` regression suite exists to catch.
- **One workspace minted per invite**, instead of every booth attendee sharing one workspace with
  private-by-default writes. Rejected: `workspaces.token_budget_limit` — the pooled event
  cost-control backstop (`PolicyEngine.decide()` Rule 5) — is per-workspace. Splintering workspaces
  per attendee would eliminate the one property the pooled cap exists to provide.

## Related

- PLAN.md §2, decisions D21, D22 (superseded in part), D23.
- `backend/tests/unit/test_require_internal.py`, `test_workspace_visibility.py`,
  `test_workspace_stamping.py`, `test_quota_precedence.py`, `test_deps.py`.
