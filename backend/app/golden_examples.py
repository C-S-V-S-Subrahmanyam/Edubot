"""Utilities for retrieving relevant golden examples from PostgreSQL."""

from __future__ import annotations

import re
from typing import List

import psycopg
from psycopg.rows import dict_row

from app.config import DATABASE_URL_SYNC


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    # Drop very short terms to keep SQL predicates meaningful.
    return [t for t in tokens if len(t) >= 3][:8]


def get_relevant_golden_examples(query: str, limit: int = 3) -> List[dict]:
    """Return up to ``limit`` active golden examples that best match query terms."""
    terms = _tokenize(query)
    if not terms:
        return []

    like_clauses = []
    params: list[str] = []
    for term in terms:
        like_clauses.append("(original_query ILIKE %s OR golden_response ILIKE %s)")
        like_term = f"%{term}%"
        params.extend([like_term, like_term])

    sql = (
        "SELECT id, source_type, original_query, original_response, golden_response, created_at "
        "FROM golden_examples "
        "WHERE is_active = TRUE AND (" + " OR ".join(like_clauses) + ") "
        "ORDER BY created_at DESC "
        "LIMIT %s"
    )
    params.append(str(limit))

    try:
        with psycopg.connect(DATABASE_URL_SYNC, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                return list(rows)
    except Exception:
        # Golden examples are best-effort context only; never fail chat flow.
        return []


def format_golden_examples_for_prompt(examples: List[dict]) -> str:
    if not examples:
        return ""

    lines = ["--- RELEVANT GOLDEN EXAMPLES (Admin-curated) ---"]
    for i, ex in enumerate(examples, start=1):
        lines.append(f"Example {i} [source={ex.get('source_type', 'manual')}]")
        lines.append(f"User query: {ex.get('original_query', '')}")
        lines.append(f"Ideal response: {ex.get('golden_response', '')}")
        lines.append("---")
    lines.append("Use these examples to improve style, structure, and factual grounding where relevant.")
    lines.append("--- END GOLDEN EXAMPLES ---")
    return "\n".join(lines)
