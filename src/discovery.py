"""
Task 1: Discovery. Fetches a company's public homepage, identifies their
AI feature, maps it to an AgenticGuard risk category. Routed to the CHEAP
role — this is mechanical extraction, not persuasive writing.

Respects robots.txt: before fetching any URL, checks whether our user
agent is allowed to fetch that specific path, and skips the fetch (falling
back to an honest "no specific AI feature identified" DiscoveryResult) if
disallowed, rather than fetching anyway.
"""
import json
import logging
import urllib.robotparser
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from pydantic import ValidationError

from . import prompts, providers
from .schemas import DiscoveryResult

logger = logging.getLogger(__name__)

USER_AGENT = "AgenticGuardGTMBot/1.0 (+https://agenticguard.example/bot)"
TIMEOUT_SECONDS = 10
MAX_PAGE_CHARS = 6000  # keep the cheap-model call small and cheap

_NOT_FOUND = DiscoveryResult(
    ai_feature="no specific AI feature identified from public site",
    risk_category="none",
    risk_rationale="Page could not be fetched (network error or robots.txt disallow).",
)


def _robots_allowed(url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
    except Exception:
        # No readable robots.txt -> treat as allowed (standard behavior);
        # a network failure here should not block discovery entirely.
        return True
    return rp.can_fetch(USER_AGENT, url)


def _fetch_page(url: str) -> str:
    """Shared robots-checked fetch. Returns raw HTML, or "" on any failure
    (network error, non-2xx, robots.txt disallow) — never raises, since
    every caller treats "nothing fetched" as a normal, honest outcome."""
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    if not _robots_allowed(url):
        logger.warning("robots.txt disallows fetching %s, skipping", url)
        return ""
    try:
        resp = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("fetch failed for %s: %s", url, e)
        return ""
    return resp.text


def fetch_page_html(url: str) -> str:
    """Raw HTML (robots-checked), for callers that need actual markup —
    e.g. enrichment.py's team-page link discovery, which needs real <a>
    tags, not the text-only output fetch_page_text produces."""
    return _fetch_page(url)


def fetch_page_text(url: str) -> str:
    html = _fetch_page(url)
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())
    return text[:MAX_PAGE_CHARS]


def discover_company(url: str) -> DiscoveryResult:
    page_text = fetch_page_text(url)
    if not page_text:
        return _NOT_FOUND

    user_prompt = f"Company homepage URL: {url}\n\nScraped page text:\n{page_text}"

    for attempt in range(2):
        try:
            result = providers.call_cheap(
                system=prompts.DISCOVERY_SYSTEM_PROMPT,
                user=user_prompt,
                json_mode=True,
                max_tokens=400,
            )
            start, end = result.text.find("{"), result.text.rfind("}")
            payload = json.loads(result.text[start : end + 1])
            return DiscoveryResult.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            logger.warning("discover_company attempt %d failed: %s", attempt + 1, e)

    return DiscoveryResult(
        ai_feature="no specific AI feature identified from public site",
        risk_category="none",
        risk_rationale="Model output could not be parsed after retry.",
    )
