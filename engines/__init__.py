"""
engines/ - Search engines that retrieve citation metadata from external APIs.

Modules:
    academic.py         - CrossrefEngine, OpenAlexEngine, SemanticScholarEngine, PubMedEngine
    books.py            - GoogleBooksAPI, OpenLibraryAPI
    legal.py            - CourtListenerEngine, FamousCasesCache
    google_cse.py       - Google Custom Search Engine
    google_scholar.py   - Google Scholar via SERPAPI
    doi.py              - DOI extraction from publisher URLs
    famous_papers.py    - 51K famous papers cache for fast lookup
    author_year_search.py - Multi-engine search by author+year (for APA/Harvard)
    base.py             - SearchEngine ABC, MultiAttemptEngine base class
"""

from engines.base import SearchEngine, MultiAttemptEngine
from engines.academic import CrossrefEngine, OpenAlexEngine, PubMedEngine
from engines.books import GoogleBooksAPI, OpenLibraryAPI
from engines.legal import CourtListenerEngine, FamousCasesCache

__all__ = [
    'SearchEngine',
    'MultiAttemptEngine',
    'CrossrefEngine',
    'OpenAlexEngine', 
    'PubMedEngine',
    'GoogleBooksAPI',
    'OpenLibraryAPI',
    'CourtListenerEngine',
    'FamousCasesCache',
]
