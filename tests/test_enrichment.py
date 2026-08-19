"""
Unlike the rest of this suite (see README — real API calls, not mocked),
Hunter.io calls in these tests ARE mocked. Groq/Gemini's free tiers are
generous enough to hit live in every test run; Hunter's free tier is a
shared 25-searches/month budget, and burning it on every `pytest` run
would make the pipeline unusable for its actual job. What's under test
here is the tiering/labeling LOGIC in enrichment.py, not Hunter's API
itself — so we control exactly what Hunter "returns" per test.
"""
import src.enrichment as enrichment
from src.enrichment import (
    PATTERN_GUESSED,
    PATTERN_INFERRED,
    PLACEHOLDER,
    VERIFIED,
    _apply_pattern,
    _find_role_match,
    enrich_contact,
)
from src.known_leadership import KNOWN_LEADERSHIP
from src.schemas import ContactExtraction


def test_apply_pattern_first_dot_last():
    assert _apply_pattern("{first}.{last}", "Ahmed", "Wagueeh") == "ahmed.wagueeh"


def test_apply_pattern_first_last_no_separator():
    assert _apply_pattern("{first}{last}", "Mostafa", "Menessy") == "mostafamenessy"


def test_apply_pattern_first_initial_last():
    assert _apply_pattern("{f}{last}", "Slava", "Slutsker") == "sslutsker"


def test_find_role_match_matches_cto_title():
    data = {
        "emails": [
            {"value": "ceo@x.com", "position": "Chief Executive Officer"},
            {"value": "cto@x.com", "position": "Chief Technology Officer"},
        ]
    }
    match = _find_role_match(data)
    assert match["value"] == "cto@x.com"


def test_find_role_match_matches_vp_engineering_via_position_raw():
    data = {
        "emails": [
            {
                "value": "slava@tabby.ai",
                "position": "Director of Engineering",
                "position_raw": "Head of Engineering",
            }
        ]
    }
    match = _find_role_match(data)
    assert match["value"] == "slava@tabby.ai"


def test_find_role_match_returns_none_when_no_role_matches():
    data = {"emails": [{"value": "sales@x.com", "position": "Sales Executive"}]}
    assert _find_role_match(data) is None


def test_find_role_match_ignores_entries_with_no_email_value():
    # A person can be listed by Hunter without a `value` (email) attached
    # in some plans/responses; must not be treated as a usable match.
    data = {"emails": [{"position": "Chief Technology Officer"}]}
    assert _find_role_match(data) is None


def test_tier1_hunter_domain_search_direct_match_is_verified(monkeypatch):
    monkeypatch.setattr(
        enrichment,
        "_hunter_domain_search",
        lambda domain: {
            "pattern": "{first}.{last}",
            "emails": [
                {
                    "value": "slava.slutsker@tabby.ai",
                    "first_name": "Slava",
                    "last_name": "Slutsker",
                    "position": "Director of Engineering",
                    "position_raw": "Head of Engineering",
                    "source_type": "found",
                    "confidence": 80,
                    "verification": {"status": "valid"},
                    "linkedin": "https://www.linkedin.com/in/slava-slutsker",
                }
            ],
        },
    )
    contact = enrich_contact("tabby.ai", "Tabby")
    assert contact.name == "Slava Slutsker"
    assert contact.title == "Head of Engineering"
    assert contact.email == "slava.slutsker@tabby.ai"
    assert contact.email_confidence == VERIFIED
    assert contact.linkedin_url == "https://www.linkedin.com/in/slava-slutsker"
    assert contact.linkedin_is_search_link is False


def test_tier2_seed_name_plus_hunter_found_email_is_verified(monkeypatch):
    assert "paymob.com" in KNOWN_LEADERSHIP  # sanity: this test relies on a real seed entry
    monkeypatch.setattr(enrichment, "_hunter_domain_search", lambda domain: {"pattern": "{first}{last}", "emails": []})
    monkeypatch.setattr(
        enrichment,
        "_hunter_email_finder",
        lambda domain, first, last: {
            "email": "mostafamenessy@paymob.com",
            "source_type": "found",
            "verification": {"status": "accept_all"},
        },
    )
    contact = enrich_contact("paymob.com", "Paymob")
    assert contact.name == "Mostafa Menessy"
    assert contact.email == "mostafamenessy@paymob.com"
    assert contact.email_confidence == VERIFIED


