"""
citeflex/claude_router.py

Claude AI-powered citation type detection and classification.
Used as the primary AI router for ambiguous citation queries.

Version History:
    2025-12-06: Initial production version with multi-option support
    2025-12-07: Added guess_citation() and guess_and_search() for Claude-first lookup
    
Usage:
    from claude_router import classify_with_claude, get_citation_options, guess_and_search
    
    # Single classification (for unified_router.py)
    citation_type, metadata = classify_with_claude("Eric Caplan mind games")
    
    # Multiple options (returns up to 5 candidates for UI selection)
    options = get_citation_options("Eric Caplan mind games")
    
    # Claude-first guess then API verification (NEW)
    result = guess_and_search("Eric Caplan trains brains")
"""

import os
import re
import json
import requests
from typing import Optional, Tuple, List
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic

from models import CitationType, CitationMetadata
from config import DEFAULT_TIMEOUT

# =============================================================================
# CONFIGURATION
# =============================================================================

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
SERPAPI_KEY = os.environ.get('SERPAPI_KEY', '')
CLAUDE_MODEL = "claude-opus-4-20250514"

# =============================================================================
# CLAUDE CLIENT
# =============================================================================

def _get_client():
    """Get Anthropic client (lazy initialization)."""
    if not ANTHROPIC_API_KEY:
        return None
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# =============================================================================
# SINGLE CLASSIFICATION (for unified_router.py compatibility)
# =============================================================================

CLASSIFY_PROMPT = """You are a citation classification expert. Analyze the input and classify it.

Classify as one of:
- legal: Court cases, statutes, legal documents (contains "v." or "v ")
- book: Books, monographs
- journal: Academic journal articles, peer-reviewed papers
- newspaper: Newspaper/magazine articles
- government: Government reports, official documents
- medical: Medical/clinical content
- interview: Interviews, oral histories
- url: Websites, online resources
- unknown: Cannot determine

Respond in JSON only:
{"type": "...", "confidence": 0.0-1.0, "title": "", "authors": [], "year": "", "reasoning": "brief explanation"}"""


class ClaudeRouter:
    """Uses Claude to classify ambiguous citation queries."""
    
    def __init__(self, api_key: Optional[str] = None, timeout: int = None):
        self.api_key = api_key or ANTHROPIC_API_KEY
        self.timeout = timeout or DEFAULT_TIMEOUT
        self.client = None
        if self.api_key:
            self.client = anthropic.Anthropic(api_key=self.api_key)
    
    def classify(self, text: str) -> Tuple[CitationType, Optional[CitationMetadata]]:
        """Classify a citation query and return type + metadata."""
        if not self.client:
            return CitationType.UNKNOWN, None
        
        try:
            response = self.client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=500,
                system=CLASSIFY_PROMPT,
                messages=[{"role": "user", "content": f"Classify this citation:\n\n{text}"}]
            )
            
            response_text = response.content[0].text
            return self._parse_response(response_text, text)
            
        except anthropic.RateLimitError:
            print("[ClaudeRouter] Rate limited")
            return CitationType.UNKNOWN, None
        except anthropic.AuthenticationError:
            print("[ClaudeRouter] Authentication failed - check ANTHROPIC_API_KEY")
            return CitationType.UNKNOWN, None
        except Exception as e:
            print(f"[ClaudeRouter] Error: {e}")
            return CitationType.UNKNOWN, None
    
    def _parse_response(self, response_text: str, original: str) -> Tuple[CitationType, Optional[CitationMetadata]]:
        """Parse Claude's JSON response."""
        try:
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if not json_match:
                return CitationType.UNKNOWN, None
            
            data = json.loads(json_match.group())
            
            type_map = {
                'legal': CitationType.LEGAL,
                'book': CitationType.BOOK,
                'journal': CitationType.JOURNAL,
                'newspaper': CitationType.NEWSPAPER,
                'government': CitationType.GOVERNMENT,
                'medical': CitationType.MEDICAL,
                'interview': CitationType.INTERVIEW,
                'url': CitationType.URL,
            }
            
            citation_type = type_map.get(data.get('type', '').lower(), CitationType.UNKNOWN)
            
            if citation_type == CitationType.UNKNOWN:
                return citation_type, None
            
            metadata = CitationMetadata(
                citation_type=citation_type,
                raw_source=original,
                source_engine="Claude Router",
                title=data.get('title', ''),
                authors=data.get('authors', []),
                year=data.get('year'),
                confidence=data.get('confidence', 0.5),
                notes=data.get('reasoning', ''),
            )
            
            return citation_type, metadata
            
        except json.JSONDecodeError:
            return CitationType.UNKNOWN, None
        except Exception:
            return CitationType.UNKNOWN, None


def classify_with_claude(text: str) -> Tuple[CitationType, Optional[CitationMetadata]]:
    """Convenience function for unified_router.py compatibility."""
    return ClaudeRouter().classify(text)


# =============================================================================
# MULTI-OPTION SEARCH (for advanced UI)
# =============================================================================

IDENTIFY_PROMPT = """You are a citation identification expert. Given a messy, incomplete, or fragmentary reference, identify what it MIGHT be.

Respond in JSON only:
{
    "possible_types": ["book", "journal", "legal"],
    "search_queries": ["query1", "query2"],
    "case_name": "for legal: the case name if applicable",
    "authors": ["possible author names"],
    "title_keywords": ["key words from title"],
    "reasoning": "brief explanation"
}

Generate 2-3 search queries optimized for different APIs (books, journals, legal).
Do NOT invent specific details - just extract what's in the input."""


# =============================================================================
# CLAUDE FIRST GUESS (use Claude's knowledge to predict full citation)
# =============================================================================

