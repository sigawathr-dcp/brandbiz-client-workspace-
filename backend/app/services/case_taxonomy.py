"""
app/services/case_taxonomy.py

The controlled vocabulary shared by the two sides of the weighted matcher:
the intake option a client picked (`intake_options.tag_value`) and the tag a
case study carries (`case_study_tags.tag_value`). Both are the SAME token
namespace, per dimension — that is the whole point. If the two sides drifted
apart the scorer would silently return zero for a dimension rather than
fail, so `VOCAB` is derived from INTAKE_SCRIPT rather than transcribed from
it, and `validate_tag()` is the only sanctioned way to admit a corpus tag.

Dimensions come from the interview's `match_tag` column — six scoring
dimensions (industry, stage, audience, challenge, asset_channel, objective).
`timeframe` and `budget` are `use_mode = "feasibility"` and deliberately
absent: they shape scope and pricing downstream, never which cases surface.

INDUSTRY_ADJACENCY exists because industry carries the joint-heaviest weight
(0.25) while the sheet's own note says it "ไม่ใช่เงื่อนไขตายตัว" — not a hard
condition. With a binary match, a same-industry case that solves the wrong
problem outranks an adjacent-industry case that solves exactly the right
one. Adjacency gives the latter partial credit instead.
"""
from __future__ import annotations

from app.services.client_intake import INTAKE_SCRIPT

# {dimension: {token, ...}} — every token a client answer or a corpus tag may
# legally use, built from the live script so the two can never disagree.
VOCAB: dict[str, frozenset[str]] = {
    step["match_tag"]: frozenset(o["tag"] for o in step["options"])
    for step in INTAKE_SCRIPT
    if step["use_mode"] == "match" and step["match_tag"]
}

# Scoring dimensions in interview order — the order breakdowns render in.
DIMENSIONS: tuple[str, ...] = tuple(VOCAB)

# {english chip value: token}, per dimension. Answers are stored as the
# English IntakeOption.value (app/routers/client.py::_load_fields), so the
# scorer needs this to get from a loaded profile back to a token. Free text
# is absent by construction and resolves to None.
_VALUE_TO_TAG: dict[str, dict[str, str]] = {
    step["match_tag"]: {o["value"]: o["tag"] for o in step["options"]}
    for step in INTAKE_SCRIPT
    if step["use_mode"] == "match" and step["match_tag"]
}

# Symmetric neighbour sets. Closed under symmetry by _symmetrise() below, so
# each pair only has to be written once here.
_ADJACENCY_SEED: dict[str, set[str]] = {
    # Personal-care and ingestible-wellness brands share the same influencer
    # /review /before-after playbook and the same regulatory caution.
    "beauty": {"health_supplement", "retail_fmcg"},
    # Supplements sit between beauty's content playbook and FMCG's
    # distribution problem.
    "health_supplement": {"food_beverage", "retail_fmcg"},
    # Restaurants and packaged F&B share promotion mechanics and delivery
    # platforms.
    "food_beverage": {"retail_fmcg"},
    # Marketplace-led retail and app/digital businesses share the same
    # conversion-funnel and first-party-data work.
    "retail_fmcg": {"tech_app"},
    # Apps and media both live on engagement and community metrics.
    "tech_app": {"entertainment_media"},
    # High-consideration purchases with long funnels and dealer/agent
    # networks behave alike.
    "automotive": {"property_travel"},
    # Both sell a considered service through relationship-led funnels.
    "b2b_service": {"property_travel"},
}


def _symmetrise(seed: dict[str, set[str]]) -> dict[str, frozenset[str]]:
    out: dict[str, set[str]] = {k: set() for k in VOCAB.get("industry", ())}
    for a, neighbours in seed.items():
        for b in neighbours:
            out.setdefault(a, set()).add(b)
            out.setdefault(b, set()).add(a)
    return {k: frozenset(v) for k, v in out.items()}


INDUSTRY_ADJACENCY: dict[str, frozenset[str]] = _symmetrise(_ADJACENCY_SEED)


def tag_for_value(dimension: str, value: str) -> str | None:
    """Resolve a stored answer back to its token, or None when the client
    typed free text (which no chip value matches)."""
    return _VALUE_TO_TAG.get(dimension, {}).get(value)


def is_valid(dimension: str, tag: str) -> bool:
    return tag in VOCAB.get(dimension, frozenset())


def validate_tag(dimension: str, tag: str) -> None:
    """Raise on anything outside the vocabulary. Called when ingesting corpus
    tags — a typo'd tag would otherwise score zero forever and look like a
    genuinely unrelated case."""
    if dimension not in VOCAB:
        raise ValueError(
            f"unknown tag dimension {dimension!r}; expected one of {sorted(VOCAB)}"
        )
    if tag not in VOCAB[dimension]:
        raise ValueError(
            f"{dimension}: {tag!r} is not in the controlled vocabulary. "
            f"Valid tokens: {sorted(VOCAB[dimension])}"
        )
