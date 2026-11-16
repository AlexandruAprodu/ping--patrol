"""In-memory rule evaluator, API.md §3."""
from dataclasses import dataclass
from enum import StrEnum


class Transition(StrEnum):
    NONE = "NONE"
    TRIGGERED = "TRIGGERED"
    RECOVERED = "RECOVERED"


@dataclass(frozen=True)
class RuleState:
    consecutive_failures: int = 0
    alerting: bool = False


def evaluate_check(
    state: RuleState, *, healthy: bool, failure_threshold: int
) -> tuple[RuleState, Transition]:
    ...
