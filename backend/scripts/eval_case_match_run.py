"""
backend/scripts/eval_case_match_run.py

Runs app.services.case_match.match_cases() — the exact pipeline behind
POST /client/cases — against every golden profile in profiles.json, joins
the results against backend/eval/case_match/labels.csv, and prints/writes
a ranking-quality + calibration report (app.eval.report).

Two modes, both run by default (--mode both):
  production — rag_top_k / rag_max_distance from settings (or --top-k /
               --max-distance overrides): what a client's Cases tab
               actually shows.
  deep       — a wide pool (--pool-chunks, default 500) with the distance
               cutoff disabled: what the retriever could reach at all.
               rag_top_k is a CHUNK budget, not a case budget (a case with
               2 chunks eats 2 of 5 slots), so production-mode recall
               cannot be measured on its own — deep mode ranks the whole
               eligible corpus so recall is exact, and gives every
               (profile, case) pair a score for calibration.

Impersonates a seat of --workspace-slug with no HTTP and no auth: prefers
an existing redeemed seat, else a transient in-memory User (never added to
the session) with that workspace_id. app.tools.rag_search._scope_filter
only ever reads user.id / user.workspace_id, so this exercises the same
scope filter production uses. --as-preview-staff instead impersonates an
internal staff member (user.workspace_id=None) previewing the funnel —
the B1 regression scenario — as a standing check, not just a one-off
manual click-through.

Preflight aborts on corpus-health problems (duplicate filenames,
unprocessed/zero-chunk/unembedded files) exactly like
eval_case_match_export.py. Label-vs-corpus mismatches (an unknown filename
in labels.csv, a case with zero judgements, sha drift vs the committed
manifest) are reported as warnings, not aborts — a partially-stale label
set shouldn't block every future run, but the report says so loudly.

Run from inside the backend-api container:
    docker compose exec backend-api sh -c "cd /app && PYTHONPATH=/app \\
        python scripts/eval_case_match_run.py --workspace-slug brandbiz-demo \\
        --labels /app/eval/case_match/labels.placeholder.csv --mode both"
"""
import argparse
import asyncio
import json
import math
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.eval import corpus as corpus_mod
from app.eval import goldens
from app.eval import report as report_mod
from app.eval.query_variants import VARIANTS
from app.models.user import User
from app.models.workspace import Workspace
from app.services import agent as agent_svc
from app.services import case_match as case_match_svc
from app.services import workspace as workspace_svc

DEFAULT_POOL_CHUNKS = 500

# (base_profile_id, variant_profile_id, field_that_differs) — see
# backend/eval/case_match/profiles.json's P01* contrast cluster.
SENSITIVITY_PAIRS: list[tuple[str, str, str]] = [
    ("P01-cafe-expand", "P01b-goal-differs", "goal"),
    ("P01-cafe-expand", "P01c-challenge-differs", "challenge"),
    ("P01-cafe-expand", "P01d-budget-differs", "budget"),
    ("P01-cafe-expand", "P01e-stage-differs", "stage"),
    ("P01-cafe-expand", "P01f-audience-differs", "audience"),
]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workspace-slug", default="brandbiz-demo")
    p.add_argument("--profiles", default=str(goldens.DEFAULT_PROFILES_PATH))
    p.add_argument("--labels", default=str(goldens.DEFAULT_LABELS_PATH))
    p.add_argument("--manifest", default=None, help="corpus_manifest.csv, for sha-drift reporting")
    p.add_argument("--mode", choices=["production", "deep", "both"], default="both")
    p.add_argument("--top-k", type=int, default=None, help="production-mode override for rag_top_k")
    p.add_argument("--max-distance", type=float, default=None, help="production-mode override for rag_max_distance")
    p.add_argument("--pool-chunks", type=int, default=DEFAULT_POOL_CHUNKS)
    p.add_argument("--query-variant", default="prod", choices=list(VARIANTS))
    p.add_argument("--baseline", default=None, help="path to a prior run's run-<ts>.json to diff against")
    p.add_argument("--out-dir", default=None, help="write report-<ts>.md and run-<ts>.json here")
    p.add_argument("--as-preview-staff", action="store_true", help="reproduce the B1 scenario: staff previewer")
    return p.parse_args()


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5
        )
        return out.stdout.strip() or None
    except Exception:
        return None


async def _resolve_workspace(session, slug: str) -> Workspace:
    workspace = (await session.execute(select(Workspace).where(Workspace.slug == slug))).scalar_one_or_none()
    if workspace is None:
        print(f"ERROR: no workspace with slug {slug!r}. Run scripts/seed_client_demo.py first.")
        sys.exit(1)
    return workspace


async def _resolve_agent_file_ids(session, workspace: Workspace) -> list[uuid.UUID]:
    agent = await workspace_svc.get_workspace_agent(session, workspace.id)
    if agent is None:
        print(f"ERROR: workspace {workspace.slug!r} has no published agent assigned.")
        sys.exit(1)
    file_ids = await agent_svc.get_agent_file_ids(session, agent.id)
    if not file_ids:
        print(f"ERROR: agent {agent.name!r} has no attached knowledge files.")
        sys.exit(1)
    return file_ids