GUESS_PROMPT = """You are a scholarly citation expert with comprehensive knowledge of academic literature, books, legal cases, and published works.

Given a fragmentary or incomplete citation hint, USE YOUR KNOWLEDGE to guess the most likely published work being referenced.

Respond in JSON only:
{
    "confidence": 0.0-1.0,
    "type": "journal|book|legal|newspaper|interview|government|unknown",
    "title": "full title of the work",
    "authors": ["First Last", "First Last"],
    "year": "YYYY",
    "journal": "journal name if applicable",
    "volume": "volume if known",
    "issue": "issue if known",
    "pages": "page range if known",
    "publisher": "publisher if book",
    "case_citation": "full legal citation if case",
    "pmid": "PubMed ID if you know it",
    "doi": "DOI if you know it",
    "search_query": "optimized query to verify in databases"
}

IMPORTANT:
- USE your training knowledge to fill in details you recognize
- Set confidence HIGH (0.8+) if you're fairly sure this is a real, published work
- Set confidence LOW (<0.5) if you're guessing or unsure
- For author names, use the format they publish under
- If you don't recognize the work at all, set type to "unknown" and confidence to 0.0
- Never invent fictional works - only guess works you believe actually exist"""


# =============================================================================
# WEB SEARCH FOR CITATION VERIFICATION
# =============================================================================

def _web_search_citation(fragment: str) -> Optional[dict]:
    """
    Search the web for a citation fragment and extract citation info.
    
    Uses SERPAPI to search Google, then has Claude parse the results
    to extract structured citation data.
    
    Args:
        fragment: Citation fragment like "Caplan trains brains 1995"
        
    Returns:
        Dict with citation info if found, None otherwise
    """
    if not SERPAPI_KEY:
        print("[WebSearch] No SERPAPI_KEY configured")
        return None
    
    try:
        # Search Google for the citation (no quotes - allow keyword matching)
        search_query = f'{fragment} citation OR article OR journal'
        
        url = "https://serpapi.com/search"
        params = {
            "q": search_query,
            "api_key": SERPAPI_KEY,
            "engine": "google",
            "num": 5
        }
        
        print(f"[WebSearch] Searching: {fragment[:50]}...")
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code != 200:
            print(f"[WebSearch] API error: {response.status_code}")
            return None
        
        data = response.json()
        organic_results = data.get("organic_results", [])
        
        if not organic_results:
            print("[WebSearch] No results found")
            return None
        
        # Collect snippets and titles from search results
        search_context = []
        for r in organic_results[:5]:
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            link = r.get("link", "")
            search_context.append(f"Title: {title}\nSnippet: {snippet}\nURL: {link}")
        
        # Have Claude parse the search results to extract citation
        return _parse_search_results_with_claude(fragment, search_context)
        
    except Exception as e:
        print(f"[WebSearch] Error: {e}")
        return None


def _parse_search_results_with_claude(fragment: str, search_results: list) -> Optional[dict]:
    """
    Use Claude to parse web search results and extract citation info.
    """
    client = _get_client()
    if not client:
        return None
    
    parse_prompt = """You are extracting citation information from web search results.

Given the original search query and web results, identify the most likely academic citation.

Respond in JSON only:
{
    "confidence": 0.0-1.0,
    "type": "journal|book|legal|newspaper|unknown",
    "title": "full title of the work",
    "authors": ["First Last"],
    "year": "YYYY",
    "journal": "journal name if applicable",
    "volume": "volume if found",
    "issue": "issue if found",
    "pages": "page range if found",
    "pmid": "PubMed ID if found",
    "doi": "DOI if found"
}

Set confidence HIGH (0.8+) if the search results clearly identify a specific published work.
Set confidence LOW (<0.5) if results are ambiguous or don't match the query."""

    results_text = "\n\n---\n\n".join(search_results)
    
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=600,
            system=parse_prompt,
            messages=[{
                "role": "user", 
                "content": f"Original query: {fragment}\n\nSearch results:\n{results_text}"
            }]
        )
        
        text = response.content[0].text.strip()
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            result = json.loads(json_match.group())
            print(f"[WebSearch] Parsed: {result.get('title', 'unknown')} (confidence: {result.get('confidence', 0)})")
            return result
            
    except Exception as e:
        print(f"[WebSearch] Parse error: {e}")
    
    return None


def guess_citation(fragment: str) -> dict:
    """
    Ask Claude to guess the full citation from a fragment.
    
    Uses Claude's training knowledge to predict what published work
    is being referenced, then returns structured data for API verification.
    
    Args:
        fragment: Messy citation fragment like "Eric Caplan trains brains"
        
    Returns:
        Dict with guessed citation details and confidence score
    """
    client = _get_client()
    if not client:
        return {"confidence": 0.0, "type": "unknown"}
    
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=600,
            system=GUESS_PROMPT,
            messages=[{"role": "user", "content": f"What published work is this referencing?\n\n{fragment}"}]
        )
        text = response.content[0].text.strip()
        
        # Parse JSON response
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            result = json.loads(json_match.group())
            result['raw_fragment'] = fragment
            print(f"[ClaudeGuess] Guessed: {result.get('title', 'unknown')} (confidence: {result.get('confidence', 0)})")
            return result
            
    except Exception as e:
        print(f"[ClaudeGuess] Error: {e}")
    
    return {"confidence": 0.0, "type": "unknown", "raw_fragment": fragment}


