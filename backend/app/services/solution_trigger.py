"""
app/services/solution_trigger.py

Post-diagnosis recommendation rules — the third thing an intake answer can
be, alongside "scores the case match" (use_mode "match") and "shapes scope
and pricing" (use_mode "feasibility").

Why this is not part of the matcher. Questions for DSMEs.xlsx adds
`own_commerce` (how much revenue depends on external, GP-charging
platforms) and states its use plainly: "ไม่ใช้คำนวณ Similarity Score /
Case Matching โดยตรง ใช้เป็น Trigger หลัง Diagnosis". Folding it into
case_score would be wrong twice over — it would dilute six weights that
sum to exactly 1.000, and it would rank case studies by a fact about the
client's P&L rather than by whether the case solves their problem. A brand
paying 30% GP is not thereby a better fit for any particular case; it is a
brand that should be shown an owned-commerce route in its PLAN.

Why a rule and not a prompt line. The client's `own_commerce` answer
already reaches the drafting model for free, as one more line of client
context (plan.py::_build_drafting_prompt). Leaving it at that would make
the recommendation a coin flip: sometimes the model notices the GP problem,
sometimes it writes a social-content plan and never mentions it. The
sheet's rule is a conditional over three fields with a definite answer, so
it is evaluated here, deterministically, and the model is handed the
conclusion to write up rather than the premises to reason from. That is the
same division of labour as the intake itself (see client_intake's docstring
on why advancing a step is a DB write, not an LLM call).

Pure: no DB, no I/O, no LLM. Takes the loaded profile, returns directives.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.services import case_taxonomy
from app.services.client_intake import INTAKE_SCRIPT

# {dimension: {token, ...}} for trigger questions only. Deliberately a
# SEPARATE namespace from case_taxonomy.VOCAB: that one is the vocabulary
# shared with the corpus (`case_study_tags.tag_value`), and no case study
# should ever be tagged with a fact about a client's platform dependency.
# case_taxonomy.validate_tag() therefore rejects these tokens, which is
# correct — it guards corpus ingest, not this.
TRIGGER_VOCAB: dict[str, frozenset[str]] = {
    step["match_tag"]: frozenset(o["tag"] for o in step["options"])
    for step in INTAKE_SCRIPT
    if step["use_mode"] == "solution_trigger" and step["match_tag"]
}

_VALUE_TO_TAG: dict[str, dict[str, str]] = {
    step["match_tag"]: {o["value"]: o["tag"] for o in step["options"]}
    for step in INTAKE_SCRIPT
    if step["use_mode"] == "solution_trigger" and step["match_tag"]
}

# Answers to `own_commerce` that fire the owned-commerce recommendation.
# "platform_mixed" is deliberately excluded: a brand already running its own
# channel alongside the platforms has made the choice, and telling it to
# build what it has reads as boilerplate. "owned_dominant" and
# "not_applicable" are self-evidently out.
_OWN_COMMERCE_FIRES = frozenset({"platform_heavy", "no_owned_channel"})


@dataclass(frozen=True)
class Trigger:
    """One fired rule. `directive` is written to be pasted into the drafting
    prompt verbatim; `reason` is the audit trail — which answers fired it —
    so a reviewer can tell a rule from a model's invention."""

    key: str
    reason: str
    directive: str


def tag_for_value(dimension: str, value: str) -> str | None:
    """Resolve a stored answer back to its token, or None when the client
    typed free text (which no chip value matches)."""
    return _VALUE_TO_TAG.get(dimension, {}).get(value)


def _scoring_tag(fields: Mapping[str, str], dimension: str) -> str | None:
    value = fields.get(dimension)
    if value is None:
        return None
    return case_taxonomy.tag_for_value(dimension, value)


def _own_commerce_directive(asset_tag: str | None, objective_tag: str | None) -> str:
    """The sheet requires the recommendation be shaded by Existing Assets /
    Channel and Business Objective ("โดยดู Existing Assets / Channel และ
    Business Objective ประกอบ") rather than fired as one fixed sentence.

    Asset channel decides WHAT to build — there is a real difference between
    a brand with a dormant LINE OA (activate it), one with a CRM already
    (connect it), and one with no owned base at all (start from zero).
    Objective decides HOW HARD to push it: when the client's own stated
    objective is first-party data, retention or O2O, owned commerce IS the
    objective and should lead the plan. When they came for awareness or a
    launch, it must not hijack the plan they asked for.
    """
    build = {
        "line_oa_no_crm": (
            "The client already has a LINE OA but no CRM behind it, so the "
            "cheapest route is activating that OA — LINE Microsite plus "
            "first-party data capture — not a new platform."
        ),
        "has_crm": (
            "The client already has a customer database / CRM, so propose "
            "connecting owned commerce to it rather than building a second "
            "data store."
        ),
        "web_plus_social": (
            "The client already has a website and social presence, so the gap "
            "is transactional and data capture on assets they own, not reach."
        ),
        "multi_channel_siloed": (
            "The client has several channels with siloed data, so owned "
            "commerce should be positioned as the place that data converges."
        ),
        "offline_touchpoint": (
            "The client has offline touchpoints, so tie owned commerce to an "
            "online-to-offline loop rather than treating it as a separate "
            "e-commerce build."
        ),
    }.get(asset_tag or "", (
        "The client has no meaningful owned customer base yet, so treat "
        "owned commerce as foundational work with its own phase in the "
        "timeline."
    ))

    if objective_tag in {"lead_data", "retention_loyalty", "o2o"}:
        stance = (
            "This aligns with the objective the client already stated, so make "
            "it a leading workstream of the plan."
        )
    elif objective_tag in {"awareness", "launch", "engagement_community"}:
        stance = (
            "The client's stated objective is reach, not retention, so include "
            "this as supporting foundation work — it must NOT displace the "
            "objective they asked for."
        )
    else:
        stance = (
            "Include it as a distinct workstream, sized against the stated "
            "objective rather than in place of it."
        )

    return (
        "OWNED COMMERCE: this client's revenue depends on external platforms "
        "that charge GP / commission, which caps their margin and denies them "
        "first-party data. The plan must address this — propose an owned sales "
        "channel (LINE Microsite / owned e-commerce) with CRM behind it. "
        + build + " " + stance
    )


def evaluate(fields: Mapping[str, str]) -> tuple[Trigger, ...]:
    """Evaluate every solution-trigger rule against a loaded intake profile.

    `fields` is {field_key: english value}, as produced by
    routers/client.py::_load_fields. A field absent from the mapping is
    unanswered; a value that resolves to no token is free text. Both are
    treated as "do not fire": a rule that recommends restructuring how a
    client sells needs an explicit answer behind it, and guessing from free
    text would put a recommendation in the plan the client never triggered.
    """
    triggers: list[Trigger] = []

    own = fields.get("own_commerce")
    own_tag = tag_for_value("own_commerce", own) if own is not None else None
    if own_tag in _OWN_COMMERCE_FIRES:
        # asset_channel and objective are SCORING dimensions, so their tokens
        # come from case_taxonomy, not from this module's TRIGGER_VOCAB.
        asset_tag = _scoring_tag(fields, "asset_channel")
        objective_tag = _scoring_tag(fields, "objective")
        triggers.append(Trigger(
            key="own_commerce",
            reason=(
                f"own_commerce={own_tag}"
                f", asset_channel={asset_tag or 'unknown'}"
                f", objective={objective_tag or 'unknown'}"
            ),
            directive=_own_commerce_directive(asset_tag, objective_tag),
        ))

    return tuple(triggers)
