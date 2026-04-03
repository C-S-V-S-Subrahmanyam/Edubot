"""
RAG Retrieval Tools — Qdrant Semantic Search

Tools for semantic similarity search across embedded documents.
Uses Qdrant vector store for cosine-similarity retrieval with
all-MiniLM-L6-v2 embeddings.

Categories:
- Academic: calendars, schedules, dates
- Administrative: policies, procedures, contact info, fees
- Educational: course materials, resources
"""

from langchain_core.tools import tool
from app.vector_store import search_documents


def _format_results(results: list, domain: str) -> str:
    """Format search results into a readable string with source citations.

    Each result block is prefixed with a ``[SOURCE: filename | category | score]``
    tag so the LLM can easily reference the originating document when composing
    its answer.
    """
    if not results:
        return (
            f"No relevant {domain} information found. "
            "The related data is not present in the system."
        )

    sections = []
    for r in results:
        source = f"[SOURCE: {r['filename']} | {r['category']} | relevance: {r['score']}]"
        sections.append(f"{source}\n{r['text']}")

    return "\n\n---\n\n".join(sections)


@tool
def search_university_info(query: str) -> str:
    """Search administrative information for university policies, procedures,
    programs, fees, financial aid, services, and contact information."""
    results = search_documents(query, category="Administrative")
    return _format_results(results, "administrative")


@tool
def search_academic_calendar(query: str) -> str:
    """Search academic files for dates, holidays, deadlines, exam schedules,
    and academic events."""
    results = search_documents(query, category="Academic")
    return _format_results(results, "academic")


@tool
def check_if_date_is_holiday(date_str: str) -> str:
    """Check if a specific date is a university holiday by searching the
    academic calendar."""
    results = search_documents(f"{date_str} holiday", category="Academic")
    return _format_results(results, "holiday")


@tool
def get_university_contact_info(department: str) -> str:
    """Get contact information for a specific university department or office."""
    results = search_documents(f"{department} contact", category="Administrative")
    return _format_results(results, "contact")


@tool
def search_educational_resources(query: str) -> str:
    """Search educational resource files for course materials, syllabi,
    study guides, and educational content."""
    results = search_documents(query, category="Educational")
    return _format_results(results, "educational")


@tool
def search_all_domains(query: str) -> str:
    """Search across ALL domains (academic, administrative, educational) when
    the query spans multiple topics or the domain is unclear."""
    results = search_documents(query, category=None)
    return _format_results(results, "university")


# List of all available tools
available_tools = [
    search_university_info,
    search_academic_calendar,
    check_if_date_is_holiday,
    get_university_contact_info,
    search_educational_resources,
    search_all_domains,
]

# Registry for name-based lookup (used by query_router)
TOOL_REGISTRY: dict[str, object] = {t.name: t for t in available_tools}
