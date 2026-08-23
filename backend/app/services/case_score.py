"""
app/services/case_score.py

The weighted case-match score — Interview_Details.xlsx columns F and G made
real. Pure: no DB, no I/O, no embedding calls, so the whole scoring model is
unit-testable off fixtures the way case_match.collapse_best_per_file() is.

Why this exists. Matching used to be one dense-vector cosine over a single
string built from every intake answer, which gives each question equal,
implicit, unauditable influence — `Weight: 0.25` in the sheet affected
nothing. Here each scoring dimension contributes its own weight, and the
result carries a per-dimension breakdown, so a card can say WHY it matched
instead of only showing a percentage.

The blend. `alpha` (settings.case_match_tag_weight) mixes the structured tag
score with the dense score that ranked cases before:

    final = alpha * tag_score + (1 - alpha) * dense_score

alpha = 0 reproduces the previous behaviour exactly, which is both the
rollback path and the A/B baseline for the eval harness. alpha = 1 ignores
the embedding entirely. Neither extreme is the default: tags are precise but
only as complete as the corpus labelling, and the dense score still carries
signal for free-text answers and thinly-tagged cases.

Partial credit, in descending confidence:
  exact token match          -> 1.0
  adjacent industry          -> ADJACENT_CREDIT
  free text / untagged case  -> that dimension's dense similarity, damped
  no overlap                 -> 0.0

The damped fallback is the important one. A dimension where we simply do not
know (the client typed something the chips did not cover, or nobody has
tagged this case for `objective` yet) must not score 0 — that would rank a
case as actively unsuitable on the basis of missing data. It also must not
score 1.0. Damping the embedding's own opinion is the honest middle, and it
keeps a half-tagged corpus usable while tagging catches up.
"""
from __future__ import annotations

from collections.abc import Mapping, Set
from dataclasses import dataclass

from app.services import case_taxonomy

# Credit for a case in an adjacent industry (see case_taxonomy's
# INDUSTRY_ADJACENCY). Half: clearly better than unrelated, clearly worse
# than the same vertical.
ADJACENT_CREDIT = 0.5

# Multiplier on the dense similarity when a dimension cannot be resolved to
# a token. Below ADJACENT_CREDIT on purpose — "the embedding thinks these are
# similar" is weaker evidence than "a human tagged these as neighbours".
FREE_TEXT_DAMPING = 0.4


@dataclass(frozen=True)
class DimensionScore:
    """One dimension's contribution, kept alongside the reason so the UI can
    show what matched and the eval harness can see why a rank moved."""

    dimension: str
    weight: float
    raw: float  # 0..1 before weighting
    contribution: float  # weight * raw
    reason: str  # exact | adjacent | inferred | miss | unanswered


@dataclass(frozen=True)
class CaseScore:
    tag_score: float  # 0..1, weighted sum over dimensions
    dense_score: float  # 0..1, the pre-existing cosine similarity
    final: float  # alpha-blended
    dimensions: tuple[DimensionScore, ...]

    @property
    def matched_dimensions(self) -> tuple[str, ...]:
        """Dimensions that matched outright — what a card should name."""
        return tuple(d.dimension for d in self.dimensions if d.reason == "exact")


def _dimension_raw(
    dimension: str,
    client_tag: str | None,
    case_tags: Set[str],
    dense: float,
) -> tuple[float, str]:
    if client_tag is None:
        # Free text: no token to compare, so defer to the embedding.
        return (max(0.0, min(1.0, dense)) * FREE_TEXT_DAMPING, "inferred")
    if not case_tags:
        # The case has no tag on this dimension at all — unknown, not absent.
        # Same treatment as free text: defer, damped.
        return (max(0.0, min(1.0, dense)) * FREE_TEXT_DAMPING, "inferred")
    if client_tag in case_tags:
        return (1.0, "exact")
    if dimension == "industry":
        neighbours = case_taxonomy.INDUSTRY_ADJACENCY.get(client_tag, frozenset())
        if neighbours & set(case_tags):
            return (ADJACENT_CREDIT, "adjacent")
    return (0.0, "miss")


def score_case(
    client_tags: Mapping[str, str | None],
    case_tags: Mapping[str, Set[str]],
    weights: Mapping[str, float],
    dense_score: float,
    *,
    alpha: float,
    dense_by_dimension: Mapping[str, float] | None = None,
) -> CaseScore:
    """Score one case study against one client profile.

    client_tags: {dimension: token or None}. None means the client answered
        this dimension in free text. A dimension missing from the mapping
        entirely means unanswered (an abandoned intake) and is dropped from
        the weighting rather than scored zero — otherwise a half-finished
        interview would drag every case down uniformly and the ranking, which
        is all that matters, would be unchanged but the displayed percentages
        would be meaningless.
    case_tags: {dimension: {token, ...}} for this case. A case may carry
        several tokens per dimension (a campaign can serve two audiences).
    weights: {dimension: weight}, normally client_intake.SCORING_WEIGHTS.
    dense_score: the 0..1 cosine similarity for the whole profile.
    dense_by_dimension: optional per-dimension similarity for the damped
        fallback. Falls back to the whole-profile dense score when absent,
        which is what production does today — per-dimension embedding is an
        extra N embed calls per match and is only worth it if the eval shows
        it moves ranks.
    """
    per_dim = dense_by_dimension or {}
    scored: list[DimensionScore] = []
    total_weight = 0.0
    accumulated = 0.0

    for dimension, weight in weights.items():
        if dimension not in client_tags:
            scored.append(
                DimensionScore(dimension, weight, 0.0, 0.0, "unanswered")
            )
            continue
        raw, reason = _dimension_raw(
            dimension,
            client_tags[dimension],
            case_tags.get(dimension, frozenset()),
            per_dim.get(dimension, dense_score),
        )
        total_weight += weight
        accumulated += weight * raw
        scored.append(DimensionScore(dimension, weight, raw, weight * raw, reason))

    # Renormalise over the dimensions actually answered, so an abandoned
    # intake still produces a 0..1 score on the same scale.
    tag_score = (accumulated / total_weight) if total_weight else 0.0

    a = max(0.0, min(1.0, alpha))
    dense = max(0.0, min(1.0, dense_score))
    final = a * tag_score + (1.0 - a) * dense
    return CaseScore(
        tag_score=tag_score,
        dense_score=dense,
        final=max(0.0, min(1.0, final)),
        dimensions=tuple(scored),
    )


def client_tags_from_fields(fields: Mapping[str, str]) -> dict[str, str | None]:
    """Map a loaded intake profile ({field: english value}) onto
    {dimension: token or None}.

    Keyed by the question's `match_tag`, which for every v2 scoring question
    equals its field name. Fields the current script does not define (a v1
    engagement's `goal` / `horizon` / `history`) are skipped: they have no
    dimension in the tag vocabulary, and the dense half of the blend is what
    carries them. That is the deliberate cost of not retro-tagging v1
    answers into v2 tokens — a mapping that guessed would put words in an old
    client's mouth.
    """
    out: dict[str, str | None] = {}
    for dimension in case_taxonomy.DIMENSIONS:
        if dimension not in fields:
            continue
        out[dimension] = case_taxonomy.tag_for_value(dimension, fields[dimension])
    return out
