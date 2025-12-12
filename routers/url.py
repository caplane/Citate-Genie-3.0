"""
citeflex/engines/url_router.py

URL routing and metadata extraction orchestrator.

This module is the entry point for all URL-based citations. It:
1. Analyzes URLs to extract embedded identifiers (DOI, arXiv, PMID, etc.)
2. Identifies domain patterns (newspaper, government, academic, etc.)
3. Routes to the appropriate specialized engine
4. Falls back to generic URL scraping when no specialized handler exists

Version History:
    2025-12-08: Initial creation - URL routing architecture
"""

import re
from typing import Optional, Tuple
from urllib.parse import urlparse

from models import CitationMetadata, CitationType
from config import NEWSPAPER_DOMAINS, GOV_AGENCY_MAP, ACADEMIC_DOMAINS, LEGAL_DOMAINS


# =============================================================================
# URL IDENTIFIER EXTRACTORS
# =============================================================================

def extract_doi_from_url(url: str) -> Optional[str]:
    """
    Extract DOI from URL.
    
    Handles:
    - doi.org/10.xxxx/yyyy
    - dx.doi.org/10.xxxx/yyyy
    - Publisher URLs with /doi/ path (OUP, Cambridge, Wiley, etc.)
    - URLs with DOI embedded anywhere
    """
    if not url:
        return None
    
    # Direct DOI URLs
    if 'doi.org/' in url.lower():
        match = re.search(r'doi\.org/(10\.\d{4,}/[^\s?#]+)', url, re.IGNORECASE)
        if match:
            return match.group(1).rstrip('.')
    
    # Publisher URLs with /doi/ in path
    # e.g., journals.uchicago.edu/doi/10.1086/737061
    match = re.search(r'/doi/(?:abs/|full/|pdf/)?(10\.\d{4,}/[^\s?#]+)', url, re.IGNORECASE)
    if match:
        return match.group(1).rstrip('.')
    
    # Generic DOI pattern anywhere in URL
    match = re.search(r'(10\.\d{4,}/[^\s?#&]+)', url)
    if match:
        return match.group(1).rstrip('.')
    
    return None


def extract_arxiv_id(url: str) -> Optional[str]:
    """
    Extract arXiv ID from URL.
    
    Handles:
    - arxiv.org/abs/2301.12345
    - arxiv.org/pdf/2301.12345
    - Old format: arxiv.org/abs/hep-th/9901001
    """
    if not url or 'arxiv' not in url.lower():
        return None
    
    # New format: 2301.12345
    match = re.search(r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)', url, re.IGNORECASE)
    if match:
        return match.group(1)
    
    # Old format: hep-th/9901001
    match = re.search(r'arxiv\.org/(?:abs|pdf)/([a-z-]+/\d{7})', url, re.IGNORECASE)
    if match:
        return match.group(1)
    
    return None


def extract_pmid_from_url(url: str) -> Optional[str]:
    """
    Extract PubMed ID from URL.
    
    Handles:
    - pubmed.ncbi.nlm.nih.gov/12345678
    - ncbi.nlm.nih.gov/pubmed/12345678
    """
    if not url:
        return None
    
    match = re.search(r'pubmed\.ncbi\.nlm\.nih\.gov/(\d+)', url, re.IGNORECASE)
    if match:
        return match.group(1)
    
    match = re.search(r'ncbi\.nlm\.nih\.gov/pubmed/(\d+)', url, re.IGNORECASE)
    if match:
        return match.group(1)
    
    return None


def extract_pmc_id(url: str) -> Optional[str]:
    """
    Extract PubMed Central ID from URL.
    
    Handles:
    - ncbi.nlm.nih.gov/pmc/articles/PMC1234567
    """
    if not url:
        return None
    
    match = re.search(r'/pmc/articles/(PMC\d+)', url, re.IGNORECASE)
    if match:
        return match.group(1)
    
    return None


