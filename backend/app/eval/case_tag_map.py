"""
app/eval/case_tag_map.py

Translate the case-study spreadsheet's prose tag phrases into the
controlled vocabulary the matcher actually scores on.

"Case studies for DSMEs.xlsx" carries six columns that mirror the six
weighted interview questions, but its cells are written for humans:
`Established / Campaign Launch`, `Beauty consumers / Premium segment`,
`Awareness / Footfall / Engagement`. The scorer compares TOKENS
(app/services/case_taxonomy.py) - `enterprise`, `mass_market`,
`awareness` - and a phrase that fails to resolve does not error, it simply
scores zero forever and makes the case look unrelated to every client. So
the translation is written down here, once, where it can be argued with.

Two resolution styles, chosen per dimension for a reason:

  COMPONENTS  Five dimensions are additive: a cell lists several things a
              campaign was about, split on "/", and each part contributes
              its own token. `Awareness / Engagement / Sales` genuinely IS
              three objectives, and case_study_tags is many-to-many per
              dimension precisely so it can say so.

  WHOLE VALUE `asset_channel` is NOT additive, because three of its tokens
              are exclusive claims rather than list items: `social_only`
              means social is the MAIN channel, `no_owned_base` means there
              is nothing owned, `multi_channel_siloed` means several
              channels whose data does not join up. Splitting
              `App / Social / Live Event` into parts would assert "social
              is the main channel" about a business whose main channel is
              its app. So that dimension maps whole cells.

UNMAPPED is as load-bearing as the maps. A component listed there is one we
looked at and decided has no honest token - `Trial`, `Growth`,
`Social shoppers`. Anything in neither a map nor UNMAPPED raises, so the
next revision of the spreadsheet cannot introduce a phrase that silently
contributes nothing. Failing the build is the cheap outcome; a corpus that
looks tagged and is not is the expensive one.

Everything here resolves at confidence 1.00: these are a human's assertions
transcribed from the sheet, not a model's reading of a narrative (contrast
scripts/tag_case_studies.py --narrative).
"""
from __future__ import annotations

import re

from app.services import case_taxonomy

# --- industry -------------------------------------------------------------
# Maps the sheet's curated "Industry Tag" column, not its prose "Category"
# column ("SKINCARE - SERUM"); the curated one is already close to our chips.
_INDUSTRY = {
    "application": ("tech_app",),
    "food delivery": ("food_beverage",),
    "entertainment": ("entertainment_media",),
    "movies": ("entertainment_media",),
    "beauty": ("beauty",),
    "skincare": ("beauty",),
    "cosmetics": ("beauty",),
    "health & supplements": ("health_supplement",),
    # CASETiFY sells a physical consumer product through e-commerce and
    # retail. `tech_app` is for businesses that ARE an app or digital
    # service (our chip reads "Application / Tech / Digital Service"), which
    # a phone-case brand is not.
    "tech accessories": ("retail_fmcg",),
    "retail": ("retail_fmcg",),
    "tech store": ("retail_fmcg",),
    "automotive": ("automotive",),
    "lubricants": ("automotive",),
}

# --- stage ----------------------------------------------------------------
# Our `enterprise` chip reads "Enterprise / Regional Expansion", so both
# "Established" and "Regional Expansion" land there.
_STAGE = {
    "established": ("enterprise",),
    "regional expansion": ("enterprise",),
    "growth": ("growth",),
    "expansion": ("growth",),
    "scale": ("growth",),
    "pre-launch": ("pre_launch",),
    "launch": ("pre_launch",),
    "market entry": ("pre_launch",),
    "reposition": ("reposition",),
    "re-launch": ("reposition",),
    "premiumization": ("reposition",),
}

