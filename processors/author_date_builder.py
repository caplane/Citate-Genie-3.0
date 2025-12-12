"""
citeflex/processors/author_date_builder.py

Builds author-date style output:
- In-text parenthetical citations: (Coleman, 1988)
- References section: alphabetized bibliography

Supports:
- APA 7
- MLA 9
- Chicago Author-Date

For each citation found in the document body, generates TWO outputs:
1. Parenthetical replacement for the body text
2. Reference entry for the bibliography

Version History:
    2025-12-12 V1.0: Initial implementation
"""

import re
import zipfile
from io import BytesIO
from typing import List, Dict, Optional, Tuple
import xml.etree.ElementTree as ET

from models import CitationMetadata, CitationType
from formatters.base import get_formatter


# Styles that use author-date format
AUTHOR_DATE_STYLES = [
    'APA 7',
    'APA',
    'MLA 9',
    'MLA',
    'Chicago Author-Date',
    'Harvard',
    'Vancouver',
    'ASA',  # American Sociological Association
]


def is_author_date_style(style: str) -> bool:
    """
    Check if style uses author-date (parenthetical) format.
    
    Args:
        style: Citation style name
        
    Returns:
        True if style uses author-date format
    """
    style_lower = style.lower()
    
    # APA and MLA are always author-date
    if 'apa' in style_lower or 'mla' in style_lower:
        return True
    
    # Chicago Author-Date specifically
    if 'chicago' in style_lower and 'author' in style_lower:
        return True
    
    # Harvard is author-date
    if 'harvard' in style_lower:
        return True
    
    # Vancouver is numbered but we'll treat as author-date for body processing
    if 'vancouver' in style_lower:
        return True
    
    # ASA (American Sociological Association) is author-date
    if style_lower == 'asa':
        return True
    
    # Default: not author-date
    return False


def format_parenthetical(
    metadata: CitationMetadata,
    style: str,
    page: str = None,
    is_narrative: bool = False
) -> str:
    """
    Format metadata as an in-text parenthetical citation.
    
    Args:
        metadata: Citation metadata
        style: Citation style (APA, MLA, Chicago Author-Date)
        page: Page number if specified
        is_narrative: If True, format for narrative use: Coleman (1988)
                      If False, format as parenthetical: (Coleman, 1988)
        
    Returns:
        Formatted parenthetical string
    """
    # Get author(s) for citation
    if metadata.authors:
        if len(metadata.authors) == 1:
            author_text = _get_last_name(metadata.authors[0])
        elif len(metadata.authors) == 2:
            style_lower = style.lower()
            if 'apa' in style_lower:
                author_text = f"{_get_last_name(metadata.authors[0])} & {_get_last_name(metadata.authors[1])}"
            else:  # MLA, Chicago
                author_text = f"{_get_last_name(metadata.authors[0])} and {_get_last_name(metadata.authors[1])}"
        else:
            author_text = f"{_get_last_name(metadata.authors[0])} et al."
    elif metadata.case_name:
        # Legal citation - use case name
        author_text = _get_short_case_name(metadata.case_name)
    else:
        # Fallback to title
        author_text = _get_short_title(metadata.title)
    
    year = metadata.year or 'n.d.'
    
    # Build citation based on style
    style_lower = style.lower()
    
    if 'mla' in style_lower:
        # MLA uses author and page, not year in parenthetical
        if page:
            citation_inner = f"{author_text} {page}"
        else:
            citation_inner = author_text
    else:
        # APA and Chicago Author-Date use (Author, Year)
        if page:
            if 'apa' in style_lower:
                citation_inner = f"{author_text}, {year}, p. {page}"
            else:
                citation_inner = f"{author_text}, {year}, {page}"
        else:
            citation_inner = f"{author_text}, {year}"
    
    if is_narrative:
        # Narrative: Coleman (1988) or Coleman (p. 45) for MLA
        if 'mla' in style_lower:
            if page:
                return f"{author_text} ({page})"
            else:
                return author_text  # MLA narrative without page is just author
        else:
            return f"{author_text} ({year})"
    else:
        # Standard parenthetical
        return f"({citation_inner})"


def format_reference_entry(
    metadata: CitationMetadata,
    style: str
) -> str:
    """
    Format metadata as a reference/bibliography entry.
    
    Args:
        metadata: Citation metadata
        style: Citation style
        
    Returns:
        Formatted reference entry string
    """
    formatter = get_formatter(style)
    return formatter.format(metadata)


