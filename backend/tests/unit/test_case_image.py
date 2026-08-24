"""Unit tests for case_image.pick_image_url()'s selection rules.

Markup shapes here are trimmed from real brandbizsolution.co.th works pages
(the corpus's Source URLs). Network access is not involved — fetch_case_image()
is a thin wrapper and is exercised by scripts/backfill_case_images.py.
"""
from __future__ import annotations

from app.services.case_image import pick_image_url

_BASE = "https://www.brandbizsolution.co.th/TH/works/grab_10_versary.html"


# The promo strip every works page carries, gallery or not. Verified present
# on ptt_lubricants, aura_blue_x_bar_b_gon, _wonka_______ (no gallery) and on
# grabmart_ (which does have a gallery).
_PROMO_STRIP = """
  <img src="https://www.brandbizsolution.co.th/images/works_post/1_6.jpg">
  <img src="https://www.brandbizsolution.co.th/images/works_post/5_13.jpg">
  <img src="https://www.brandbizsolution.co.th/images/works_post/messageimage_1727866151172.jpg">
"""


def test_prefers_gallery_image_over_promo_strip():
    html = (
        _PROMO_STRIP
        + '<img src="https://www.brandbizsolution.co.th/images/works_post/gallerys/2.jpg">'
    )
    assert pick_image_url(html, _BASE) == (
        "https://www.brandbizsolution.co.th/images/works_post/gallerys/2.jpg"
    )


def test_promo_strip_alone_yields_no_image():
    # Regression: these used to be a fallback, which handed the same 1_6.jpg to
    # every gallery-less case (ptt_lubricants, aura_blue, wonka all matched).
    # A shared thumbnail misrepresents whose work the card shows — blank is right.
    assert pick_image_url(_PROMO_STRIP, _BASE) is None


def test_non_gallery_works_post_image_is_never_selected():
    html = '<img src="https://www.brandbizsolution.co.th/images/works_post/21.jpg">'
    assert pick_image_url(html, _BASE) is None


def test_skips_site_chrome():
    # Every works page carries these; none is a campaign thumbnail. og:image
    # is the same webclip.png sitewide, which is why it is not consulted.
    html = """
      <meta property="og:image" content="https://www.brandbizsolution.co.th/images/webclip.png"/>
      <img src="https://www.brandbizsolution.co.th/assets/img/logo-sticky.svg">
      <img src="https://www.brandbizsolution.co.th/assets/img/logo.svg">
      <img src="https://www.brandbizsolution.co.th/images/webclip.png">
    """
    assert pick_image_url(html, _BASE) is None


def test_absolutises_relative_src():
    html = '<img src="/images/works_post/gallerys/37.jpg">'
    assert pick_image_url(html, _BASE) == (
        "https://www.brandbizsolution.co.th/images/works_post/gallerys/37.jpg"
    )


def test_ignores_non_http_schemes():
    # A data: or javascript: src must never reach an <img src> on a client page.
    html = '<img src="data:image/png;base64,iVBORw0KGgo=">'
    assert pick_image_url(html, _BASE) is None


def test_returns_none_when_page_has_no_images():
    assert pick_image_url("<html><body><p>no images</p></body></html>", _BASE) is None


def test_ignores_unrelated_content_images():
    # /images/Brandbiz/*.jpg are the about-page collage, not campaign photos.
    html = '<img src="/images/Brandbiz/13.jpg">'
    assert pick_image_url(html, _BASE) is None
