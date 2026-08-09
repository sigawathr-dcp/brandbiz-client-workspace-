"""Unit tests for app/services/case_card.py — parsing the scraped
case-study markdown template into client-facing card fields."""
from app.services.case_card import parse_case_card

FULL_CASE = """# Case Study: AURABLUEคู่หน้าGON

- **Client:** AURA BLUE
- **Category:** SKINCARE - SERUM
- **Source:** https://www.brandbizsolution.co.th/TH/works/aura_blue_x_bar_b_gon.html
- **Image:** https://www.brandbizsolution.co.th/images/aura_blue.jpg

## What we did

**OUR WORK :**
- CREATE BRAND PHENOMENA OF THE TOP TIER ONLINE BRAND IN THAILAND VIABRAND COMMUNICATION
- Branding & Communication Campaigns
  - Collaboration WithBar B Gon

**BRAND COMMUNICATION :**
จากแบรนด์ออนไลน์มุ่งสู่แคมเปญระดับประเทศที่สร้างความน่าเชื่อถือให้กับแบรนด์ผ่านการ collaboration กับแบรนด์ระดับประเทศที่มีแบรนด์ดิ้งสุดสตรองอย่างBar B Q PLAZA เป็นการนำเสนอมุมมองใหม่ๆ ที่เข้าถึงกลุ่มเป้าหมายอย่างชัดเจน
"""

PLACEHOLDER_CASE = """# Case Study: BENOVA GOBAL

- **Client:** BENOVA GOBAL
- **Source:** https://www.brandbizsolution.co.th/TH/works/shin_yubin.html

---
_Portfolio write-up scraped from the Brandbiz Solution website. Objective/brief and measurable results are not yet included; this entry will be replaced with the full case study when available._
"""

BULLETS_ONLY_CASE = """# Case Study: GRAB 10 VERSARY

- **Client:** GRAB THAILAND
- **Category:** APPLICATION
- **Source:** https://www.brandbizsolution.co.th/TH/works/grab_10_versary.html

## What we did

**OUR WORK :**
- Branding & Communication Campaigns

**BRAND EXPERIENCE :**
- Creative Event 10 years
"""


def test_full_case_parses_every_field() -> None:
    card = parse_case_card(FULL_CASE)
    assert card.title == "AURABLUEคู่หน้าGON"
    assert card.client == "AURA BLUE"
    assert card.category == "SKINCARE - SERUM"
    assert card.source_url == "https://www.brandbizsolution.co.th/TH/works/aura_blue_x_bar_b_gon.html"
    assert card.image_url == "https://www.brandbizsolution.co.th/images/aura_blue.jpg"
    assert card.summary is not None
    assert card.summary.startswith("จากแบรนด์ออนไลน์")
    assert "**" not in card.summary


def test_summary_is_truncated_for_card_body() -> None:
    card = parse_case_card(FULL_CASE)
    assert card.summary is not None
    assert len(card.summary) <= 221  # 220 + ellipsis


def test_placeholder_case_has_no_summary_but_keeps_identity() -> None:
    card = parse_case_card(PLACEHOLDER_CASE)
    assert card.client == "BENOVA GOBAL"
    assert card.category is None
    # the scraper's italic placeholder note must not leak into the card
    assert card.summary is None
    assert card.source_url is not None
    assert card.image_url is None


def test_bullets_fallback_when_no_narrative() -> None:
    card = parse_case_card(BULLETS_ONLY_CASE)
    assert card.summary == "Branding & Communication Campaigns · Creative Event 10 years"
    assert card.image_url is None


def test_untemplated_text_returns_all_none() -> None:
    card = parse_case_card("just some unrelated short text")
    assert card.title is None and card.client is None
    assert card.category is None and card.source_url is None and card.summary is None
    assert card.image_url is None


def test_image_falls_back_to_first_markdown_image() -> None:
    text = """# Case Study: GRAB 10 VERSARY

- **Client:** GRAB THAILAND
- **Category:** APPLICATION
- **Source:** https://www.brandbizsolution.co.th/TH/works/grab_10_versary.html

![Grab 10th anniversary campaign hero shot](https://www.brandbizsolution.co.th/images/grab_hero.jpg)

## What we did

**BRAND COMMUNICATION :**
แคมเปญฉลองครบรอบ 10 ปีที่สร้างการรับรู้แบรนด์ในวงกว้างผ่านสื่อดิจิทัลและออฟไลน์ทั่วประเทศไทยอย่างต่อเนื่อง
"""
    card = parse_case_card(text)
    assert card.image_url == "https://www.brandbizsolution.co.th/images/grab_hero.jpg"
    # the markdown image line must not leak into the narrative summary
    assert card.summary is not None
    assert "grab_hero.jpg" not in card.summary
    assert "![" not in card.summary


def test_image_field_rejects_non_http_scheme() -> None:
    text = """# Case Study: UNSAFE CASE

- **Client:** UNSAFE CLIENT
- **Image:** javascript:alert(1)
"""
    card = parse_case_card(text)
    assert card.image_url is None