def extract_jstor_id(url: str) -> Optional[str]:
    """
    Extract JSTOR stable ID from URL.
    
    Handles:
    - jstor.org/stable/12345678
    """
    if not url or 'jstor' not in url.lower():
        return None
    
    match = re.search(r'jstor\.org/stable/(\d+)', url, re.IGNORECASE)
    if match:
        return match.group(1)
    
    return None


def extract_ssrn_id(url: str) -> Optional[str]:
    """
    Extract SSRN abstract ID from URL.
    
    Handles:
    - ssrn.com/abstract=1234567
    - papers.ssrn.com/sol3/papers.cfm?abstract_id=1234567
    """
    if not url or 'ssrn' not in url.lower():
        return None
    
    # Pattern 1: abstract_id=1234567
    match = re.search(r'abstract_id=(\d+)', url, re.IGNORECASE)
    if match:
        return match.group(1)
    
    # Pattern 2: abstract=1234567
    match = re.search(r'abstract=(\d+)', url, re.IGNORECASE)
    if match:
        return match.group(1)
    
    return None


def extract_wikipedia_title(url: str) -> Optional[str]:
    """
    Extract Wikipedia article title from URL.
    
    Handles:
    - en.wikipedia.org/wiki/Article_Title
    - wikipedia.org/wiki/Article_Title
    """
    if not url or 'wikipedia.org' not in url.lower():
        return None
    
    match = re.search(r'wikipedia\.org/wiki/([^?#]+)', url, re.IGNORECASE)
    if match:
        # URL decode and replace underscores
        title = match.group(1)
        title = title.replace('_', ' ')
        # Basic URL decoding
        import urllib.parse
        title = urllib.parse.unquote(title)
        return title
    
    return None


def extract_youtube_id(url: str) -> Optional[str]:
    """
    Extract YouTube video ID from URL.
    
    Handles:
    - youtube.com/watch?v=VIDEO_ID
    - youtu.be/VIDEO_ID
    - youtube.com/embed/VIDEO_ID
    """
    if not url:
        return None
    
    lower = url.lower()
    if 'youtube.com' not in lower and 'youtu.be' not in lower:
        return None
    
    # youtu.be/VIDEO_ID
    match = re.search(r'youtu\.be/([a-zA-Z0-9_-]{11})', url)
    if match:
        return match.group(1)
    
    # youtube.com/watch?v=VIDEO_ID
    match = re.search(r'[?&]v=([a-zA-Z0-9_-]{11})', url)
    if match:
        return match.group(1)
    
    # youtube.com/embed/VIDEO_ID
    match = re.search(r'/embed/([a-zA-Z0-9_-]{11})', url)
    if match:
        return match.group(1)
    
    return None


def extract_google_books_id(url: str) -> Optional[str]:
    """
    Extract Google Books volume ID from URL.
    
    Handles:
    - books.google.com/books?id=VOLUME_ID
    """
    if not url or 'books.google' not in url.lower():
        return None
    
    match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    
    return None


def extract_internet_archive_id(url: str) -> Optional[str]:
    """
    Extract Internet Archive item ID from URL.
    
    Handles:
    - archive.org/details/ITEM_ID
    """
    if not url or 'archive.org' not in url.lower():
        return None
    
    match = re.search(r'archive\.org/details/([^/?#]+)', url)
    if match:
        return match.group(1)
    
    return None


# =============================================================================
# DOMAIN CLASSIFICATION
# =============================================================================

class URLType:
    """Enumeration of URL source types for routing."""
    DOI = "doi"
    ARXIV = "arxiv"
    PUBMED = "pubmed"
    PMC = "pmc"
    JSTOR = "jstor"
    SSRN = "ssrn"
    WIKIPEDIA = "wikipedia"
    YOUTUBE = "youtube"
    GOOGLE_BOOKS = "google_books"
    INTERNET_ARCHIVE = "internet_archive"
    NEWSPAPER = "newspaper"
    GOVERNMENT = "government"
    LEGAL = "legal"
    ACADEMIC = "academic"
    GENERIC = "generic"