def _get_last_name(author: str) -> str:
    """
    Extract last name from author string.
    
    Handles:
    - "John Smith" -> "Smith"
    - "Smith, John" -> "Smith"
    - "J. Smith" -> "Smith"
    - "Smith" -> "Smith"
    
    Args:
        author: Author name string
        
    Returns:
        Last name
    """
    if not author:
        return ""
    
    author = author.strip()
    
    # If comma present, last name is before comma
    if ',' in author:
        return author.split(',')[0].strip()
    
    # Otherwise, last name is the last word
    parts = author.split()
    if parts:
        return parts[-1]
    
    return author


def _get_short_case_name(case_name: str) -> str:
    """
    Get shortened case name for parenthetical.
    
    "Brown v. Board of Education" -> "Brown"
    
    Args:
        case_name: Full case name
        
    Returns:
        Short name (first party)
    """
    if not case_name:
        return ""
    
    # Split on v. or vs.
    parts = re.split(r'\s+v\.?\s+', case_name, flags=re.IGNORECASE)
    if parts:
        return parts[0].strip()
    
    return case_name


def _get_short_title(title: str, max_words: int = 3) -> str:
    """
    Get shortened title for parenthetical.
    
    Args:
        title: Full title
        max_words: Maximum words to include
        
    Returns:
        Shortened title in italics marker
    """
    if not title:
        return "Untitled"
    
    words = title.split()[:max_words]
    short = ' '.join(words)
    
    if len(title.split()) > max_words:
        short += '...'
    
    return f"<i>{short}</i>"


def generate_sort_key(metadata: CitationMetadata) -> str:
    """
    Generate sort key for alphabetizing references.
    
    Sort order:
    1. By first author's last name
    2. Then by year
    3. Then by title
    
    Args:
        metadata: Citation metadata
        
    Returns:
        Sort key string
    """
    author_key = ""
    if metadata.authors:
        author_key = _get_last_name(metadata.authors[0]).lower()
    elif metadata.case_name:
        author_key = _get_short_case_name(metadata.case_name).lower()
    elif metadata.title:
        # Skip articles for sorting
        title = metadata.title.lower()
        for article in ['the ', 'a ', 'an ']:
            if title.startswith(article):
                title = title[len(article):]
                break
        author_key = title
    
    year_key = metadata.year or '9999'
    title_key = (metadata.title or '').lower()[:50]
    
    return f"{author_key}|{year_key}|{title_key}"


def build_references_section(
    metadata_list: List[CitationMetadata],
    style: str
) -> str:
    """
    Build formatted References section from all cited works.
    
    Args:
        metadata_list: List of all cited works' metadata
        style: Citation style
        
    Returns:
        Formatted References section as string
    """
    if not metadata_list:
        return ""
    
    # Deduplicate by source key
    seen = set()
    unique = []
    for meta in metadata_list:
        key = _get_source_key(meta)
        if key not in seen:
            seen.add(key)
            unique.append(meta)
    
    # Sort alphabetically
    unique.sort(key=generate_sort_key)
    
    # Format each entry
    entries = []
    for meta in unique:
        entry = format_reference_entry(meta, style)
        entries.append(entry)
    
    # Build section
    style_lower = style.lower()
    if 'apa' in style_lower:
        header = "References"
    elif 'mla' in style_lower:
        header = "Works Cited"
    else:
        header = "References"
    
    # Join entries with double newlines
    return f"{header}\n\n" + "\n\n".join(entries)


def _get_source_key(metadata: CitationMetadata) -> str:
    """Generate unique key for deduplication."""
    if metadata.doi:
        return f"doi:{metadata.doi.lower()}"
    if metadata.isbn:
        return f"isbn:{metadata.isbn}"
    if metadata.url:
        return f"url:{metadata.url.lower()}"
    
    # Fallback to title + first author
    key = (metadata.title or '').lower()[:50]
    if metadata.authors:
        key += f":{metadata.authors[0].lower()}"
    return key


