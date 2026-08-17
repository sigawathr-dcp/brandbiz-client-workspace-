"""
app/services/case_image.py

Recover a campaign thumbnail for a case study from its portfolio page.

The scraped corpus (`case-study_*.md`, see app/services/case_card.py) never
captured images: all 30 files carry a Source URL but no `**Image:**` field and
no `![alt](url)`, so parse_case_card()'s image_url is None for every one of
them and the Cases cards render text-only. The images do exist — on the
brandbizsolution.co.th works page each file already links to.

Splitting the work in two:
  * pick_image_url() is PURE (html in, url out) so the selection rules below
    are unit-testable without network access;
  * fetch_case_image() is the thin httpx wrapper around it.

Neither is called on a request path. Case cards must never block on a third-
party fetch — scripts/backfill_case_images.py runs this offline and stores the
result on case_studies.image_url, which is what the readers use.

Selection rules, derived from the actual markup:
  * A campaign photo is ONLY an image under /images/works_post/gallerys/ —
    the per-campaign gallery. Nothing else on the page qualifies.
  * Other /images/works_post/ images are site furniture, not campaign
    photos. Every works page carries the same three — 1_6.jpg, 5_13.jpg and
    messageimage_1727866151172.jpg — in a promo strip, including pages that
    also have a real gallery. They used to serve as a fallback here, which
    put one identical thumbnail on every gallery-less case: measured over
    the 23 cases that resolved an image, all 20 gallery hits were unique
    while all 3 fallback hits were the same 1_6.jpg.
  * og:image is deliberately NOT used: every page on the site sets it to the
    same generic /images/webclip.png site logo, which would put an identical
    meaningless thumbnail on every card.
  * Chrome (/assets/img/logo*.svg, webclip) is excluded outright.

So a page with no gallery yields None and the card stays text-only. That is
the intended outcome, not a gap to paper over: a shared thumbnail is worse
than no thumbnail, because it misrepresents whose work the card is showing.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

import httpx

_IMG_SRC_RE = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.IGNORECASE)

# Site chrome that appears on every works page — never a campaign thumbnail.
_CHROME_MARKERS = ("/assets/", "logo", "webclip", "placeholder", "loading")

_GALLERY_MARKER = "/images/works_post/gallerys/"


def _is_chrome(url: str) -> bool:
    lowered = url.lower()
    return any(marker in lowered for marker in _CHROME_MARKERS)


def pick_image_url(html: str, base_url: str) -> str | None:
    """Best campaign image on a works page, absolutised against base_url.

    Returns None when the page has no gallery image — the caller leaves
    image_url NULL and the card keeps its existing text-only layout rather
    than showing an irrelevant thumbnail borrowed from the promo strip.
    """
    for raw in _IMG_SRC_RE.findall(html):
        src = raw.strip()
        if not src or _is_chrome(src):
            continue
        absolute = urljoin(base_url, src)
        # Only http(s) — this value ends up in an <img src> on a client page.
        if not absolute.startswith(("http://", "https://")):
            continue
        if _GALLERY_MARKER in absolute:
            return absolute
    return None


async def fetch_case_image(client: httpx.AsyncClient, source_url: str) -> str | None:
    """Fetch a works page and pick its campaign image. Returns None on any
    network/HTTP failure — a missing thumbnail must never fail a backfill run
    over the whole corpus."""
    try:
        response = await client.get(source_url)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    return pick_image_url(response.text, str(response.url))
