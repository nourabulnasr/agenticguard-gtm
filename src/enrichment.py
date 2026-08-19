"""
Task 2: Enrichment. Finds a real CTO/CISO/VP Eng name + email, and is
explicit in the data itself about how confident that email is.

Priority order (each tier only runs if the one above didn't produce a
result):

1. Hunter.io domain-search on the company's domain, scanned for a named
   person whose title matches CTO/CISO/VP Eng/Head of Engineering. If
   Hunter's own dataset has a real, found (not pattern-generated) email
   for that person -> VERIFIED.
2. A manually researched, cited public-source name for this domain
   (`known_leadership.py` — built from live Crunchbase/TheOrg/company-blog
   lookups, never invented) fed into Hunter's email-finder:
   - Hunter finds a real, sourced email for that exact name -> VERIFIED.
   - Hunter only has a confirmed email PATTERN for the domain (either via
     email-finder's "generated" result or via domain-search's `pattern`
     field) -> construct the email from that real pattern -> PATTERN-INFERRED.
   - Hunter has no data on the domain at all -> construct a generic
     first.last@domain guess -> PATTERN-GUESSED, honestly weaker than
     PATTERN-INFERRED since no real pattern backs it.
3. Parse the company's public About/Team page (including pages linked
   from the homepage nav, not just guessed static paths) with the cheap
   model for a named CTO/CISO/VP Eng, then run the same Hunter
   confirm-or-construct logic from step 2 on whatever name is found.
4. Nothing real found anywhere -> a role-based placeholder (cto@domain),
   clearly flagged PLACEHOLDER.

Hunter.io responses are cached to a local JSON file (`.hunter_cache.json`,
gitignored) keyed by request — the free tier is a shared 25 searches/month
budget, and this pipeline is re-run often during development.

Never resolves a real LinkedIn profile URL by scraping — LinkedIn's ToS
prohibits that; in production this is exactly where Apollo.io's API would
replace this function's contact-lookup role, since Apollo licenses this
data rather than scraping it (see README). When Hunter itself returns a
real linkedin_url (it licenses/aggregates this data, it doesn't scrape),
we use it directly. Otherwise we build a real, working LinkedIn
PEOPLE-SEARCH url for the name + company — an honest link a human can
click and resolve themselves, never a fabricated profile URL asserted as
real.
"""
import json
import logging
import os
import re
import urllib.parse
from dataclasses import dataclass
from typing import Optional

import requests

from . import config, discovery, known_leadership, prompts, providers
from .schemas import ContactExtraction

logger = logging.getLogger(__name__)

TEAM_PAGE_PATHS = [
    "/about", "/about-us", "/team", "/leadership", "/company",
    "/leadership-team", "/our-team", "/people", "/company/about",
    "/en/about-us", "/about/leadership",
]
# Homepage nav links whose href or link text contains one of these are
# also tried, in addition to the static guesses above — this is what
# lets the pipeline find team pages it didn't already know the URL of.
_TEAM_LINK_HINTS = ("team", "leadership", "about", "company", "people", "management")

_ROLE_KEYWORDS = (
    "cto", "chief technology officer", "chief technology",
    "ciso", "chief information security officer", "chief information security",
    "vp engineering", "vp of engineering", "vice president of engineering",
    "vice president, engineering", "head of engineering", "director of engineering",
)
# Word-boundary matching, not bare substrings: "cto" is a literal substring
# of "director" (di-rec-TO-r... "c-t-o" falls right in the middle), so a
# naive `"cto" in title.lower()` false-positives on ANY "Director" title —
# caught by actually running the pipeline against the 5 live targets,
# where it silently matched Khazna's "Funnel Growth Director" and
# Paymob's "Treasury Director" as if they were the CTO.
_ROLE_KEYWORD_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _ROLE_KEYWORDS) + r")\b"
)

VERIFIED = "VERIFIED"
PATTERN_INFERRED = "PATTERN-INFERRED"
PATTERN_GUESSED = "PATTERN-GUESSED"
PLACEHOLDER = "PLACEHOLDER"

_CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".hunter_cache.json")


@dataclass
class ContactInfo:
    name: Optional[str]
    title: Optional[str]
    email: str
    email_confidence: str  # one of VERIFIED / PATTERN_INFERRED / PATTERN_GUESSED / PLACEHOLDER
    email_confidence_note: str
    linkedin_url: str
    linkedin_is_search_link: bool


