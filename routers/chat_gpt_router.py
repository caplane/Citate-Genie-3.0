"""
citeflex/engines/ai_lookup.py

AI-powered citation lookup for author-date references.

Uses OpenAI (GPT-4o) first (cheaper), falls back to Claude if needed.
Designed for APA-style parenthetical citations like:
    (Simonton, 1992)
    (Zimbardo, Johnson, & McCann, 2009)

The AI identifies the academic work and returns structured metadata
that can be passed to formatters.

Version History:
    2025-12-10 V1.1: Added multi-option support - lookup_parenthetical_citation_options()
                     returns up to 5 possible matches for user selection
    2025-12-10 V1.0: Initial implementation - OpenAI first, Claude fallback
"""

import re
import json
import requests
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass

from models import CitationMetadata, CitationType

# Get API keys from config (centralized with .lstrip('=') fix)
from config import OPENAI_API_KEY, ANTHROPIC_API_KEY


# =============================================================================
# PARENTHETICAL CITATION PARSER
# =============================================================================

# Pattern for APA-style parenthetical citations
# Matches: (Smith, 2020), (Smith & Jones, 2020), (Smith, Jones, & Lee, 2020)
# Also handles "et al." cases: (Smith et al., 2020)
PARENTHETICAL_PATTERN = re.compile(
    r'\(([A-Z][a-z]+(?:\s+(?:&|and)\s+[A-Z][a-z]+)*(?:,?\s+[A-Z][a-z]+)*(?:\s+et\s+al\.)?),\s*(\d{4}[a-z]?)\)',
    re.IGNORECASE
)

# Simpler pattern that's more permissive
SIMPLE_AUTHOR_YEAR_PATTERN = re.compile(
    r'\(([^()]+?),\s*(\d{4}[a-z]?)\)'
)


def parse_parenthetical_citation(text: str) -> Optional[Tuple[List[str], str]]:
    """
    Parse an APA-style parenthetical citation into authors and year.
    
    Args:
        text: Citation text like "(Simonton, 1992)" or "(Zimbardo, Johnson, & McCann, 2009)"
        
    Returns:
        Tuple of (authors_list, year) or None if not parseable
        
    Examples:
        "(Simonton, 1992)" -> (["Simonton"], "1992")
        "(Smith & Jones, 2020)" -> (["Smith", "Jones"], "2020")
        "(Zimbardo, Johnson, & McCann, 2009)" -> (["Zimbardo", "Johnson", "McCann"], "2009")
        "(Smith et al., 2020)" -> (["Smith et al."], "2020")
    """
    text = text.strip()
    
    # Try simple pattern first
    match = SIMPLE_AUTHOR_YEAR_PATTERN.match(text)
    if not match:
        # Maybe it's just "Simonton, 1992" without parens
        if re.match(r'^[A-Z][a-z]+.*,\s*\d{4}', text):
            text = f"({text})"
            match = SIMPLE_AUTHOR_YEAR_PATTERN.match(text)
    
    if not match:
        return None
    
    authors_part = match.group(1).strip()
    year = match.group(2).strip()
    
    # Parse authors
    # Handle "et al." case
    if 'et al' in authors_part.lower():
        # Keep as single author with et al.
        authors = [authors_part]
    else:
        # Split on "&", "and", or ","
        # First normalize separators
        authors_part = re.sub(r'\s*&\s*', ', ', authors_part)
        authors_part = re.sub(r'\s+and\s+', ', ', authors_part, flags=re.IGNORECASE)
        
        # Split and clean
        authors = [a.strip() for a in authors_part.split(',') if a.strip()]
    
    return (authors, year)


def is_parenthetical_citation(text: str) -> bool:
    """
    Check if text looks like a parenthetical author-date citation.
    
    Args:
        text: Text to check
        
    Returns:
        True if it matches the pattern
    """
    result = parse_parenthetical_citation(text)
    return result is not None


