"""
Domain-Aware Query Router

Classifies user queries into one or more knowledge domains and routes
them to the appropriate retrieval tools. Supports multi-hop reasoning
by enabling parallel retrieval across multiple domains when a query
spans more than one area.

Domains (matching the data/ directory structure):
  - Academic: Calendars, schedules, dates, holidays, deadlines, events
  - Administrative: Policies, procedures, contact info, fees, financial aid,
                    tuition, scholarships, refunds, campus facilities
  - Educational: Course materials, syllabi, study guides, resources
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Set


class Domain(str, Enum):
    """Knowledge-base domains aligned with the data/ directory structure."""
    ACADEMIC = "academic"
    ADMINISTRATIVE = "administrative"
    EDUCATIONAL = "educational"


# ── Keyword / pattern dictionaries per domain ──────────────────────────

_ACADEMIC_PATTERNS: List[str] = [
    r"\bcalendar\b", r"\bschedule[s]?\b", r"\bholiday[s]?\b",
    r"\bsemester\b", r"\bexam[s]?\b", r"\bexamination[s]?\b",
    r"\bdeadline[s]?\b", r"\bregistration\b", r"\bbreak\b",
    r"\bvacation[s]?\b", r"\bacademic\s*year\b",
    r"\bclass\s*start\b", r"\bclass\s*end\b", r"\bcommencement\b",
    r"\bconvocation\b", r"\borientation\b", r"\brecess\b",
    r"\binternals?\b", r"\bsupplementary\b", r"\bbacklog[s]?\b",
    r"\bmid[\s-]?term[s]?\b", r"\bend[\s-]?sem\b",
    r"\bdate[s]?\b", r"\bwhen\b", r"\bmonth\b",
    r"\bjanuary\b", r"\bfebruary\b", r"\bmarch\b", r"\bapril\b",
    r"\bmay\b", r"\bjune\b", r"\bjuly\b", r"\baugust\b",
    r"\bseptember\b", r"\boctober\b", r"\bnovember\b", r"\bdecember\b",
    r"\bjan\b", r"\bfeb\b", r"\bmar\b", r"\bapr\b",
    r"\bjun\b", r"\bjul\b", r"\baug\b", r"\bsep\b",
    r"\boct\b", r"\bnov\b", r"\bdec\b",
    r"\bdiwali\b", r"\bchristmas\b", r"\bsankranti\b",
    r"\bugadi\b", r"\bindependence\s*day\b", r"\brepublic\s*day\b",
]

_ADMINISTRATIVE_PATTERNS: List[str] = [
    # General admin
    r"\bpolic(?:y|ies)\b", r"\bprocedure[s]?\b", r"\brule[s]?\b",
    r"\bregulation[s]?\b", r"\bcontact\b", r"\bphone\b",
    r"\bemail\b", r"\baddress\b", r"\boffice[s]?\b",
    r"\bdepartment[s]?\b", r"\bfacult(?:y|ies)\b",
    r"\badmission[s]?\b", r"\benroll(?:ment)?\b",
    r"\battendance\b", r"\bgrading\b", r"\bgpa\b", r"\bcgpa\b",
    r"\bwithdraw(?:al)?\b", r"\bdrop\b",
    r"\bcampus\b", r"\bhostel\b", r"\blibrary\b",
    r"\bplacement[s]?\b", r"\bcareer\b", r"\binternship[s]?\b",
    r"\blab(?:oratory|oratories)?\b", r"\binfrastructure\b",
    r"\bprogram(?:me)?[s]?\b", r"\bcourse[s]?\b", r"\bbranch(?:es)?\b",
    r"\bnaac\b", r"\bnba\b", r"\baccreditation\b",
    r"\bragging\b", r"\bdisciplin(?:e|ary)\b",
    r"\bprincipal\b", r"\bdean\b", r"\bhod\b",
    r"\buniversity\b", r"\bjntuk\b", r"\bpvpsit\b",
    r"\bcanteen\b", r"\btransport\b", r"\bbus\b",
    r"\bit\s*help\s*desk\b", r"\btechnical\s*support\b",
    # Financial (part of Administrative domain)
    r"\bfee[s]?\b", r"\btuition\b", r"\bscholarship[s]?\b",
    r"\bfinancial\s*aid\b", r"\brefund[s]?\b", r"\bloan[s]?\b",
    r"\bbilling\b", r"\bpayment[s]?\b", r"\bpay\b",
    r"\bcost[s]?\b", r"\bexpense[s]?\b", r"\bprice[s]?\b",
    r"\bstipend[s]?\b", r"\bwaiver[s]?\b", r"\bdiscount[s]?\b",
    r"\bfine[s]?\b", r"\bdeposit[s]?\b", r"\bcaution\s*deposit\b",
    r"\bhostel\s*fee[s]?\b", r"\btransport\s*fee[s]?\b",
    r"\beducation\s*loan[s]?\b", r"\bbank\b",
    r"\bbursar\b", r"\baccounts\b",
]

_EDUCATIONAL_PATTERNS: List[str] = [
    r"\bsyllabi?\b", r"\bsyllabus\b", r"\bcurriculum\b",
    r"\bstudy\s*(?:guide|material)[s]?\b",
    r"\btext\s*book[s]?\b", r"\breference[s]?\b",
    r"\bnotes?\b", r"\blecture[s]?\b", r"\btutorial[s]?\b",
    r"\bassignment[s]?\b", r"\bproject[s]?\b",
    r"\blearning\s*(?:resource|material|outcome)[s]?\b",
    r"\bmodule[s]?\b", r"\bunit[s]?\b", r"\btopic[s]?\b",
    r"\bteach(?:ing)?\b", r"\bpedagog(?:y|ical)\b",
    r"\bcredit[s]?\b", r"\belective[s]?\b",
    r"\blab\s*manual[s]?\b", r"\bworksheet[s]?\b",
]

# Pre-compiled pattern map (compiled once at import time for speed)
_DOMAIN_REGEXES: dict[Domain, re.Pattern] = {
    domain: re.compile("|".join(patterns), re.IGNORECASE)
    for domain, patterns in [
        (Domain.ACADEMIC, _ACADEMIC_PATTERNS),
        (Domain.ADMINISTRATIVE, _ADMINISTRATIVE_PATTERNS),
        (Domain.EDUCATIONAL, _EDUCATIONAL_PATTERNS),
    ]
}

# Minimum pattern hits needed to consider a domain relevant
_MIN_CONFIDENCE_HITS = 1


@dataclass
class RoutingResult:
    """Result of domain classification for a single query."""
    query: str
    domains: List[Domain]
    scores: dict[Domain, int] = field(default_factory=dict)
    is_multi_domain: bool = False

    @property
    def primary_domain(self) -> Domain | None:
        """Highest-scoring domain, or None if no match."""
        if not self.domains:
            return None
        return self.domains[0]

    def tool_names(self) -> List[str]:
        """Map matched domains to their corresponding tool function names."""
        mapping = {
            Domain.ACADEMIC: ["search_academic_calendar", "check_if_date_is_holiday"],
            Domain.ADMINISTRATIVE: ["search_university_info", "get_university_contact_info"],
            Domain.EDUCATIONAL: ["search_educational_resources"],
        }
        names: list[str] = []
        for d in self.domains:
            names.extend(mapping[d])
        return names


def classify_query(query: str) -> RoutingResult:
    """
    Classify a user query into one or more knowledge domains.

    Uses keyword / regex matching to score each domain.  Domains with
    at least ``_MIN_CONFIDENCE_HITS`` pattern matches are included in
    the result, sorted by descending score.

    If no domain is matched the result contains *all* domains so the
    agent can do a broad search (fallback behaviour).

    Args:
        query: Raw user question text.

    Returns:
        RoutingResult with ordered list of matched domains and scores.
    """
    scores: dict[Domain, int] = {}

    for domain, pattern in _DOMAIN_REGEXES.items():
        hits = len(pattern.findall(query))
        if hits >= _MIN_CONFIDENCE_HITS:
            scores[domain] = hits

    # Sort by score descending
    sorted_domains = sorted(scores, key=lambda d: scores[d], reverse=True)

    # Fallback: if nothing matched, include all domains
    if not sorted_domains:
        sorted_domains = list(Domain)
        scores = {d: 0 for d in Domain}

    is_multi = len(sorted_domains) > 1

    return RoutingResult(
        query=query,
        domains=sorted_domains,
        scores=scores,
        is_multi_domain=is_multi,
    )


def get_routing_context(query: str) -> str:
    """
    Return a compact string that can be prepended to the system prompt
    so the LLM knows which domains were identified and which tools
    to prefer.

    Example output:
        "[Domain Routing] Query classified as: Administrative (3 hits), Academic (1 hit).
         Recommended tools: search_university_info, get_university_contact_info, search_academic_calendar, check_if_date_is_holiday.
         This is a multi-domain query — retrieve from all matched domains before answering."
    """
    result = classify_query(query)

    domain_parts = []
    for d in result.domains:
        hits = result.scores.get(d, 0)
        domain_parts.append(f"{d.value.title()} ({hits} hit{'s' if hits != 1 else ''})")

    tools = result.tool_names()

    lines = [
        f"[Domain Routing] Query classified as: {', '.join(domain_parts)}.",
        f"Recommended tools: {', '.join(tools)}.",
    ]

    if result.is_multi_domain:
        lines.append(
            "This is a MULTI-DOMAIN query — retrieve information from ALL matched "
            "domains before composing your answer to ensure completeness."
        )

    return "\n".join(lines)


# ── Convenience helpers for the graph nodes ─────────────────────────────

def get_domain_tools_for_query(query: str):
    """
    Return only the LangChain tool objects relevant to the classified
    domains.  Used by the graph to dynamically bind tools per turn.

    Falls back to *all* tools when classification is uncertain.
    """
    from app.tools import TOOL_REGISTRY, available_tools

    result = classify_query(query)
    tool_names_set: Set[str] = set(result.tool_names())

    # Filter tools from the registry
    filtered = [t for t in available_tools if t.name in tool_names_set]

    # Safety: never return an empty list — fall back to all tools
    return filtered if filtered else available_tools