def build_author_date_output(
    extractions: List[Dict],
    metadata_map: Dict[str, CitationMetadata],
    style: str
) -> Tuple[List[Dict], str]:
    """
    Build complete author-date output: replacements and References section.
    
    Args:
        extractions: List of extracted citations from document body
        metadata_map: Dict mapping original text -> CitationMetadata
        style: Citation style
        
    Returns:
        Tuple of:
        - List of replacement dicts with 'original', 'replacement', 'position'
        - Formatted References section string
    """
    replacements = []
    all_metadata = []
    
    for extraction in extractions:
        original = extraction.get('original', '')
        
        # Handle multiple citations first (they look up sub-citations, not original)
        if extraction.get('type') == 'multiple' and extraction.get('sub_citations'):
            # Build combined parenthetical like (Coleman, 1988; Weber, 1905)
            parts = []
            found_any = False
            for sub in extraction['sub_citations']:
                sub_key = sub.get('citation_text', sub.get('original', ''))
                sub_meta = metadata_map.get(sub_key)
                if sub_meta:
                    all_metadata.append(sub_meta)
                    # Get inner part without parentheses
                    inner = format_parenthetical(sub_meta, style).strip('()')
                    parts.append(inner)
                    found_any = True
            
            if parts:
                replacement = '(' + '; '.join(parts) + ')'
                replacements.append({
                    'original': original,
                    'replacement': replacement,
                    'position_start': extraction.get('global_start', extraction.get('start', 0)),
                    'position_end': extraction.get('global_end', extraction.get('end', 0)),
                    'success': found_any,
                })
            else:
                replacements.append({
                    'original': original,
                    'replacement': original,
                    'position_start': extraction.get('global_start', extraction.get('start', 0)),
                    'position_end': extraction.get('global_end', extraction.get('end', 0)),
                    'success': False,
                })
            continue
        
        # Look up metadata for single citations
        metadata = metadata_map.get(original)
        
        if not metadata:
            # No metadata found - keep original
            replacements.append({
                'original': original,
                'replacement': original,
                'position_start': extraction.get('global_start', extraction.get('start', 0)),
                'position_end': extraction.get('global_end', extraction.get('end', 0)),
                'success': False,
            })
            continue
        
        # Track for References
        all_metadata.append(metadata)
        
        # Determine if narrative or standard
        is_narrative = extraction.get('type') == 'narrative'
        page = extraction.get('page')
        
        # Single citation
        replacement = format_parenthetical(metadata, style, page, is_narrative)
        
        replacements.append({
            'original': original,
            'replacement': replacement,
            'position_start': extraction.get('global_start', extraction.get('start', 0)),
            'position_end': extraction.get('global_end', extraction.get('end', 0)),
            'metadata': metadata,
            'success': True,
        })
    
    # Build References section
    references = build_references_section(all_metadata, style)
    
    return replacements, references


def apply_body_replacements(
    body_text: str,
    replacements: List[Dict]
) -> str:
    """
    Apply citation replacements to body text.
    
    Processes replacements in reverse order to preserve positions.
    
    Args:
        body_text: Original document body text
        replacements: List of replacement dicts with positions
        
    Returns:
        Updated body text
    """
    # Sort by position descending (process from end to preserve earlier positions)
    sorted_replacements = sorted(
        replacements,
        key=lambda x: x.get('position_start', 0),
        reverse=True
    )
    
    result = body_text
    
    for repl in sorted_replacements:
        start = repl.get('position_start', 0)
        end = repl.get('position_end', 0)
        replacement_text = repl.get('replacement', repl.get('original', ''))
        
        if start >= 0 and end > start:
            result = result[:start] + replacement_text + result[end:]
    
    return result


def update_document_body(
    file_bytes: bytes,
    replacements: List[Dict],
    references_section: str
) -> bytes:
    """
    Update Word document body with parenthetical replacements and References.
    
    Args:
        file_bytes: Original document bytes
        replacements: List of replacement dicts
        references_section: Formatted References section to append
        
    Returns:
        Updated document bytes
    """
    from processors.word_document import (
        extract_body_text_with_positions,
        apply_text_replacements,
        append_references_section
    )
    
    # Apply replacements to body
    updated_bytes = apply_text_replacements(file_bytes, replacements)
    
    # Append References section
    if references_section:
        updated_bytes = append_references_section(updated_bytes, references_section)
    
    return updated_bytes


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    # Test parenthetical formatting
    from models import CitationMetadata, CitationType
    
    test_meta = CitationMetadata(
        citation_type=CitationType.JOURNAL,
        title="Social Capital in the Creation of Human Capital",
        authors=["James S. Coleman"],
        year="1988",
        journal="American Journal of Sociology",
        volume="94",
        pages="S95-S120",
        doi="10.1086/228943"
    )
    
    print("Parenthetical formats:")
    for style in ['APA 7', 'MLA 9', 'Chicago Author-Date']:
        paren = format_parenthetical(test_meta, style)
        narrative = format_parenthetical(test_meta, style, is_narrative=True)
        with_page = format_parenthetical(test_meta, style, page="45")
        print(f"  {style}:")
        print(f"    Standard: {paren}")
        print(f"    Narrative: {narrative}")
        print(f"    With page: {with_page}")
    
    # Test multiple authors
    test_meta_2 = CitationMetadata(
        citation_type=CitationType.JOURNAL,
        authors=["James Coleman", "Robert Weber", "Karl Marx"],
        year="2020",
    )
    
    print("\nMultiple authors (et al.):")
    print(f"  APA: {format_parenthetical(test_meta_2, 'APA 7')}")