def guess_and_search(fragment: str) -> Optional[CitationMetadata]:
    """
    Two-step process: Claude guesses, then APIs verify.
    
    1. Ask Claude to guess the full citation from its knowledge
    2. Use that guess to construct targeted API queries
    3. Return verified result from APIs (or Claude's guess if confident)
    
    Args:
        fragment: Messy citation fragment
        
    Returns:
        CitationMetadata if found/verified, None otherwise
    """
    from engines.academic import CrossrefEngine, OpenAlexEngine, PubMedEngine
    
    # Step 1: Get Claude's guess
    guess = guess_citation(fragment)
    
    if guess.get('confidence', 0) < 0.3:
        print(f"[ClaudeGuess] Low confidence ({guess.get('confidence')}), skipping")
        return None
    
    # Step 2: Build targeted search queries from guess
    title = guess.get('title', '')
    authors = guess.get('authors', [])
    year = guess.get('year', '')
    journal = guess.get('journal', '')
    pmid = guess.get('pmid', '')
    doi = guess.get('doi', '')
    
    # Try direct lookups first (most reliable)
    # BUT verify the result actually matches the original fragment
    if doi:
        try:
            result = CrossrefEngine().get_by_id(doi)
            if result and result.title:
                # Verify result matches ORIGINAL fragment, not just Claude's guess
                if _fragment_matches_result(fragment, result):
                    print(f"[ClaudeGuess] Verified via DOI: {doi}")
                    result.source_engine = "Claude + Crossref (DOI)"
                    return result
                else:
                    print(f"[ClaudeGuess] DOI result doesn't match fragment: {result.title[:50]}...")
        except:
            pass
    
    if pmid:
        try:
            result = PubMedEngine().get_by_id(pmid)
            if result and result.title:
                # Verify result matches ORIGINAL fragment
                if _fragment_matches_result(fragment, result):
                    print(f"[ClaudeGuess] Verified via PMID: {pmid}")
                    result.source_engine = "Claude + PubMed (PMID)"
                    return result
                else:
                    print(f"[ClaudeGuess] PMID result doesn't match fragment: {result.title[:50]}...")
        except:
            pass
    
    # Build smart queries from guessed metadata
    queries_to_try = []
    
    # Query 1: Author + key title words
    if authors and title:
        # Get last name of first author
        first_author = authors[0].split()[-1] if authors else ''
        # Get first few significant words from title
        title_words = [w for w in title.split()[:4] if len(w) > 3]
        if first_author and title_words:
            queries_to_try.append(f"{first_author} {' '.join(title_words)}")
    
    # Query 2: Exact title (for OpenAlex which handles this well)
    if title:
        queries_to_try.append(title)
    
    # Query 3: Claude's suggested search query
    if guess.get('search_query'):
        queries_to_try.append(guess['search_query'])
    
    # Step 3: Try APIs with constructed queries
    engines = [
        ('OpenAlex', OpenAlexEngine()),
        ('Crossref', CrossrefEngine()),
        ('PubMed', PubMedEngine()),
    ]
    
    for query in queries_to_try[:3]:  # Limit attempts
        for engine_name, engine in engines:
            try:
                result = engine.search(query)
                if result and result.title:
                    # Verify against ORIGINAL fragment, not Claude's guess
                    if _fragment_matches_result(fragment, result):
                        print(f"[ClaudeGuess] Verified via {engine_name}: {result.title[:50]}...")
                        result.source_engine = f"Claude + {engine_name}"
                        return result
            except Exception as e:
                continue
    
    # Step 4: Web search fallback - search the web and parse results
    print(f"[ClaudeGuess] API verification failed, trying web search...")
    web_result = _web_search_citation(fragment)
    
    if web_result and web_result.get('confidence', 0) >= 0.7:
        web_title = web_result.get('title', '')
        web_doi = web_result.get('doi', '')
        web_pmid = web_result.get('pmid', '')
        
        # Try to verify web search result via APIs
        if web_doi:
            try:
                result = CrossrefEngine().get_by_id(web_doi)
                if result:
                    print(f"[WebSearch] Verified via DOI: {web_doi}")
                    result.source_engine = "Web Search + Crossref (DOI)"
                    return result
            except:
                pass
        
        if web_pmid:
            try:
                result = PubMedEngine().get_by_id(web_pmid)
                if result:
                    print(f"[WebSearch] Verified via PMID: {web_pmid}")
                    result.source_engine = "Web Search + PubMed (PMID)"
                    return result
            except:
                pass
        
        # Try searching with the web-derived title
        if web_title:
            for engine_name, engine in engines:
                try:
                    result = engine.search(web_title)
                    if result and result.title:
                        # Verify against ORIGINAL fragment
                        if _fragment_matches_result(fragment, result):
                            print(f"[WebSearch] Verified via {engine_name}: {result.title[:50]}...")
                            result.source_engine = f"Web Search + {engine_name}"
                            return result
                except:
                    continue
        
        # Return web search result if high confidence even without API verification
        # But only if it matches the original fragment
        if web_result.get('confidence', 0) >= 0.85 and web_title:
            # Build a temp metadata to check match
            temp_meta = CitationMetadata(
                citation_type=CitationType.UNKNOWN,
                raw_source=fragment,
                title=web_title,
                authors=web_result.get('authors', []),
                year=web_result.get('year', '')
            )
            
            if _fragment_matches_result(fragment, temp_meta):
                print(f"[WebSearch] Returning high-confidence web result (unverified)")
                
                type_map = {
                    'journal': CitationType.JOURNAL,
                    'book': CitationType.BOOK,
                    'legal': CitationType.LEGAL,
                    'newspaper': CitationType.NEWSPAPER,
                }
                
                return CitationMetadata(
                    citation_type=type_map.get(web_result.get('type', ''), CitationType.UNKNOWN),
                    raw_source=fragment,
                    source_engine="Web Search (unverified)",
                    title=web_title,
                    authors=web_result.get('authors', []),
                    year=web_result.get('year', ''),
                    journal=web_result.get('journal', ''),
                    volume=web_result.get('volume', ''),
                    issue=web_result.get('issue', ''),
                    pages=web_result.get('pages', ''),
                    doi=web_doi,
                    pmid=web_pmid,
                    confidence=web_result.get('confidence', 0.5),
                )
    
    return None


def _titles_match(title1: str, title2: str, threshold: float = 0.6) -> bool:
    """Check if two titles are similar enough to be the same work."""
    if not title1 or not title2:
        return False
    
    # Normalize
    t1 = title1.lower().strip()
    t2 = title2.lower().strip()
    
    # Exact match
    if t1 == t2:
        return True
    
    # One contains the other (handles subtitles)
    if t1 in t2 or t2 in t1:
        return True
    
    # Word overlap ratio
    words1 = set(t1.split())
    words2 = set(t2.split())
    
    if not words1 or not words2:
        return False
    
    overlap = len(words1 & words2)
    smaller = min(len(words1), len(words2))
    
    return (overlap / smaller) >= threshold


