"""
Manually researched public-source leadership data for domains where
Hunter.io's own domain-search doesn't independently surface a named
CTO/CISO/VP Eng — this is the "search LinkedIn/Crunchbase-style public
sources for the name" layer that sits between Hunter and the last-resort
placeholder in enrichment.py.

Hunter's free-tier domain-search caps at 10 results per domain, ranked by
its own relevance signals — a real named executive can exist in Hunter's
underlying dataset without appearing on that first page (this is exactly
what happened for all four companies below: Hunter had zero CTO/CISO/eng-
lead titles in the top 10 for each). Live web search (Crunchbase person
profiles, TheOrg org charts, a company's own engineering blog) fills that
gap with a real, citable name — but this file only ever supplies a
NAME + TITLE, never an email. The email still always comes from
enrichment.py asking Hunter to confirm/construct it, so the eventual
VERIFIED / PATTERN-INFERRED / PATTERN-GUESSED label on the CSV always
reflects what Hunter actually returned, never what this file asserts.

Every entry was verified live on 2026-08-19 against the cited source —
see source_url. Keyed by the CORRECTED domain (tabby.com turned out to be
a wrong domain entirely — an unrelated kids'-tablet company, not the BNPL
fintech — same class of bug as the khazna.com/khazna.app mixup documented
in main.py and the README; the real domain is tabby.ai).

tabby.ai has NO entry here on purpose: Hunter's own domain-search
independently found a real, sourced, deliverability-verified engineering
lead for it (Slava Slutsker, Head of Engineering) — that live Hunter
record is more current than a static seed could be, so enrichment.py's
domain-search tier resolves Tabby before this file is ever consulted.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class KnownExec:
    first_name: str
    last_name: str
    title: str
    source_url: str
    source_note: str

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


KNOWN_LEADERSHIP: dict[str, KnownExec] = {
    "paymob.com": KnownExec(
        first_name="Mostafa",
        last_name="Menessy",
        title="Co-founder & Chief Technology Officer",
        source_url="https://www.crunchbase.com/person/mostafa-menessy",
        source_note="Crunchbase person profile",
    ),
    "nowpay.com": KnownExec(
        first_name="Ahmed",
        last_name="Sabry",
        title="Co-founder & Chief Technology Officer",
        source_url="https://www.crunchbase.com/person/ahmed-sabry-4123",
        source_note=(
            "Crunchbase person profile; NowPay was founded in 2019 by "
            "Mostafa Ashour (CEO) and Ahmed Sabry (CTO), per MENAbytes/"
            "Ventureburn funding coverage"
        ),
    ),
    "tamara.com": KnownExec(
        first_name="Chien",
        last_name="Hoang",
        title="VP Engineering",
        source_url=(
            "https://medium.com/tamara-tech-product/"
            "from-self-taught-developer-to-tech-leader-a-journey-of-"
            "impact-and-growth-e18511dafd37"
        ),
        source_note=(
            "Byline on Tamara's own engineering blog ('Tamara Tech & "
            "Product'), corroborated by RocketReach listing him as VP "
            "Engineering at Tamara"
        ),
    ),
    "khazna.app": KnownExec(
        first_name="Ahmed",
        last_name="Wagueeh",
        title="Co-founder & Chief Technology Officer",
        source_url="https://www.crunchbase.com/person/ahmed-wagueeh",
        source_note=(
            "Crunchbase person profile; Khazna was founded in 2019 by "
            "Omar Saleh, Omar Salah, Ahmed Wagueeh and Fatma ElShenawy"
        ),
    ),
}
