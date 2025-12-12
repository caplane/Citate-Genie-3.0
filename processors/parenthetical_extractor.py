"""
citeflex/processors/parenthetical_extractor.py

Extracts parenthetical citations from Word document body text:
- Clean (Author, Year): (Coleman, 1988)
- Multiple authors: (Coleman & Weber, 1988) or (Coleman, Weber, & Marx, 1988)
- Multiple citations: (Coleman, 1988; Weber, 1905)
- With page numbers: (Coleman, 1988, p. 45) or (Coleman, 1988, pp. 45-50)
- Narrative: Coleman (1988) showed...
- Et al.: (Smith et al., 2020)
- Messy keywords: (caplan trains spain) - treat as search query

Version History:
    2025-12-12 V1.0: Initial implementation
"""

import re
import zipfile
from io import BytesIO
from typing import List, Dict, Optional, Tuple
import xml.etree.ElementTree as ET


# =============================================================================
# PATTERNS
# =============================================================================

# Author name pattern - capitalized word, may include hyphen or apostrophe
AUTHOR_NAME = r"[A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)*"

# Year pattern - 4 digits, optionally with letter suffix (2020a, 2020b)
YEAR = r"\d{4}[a-z]?"

# Page number pattern
PAGE_NUM = r"(?:pp?\.?\s*\d+(?:\s*[-–—]\s*\d+)?)"

# Standard parenthetical: (Author, Year) or (Author & Author, Year)
STANDARD_PARENTHETICAL = re.compile(
    rf'\(({AUTHOR_NAME}(?:\s*(?:&|and|,)\s*{AUTHOR_NAME})*(?:\s+et\s+al\.?)?)\s*,\s*({YEAR})(?:\s*,\s*{PAGE_NUM})?\)',
    re.IGNORECASE
)

# Multiple citations in one parenthetical: (Author, Year; Author, Year)
MULTI_CITATION = re.compile(
    rf'\(({AUTHOR_NAME}\s*,\s*{YEAR}(?:\s*;\s*{AUTHOR_NAME}\s*,\s*{YEAR})+)\)',
    re.IGNORECASE
)

# Narrative citation: Author (Year) or Author & Author (Year)
NARRATIVE_CITATION = re.compile(
    rf'({AUTHOR_NAME}(?:\s*(?:&|and)\s*{AUTHOR_NAME})?(?:\s+et\s+al\.?)?)\s*\(({YEAR})\)',
    re.IGNORECASE
)

# Any parenthetical content that might be a citation attempt
# Used to catch messy keywords like (caplan trains spain)
PARENTHETICAL_CONTENT = re.compile(r'\(([^()]{3,100})\)')


# =============================================================================
# EXTRACTION FUNCTIONS
# =============================================================================

def extract_standard_parentheticals(text: str) -> List[Dict]:
    """
    Extract standard (Author, Year) citations.
    
    Handles:
    - (Coleman, 1988)
    - (Coleman & Weber, 1988)
    - (Smith, Jones, & Lee, 2020)
    - (Smith et al., 2020)
    - (Coleman, 1988, p. 45)
    
    Args:
        text: Text to search
        
    Returns:
        List of citation dicts
    """
    results = []
    
    for match in STANDARD_PARENTHETICAL.finditer(text):
        authors_str = match.group(1).strip()
        year = match.group(2).strip()
        
        # Parse authors
        authors = parse_author_string(authors_str)
        
        # Check for page number
        full_match = match.group(0)
        page_match = re.search(r'(?:pp?\.?\s*)(\d+(?:\s*[-–—]\s*\d+)?)', full_match)
        page = page_match.group(1) if page_match else None
        
        results.append({
            'type': 'standard',
            'authors': authors,
            'year': year,
            'page': page,
            'original': full_match,
            'start': match.start(),
            'end': match.end(),
            'citation_text': f"({authors_str}, {year})",
        })
    
    return results


