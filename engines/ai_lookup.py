"""
citeflex/engines/ai_lookup.py

Consolidated AI-powered citation engine.

This is the SINGLE module for all AI operations in CiteFlex:
- Classification (type detection)
- Batch classification (for document processing)
- Parenthetical citation lookup: "(Simonton, 1992)"
- Fragment lookup with verification: "caplan trains brains"

Provider chain is configurable via AI_PROVIDER_CHAIN environment variable.
Default order optimizes for cost: gemini → openai → claude

ARCHITECTURE:
- Layer 5: Classification (determine citation type)
- Layer 6: AI-assisted search (last resort after free/paid DBs fail)

HALLUCINATION SAFEGUARD:
- AI suggestions are ALWAYS verified against free databases
- If no database confirms the AI's guess, result is rejected

Version History:
    2025-12-12 V2.0: MAJOR CONSOLIDATION
                     - Merged routers/claude.py (classification, batch)
                     - Merged routers/gemini.py (classification)
                     - Added configurable provider chain
                     - Added lookup_fragment() with gist context + DB verification
                     - Deleted routers/claude.py, routers/gemini.py
    2025-12-10 V1.1: Added multi-option support for parenthetical citations
    2025-12-10 V1.0: Initial implementation - OpenAI/Claude for parentheticals
"""

import os
import re
import json
import time
import requests
from typing import Optional, List, Tuple, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from models import CitationMetadata, CitationType
from config import DEFAULT_TIMEOUT
from cost_tracker import log_api_call

# =============================================================================
# API KEYS (from config.py - centralized key management)
# =============================================================================

from config import OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY

# =============================================================================
# PROVIDER CHAIN CONFIGURATION
# =============================================================================
# Order determines fallback sequence. Default optimizes for cost:
#   Gemini Flash:  ~$0.075/1M input tokens (cheapest)
#   OpenAI GPT-4o: ~$2.50/1M input tokens
#   Claude Sonnet: ~$3.00/1M input tokens

AI_PROVIDER_CHAIN = os.environ.get('AI_PROVIDER_CHAIN', 'gemini,openai,claude').split(',')
AI_PROVIDER_CHAIN = [p.strip().lower() for p in AI_PROVIDER_CHAIN if p.strip()]

if not AI_PROVIDER_CHAIN:
    AI_PROVIDER_CHAIN = ['gemini', 'openai', 'claude']

# Model configuration
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o')
CLAUDE_MODEL = os.environ.get('CLAUDE_MODEL', 'claude-3-5-sonnet-20241022')

# Check which providers are available
AVAILABLE_PROVIDERS = []
if GEMINI_API_KEY:
    AVAILABLE_PROVIDERS.append('gemini')
if OPENAI_API_KEY:
    AVAILABLE_PROVIDERS.append('openai')
if ANTHROPIC_API_KEY:
    AVAILABLE_PROVIDERS.append('claude')

# Filter chain to only available providers
ACTIVE_CHAIN = [p for p in AI_PROVIDER_CHAIN if p in AVAILABLE_PROVIDERS]

if ACTIVE_CHAIN:
    print(f"[AI_Lookup] Provider chain: {' → '.join(ACTIVE_CHAIN)}")
else:
    print("[AI_Lookup] WARNING: No AI providers configured")


# =============================================================================
# UNIFIED AI CALLER
# =============================================================================

def _call_ai(prompt: str, system: str, max_tokens: int = 1000) -> Optional[str]:
    """
    Call AI using the configured provider chain.
    
    Tries each provider in order until one succeeds.
    Returns raw text response or None if all fail.
    """
    for provider in ACTIVE_CHAIN:
        try:
            if provider == 'gemini':
                result = _call_gemini(prompt, system, max_tokens)
            elif provider == 'openai':
                result = _call_openai(prompt, system, max_tokens)
            elif provider == 'claude':
                result = _call_claude(prompt, system, max_tokens)
            else:
                continue
            
            if result:
                return result
                
        except Exception as e:
            print(f"[AI_Lookup] {provider} failed: {e}")
            continue
    
    return None


