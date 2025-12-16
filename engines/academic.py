"""
citeflex/engines/academic.py

Academic database search engines.
- CrossrefEngine: Official DOI registry
- OpenAlexEngine: Broad academic coverage
- SemanticScholarEngine: AI-powered with author matching
- PubMedEngine: Biomedical literature

UPDATED 2025-12-12: All engines now use author-position scoring.
When multiple results are found, the one where the query author is
sole/first author ranks highest. This fixes the "Eric Caplan trains brains"
problem where the correct paper was found but discarded in favor of
papers by Louis Caplan (different author, same surname).
"""

import re
import difflib
from typing import Optional, List, Tuple

from engines.base import SearchEngine
from models import CitationMetadata, CitationType
from config import PUBMED_API_KEY, SEMANTIC_SCHOLAR_API_KEY

# Shorter timeout for faster failures
ENGINE_TIMEOUT = 5  # seconds


# =============================================================================
# SHARED AUTHOR-POSITION SCORING
# =============================================================================
# This is the key insight: PubMed/Crossref/etc often FIND the correct paper,
# but it's not first in their ranking. By scoring author POSITION, we can
# identify where the query author is sole/first author vs. 47th author.

# Common first names to skip when extracting surname from query
COMMON_FIRST_NAMES = {
    'james', 'john', 'robert', 'michael', 'william', 'david', 'richard', 'joseph',
    'thomas', 'charles', 'christopher', 'daniel', 'matthew', 'anthony', 'mark',
    'donald', 'steven', 'paul', 'andrew', 'joshua', 'kenneth', 'kevin', 'brian',
    'george', 'edward', 'ronald', 'timothy', 'jason', 'jeffrey', 'ryan', 'jacob',
    'mary', 'patricia', 'jennifer', 'linda', 'elizabeth', 'barbara', 'susan',
    'jessica', 'sarah', 'karen', 'nancy', 'lisa', 'betty', 'margaret', 'sandra',
    'ashley', 'dorothy', 'kimberly', 'emily', 'donna', 'michelle', 'carol', 'amanda',
    'eric', 'louis', 'peter', 'henry', 'arthur', 'albert', 'frank', 'raymond',
    'anna', 'ruth', 'helen', 'laura', 'marie', 'ann', 'jane', 'alice', 'grace'
}


def extract_query_author(query: str) -> Optional[str]:
    """
    Extract the likely author surname from a query.
    
    For "Eric Caplan trains brains" → returns "caplan"
    For "trains brains" → returns None
    """
    words = query.split()
    
    # Strategy 1: "FirstName LastName keywords" pattern
    if len(words) >= 2:
        first_word = words[0].strip().lower()
        second_word = words[1].strip()
        
        if first_word in COMMON_FIRST_NAMES:
            if second_word[0].isupper() and len(second_word) >= 3:
                return second_word.lower()
    
    # Strategy 2: Find capitalized word that's not a common first name
    for word in words:
        clean = re.sub(r'[^\w]', '', word)
        if clean and clean[0].isupper() and len(clean) >= 3:
            if clean.lower() not in COMMON_FIRST_NAMES:
                return clean.lower()
    
    return None


def score_author_position(authors: List[str], query: str) -> float:
    """
    Score based on where query author appears in author list.
    
    Returns:
        1.0 = sole author (best match!)
        0.9 = first author
        0.7 = 2nd-3rd author
        0.3 = 4th+ author (likely coincidental)
        0.1 = author not found
        0.5 = no clear author in query
    """
    if not authors:
        return 0.1
    
    query_author = extract_query_author(query)
    if not query_author:
        return 0.5  # No clear author in query, can't score
    
    # Check each author position
    for i, author in enumerate(authors):
        author_lower = author.lower()
        if query_author in author_lower:
            if len(authors) == 1:
                return 1.0  # Sole author — best match!
            elif i == 0:
                return 0.9  # First author
            elif i <= 2:
                return 0.7  # 2nd-3rd author
            else:
                return 0.3  # 4th+ author (likely coincidental)
    
    return 0.1  # Author not found


# =============================================================================
# CROSSREF ENGINE
# =============================================================================

