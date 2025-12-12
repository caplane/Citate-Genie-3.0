"""
citeflex/processors/doi_extractor.py

Extracts bare identifiers from Word document body text:
- DOIs (10.1086/226147)
- PMIDs (PMID: 12345678)
- arXiv IDs (arXiv:2301.12345)

These are identifiers that appear WITHOUT full URLs, which users often
copy from PDFs or reference lists.

Version History:
    2025-12-12 V1.0: Initial implementation
"""

import re
import zipfile
from io import BytesIO
from typing import List, Dict, Optional
import xml.etree.ElementTree as ET


# =============================================================================
# IDENTIFIER PATTERNS
# =============================================================================

# DOI pattern - matches bare DOIs like "10.1086/226147"
# Must start with 10. and have a suffix after the /
DOI_PATTERN = re.compile(
    r'\b(10\.\d{4,}/[^\s<>"\')\],;]+)',
    re.IGNORECASE
)

# PMID pattern - matches "PMID: 12345678" or "PMID 12345678" or "PMID:12345678"
PMID_PATTERN = re.compile(
    r'\bPMID:?\s*(\d{6,9})\b',
    re.IGNORECASE
)

# arXiv pattern - matches "arXiv:2301.12345" or "arXiv: 2301.12345"
# Also matches old format like "arXiv:hep-th/9901001"
ARXIV_PATTERN = re.compile(
    r'\barXiv:?\s*(\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+/\d{7})\b',
    re.IGNORECASE
)

# ISBN pattern - matches ISBN-10 and ISBN-13
ISBN_PATTERN = re.compile(
    r'\bISBN[-:]?\s*((?:\d[-\s]?){9}[\dXx]|(?:\d[-\s]?){13})\b',
    re.IGNORECASE
)


# =============================================================================
# EXTRACTION FUNCTIONS
# =============================================================================

def extract_dois(text: str) -> List[Dict]:
    """
    Extract bare DOIs from text.
    
    Args:
        text: Text to search
        
    Returns:
        List of dicts with 'identifier', 'type', 'start', 'end'
    """
    results = []
    
    for match in DOI_PATTERN.finditer(text):
        doi = match.group(1)
        # Clean trailing punctuation
        doi = doi.rstrip('.,;:!?)]\'"')
        
        results.append({
            'identifier': doi,
            'type': 'doi',
            'original': match.group(0),
            'start': match.start(),
            'end': match.end(),
        })
    
    return results


def extract_pmids(text: str) -> List[Dict]:
    """
    Extract PMIDs from text.
    
    Args:
        text: Text to search
        
    Returns:
        List of dicts with 'identifier', 'type', 'start', 'end'
    """
    results = []
    
    for match in PMID_PATTERN.finditer(text):
        results.append({
            'identifier': match.group(1),
            'type': 'pmid',
            'original': match.group(0),
            'start': match.start(),
            'end': match.end(),
        })
    
    return results


def extract_arxiv_ids(text: str) -> List[Dict]:
    """
    Extract arXiv IDs from text.
    
    Args:
        text: Text to search
        
    Returns:
        List of dicts with 'identifier', 'type', 'start', 'end'
    """
    results = []
    
    for match in ARXIV_PATTERN.finditer(text):
        results.append({
            'identifier': match.group(1),
            'type': 'arxiv',
            'original': match.group(0),
            'start': match.start(),
            'end': match.end(),
        })
    
    return results


def extract_isbns(text: str) -> List[Dict]:
    """
    Extract ISBNs from text.
    
    Args:
        text: Text to search
        
    Returns:
        List of dicts with 'identifier', 'type', 'start', 'end'
    """
    results = []
    
    for match in ISBN_PATTERN.finditer(text):
        # Normalize ISBN - remove hyphens and spaces
        isbn = re.sub(r'[-\s]', '', match.group(1))
        
        results.append({
            'identifier': isbn,
            'type': 'isbn',
            'original': match.group(0),
            'start': match.start(),
            'end': match.end(),
        })
    
    return results


def extract_all_identifiers(text: str) -> List[Dict]:
    """
    Extract all identifier types from text.
    
    Args:
        text: Text to search
        
    Returns:
        List of all identifiers found, sorted by position
    """
    results = []
    results.extend(extract_dois(text))
    results.extend(extract_pmids(text))
    results.extend(extract_arxiv_ids(text))
    results.extend(extract_isbns(text))
    
    # Sort by position
    results.sort(key=lambda x: x['start'])
    
    return results


def extract_identifiers_from_docx(file_bytes: bytes) -> List[Dict]:
    """
    Extract bare identifiers from a Word document's body text.
    
    Does NOT extract from footnotes/endnotes.
    
    Args:
        file_bytes: The .docx file as bytes
        
    Returns:
        List of identifier dicts with position data
    """
    try:
        with zipfile.ZipFile(BytesIO(file_bytes), 'r') as zf:
            if 'word/document.xml' not in zf.namelist():
                print("[DOIExtractor] No document.xml found")
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
                
                # Find identifiers in this paragraph
                para_ids = extract_all_identifiers(para_text)
                
                for id_info in para_ids:
                    id_info['paragraph_offset'] = char_offset
                    id_info['global_start'] = char_offset + id_info['start']
                    id_info['global_end'] = char_offset + id_info['end']
                    results.append(id_info)
                
                char_offset += len(para_text) + 1
            
            # Count by type
            type_counts = {}
            for r in results:
                t = r['type']
                type_counts[t] = type_counts.get(t, 0) + 1
            
            print(f"[DOIExtractor] Found identifiers: {type_counts}")
            return results
            
    except Exception as e:
        print(f"[DOIExtractor] Error: {e}")
        return []


def get_unique_identifiers(id_list: List[Dict]) -> List[Dict]:
    """
    Deduplicate identifiers, keeping first occurrence.
    
    Args:
        id_list: List of identifier dicts
        
    Returns:
        Deduplicated list
    """
    seen = set()
    unique = []
    
    for id_info in id_list:
        key = (id_info['type'], id_info['identifier'])
        if key not in seen:
            seen.add(key)
            unique.append(id_info)
    
    return unique


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def is_valid_doi(doi: str) -> bool:
    """Check if string is a valid DOI format."""
    return bool(DOI_PATTERN.match(doi))


def is_valid_pmid(pmid: str) -> bool:
    """Check if string is a valid PMID."""
    return bool(re.match(r'^\d{6,9}$', pmid))


def is_valid_arxiv_id(arxiv_id: str) -> bool:
    """Check if string is a valid arXiv ID."""
    return bool(re.match(r'^(\d{4}\.\d{4,5}(v\d+)?|[a-z-]+/\d{7})$', arxiv_id, re.IGNORECASE))


def is_valid_isbn(isbn: str) -> bool:
    """Check if string is a valid ISBN-10 or ISBN-13."""
    isbn = re.sub(r'[-\s]', '', isbn)
    return bool(re.match(r'^(\d{10}|\d{13})$', isbn))


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    test_text = """
    The DOI is 10.1086/226147 for the Coleman paper.
    See PMID: 12345678 for the clinical trial.
    The preprint is at arXiv:2301.12345 or arXiv: hep-th/9901001.
    The book ISBN is 978-0-14-028329-7.
    Another DOI: 10.1177/0003122410395370.
    """
    
    ids = extract_all_identifiers(test_text)
    print("Extracted identifiers:")
    for i in ids:
        print(f"  [{i['type']}] {i['identifier']}")