def _fragment_matches_result(fragment: str, result: CitationMetadata) -> bool:
    """
    Verify that an API result actually matches the original search fragment.
    
    This prevents returning wrong results when Claude guesses incorrectly.
    E.g., fragment "Caplan trains brains" should not match an article about
    "Brain Injury Rehabilitation" even if author is named Caplan.
    
    Requirements:
    1. At least 2 meaningful words from fragment must appear in title+authors
    2. If fragment has a year, it must match
    """
    if not result or not result.title:
        return False
    
    fragment_lower = fragment.lower()
    title_lower = result.title.lower()
    
    # Common words to ignore
    stop_words = {'the', 'a', 'an', 'of', 'and', 'in', 'on', 'at', 'to', 'for', 'by', 'with'}
    
    # Extract meaningful words from fragment (3+ chars, not stop words, not year)
    fragment_words = [w for w in fragment_lower.split() 
                      if len(w) >= 3 and w not in stop_words and not w.isdigit()]
    
    if not fragment_words:
        return True  # Nothing to match against
    
    # Build searchable text from result
    searchable = title_lower
    if result.authors:
        searchable += ' ' + ' '.join(result.authors).lower()
    
    # Count how many fragment words appear in searchable text
    matches = sum(1 for word in fragment_words if word in searchable)
    
    # Require at least 2 matches, OR all matches if only 1-2 words
    min_required = min(2, len(fragment_words))
    word_match = matches >= min_required
    
    # Check year if fragment contains one
    year_match = True  # Default to true if no year in fragment
    year_in_fragment = re.search(r'\b(19|20)\d{2}\b', fragment)
    if year_in_fragment and result.year:
        year_match = year_in_fragment.group() == str(result.year)
    
    if word_match and year_match:
        print(f"[FragmentMatch] ✓ Matched {matches}/{len(fragment_words)} words: {fragment_words}")
    else:
        print(f"[FragmentMatch] ✗ Only {matches}/{len(fragment_words)} words matched in '{result.title[:50]}...'")
    
    return word_match and year_match


def _identify_with_claude(messy_note: str) -> dict:
    """Have Claude identify what the citation might be."""
    client = _get_client()
    if not client:
        return {"possible_types": ["unknown"], "search_queries": [messy_note]}
    
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=400,
            system=IDENTIFY_PROMPT,
            messages=[{"role": "user", "content": f"Identify this citation:\n\n{messy_note}"}]
        )
        text = response.content[0].text.strip()
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        print(f"    [Claude error: {e}]")
    return {"possible_types": ["unknown"], "search_queries": [messy_note]}


# =============================================================================
# EXTERNAL API SEARCH FUNCTIONS
# =============================================================================

def _format_authors(authors: list) -> str:
    """Format author list for citation."""
    if not authors:
        return ""
    if len(authors) == 1:
        return authors[0]
    elif len(authors) == 2:
        return f"{authors[0]} and {authors[1]}"
    elif len(authors) <= 3:
        return ", ".join(authors[:-1]) + f", and {authors[-1]}"
    else:
        return f"{authors[0]} et al."


