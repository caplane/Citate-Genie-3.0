"""
citategenie/extractors.py

Citation metadata extraction logic.
Extracts structured metadata from detected citation types.
"""

import re
from typing import Optional
from models import CitationMetadata, CitationType


def extract_by_type(query: str, citation_type: CitationType) -> Optional[CitationMetadata]:
    """
    Extract metadata from query based on the detected citation type.
    
    Args:
        query: The citation text
        citation_type: The detected type
        
    Returns:
        CitationMetadata if extraction successful, None otherwise
    """
    if not query:
        return None
    
    query = query.strip()
    
    if citation_type == CitationType.URL:
        return _extract_url(query)
    elif citation_type == CitationType.NEWSPAPER:
        return _extract_newspaper(query)
    elif citation_type == CitationType.GOVERNMENT:
        return _extract_government(query)
    elif citation_type == CitationType.INTERVIEW:
        return _extract_interview(query)
    elif citation_type == CitationType.LETTER:
        return _extract_letter(query)
    else:
        # Return basic metadata with original text
        return CitationMetadata(
            citation_type=citation_type,
            raw_data={'original': query}
        )


def _extract_url(query: str) -> Optional[CitationMetadata]:
    """Extract metadata from a URL."""
    # Basic URL extraction - can be enhanced
    return CitationMetadata(
        citation_type=CitationType.URL,
        url=query,
        raw_data={'original': query}
    )


def _extract_newspaper(query: str) -> Optional[CitationMetadata]:
    """Extract metadata from a newspaper citation or URL."""
    return CitationMetadata(
        citation_type=CitationType.NEWSPAPER,
        url=query if query.startswith('http') else None,
        raw_data={'original': query}
    )


def _extract_government(query: str) -> Optional[CitationMetadata]:
    """Extract metadata from a government document reference."""
    return CitationMetadata(
        citation_type=CitationType.GOVERNMENT,
        raw_data={'original': query}
    )


def _extract_interview(query: str) -> Optional[CitationMetadata]:
    """Extract metadata from an interview citation."""
    # Try to parse interview format: "Name, interview by author, Date"
    patterns = [
        # Name, interview by author, Date
        re.compile(r'^([^,]+),\s*interview\s+(?:by|with)\s+([^,]+),\s*(.+)$', re.IGNORECASE),
        # Name, oral history, Date
        re.compile(r'^([^,]+),\s*oral\s+history[^,]*,\s*(.+)$', re.IGNORECASE),
    ]
    
    for pattern in patterns:
        match = pattern.match(query)
        if match:
            groups = match.groups()
            return CitationMetadata(
                citation_type=CitationType.INTERVIEW,
                authors=[groups[0].strip()],
                raw_data={'original': query, 'parsed': True}
            )
    
    return CitationMetadata(
        citation_type=CitationType.INTERVIEW,
        raw_data={'original': query}
    )


def _extract_letter(query: str) -> Optional[CitationMetadata]:
    """Extract metadata from a letter/correspondence citation."""
    # Try to parse letter format: "Author to Recipient, Date"
    pattern = re.compile(r'^([^,]+)\s+to\s+([^,]+),\s*(.+)$', re.IGNORECASE)
    match = pattern.match(query)
    
    if match:
        return CitationMetadata(
            citation_type=CitationType.LETTER,
            authors=[match.group(1).strip()],
            raw_data={
                'original': query,
                'recipient': match.group(2).strip(),
                'date': match.group(3).strip()
            }
        )
    
    return CitationMetadata(
        citation_type=CitationType.LETTER,
        raw_data={'original': query}
    )