async def _resolve_user(session, workspace: Workspace, as_preview_staff: bool) -> tuple[User, bool]:
    if as_preview_staff:
        return (
            User(id=uuid.uuid4(), google_email="preview-staff@internal.invalid", workspace_id=None, role="L1"),
            True,
        )
    existing = (
        await session.execute(
            select(User).where(User.workspace_id == workspace.id).order_by(User.created_at.asc())
        )
    ).scalars().first()
    if existing is not None:
        return existing, False
    return (
        User(
            id=uuid.uuid4(),
            google_email=f"eval-harness@{workspace.slug}.client.invalid",
            workspace_id=workspace.id,
            role="L1",
        ),
        False,
    )


def _flatten_from_run_json(run_json: dict) -> dict[str, float]:
    """Rebuild the flat baseline-diff keys from a previously written
    run-<ts>.json (dataclasses.asdict'd RunReport). Mirrors
    app.eval.report._flatten_aggregate's key naming."""
    flat: dict[str, float] = {}
    for mode_key, prefix in (("production_aggregate", "production"), ("deep_aggregate", "deep")):
        agg = run_json[mode_key]
        for group in ("mean_precision_at_k", "mean_recall_at_k", "mean_strong_recall_at_k", "mean_ndcg_at_k"):
            for k, v in agg[group].items():
                short = {"mean_precision_at_k": "mean_precision_at", "mean_recall_at_k": "mean_recall_at",
                         "mean_strong_recall_at_k": "mean_strong_recall_at", "mean_ndcg_at_k": "mean_ndcg_at"}[group]
                flat[f"{prefix}.{short}_{k}"] = v
        flat[f"{prefix}.mean_mrr"] = agg["mean_mrr"]
        flat[f"{prefix}.mean_n_returned"] = agg["mean_n_returned"]
    return flat


async def _run_mode(
    session, user, agent_file_ids, workspace, profile, query, *, top_k, max_distance
) -> case_match_svc.CaseMatchRun:
    return await case_match_svc.match_cases(
        session,
        user,
        profile.fields,
        agent_file_ids=agent_file_ids,
        effective_workspace_id=workspace.id,
        top_k=top_k,
        max_distance=max_distance,
        query=query,
        include_cards=False,
        strict=True,
    )