def _get_publisher_place(publisher: str) -> str:
    """Get publication place from publisher name."""
    if not publisher:
        return ""
    
    publisher_places = {
        # === MAJOR TRADE PUBLISHERS (Big 5 and imprints) ===
        "simon & schuster": "New York",
        "simon and schuster": "New York",
        "scribner": "New York",
        "atria": "New York",
        "gallery books": "New York",
        "pocket books": "New York",
        "threshold": "New York",
        
        "penguin": "New York",
        "penguin random house": "New York",
        "penguin books": "New York",
        "penguin press": "New York",
        "viking": "New York",
        "dutton": "New York",
        "putnam": "New York",
        "berkley": "New York",
        "ace books": "New York",
        "plume": "New York",
        "riverhead": "New York",
        
        "random house": "New York",
        "knopf": "New York",
        "alfred a. knopf": "New York",
        "doubleday": "New York",
        "crown": "New York",
        "ballantine": "New York",
        "bantam": "New York",
        "dell": "New York",
        "anchor books": "New York",
        "anchor": "New York",
        "vintage": "New York",
        "vintage books": "New York",
        "pantheon": "New York",
        "modern library": "New York",
        
        "harpercollins": "New York",
        "harper": "New York",
        "harper & row": "New York",
        "harper perennial": "New York",
        "william morrow": "New York",
        "morrow": "New York",
        "avon": "New York",
        "ecco": "New York",
        "harperone": "New York",
        
        "hachette": "New York",
        "little, brown": "Boston",
        "little brown": "Boston",
        "grand central": "New York",
        "twelve": "New York",
        "basic books": "New York",
        "publicaffairs": "New York",
        "public affairs": "New York",
        
        "macmillan": "New York",
        "st. martin's": "New York",
        "st martin's": "New York",
        "st. martin's press": "New York",
        "st martin's press": "New York",
        "st. martins": "New York",
        "henry holt": "New York",
        "holt": "New York",
        "farrar, straus": "New York",
        "farrar straus": "New York",
        "fsg": "New York",
        "hill and wang": "New York",
        "picador": "New York",
        "flatiron": "New York",
        "tor books": "New York",
        "tor": "New York",
        
        # === OTHER MAJOR TRADE ===
        "norton": "New York",
        "w. w. norton": "New York",
        "w.w. norton": "New York",
        "liveright": "New York",
        "bloomsbury": "New York",
        "grove": "New York",
        "grove atlantic": "New York",
        "grove press": "New York",
        "atlantic monthly": "New York",
        "algonquin": "Chapel Hill",
        "workman": "New York",
        "artisan": "New York",
        "abrams": "New York",
        "chronicle books": "San Francisco",
        "ten speed": "Berkeley",
        "clarkson potter": "New York",
        "potter": "New York",
        "rizzoli": "New York",
        "phaidon": "London",
        "taschen": "Cologne",
        "dk": "New York",
        "dorling kindersley": "New York",
        "national geographic": "Washington, DC",
        "smithsonian": "Washington, DC",
        "time life": "New York",
        "reader's digest": "New York",
        "rodale": "New York",
        "hay house": "Carlsbad, CA",
        "sounds true": "Boulder",
        "shambhala": "Boulder",
        "new world library": "Novato, CA",
        "berrett-koehler": "San Francisco",
        "jossey-bass": "San Francisco",
        "wiley": "Hoboken",
        "john wiley": "Hoboken",
        "for dummies": "Hoboken",
        "mcgraw-hill": "New York",
        "mcgraw hill": "New York",
        "pearson": "New York",
        "cengage": "Boston",
        "wadsworth": "Belmont, CA",
        "sage": "Thousand Oaks, CA",
        "sage publications": "Thousand Oaks, CA",
        
        # === UNIVERSITY PRESSES (full names) ===
        "oxford university press": "Oxford",
        "oxford univ press": "Oxford",
        "oup": "Oxford",
        "cambridge university press": "Cambridge",
        "cambridge univ press": "Cambridge",
        "cup": "Cambridge",
        "harvard university press": "Cambridge, MA",
        "harvard univ press": "Cambridge, MA",
        "yale university press": "New Haven",
        "yale univ press": "New Haven",
        "princeton university press": "Princeton",
        "princeton univ press": "Princeton",
        "columbia university press": "New York",
        "columbia univ press": "New York",
        "mit press": "Cambridge, MA",
        "stanford university press": "Stanford",
        "stanford univ press": "Stanford",
        "university of chicago press": "Chicago",
        "univ of chicago press": "Chicago",
        "u of chicago press": "Chicago",
        "chicago university press": "Chicago",
        "university of california press": "Berkeley",
        "univ of california press": "Berkeley",
        "u of california press": "Berkeley",
        "uc press": "Berkeley",
        "california university press": "Berkeley",
        "johns hopkins university press": "Baltimore",
        "johns hopkins univ press": "Baltimore",
        "jhu press": "Baltimore",
        "johns hopkins": "Baltimore",
        "duke university press": "Durham",
        "duke univ press": "Durham",
        "cornell university press": "Ithaca",
        "cornell univ press": "Ithaca",
        "university of pennsylvania press": "Philadelphia",
        "univ of pennsylvania press": "Philadelphia",
        "penn press": "Philadelphia",
        "upenn press": "Philadelphia",
        "university of north carolina press": "Chapel Hill",
        "univ of north carolina press": "Chapel Hill",
        "unc press": "Chapel Hill",
        "university of virginia press": "Charlottesville",
        "univ of virginia press": "Charlottesville",
        "uva press": "Charlottesville",
        "university of texas press": "Austin",
        "univ of texas press": "Austin",
        "ut press": "Austin",
        "university of michigan press": "Ann Arbor",
        "univ of michigan press": "Ann Arbor",
        "michigan university press": "Ann Arbor",
        "university of illinois press": "Urbana",
        "univ of illinois press": "Urbana",
        "illinois university press": "Urbana",
        "university of wisconsin press": "Madison",
        "univ of wisconsin press": "Madison",
        "wisconsin university press": "Madison",
        "university of minnesota press": "Minneapolis",
        "univ of minnesota press": "Minneapolis",
        "minnesota university press": "Minneapolis",
        "indiana university press": "Bloomington",
        "indiana univ press": "Bloomington",
        "iu press": "Bloomington",
        "ohio state university press": "Columbus",
        "ohio state univ press": "Columbus",
        "osu press": "Columbus",
        "penn state university press": "University Park",
        "penn state univ press": "University Park",
        "psu press": "University Park",
        "university of georgia press": "Athens",
        "univ of georgia press": "Athens",
        "uga press": "Athens",
        "louisiana state university press": "Baton Rouge",
        "lsu press": "Baton Rouge",
        "university of washington press": "Seattle",
        "univ of washington press": "Seattle",
        "uw press": "Seattle",
        "university of arizona press": "Tucson",
        "univ of arizona press": "Tucson",
        "university of new mexico press": "Albuquerque",
        "univ of new mexico press": "Albuquerque",
        "unm press": "Albuquerque",
        "university of oklahoma press": "Norman",
        "univ of oklahoma press": "Norman",
        "ou press": "Norman",
        "university of nebraska press": "Lincoln",
        "univ of nebraska press": "Lincoln",
        "nebraska university press": "Lincoln",
        "university of iowa press": "Iowa City",
        "univ of iowa press": "Iowa City",
        "iowa university press": "Iowa City",
        "university of missouri press": "Columbia, MO",
        "univ of missouri press": "Columbia, MO",
        "university of kansas press": "Lawrence",
        "univ of kansas press": "Lawrence",
        "university of colorado press": "Boulder",
        "univ of colorado press": "Boulder",
        "university of utah press": "Salt Lake City",
        "univ of utah press": "Salt Lake City",
        "university of hawaii press": "Honolulu",
        "univ of hawaii press": "Honolulu",
        "university of toronto press": "Toronto",
        "univ of toronto press": "Toronto",
        "utp": "Toronto",
        "mcgill-queen's university press": "Montreal",
        "mcgill-queens university press": "Montreal",
        "mcgill queen's": "Montreal",
        "university of british columbia press": "Vancouver",
        "ubc press": "Vancouver",
        "edinburgh university press": "Edinburgh",
        "manchester university press": "Manchester",
        "university of wales press": "Cardiff",
        "liverpool university press": "Liverpool",
        "bristol university press": "Bristol",
        "amsterdam university press": "Amsterdam",
        "leiden university press": "Leiden",
        
        # === ACADEMIC/SCHOLARLY PUBLISHERS ===
        "routledge": "London",
        "taylor & francis": "London",
        "taylor and francis": "London",
        "crc press": "Boca Raton",
        "brill": "Leiden",
        "elsevier": "Amsterdam",
        "springer": "New York",
        "springer nature": "New York",
        "springer verlag": "Berlin",
        "springer-verlag": "Berlin",
        "palgrave": "London",
        "palgrave macmillan": "London",
        "de gruyter": "Berlin",
        "walter de gruyter": "Berlin",
        "mouton de gruyter": "Berlin",
        "academic press": "San Diego",
        "blackwell": "Oxford",
        "wiley-blackwell": "Oxford",
        "polity": "Cambridge",
        "polity press": "Cambridge",
        "verso": "London",
        "zed books": "London",
        "pluto press": "London",
        "berg": "Oxford",
        "ashgate": "Farnham",
        "edward elgar": "Cheltenham",
        "peter lang": "New York",
        "lexington books": "Lanham",
        "rowman & littlefield": "Lanham",
        "rowman and littlefield": "Lanham",
        "scarecrow": "Lanham",
        "university press of america": "Lanham",
        "upa": "Lanham",
        "continuum": "London",
        "t&t clark": "London",
        "t & t clark": "London",
        "fortress press": "Minneapolis",
        "westminster john knox": "Louisville",
        "wjk": "Louisville",
        "eerdmans": "Grand Rapids",
        "baker academic": "Grand Rapids",
        "intervarsity press": "Downers Grove",
        "ivp": "Downers Grove",
        "zondervan": "Grand Rapids",
        "abingdon": "Nashville",
        "broadman & holman": "Nashville",
        "b&h": "Nashville",
        "moody": "Chicago",
        "crossway": "Wheaton",
        
        # === LAW PUBLISHERS ===
        "west": "St. Paul",
        "west publishing": "St. Paul",
        "thomson west": "St. Paul",
        "lexisnexis": "New York",
        "lexis nexis": "New York",
        "matthew bender": "New York",
        "wolters kluwer": "New York",
        "aspen": "New York",
        "aspen publishers": "New York",
        "foundation press": "St. Paul",
        "carolina academic press": "Durham",
        "cap": "Durham",
        
        # === MEDICAL/SCIENCE ===
        "lippincott": "Philadelphia",
        "lippincott williams": "Philadelphia",
        "lww": "Philadelphia",
        "saunders": "Philadelphia",
        "mosby": "St. Louis",
        "elsevier health": "Philadelphia",
        "thieme": "New York",
        "karger": "Basel",
        "nature publishing": "London",
        "cold spring harbor": "Cold Spring Harbor",
        "cshl press": "Cold Spring Harbor",
        "asm press": "Washington, DC",
        "american chemical society": "Washington, DC",
        "acs": "Washington, DC",
        "american psychological association": "Washington, DC",
        "apa": "Washington, DC",
        "american psychiatric": "Washington, DC",
        "guilford": "New York",
        "guilford press": "New York",
        
        # === ARTS/HUMANITIES ===
        "yale art": "New Haven",
        "metropolitan museum": "New York",
        "met publications": "New York",
        "getty": "Los Angeles",
        "getty publications": "Los Angeles",
        "prestel": "Munich",
        "thames & hudson": "London",
        "thames and hudson": "London",
        "laurence king": "London",
        
        # === TECH ===
        "o'reilly": "Sebastopol",
        "oreilly": "Sebastopol",
        "addison-wesley": "Boston",
        "addison wesley": "Boston",
        "prentice hall": "Upper Saddle River",
        "apress": "New York",
        "manning": "Shelter Island",
        "no starch": "San Francisco",
        "no starch press": "San Francisco",
        "pragmatic": "Raleigh",
        "pragmatic bookshelf": "Raleigh",
        "packt": "Birmingham",
        "sams": "Indianapolis",
        "que": "Indianapolis",
        "new riders": "Berkeley",
        "peachpit": "San Francisco",
        
        # === INTERNATIONAL ===
        "gallimard": "Paris",
        "flammarion": "Paris",
        "seuil": "Paris",
        "albin michel": "Paris",
        "fayard": "Paris",
        "hachette livre": "Paris",
        "puf": "Paris",
        "suhrkamp": "Frankfurt",
        "fischer": "Frankfurt",
        "rowohlt": "Hamburg",
        "hanser": "Munich",
        "beck": "Munich",
        "c.h. beck": "Munich",
        "dtv": "Munich",
        "einaudi": "Turin",
        "mondadori": "Milan",
        "feltrinelli": "Milan",
        "laterza": "Rome",
        "alianza": "Madrid",
        "anagrama": "Barcelona",
        "tusquets": "Barcelona",
        "fondo de cultura": "Mexico City",
        "siglo xxi": "Mexico City",
    }
    
    pub_lower = publisher.lower()
    for pub_key, place in publisher_places.items():
        if pub_key in pub_lower:
            return place
    return ""


