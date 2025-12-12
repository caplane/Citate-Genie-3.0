"""
citeflex/engines/google_scholar.py

Google Scholar search via SerpAPI.
- Excellent coverage of academic literature
- Returns citation counts, links, BibTeX data
- Finds articles other APIs miss (like JSTOR-indexed content)
"""

from typing import Optional, List

from engines.base import SearchEngine
from models import CitationMetadata, CitationType
from config import SERPAPI_KEY

ENGINE_TIMEOUT = 10  # SerpAPI can be slower


class GoogleScholarEngine(SearchEngine):
    """
    Search Google Scholar via SerpAPI.
    
    Excellent for:
    - Broad academic coverage
    - JSTOR and other paywalled content metadata
    - Older publications
    - Citation counts
    """
    
    name = "Google Scholar"
    base_url = "https://serpapi.com/search"
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key=api_key or SERPAPI_KEY, **kwargs)
    
    def search(self, query: str) -> Optional[CitationMetadata]:
        """Search Google Scholar and return best match."""
        print(f"[{self.name}] Searching for: {query}")
        
        if not self.api_key:
            print(f"[{self.name}] No API key configured")
            return None
        
        print(f"[{self.name}] API key present (length: {len(self.api_key)})")
        
        params = {
            'engine': 'google_scholar',
            'q': query,
            'api_key': self.api_key,
            'num': 5  # Get a few results to find best match
        }
        
        response = self._make_request(self.base_url, params=params)
        if not response:
            print(f"[{self.name}] No response from API")
            return None
        
        print(f"[{self.name}] Got response, status: {response.status_code}")
        
        try:
            data = response.json()
            
            # Check for errors
            if 'error' in data:
                print(f"[{self.name}] API error: {data['error']}")
                return None
            
            results = data.get('organic_results', [])
            print(f"[{self.name}] Found {len(results)} results")
            
            if not results:
                return None
            
            # Find best match
            best = self._find_best_match(results, query)
            print(f"[{self.name}] Best match: {best.get('title', 'No title')[:50]}")
            return self._normalize(best, query)
            
        except Exception as e:
            print(f"[{self.name}] Parse error: {e}")
            return None
    
    def search_multiple(self, query: str, limit: int = 5) -> List[CitationMetadata]:
        """Return multiple results."""
        if not self.api_key:
            return []
        
        params = {
            'engine': 'google_scholar',
            'q': query,
            'api_key': self.api_key,
            'num': limit
        }
        
        response = self._make_request(self.base_url, params=params)
        if not response:
            return []
        
        try:
            data = response.json()
            results = data.get('organic_results', [])
            return [self._normalize(r, query) for r in results[:limit]]
        except:
            return []
    
    def _find_best_match(self, results: List[dict], query: str) -> dict:
        """Score results and return best match."""
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        best = results[0]
        best_score = 0
        
        for result in results:
            score = 0
            title = result.get('title', '').lower()
            
            # Check author match
            pub_info = result.get('publication_info', {})
            authors = pub_info.get('authors', [])
            for author in authors:
                author_name = author.get('name', '').lower()
                for name_part in author_name.split():
                    if len(name_part) >= 3 and name_part in query_lower:
                        score += 15
            
            # Check title word overlap
            title_words = set(title.split())
            overlap = len(query_words & title_words)
            score += overlap * 3
            
            # Bonus for exact phrase matches
            for word in query_words:
                if len(word) >= 4 and word in title:
                    score += 2
            
            if score > best_score:
                best_score = score
                best = result
        
        return best
    
    def _normalize(self, item: dict, raw_source: str) -> CitationMetadata:
        """Convert SerpAPI Google Scholar response to CitationMetadata."""
        
        # Extract publication info
        pub_info = item.get('publication_info', {})
        summary = pub_info.get('summary', '')  # e.g., "EM Caplan - Bulletin of the History of Medicine, 1995 - JSTOR"
        
        # Parse authors
        authors = []
        author_list = pub_info.get('authors', [])
        if author_list:
            authors = [a.get('name', '') for a in author_list if a.get('name')]
        
        # Parse summary for journal and year if not in structured data
        journal = ''
        year = None
        
        if summary:
            parts = summary.split(' - ')
            if len(parts) >= 2:
                # Second part usually has journal, year, source
                journal_part = parts[1] if len(parts) > 1 else ''
                
                # Extract year (4 digits)
                import re
                year_match = re.search(r'\b(19|20)\d{2}\b', summary)
                if year_match:
                    year = year_match.group(0)
                
                # Extract journal (before the year or comma)
                if journal_part:
                    # Remove source like "JSTOR", "Springer", etc.
                    journal_clean = re.split(r'\s*-\s*', journal_part)[0]
                    journal_clean = re.sub(r',?\s*(19|20)\d{2}.*', '', journal_clean)
                    journal = journal_clean.strip().strip(',').strip()
        
        # Get URL - prefer the link, fall back to result link
        url = item.get('link', '')
        
        # Check for resources (PDF links, etc.)
        resources = item.get('resources', [])
        pdf_url = ''
        for resource in resources:
            if resource.get('file_format') == 'PDF':
                pdf_url = resource.get('link', '')
                break
        
        # Get inline links for "Cited by" count
        cited_by = None
        inline_links = item.get('inline_links', {})
        cited_by_info = inline_links.get('cited_by', {})
        if cited_by_info:
            cited_by = cited_by_info.get('total')
        
        # Determine citation type based on content
        citation_type = CitationType.JOURNAL
        title = item.get('title', '')
        snippet = item.get('snippet', '').lower()
        
        if 'book' in snippet or '[book]' in title.lower():
            citation_type = CitationType.BOOK
        
        return self._create_metadata(
            citation_type=citation_type,
            raw_source=raw_source,
            title=title,
            authors=authors,
            year=year,
            journal=journal,
            doi='',  # Scholar doesn't always provide DOI directly
            url=url,
            raw_data={
                **item,
                'pdf_url': pdf_url,
                'cited_by': cited_by
            }
        )