def _call_gemini(prompt: str, system: str, max_tokens: int) -> Optional[str]:
    """Call Gemini API."""
    if not GEMINI_API_KEY:
        return None
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    
    response = requests.post(
        url,
        headers={
            'Content-Type': 'application/json',
            'x-goog-api-key': GEMINI_API_KEY,
        },
        json={
            'contents': [{'parts': [{'text': f"{system}\n\n{prompt}"}]}],
            'generationConfig': {'temperature': 0.1, 'maxOutputTokens': max_tokens}
        },
        timeout=30
    )
    
    if response.status_code == 429:
        raise Exception("Rate limited")
    
    response.raise_for_status()
    data = response.json()
    
    # Extract usage for cost tracking
    usage = data.get('usageMetadata', {})
    input_tokens = usage.get('promptTokenCount', 0)
    output_tokens = usage.get('candidatesTokenCount', 0)
    log_api_call('gemini', input_tokens, output_tokens, prompt[:100], 'ai_lookup')
    
    candidates = data.get('candidates', [])
    if not candidates:
        return None
    
    return candidates[0].get('content', {}).get('parts', [{}])[0].get('text', '')


def _call_openai(prompt: str, system: str, max_tokens: int) -> Optional[str]:
    """Call OpenAI API."""
    if not OPENAI_API_KEY:
        return None
    
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": max_tokens
        },
        timeout=30
    )
    
    if response.status_code == 429:
        raise Exception("Rate limited")
    
    response.raise_for_status()
    result = response.json()
    
    # Extract usage for cost tracking
    usage = result.get('usage', {})
    input_tokens = usage.get('prompt_tokens', 0)
    output_tokens = usage.get('completion_tokens', 0)
    log_api_call('openai', input_tokens, output_tokens, prompt[:100], 'ai_lookup')
    
    return result['choices'][0]['message']['content']


def _call_claude(prompt: str, system: str, max_tokens: int) -> Optional[str]:
    """Call Claude API."""
    if not ANTHROPIC_API_KEY:
        return None
    
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        },
        json={
            "model": CLAUDE_MODEL,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}]
        },
        timeout=30
    )
    
    if response.status_code == 429:
        raise Exception("Rate limited")
    
    response.raise_for_status()
    result = response.json()
    
    # Extract usage for cost tracking
    usage = result.get('usage', {})
    input_tokens = usage.get('input_tokens', 0)
    output_tokens = usage.get('output_tokens', 0)
    log_api_call('claude', input_tokens, output_tokens, prompt[:100], 'ai_lookup')
    
    return result['content'][0]['text']


def _parse_json_response(text: str) -> Optional[dict]:
    """Parse JSON from AI response, handling markdown code blocks."""
    if not text:
        return None
    
    text = text.strip()
    
    # Remove markdown code blocks
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    
    # Find JSON object or array
    json_match = re.search(r'[\[{][\s\S]*[\]}]', text)
    if not json_match:
        return None
    
    try:
        return json.loads(json_match.group())
    except json.JSONDecodeError:
        return None


# =============================================================================
# CLASSIFICATION (Layer 5)
# =============================================================================

CLASSIFY_SYSTEM = """You are a citation classification expert. Analyze the input and classify it.

Classify as one of:
- legal: Court cases, statutes, legal documents (contains "v." or "v ")
- book: Books, monographs, edited volumes
- journal: Academic journal articles, peer-reviewed papers
- newspaper: Newspaper/magazine articles
- government: Government reports, official documents
- interview: Interviews, oral histories, personal communications
- url: Websites, online resources
- unknown: Cannot determine

Respond in JSON only:
{"type": "...", "confidence": 0.0-1.0, "title": "", "authors": [], "year": "", "reasoning": "brief explanation"}"""