# --- audience -------------------------------------------------------------
# "Cambodia market" -> tourist_overseas because our chip reads
# "tourists / overseas markets", not tourists alone.
_AUDIENCE = {
    "mass market": ("mass_market",),
    "urban consumers": ("mass_market",),
    "existing users": ("mass_market",),
    "existing customers": ("mass_market",),
    "beauty consumers": ("mass_market",),
    "tech shoppers": ("mass_market",),
    "store visitors": ("mass_market",),
    "gen z": ("gen_z_student",),
    "gen z 13-25": ("gen_z_student",),
    "university students": ("gen_z_student",),
    "students": ("gen_z_student",),
    "fandom": ("fandom_community",),
    "movie fans": ("fandom_community",),
    # A horror audience is an interest community, and the campaign was built
    # around that community's behaviour rather than a demographic.
    "horror interest": ("fandom_community",),
    "urban adults": ("working_adult",),
    "male adults": ("working_adult",),
    # Premium beauty buyers are the disposable-income working adult; there is
    # no "premium" chip, and inventing one breaks the namespace the corpus
    # shares with intake_options.
    "premium segment": ("working_adult",),
    "cambodia market": ("tourist_overseas",),
}

# --- challenge ------------------------------------------------------------
_CHALLENGE = {
    "awareness": ("low_awareness",),
    "social impact": ("low_awareness",),
    "viral buzz": ("low_awareness",),
    "sales": ("slow_conversion",),
    "sales growth": ("slow_conversion",),
    "conversion": ("slow_conversion",),
    "store traffic": ("slow_conversion",),
    "engagement": ("weak_engagement",),
    "brand engagement": ("weak_engagement",),
    "cinema engagement": ("weak_engagement",),
    "brand experience": ("weak_engagement",),
    "experience": ("weak_engagement",),
    # Wonka's brief. "The audience knows us but feels nothing" is what our
    # weak_engagement chip describes ("content/social not making an impact").
    "emotional connection": ("weak_engagement",),
    "loyalty": ("low_retention",),
    "launch": ("launch_need",),
    "market entry": ("launch_need",),
    "positioning": ("weak_positioning",),
    "brand image": ("weak_positioning",),
    "brand trust": ("weak_positioning",),
    "trust": ("weak_positioning",),
    "credibility": ("weak_positioning",),
    "differentiation": ("weak_positioning",),
    "premiumization": ("reposition_premiumize",),
}

# --- objective ------------------------------------------------------------
_OBJECTIVE = {
    "awareness": ("awareness",),
    "engagement": ("engagement_community",),
    "brand love": ("retention_loyalty",),
    "o2o": ("o2o",),
    # Driving store visits off the back of online activity is exactly what
    # our o2o chip ("connect online-offline / O2O") describes.
    "footfall": ("o2o",),
    "sales": ("sales_acquisition",),
    "conversion": ("sales_acquisition",),
    "trial": ("sales_acquisition",),
    "product launch": ("launch",),
    "launch": ("launch",),
    "reposition": ("reposition",),
    "premiumization": ("reposition",),
    "market expansion": ("market_expansion",),
    "audience expansion": ("market_expansion",),
    "scale": ("market_expansion",),
}

COMPONENT_MAP: dict[str, dict[str, tuple[str, ...]]] = {
    "industry": _INDUSTRY,
    "stage": _STAGE,
    "audience": _AUDIENCE,
    "challenge": _CHALLENGE,
    "objective": _OBJECTIVE,
}

# --- asset_channel (whole-cell) -------------------------------------------
# Read as "what does this brand already own?", which is the question the
# interview asks. A Grab campaign runs on Grab's own app plus social plus
# events - several channels that do not share one customer view, which is
# `multi_channel_siloed`, not three separate claims.
WHOLE_VALUE_MAP: dict[str, dict[str, tuple[str, ...]]] = {
    "asset_channel": {
        "app / social / live event": ("multi_channel_siloed", "offline_touchpoint"),
        "app / online + offline touchpoints": ("multi_channel_siloed", "offline_touchpoint"),
        "app / live / online + offline": ("multi_channel_siloed", "offline_touchpoint"),
        "app / social / video": ("multi_channel_siloed",),
        "social / event / presenter": ("social_only", "offline_touchpoint"),
        "online brand / collaboration": ("web_plus_social",),
        "online / presenter / content": ("web_plus_social",),
        "social / content / production": ("social_only",),
        "content / production / social": ("social_only",),
        "social / community / direct marketing": ("social_only",),
        "social / community": ("social_only",),
        "live streaming / social / kol": ("social_only",),
        "social / ambassador / regional": ("social_only",),
        "social / influencer / regional": ("social_only",),
        "presenter / content": ("social_only",),
        "pop-up / offline + social": ("offline_touchpoint",),
        "experiential / social": ("offline_touchpoint",),
        "retail store / social / kol": ("offline_touchpoint",),
        # Campus and school activations are physical touchpoints the brand
        # controls for the run of the campaign.
        "university / social": ("offline_touchpoint",),
        "school / social": ("offline_touchpoint",),
    }
}