# =============================================================================
# AI LOOKUP ENGINE
# =============================================================================

SYSTEM_PROMPT = """You are an expert academic reference librarian. Given author name(s) and a publication year, identify the most likely academic work being referenced.

You must respond with a JSON object containing the citation metadata. Include ONLY fields you are confident about.

Required JSON structure:
{
    "found": true/false,
    "confidence": "high"/"medium"/"low",
    "citation_type": "journal"/"book"/"chapter"/"conference"/"report"/"other",
    "title": "Full title of the work",
    "authors": ["Last, First M.", "Last2, First2"],
    "year": "YYYY",
    "journal": "Journal name (if journal article)",
    "volume": "volume number",
    "issue": "issue number", 
    "pages": "start-end",
    "doi": "10.xxxx/xxxxx (if known)",
    "publisher": "Publisher name (if book)",
    "place": "Publication place (if book)",
    "edition": "edition (if applicable)",
    "url": "URL if applicable"
}

Important guidelines:
1. If you're not sure about a field, omit it rather than guess
2. For "authors", use "Last, First M." format
3. Set "found": false if you cannot identify the work
4. Consider the academic context provided
5. Be especially careful with common names - verify the specific work"""


SYSTEM_PROMPT_MULTI = """You are an expert academic reference librarian. Given author name(s) and a publication year, identify ALL likely academic works that could be referenced.

Authors often publish multiple works in the same year. Return up to 5 possible matches, ordered by likelihood (most likely first).

You must respond with a JSON object containing an array of possible works:
{
    "works": [
        {
            "confidence": "high"/"medium"/"low",
            "citation_type": "journal"/"book"/"chapter"/"conference"/"report"/"other",
            "title": "Full title of the work",
            "authors": ["Last, First M.", "Last2, First2"],
            "year": "YYYY",
            "journal": "Journal name (if journal article)",
            "volume": "volume number",
            "issue": "issue number", 
            "pages": "start-end",
            "doi": "10.xxxx/xxxxx (if known)",
            "publisher": "Publisher name (if book)",
            "place": "Publication place (if book)",
            "edition": "edition (if applicable)",
            "url": "URL if applicable"
        }
    ]
}

Important guidelines:
1. Return up to 5 works, but only include works you're reasonably confident about
2. Order by likelihood - most likely match first
3. If you're not sure about a field, omit it rather than guess
4. For "authors", use "Last, First M." format
5. Consider the academic context provided
6. Include different types of works (articles, books, chapters) if the author published multiple types that year"""


