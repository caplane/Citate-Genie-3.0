"""
citeflex/processors/footnote_builder.py

Builds formatted footnote/endnote output for footnote-based citation styles:
- Chicago Notes-Bibliography
- Bluebook
- OSCOLA

Takes metadata from lookups and formats as footnotes in the Word document.

Version History:
    2025-12-12 V1.0: Initial implementation
"""

import zipfile
from io import BytesIO
from typing import List, Dict, Optional, Tuple
import xml.etree.ElementTree as ET

from models import CitationMetadata, CitationType
from formatters.base import get_formatter


# Styles that use footnotes/endnotes
FOOTNOTE_STYLES = [
    'Chicago Manual of Style',
    'Chicago Notes-Bibliography', 
    'Chicago',
    'Bluebook',
    'OSCOLA',
]


def is_footnote_style(style: str) -> bool:
    """
    Check if style uses footnotes/endnotes.
    
    Args:
        style: Citation style name
        
    Returns:
        True if style uses footnotes
    """
    style_lower = style.lower()
    
    # Check for footnote-based styles
    if 'bluebook' in style_lower or 'oscola' in style_lower:
        return True
    
    # Chicago is footnote unless specified as Author-Date
    if 'chicago' in style_lower:
        if 'author' in style_lower and 'date' in style_lower:
            return False
        return True
    
    # Default: not footnote style
    return False


def format_footnote(
    metadata: CitationMetadata, 
    style: str,
    is_first_occurrence: bool = True,
    page: str = None
) -> str:
    """
    Format metadata as a footnote citation.
    
    Args:
        metadata: Citation metadata
        style: Citation style
        is_first_occurrence: If True, use full citation. If False, use short form.
        page: Page number to append (optional)
        
    Returns:
        Formatted footnote string
    """
    formatter = get_formatter(style)
    
    if is_first_occurrence:
        formatted = formatter.format(metadata)
    else:
        # Use short form for subsequent citations
        formatted = formatter.format_short(metadata) if hasattr(formatter, 'format_short') else formatter.format(metadata)
    
    # Append page number if provided
    if page:
        # Remove trailing period for page addition
        formatted = formatted.rstrip('.')
        formatted += f", {page}."
    
    return formatted


def build_footnotes_from_extractions(
    extractions: List[Dict],
    metadata_map: Dict[str, CitationMetadata],
    style: str
) -> List[Dict]:
    """
    Build formatted footnotes from extractions and looked-up metadata.
    
    Args:
        extractions: List of extracted citations from document
        metadata_map: Dict mapping original text -> CitationMetadata
        style: Citation style
        
    Returns:
        List of dicts with 'original', 'formatted', 'position' keys
    """
    results = []
    seen_sources = {}  # Track first occurrences for short form
    
    for extraction in extractions:
        original = extraction.get('original', '')
        
        # Look up metadata
        metadata = metadata_map.get(original)
        
        if not metadata:
            # No metadata found - keep original
            results.append({
                'original': original,
                'formatted': original,
                'position_start': extraction.get('global_start', extraction.get('start', 0)),
                'position_end': extraction.get('global_end', extraction.get('end', 0)),
                'success': False,
            })
            continue
        
        # Check if first occurrence
        source_key = _get_source_key(metadata)
        is_first = source_key not in seen_sources
        
        if is_first:
            seen_sources[source_key] = metadata
        
        # Get page number if present
        page = extraction.get('page')
        
        # Format footnote
        formatted = format_footnote(metadata, style, is_first, page)
        
        results.append({
            'original': original,
            'formatted': formatted,
            'position_start': extraction.get('global_start', extraction.get('start', 0)),
            'position_end': extraction.get('global_end', extraction.get('end', 0)),
            'metadata': metadata,
            'success': True,
            'is_first_occurrence': is_first,
        })
    
    return results


def _get_source_key(metadata: CitationMetadata) -> str:
    """
    Generate a unique key for a source to track first occurrences.
    
    Args:
        metadata: Citation metadata
        
    Returns:
        String key for source identification
    """
    if metadata.doi:
        return f"doi:{metadata.doi.lower()}"
    
    if metadata.isbn:
        return f"isbn:{metadata.isbn}"
    
    if metadata.url:
        return f"url:{metadata.url.lower()}"
    
    if metadata.case_name and metadata.citation:
        return f"legal:{metadata.case_name.lower()}:{metadata.citation.lower()}"
    
    # Fallback to title + first author
    key = metadata.title.lower()[:50] if metadata.title else ''
    if metadata.authors:
        key += f":{metadata.authors[0].lower()}"
    
    return key


def update_document_footnotes(
    file_bytes: bytes,
    footnote_updates: List[Dict]
) -> bytes:
    """
    Update footnotes/endnotes in a Word document.
    
    This function delegates to document_processor for actual XML manipulation.
    
    Args:
        file_bytes: Original document bytes
        footnote_updates: List of dicts with 'note_id' and 'formatted' keys
        
    Returns:
        Updated document bytes
    """
    from document_processor import WordDocumentProcessor, LinkActivator
    
    processor = WordDocumentProcessor(BytesIO(file_bytes))
    
    for update in footnote_updates:
        note_id = update.get('note_id')
        formatted = update.get('formatted', '')
        note_type = update.get('note_type', 'endnote')
        
        if note_id and formatted:
            if note_type == 'footnote':
                processor.write_footnote(str(note_id), formatted)
            else:
                processor.write_endnote(str(note_id), formatted)
    
    # Save to buffer
    output_buffer = processor.save_to_buffer()
    
    # Activate URLs as hyperlinks
    output_buffer = LinkActivator.process(output_buffer)
    
    processor.cleanup()
    
    return output_buffer.read()


def process_footnote_document(
    file_bytes: bytes,
    style: str,
    document_context: str = ""
) -> Tuple[bytes, List[Dict]]:
    """
    Full pipeline: extract footnotes, look up, format, update document.
    
    This integrates with the existing document_processor.process_document()
    function but provides a cleaner interface.
    
    Args:
        file_bytes: Document bytes
        style: Citation style
        document_context: Topic context for AI lookups
        
    Returns:
        Tuple of (processed_document_bytes, results_list)
    """
    # Use existing process_document function which handles footnotes well
    from document_processor import process_document
    
    return process_document(
        file_bytes,
        style=style,
        add_links=True
    )


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    # Test style detection
    test_styles = [
        'Chicago Manual of Style',
        'Chicago Author-Date',
        'APA 7',
        'Bluebook',
        'OSCOLA',
        'MLA 9',
    ]
    
    print("Style classification:")
    for style in test_styles:
        is_fn = is_footnote_style(style)
        print(f"  {style}: {'footnote' if is_fn else 'author-date'}")
