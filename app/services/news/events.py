"""Rule-based event extraction + event studies (addendum C/D).

Events are extracted from news items by inspectable rules with confidence
scores (not opaque inference). Event studies measure price paths around
events with explicit windows, sample sizes and CIs — no p-hacking.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

EVENT_RULES = [
    (
        "rate_decision",
        r"(نرخ بهره|interest rate|rate (decision|hike|cut)|فدرال رزرو|federal reserve|بانک مرکزی)",
        0.8,
    ),
    (
        "sanctions",
        r"(تحریم|sanction|ofac|embargo|ممنوعیت صادرات)",
        0.85,
    ),
    (
        "inflation_print",
        r"(تورم|inflation|cpi|شاخص قیمت)",
        0.7,
    ),
    (
        "market_move",
        r"(جهش|ریزش|surge|plunge|رکورد|record high|record low|سقوط)",
        0.6,
    ),
    (
        "policy_domestic",
        r"(بانک مرکزی|نیما|یارانه|بودجه|budget|central bank)",
        0.65,
    ),
]


@dataclass(frozen=True)
class Event:
    event_type: str
    confidence: float
    item_title: str
    detected_by: str = "rules/1"


def extract_events(title: str, snippet: str = "") -> list[Event]:
    text = f"{title} {snippet}".lower()
    out: list[Event] = []
    for etype, pattern, conf in EVENT_RULES:
        if re.search(pattern, text):
            out.append(Event(etype, conf, title))
    return out


@dataclass
class EventStudyResult:
    event_type: str
    window_days: int
    n_events: int
    mean_return: float
    std_return: float
    ci_low: float
    ci_high: float
    note: str = "observational study — no causal claim"


def event_study(
    event_type: str,
    event_returns: Sequence[float],
    window_days: int,
) -> EventStudyResult:
    """Mean post-event return with a normal-approx 95% CI and sample size."""
    n = len(event_returns)
    if n == 0:
        return EventStudyResult(
            event_type,
            window_days,
            0,
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
            "no events in sample",
        )
    mean = sum(event_returns) / n
    var = sum((x - mean) ** 2 for x in event_returns) / max(1, n - 1)
    se = (var / n) ** 0.5 if n > 1 else float("nan")
    ci = 1.96 * se if n > 1 else float("nan")
    return EventStudyResult(
        event_type,
        window_days,
        n,
        round(mean, 6),
        round(var**0.5, 6) if n > 1 else float("nan"),
        round(mean - ci, 6) if n > 1 else float("nan"),
        round(mean + ci, 6) if n > 1 else float("nan"),
    )