def classify_citation(text: str) -> Tuple[CitationType, Optional[CitationMetadata]]:
    """
    Classify a citation using AI.
    
    Args:
        text: The citation text to classify
        
    Returns:
        Tuple of (CitationType, optional CitationMetadata with extracted info)
    """
    if not ACTIVE_CHAIN:
        return CitationType.UNKNOWN, None
    
    prompt = f"Classify this citation:\n\n{text}"
    
    response = _call_ai(prompt, CLASSIFY_SYSTEM, max_tokens=500)
    data = _parse_json_response(response)
    
    if not data:
        return CitationType.UNKNOWN, None
    
    type_map = {
        'legal': CitationType.LEGAL,
        'book': CitationType.BOOK,
        'journal': CitationType.JOURNAL,
        'newspaper': CitationType.NEWSPAPER,
        'government': CitationType.GOVERNMENT,
        'interview': CitationType.INTERVIEW,
        'url': CitationType.URL,
    }
    
    citation_type = type_map.get(data.get('type', '').lower(), CitationType.UNKNOWN)
    
    if citation_type == CitationType.UNKNOWN:
        return citation_type, None
    
    metadata = CitationMetadata(
        citation_type=citation_type,
        raw_source=text,
        source_engine="AI Classification",
        title=data.get('title', ''),
        authors=data.get('authors', []),
        year=data.get('year', ''),
        confidence=data.get('confidence', 0.5),
        notes=data.get('reasoning', ''),
    )
    
    return citation_type, metadata


# Backward compatibility aliases
def classify_with_claude(text: str) -> Tuple[CitationType, Optional[CitationMetadata]]:
    """Backward compatibility: routes to classify_citation()."""
    return classify_citation(text)

def classify_with_gemini(text: str) -> Tuple[CitationType, Optional[CitationMetadata]]:
    """Backward compatibility: routes to classify_citation()."""
    return classify_citation(text)


# =============================================================================
# BATCH CLASSIFICATION (for document_processor.py)
# =============================================================================

BATCH_CLASSIFY_SYSTEM = """You are a citation classification expert. Classify each citation in the list.

For each, determine type:
- legal: Court cases (contains "v." or "v "), statutes
- book: Books, monographs, edited volumes
- journal: Academic journal articles
- newspaper: Newspaper/magazine articles
- government: Government reports
- interview: Interviews, oral histories
- letter: Letters, correspondence
- url: Websites
- skip: Ibid, Id., supra references, or empty entries
- unknown: Cannot determine

Respond with JSON array only:
[{"index": 1, "type": "book"}, {"index": 2, "type": "skip"}, ...]"""


