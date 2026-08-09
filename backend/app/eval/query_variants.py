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
from app.services.client_intake import INTAKE_SCRIPT

QueryBuilder = Callable[[Mapping[str, str]], str]


def _script_fields() -> list[str]:
    return [step["field"] for step in INTAKE_SCRIPT]


def thai_labels(fields: Mapping[str, str]) -> str:
    """Thai field labels + Thai chip labels (falls back to the raw stored
    value for free-text fields, which are typically Thai prose already)."""
    parts = []
    for f in _script_fields():
        if f not in fields:
            continue
        value = fields[f]
        display = thai_chip_label(f, value) or value
        parts.append(f"{THAI_FIELD_LABELS.get(f, f)}: {display}")
    return "; ".join(parts)


def values_only(fields: Mapping[str, str]) -> str:
    """No field labels at all — just the chip values / free text,
    semicolon-joined. Tests whether the "Business:", "Stage:", etc.
    labels in the production query help, hurt, or do nothing."""
    return "; ".join(fields[f] for f in _script_fields() if f in fields)


def natural_th(fields: Mapping[str, str]) -> str:
    """One Thai sentence roughly as a consultant might phrase the brief,
    instead of a label:value list — the shape closest to the corpus's own
    prose narrative."""

    def val(f: str) -> str:
        v = fields.get(f, "")
        return thai_chip_label(f, v) or v

    return (
        f"ธุรกิจ{val('industry')} อยู่ในระยะ{val('stage')} "
        f"กลุ่มลูกค้าหลักคือ{val('audience')} "
        f"ปัญหาหลักคือ{val('challenge')} "
        f"เป้าหมายคือ{val('goal')} ภายใน{val('horizon')} "
        f"งบประมาณ{val('budget')} ประสบการณ์ด้าน branding: {val('history')}"
    )


VARIANTS: dict[str, QueryBuilder] = {
    "prod": case_match.build_context_query,
    "thai_labels": thai_labels,
    "values_only": values_only,
    "natural_th": natural_th,
}