class CrossrefEngine(SearchEngine):
    """
    Search Crossref - the official DOI registry.
    
    Excellent for:
    - Journal articles with DOIs
    - Recent publications
    - Accurate metadata
    
    UPDATED: Now fetches multiple results and scores by author-position.
    """
    
    name = "Crossref"
    base_url = "https://api.crossref.org/works"
    
    def search(self, query: str) -> Optional[CitationMetadata]:
        """
        Search Crossref with author-position scoring.
        
        Fetches up to 10 results and returns the one where query author
        is sole/first author.
        """
        params = {
            'query.bibliographic': query,
            'rows': 10  # Get multiple to find best author match
        }
        
        response = self._make_request(self.base_url, params=params)
        if not response:
            return None
        
        try:
            data = response.json()
            items = data.get('message', {}).get('items', [])
            if not items:
                return None
            
            # If only one result, just return it
            if len(items) == 1:
                return self._normalize(items[0], query)
            
            # Score each by author position
            candidates = []
            for item in items:
                meta = self._normalize(item, query)
                if meta:
                    score = score_author_position(meta.authors or [], query)
                    candidates.append((score, meta))
            
            if not candidates:
                return None
            
            # Sort by score (highest first)
            candidates.sort(key=lambda x: x[0], reverse=True)
            best_score, best_meta = candidates[0]
            
            print(f"[{self.name}] Selected result (author-score: {best_score})")
            return best_meta
            
        except Exception as e:
            print(f"[{self.name}] Parse error: {e}")
            return None
    
    def search_multiple(self, query: str, limit: int = 5) -> List[CitationMetadata]:
        """Return multiple results, sorted by author-position score."""
        params = {
            'query.bibliographic': query,
            'rows': max(limit, 10)  # Get extra for scoring
        }
        
        response = self._make_request(self.base_url, params=params)
        if not response:
            return []
        
        try:
            data = response.json()
            items = data.get('message', {}).get('items', [])
            
            # Normalize and score all
            candidates = []
            for item in items:
                meta = self._normalize(item, query)
                if meta:
                    score = score_author_position(meta.authors or [], query)
                    meta.confidence = score
                    candidates.append((score, meta))
            
            # Sort by score
            candidates.sort(key=lambda x: x[0], reverse=True)
            
            return [meta for score, meta in candidates[:limit]]
        except:
            return []
    
    def get_by_id(self, doi: str) -> Optional[CitationMetadata]:
        """Look up by DOI directly."""
        # Clean DOI
        doi = doi.replace('https://doi.org/', '').replace('http://dx.doi.org/', '')
        url = f"{self.base_url}/{doi}"
        
        response = self._make_request(url)
        if not response:
            return None
        
        try:
            data = response.json()
            item = data.get('message', {})
            if item:
                return self._normalize(item, doi)
        except:
            pass
        return None
    
    def _normalize(self, item: dict, raw_source: str) -> CitationMetadata:
        """Convert Crossref response to CitationMetadata."""
        # Extract authors - preserve structured data
        authors = []
        authors_parsed = []
        for author in item.get('author', []):
            given = author.get('given', '')
            family = author.get('family', '')
            if given and family:
                authors.append(f"{given} {family}")
                authors_parsed.append({"given": given, "family": family})
            elif family:
                # Could be organizational or single-name author
                authors.append(family)
                # Check if it looks like an organization
                from models import _is_organizational_author
                if _is_organizational_author(family):
                    authors_parsed.append({"family": family, "is_org": True})
                else:
                    authors_parsed.append({"family": family})
        
        # Extract year
        year = None
        for date_field in ['published-print', 'published-online', 'created']:
            if item.get(date_field, {}).get('date-parts'):
                parts = item[date_field]['date-parts'][0]
                if parts:
                    year = str(parts[0])
                    break
        
        # Get container (journal) title
        journal = ''
        container = item.get('container-title', [])
        if container:
            journal = container[0] if isinstance(container, list) else container
        
        # Determine type
        item_type = item.get('type', '')
        if item_type in ['book', 'monograph', 'edited-book']:
            citation_type = CitationType.BOOK
        elif item_type in ['book-chapter', 'book-section']:
            citation_type = CitationType.BOOK
        else:
            citation_type = CitationType.JOURNAL
        
        # Get title
        title_list = item.get('title', [])
        title = title_list[0] if title_list else ''
        
        return self._create_metadata(
            citation_type=citation_type,
            raw_source=raw_source,
            title=title,
            authors=authors,
            authors_parsed=authors_parsed,
            year=year,
            journal=journal,
            volume=item.get('volume', ''),
            issue=item.get('issue', ''),
            pages=item.get('page', ''),
            doi=item.get('DOI', ''),
            url=f"https://doi.org/{item.get('DOI')}" if item.get('DOI') else '',
            publisher=item.get('publisher', ''),
            raw_data=item
        )


