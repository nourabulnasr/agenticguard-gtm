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

TARGET_URLS = [
    "khazna.com",
    "nowpay.com",
    "paymob.com",
    "tabby.com",
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