def test_tier2_seed_name_plus_hunter_generated_pattern_is_pattern_inferred(monkeypatch):
    monkeypatch.setattr(enrichment, "_hunter_domain_search", lambda domain: {"pattern": "{first}.{last}", "emails": []})
    monkeypatch.setattr(
        enrichment,
        "_hunter_email_finder",
        lambda domain, first, last: {
            "email": "chien.hoang@tamara.co",
            "source_type": "generated",
            "verification": {"status": "valid"},
        },
    )
    contact = enrich_contact("tamara.com", "Tamara")
    assert contact.name == "Chien Hoang"
    assert contact.email == "chien.hoang@tamara.co"
    assert contact.email_confidence == PATTERN_INFERRED


def test_tier2_seed_name_with_domain_pattern_but_no_finder_hit_is_pattern_inferred(monkeypatch):
    # Hunter's email-finder has no record for this exact person, but
    # domain-search's `pattern` field (from OTHER real addresses at this
    # domain) is still a real, confirmed pattern worth using.
    monkeypatch.setattr(
        enrichment,
        "_hunter_domain_search",
        lambda domain: {"pattern": "{first}.{last}", "emails": []},
    )
    monkeypatch.setattr(enrichment, "_hunter_email_finder", lambda domain, first, last: None)
    contact = enrich_contact("khazna.app", "Khazna")
    assert contact.name == "Ahmed Wagueeh"
    assert contact.email == "ahmed.wagueeh@khazna.app"
    assert contact.email_confidence == PATTERN_INFERRED


def test_tier2_seed_name_with_no_hunter_data_at_all_is_pattern_guessed(monkeypatch):
    monkeypatch.setattr(enrichment, "_hunter_domain_search", lambda domain: None)
    monkeypatch.setattr(enrichment, "_hunter_email_finder", lambda domain, first, last: None)
    contact = enrich_contact("nowpay.com", "Nowpay")
    assert contact.name == "Ahmed Sabry"
    assert contact.email == "ahmed.sabry@nowpay.com"
    assert contact.email_confidence == PATTERN_GUESSED


def test_tier3_team_page_parse_used_when_no_seed_entry(monkeypatch):
    # A domain with no seed data and no Hunter match at all must still
    # try the team-page parse fallback before giving up.
    monkeypatch.setattr(enrichment, "_hunter_domain_search", lambda domain: None)
    monkeypatch.setattr(enrichment, "_hunter_email_finder", lambda domain, first, last: None)
    monkeypatch.setattr(
        enrichment, "_parse_team_page", lambda domain: ContactExtraction(name="Jane Doe", title="CTO")
    )
    contact = enrich_contact("unseeded-example.com", "UnseededExample")
    assert contact.name == "Jane Doe"
    assert contact.email == "jane.doe@unseeded-example.com"
    assert contact.email_confidence == PATTERN_GUESSED


def test_tier4_placeholder_when_nothing_found_anywhere(monkeypatch):
    monkeypatch.setattr(enrichment, "_hunter_domain_search", lambda domain: None)
    monkeypatch.setattr(
        enrichment, "_parse_team_page", lambda domain: ContactExtraction(name=None, title=None)
    )
    contact = enrich_contact("unseeded-example.com", "UnseededExample")
    assert contact.name is None
    assert contact.email == "cto@unseeded-example.com"
    assert contact.email_confidence == PLACEHOLDER


def test_hunter_calls_are_cached_across_repeated_lookups(monkeypatch, tmp_path):
    call_count = {"n": 0}

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"pattern": "{first}.{last}", "emails": []}}

    def _fake_get(url, params, timeout):
        call_count["n"] += 1
        return _FakeResponse()

    monkeypatch.setattr(enrichment, "_CACHE_PATH", str(tmp_path / "hunter_cache.json"))
    monkeypatch.setattr(enrichment.config, "HUNTER_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(enrichment.requests, "get", _fake_get)

    first = enrichment._hunter_domain_search("cached-example.com")
    second = enrichment._hunter_domain_search("cached-example.com")

    assert first == second == {"pattern": "{first}.{last}", "emails": []}
    assert call_count["n"] == 1