def extract_multi_citations(text: str) -> List[Dict]:
    """
    Extract multiple citations in one parenthetical.
    
    Handles: (Coleman, 1988; Weber, 1905; Marx, 1867)
    
    Returns the full parenthetical plus parsed individual citations.
    
    Args:
        text: Text to search
        
    Returns:
        List of citation dicts, each containing 'sub_citations' list
    """
    results = []
    
    for match in MULTI_CITATION.finditer(text):
        full_content = match.group(1)
        
        # Split on semicolon
        parts = [p.strip() for p in full_content.split(';')]
        sub_citations = []
        
        for part in parts:
            # Parse each "Author, Year" pair
            sub_match = re.match(rf'({AUTHOR_NAME})\s*,\s*({YEAR})', part, re.IGNORECASE)
            if sub_match:
                sub_citations.append({
                    'authors': [sub_match.group(1)],
                    'year': sub_match.group(2),
                    'citation_text': f"({sub_match.group(1)}, {sub_match.group(2)})",
                })
        
        if len(sub_citations) > 1:  # Only if we actually found multiple
            results.append({
                'type': 'multiple',
                'original': match.group(0),
                'start': match.start(),
                'end': match.end(),
                'sub_citations': sub_citations,
            })
    
    return results


def extract_narrative_citations(text: str) -> List[Dict]:
    """
    Extract narrative citations like "Coleman (1988) showed..."
    
    Args:
        text: Text to search
        
    Returns:
        List of citation dicts
    """
    results = []
    
    for match in NARRATIVE_CITATION.finditer(text):
        authors_str = match.group(1).strip()
        year = match.group(2).strip()
        
        authors = parse_author_string(authors_str)
        
        results.append({
            'type': 'narrative',
            'authors': authors,
            'year': year,
            'original': match.group(0),
            'start': match.start(),
            'end': match.end(),
            'citation_text': f"({authors_str}, {year})",
        })
    
    return results


def extract_messy_parentheticals(text: str, known_positions: set) -> List[Dict]:
    """
    Extract parenthetical content that might be messy citation attempts.
    
    Skips positions already identified as standard/narrative/multi citations.
    
    Args:
        text: Text to search
        known_positions: Set of (start, end) tuples already identified
        
    Returns:
        List of potential messy citation dicts
    """
    results = []
    
    for match in PARENTHETICAL_CONTENT.finditer(text):
        # Skip if already identified
        if (match.start(), match.end()) in known_positions:
            continue
        
        content = match.group(1).strip()
        
        # Skip if it looks like a standard citation we missed
        if re.match(rf'^{AUTHOR_NAME}\s*,\s*{YEAR}', content, re.IGNORECASE):
            continue
        
        # Skip if it's just a number or very short
        if re.match(r'^[\d\s,.-]+$', content) or len(content) < 5:
            continue
        
        # Skip if it looks like a parenthetical aside, not a citation
        # (common patterns: "i.e.", "e.g.", "see", "for example")
        if re.match(r'^(i\.?e\.?|e\.?g\.?|see|for example|that is|namely)', content, re.IGNORECASE):
            continue
        
        # Skip if it's a URL (handled by url_extractor)
        if content.startswith('http'):
            continue
        
        # This might be a messy keyword search like (caplan trains spain)
        results.append({
            'type': 'keywords',
            'query': content,
            'original': match.group(0),
            'start': match.start(),
            'end': match.end(),
        })
    
    return results


def parse_author_string(authors_str: str) -> List[str]:
    """
    Parse author string into list of author names.
    
    "Coleman" -> ["Coleman"]
    "Coleman & Weber" -> ["Coleman", "Weber"]
    "Smith, Jones, & Lee" -> ["Smith", "Jones", "Lee"]
    "Smith et al." -> ["Smith et al."]
    
    Args:
        authors_str: Raw author string
        
    Returns:
        List of author names
    """
    # Handle "et al."
    if 'et al' in authors_str.lower():
        # Keep as single entry with et al.
        base = re.sub(r'\s+et\s+al\.?', '', authors_str, flags=re.IGNORECASE).strip()
        base = re.sub(r'[,&]', '', base).strip()
        return [f"{base} et al."]
    
    # Normalize separators
    normalized = re.sub(r'\s*&\s*', ', ', authors_str)
    normalized = re.sub(r'\s+and\s+', ', ', normalized, flags=re.IGNORECASE)
    
    # Split and clean
    parts = [p.strip() for p in normalized.split(',') if p.strip()]
    
    return parts


