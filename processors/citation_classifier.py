"""
citeflex/processors/citation_classifier.py

Classifies extracted citations and routes them to the correct lookup engine.

Classification hierarchy:
1. URL → route by domain (academic publisher, PubMed, arXiv, etc.)
2. DOI → CrossrefEngine.get_by_id()
3. PMID → PubMedEngine.get_by_id()
4. arXiv ID → ArxivEngine.get_by_id()
5. ISBN → GoogleBooksAPI or OpenLibrary
6. Author-Year → ai_lookup (with document context)
7. Keywords → get_multiple_citations() search

Version History:
    2025-12-12 V1.0: Initial implementation
"""

import re
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass
from enum import Enum, auto

from models import CitationMetadata, CitationType


class CitationInputType(Enum):
    """Type of input extracted from document."""
    URL = auto()
    DOI = auto()
    PMID = auto()
    ARXIV = auto()
    ISBN = auto()
    AUTHOR_YEAR = auto()
    KEYWORDS = auto()
    UNKNOWN = auto()


@dataclass
class ClassifiedCitation:
    """Result of classifying an extracted citation."""
    input_type: CitationInputType
    original_text: str
    identifier: str  # The key piece for lookup (URL, DOI, author+year string, etc.)
    position_start: int = 0
    position_end: int = 0
    authors: List[str] = None  # For author-year types
    year: str = None
    page: str = None  # Page number if present
    is_narrative: bool = False  # Coleman (1988) vs (Coleman, 1988)
    sub_citations: List['ClassifiedCitation'] = None  # For multiple citations
    
    def __post_init__(self):
        if self.authors is None:
            self.authors = []
        if self.sub_citations is None:
            self.sub_citations = []


def classify_url(url: str) -> Tuple[CitationInputType, str]:
    """
    Classify a URL and extract identifier if possible.
    
    Returns:
        Tuple of (input_type, identifier)
    """
    url_lower = url.lower()
    
    # DOI URL
    if 'doi.org/' in url_lower:
        # Extract DOI from URL
        match = re.search(r'doi\.org/(10\.\d+/.+)$', url, re.IGNORECASE)
        if match:
            return CitationInputType.DOI, match.group(1)
    
    # PubMed URL
    if 'pubmed' in url_lower or 'ncbi.nlm.nih.gov' in url_lower:
        match = re.search(r'/(\d{6,9})/?$', url)
        if match:
            return CitationInputType.PMID, match.group(1)
    
    # arXiv URL
    if 'arxiv.org' in url_lower:
        match = re.search(r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)', url, re.IGNORECASE)
        if match:
            return CitationInputType.ARXIV, match.group(1)
        # Old format
        match = re.search(r'arxiv\.org/(?:abs|pdf)/([a-z-]+/\d{7})', url, re.IGNORECASE)
        if match:
            return CitationInputType.ARXIV, match.group(1)
    
    # Academic publisher with DOI in URL
    doi_match = re.search(r'(10\.\d{4,}/[^\s?#]+)', url)
    if doi_match:
        return CitationInputType.DOI, doi_match.group(1).rstrip('.,;')
    
    # Generic URL - will need metadata extraction
    return CitationInputType.URL, url


def classify_extracted_item(item: Dict) -> ClassifiedCitation:
    """
    Classify an item from one of the extractors.
    
    Args:
        item: Dict from url_extractor, doi_extractor, or parenthetical_extractor
        
    Returns:
        ClassifiedCitation with routing info
    """
    # From doi_extractor
    if 'type' in item and item['type'] in ('doi', 'pmid', 'arxiv', 'isbn'):
        type_map = {
            'doi': CitationInputType.DOI,
            'pmid': CitationInputType.PMID,
            'arxiv': CitationInputType.ARXIV,
            'isbn': CitationInputType.ISBN,
        }
        return ClassifiedCitation(
            input_type=type_map[item['type']],
            original_text=item.get('original', ''),
            identifier=item['identifier'],
            position_start=item.get('start', 0),
            position_end=item.get('end', 0),
        )
    
    # From url_extractor
    if 'url' in item:
        input_type, identifier = classify_url(item['url'])
        return ClassifiedCitation(
            input_type=input_type,
            original_text=item.get('original', item['url']),
            identifier=identifier,
            position_start=item.get('start', 0),
            position_end=item.get('end', 0),
        )
    
    # From parenthetical_extractor
    if 'type' in item:
        paren_type = item['type']
        
        if paren_type == 'keywords':
            return ClassifiedCitation(
                input_type=CitationInputType.KEYWORDS,
                original_text=item.get('original', ''),
                identifier=item.get('query', ''),
                position_start=item.get('start', 0),
                position_end=item.get('end', 0),
            )
        
        if paren_type == 'multiple':
            # Has sub-citations to process individually
            sub_classified = []
            for sub in item.get('sub_citations', []):
                sub_classified.append(ClassifiedCitation(
                    input_type=CitationInputType.AUTHOR_YEAR,
                    original_text=sub.get('citation_text', ''),
                    identifier=sub.get('citation_text', ''),
                    authors=sub.get('authors', []),
                    year=sub.get('year', ''),
                ))
            
            return ClassifiedCitation(
                input_type=CitationInputType.AUTHOR_YEAR,
                original_text=item.get('original', ''),
                identifier=item.get('original', ''),
                position_start=item.get('start', 0),
                position_end=item.get('end', 0),
                sub_citations=sub_classified,
            )
        
        if paren_type in ('standard', 'narrative'):
            return ClassifiedCitation(
                input_type=CitationInputType.AUTHOR_YEAR,
                original_text=item.get('original', ''),
                identifier=item.get('citation_text', ''),
                authors=item.get('authors', []),
                year=item.get('year', ''),
                page=item.get('page'),
                is_narrative=paren_type == 'narrative',
                position_start=item.get('start', 0),
                position_end=item.get('end', 0),
            )
    
    # Unknown
    return ClassifiedCitation(
        input_type=CitationInputType.UNKNOWN,
        original_text=str(item),
        identifier=str(item),
    )


