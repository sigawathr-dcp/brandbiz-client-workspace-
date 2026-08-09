"""
app/services/classifier.py

Data classifier — scans arbitrary text (full conversation history + new message,
per §7.6) for sensitive-data patterns and returns the highest matching DataTier.

Usage
-----
    # At application startup (called from the FastAPI lifespan handler):
    count = await classifier.load_rules(session)

    # Per request — sync, reads the in-process cache only:
    tier = classifier.detect_tier(full_payload)

Patterns are loaded from ``data_classification_rules`` (only ``is_active=True`` rows).
The cache is replaced atomically on each ``load_rules`` / ``reload`` call so no locking
is needed — Python's GIL guarantees list-assignment is atomic.

Pattern types supported:
    regex   — compiled Python re pattern; some rules carry a post-match validator
              (e.g. Thai national-ID Mod-11 checksum, §8.8).
    keyword — case-insensitive substring match.
    ner     — Phase-4 deferred; rules with this type are skipped (logged).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.classification import DataClassificationRule, DataTier

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level in-process rule cache (replaced atomically on reload)
# ---------------------------------------------------------------------------

_RULES: list[_CompiledRule] = []


# ---------------------------------------------------------------------------
# Thai National-ID Mod-11 checksum validator (PLAN.md §8.8)
# ---------------------------------------------------------------------------

def is_valid_thai_national_id(text: str) -> bool:
    """Return True iff *text* contains exactly 13 digits with a valid Mod-11 check digit.

    Algorithm:
        sum(digit[i] * (13 - i)  for i in 0..11) mod 11
        check_digit = (11 - that_sum) mod 10
        must equal digit[12]
    """
    digits = re.sub(r"\D", "", text)
    if len(digits) != 13:
        return False
    weighted = sum(int(digits[i]) * (13 - i) for i in range(12))
    expected = (11 - (weighted % 11)) % 10
    return int(digits[12]) == expected


# ---------------------------------------------------------------------------
# Per-rule validator registry — keyed by rule *name* in data_classification_rules
# ---------------------------------------------------------------------------

_VALIDATORS: dict[str, Callable[[str], bool]] = {
    "Thai National ID": is_valid_thai_national_id,
    # Dash-less form users type without any separators — e.g. "1195644567342".
    # The same Mod-11 checksum guards against false positives (random 13-digit sequences).
    "Thai National ID (compact)": is_valid_thai_national_id,
}


# ---------------------------------------------------------------------------
# Internal compiled-rule dataclass
# ---------------------------------------------------------------------------

@dataclass
class _CompiledRule:
    name: str
    kind: str  # 'regex' | 'keyword'
    # For regex: a compiled re.Pattern; for keyword: a lowercased string.
    matcher: re.Pattern | str
    tier: DataTier
    # Optional post-match validator; if present, a regex match is only counted
    # when validator(matched_text) returns True.
    validator: Callable[[str], bool] | None = field(default=None)


# ---------------------------------------------------------------------------
# Rule compilation (pure — no DB access, easy to unit-test)
# ---------------------------------------------------------------------------

def _compile_rules(rows: list) -> list[_CompiledRule]:
    """Compile ORM rows (or any objects with the same attributes) into _CompiledRule entries.

    Unknown or deferred pattern types (e.g. 'ner') are skipped with a warning.
    """
    compiled: list[_CompiledRule] = []
    for row in rows:
        tier = DataTier(row.detected_tier)
        validator = _VALIDATORS.get(row.name)

        if row.pattern_type == "regex":
            try:
                pattern = re.compile(row.pattern)
            except re.error as exc:
                logger.warning(
                    "Skipping rule %r — invalid regex %r: %s", row.name, row.pattern, exc
                )
                continue
            compiled.append(
                _CompiledRule(
                    name=row.name,
                    kind="regex",
                    matcher=pattern,
                    tier=tier,
                    validator=validator,
                )
            )

        elif row.pattern_type == "keyword":
            compiled.append(
                _CompiledRule(
                    name=row.name,
                    kind="keyword",
                    matcher=row.pattern.lower(),
                    tier=tier,
                    validator=validator,
                )
            )

        else:
            # 'ner' is Phase-4 deferred; any other unknown type is also skipped.
            logger.debug(
                "Skipping rule %r — pattern_type=%r not yet supported",
                row.name,
                row.pattern_type,
            )

    return compiled


# ---------------------------------------------------------------------------
# Async loaders (called from lifespan / admin reload)
# ---------------------------------------------------------------------------

async def load_rules(session: AsyncSession) -> int:
    """Load active rules from DB, compile, and replace the in-process cache.

    Returns the number of rules loaded.
    """
    global _RULES  # noqa: PLW0603  (intentional module-level replacement)

    stmt = select(DataClassificationRule).where(DataClassificationRule.is_active.is_(True))
    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    new_rules = _compile_rules(rows)
    _RULES = new_rules  # atomic list replacement

    logger.info("Classifier loaded %d active rules.", len(_RULES))
    return len(_RULES)


async def reload(session: AsyncSession) -> int:
    """Reload rules from DB (alias of load_rules; called by admin-update endpoint)."""
    return await load_rules(session)


# ---------------------------------------------------------------------------
# Tier detection (sync — reads cache only, §7.6: pass full payload)
# ---------------------------------------------------------------------------

def detect_tier(text: str) -> DataTier:
    """Return the highest DataTier found in *text* across all cached rules.

    *text* should be the full conversation history concatenated with the new
    message (§7.6) so that a Tier-1 conversation that acquires a Tier-3 message
    is correctly classified as Tier-3 for the next LLM call.

    Returns ``DataTier.TIER_1_PUBLIC`` when:
    - *text* is empty / whitespace-only, OR
    - no active rule matches.
    """
    if not text or not text.strip():
        return DataTier.TIER_1_PUBLIC

    matched_tiers: list[DataTier] = []

    for rule in _RULES:
        if rule.kind == "regex":
            assert isinstance(rule.matcher, re.Pattern)
            # Iterate matches; as soon as one passes the validator (if any),
            # record the tier and move on to the next rule.
            for m in rule.matcher.finditer(text):
                if rule.validator is None or rule.validator(m.group(0)):
                    matched_tiers.append(rule.tier)
                    break  # one confirmed match per rule is enough

        elif rule.kind == "keyword":
            assert isinstance(rule.matcher, str)
            if rule.matcher in text.lower():
                matched_tiers.append(rule.tier)

    if not matched_tiers:
        return DataTier.TIER_1_PUBLIC

    return max(matched_tiers, key=lambda t: t.rank)
