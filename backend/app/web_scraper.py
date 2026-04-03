"""
Web Scraper Module — Official College Website

Scrapes pages from pvpsiddhartha.ac.in, cleans the HTML content,
auto-categorises the extracted text, and feeds it into the knowledge
base (file-system + Qdrant vector store + PostgreSQL Document record).

Uses:
- httpx          — async HTTP client (already a project dependency)
- BeautifulSoup  — HTML parsing and cleaning
"""

from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import ACADEMIC_DIR, ADMINISTRATIVE_DIR, EDUCATIONAL_DIR


# ── Default target pages ──────────────────────────────────────────────

DEFAULT_URLS: list[str] = []

# ── Category detection heuristics ─────────────────────────────────────

_ACADEMIC_KEYWORDS = re.compile(
    r"calendar|exam|schedule|semester|holiday|syllabus|timetable|academic",
    re.IGNORECASE,
)
_ADMIN_KEYWORDS = re.compile(
    r"admission|fee|policy|contact|office|regulation|mandatory|disclosure"
    r"|placement|recruit|infrastructure|hostel|library|transport|facility",
    re.IGNORECASE,
)
_EDUCATIONAL_KEYWORDS = re.compile(
    r"department|course|curriculum|lab|research|faculty|program|b\.?\s?tech"
    r"|m\.?\s?tech|cse|ece|eee|mech|civil|it\b|mba|phd",
    re.IGNORECASE,
)

CATEGORY_DIRS = {
    "Academic": ACADEMIC_DIR,
    "Administrative": ADMINISTRATIVE_DIR,
    "Educational": EDUCATIONAL_DIR,
}


def categorize_content(url: str, text: str) -> str:
    """Return the most likely category for scraped content."""
    combined = f"{url} {text[:2000]}"
    scores = {
        "Academic": len(_ACADEMIC_KEYWORDS.findall(combined)),
        "Administrative": len(_ADMIN_KEYWORDS.findall(combined)),
        "Educational": len(_EDUCATIONAL_KEYWORDS.findall(combined)),
    }
    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    # Default to Administrative when no strong signal
    return best if scores[best] > 0 else "Administrative"


# ── HTML cleaning ─────────────────────────────────────────────────────

_STRIP_TAGS = {"script", "style", "nav", "footer", "header", "noscript", "iframe", "form"}


def clean_html(html: str, url: str = "") -> str:
    """
    Extract meaningful text from raw HTML.

    Removes scripts, styles, nav/footer chrome, and collapses whitespace.
    Adds the source URL as a header line for provenance.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Drop non-content elements
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()

    # Try to grab <main> or <article> first; fall back to <body>
    content = soup.find("main") or soup.find("article") or soup.find("body") or soup
    raw_text = content.get_text(separator="\n", strip=True)

    # Collapse multiple blank lines
    lines = [ln.strip() for ln in raw_text.splitlines()]
    cleaned = "\n".join(ln for ln in lines if ln)

    # Remove very short scrapes (cookie banners, error pages, etc.)
    if len(cleaned) < 100:
        return ""

    header = f"Source: {url}\nScraped: {datetime.now(timezone.utc).isoformat()}\n\n"
    return header + cleaned


# ── Filename helper ───────────────────────────────────────────────────

def _url_to_filename(url: str) -> str:
    """Derive a safe .txt filename from a URL."""
    parsed = urlparse(url)
    path = parsed.path.strip("/").replace("/", "_") or "index"
    # Strip common extensions
    path = re.sub(r"\.(aspx?|html?|php|jsp)$", "", path, flags=re.IGNORECASE)
    # Collapse unsafe chars
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", path)
    # Prefix with abbreviated domain
    domain = parsed.netloc.replace("www.", "").split(".")[0]  # e.g. "pvpsiddhartha"
    name = f"scraped_{domain}_{safe}" if safe else f"scraped_{domain}_index"
    return name[:120] + ".txt"


# ── Page result ───────────────────────────────────────────────────────

@dataclass
class PageResult:
    url: str
    success: bool
    category: str = ""
    filename: str = ""
    text_length: int = 0
    chunks: int = 0
    error: str = ""


# ── Core scraping logic ──────────────────────────────────────────────

async def scrape_page(client: httpx.AsyncClient, url: str) -> tuple[str, str]:
    """
    Fetch *url* and return ``(cleaned_text, filename)``.

    Raises on HTTP or parsing errors.
    """
    response = await client.get(url, follow_redirects=True, timeout=20.0)
    response.raise_for_status()

    text = clean_html(response.text, url)
    if not text:
        raise ValueError("Page contained no useful content after cleaning")

    filename = _url_to_filename(url)
    return text, filename


async def run_scrape(
    urls: list[str] | None = None,
) -> list[PageResult]:
    """
    Scrape a list of URLs, save extracted text to the data directory,
    index in Qdrant, and return per-page results.

    This function does **not** touch the database directly — callers
    (the API endpoint) should create the ``ScraperRun`` record and
    ``Document`` records.

    Returns a list of ``PageResult`` objects.
    """
    if urls is None:
        urls = list(DEFAULT_URLS)

    results: list[PageResult] = []

    async with httpx.AsyncClient(
        headers={
            "User-Agent": "EduBot+ Web Scraper/1.0 (educational; pvpsiddhartha.ac.in)"
        },
    ) as client:
        for url in urls:
            pr = PageResult(url=url, success=False)
            try:
                text, filename = await scrape_page(client, url)
                category = categorize_content(url, text)

                # Ensure target directory exists
                target_dir = CATEGORY_DIRS[category]
                try:
                    target_dir.mkdir(parents=True, exist_ok=True)
                    file_path = target_dir / filename
                    # Save .txt (overwrite on re-scrape)
                    file_path.write_text(text, encoding="utf-8")
                except OSError:
                    # Read-only filesystem (e.g. Vercel) – skip local save
                    pass

                # Index in Qdrant
                chunk_count = 0
                try:
                    from app.vector_store import index_document
                    chunk_count, _ = index_document(text, filename, category)
                except Exception as vec_err:
                    pr.error = f"Vector indexing warning: {vec_err}"

                pr.success = True
                pr.category = category
                pr.filename = filename
                pr.text_length = len(text)
                pr.chunks = chunk_count

            except httpx.HTTPStatusError as e:
                pr.error = f"HTTP {e.response.status_code}"
            except httpx.RequestError as e:
                pr.error = f"Request error: {e}"
            except ValueError as e:
                pr.error = str(e)
            except Exception as e:
                pr.error = f"Unexpected: {e}"

            results.append(pr)

    return results


# ── In-memory URL config ──────────────────────────────────────────────

class ScraperConfig:
    """Simple in-memory store for the target URL list."""

    def __init__(self) -> None:
        self.urls: list[str] = list(DEFAULT_URLS)

    def get_urls(self) -> list[str]:
        return list(self.urls)

    def set_urls(self, urls: list[str]) -> None:
        # Basic validation
        self.urls = [u.strip() for u in urls if u.strip().startswith("http")]

    def add_url(self, url: str) -> bool:
        url = url.strip()
        if url and url.startswith("http") and url not in self.urls:
            self.urls.append(url)
            return True
        return False

    def remove_url(self, url: str) -> bool:
        url = url.strip()
        if url in self.urls:
            self.urls.remove(url)
            return True
        return False


# Global singleton
scraper_config = ScraperConfig()