# =============================================================================
# OPENALEX ENGINE
# =============================================================================

class OpenAlexEngine(SearchEngine):
    """
    Search OpenAlex - broad academic coverage.
    
    Excellent for:
    - Older publications
    - Open access content
    - Citation networks
    
    UPDATED: Now fetches multiple results and scores by author-position.
    """
    
    name = "OpenAlex"
    base_url = "https://api.openalex.org/works"
    
    def search(self, query: str) -> Optional[CitationMetadata]:
        """
        Search OpenAlex with author-position scoring.
        """
        params = {
            'search': query,
            'per-page': 10  # Get multiple to find best author match
        }
        
        response = self._make_request(self.base_url, params=params)
        if not response:
            return None
        
        try:
            data = response.json()
            results = data.get('results', [])
            if not results:
                return None
            
            # If only one result, just return it
            if len(results) == 1:
                return self._normalize(results[0], query)
            
            # Score each by author position
            candidates = []
            for item in results:
                meta = self._normalize(item, query)
                if meta:
                    score = score_author_position(meta.authors or [], query)
                    candidates.append((score, meta))
            
            if not candidates:
                return None
            
            # Sort by score (highest first)
            candidates.sort(key=lambda x: x[0], reverse=True)
            best_score, best_meta = candidates[0]
            
            print(f"[{self.name}] Selected result (author-score: {best_score})")
            return best_meta
            
        except Exception as e:
            print(f"[{self.name}] Parse error: {e}")
            return None
    
    def search_multiple(self, query: str, limit: int = 5) -> List[CitationMetadata]:
        """Return multiple results, sorted by author-position score."""
        params = {
            'search': query,
            'per-page': max(limit, 10)
        }
        
        response = self._make_request(self.base_url, params=params)
        if not response:
            return []
        
        try:
            data = response.json()
            results = data.get('results', [])
            
            candidates = []
            for item in results:
                meta = self._normalize(item, query)
                if meta:
                    score = score_author_position(meta.authors or [], query)
                    meta.confidence = score
                    candidates.append((score, meta))
            
            candidates.sort(key=lambda x: x[0], reverse=True)
            return [meta for score, meta in candidates[:limit]]
        except:
            return []
    
    def _normalize(self, item: dict, raw_source: str) -> CitationMetadata:
        """Convert OpenAlex response to CitationMetadata."""
        # Extract authors - parse display_name into structured format
        authors = []
        authors_parsed = []
        for authorship in item.get('authorships', []):
            author_info = authorship.get('author', {})
            name = author_info.get('display_name')
            if name:
                authors.append(name)
                # Parse the display name into given/family
                from models import parse_author_name
                authors_parsed.append(parse_author_name(name))
        
        # Get journal from primary location
        journal = ''
        location = item.get('primary_location', {}) or {}
        source = location.get('source', {}) or {}
        if source.get('display_name'):
            journal = source['display_name']
        
        # Get bibliographic info
        biblio = item.get('biblio', {}) or {}
        
        # Extract DOI
        doi = item.get('doi', '')
        if doi and doi.startswith('https://doi.org/'):
            doi = doi.replace('https://doi.org/', '')
        
        # Get URL
        url = item.get('doi', '') or item.get('id', '')
        
        return self._create_metadata(
            citation_type=CitationType.JOURNAL,
            raw_source=raw_source,
            title=item.get('display_name', item.get('title', '')),
            authors=authors,
            authors_parsed=authors_parsed,
            year=str(item.get('publication_year', '')) if item.get('publication_year') else None,
            journal=journal,
            volume=biblio.get('volume', ''),
            issue=biblio.get('issue', ''),
            pages=f"{biblio.get('first_page', '')}-{biblio.get('last_page', '')}" if biblio.get('first_page') else '',
            doi=doi,
            url=url,
            raw_data=item
        )


