"""
app/eval/query_variants.py

Alternate ways to turn an intake profile's 8 fields into an embeddable
query string, registered so eval_case_match_run.py's --query-variant flag
can A/B them against production.

"prod" is imported directly from app.services.case_match, not
reimplemented — every other entry is a candidate the harness can compare
it to, never a copy of production logic. An eval that quietly drifted from
what the router actually sends to rag_search.retrieve() would stop
measuring the real pipeline without saying so.

Motivation for even having variants: intake chip *values* are English
(see app.services.client_intake.INTAKE_SCRIPT), but the case-study
corpus's narrative text is Thai (app.services.case_card's
"BRAND COMMUNICATION" section). bge-m3 is multilingual, so this asymmetry
may not matter in practice — but it is the single largest untested
assumption behind the score shown to a client, and comparing "prod"
against a Thai-labeled variant is the cheapest way to find out.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping

from app.eval.goldens import THAI_FIELD_LABELS, thai_chip_label
from app.services import case_match
from app.services.client_intake import INTAKE_SCRIPT, match_query_fields

QueryBuilder = Callable[[Mapping[str, str]], str]


def _script_fields() -> list[str]:
    return [step["field"] for step in INTAKE_SCRIPT]


# Every variant below is an alternative CASE-MATCH query, so each one obeys
# the same field eligibility rule as production
# (client_intake.match_query_fields) — otherwise a variant could beat prod in
# the eval report purely by embedding an answer prod is forbidden to use.


def thai_labels(fields: Mapping[str, str]) -> str:
    """Thai field labels + Thai chip labels (falls back to the raw stored
    value for free-text fields, which are typically Thai prose already)."""
    parts = []
    for f in match_query_fields(fields):
        value = fields[f]
        display = thai_chip_label(f, value) or value
        parts.append(f"{THAI_FIELD_LABELS.get(f, f)}: {display}")
    return "; ".join(parts)


def values_only(fields: Mapping[str, str]) -> str:
    """No field labels at all — just the chip values / free text,
    semicolon-joined. Tests whether the "Business:", "Stage:", etc.
    labels in the production query help, hurt, or do nothing."""
    return "; ".join(fields[f] for f in match_query_fields(fields))


_TH_PHRASE: dict[str, str] = {
    # v2
    "industry": "ธุรกิจ{v}",
    "stage": "อยู่ในระยะ{v}",
    "audience": "กลุ่มลูกค้าหลักคือ{v}",
    "challenge": "ปัญหาหลักคือ{v}",
    "asset_channel": "ช่องทางที่มีอยู่คือ{v}",
    "objective": "เป้าหมายคือ{v}",
    "timeframe": "ภายใน{v}",
    "budget": "งบประมาณ{v}",
    # v1 only — an engagement pinned to script v1 still answers these
    "goal": "เป้าหมายคือ{v}",
    "horizon": "ภายใน{v}",
    "history": "ประสบการณ์ด้าน branding: {v}",
}


def natural_th(fields: Mapping[str, str]) -> str:
    """One Thai sentence roughly as a consultant might phrase the brief,
    instead of a label:value list — the shape closest to the corpus's own
    prose narrative.

    Driven by INTAKE_SCRIPT order rather than a hand-written sentence, so
    renaming or adding a question cannot silently drop a field from the
    variant (v2 renamed goal -> objective and horizon -> timeframe, and
    replaced history with asset_channel). Fields with no phrase template
    fall back to "label: value" so a new question degrades to something
    readable instead of vanishing.
    """

    def val(f: str) -> str:
        v = fields.get(f, "")
        return thai_chip_label(f, v) or v

    parts: list[str] = []
    for f in match_query_fields(fields):
        template = _TH_PHRASE.get(f)
        if template is None:
            label = THAI_FIELD_LABELS.get(f, f)
            parts.append(f"{label}: {val(f)}")
        else:
            parts.append(template.format(v=val(f)))
    return " ".join(parts)


VARIANTS: dict[str, QueryBuilder] = {
    "prod": case_match.build_context_query,
    "thai_labels": thai_labels,
    "values_only": values_only,
    "natural_th": natural_th,
}
