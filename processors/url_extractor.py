"""
citeflex/processors/url_extractor.py

Extracts URLs from Word document body text.

Identifies academic URLs (DOI, JSTOR, PubMed, arXiv, etc.) and general URLs
that users paste into drafts as citation placeholders.

Version History:
    2025-12-12 V1.0: Initial implementation
"""

import re
import zipfile
from io import BytesIO
from typing import List, Dict, Optional
import xml.etree.ElementTree as ET


# URL pattern - matches http/https URLs
# Note: We allow parentheses in URLs (common in DOIs, Lancet article IDs, etc.)
# The clean_url() function will handle unbalanced trailing parens
URL_PATTERN = re.compile(
    r'https?://[^\s<>"\'\]]+',
    re.IGNORECASE
)

# Academic domain patterns for prioritization
ACADEMIC_DOMAINS = [
    'doi.org',
    'dx.doi.org',
    'jstor.org',
    'pubmed.ncbi.nlm.nih.gov',
    'ncbi.nlm.nih.gov',
    'arxiv.org',
    'scholar.google.com',
    'academic.oup.com',
    'cambridge.org',
    'springer.com',
    'link.springer.com',
    'wiley.com',
    'onlinelibrary.wiley.com',
    'tandfonline.com',
    'sagepub.com',
    'sciencedirect.com',
    'nature.com',
    'science.org',
    'pnas.org',
    'cell.com',
    'biorxiv.org',
    'medrxiv.org',
    'ssrn.com',
    'researchgate.net',
]


def is_academic_url(url: str) -> bool:
    """
    Check if URL is from an academic source.
    
    Args:
        url: The URL to check
        
    Returns:
        True if from academic domain
    """
    url_lower = url.lower()
    return any(domain in url_lower for domain in ACADEMIC_DOMAINS)


def clean_url(url: str) -> str:
    """
    Clean URL by removing trailing punctuation that may have been captured.
    
    Args:
        url: Raw extracted URL
        
    Returns:
        Cleaned URL
    """
    # Remove trailing punctuation that's likely not part of URL
    url = url.rstrip('.,;:!?)]\'"')
    
    # Handle parentheses - if URL has unbalanced closing parens, remove them
    open_count = url.count('(')
    close_count = url.count(')')
    while close_count > open_count and url.endswith(')'):
        url = url[:-1]
        close_count -= 1
    
    return url


def extract_urls_from_text(text: str) -> List[Dict[str, any]]:
    """
    Extract all URLs from text.
    
    Args:
        text: Plain text to search
        
    Returns:
        List of dicts with 'url', 'start', 'end', 'is_academic' keys
    """
    results = []
    
    for match in URL_PATTERN.finditer(text):
        raw_url = match.group(0)
        cleaned = clean_url(raw_url)
        
        results.append({
            'url': cleaned,
            'original': raw_url,
            'start': match.start(),
            'end': match.start() + len(cleaned),
            'is_academic': is_academic_url(cleaned),
        })
    
    return results


def extract_urls_from_docx(file_bytes: bytes) -> List[Dict[str, any]]:
    """
    Extract URLs from a Word document's body text.
    
    Does NOT extract from footnotes/endnotes - those are handled separately.
    
    Args:
        file_bytes: The .docx file as bytes
        
    Returns:
        List of dicts with URL info including position data
    """
    try:
        with zipfile.ZipFile(BytesIO(file_bytes), 'r') as zf:
            # Read document.xml (main body only)
            if 'word/document.xml' not in zf.namelist():
                print("[URLExtractor] No document.xml found")
                return []
            
            with zf.open('word/document.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
            
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            
            # Extract text while tracking paragraph positions
            results = []
            char_offset = 0
            
            for para in root.findall('.//w:p', ns):
                para_text_parts = []
                
                for t in para.findall('.//w:t', ns):
                    if t.text:
                        para_text_parts.append(t.text)
                
                para_text = ''.join(para_text_parts)
                
                # Find URLs in this paragraph
                para_urls = extract_urls_from_text(para_text)
                
                for url_info in para_urls:
                    url_info['paragraph_offset'] = char_offset
                    url_info['global_start'] = char_offset + url_info['start']
                    url_info['global_end'] = char_offset + url_info['end']
                    results.append(url_info)
                
                char_offset += len(para_text) + 1  # +1 for paragraph break
            
            print(f"[URLExtractor] Found {len(results)} URLs in document body")
            return results
            
    except Exception as e:
        print(f"[URLExtractor] Error: {e}")
        return []


def get_unique_urls(url_list: List[Dict]) -> List[Dict]:
    """
    Deduplicate URLs, keeping first occurrence.
    
    Args:
        url_list: List of URL dicts from extract_urls_from_docx
        
    Returns:
        Deduplicated list
    """
    seen = set()
    unique = []
    
    for url_info in url_list:
        url = url_info['url']
        if url not in seen:
            seen.add(url)
            unique.append(url_info)
    
    return unique


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    test_text = """
    According to https://doi.org/10.1086/226147, social capital is important.
    See also https://www.jstor.org/stable/2095101 for more details.
    The study (https://pubmed.ncbi.nlm.nih.gov/12345678/) found significant results.
    More info at https://example.com/page?q=test.
    """
    
    urls = extract_urls_from_text(test_text)
    print("Extracted URLs:")
    for u in urls:
        print(f"  {u['url']} (academic: {u['is_academic']})")