def classify_url(url: str) -> Tuple[str, Optional[str]]:
    """
    Classify a URL and extract any embedded identifier.
    
    Returns:
        Tuple of (URLType, identifier or None)
    """
    if not url:
        return (URLType.GENERIC, None)
    
    # ==========================================================================
    # PHASE 1: Check for embedded identifiers (highest priority)
    # ==========================================================================
    
    # DOI - check first since many academic URLs contain DOIs
    doi = extract_doi_from_url(url)
    if doi:
        return (URLType.DOI, doi)
    
    # arXiv
    arxiv_id = extract_arxiv_id(url)
    if arxiv_id:
        return (URLType.ARXIV, arxiv_id)
    
    # PubMed
    pmid = extract_pmid_from_url(url)
    if pmid:
        return (URLType.PUBMED, pmid)
    
    # PMC
    pmc_id = extract_pmc_id(url)
    if pmc_id:
        return (URLType.PMC, pmc_id)
    
    # JSTOR
    jstor_id = extract_jstor_id(url)
    if jstor_id:
        return (URLType.JSTOR, jstor_id)
    
    # SSRN
    ssrn_id = extract_ssrn_id(url)
    if ssrn_id:
        return (URLType.SSRN, ssrn_id)
    
    # Wikipedia
    wiki_title = extract_wikipedia_title(url)
    if wiki_title:
        return (URLType.WIKIPEDIA, wiki_title)
    
    # YouTube
    youtube_id = extract_youtube_id(url)
    if youtube_id:
        return (URLType.YOUTUBE, youtube_id)
    
    # Google Books
    gbooks_id = extract_google_books_id(url)
    if gbooks_id:
        return (URLType.GOOGLE_BOOKS, gbooks_id)
    
    # Internet Archive
    archive_id = extract_internet_archive_id(url)
    if archive_id:
        return (URLType.INTERNET_ARCHIVE, archive_id)
    
    # ==========================================================================
    # PHASE 2: Domain-based classification
    # ==========================================================================
    
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace('www.', '')
    except Exception:
        return (URLType.GENERIC, None)
    
    # Legal domains
    for legal_domain in LEGAL_DOMAINS:
        if legal_domain in domain:
            return (URLType.LEGAL, None)
    
    # Newspaper domains
    for news_domain in NEWSPAPER_DOMAINS:
        if news_domain in domain:
            return (URLType.NEWSPAPER, None)
    
    # UK government (gov.uk) - check before generic .gov
    if 'gov.uk' in domain:
        return (URLType.GOVERNMENT, None)
    
    # UK NHS and related health bodies
    if 'nhs.uk' in domain or 'nice.org.uk' in domain:
        return (URLType.GOVERNMENT, None)
    
    # UK Parliament and devolved governments
    if 'parliament.uk' in domain or 'gov.scot' in domain or 'gov.wales' in domain:
        return (URLType.GOVERNMENT, None)
    
    # Canada (.gc.ca, .canada.ca, provincial)
    if '.gc.ca' in domain or '.canada.ca' in domain or domain.endswith('canada.ca'):
        return (URLType.GOVERNMENT, None)
    # Canadian provincial governments
    canadian_provincial = [
        'ontario.ca', 'quebec.ca', 'gov.bc.ca', 'alberta.ca',
        'gov.mb.ca', 'gov.sk.ca', 'gov.ns.ca', 'gnb.ca',
        'gov.nl.ca', 'gov.pe.ca', 'gov.nt.ca', 'gov.nu.ca', 'gov.yk.ca'
    ]
    if any(prov in domain for prov in canadian_provincial):
        return (URLType.GOVERNMENT, None)
    # Canadian parliament and courts
    if 'parl.ca' in domain or 'scc-csc.ca' in domain:
        return (URLType.GOVERNMENT, None)
    
    # Australia (.gov.au)
    if '.gov.au' in domain:
        return (URLType.GOVERNMENT, None)
    # Australian state/territory specific patterns
    aus_states = ['nsw.gov.au', 'vic.gov.au', 'qld.gov.au', 'wa.gov.au',
                  'sa.gov.au', 'tas.gov.au', 'nt.gov.au', 'act.gov.au']
    if any(state in domain for state in aus_states):
        return (URLType.GOVERNMENT, None)
    # CSIRO (not .gov.au but government)
    if 'csiro.au' in domain:
        return (URLType.GOVERNMENT, None)
    
    # New Zealand (.govt.nz)
    if 'govt.nz' in domain:
        return (URLType.GOVERNMENT, None)
    # NZ Parliament and other government
    if 'parliament.nz' in domain or 'elections.nz' in domain:
        return (URLType.GOVERNMENT, None)
    
    # Ireland (.gov.ie and other government bodies)
    if 'gov.ie' in domain:
        return (URLType.GOVERNMENT, None)
    # Irish government bodies
    irish_gov = ['oireachtas.ie', 'courts.ie', 'cso.ie', 'revenue.ie',
                 'citizensinformation.ie', 'hse.ie', 'centralbank.ie']
    if any(ie_gov in domain for ie_gov in irish_gov):
        return (URLType.GOVERNMENT, None)
    
    # European Union (.europa.eu)
    if '.europa.eu' in domain or domain.endswith('europa.eu'):
        return (URLType.GOVERNMENT, None)
    
    # International organizations
    intl_orgs = ['who.int', 'un.org', 'oecd.org', 'imf.org', 
                 'worldbank.org', 'wto.org', 'nato.int', 'icrc.org']
    if any(org in domain for org in intl_orgs):
        return (URLType.GOVERNMENT, None)
    
    # Government domains (.gov) - US and generic
    if '.gov' in domain:
        # Exclude medical .gov sites - they should use PubMed/PMC engines
        medical_gov = ['pubmed', 'ncbi', 'nlm.nih', 'clinicaltrials']
        if not any(med in domain for med in medical_gov):
            return (URLType.GOVERNMENT, None)
    
    # Academic publisher domains
    for academic_domain in ACADEMIC_DOMAINS:
        if academic_domain in domain:
            return (URLType.ACADEMIC, None)
    
    # Fallback
    return (URLType.GENERIC, None)