def _search_google_books(query: str, limit: int = 3) -> list:
    """Search Google Books, return multiple results."""
    results = []
    try:
        url = "https://www.googleapis.com/books/v1/volumes"
        params = {"q": query, "maxResults": limit * 2, "orderBy": "relevance"}
        resp = requests.get(url, params=params, timeout=10)
        
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            
            for item in items[:limit * 2]:
                info = item.get("volumeInfo", {})
                title = info.get("title", "")
                
                # Skip knockoffs
                if any(skip in title.lower() for skip in ["summary of", "study guide", "analysis of"]):
                    continue
                
                authors = info.get("authors", [])
                if not authors:
                    continue
                
                publisher = info.get("publisher", "")
                year = info.get("publishedDate", "")[:4] if info.get("publishedDate") else ""
                subtitle = info.get("subtitle", "")
                place = _get_publisher_place(publisher)
                
                author_str = _format_authors(authors)
                full_title = f"{title}: {subtitle}" if subtitle else title
                
                cite = f"{author_str}, {full_title}"
                if place or publisher or year:
                    cite += " ("
                    if place:
                        cite += f"{place}: "
                    if publisher:
                        cite += publisher
                    if year:
                        cite += f", {year}"
                    cite += ")"
                cite += "."
                
                results.append({
                    "citation": cite,
                    "source": "Google Books",
                    "title": title,
                    "authors": authors,
                    "year": year
                })
                
                if len(results) >= limit:
                    break
                    
    except Exception as e:
        print(f"    [Google Books error: {e}]")
    return results