# ---------------------------------------------------------------------
# Hunter.io — cached HTTP calls
# ---------------------------------------------------------------------


def _cache_load() -> dict:
    try:
        with open(_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _cache_get(key: str):
    cache = _cache_load()
    entry = cache.get(key)
    return entry["value"] if entry is not None else None


def _cache_set(key: str, value) -> None:
    cache = _cache_load()
    cache[key] = {"value": value}
    with open(_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def _hunter_get(path: str, params: dict, cache_key: str) -> Optional[dict]:
    if not config.HUNTER_API_KEY:
        return None
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        resp = requests.get(
            f"https://api.hunter.io/v2/{path}",
            params={**params, "api_key": config.HUNTER_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        _cache_set(cache_key, data)
        return data
    except requests.RequestException as e:
        logger.warning("Hunter.io %s failed for %s: %s", path, params.get("domain"), e)
        return None


def _hunter_domain_search(domain: str) -> Optional[dict]:
    return _hunter_get("domain-search", {"domain": domain, "limit": 10}, f"domain-search:{domain}")


def _hunter_email_finder(domain: str, first_name: str, last_name: str) -> Optional[dict]:
    return _hunter_get(
        "email-finder",
        {"domain": domain, "first_name": first_name, "last_name": last_name},
        f"email-finder:{domain}:{first_name}:{last_name}",
    )


def _apply_pattern(pattern: str, first: str, last: str) -> str:
    first, last = first.lower(), last.lower()
    local = pattern
    for token, value in (("{first}", first), ("{last}", last), ("{f}", first[:1]), ("{l}", last[:1])):
        local = local.replace(token, value)
    return local


def _find_role_match(hunter_domain_data: dict) -> Optional[dict]:
    for person in hunter_domain_data.get("emails", []):
        if not person.get("value"):
            continue
        titles = " ".join(filter(None, [person.get("position"), person.get("position_raw")])).lower()
        if _ROLE_KEYWORD_PATTERN.search(titles):
            return person
    return None


def _resolve_email_for_name(
    domain: str, first: str, last: str, hunter_domain_data: Optional[dict]
) -> tuple[str, str, str]:
    """Ask Hunter to confirm/construct an email for a name we already
    have from elsewhere (seed data or a team-page parse). Returns
    (email, confidence_label, note)."""
    finder = _hunter_email_finder(domain, first, last)
    if finder and finder.get("email"):
        status = (finder.get("verification") or {}).get("status") or "unknown"
        if finder.get("source_type") == "found":
            return (
                finder["email"],
                VERIFIED,
                f"Hunter.io found this exact address for {first} {last} from a real "
                f"source (verification status: {status})",
            )
        return (
            finder["email"],
            PATTERN_INFERRED,
            f"Hunter.io constructed this from the domain's confirmed email pattern "
            f"for {first} {last} (verification status: {status})",
        )

    if hunter_domain_data and hunter_domain_data.get("pattern"):
        pattern = hunter_domain_data["pattern"]
        local = _apply_pattern(pattern, first, last)
        email_domain = domain
        return (
            f"{local}@{email_domain}",
            PATTERN_INFERRED,
            f"Constructed from Hunter.io's confirmed '{pattern}' pattern for {domain} "
            f"(seen on other real addresses at this domain) — not individually "
            f"confirmed for {first} {last}",
        )

    guessed = f"{first}.{last}@{domain}".lower()
    return (
        guessed,
        PATTERN_GUESSED,
        f"Hunter.io has no data at all for {domain} — common first.last email "
        f"convention applied to a publicly-sourced name, unverified by any tool",
    )


# ---------------------------------------------------------------------
# Team-page parsing fallback (broadened: static guesses + discovered nav links)
# ---------------------------------------------------------------------


def _discover_team_page_urls(domain: str) -> list[str]:
    home_html = discovery.fetch_page_html(f"https://{domain}")
    if not home_html:
        return []
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(home_html, "html.parser")
    found = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(separator=" ").strip().lower()
        haystack = f"{href.lower()} {text}"
        if any(hint in haystack for hint in _TEAM_LINK_HINTS):
            resolved = urllib.parse.urljoin(f"https://{domain}", href)
            if urllib.parse.urlparse(resolved).netloc.replace("www.", "") == domain and resolved not in found:
                found.append(resolved)
    return found[:5]  # cap discovery so a large nav doesn't blow up request volume


def _parse_team_page(domain: str) -> ContactExtraction:
    candidate_urls = [f"https://{domain}{path}" for path in TEAM_PAGE_PATHS]
    candidate_urls += _discover_team_page_urls(domain)

    for url in candidate_urls:
        text = discovery.fetch_page_text(url)
        if not text:
            continue
        try:
            result = providers.call_cheap(
                system=prompts.ENRICHMENT_SYSTEM_PROMPT,
                user=f"Page text:\n{text}",
                json_mode=True,
                max_tokens=150,
            )
            start, end = result.text.find("{"), result.text.rfind("}")
            payload = json.loads(result.text[start : end + 1])
            extraction = ContactExtraction.model_validate(payload)
            if extraction.name:
                return extraction
        except Exception as e:
            logger.warning("team page parse failed for %s: %s", url, e)
    return ContactExtraction(name=None, title=None)


def _linkedin_search_url(name: Optional[str], company: str) -> str:
    query = f"{name} {company}" if name else company
    return "https://www.linkedin.com/search/results/people/?keywords=" + urllib.parse.quote(query)


# ---------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------


def enrich_contact(domain: str, company: str) -> ContactInfo:
    hunter_domain_data = _hunter_domain_search(domain)

    # Tier 1: Hunter's own domain-search independently names a
    # role-matching exec with a real (not pattern-generated) email.
    if hunter_domain_data:
        match = _find_role_match(hunter_domain_data)
        if match:
            name = f"{match.get('first_name', '')} {match.get('last_name', '')}".strip() or None
            title = match.get("position_raw") or match.get("position")
            status = (match.get("verification") or {}).get("status") or "unknown"
            linkedin = match.get("linkedin")
            return ContactInfo(
                name=name,
                title=title,
                email=match["value"],
                email_confidence=VERIFIED,
                email_confidence_note=(
                    f"Hunter.io domain-search found this address directly for "
                    f"{name} ({title}), source: {match.get('source_type', 'found')}, "
                    f"verification status: {status}, confidence: {match.get('confidence')}"
                ),
                linkedin_url=linkedin or _linkedin_search_url(name, company),
                linkedin_is_search_link=not bool(linkedin),
            )

    # Tier 2: a manually researched, cited public-source name for this
    # domain, with Hunter asked to confirm or construct the email.
    seed = known_leadership.KNOWN_LEADERSHIP.get(domain)
    if seed:
        email, label, note = _resolve_email_for_name(
            domain, seed.first_name, seed.last_name, hunter_domain_data
        )
        return ContactInfo(
            name=seed.full_name,
            title=seed.title,
            email=email,
            email_confidence=label,
            email_confidence_note=(
                f"{note}. Name/title sourced from {seed.source_url} ({seed.source_note})."
            ),
            linkedin_url=_linkedin_search_url(seed.full_name, company),
            linkedin_is_search_link=True,
        )

    # Tier 3: broadened team-page parse for domains with no seed entry.
    extraction = _parse_team_page(domain)
    if extraction.name:
        parts = extraction.name.split()
        if len(parts) >= 2:
            first, last = parts[0], parts[-1]
            email, label, note = _resolve_email_for_name(domain, first, last, hunter_domain_data)
            note = f"{note}. Name found by parsing {domain}'s public team page."
        else:
            email, label, note = (
                f"cto@{domain}",
                PLACEHOLDER,
                f"Found a single-word name ({extraction.name}) on {domain}'s team page — "
                f"not enough to construct or confirm an email",
            )
        return ContactInfo(
            name=extraction.name,
            title=extraction.title,
            email=email,
            email_confidence=label,
            email_confidence_note=note,
            linkedin_url=_linkedin_search_url(extraction.name, company),
            linkedin_is_search_link=True,
        )

    # Tier 4: nothing real found anywhere.
    return ContactInfo(
        name=None,
        title=None,
        email=f"cto@{domain}",
        email_confidence=PLACEHOLDER,
        email_confidence_note=(
            "No named CTO/CISO/VP Eng found via Hunter.io domain-search, "
            "public-source research, or the company's team pages."
        ),
        linkedin_url=_linkedin_search_url(None, company),
        linkedin_is_search_link=True,
    )