# =============================================================================
# SEMANTIC SCHOLAR ENGINE
# =============================================================================

class SemanticScholarEngine(SearchEngine):
    """
    Search Semantic Scholar - AI-powered with author matching.
    
    Features:
    - Author-aware result ranking
    - Good for finding papers by "Author Title" queries
    
    UPDATED: Now includes author-POSITION scoring, not just name matching.
    """
    
    name = "Semantic Scholar"
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    details_url = "https://api.semanticscholar.org/graph/v1/paper/"
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key=api_key or SEMANTIC_SCHOLAR_API_KEY, **kwargs)
    
    def _get_headers(self) -> dict:
        """Get headers with API key if available."""
        headers = {}
        if self.api_key:
            headers['x-api-key'] = self.api_key
        return headers
    
    def search(self, query: str) -> Optional[CitationMetadata]:
        """
        Search with author-position scoring.
        Gets top 10 results, scores by author position, returns best.
        """
        headers = self._get_headers()
        params = {
            'query': query,
            'limit': 10,
            'fields': 'paperId,title,authors'
        }
        
        response = self._make_request(self.base_url, params=params, headers=headers)
        if not response:
            return None
        
        try:
            data = response.json()
            if data.get('total', 0) == 0:
                return None
            
            papers = data.get('data', [])
            if not papers:
                return None
            
            # Score each paper by author position
            best_match = self._find_best_match(papers, query)
            
            # Get full details
            return self._fetch_details(best_match['paperId'], query, headers)
            
        except Exception as e:
            print(f"[{self.name}] Parse error: {e}")
            return None
    
    def _find_best_match(self, papers: List[dict], query: str) -> dict:
        """
        Score papers by author POSITION (not just name presence).
        
        UPDATED: Sole author scores highest, first author next, 4th+ lowest.
        """
        query_lower = query.lower()
        query_author = extract_query_author(query)
        
        best_match = papers[0]
        best_score = -1
        
        # Stopwords for title matching
        stopwords = {'the', 'a', 'an', 'of', 'and', 'in', 'on', 'for', 'to'}
        query_words = [w for w in query_lower.split() if len(w) >= 3 and w not in stopwords]
        
        for paper in papers:
            score = 0
            authors = paper.get('authors', [])
            title = paper.get('title', '').lower()
            
            # AUTHOR POSITION SCORING (the key fix!)
            if query_author:
                author_names = [a.get('name', '').lower() for a in authors]
                for i, author_name in enumerate(author_names):
                    if query_author in author_name:
                        if len(authors) == 1:
                            score += 50  # Sole author - huge bonus!
                        elif i == 0:
                            score += 30  # First author
                        elif i <= 2:
                            score += 15  # 2nd-3rd author
                        else:
                            score += 5   # 4th+ author
                        break
            
            # Title word overlap (secondary)
            title_words = set(title.split()) - stopwords
            exact_overlap = len(set(query_words) & title_words)
            score += exact_overlap * 3
            
            # Partial word matches
            for qword in query_words:
                if len(qword) >= 4:
                    for tword in title_words:
                        if qword[:4] in tword or tword[:4] in qword:
                            score += 2
            
            if score > best_score:
                best_score = score
                best_match = paper
        
        return best_match
    
    def _fetch_details(self, paper_id: str, raw_source: str, headers: dict) -> Optional[CitationMetadata]:
        """Fetch full paper details by ID."""
        params = {
            'fields': 'title,authors,venue,publicationVenue,year,volume,issue,pages,externalIds,url'
        }
        
        url = f"{self.details_url}{paper_id}"
        response = self._make_request(url, params=params, headers=headers)
        if not response:
            return None
        
        try:
            item = response.json()
            return self._normalize(item, raw_source)
        except:
            return None
    
    def _normalize(self, item: dict, raw_source: str) -> CitationMetadata:
        """Convert Semantic Scholar response to CitationMetadata."""
        # Extract authors - parse names into structured format
        authors = [a.get('name', '') for a in item.get('authors', []) if a.get('name')]
        authors_parsed = []
        for a in item.get('authors', []):
            name = a.get('name', '')
            if name:
                from models import parse_author_name
                authors_parsed.append(parse_author_name(name))
        
        # Get journal/venue
        venue = item.get('venue', '')
        pub_venue = item.get('publicationVenue', {}) or {}
        if pub_venue.get('name'):
            venue = pub_venue['name']
        
        # Get DOI from external IDs
        external_ids = item.get('externalIds', {}) or {}
        doi = external_ids.get('DOI', '')
        
        url = item.get('url', '')
        if not url and doi:
            url = f"https://doi.org/{doi}"
        
        return self._create_metadata(
            citation_type=CitationType.JOURNAL,
            raw_source=raw_source,
            title=item.get('title', ''),
            authors=authors,
            authors_parsed=authors_parsed,
            year=str(item.get('year', '')) if item.get('year') else None,
            journal=venue,
            volume=str(item.get('volume', '')) if item.get('volume') else '',
            issue=str(item.get('issue', '')) if item.get('issue') else '',
            pages=item.get('pages', ''),
            doi=doi,
            url=url,
            raw_data=item
        )


