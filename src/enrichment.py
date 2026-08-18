"""
Task 2: Enrichment. Finds a CTO/CISO name + email.

Priority order:
1. Hunter.io free tier domain search, if HUNTER_API_KEY is set — real,
   attributed emails only (we only accept a result where Hunter itself
   returns an actual email value for an executive-level contact, never a
   pattern guess with no verified value).
2. Otherwise, parse the company's public About/Team page with the cheap
   model to find a named CTO/CISO — if found, construct a placeholder
   email at that domain, clearly flagged in the data itself.
3. If no name is found anywhere, construct a role-based placeholder
   (cto@domain) and flag it the same way.

Never resolves a real LinkedIn profile URL — LinkedIn's ToS prohibits
scraping profile data; in production this is exactly where Apollo.io's
API would replace this function's contact-lookup role, since Apollo
licenses this data rather than scraping it (see README). Instead this
builds a real, working LinkedIn PEOPLE-SEARCH url for the name + company
— an honest link a human can click and resolve themselves, never a
fabricated profile URL asserted as real.
"""
import json
import logging
import urllib.parse
from dataclasses import dataclass
from typing import Optional

import requests

from . import config, discovery, prompts, providers
from .schemas import ContactExtraction

logger = logging.getLogger(__name__)

TEAM_PAGE_PATHS = ["/about", "/about-us", "/team", "/leadership", "/company"]


@dataclass
class ContactInfo:
    name: Optional[str]
    email: str
    email_is_placeholder: bool
    linkedin_url: str
    linkedin_is_search_link: bool


def _hunter_lookup(domain: str) -> Optional[tuple[ContactExtraction, str]]:
    if not config.HUNTER_API_KEY:
        return None
    try:
        resp = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={
                "domain": domain,
                "api_key": config.HUNTER_API_KEY,
                "seniority": "executive",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        for person in data.get("emails", []):
            position = (person.get("position") or "").lower()
            is_target_role = "cto" in position or "chief technology" in position or "ciso" in position
            if is_target_role and person.get("value"):  # only accept a real returned email
                name = f"{person.get('first_name', '')} {person.get('last_name', '')}".strip() or None
                return ContactExtraction(name=name, title=person.get("position")), person["value"]
    except requests.RequestException as e:
        logger.warning("Hunter.io lookup failed for %s: %s", domain, e)
    return None


def _parse_team_page(domain: str) -> ContactExtraction:
    for path in TEAM_PAGE_PATHS:
        text = discovery.fetch_page_text(f"https://{domain}{path}")
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
            logger.warning("team page parse failed for %s%s: %s", domain, path, e)
    return ContactExtraction(name=None, title=None)


def _linkedin_search_url(name: Optional[str], company: str) -> str:
    query = f"{name} {company}" if name else company
    return "https://www.linkedin.com/search/results/people/?keywords=" + urllib.parse.quote(query)


def enrich_contact(domain: str, company: str) -> ContactInfo:
    hunter_result = _hunter_lookup(domain)
    if hunter_result:
        extraction, real_email = hunter_result
        return ContactInfo(
            name=extraction.name,
            email=real_email,
            email_is_placeholder=False,
            linkedin_url=_linkedin_search_url(extraction.name, company),
            linkedin_is_search_link=True,
        )

    extraction = _parse_team_page(domain)
    placeholder_email = f"cto@{domain}"
    return ContactInfo(
        name=extraction.name,
        email=f"{placeholder_email} [UNVERIFIED PLACEHOLDER]",
        email_is_placeholder=True,
        linkedin_url=_linkedin_search_url(extraction.name, company),
        linkedin_is_search_link=True,
    )