def lookup_citation(
    classified: ClassifiedCitation,
    document_context: str = "",
    style: str = "APA 7"
) -> Optional[CitationMetadata]:
    """
    Look up metadata for a classified citation using appropriate engine.
    
    Args:
        classified: ClassifiedCitation to look up
        document_context: Topic context from document (for AI disambiguation)
        style: Citation style (for formatting hints)
        
    Returns:
        CitationMetadata if found, None otherwise
    """
    input_type = classified.input_type
    identifier = classified.identifier
    
    try:
        if input_type == CitationInputType.DOI:
            from engines.academic import CrossrefEngine
            engine = CrossrefEngine()
            return engine.get_by_id(identifier)
        
        elif input_type == CitationInputType.PMID:
            from engines.academic import PubMedEngine
            engine = PubMedEngine()
            return engine.get_by_id(identifier)
        
        elif input_type == CitationInputType.ARXIV:
            from engines.arxiv import ArxivEngine
            engine = ArxivEngine()
            return engine.get_by_id(identifier)
        
        elif input_type == CitationInputType.ISBN:
            from engines.books import GoogleBooksAPI
            engine = GoogleBooksAPI()
            result = engine.search_by_isbn(identifier)
            if result:
                return _book_dict_to_metadata(result, identifier)
            return None
        
        elif input_type == CitationInputType.URL:
            # Use unified router's URL handling
            from unified_router import route_citation
            metadata, _ = route_citation(identifier, style)
            return metadata
        
        elif input_type == CitationInputType.AUTHOR_YEAR:
            # Use AI lookup with context
            from engines.ai_lookup import lookup_parenthetical_citation
            return lookup_parenthetical_citation(
                classified.identifier,
                context=document_context
            )
        
        elif input_type == CitationInputType.KEYWORDS:
            # Search across engines
            from unified_router import route_citation
            metadata, _ = route_citation(identifier, style)
            return metadata
        
        else:
            print(f"[Classifier] Unknown input type: {input_type}")
            return None
            
    except Exception as e:
        print(f"[Classifier] Lookup error for {input_type.name}: {e}")
        return None


def lookup_with_options(
    classified: ClassifiedCitation,
    document_context: str = "",
    limit: int = 5
) -> List[CitationMetadata]:
    """
    Look up multiple options for a citation (for user selection).
    
    Used for author-year and keyword searches where multiple matches possible.
    
    Args:
        classified: ClassifiedCitation to look up
        document_context: Topic context from document
        limit: Maximum options to return
        
    Returns:
        List of CitationMetadata options
    """
    input_type = classified.input_type
    
    try:
        if input_type in (CitationInputType.DOI, CitationInputType.PMID, 
                          CitationInputType.ARXIV, CitationInputType.ISBN):
            # Deterministic lookups - only one result
            result = lookup_citation(classified, document_context)
            return [result] if result else []
        
        elif input_type == CitationInputType.AUTHOR_YEAR:
            from engines.ai_lookup import lookup_parenthetical_citation_options
            return lookup_parenthetical_citation_options(
                classified.identifier,
                context=document_context,
                limit=limit
            )
        
        elif input_type == CitationInputType.KEYWORDS:
            from unified_router import get_multiple_citations
            results = get_multiple_citations(classified.identifier, "APA 7", limit)
            return [meta for meta, _, _ in results if meta]
        
        elif input_type == CitationInputType.URL:
            # URLs are typically deterministic
            result = lookup_citation(classified, document_context)
            return [result] if result else []
        
        else:
            return []
            
    except Exception as e:
        print(f"[Classifier] Options lookup error: {e}")
        return []


def _book_dict_to_metadata(data: dict, raw_source: str) -> CitationMetadata:
    """Convert book search result dict to CitationMetadata."""
    return CitationMetadata(
        citation_type=CitationType.BOOK,
        raw_source=raw_source,
        source_engine="Google Books",
        title=data.get('title', ''),
        authors=data.get('authors', []),
        year=data.get('year', ''),
        publisher=data.get('publisher', ''),
        place=data.get('place', ''),
        isbn=data.get('isbn', ''),
        raw_data=data
    )


def is_deterministic_type(input_type: CitationInputType) -> bool:
    """
    Check if input type gives deterministic results (no user choice needed).
    
    Args:
        input_type: The citation input type
        
    Returns:
        True if lookup returns single definitive result
    """
    return input_type in (
        CitationInputType.DOI,
        CitationInputType.PMID,
        CitationInputType.ARXIV,
        CitationInputType.ISBN,
        CitationInputType.URL,
    )


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    # Test classification
    test_items = [
        {'url': 'https://doi.org/10.1086/226147'},
        {'url': 'https://pubmed.ncbi.nlm.nih.gov/12345678/'},
        {'url': 'https://arxiv.org/abs/2301.12345'},
        {'url': 'https://www.jstor.org/stable/2095101'},
        {'type': 'doi', 'identifier': '10.1177/0003122410395370', 'original': '10.1177/0003122410395370'},
        {'type': 'standard', 'authors': ['Coleman'], 'year': '1988', 'original': '(Coleman, 1988)'},
        {'type': 'keywords', 'query': 'caplan trains spain', 'original': '(caplan trains spain)'},
    ]
    
    print("Classification results:")
    for item in test_items:
        result = classify_extracted_item(item)
        print(f"  {result.input_type.name}: {result.identifier}")