# =============================================================================
# URL ROUTER CLASS
# =============================================================================

class URLRouter:
    """
    Routes URLs to appropriate engines for metadata extraction.
    
    Usage:
        router = URLRouter()
        metadata = router.route("https://www.nytimes.com/2025/...")
    
    The router:
    1. Extracts any embedded identifiers (DOI, arXiv ID, PMID, etc.)
    2. Classifies the URL by domain pattern
    3. Routes to the appropriate specialized engine
    4. Falls back to generic URL scraping if no specialized handler exists
    """
    
    def __init__(self):
        """Initialize router with available engines."""
        self._engines = {}
        self._load_engines()
    
    def _load_engines(self):
        """
        Load available engines.
        
        Engines are loaded lazily to avoid import errors if some
        dependencies are missing.
        """
        # DOI -> Crossref
        try:
            from engines.academic import CrossrefEngine
            self._engines[URLType.DOI] = CrossrefEngine()
        except ImportError:
            print("[URLRouter] CrossrefEngine not available")
        
        # PubMed
        try:
            from engines.academic import PubMedEngine
            self._engines[URLType.PUBMED] = PubMedEngine()
        except ImportError:
            print("[URLRouter] PubMedEngine not available")
        
        # Google Books
        try:
            from engines.google_cse import GoogleBooksEngine
            self._engines[URLType.GOOGLE_BOOKS] = GoogleBooksEngine()
        except ImportError:
            print("[URLRouter] GoogleBooksEngine not available")
        
        # Generic URL engine (fallback for all URLs)
        try:
            from engines.generic_url_engine import GenericURLEngine
            self._engines[URLType.GENERIC] = GenericURLEngine()
        except ImportError:
            print("[URLRouter] GenericURLEngine not available")
        
        # Newspaper engine
        try:
            from engines.generic_url_engine import NewspaperEngine
            self._engines[URLType.NEWSPAPER] = NewspaperEngine()
        except ImportError:
            print("[URLRouter] NewspaperEngine not available")
        
        # Government engine
        try:
            from engines.generic_url_engine import GovernmentEngine
            self._engines[URLType.GOVERNMENT] = GovernmentEngine()
        except ImportError:
            print("[URLRouter] GovernmentEngine not available")
        
        # arXiv engine
        try:
            from engines.arxiv_engine import ArxivEngine
            self._engines[URLType.ARXIV] = ArxivEngine()
        except ImportError:
            print("[URLRouter] ArxivEngine not available")
        
        # Wikipedia engine
        try:
            from engines.wikipedia_engine import WikipediaEngine
            self._engines[URLType.WIKIPEDIA] = WikipediaEngine()
        except ImportError:
            print("[URLRouter] WikipediaEngine not available")
        
        # YouTube engine
        try:
            from engines.youtube_engine import YouTubeEngine
            self._engines[URLType.YOUTUBE] = YouTubeEngine()
        except ImportError:
            print("[URLRouter] YouTubeEngine not available")
    
    def route(self, url: str) -> Optional[CitationMetadata]:
        """
        Route a URL to the appropriate engine and return metadata.
        
        Args:
            url: The URL to process
            
        Returns:
            CitationMetadata if successful, None otherwise
        """
        if not url or not url.strip():
            return None
        
        url = url.strip()
        
        # Ensure URL has a scheme
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Classify the URL
        url_type, identifier = classify_url(url)
        print(f"[URLRouter] Classified as {url_type}" + (f" (ID: {identifier})" if identifier else ""))
        
        # Route based on classification
        return self._dispatch(url, url_type, identifier)
    
    def _dispatch(self, url: str, url_type: str, identifier: Optional[str]) -> Optional[CitationMetadata]:
        """
        Dispatch to the appropriate engine based on URL type.
        """
        # =======================================================================
        # IDENTIFIER-BASED ROUTING (highest confidence)
        # =======================================================================
        
        if url_type == URLType.DOI and identifier:
            engine = self._engines.get(URLType.DOI)
            if engine:
                print(f"[URLRouter] Using CrossrefEngine for DOI: {identifier}")
                result = engine.get_by_id(identifier)
                if result:
                    result.url = result.url or url  # Preserve original URL
                    return result
        
        if url_type == URLType.PUBMED and identifier:
            engine = self._engines.get(URLType.PUBMED)
            if engine:
                print(f"[URLRouter] Using PubMedEngine for PMID: {identifier}")
                result = engine.get_by_id(identifier)
                if result:
                    result.url = result.url or url
                    return result
        
        if url_type == URLType.ARXIV and identifier:
            engine = self._engines.get(URLType.ARXIV)
            if engine:
                print(f"[URLRouter] Using ArxivEngine for arXiv ID: {identifier}")
                result = engine.get_by_id(identifier)
                if result:
                    result.url = result.url or url
                    return result
            else:
                # Fallback: arXiv IDs can sometimes be found via Crossref
                print(f"[URLRouter] ArxivEngine not available, trying Crossref")
                # TODO: Implement arXiv -> DOI lookup
        
        if url_type == URLType.GOOGLE_BOOKS and identifier:
            engine = self._engines.get(URLType.GOOGLE_BOOKS)
            if engine:
                print(f"[URLRouter] Using GoogleBooksEngine for ID: {identifier}")
                # GoogleBooksEngine.get_by_id expects ISBN, not volume ID
                # We need to fetch the volume directly
                # TODO: Add get_by_volume_id method to GoogleBooksEngine
        
        if url_type == URLType.WIKIPEDIA and identifier:
            engine = self._engines.get(URLType.WIKIPEDIA)
            if engine:
                print(f"[URLRouter] Using WikipediaEngine for: {identifier}")
                result = engine.get_by_id(identifier)
                if result:
                    result.url = result.url or url
                    return result
            else:
                print(f"[URLRouter] WikipediaEngine not available")
        
        if url_type == URLType.YOUTUBE and identifier:
            engine = self._engines.get(URLType.YOUTUBE)
            if engine:
                print(f"[URLRouter] Using YouTubeEngine for video: {identifier}")
                result = engine.get_by_id(identifier)
                if result:
                    result.url = result.url or url
                    return result
            else:
                print(f"[URLRouter] YouTubeEngine not available")
        
        # =======================================================================
        # DOMAIN-BASED ROUTING
        # =======================================================================
        
        if url_type == URLType.NEWSPAPER:
            engine = self._engines.get(URLType.NEWSPAPER)
            if engine:
                print(f"[URLRouter] Using NewspaperEngine")
                return engine.fetch_by_url(url)
            else:
                print(f"[URLRouter] NewspaperEngine not available, falling back to generic")
                return self._fallback_generic(url, CitationType.NEWSPAPER)
        
        if url_type == URLType.GOVERNMENT:
            engine = self._engines.get(URLType.GOVERNMENT)
            if engine:
                print(f"[URLRouter] Using GovernmentEngine")
                return engine.fetch_by_url(url)
            else:
                print(f"[URLRouter] GovernmentEngine not available, falling back to generic")
                return self._fallback_generic(url, CitationType.GOVERNMENT)
        
        if url_type == URLType.LEGAL:
            engine = self._engines.get(URLType.LEGAL)
            if engine:
                print(f"[URLRouter] Using LegalEngine")
                return engine.fetch_by_url(url)
            else:
                print(f"[URLRouter] LegalEngine not available")
                # Legal citations need specialized handling, don't fall back to generic
                return None
        
        if url_type == URLType.ACADEMIC:
            # Try Google Scholar as fallback for academic URLs without DOI
            try:
                from engines.google_scholar import GoogleScholarEngine
                engine = GoogleScholarEngine()
                print(f"[URLRouter] Using GoogleScholarEngine for academic URL")
                # Extract potential search terms from URL
                parsed = urlparse(url)
                path_parts = parsed.path.strip('/').split('/')
                if path_parts:
                    query = path_parts[-1].replace('-', ' ').replace('_', ' ')
                    return engine.search(query)
            except ImportError:
                pass
        
        # =======================================================================
        # FALLBACK: Generic URL scraping
        # =======================================================================
        
        return self._fallback_generic(url, CitationType.URL)
    
    def _fallback_generic(self, url: str, citation_type: CitationType) -> Optional[CitationMetadata]:
        """
        Fallback to generic URL scraping.
        
        Uses GenericURLEngine if available, otherwise returns minimal metadata.
        """
        engine = self._engines.get(URLType.GENERIC)
        if engine:
            print(f"[URLRouter] Using GenericURLEngine")
            result = engine.fetch_by_url(url)
            if result:
                result.citation_type = citation_type
                return result
        
        # Last resort: return minimal metadata with just the URL
        print(f"[URLRouter] No engine available, returning minimal metadata")
        return CitationMetadata(
            citation_type=citation_type,
            raw_source=url,
            source_engine="URLRouter (minimal)",
            url=url,
            title="",  # Will need to be filled by user or formatter
        )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def route_url(url: str) -> Optional[CitationMetadata]:
    """
    Convenience function to route a URL without instantiating router.
    
    Args:
        url: The URL to process
        
    Returns:
        CitationMetadata if successful, None otherwise
    """
    router = URLRouter()
    return router.route(url)


def get_url_type(url: str) -> Tuple[str, Optional[str]]:
    """
    Get the classification of a URL without processing it.
    
    Args:
        url: The URL to classify
        
    Returns:
        Tuple of (URLType, identifier or None)
    """
    return classify_url(url)