async def main() -> None:
    args = _parse_args()
    from app.db import session_factory

    async with session_factory() as session:
        workspace = await _resolve_workspace(session, args.workspace_slug)
        agent_file_ids = await _resolve_agent_file_ids(session, workspace)

        print("--- Corpus preflight ---")
        corpus_report = await corpus_mod.load_corpus(session, agent_file_ids)
        if not corpus_report.is_healthy():
            print("ERROR: corpus is not eval-ready:")
            for problem in corpus_report.problems():
                print(f"  - {problem}")
            sys.exit(1)
        filename_map = corpus_mod.resolve_filenames(corpus_report)
        all_filenames = sorted(filename_map)
        print(f"  OK: {len(all_filenames)} files eval-ready.")

        manifest = corpus_mod.load_manifest(args.manifest) if args.manifest else {}
        drifted = corpus_mod.sha_drift(corpus_report, manifest) if manifest else []
        if drifted:
            print(f"  WARNING: {len(drifted)} file(s) drifted since the manifest was captured — labels may be stale:")
            for fn in drifted:
                print(f"    - {fn}")

        try:
            labels = goldens.load_labels(args.labels)
        except FileNotFoundError:
            print(
                f"ERROR: labels file not found: {args.labels}\n"
                f"  Run scripts/eval_case_match_export.py --bootstrap-labels ... first "
                f"to unblock plumbing tests, or scripts/eval_case_match_import.py once a "
                f"consultant has labeled the sheet."
            )
            sys.exit(1)

        unknown_label_files = {fn for (_, fn) in labels.rows if fn not in filename_map}
        if unknown_label_files:
            print(f"  WARNING: labels reference {len(unknown_label_files)} filename(s) not in the live corpus:")
            for fn in sorted(unknown_label_files):
                print(f"    - {fn}")

        profiles = goldens.load_profiles(args.profiles)
        seat, is_preview = await _resolve_user(session, workspace, args.as_preview_staff)
        print(f"\n--- Impersonating {seat.google_email} (workspace={workspace.slug}, preview={is_preview}) ---")

        query_builder = VARIANTS[args.query_variant]
        top_k = args.top_k if args.top_k is not None else settings.rag_top_k
        max_distance = args.max_distance if args.max_distance is not None else settings.rag_max_distance

        production_results: list[report_mod.ProfileResult] = []
        deep_results: dict[str, report_mod.ProfileResult] = {}
        scores_by_label: dict[int, list[float]] = {0: [], 1: [], 2: []}

        for profile in profiles:
            query = query_builder(profile.fields)
            all_labels = [labels.label_for(profile.id, fn) for fn in all_filenames]
            total_relevant = sum(1 for l in all_labels if l >= 1)
            total_strong = sum(1 for l in all_labels if l >= 2)
            judged_count = len(labels.judged_filenames(profile.id) & set(all_filenames))

            if args.mode in ("production", "both"):
                run = await _run_mode(
                    session, seat, agent_file_ids, workspace, profile, query,
                    top_k=top_k, max_distance=max_distance,
                )
                ranked_filenames = [r.filename for r in run.results]
                production_results.append(
                    report_mod.ProfileResult(
                        profile_id=profile.id, label_th=profile.label_th,
                        ranked_filenames=ranked_filenames,
                        ranked_labels=[labels.label_for(profile.id, fn) for fn in ranked_filenames],
                        all_labels=all_labels, total_relevant=total_relevant, total_strong=total_strong,
                        judged_count=judged_count, corpus_size=len(all_filenames),
                    )
                )

            if args.mode in ("deep", "both"):
                run = await _run_mode(
                    session, seat, agent_file_ids, workspace, profile, query,
                    top_k=args.pool_chunks, max_distance=math.inf,
                )
                ranked_filenames = [r.filename for r in run.results]
                ranked_labels = [labels.label_for(profile.id, fn) for fn in ranked_filenames]
                deep_results[profile.id] = report_mod.ProfileResult(
                    profile_id=profile.id, label_th=profile.label_th,
                    ranked_filenames=ranked_filenames, ranked_labels=ranked_labels,
                    all_labels=all_labels, total_relevant=total_relevant, total_strong=total_strong,
                    judged_count=judged_count, corpus_size=len(all_filenames),
                )
                for r, label in zip(run.results, ranked_labels):
                    scores_by_label.setdefault(label, []).append(r.score)

            print(f"  {profile.id}: done")

        production_rows = [report_mod.compute_profile_metrics(r) for r in production_results]
        deep_rows = [report_mod.compute_profile_metrics(r) for r in deep_results.values()]
        production_aggregate = report_mod.aggregate(production_rows)
        deep_aggregate = report_mod.aggregate(deep_rows)

        failures = report_mod.worst_failures(production_results, deep_results) if production_results else []

        available_ids = {p.id for p in profiles}
        pairs = [(b, v, f) for (b, v, f) in SENSITIVITY_PAIRS if b in available_ids and v in available_ids]
        deep_rankings = {pid: r.ranked_filenames for pid, r in deep_results.items()}
        sensitivity = report_mod.compute_sensitivity(pairs, deep_rankings) if deep_results else []

        calibration = report_mod.compute_calibration(scores_by_label)

        total_pairs = len(profiles) * len(all_filenames)
        judged_pairs = sum(
            r.judged_count for r in (production_results or list(deep_results.values()))
        )
        n_strong = sum(1 for pid in [p.id for p in profiles] for fn in all_filenames if labels.label_for(pid, fn) == 2)
        n_some = sum(1 for pid in [p.id for p in profiles] for fn in all_filenames if labels.label_for(pid, fn) == 1)
        n_none = total_pairs - n_strong - n_some

        report = report_mod.RunReport(
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            config=report_mod.RunConfig(
                rag_top_k=top_k, rag_max_distance=max_distance, embed_model=settings.llm_embed_model,
                chunk_tokens=settings.rag_chunk_tokens, chunk_overlap=settings.rag_chunk_overlap,
                query_variant=args.query_variant, workspace_slug=workspace.slug,
                impersonated_user=seat.google_email, is_preview_impersonation=is_preview, git_sha=_git_sha(),
            ),
            corpus=report_mod.CorpusSummary(
                file_count=len(all_filenames),
                chunk_count=sum(f.chunk_count for f in corpus_report.files),
                unembedded_file_count=len(corpus_report.unembedded_chunk_files),
                sha_drift_count=len(drifted),
            ),
            labels=report_mod.LabelSummary(
                source=str(args.labels), is_placeholder=labels.is_placeholder,
                coverage_pct=(judged_pairs / total_pairs) if total_pairs else 0.0,
                n_strong=n_strong, n_some=n_some, n_none=n_none,
            ),
            production_rows=production_rows, production_aggregate=production_aggregate,
            deep_rows=deep_rows, deep_aggregate=deep_aggregate,
            failures=failures, sensitivity=sensitivity, calibration=calibration,
        )

    print("\n" + report_mod.render_markdown(report))

    if args.baseline:
        baseline_json = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        baseline_flat = _flatten_from_run_json(baseline_json)
        diffs = report_mod.diff_against_baseline(report, baseline_flat)
        print("\n## Baseline diff")
        for key, d in sorted(diffs.items()):
            sign = "+" if d["delta"] >= 0 else ""
            print(f"  {key}: {d['current']:.4f} (baseline {d['baseline']:.4f}, {sign}{d['delta']:.4f})")

    if args.out_dir:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        (out_dir / f"report-{ts}.md").write_text(report_mod.render_markdown(report), encoding="utf-8")
        (out_dir / f"run-{ts}.json").write_text(
            json.dumps(report_mod.to_json_dict(report), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nWrote {out_dir / f'report-{ts}.md'} and run-{ts}.json")


if __name__ == "__main__":
    asyncio.run(main())
