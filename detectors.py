"""
citategenie/detectors.py

Citation type detection logic.
Analyzes text patterns to determine the type of citation.
"""

import re
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from models import CitationType


@dataclass
class DetectionResult:
    """Result from the detection layer."""
    citation_type: CitationType
    confidence: float = 1.0
    cleaned_query: str = ""  # Cleaned/normalized version of input for searching
    hints: Dict[str, Any] = field(default_factory=dict)  # Type-specific hints for extractors


# URL detection patterns
URL_PATTERN = re.compile(
    r'^https?://[^\s]+$|'
    r'^www\.[^\s]+$|'
    r'\bhttps?://[^\s]+',
    re.IGNORECASE
)

# DOI patterns
DOI_PATTERN = re.compile(
    r'(?:doi[:\s]*)?10\.\d{4,}/[^\s]+',
    re.IGNORECASE
)

# Legal citation patterns
LEGAL_PATTERNS = [
    re.compile(r'\d+\s+U\.?S\.?\s+\d+'),  # US Reports: 388 U.S. 1
    re.compile(r'\d+\s+S\.?\s*Ct\.?\s+\d+'),  # Supreme Court Reporter
    re.compile(r'\d+\s+F\.?\s*(?:2d|3d|4th)?\s+\d+'),  # Federal Reporter
    re.compile(r'\d+\s+F\.?\s*Supp\.?\s*(?:2d|3d)?\s+\d+'),  # Federal Supplement
    re.compile(r'\d+\s+[A-Z][a-z]*\.?\s*(?:2d|3d)?\s+\d+'),  # State reporters
    re.compile(r'\bv\.\s+', re.IGNORECASE),  # Case name indicator
    re.compile(r'\[\d{4}\]\s+[A-Z]+(?:\s+[A-Za-z]+)*\s+\d+'),  # UK neutral citation [2024] UKSC 1, [2023] EWCA Civ 123, [2022] EWHC 456 (Ch)
]

# Book patterns
BOOK_PATTERNS = [
    re.compile(r'ISBN[:\s]*[\d\-X]+', re.IGNORECASE),
    re.compile(r'\([\w\s]+(?:Press|Publishers?|Books?),?\s*\d{4}\)', re.IGNORECASE),
]

# Interview patterns
INTERVIEW_PATTERNS = [
    re.compile(r'interview\s+(?:by|with)', re.IGNORECASE),
    re.compile(r'oral\s+history', re.IGNORECASE),
    re.compile(r'personal\s+communication', re.IGNORECASE),
]

# Newspaper patterns  
NEWSPAPER_DOMAINS = [
    'nytimes.com', 'washingtonpost.com', 'wsj.com', 'theguardian.com',
    'bbc.com', 'reuters.com', 'apnews.com', 'cnn.com', 'latimes.com'
]


def is_url(text: str) -> bool:
    """Check if text is or contains a URL."""
    if not text:
        return False
    return bool(URL_PATTERN.search(text.strip()))


def detect_type(query: str) -> DetectionResult:
    """
    Detect the type of citation from the query text.
    
    Args:
        query: The citation text to analyze
        
    Returns:
        DetectionResult with type, confidence, and hints
    """
    if not query:
        return DetectionResult(CitationType.UNKNOWN, 0.0, "")
    
    query = query.strip()
    cleaned = query
    hints = {}
    
    # Check for DOI
    doi_match = DOI_PATTERN.search(query)
    if doi_match:
        hints['doi'] = doi_match.group()
        return DetectionResult(CitationType.JOURNAL, 0.95, cleaned, hints)
    
    # Check for URL
    if is_url(query):
        # Check for newspaper domains
        lower_query = query.lower()
        for domain in NEWSPAPER_DOMAINS:
            if domain in lower_query:
                return DetectionResult(CitationType.NEWSPAPER, 0.9, cleaned, {'url': query})
        return DetectionResult(CitationType.URL, 0.9, cleaned, {'url': query})
    
    # Check for legal citations
    for pattern in LEGAL_PATTERNS:
        if pattern.search(query):
            return DetectionResult(CitationType.LEGAL, 0.85, cleaned, hints)
    
    # Check for interview
    for pattern in INTERVIEW_PATTERNS:
        if pattern.search(query):
            return DetectionResult(CitationType.INTERVIEW, 0.9, cleaned, hints)
    
    # Check for book indicators
    for pattern in BOOK_PATTERNS:
        if pattern.search(query):
            return DetectionResult(CitationType.BOOK, 0.8, cleaned, hints)
    
    # Default to unknown - let AI classify
    return DetectionResult(CitationType.UNKNOWN, 0.5, cleaned, hints)