def _search_crossref(query: str, limit: int = 3) -> list:
    """Search Crossref, return multiple results."""
    results = []
    try:
        url = "https://api.crossref.org/works"
        params = {"query": query, "rows": limit * 2}
        headers = {"User-Agent": "CiteFlex/1.0 (mailto:contact@citeflex.com)"}
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        
        if resp.status_code == 200:
            items = resp.json().get("message", {}).get("items", [])
            
            for item in items:
                item_type = item.get("type", "")
                title = item.get("title", [""])[0] if item.get("title") else ""
                
                authors = []
                for a in item.get("author", []):
                    given = a.get('given', '')
                    family = a.get('family', '')
                    if given and family:
                        authors.append(f"{given} {family}")
                    elif family:
                        authors.append(family)
                
                if not authors:
                    continue
                
                year = ""
                if item.get("published"):
                    year = str(item["published"].get("date-parts", [[""]])[0][0])
                elif item.get("issued"):
                    year = str(item["issued"].get("date-parts", [[""]])[0][0])
                
                journal = item.get("container-title", [""])[0] if item.get("container-title") else ""
                volume = item.get("volume", "")
                issue = item.get("issue", "")
                pages = item.get("page", "")
                doi = item.get("DOI", "")
                publisher = item.get("publisher", "")
                
                # Format based on type
                author_str = _format_authors(authors)
                if item_type in ["book", "monograph"]:
                    place = _get_publisher_place(publisher)
                    cite = f"{author_str}, {title}"
                    if place or publisher or year:
                        cite += " ("
                        if place:
                            cite += f"{place}: "
                        if publisher:
                            cite += publisher
                        if year:
                            cite += f", {year}"
                        cite += ")"
                    cite += "."
                else:
                    # Journal article
                    cite = f'{author_str}, "{title},"'
                    if journal:
                        cite += f" {journal}"
                    if volume:
                        cite += f" {volume}"
                    if issue:
                        cite += f", no. {issue}"
                    if year:
                        cite += f" ({year})"
                    if pages:
                        cite += f": {pages}"
                    cite += "."
                    if doi:
                        cite += f" https://doi.org/{doi}."
                
                results.append({
                    "citation": cite,
                    "source": f"Crossref ({item_type})",
                    "title": title,
                    "authors": authors,
                    "year": year,
                    "doi": doi
                })
                
                if len(results) >= limit:
                    break
                    
    except Exception as e:
        print(f"    [Crossref error: {e}]")
    return results


def _search_pubmed(query: str, limit: int = 3) -> list:
    """Search PubMed for medical/scientific articles."""
    results = []
    try:
        # Step 1: Search for PMIDs
        search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        search_params = {"db": "pubmed", "term": query, "retmax": limit, "retmode": "json"}
        search_resp = requests.get(search_url, params=search_params, timeout=10)
        
        if search_resp.status_code != 200:
            return results
        
        pmids = search_resp.json().get("esearchresult", {}).get("idlist", [])
        if not pmids:
            return results
        
        # Step 2: Fetch details
        fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        fetch_params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "json"}
        fetch_resp = requests.get(fetch_url, params=fetch_params, timeout=10)
        
        if fetch_resp.status_code != 200:
            return results
        
        data = fetch_resp.json().get("result", {})
        
        for pmid in pmids:
            if pmid not in data:
                continue
            
            article = data[pmid]
            title = article.get("title", "").rstrip(".")
            
            authors = [a.get("name", "") for a in article.get("authors", []) if a.get("name")]
            if not authors:
                continue
            
            journal = article.get("fulljournalname", "") or article.get("source", "")
            volume = article.get("volume", "")
            issue = article.get("issue", "")
            pages = article.get("pages", "")
            year = article.get("pubdate", "")[:4]
            
            author_str = _format_authors(authors)
            cite = f'{author_str}, "{title},"'
            if journal:
                cite += f" {journal}"
            if volume:
                cite += f" {volume}"
            if issue:
                cite += f", no. {issue}"
            if year:
                cite += f" ({year})"
            if pages:
                cite += f": {pages}"
            cite += f". PMID: {pmid}."
            
            results.append({
                "citation": cite,
                "source": "PubMed",
                "title": title,
                "authors": authors,
                "year": year,
                "pmid": pmid
            })
            
    except Exception as e:
        print(f"    [PubMed error: {e}]")
    return results


# Famous cases cache
FAMOUS_CASES = {
    "roe v. wade": "Roe v. Wade, 410 U.S. 113 (1973).",
    "roe v wade": "Roe v. Wade, 410 U.S. 113 (1973).",
    "osheroff v. chestnut lodge": "Osheroff v. Chestnut Lodge, Inc., 490 A.2d 720 (Md. Ct. Spec. App. 1985).",
    "osheroff v chestnut lodge": "Osheroff v. Chestnut Lodge, Inc., 490 A.2d 720 (Md. Ct. Spec. App. 1985).",
    "brown v. board of education": "Brown v. Board of Education, 347 U.S. 483 (1954).",
    "loving v. virginia": "Loving v. Virginia, 388 U.S. 1 (1967).",
    "miranda v. arizona": "Miranda v. Arizona, 384 U.S. 436 (1966).",
    "marbury v. madison": "Marbury v. Madison, 5 U.S. 137 (1803).",
}


def _search_famous_cases(query: str) -> list:
    """Check famous cases cache."""
    results = []
    lookup = query.lower().strip()
    if lookup in FAMOUS_CASES:
        results.append({
            "citation": FAMOUS_CASES[lookup],
            "source": "Famous Cases Cache",
            "title": query
        })
    return results


def _dedupe_results(results: list) -> list:
    """Remove duplicate results based on title similarity."""
    seen_titles = set()
    deduped = []
    
    for r in results:
        title = r.get("title", "").lower()[:40]
        if title and title in seen_titles:
            continue
        seen_titles.add(title)
        deduped.append(r)
    
    return deduped


# =============================================================================
# MAIN MULTI-OPTION FUNCTION
# =============================================================================

