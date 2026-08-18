"""
Tracks real token usage from every provider call and projects it against
the PRODUCTION architecture's pricing (Claude Haiku 4.5 / Sonnet 5), per
config.PRICING — regardless of which free-tier model actually served the
call. Actual PoC spend is always $0 (free tier); this answers "what would
this run cost on the architecture the brief specifies."
"""
from dataclasses import dataclass, field

from . import config
from .providers import LLMResult


@dataclass
class CostTracker:
    calls: list = field(default_factory=list)

    def record(self, result: LLMResult) -> None:
        self.calls.append(result)

    def _cost_of(self, result: LLMResult) -> float:
        rate = config.PRICING[result.role]
        return (
            result.input_tokens * rate["input_per_1m"] / 1_000_000
            + result.output_tokens * rate["output_per_1m"] / 1_000_000
        )

    def total_projected_usd(self) -> float:
        return sum(self._cost_of(c) for c in self.calls)

    def print_summary(self) -> None:
        print("\n=== Cost Tracker (projected onto Haiku 4.5 / Sonnet 5 pricing) ===")
        for c in self.calls:
            rate = config.PRICING[c.role]
            cost = self._cost_of(c)
            print(
                f"  [{c.role:7s}] {c.model:28s} "
                f"in={c.input_tokens:5d} out={c.output_tokens:4d} "
                f"-> ${cost:.5f} (as {rate['model_label']})"
            )
        total = self.total_projected_usd()
        print(f"  {'-' * 60}")
        print(f"  TOTAL PROJECTED COST: ${total:.4f}  (actual PoC spend: $0.00, free tier)")
        print(f"  Budget check: {'PASS' if total < 50 else 'FAIL'} (<$50 for this run)")


TRACKER = CostTracker()