def query_openai(authors: List[str], year: str, context: str = "") -> Optional[Dict[str, Any]]:
    """
    Query OpenAI to identify an academic work.
    
    Args:
        authors: List of author last names
        year: Publication year
        context: Optional context about the document/field
        
    Returns:
        Dict with citation metadata or None if failed
    """
    if not OPENAI_API_KEY:
        print("[AI_Lookup] No OpenAI API key configured")
        return None
    
    authors_str = ", ".join(authors)
    
    user_prompt = f"""Identify this academic reference:

Authors: {authors_str}
Year: {year}
"""
    if context:
        user_prompt += f"\nContext: This citation appears in {context}"
    
    user_prompt += "\n\nRespond with JSON only, no other text."
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.1,  # Low temperature for factual accuracy
                "max_tokens": 500
            },
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"[AI_Lookup] OpenAI error: {response.status_code} - {response.text}")
            return None
        
        result = response.json()
        content = result['choices'][0]['message']['content']
        
        # Parse JSON from response
        # Handle potential markdown code blocks
        content = content.strip()
        if content.startswith('```'):
            content = re.sub(r'^```(?:json)?\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
        
        return json.loads(content)
        
    except json.JSONDecodeError as e:
        print(f"[AI_Lookup] Failed to parse OpenAI response as JSON: {e}")
        return None
    except requests.RequestException as e:
        print(f"[AI_Lookup] OpenAI request failed: {e}")
        return None
    except Exception as e:
        print(f"[AI_Lookup] Unexpected error with OpenAI: {e}")
        return None


def query_claude(authors: List[str], year: str, context: str = "") -> Optional[Dict[str, Any]]:
    """
    Query Claude as fallback to identify an academic work.
    
    Args:
        authors: List of author last names
        year: Publication year
        context: Optional context about the document/field
        
    Returns:
        Dict with citation metadata or None if failed
    """
    if not ANTHROPIC_API_KEY:
        print("[AI_Lookup] No Anthropic API key configured")
        return None
    
    authors_str = ", ".join(authors)
    
    user_prompt = f"""Identify this academic reference:

Authors: {authors_str}
Year: {year}
"""
    if context:
        user_prompt += f"\nContext: This citation appears in {context}"
    
    user_prompt += "\n\nRespond with JSON only, no other text."
    
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "claude-3-5-sonnet-20241022",
                "max_tokens": 500,
                "system": SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": user_prompt}
                ]
            },
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"[AI_Lookup] Claude error: {response.status_code} - {response.text}")
            return None
        
        result = response.json()
        content = result['content'][0]['text']
        
        # Parse JSON from response
        content = content.strip()
        if content.startswith('```'):
            content = re.sub(r'^```(?:json)?\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
        
        return json.loads(content)
        
    except json.JSONDecodeError as e:
        print(f"[AI_Lookup] Failed to parse Claude response as JSON: {e}")
        return None
    except requests.RequestException as e:
        print(f"[AI_Lookup] Claude request failed: {e}")
        return None
    except Exception as e:
        print(f"[AI_Lookup] Unexpected error with Claude: {e}")
        return None


def query_openai_multi(authors: List[str], year: str, context: str = "", limit: int = 5) -> List[Dict[str, Any]]:
    """
    Query OpenAI to get multiple possible academic works.
    
    Args:
        authors: List of author last names
        year: Publication year
        context: Optional context about the document/field
        limit: Maximum number of results to return
        
    Returns:
        List of dicts with citation metadata
    """
    if not OPENAI_API_KEY:
        print("[AI_Lookup] No OpenAI API key configured")
        return []
    
    authors_str = ", ".join(authors)
    
    user_prompt = f"""Identify ALL possible academic works matching this reference:

Authors: {authors_str}
Year: {year}
"""
    if context:
        user_prompt += f"\nContext: This citation appears in {context}"
    
    user_prompt += f"\n\nReturn up to {limit} possible matches. Respond with JSON only, no other text."
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT_MULTI},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.3,  # Slightly higher for variety
                "max_tokens": 2000
            },
            timeout=45
        )
        
        if response.status_code != 200:
            print(f"[AI_Lookup] OpenAI error: {response.status_code} - {response.text}")
            return []
        
        result = response.json()
        content = result['choices'][0]['message']['content']
        
        # Parse JSON from response
        content = content.strip()
        if content.startswith('```'):
            content = re.sub(r'^```(?:json)?\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
        
        data = json.loads(content)
        return data.get('works', [])[:limit]
        
    except json.JSONDecodeError as e:
        print(f"[AI_Lookup] Failed to parse OpenAI multi response as JSON: {e}")
        return []
    except requests.RequestException as e:
        print(f"[AI_Lookup] OpenAI multi request failed: {e}")
        return []
    except Exception as e:
        print(f"[AI_Lookup] Unexpected error with OpenAI multi: {e}")
        return []


def query_claude_multi(authors: List[str], year: str, context: str = "", limit: int = 5) -> List[Dict[str, Any]]:
    """
    Query Claude to get multiple possible academic works.
    
    Args:
        authors: List of author last names
        year: Publication year
        context: Optional context about the document/field
        limit: Maximum number of results to return
        
    Returns:
        List of dicts with citation metadata
    """
    if not ANTHROPIC_API_KEY:
        print("[AI_Lookup] No Anthropic API key configured")
        return []
    
    authors_str = ", ".join(authors)
    
    user_prompt = f"""Identify ALL possible academic works matching this reference:

Authors: {authors_str}
Year: {year}
"""
    if context:
        user_prompt += f"\nContext: This citation appears in {context}"
    
    user_prompt += f"\n\nReturn up to {limit} possible matches. Respond with JSON only, no other text."
    
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "claude-3-5-sonnet-20241022",
                "max_tokens": 2000,
                "system": SYSTEM_PROMPT_MULTI,
                "messages": [
                    {"role": "user", "content": user_prompt}
                ]
            },
            timeout=45
        )
        
        if response.status_code != 200:
            print(f"[AI_Lookup] Claude error: {response.status_code} - {response.text}")
            return []
        
        result = response.json()
        content = result['content'][0]['text']
        
        # Parse JSON from response
        content = content.strip()
        if content.startswith('```'):
            content = re.sub(r'^```(?:json)?\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
        
        data = json.loads(content)
        return data.get('works', [])[:limit]
        
    except json.JSONDecodeError as e:
        print(f"[AI_Lookup] Failed to parse Claude multi response as JSON: {e}")
        return []
    except requests.RequestException as e:
        print(f"[AI_Lookup] Claude multi request failed: {e}")
        return []
    except Exception as e:
        print(f"[AI_Lookup] Unexpected error with Claude multi: {e}")
        return []


def ai_lookup(authors: List[str], year: str, context: str = "") -> Optional[CitationMetadata]:
    """
    Look up an academic work using AI (OpenAI first, Claude fallback).
    
    Args:
        authors: List of author last names
        year: Publication year  
        context: Optional context about the document/field
        
    Returns:
        CitationMetadata if found, None otherwise
    """
    # Try OpenAI first (cheaper)
    print(f"[AI_Lookup] Looking up: {', '.join(authors)} ({year})")
    
    result = query_openai(authors, year, context)
    
    # Fallback to Claude if OpenAI fails or returns not found
    if not result or not result.get('found', False):
        print("[AI_Lookup] OpenAI didn't find it, trying Claude...")
        result = query_claude(authors, year, context)
    
    if not result or not result.get('found', False):
        print(f"[AI_Lookup] Could not identify: {', '.join(authors)} ({year})")
        return None
    
    # Convert to CitationMetadata
    return _dict_to_metadata(result, authors, year)


def _dict_to_metadata(data: Dict[str, Any], original_authors: List[str], original_year: str) -> CitationMetadata:
    """
    Convert AI response dict to CitationMetadata.
    
    Args:
        data: Dict from AI response
        original_authors: Original author names from citation
        original_year: Original year from citation
        
    Returns:
        CitationMetadata object
    """
    # Determine citation type
    type_map = {
        'journal': CitationType.JOURNAL,
        'book': CitationType.BOOK,
        'chapter': CitationType.BOOK,
        'conference': CitationType.JOURNAL,
        'report': CitationType.GOVERNMENT,
        'other': CitationType.UNKNOWN
    }
    
    citation_type = type_map.get(
        data.get('citation_type', 'other').lower(), 
        CitationType.UNKNOWN
    )
    
    # Parse authors - AI should return in "Last, First" format
    authors = data.get('authors', [])
    if not authors:
        # Fallback to original author names
        authors = original_authors
    
    return CitationMetadata(
        citation_type=citation_type,
        raw_source=f"({', '.join(original_authors)}, {original_year})",
        source_engine="ai_lookup",
        title=data.get('title', ''),
        authors=authors,
        year=data.get('year', original_year),
        journal=data.get('journal', ''),
        volume=data.get('volume', ''),
        issue=data.get('issue', ''),
        pages=data.get('pages', ''),
        doi=data.get('doi', ''),
        publisher=data.get('publisher', ''),
        place=data.get('place', ''),
        edition=data.get('edition', ''),
        url=data.get('url', ''),
        confidence=1.0 if data.get('confidence') == 'high' else 0.7 if data.get('confidence') == 'medium' else 0.5
    )


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def lookup_parenthetical_citation(citation_text: str, context: str = "") -> Optional[CitationMetadata]:
    """
    Main entry point: Parse and look up a parenthetical citation.
    
    Args:
        citation_text: Text like "(Simonton, 1992)" or "Simonton, 1992"
        context: Optional context about the source document
        
    Returns:
        CitationMetadata if found, None otherwise
        
    Example:
        >>> metadata = lookup_parenthetical_citation("(Zimbardo, Johnson, & McCann, 2009)")
        >>> print(metadata.title)
        "Psychology: Core concepts"
    """
    parsed = parse_parenthetical_citation(citation_text)
    
    if not parsed:
        print(f"[AI_Lookup] Could not parse citation: {citation_text}")
        return None
    
    authors, year = parsed
    return ai_lookup(authors, year, context)


def lookup_parenthetical_citation_options(
    citation_text: str, 
    context: str = "", 
    limit: int = 5
) -> List[CitationMetadata]:
    """
    Get multiple possible matches for a parenthetical citation.
    
    Use this when you want to present options to the user for selection,
    since authors often publish multiple works in the same year.
    
    Args:
        citation_text: Text like "(Simonton, 1992)" or "Simonton, 1992"
        context: Optional context about the source document
        limit: Maximum number of options to return (default 5)
        
    Returns:
        List of CitationMetadata options, ordered by likelihood (best first)
        
    Example:
        >>> options = lookup_parenthetical_citation_options("(Simonton, 1992)")
        >>> for opt in options:
        ...     print(f"{opt.title} - {opt.journal or opt.publisher}")
    """
    parsed = parse_parenthetical_citation(citation_text)
    
    if not parsed:
        print(f"[AI_Lookup] Could not parse citation: {citation_text}")
        return []
    
    authors, year = parsed
    print(f"[AI_Lookup] Getting options for: {', '.join(authors)} ({year})")
    
    # Try OpenAI first (cheaper)
    works = query_openai_multi(authors, year, context, limit)
    
    # Fallback to Claude if OpenAI returns nothing
    if not works:
        print("[AI_Lookup] OpenAI returned no options, trying Claude...")
        works = query_claude_multi(authors, year, context, limit)
    
    if not works:
        print(f"[AI_Lookup] No options found for: {', '.join(authors)} ({year})")
        return []
    
    # Convert all to CitationMetadata
    results = []
    for work in works:
        try:
            meta = _dict_to_metadata(work, authors, year)
            if meta and meta.title:  # Must have at least a title
                results.append(meta)
        except Exception as e:
            print(f"[AI_Lookup] Error converting work to metadata: {e}")
            continue
    
    print(f"[AI_Lookup] Found {len(results)} options")
    return results


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    # Test parsing
    test_citations = [
        "(Simonton, 1992)",
        "(Smith & Jones, 2020)",
        "(Zimbardo, Johnson, & McCann, 2009)",
        "(Smith et al., 2020)",
        "Merton, 1968",
    ]
    
    print("=== Testing Parser ===")
    for cite in test_citations:
        result = parse_parenthetical_citation(cite)
        print(f"{cite} -> {result}")
    
    print("\n=== Testing AI Lookup ===")
    # Only run if API keys are configured
    if OPENAI_API_KEY or ANTHROPIC_API_KEY:
        test_lookup = lookup_parenthetical_citation(
            "(Simonton, 1992)", 
            context="a psychology article about eminent psychologists"
        )
        if test_lookup:
            print(f"Found: {test_lookup.title}")
            print(f"Authors: {test_lookup.authors}")
            print(f"Journal: {test_lookup.journal}")
            print(f"DOI: {test_lookup.doi}")
        else:
            print("Not found")
    else:
        print("No API keys configured - skipping AI lookup test")