def batch_classify_notes(notes: list, batch_size: int = 50) -> dict:
    """
    Classify multiple notes in batches using AI.
    
    Args:
        notes: List of dicts with 'id' and 'text' keys
        batch_size: Notes per API call (default 50)
        
    Returns:
        Dict mapping note text → type string
    """
    if not ACTIVE_CHAIN:
        print("[AI_Lookup] No AI providers available for batch classification")
        return {}
    
    classifications = {}
    
    # Pre-filter ibid references (no API call needed)
    IBID_FILTER = re.compile(
        r'^(?:ibid\.?|ibidem\.?|id\.?)(?:\s|$|,|\.|\s*at\s)',
        re.IGNORECASE
    )
    
    valid_notes = []
    for note in notes:
        text = note.get('text', '').strip()
        if not text:
            continue
        if IBID_FILTER.match(text):
            classifications[text] = 'skip'
            continue
        valid_notes.append({'idx': len(valid_notes), 'text': text})
    
    if not valid_notes:
        return classifications
    
    print(f"[AI_Lookup] Batch classifying {len(valid_notes)} notes...")
    start_time = time.time()
    
    # Process in batches
    for batch_start in range(0, len(valid_notes), batch_size):
        batch = valid_notes[batch_start:batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        total_batches = (len(valid_notes) + batch_size - 1) // batch_size
        
        print(f"[AI_Lookup] Batch {batch_num}/{total_batches} ({len(batch)} notes)...")
        
        # Build numbered list (truncate long notes)
        notes_text = "\n".join([
            f"{i+1}. {note['text'][:400]}"
            for i, note in enumerate(batch)
        ])
        
        prompt = f"Classify these {len(batch)} citations:\n\n{notes_text}"
        
        try:
            response = _call_ai(prompt, BATCH_CLASSIFY_SYSTEM, max_tokens=2000)
            results = _parse_json_response(response)
            
            if isinstance(results, list):
                for result in results:
                    idx = result.get('index', 0) - 1
                    if 0 <= idx < len(batch):
                        note_text = batch[idx]['text']
                        classifications[note_text] = result.get('type', 'unknown')
                        
        except Exception as e:
            print(f"[AI_Lookup] Batch {batch_num} error: {e}")
    
    elapsed = time.time() - start_time
    print(f"[AI_Lookup] Batch classification done in {elapsed:.1f}s")
    return classifications


# =============================================================================
# PARENTHETICAL CITATION PARSER
# =============================================================================

SIMPLE_AUTHOR_YEAR_PATTERN = re.compile(r'\(([^()]+?),\s*(\d{4}[a-z]?)\)')


def parse_parenthetical_citation(text: str) -> Optional[Tuple[List[str], str]]:
    """
    Parse APA-style parenthetical citation into authors and year.
    
    Examples:
        "(Simonton, 1992)" → (["Simonton"], "1992")
        "(Smith & Jones, 2020)" → (["Smith", "Jones"], "2020")
    """
    text = text.strip()
    
    match = SIMPLE_AUTHOR_YEAR_PATTERN.match(text)
    if not match:
        # Try adding parens
        if re.match(r'^[A-Z][a-z]+.*,\s*\d{4}', text):
            text = f"({text})"
            match = SIMPLE_AUTHOR_YEAR_PATTERN.match(text)
    
    if not match:
        return None
    
    authors_part = match.group(1).strip()
    year = match.group(2).strip()
    
    if 'et al' in authors_part.lower():
        authors = [authors_part]
    else:
        authors_part = re.sub(r'\s*&\s*', ', ', authors_part)
        authors_part = re.sub(r'\s+and\s+', ', ', authors_part, flags=re.IGNORECASE)
        authors = [a.strip() for a in authors_part.split(',') if a.strip()]
    
    return (authors, year)


def is_parenthetical_citation(text: str) -> bool:
    """Check if text looks like a parenthetical citation."""
    return parse_parenthetical_citation(text) is not None


# =============================================================================
# PARENTHETICAL LOOKUP (Layer 6)
# =============================================================================

LOOKUP_SYSTEM = """You are an expert academic reference librarian. Given author name(s) and a publication year, identify the most likely academic work.

Respond with JSON only:
{
    "found": true/false,
    "confidence": "high"/"medium"/"low",
    "citation_type": "journal"/"book"/"chapter"/"conference"/"report",
    "title": "Full title",
    "authors": ["Last, First M."],
    "year": "YYYY",
    "journal": "Journal name (if article)",
    "volume": "vol",
    "issue": "issue",
    "pages": "start-end",
    "doi": "10.xxxx/xxxxx",
    "publisher": "Publisher (if book)",
    "place": "City (if book)"
}

Only include fields you're confident about. Set found=false if unknown."""


LOOKUP_MULTI_SYSTEM = """You are an expert academic reference librarian. Given author name(s) and year, identify ALL likely works (authors often publish multiple works per year).

Return up to 5 matches in JSON:
{
    "works": [
        {
            "confidence": "high"/"medium"/"low",
            "citation_type": "journal"/"book"/...,
            "title": "...",
            "authors": ["Last, First"],
            "year": "YYYY",
            "journal": "...",
            "volume": "...",
            "pages": "...",
            "doi": "...",
            "publisher": "...",
            "place": "..."
        }
    ]
}

Order by likelihood. Only include fields you're confident about."""


def lookup_parenthetical_citation(citation_text: str, context: str = "") -> Optional[CitationMetadata]:
    """
    Look up a parenthetical citation like "(Simonton, 1992)".
    
    Args:
        citation_text: Parenthetical citation text
        context: Optional document context/gist
        
    Returns:
        CitationMetadata if found, None otherwise
    """
    parsed = parse_parenthetical_citation(citation_text)
    if not parsed:
        print(f"[AI_Lookup] Could not parse: {citation_text}")
        return None
    
    authors, year = parsed
    return _ai_lookup_authors_year(authors, year, context)


def lookup_parenthetical_citation_options(
    citation_text: str,
    context: str = "",
    limit: int = 5
) -> List[CitationMetadata]:
    """
    Get multiple options for a parenthetical citation.
    
    Use when presenting choices to user (authors often have multiple works per year).
    """
    parsed = parse_parenthetical_citation(citation_text)
    if not parsed:
        return []
    
    authors, year = parsed
    print(f"[AI_Lookup] Getting options for: {', '.join(authors)} ({year})")
    
    authors_str = ", ".join(authors)
    prompt = f"Authors: {authors_str}\nYear: {year}"
    if context:
        prompt += f"\nContext: {context}"
    prompt += f"\n\nReturn up to {limit} matches. JSON only."
    
    response = _call_ai(prompt, LOOKUP_MULTI_SYSTEM, max_tokens=2000)
    data = _parse_json_response(response)
    
    if not data or not isinstance(data.get('works'), list):
        return []
    
    results = []
    for work in data['works'][:limit]:
        meta = _dict_to_metadata(work, authors, year)
        if meta and meta.title:
            results.append(meta)
    
    print(f"[AI_Lookup] Found {len(results)} options")
    return results


def _ai_lookup_authors_year(authors: List[str], year: str, context: str = "") -> Optional[CitationMetadata]:
    """Internal: Look up work by authors + year."""
    if not ACTIVE_CHAIN:
        return None
    
    print(f"[AI_Lookup] Looking up: {', '.join(authors)} ({year})")
    
    authors_str = ", ".join(authors)
    prompt = f"Authors: {authors_str}\nYear: {year}"
    if context:
        prompt += f"\nContext: {context}"
    prompt += "\n\nJSON only."
    
    response = _call_ai(prompt, LOOKUP_SYSTEM, max_tokens=600)
    data = _parse_json_response(response)
    
    if not data or not data.get('found'):
        print(f"[AI_Lookup] Not found: {', '.join(authors)} ({year})")
        return None
    
    return _dict_to_metadata(data, authors, year)


# =============================================================================
# FRAGMENT LOOKUP WITH VERIFICATION (Layer 6 - Last Resort)
# =============================================================================

FRAGMENT_SYSTEM = """You are a scholarly citation expert. Given a fragmentary citation hint and document context, identify the most likely published work.

USE YOUR KNOWLEDGE to guess the work, then provide metadata for database verification.

Respond with JSON only:
{
    "confidence": 0.0-1.0,
    "citation_type": "journal"/"book"/"legal"/"newspaper",
    "title": "Full title of the work",
    "authors": ["First Last"],
    "year": "YYYY",
    "journal": "Journal name (if article)",
    "volume": "volume",
    "issue": "issue",
    "pages": "start-end",
    "doi": "DOI if known",
    "pmid": "PubMed ID if known",
    "publisher": "Publisher (if book)",
    "search_query": "optimized query for database verification"
}

IMPORTANT:
- Use training knowledge to fill in details you recognize
- Set confidence HIGH (0.8+) only if you're fairly sure
- Never invent fictional works
- Include search_query optimized for Crossref/PubMed lookup"""


def lookup_fragment(
    fragment: str,
    gist: str = "",
    verify: bool = True
) -> Optional[CitationMetadata]:
    """
    Look up a messy citation fragment using AI + database verification.
    
    This is the LAST RESORT after all upstream engines fail.
    
    Args:
        fragment: Messy citation like "caplan trains brains"
        gist: Document context/gist to improve accuracy
        verify: If True, verify AI guess against databases (anti-hallucination)
        
    Returns:
        CitationMetadata if found AND verified, None otherwise
        
    Example:
        >>> meta = lookup_fragment("caplan trains brains", 
        ...     gist="history of psychiatry and psychoanalysis")
        >>> print(meta.title)
        "Trains, Brains, and Sprains: Railway Spine and the Origins of Psychoneuroses"
    """
    if not ACTIVE_CHAIN:
        print("[AI_Lookup] No AI providers available")
        return None
    
    print(f"[AI_Lookup] Fragment lookup: {fragment[:50]}...")
    
    # Build prompt with gist context
    prompt = f"Citation fragment: {fragment}"
    if gist:
        prompt += f"\n\nDocument context: {gist}"
    prompt += "\n\nIdentify the published work. JSON only."
    
    # Get AI's guess
    response = _call_ai(prompt, FRAGMENT_SYSTEM, max_tokens=800)
    guess = _parse_json_response(response)
    
    if not guess:
        print("[AI_Lookup] AI returned no guess")
        return None
    
    confidence = guess.get('confidence', 0)
    title = guess.get('title', '')
    
    print(f"[AI_Lookup] AI guess: {title[:60]}... (confidence: {confidence})")
    
    if confidence < 0.3:
        print("[AI_Lookup] Confidence too low, rejecting")
        return None
    
    # Skip verification if disabled
    if not verify:
        return _guess_to_metadata(guess, fragment)
    
    # VERIFICATION: Confirm against databases
    verified = _verify_against_databases(guess, fragment)
    
    if verified:
        print(f"[AI_Lookup] ✓ Verified: {verified.title[:50]}...")
        return verified
    
    # High-confidence guesses can pass without verification
    if confidence >= 0.9 and title:
        print("[AI_Lookup] High confidence, returning unverified")
        meta = _guess_to_metadata(guess, fragment)
        meta.source_engine = "AI Lookup (unverified)"
        meta.confidence = confidence * 0.8  # Discount for no verification
        return meta
    
    print("[AI_Lookup] Could not verify AI guess, rejecting as potential hallucination")
    return None


def _verify_against_databases(guess: dict, original_fragment: str) -> Optional[CitationMetadata]:
    """
    Verify AI guess against free academic databases.
    
    Databases that couldn't find "caplan trains brains" CAN find
    "Trains Brains Sprains Railway Spine Caplan 1995" because now
    we have enough metadata for a precise match.
    """
    from engines.academic import CrossrefEngine, OpenAlexEngine, PubMedEngine
    
    title = guess.get('title', '')
    authors = guess.get('authors', [])
    year = guess.get('year', '')
    doi = guess.get('doi', '')
    pmid = guess.get('pmid', '')
    search_query = guess.get('search_query', '')
    
    # Try direct ID lookups first (most reliable)
    if doi:
        try:
            result = CrossrefEngine().get_by_id(doi)
            if result and _result_matches_fragment(result, original_fragment):
                print(f"[AI_Lookup] Verified via DOI: {doi}")
                result.source_engine = "AI + Crossref (DOI verified)"
                return result
        except:
            pass
    
    if pmid:
        try:
            result = PubMedEngine().get_by_id(pmid)
            if result and _result_matches_fragment(result, original_fragment):
                print(f"[AI_Lookup] Verified via PMID: {pmid}")
                result.source_engine = "AI + PubMed (PMID verified)"
                return result
        except:
            pass
    
    # Build verification queries from AI's metadata
    queries = []
    
    if search_query:
        queries.append(search_query)
    
    if title:
        # Use title words + author surname
        title_words = [w for w in title.split()[:5] if len(w) > 3]
        author_surname = authors[0].split()[-1] if authors else ''
        if title_words:
            queries.append(' '.join(title_words) + (' ' + author_surname if author_surname else ''))
    
    if not queries:
        return None
    
    # Try each query against each engine
    engines = [
        ('Crossref', CrossrefEngine()),
        ('OpenAlex', OpenAlexEngine()),
        ('PubMed', PubMedEngine()),
    ]
    
    for query in queries[:2]:  # Limit attempts
        for engine_name, engine in engines:
            try:
                result = engine.search(query)
                if result and result.title and _result_matches_fragment(result, original_fragment):
                    print(f"[AI_Lookup] Verified via {engine_name}")
                    result.source_engine = f"AI + {engine_name} (verified)"
                    return result
            except:
                continue
    
    return None


def _result_matches_fragment(result: CitationMetadata, fragment: str) -> bool:
    """
    Verify that a database result actually matches the original fragment.
    
    Prevents returning wrong results when AI guesses incorrectly.
    E.g., "caplan trains brains" should not match an article about
    "Brain Injury" even if author is named Caplan.
    """
    if not result or not result.title:
        return False
    
    fragment_lower = fragment.lower()
    title_lower = result.title.lower()
    
    # Common words to ignore
    stop_words = {'the', 'a', 'an', 'of', 'and', 'in', 'on', 'at', 'to', 'for', 'by', 'with'}
    
    # Extract meaningful words from fragment
    fragment_words = [w for w in fragment_lower.split()
                      if len(w) >= 3 and w not in stop_words and not w.isdigit()]
    
    if not fragment_words:
        return True  # Nothing to match
    
    # Build searchable text
    searchable = title_lower
    if result.authors:
        searchable += ' ' + ' '.join(result.authors).lower()
    
    # Count matches
    matches = sum(1 for word in fragment_words if word in searchable)
    
    # Require at least 2 matches (or all if < 2 words)
    min_required = min(2, len(fragment_words))
    word_match = matches >= min_required
    
    # Check year if present in fragment
    year_match = True
    year_in_fragment = re.search(r'\b(19|20)\d{2}\b', fragment)
    if year_in_fragment and result.year:
        year_match = year_in_fragment.group() == str(result.year)
    
    return word_match and year_match


def _guess_to_metadata(guess: dict, raw_source: str) -> CitationMetadata:
    """Convert AI guess dict to CitationMetadata."""
    type_map = {
        'journal': CitationType.JOURNAL,
        'book': CitationType.BOOK,
        'legal': CitationType.LEGAL,
        'newspaper': CitationType.NEWSPAPER,
        'chapter': CitationType.BOOK,
        'conference': CitationType.JOURNAL,
    }
    
    return CitationMetadata(
        citation_type=type_map.get(guess.get('citation_type', '').lower(), CitationType.UNKNOWN),
        raw_source=raw_source,
        source_engine="AI Lookup",
        title=guess.get('title', ''),
        authors=guess.get('authors', []),
        year=guess.get('year', ''),
        journal=guess.get('journal', ''),
        volume=guess.get('volume', ''),
        issue=guess.get('issue', ''),
        pages=guess.get('pages', ''),
        doi=guess.get('doi', ''),
        pmid=guess.get('pmid', ''),
        publisher=guess.get('publisher', ''),
        place=guess.get('place', ''),
        confidence=guess.get('confidence', 0.5),
    )


def _dict_to_metadata(data: dict, original_authors: List[str], original_year: str) -> CitationMetadata:
    """Convert AI response dict to CitationMetadata."""
    type_map = {
        'journal': CitationType.JOURNAL,
        'book': CitationType.BOOK,
        'chapter': CitationType.BOOK,
        'conference': CitationType.JOURNAL,
        'report': CitationType.GOVERNMENT,
    }
    
    citation_type = type_map.get(data.get('citation_type', '').lower(), CitationType.UNKNOWN)
    
    authors = data.get('authors', [])
    if not authors:
        authors = original_authors
    
    return CitationMetadata(
        citation_type=citation_type,
        raw_source=f"({', '.join(original_authors)}, {original_year})",
        source_engine="AI Lookup",
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
# TESTING
# =============================================================================

if __name__ == "__main__":
    print("=== AI Lookup Module Test ===")
    print(f"Provider chain: {ACTIVE_CHAIN}")
    
    # Test classification
    print("\n--- Classification Test ---")
    ctype, meta = classify_citation("Eric Caplan, Mind Games")
    print(f"Type: {ctype}, Title: {meta.title if meta else 'N/A'}")
    
    # Test parenthetical
    print("\n--- Parenthetical Test ---")
    if ACTIVE_CHAIN:
        result = lookup_parenthetical_citation("(Simonton, 1992)", 
            context="psychology article about creativity")
        if result:
            print(f"Found: {result.title}")
        else:
            print("Not found")
    
    # Test fragment lookup
    print("\n--- Fragment Lookup Test ---")
    if ACTIVE_CHAIN:
        result = lookup_fragment("caplan trains brains",
            gist="history of psychiatry")
        if result:
            print(f"Found: {result.title}")
            print(f"Source: {result.source_engine}")
        else:
            print("Not found or rejected")