def extract_all_parentheticals(text: str) -> List[Dict]:
    """
    Extract all parenthetical citations from text.
    
    Args:
        text: Text to search
        
    Returns:
        All citations found, sorted by position
    """
    results = []
    known_positions = set()
    
    # Standard parentheticals first
    standard = extract_standard_parentheticals(text)
    for r in standard:
        results.append(r)
        known_positions.add((r['start'], r['end']))
    
    # Multiple citations
    multi = extract_multi_citations(text)
    for r in multi:
        results.append(r)
        known_positions.add((r['start'], r['end']))
    
    # Narrative citations
    narrative = extract_narrative_citations(text)
    for r in narrative:
        results.append(r)
        known_positions.add((r['start'], r['end']))
    
    # Messy/keyword parentheticals (last, to avoid duplicates)
    messy = extract_messy_parentheticals(text, known_positions)
    results.extend(messy)
    
    # Sort by position
    results.sort(key=lambda x: x['start'])
    
    return results


def extract_parentheticals_from_docx(file_bytes: bytes) -> List[Dict]:
    """
    Extract parenthetical citations from a Word document's body text.
    
    Args:
        file_bytes: The .docx file as bytes
        
    Returns:
        List of citation dicts with position data
    """
    try:
        with zipfile.ZipFile(BytesIO(file_bytes), 'r') as zf:
            if 'word/document.xml' not in zf.namelist():
                print("[ParentheticalExtractor] No document.xml found")
                return []
            
            with zf.open('word/document.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
            
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            
            results = []
            char_offset = 0
            
            for para in root.findall('.//w:p', ns):
                para_text_parts = []
                
                for t in para.findall('.//w:t', ns):
                    if t.text:
                        para_text_parts.append(t.text)
                
                para_text = ''.join(para_text_parts)
                
                # Find citations in this paragraph
                para_citations = extract_all_parentheticals(para_text)
                
                for cite in para_citations:
                    cite['paragraph_offset'] = char_offset
                    cite['global_start'] = char_offset + cite['start']
                    cite['global_end'] = char_offset + cite['end']
                    results.append(cite)
                
                char_offset += len(para_text) + 1
            
            # Count by type
            type_counts = {}
            for r in results:
                t = r['type']
                type_counts[t] = type_counts.get(t, 0) + 1
            
            print(f"[ParentheticalExtractor] Found citations: {type_counts}")
            return results
            
    except Exception as e:
        print(f"[ParentheticalExtractor] Error: {e}")
        return []


def get_unique_citations(cite_list: List[Dict]) -> List[Dict]:
    """
    Deduplicate citations for lookup purposes.
    
    Multiple occurrences of (Coleman, 1988) only need one lookup.
    
    Args:
        cite_list: List of citation dicts
        
    Returns:
        Deduplicated list (keeps first occurrence)
    """
    seen = set()
    unique = []
    
    for cite in cite_list:
        if cite['type'] == 'multiple':
            # For multiple citations, each sub-citation needs lookup
            for sub in cite.get('sub_citations', []):
                key = (tuple(sub.get('authors', [])), sub.get('year', ''))
                if key not in seen:
                    seen.add(key)
                    unique.append({
                        'type': 'standard',
                        'authors': sub['authors'],
                        'year': sub['year'],
                        'citation_text': sub['citation_text'],
                        'original': sub['citation_text'],
                        'from_multiple': True,
                    })
        elif cite['type'] == 'keywords':
            key = cite.get('query', '')
            if key and key not in seen:
                seen.add(key)
                unique.append(cite)
        else:
            key = (tuple(cite.get('authors', [])), cite.get('year', ''))
            if key not in seen:
                seen.add(key)
                unique.append(cite)
    
    return unique


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    test_text = """
    According to (Coleman, 1988), social capital matters.
    Weber (1905) also discussed this topic.
    See (Smith & Jones, 2020, p. 45) for more details.
    Multiple sources agree (Coleman, 1988; Weber, 1905; Marx, 1867).
    Smith et al. (2020) found similar results.
    The study (Smith et al., 2020) confirmed this.
    Some argue (caplan trains spain) that transportation matters.
    """
    
    citations = extract_all_parentheticals(test_text)
    print("Extracted citations:")
    for c in citations:
        print(f"  [{c['type']}] {c['original']}")
        if c['type'] == 'multiple':
            for sub in c.get('sub_citations', []):
                print(f"      -> {sub['citation_text']}")