# =============================================================================
# PUBMED ENGINE
# =============================================================================

class PubMedEngine(SearchEngine):
    """
    Search PubMed / NCBI - biomedical literature.
    
    Excellent for:
    - Medical/clinical articles
    - PMID lookups
    - Life sciences
    
    UPDATED 2025-12-12: Fetches multiple results and scores by author-position.
    PubMed almost always HAS the correct paper — it might just not be first.
    """
    
    name = "PubMed"
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key=api_key or PUBMED_API_KEY, **kwargs)
    
    def search(self, query: str) -> Optional[CitationMetadata]:
        """
        Search PubMed with author-position scoring.
        
        Fetches multiple PMIDs and returns the one where query author
        is sole/first author.
        """
        # Get multiple PMIDs
        pmids = self._search_for_pmids(query, max_results=10)
        if not pmids:
            return None
        
        # If only one result, just return it
        if len(pmids) == 1:
            return self._fetch_details(pmids[0], query)
        
        # Fetch details for all and score by author-position
        candidates = []
        for pmid in pmids:
            result = self._fetch_details(pmid, query)
            if result:
                score = score_author_position(result.authors or [], query)
                candidates.append((score, result))
        
        if not candidates:
            return None
        
        # Sort by author-position score (highest first)
        candidates.sort(key=lambda x: x[0], reverse=True)
        
        best_score, best_result = candidates[0]
        print(f"[{self.name}] Selected PMID {best_result.pmid} (author-score: {best_score})")
        
        return best_result
    
    def _search_for_pmids(self, query: str, max_results: int = 10) -> List[str]:
        """
        Search PubMed and return list of PMIDs.
        """
        search_queries = self._build_pubmed_queries(query)
        
        for search_query in search_queries:
            params = {
                'db': 'pubmed',
                'term': search_query,
                'retmode': 'json',
                'retmax': max_results
            }
            if self.api_key:
                params['api_key'] = self.api_key
            
            response = self._make_request(f"{self.base_url}esearch.fcgi", params=params)
            if response:
                try:
                    data = response.json()
                    id_list = data.get('esearchresult', {}).get('idlist', [])
                    if id_list:
                        print(f"[{self.name}] Found {len(id_list)} results for: {search_query[:50]}...")
                        return id_list
                except:
                    pass
        
        return []
    
    def get_by_id(self, pmid: str) -> Optional[CitationMetadata]:
        """Look up by PMID directly."""
        pmid = re.sub(r'\D', '', pmid)
        return self._fetch_details(pmid, f"PMID:{pmid}")
    
    def _build_pubmed_queries(self, query: str) -> List[str]:
        """
        Build multiple PubMed query strategies.
        
        Handles "FirstName LastName keywords" patterns.
        """
        queries = []
        words = query.split()
        
        potential_author = None
        potential_first_name = None
        title_words = []
        
        # Detect "FirstName LastName keywords" pattern
        if len(words) >= 2:
            first_word = words[0].strip()
            second_word = words[1].strip()
            
            if first_word.lower() in COMMON_FIRST_NAMES:
                if second_word[0].isupper() and len(second_word) >= 3:
                    potential_first_name = first_word
                    potential_author = second_word
                    title_words = words[2:]
        
        # Fallback: scan for capitalized word as author
        if not potential_author:
            for word in words:
                if len(word) <= 2:
                    continue
                if word.isdigit() and len(word) == 4:
                    continue
                
                clean_word = re.sub(r'[^\w]', '', word)
                if clean_word and clean_word[0].isupper() and len(clean_word) >= 3:
                    common_title_words = {'the', 'and', 'for', 'from', 'with', 'new', 'study'}
                    if clean_word.lower() not in common_title_words and clean_word.lower() not in COMMON_FIRST_NAMES:
                        potential_author = clean_word
                
                title_words.append(word)
        
        # Build queries
        if potential_author and title_words:
            title_only = [w for w in title_words 
                          if w.lower() != potential_author.lower() 
                          and w.lower() != (potential_first_name or '').lower()]
            
            if title_only:
                # Strategy 1: Surname[au] + title words
                queries.append(f"{potential_author}[au] AND ({' '.join(title_only)}[ti])")
                
                # Strategy 2: First initial + surname
                if potential_first_name:
                    initial = potential_first_name[0].upper()
                    queries.append(f"{potential_author} {initial}[au] AND ({' '.join(title_only)}[ti])")
        
        # Strategy 3: All significant words in title/abstract
        significant_words = [w for w in words if len(w) >= 4 and not w.isdigit()]
        if significant_words:
            tiab_query = ' AND '.join([f"{w}[tiab]" for w in significant_words[:4]])
            if tiab_query:
                queries.append(tiab_query)
        
        # Strategy 4: Simple AND search
        queries.append(query)
        
        # Strategy 5: Just surname + significant title words
        if potential_author and title_words:
            title_only = [w for w in title_words 
                          if w.lower() != potential_author.lower() 
                          and w.lower() != (potential_first_name or '').lower()
                          and len(w) >= 4]
            if title_only:
                queries.append(f"{potential_author}[au] AND {' AND '.join(title_only[:3])}")
        
        return queries
    
    def _fetch_details(self, pmid: str, raw_source: str) -> Optional[CitationMetadata]:
        """Fetch article details using ESummary."""
        params = {
            'db': 'pubmed',
            'id': pmid,
            'retmode': 'json'
        }
        if self.api_key:
            params['api_key'] = self.api_key
        
        response = self._make_request(f"{self.base_url}esummary.fcgi", params=params)
        if not response:
            return None
        
        try:
            data = response.json()
            article = data.get('result', {}).get(pmid, {})
            if not article or 'error' in article:
                return None
            
            return self._normalize_summary(article, pmid, raw_source)
        except Exception as e:
            print(f"[{self.name}] Parse error: {e}")
            return None
    
    def _normalize_summary(self, article: dict, pmid: str, raw_source: str) -> CitationMetadata:
        """Convert PubMed ESummary response to CitationMetadata."""
        # Extract authors - parse PubMed format (e.g., "JAMES TG") into structured format
        authors = []
        authors_parsed = []
        author_list = article.get('authors', [])
        for author in author_list:
            name = author.get('name', '')
            if name:
                authors.append(name)
                # Parse the PubMed format name into given/family
                from models import parse_author_name
                authors_parsed.append(parse_author_name(name))
        
        # Extract year from pubdate
        year = None
        pubdate = article.get('pubdate', '')
        if pubdate:
            year_match = re.match(r'(\d{4})', pubdate)
            if year_match:
                year = year_match.group(1)
        
        # Get journal
        journal = article.get('fulljournalname', '') or article.get('source', '')
        
        # Get DOI from articleids
        doi = ''
        for aid in article.get('articleids', []):
            if aid.get('idtype') == 'doi':
                doi = aid.get('value', '')
                break
        
        # Build URL
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        
        return self._create_metadata(
            citation_type=CitationType.JOURNAL,
            raw_source=raw_source,
            title=article.get('title', ''),
            authors=authors,
            authors_parsed=authors_parsed,
            year=year,
            journal=journal,
            volume=article.get('volume', ''),
            issue=article.get('issue', ''),
            pages=article.get('pages', ''),
            doi=doi,
            url=url,
            pmid=pmid,
            raw_data=article
        )
