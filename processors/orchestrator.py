"""
citeflex/processors/orchestrator.py

Thin orchestration layer that coordinates the unified processing pipeline.

Flow:
1. Receive document + style
2. Determine if footnote or author-date based on style
3. Extract citations (URLs, DOIs, parentheticals)
4. Classify and route to engines
5. Build output (footnotes or parenthetical + References)
6. Return processed document

This module contains NO business logic - it only wires together:
- url_extractor
- doi_extractor
- parenthetical_extractor
- citation_classifier
- footnote_builder OR author_date_builder
- topic_extractor (for document context)

Version History:
    2025-12-12 V1.0: Initial implementation
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

from processors.url_extractor import extract_urls_from_docx, get_unique_urls
from processors.doi_extractor import extract_identifiers_from_docx, get_unique_identifiers
from processors.parenthetical_extractor import extract_parentheticals_from_docx, get_unique_citations
from processors.citation_classifier import (
    classify_extracted_item, 
    lookup_citation,
    ClassifiedCitation,
    CitationInputType,
    is_deterministic_type
)
from processors.footnote_builder import is_footnote_style, process_footnote_document
from processors.author_date_builder import (
    is_author_date_style,
    build_author_date_output,
    format_parenthetical,
    build_references_section
)
from processors.topic_extractor import extract_topics
from processors.word_document import (
    extract_body_text,
    apply_text_replacements,
    append_references_section
)
from models import CitationMetadata


@dataclass
class ProcessingResult:
    """Result from the unified processing pipeline."""
    success: bool
    document_bytes: bytes
    citations_found: int
    citations_resolved: int
    errors: List[str]
    style_used: str
    output_type: str  # "footnote" or "author-date"
    references_section: str = ""  # For author-date styles


def process_document_unified(
    file_bytes: bytes,
    style: str = "APA 7",
    add_links: bool = True
) -> ProcessingResult:
    """
    Unified document processing entry point.
    
    Automatically determines processing mode based on citation style:
    - Chicago Notes-Bibliography, Bluebook, OSCOLA → footnote processing
    - APA, MLA, Chicago Author-Date → author-date processing
    
    Args:
        file_bytes: Word document as bytes
        style: Citation style (determines output format)
        add_links: Whether to make URLs clickable
        
    Returns:
        ProcessingResult with processed document and statistics
    """
    errors = []
    
    # Determine processing mode from style
    if is_footnote_style(style):
        return _process_footnote_style(file_bytes, style, add_links, errors)
    else:
        return _process_author_date_style(file_bytes, style, add_links, errors)


def _process_footnote_style(
    file_bytes: bytes,
    style: str,
    add_links: bool,
    errors: List[str]
) -> ProcessingResult:
    """
    Process document using footnote/endnote style.
    
    Delegates to existing document_processor which handles footnotes well.
    """
    try:
        processed_bytes, results = process_footnote_document(
            file_bytes, 
            style,
            document_context=""  # Topic extraction for footnotes handled internally
        )
        
        citations_found = len(results)
        citations_resolved = sum(1 for r in results if r.success)
        
        return ProcessingResult(
            success=True,
            document_bytes=processed_bytes,
            citations_found=citations_found,
            citations_resolved=citations_resolved,
            errors=errors,
            style_used=style,
            output_type="footnote"
        )
        
    except Exception as e:
        errors.append(f"Footnote processing error: {str(e)}")
        return ProcessingResult(
            success=False,
            document_bytes=file_bytes,
            citations_found=0,
            citations_resolved=0,
            errors=errors,
            style_used=style,
            output_type="footnote"
        )


def _process_author_date_style(
    file_bytes: bytes,
    style: str,
    add_links: bool,
    errors: List[str]
) -> ProcessingResult:
    """
    Process document using author-date style.
    
    1. Extract URLs, DOIs, parentheticals from body
    2. Extract document topics for AI context
    3. Look up metadata for each
    4. Replace with parentheticals
    5. Append References section
    """
    try:
        # Step 1: Extract all citation candidates from body
        print(f"[Orchestrator] Extracting citations from document body...")
        
        urls = extract_urls_from_docx(file_bytes)
        identifiers = extract_identifiers_from_docx(file_bytes)
        parentheticals = extract_parentheticals_from_docx(file_bytes)
        
        # Combine and deduplicate
        all_extractions = []
        seen_positions = set()
        
        # URLs first (most common real-world input)
        for url in urls:
            pos = (url.get('global_start', 0), url.get('global_end', 0))
            if pos not in seen_positions:
                seen_positions.add(pos)
                all_extractions.append(url)
        
        # Then DOIs/PMIDs/etc
        for ident in identifiers:
            pos = (ident.get('global_start', 0), ident.get('global_end', 0))
            if pos not in seen_positions:
                seen_positions.add(pos)
                all_extractions.append(ident)
        
        # Then parentheticals (may overlap with above)
        for paren in parentheticals:
            pos = (paren.get('global_start', 0), paren.get('global_end', 0))
            if pos not in seen_positions:
                seen_positions.add(pos)
                all_extractions.append(paren)
        
        citations_found = len(all_extractions)
        print(f"[Orchestrator] Found {citations_found} citation candidates")
        
        if citations_found == 0:
            return ProcessingResult(
                success=True,
                document_bytes=file_bytes,
                citations_found=0,
                citations_resolved=0,
                errors=errors,
                style_used=style,
                output_type="author-date",
                references_section=""
            )
        
        # Step 2: Extract document topics for AI context
        body_text = extract_body_text(file_bytes)
        topics = extract_topics(body_text)
        document_context = ", ".join(topics) if topics else ""
        print(f"[Orchestrator] Document topics: {document_context[:100]}...")
        
        # Step 3: Classify and lookup each extraction
        metadata_map = {}  # original_text -> CitationMetadata
        all_metadata = []
        
        for extraction in all_extractions:
            classified = classify_extracted_item(extraction)
            original = extraction.get('original', extraction.get('url', str(extraction)))
            
            print(f"[Orchestrator] Looking up: {original[:50]}...")
            
            metadata = lookup_citation(classified, document_context, style)
            
            if metadata:
                metadata_map[original] = metadata
                all_metadata.append(metadata)
                print(f"[Orchestrator] ✓ Found: {metadata.title[:50] if metadata.title else 'No title'}...")
            else:
                print(f"[Orchestrator] ✗ Not found")
                errors.append(f"Could not resolve: {original[:50]}")
        
        citations_resolved = len(metadata_map)
        
        # Step 4: Build replacements and References
        replacements, references_section = build_author_date_output(
            all_extractions,
            metadata_map,
            style
        )
        
        # Step 5: Apply replacements to document body
        updated_bytes = apply_text_replacements(file_bytes, replacements)
        
        # Step 6: Append References section
        if references_section:
            updated_bytes = append_references_section(updated_bytes, references_section, style)
        
        # Step 7: Activate URLs if requested
        if add_links:
            from document_processor import LinkActivator
            from io import BytesIO
            buffer = BytesIO(updated_bytes)
            buffer = LinkActivator.process(buffer)
            updated_bytes = buffer.read()
        
        return ProcessingResult(
            success=True,
            document_bytes=updated_bytes,
            citations_found=citations_found,
            citations_resolved=citations_resolved,
            errors=errors,
            style_used=style,
            output_type="author-date",
            references_section=references_section
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        errors.append(f"Author-date processing error: {str(e)}")
        return ProcessingResult(
            success=False,
            document_bytes=file_bytes,
            citations_found=0,
            citations_resolved=0,
            errors=errors,
            style_used=style,
            output_type="author-date"
        )


def get_style_info(style: str) -> Dict:
    """
    Get information about a citation style.
    
    Args:
        style: Style name
        
    Returns:
        Dict with style metadata
    """
    is_footnote = is_footnote_style(style)
    
    return {
        'style': style,
        'output_type': 'footnote' if is_footnote else 'author-date',
        'uses_bibliography': not is_footnote,
        'bibliography_title': _get_bibliography_title(style),
    }


def _get_bibliography_title(style: str) -> str:
    """Get the appropriate bibliography heading for a style."""
    style_lower = style.lower()
    
    if 'mla' in style_lower:
        return "Works Cited"
    elif 'chicago' in style_lower and 'note' not in style_lower:
        return "References"
    elif 'apa' in style_lower:
        return "References"
    else:
        return "Bibliography"


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def process_single_citation(
    text: str,
    style: str = "APA 7",
    document_context: str = ""
) -> Tuple[Optional[CitationMetadata], str]:
    """
    Process a single citation text and return formatted output.
    
    Convenience function for API use.
    
    Args:
        text: Citation text (URL, DOI, author-year, etc.)
        style: Citation style
        document_context: Optional topic context
        
    Returns:
        Tuple of (metadata, formatted_citation)
    """
    from unified_router import get_citation
    return get_citation(text, style)


def detect_style_from_document(file_bytes: bytes) -> str:
    """
    Attempt to detect citation style from document content.
    
    Looks for patterns like:
    - Existing footnotes/endnotes → likely Chicago/Bluebook
    - (Author, Year) patterns → likely APA/MLA
    
    Args:
        file_bytes: Document bytes
        
    Returns:
        Detected style name or "APA 7" as default
    """
    from document_processor import WordDocumentProcessor
    from io import BytesIO
    
    processor = WordDocumentProcessor(BytesIO(file_bytes))
    
    # Check for existing footnotes/endnotes
    footnotes = processor.get_footnotes()
    endnotes = processor.get_endnotes()
    
    processor.cleanup()
    
    if footnotes or endnotes:
        # Document has footnotes - likely needs footnote style
        return "Chicago Manual of Style"
    
    # Check body for parenthetical patterns
    body_text = extract_body_text(file_bytes)
    
    import re
    # Look for (Author, Year) patterns
    apa_pattern = r'\([A-Z][a-z]+(?:\s+(?:&|and)\s+[A-Z][a-z]+)*,\s*\d{4}\)'
    if re.search(apa_pattern, body_text):
        return "APA 7"
    
    # Default to APA
    return "APA 7"


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    # Test style detection
    test_styles = [
        "Chicago Manual of Style",
        "Chicago Notes-Bibliography",
        "Chicago Author-Date",
        "APA 7",
        "APA",
        "MLA 9",
        "Bluebook",
        "OSCOLA",
    ]
    
    print("Style classification:")
    for style in test_styles:
        info = get_style_info(style)
        print(f"  {style}: {info['output_type']} ({info['bibliography_title']})")