def get_citation_options(messy_note: str, max_options: int = 5) -> list:
    """
    Generate up to max_options candidate citations from multiple sources.
    Returns list of {citation, source, title, ...} dicts.
    
    This is the main function for the multi-option UI.
    """
    all_results = []
    
    # Check for DOI in input
    doi_match = re.search(r'(10\.\d{4,}/[^\s\'"<>]+)', messy_note)
    if doi_match:
        doi = doi_match.group(1).rstrip('.,;')
        # Direct DOI lookup via Crossref
        try:
            url = f"https://api.crossref.org/works/{doi}"
            headers = {"User-Agent": "CiteFlex/1.0"}
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                item = resp.json().get("message", {})
                title = item.get("title", [""])[0] if item.get("title") else ""
                authors = []
                for a in item.get("author", []):
                    given = a.get('given', '')
                    family = a.get('family', '')
                    if given and family:
                        authors.append(f"{given} {family}")
                
                year = ""
                if item.get("published"):
                    year = str(item["published"].get("date-parts", [[""]])[0][0])
                
                journal = item.get("container-title", [""])[0] if item.get("container-title") else ""
                volume = item.get("volume", "")
                issue = item.get("issue", "")
                pages = item.get("page", "")
                
                author_str = _format_authors(authors)
                cite = f'{author_str}, "{title},"'
                if journal:
                    cite += f" {journal}"
                if volume:
                    cite += f" {volume}"
                if issue:
                    cite += f", no. {issue}"
                if year:
                    cite += f" ({year})"
                if pages:
                    cite += f": {pages}"
                cite += f". https://doi.org/{doi}."
                
                all_results.append({
                    "citation": cite,
                    "source": "Crossref (DOI lookup)",
                    "title": title,
                    "authors": authors,
                    "year": year,
                    "doi": doi
                })
        except Exception:
            pass
    
    # Check for legal case (contains "v." or "v ")
    if " v. " in messy_note or " v " in messy_note:
        all_results.extend(_search_famous_cases(messy_note))
    
    # If we already have good results, maybe we're done
    if len(all_results) >= max_options:
        return _dedupe_results(all_results)[:max_options]
    
    # Get Claude's analysis
    identified = _identify_with_claude(messy_note)
    queries = identified.get("search_queries", [messy_note])
    if not queries:
        queries = [messy_note]
    
    # Search multiple APIs in parallel
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = []
        
        for query in queries[:2]:
            futures.append(executor.submit(_search_google_books, query, 2))
            futures.append(executor.submit(_search_crossref, query, 2))
            futures.append(executor.submit(_search_pubmed, query, 2))
        
        if messy_note not in queries:
            futures.append(executor.submit(_search_google_books, messy_note, 2))
            futures.append(executor.submit(_search_crossref, messy_note, 2))
            futures.append(executor.submit(_search_pubmed, messy_note, 2))
        
        for future in as_completed(futures, timeout=20):
            try:
                results = future.result(timeout=5)
                all_results.extend(results)
            except Exception:
                pass
    
    return _dedupe_results(all_results)[:max_options]


# =============================================================================
# BATCH CLASSIFICATION (for document_processor.py performance)
# Added: 2025-12-06
# =============================================================================

BATCH_CLASSIFY_PROMPT = """You are a citation classification expert. Classify each citation in the list below.

For each citation, determine its type:
- legal: Court cases (contains "v." or "v "), statutes, legal documents
- book: Books, monographs, edited volumes
- journal: Academic journal articles, peer-reviewed papers
- newspaper: Newspaper/magazine articles
- government: Government reports, official documents
- interview: Interviews, oral histories, personal communications
- letter: Letters, correspondence
- url: Websites, online resources
- skip: Ibid, Id., supra references, or empty/invalid entries
- unknown: Cannot determine

Respond with a JSON array. Each element must have:
- "index": the note number (1-based)
- "type": one of the types above

Example response:
[{"index": 1, "type": "book"}, {"index": 2, "type": "skip"}, {"index": 3, "type": "legal"}]

Return ONLY the JSON array, no explanation."""


def batch_classify_notes(notes: list, batch_size: int = 50) -> dict:
    """
    Classify multiple notes in batches using Claude.
    
    Args:
        notes: List of dicts with 'id' and 'text' keys
        batch_size: How many notes to classify per API call
        
    Returns:
        Dict mapping note text -> type string
    """
    import time
    
    if not ANTHROPIC_API_KEY:
        print("[BatchClassifier] No API key, skipping batch classification")
        return {}
    
    client = _get_client()
    if not client:
        return {}
    
    classifications = {}
    
    # Pre-filter ibid references (no need for Claude)
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
    
    print(f"[BatchClassifier] Classifying {len(valid_notes)} notes in batches of {batch_size}")
    start_time = time.time()
    
    # Process in batches
    for batch_start in range(0, len(valid_notes), batch_size):
        batch = valid_notes[batch_start:batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        total_batches = (len(valid_notes) + batch_size - 1) // batch_size
        
        print(f"[BatchClassifier] Batch {batch_num}/{total_batches} ({len(batch)} notes)...")
        
        # Build prompt with numbered notes (truncate long ones)
        notes_text = "\n".join([
            f"{i+1}. {note['text'][:400]}"
            for i, note in enumerate(batch)
        ])
        
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=2000,
                system=BATCH_CLASSIFY_PROMPT,
                messages=[{
                    "role": "user", 
                    "content": f"Classify these {len(batch)} citations:\n\n{notes_text}"
                }]
            )
            
            response_text = response.content[0].text.strip()
            
            # Parse JSON response
            json_match = re.search(r'\[[\s\S]*\]', response_text)
            if json_match:
                results = json.loads(json_match.group())
                for result in results:
                    idx = result.get('index', 0) - 1
                    if 0 <= idx < len(batch):
                        note_text = batch[idx]['text']
                        classifications[note_text] = result.get('type', 'unknown')
                        
        except anthropic.RateLimitError:
            print(f"[BatchClassifier] Rate limited on batch {batch_num}")
        except json.JSONDecodeError as e:
            print(f"[BatchClassifier] JSON parse error on batch {batch_num}: {e}")
        except Exception as e:
            print(f"[BatchClassifier] Error on batch {batch_num}: {e}")
    
    elapsed = time.time() - start_time
    print(f"[BatchClassifier] Completed in {elapsed:.1f}s - classified {len(classifications)} notes")
    return classifications
