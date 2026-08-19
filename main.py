"""
Entry point: runs the full GTM loop over the 5 target fintech URLs from
the brief, writes output/leads.csv, prints the projected cost summary,
then runs the reply-classifier demo against the brief's four required
test cases.
"""
import logging

from src.pipeline import run_pipeline
from src.reply_classifier import classify_reply

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# NOTE: the brief listed "khazna.com" as the target. Verified via web
# search that this resolves to an unrelated Gulf trading-card-collection
# app, not the Egyptian earned-wage-access fintech "Khazna" the brief
# means — the real Khazna is at khazna.app. Corrected here; see README's
# "What real-world testing caught" for the full story (the original
# domain produced a discovery result that looked like a hallucination but
# was actually an accurate description of the wrong company).
#
# Same catch, same fix, for "tabby.com": it resolves to an unrelated
# kids'-tablet company ("TABBY | The Kids' Tablet Built for Safe
# Discovery"), not the Tabby BNPL fintech the brief means — the real
# Tabby is at tabby.ai. Verified live (2026-08-19): tabby.com serves that
# unrelated site directly (HTTP 200, no redirect); tabby.ai is the real
# fintech (its CSP header even lists tabby.ai/tabby.sa/tabby.dev as
# related domains). Corrected here for the same reason as Khazna above.
TARGET_URLS = [
    "khazna.app",
    "nowpay.com",
    "paymob.com",
    "tabby.ai",
    "tamara.com",
]


def main() -> None:
    print("=== AgenticGuard GTM Loop ===\n")
    run_pipeline(TARGET_URLS, "output/leads.csv")

    print("\n=== Reply Classifier: required test cases ===")
    cases = [
        "Thanks, but not interested.",
        "Sure, Tuesday works.",
        "Let me think about it.",
        "Yes let's talk",
    ]
    for reply in cases:
        result = classify_reply(reply)
        print(f"  {reply!r} -> {result.model_dump_json()}")


if __name__ == "__main__":
    main()
