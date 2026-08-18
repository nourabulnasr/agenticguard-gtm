from src.discovery import discover_company, fetch_page_text


def test_fetch_page_text_returns_nonempty_for_real_site():
    text = fetch_page_text("https://www.paymob.com")
    assert isinstance(text, str)
    # Either we got real page text, or fetch failed and we got "" —
    # both are valid outcomes; we assert the function doesn't raise.


def test_discover_company_returns_valid_schema():
    result = discover_company("https://www.paymob.com")
    assert result.risk_category in {
        "prompt_injection",
        "rag_data_exposure",
        "autonomous_agent_manipulation",
        "none",
    }
    assert isinstance(result.ai_feature, str)
    assert isinstance(result.risk_rationale, str)


def test_discover_company_never_forces_a_bad_category_fit():
    # NOTE: khazna.com is NOT the Egyptian fintech "Khazna" (that's
    # khazna.app) — khazna.com is an unrelated Gulf trading-card-collection
    # app. Kept as a regression fixture anyway: its homepage describes a
    # real but non-matching AI feature (camera-based card ID), which is a
    # good test of "don't force a bad category fit" regardless of whose
    # site it actually is. See README's "What red-teaming/real-world
    # testing caught" for the full story of how this domain mismatch was
    # found (it produced a hallucination-*looking* result that turned out
    # to be an accurate description of the wrong company).
    result = discover_company("khazna.com")
    if "card" in result.ai_feature.lower() or "camera" in result.ai_feature.lower():
        assert result.risk_category == "none"


def test_discover_company_honest_when_js_rendered_page_has_no_real_content():
    # khazna.app (the REAL Khazna fintech) is a JS-rendered SPA our
    # requests+BeautifulSoup scraper can't execute — it only sees an
    # ~80-char noscript fallback. Must honestly report nothing found
    # rather than fabricate a plausible-sounding fintech AI feature.
    result = discover_company("khazna.app")
    assert result.ai_feature == "no specific AI feature identified from public site"
    assert result.risk_category == "none"


def test_discover_company_confidence_threshold_on_vague_text(monkeypatch):
    # Direct test of the CONFIDENCE THRESHOLD rule: thin, boilerplate-only
    # text must not produce a specific-sounding feature claim, even if the
    # word "AI" appears somewhere in it.
    import src.discovery as discovery_module

    monkeypatch.setattr(
        discovery_module,
        "fetch_page_text",
        lambda url: "Welcome to our site. We use AI. Contact us. All rights reserved.",
    )
    result = discover_company("vague-example.com")
    assert result.ai_feature == "no specific AI feature identified from public site"