# Components we read and deliberately did not map. Each would need a token
# that does not exist, and inventing one breaks the namespace the intake
# options share with the corpus.
UNMAPPED: dict[str, frozenset[str]] = {
    "industry": frozenset(),
    # "Anniversary" and "Campaign Launch" describe the CAMPAIGN, not the
    # business's stage. Mapping "Campaign Launch" to pre_launch would file
    # six Warner tentpole releases as pre-launch startups.
    "stage": frozenset({"anniversary", "campaign launch"}),
    # "New audience" is a direction, not a segment. The rest are shopping
    # behaviours we have no chip for.
    "audience": frozenset(
        {
            "new audience",
            "social shoppers",
            "online shoppers",
            "health-conscious consumers",
            "health consumers",
        }
    ),
    # "Scale", "Growth", "Trial" and "Audience expansion" are outcomes
    # wanted, not problems being solved - they belong to the objective
    # column, where they ARE mapped.
    "challenge": frozenset({"scale", "growth", "trial", "audience expansion"}),
    "objective": frozenset({"brand trust", "trust", "growth"}),
    "asset_channel": frozenset(),
}

# The sheet mixes hyphens with en/em dashes ("Gen Z 13-25", "Pre-launch"),
# and the two spellings must not become two keys.
_DASHES = re.compile("[‐-―−]")


def normalise(text: str) -> str:
    """Fold a sheet cell to its lookup key: ASCII dashes, lowercase,
    collapsed whitespace."""
    return " ".join(_DASHES.sub("-", text).lower().split())


def split_components(value: str) -> list[str]:
    """The sheet's own separator is "/". Empty parts are dropped so a
    trailing slash does not read as an unknown component."""
    return [p.strip() for p in value.split("/") if p.strip()]


def tags_for(dimension: str, value: str) -> tuple[str, ...]:
    """Tokens for one spreadsheet cell, de-duplicated, in first-seen order.

    Raises ValueError on any phrase that is neither mapped nor explicitly
    unmapped - see the module docstring for why that is a hard failure.
    """
    value = (value or "").strip()
    if not value:
        return ()

    if dimension in WHOLE_VALUE_MAP:
        table = WHOLE_VALUE_MAP[dimension]
        key = normalise(value)
        if key not in table:
            raise ValueError(
                f"{dimension}: unmapped cell {value!r}. Add it to "
                f"WHOLE_VALUE_MAP[{dimension!r}] in app/eval/case_tag_map.py."
            )
        tokens: tuple[str, ...] = table[key]
    else:
        component_table = COMPONENT_MAP.get(dimension)
        if component_table is None:
            raise ValueError(f"no mapping table for dimension {dimension!r}")
        seen: list[str] = []
        for part in split_components(value):
            key = normalise(part)
            if key in component_table:
                seen.extend(t for t in component_table[key] if t not in seen)
            elif key in UNMAPPED.get(dimension, frozenset()):
                continue
            else:
                raise ValueError(
                    f"{dimension}: unmapped component {part!r} (from {value!r}). "
                    f"Add it to COMPONENT_MAP[{dimension!r}] or, if it has no "
                    f"honest token, to UNMAPPED[{dimension!r}] - "
                    f"app/eval/case_tag_map.py."
                )
        tokens = tuple(seen)

    for token in tokens:
        case_taxonomy.validate_tag(dimension, token)
    return tokens
