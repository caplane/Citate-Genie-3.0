"""
processors/ - Document-level processing pipelines.

Modules:
    word_document.py        - Read/write Word footnotes and endnotes + body text
    author_date.py          - Full pipeline for author-year citation documents (legacy)
    author_year_extractor.py - Parse "(Smith, 2020)" patterns from text
    
    # New unified processor modules (2025-12-12):
    url_extractor.py        - Extract URLs from document body
    doi_extractor.py        - Extract DOIs, PMIDs, arXiv IDs, ISBNs
    parenthetical_extractor.py - Extract (Author, Year) and narrative citations
    citation_classifier.py  - Route citations to correct lookup engines
    topic_extractor.py      - Extract document topics for AI context
    footnote_builder.py     - Build footnote-style output
    author_date_builder.py  - Build author-date + References output
    orchestrator.py         - Thin wiring layer coordinating all modules
    
    # Embedded metadata cache (2025-12-14):
    document_metadata.py    - Read/write citation cache embedded in documents
"""

from processors.word_document import WordDocumentProcessor
from processors.author_date import process_author_date_document
from processors.orchestrator import process_document_unified, ProcessingResult
from processors.document_metadata import (
    CitationMetadataCache,
    load_cache_from_docx,
    save_cache_to_docx,
    export_cache_to_csv,
    hash_citation_text,
)

__all__ = [
    # Legacy
    'WordDocumentProcessor',
    'process_author_date_document',
    # New unified processor
    'process_document_unified',
    'ProcessingResult',
    # Embedded metadata cache
    'CitationMetadataCache',
    'load_cache_from_docx',
    'save_cache_to_docx',
    'export_cache_to_csv',
    'hash_citation_text',
]
