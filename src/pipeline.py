"""
Orchestrates Discovery -> Enrichment -> Drafting across the target URL
list and writes the CSV deliverable. Does NOT send anything — see the
mock-send comment below.
"""
import csv
import logging
from urllib.parse import urlparse

from . import cost_tracker
from .discovery import discover_company
from .drafting import draft_outreach
from .enrichment import enrich_contact

logger = logging.getLogger(__name__)

CSV_HEADERS = [
    "Company",
    "CTO Name",
    "CTO Email",
    "LinkedIn URL",
    "Drafted Email",
    "Drafted LinkedIn Note",
]


def _domain_and_company(url: str) -> tuple[str, str]:
    netloc = urlparse(url if "://" in url else f"https://{url}").netloc or url
    domain = netloc.replace("www.", "")
    company = domain.split(".")[0].capitalize()
    return domain, company


def run_pipeline(urls: list[str], out_csv_path: str) -> None:
    rows = []
    for url in urls:
        domain, company = _domain_and_company(url)
        logger.info("Processing %s (%s)", company, domain)

        discovery_result = discover_company(url)
        contact = enrich_contact(domain, company)
        draft = draft_outreach(company, discovery_result, contact)

        # MOCK SEND ONLY — we generate the email/LinkedIn payloads above
        # and write them to CSV below. We deliberately do NOT call
        # SendGrid, LinkedIn, or any send API here; per the brief this
        # pipeline generates outreach content for human review, it does
        # not autonomously contact anyone.
        rows.append(
            {
                "Company": company,
                "CTO Name": contact.name or "Unknown (not found on public pages)",
                "CTO Email": contact.email,
                "LinkedIn URL": contact.linkedin_url
                + (
                    " [search link, not a resolved profile]"
                    if contact.linkedin_is_search_link
                    else ""
                ),
                "Drafted Email": f"Subject: {draft.email_subject}\n\n{draft.email_body}",
                "Drafted LinkedIn Note": draft.linkedin_note,
            }
        )

    with open(out_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(rows)

    logger.info("Wrote %d leads to %s", len(rows), out_csv_path)
    cost_tracker.TRACKER.print_summary()
