"""
app/services/case_card.py

Parse a case-study markdown document into the display fields the client
Cases cards need (Phase 5, D21/D22).

The case-study corpus (the `case-study_*.md` files attached to the
workspace agent) comes in two shapes that share one header block:

    # Case Study: <campaign title>
    - **Client:** <brand name>
    - **Category:** <vertical>
    - **Source:** <works-page URL>          (absent on spreadsheet-only cases)
    - **Video:** <embed URL>                (optional, repeatable)
    - **Also published at:** <URL>          (optional — merged portfolio pages)
    - **Reference:** <article URL>          (optional, not an image)
    - **Image:** <thumbnail URL>      (optional — falls back to the first
                                        `![alt](url)` in the doc, else no
                                        image; cards degrade to text-only.
                                        No file in the corpus carries one
                                        today: thumbnails are recovered
                                        offline into case_studies.image_url
                                        by scripts/backfill_case_images.py,
                                        see services/case_image.py)

Scraped from brandbizsolution.co.th — everything under one H2, with the
section names as bold inline labels:

    ## What we did
    **OUR WORK :**
    - <service bullet>
    **BRAND COMMUNICATION :**
    <free-text Thai narrative paragraph>

Curated from "Data for DSMEs Agent.xlsx" — the same sections promoted to
real H2s, with the leftover scraped detail kept below them:

    ## Our work
    - <service bullet>
    ## Brand communication
    <free-text Thai narrative paragraph>
    ## Execution details (from portfolio site)
    ### <scraped section name>
    ...

The narrative is found by prose shape, not by heading name, so both shapes
yield the same summary; only _services_summary()'s fallback has to know
that "## Our work" and "## What we did" mean the same thing.

A client seat looking at a case card wants "have they done work like mine,
for brands I recognise?" — the brand name, the kind of work, and a readable
sentence about it. Raw markdown, filenames, and embed URLs are noise, so
run_case_match (app/routers/client.py) parses each matched file through
parse_case_card() instead of echoing chunk text at the UI.

Every field is best-effort: the corpus includes placeholder write-ups with
no Category/narrative, and future re-uploads may drift from the template.
Missing fields come back as None and the frontend falls back gracefully
(components/client/CaseMatchCards.tsx).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_TITLE_RE = re.compile(r"^#\s*Case Study:\s*(.+?)\s*$", re.MULTILINE)
_CLIENT_RE = re.compile(r"\*\*Client:\*\*\s*(.+)")
_CATEGORY_RE = re.compile(r"\*\*Category:\*\*\s*(.+)")
_SOURCE_RE = re.compile(r"\*\*Source:\*\*\s*(\S+)")
_IMAGE_FIELD_RE = re.compile(r"\*\*Image:\*\*\s*(\S+)")
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((\S+?)\)")

_SUMMARY_MAX_CHARS = 220

# Lines that are markdown structure rather than prose. The trailing
# "_..._" italic line is the scraper's own placeholder note ("Portfolio
# write-up scraped from ...") — never client-facing copy. "!" excludes
# markdown image lines (`![alt](url)`), which otherwise read as a long
# prose line and would leak a raw URL into the card summary.
_NON_PROSE_PREFIXES = ("#", "-", "*", "_", ">", "|", "`", "!")

# Headings whose top-level bullets are the service list. The scraped corpus
# nests "**OUR WORK :**" under "## What we did"; the spreadsheet-curated
# corpus promotes it to its own "## Our work" H2. Both name the same thing,
# so _services_summary() accepts either.
_WORK_SECTION_HEADINGS = ("## what we did", "## our work")


@dataclass
class CaseCard:
    title: str | None
    client: str | None
    category: str | None
    source_url: str | None
    summary: str | None
    image_url: str | None


def _clean_inline(text: str) -> str:
    """Strip markdown emphasis markers left inside a prose line."""
    return re.sub(r"\*\*|__", "", text).strip()


def _narrative_summary(text: str) -> str | None:
    """First free-text prose paragraph (the Thai campaign narrative under
    **BRAND COMMUNICATION :**), truncated for a card body."""
    paragraph: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        is_prose = bool(line) and not line.startswith(_NON_PROSE_PREFIXES) and len(line) >= 40
        if is_prose:
            paragraph.append(_clean_inline(line))
        elif paragraph:
            break  # paragraph ended
    if not paragraph:
        return None
    summary = " ".join(paragraph)
    if len(summary) > _SUMMARY_MAX_CHARS:
        summary = summary[:_SUMMARY_MAX_CHARS].rstrip() + "…"
    return summary


def _services_summary(text: str) -> str | None:
    """Fallback when there is no narrative: the top-level service bullets
    under "## What we did" / "## Our work" (e.g. "Branding & Communication
    Campaigns"), deduplicated, joined as one line."""
    in_work_section = False
    services: list[str] = []
    for raw in text.splitlines():
        if raw.startswith("## "):
            in_work_section = raw.strip().lower() in _WORK_SECTION_HEADINGS
            continue
        # top-level bullets only — indented bullets are campaign sub-items
        if in_work_section and raw.startswith("- "):
            item = _clean_inline(raw[2:])
            if item and item not in services:
                services.append(item)
    if not services:
        return None
    return " · ".join(services[:4])


def _image_url(text: str) -> str | None:
    """Best-effort thumbnail URL: the explicit `**Image:**` field, else the
    first markdown image in the document, else None. Only http(s) URLs are
    trusted — this value lands directly in an `<img src>` on the client, and
    the source document is an uploaded file, not code."""
    match = _IMAGE_FIELD_RE.search(text) or _MD_IMAGE_RE.search(text)
    if not match:
        return None
    url = match.group(1).strip()
    return url if url.startswith(("http://", "https://")) else None


def parse_case_card(text: str) -> CaseCard:
    title = _TITLE_RE.search(text)
    client = _CLIENT_RE.search(text)
    category = _CATEGORY_RE.search(text)
    source = _SOURCE_RE.search(text)
    return CaseCard(
        title=title.group(1).strip() if title else None,
        client=client.group(1).strip() if client else None,
        category=category.group(1).strip() if category else None,
        source_url=source.group(1).strip() if source else None,
        summary=_narrative_summary(text) or _services_summary(text),
        image_url=_image_url(text),
    )
