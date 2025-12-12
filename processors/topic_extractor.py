"""
citeflex/topic_extractor.py

Extracts topic keywords from document text to provide context for AI citation lookup.

The extracted topics help disambiguate between authors with the same name
working in different fields. For example, "Collins" could be:
- Francis Collins (genetics)
- Randall Collins (sociology)
- Patricia Hill Collins (sociology/feminism)

By providing topic context like "religion, sexuality, sociology", the AI
can identify the correct author and work.

Version History:
    2025-12-12 V1.0: Initial implementation
"""

import re
from collections import Counter
from typing import List, Optional
import zipfile
from io import BytesIO
import xml.etree.ElementTree as ET


# Common English stop words to exclude
STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
    'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
    'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need',
    'this', 'that', 'these', 'those', 'it', 'its', 'they', 'them', 'their',
    'we', 'us', 'our', 'you', 'your', 'he', 'him', 'his', 'she', 'her',
    'who', 'whom', 'which', 'what', 'where', 'when', 'why', 'how',
    'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other',
    'some', 'such', 'no', 'not', 'only', 'same', 'so', 'than', 'too',
    'very', 'just', 'also', 'now', 'here', 'there', 'then', 'once',
    'if', 'because', 'although', 'while', 'though', 'after', 'before',
    'about', 'into', 'through', 'during', 'above', 'below', 'between',
    'under', 'over', 'again', 'further', 'any', 'even', 'still', 'already',
}

# Generic academic terms that don't help with topic identification
ACADEMIC_STOP_WORDS = {
    'study', 'studies', 'research', 'researchers', 'analysis', 'analyses',
    'results', 'result', 'findings', 'finding', 'data', 'method', 'methods',
    'approach', 'approaches', 'theory', 'theories', 'theoretical',
    'model', 'models', 'table', 'figure', 'chapter', 'section',
    'paper', 'article', 'journal', 'review', 'literature', 'hypothesis',
    'conclusion', 'conclusions', 'introduction', 'discussion', 'abstract',
    'sample', 'samples', 'variable', 'variables', 'effect', 'effects',
    'relationship', 'relationships', 'association', 'associations',
    'significant', 'significance', 'level', 'levels', 'measure', 'measures',
    'coefficient', 'coefficients', 'standard', 'error', 'errors',
    'percent', 'percentage', 'number', 'total', 'mean', 'average',
    'however', 'therefore', 'thus', 'hence', 'moreover', 'furthermore',
    'regarding', 'concerning', 'according', 'based', 'using', 'used',
    'show', 'shows', 'shown', 'found', 'suggest', 'suggests', 'suggested',
    'indicate', 'indicates', 'indicated', 'note', 'noted', 'see', 'example',
    'first', 'second', 'third', 'one', 'two', 'three', 'four', 'five',
    'year', 'years', 'time', 'times', 'case', 'cases', 'point', 'points',
    'new', 'different', 'similar', 'important', 'general', 'specific',
    'recent', 'previous', 'current', 'present', 'following', 'given',
    'particular', 'available', 'possible', 'likely', 'certain', 'common',
    'among', 'within', 'across', 'whether', 'being', 'become', 'became',
    'make', 'made', 'take', 'taken', 'give', 'given', 'come', 'came',
    'work', 'works', 'working', 'include', 'includes', 'including',
    'provide', 'provides', 'provided', 'consider', 'considered',
    'report', 'reports', 'reported', 'describe', 'described',
    'examine', 'examines', 'examined', 'explore', 'explores', 'explored',
    'argue', 'argues', 'argued', 'claim', 'claims', 'claimed',
    'focus', 'focused', 'address', 'addressed', 'attempt', 'attempted',
}

# Combine all stop words
ALL_STOP_WORDS = STOP_WORDS | ACADEMIC_STOP_WORDS


def extract_text_from_docx(file_bytes: bytes) -> str:
    """
    Extract body text from a .docx file.
    
    Args:
        file_bytes: The document as bytes
        
    Returns:
        Plain text content of the document body
    """
    try:
        with zipfile.ZipFile(BytesIO(file_bytes), 'r') as zf:
            # Read document.xml (main body)
            if 'word/document.xml' not in zf.namelist():
                return ""
            
            with zf.open('word/document.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
            
            # Extract all text elements
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            text_parts = []
            
            for t in root.findall('.//w:t', ns):
                if t.text:
                    text_parts.append(t.text)
            
            return ' '.join(text_parts)
            
    except Exception as e:
        print(f"[TopicExtractor] Error extracting text: {e}")
        return ""


def extract_topics(text: str, max_topics: int = 15) -> List[str]:
    """
    Extract topic keywords from text.
    
    Args:
        text: Document body text
        max_topics: Maximum number of topics to return
        
    Returns:
        List of topic keywords, ordered by frequency
    """
    if not text or len(text) < 100:
        return []
    
    # Tokenize: extract words (letters only, 4+ chars)
    words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
    
    # Filter stop words
    meaningful_words = [w for w in words if w not in ALL_STOP_WORDS]
    
    # Count frequencies
    word_counts = Counter(meaningful_words)
    
    # Get top N most common
    top_words = [word for word, count in word_counts.most_common(max_topics * 2)
                 if count >= 3]  # Must appear at least 3 times
    
    return top_words[:max_topics]


def extract_topics_from_docx(file_bytes: bytes, max_topics: int = 15) -> List[str]:
    """
    Extract topic keywords directly from a .docx file.
    
    Args:
        file_bytes: The document as bytes
        max_topics: Maximum number of topics to return
        
    Returns:
        List of topic keywords
    """
    text = extract_text_from_docx(file_bytes)
    return extract_topics(text, max_topics)


def format_context_string(topics: List[str]) -> str:
    """
    Format topics into a context string for AI lookup.
    
    Args:
        topics: List of topic keywords
        
    Returns:
        Formatted context string like:
        "an academic document about religion, sexuality, HIV, sociology"
    """
    if not topics:
        return ""
    
    return f"an academic document about {', '.join(topics)}"


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def get_document_context(file_bytes: bytes, max_topics: int = 15) -> str:
    """
    Main entry point: Extract topics from docx and format as context string.
    
    Args:
        file_bytes: The document as bytes
        max_topics: Maximum topics to include
        
    Returns:
        Context string for AI lookup, e.g.:
        "an academic document about religion, sexuality, sociology, marriage"
        
    Example:
        >>> context = get_document_context(doc_bytes)
        >>> # Pass to AI lookup:
        >>> lookup_parenthetical_citation_options("(Adamczyk, 2010)", context=context)
    """
    topics = extract_topics_from_docx(file_bytes, max_topics)
    
    if topics:
        print(f"[TopicExtractor] Extracted topics: {topics}")
    else:
        print("[TopicExtractor] No topics extracted")
    
    return format_context_string(topics)


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    # Test with sample text
    sample_text = """
    This article examines the relationship between religion and attitudes toward 
    premarital sex among young adults in the United States. Using data from the 
    National Longitudinal Study of Adolescent Health, we analyze how religious 
    affiliation, religious attendance, and religious salience affect sexual 
    attitudes and behaviors. Our findings suggest that Muslims and evangelical 
    Protestants hold more conservative attitudes toward sexuality compared to 
    mainline Protestants and Catholics. We also find that HIV/AIDS awareness 
    programs in religious communities have varying effects on sexual behavior.
    The sociology of religion provides important theoretical frameworks for 
    understanding these patterns of sexuality and morality.
    """
    
    topics = extract_topics(sample_text, max_topics=10)
    print(f"Extracted topics: {topics}")
    print(f"Context string: {format_context_string(topics)}")
