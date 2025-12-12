"""
citeflex/engines/wikipedia_engine.py

Wikipedia article metadata extraction via the MediaWiki API.

The Wikipedia API is free and requires no authentication.
Documentation: https://www.mediawiki.org/wiki/API:Main_page

Version History:
    2025-12-08: Initial creation
"""

import re
from typing import Optional
from datetime import datetime
from urllib.parse import urlparse, unquote

from engines.base import SearchEngine
from models import CitationMetadata, CitationType


class WikipediaEngine(SearchEngine):
    """
    Wikipedia article metadata engine.
    
    Uses the MediaWiki API to fetch metadata for Wikipedia articles.
    The API is free and requires no authentication.
    
    Handles:
    - Wikipedia URLs: en.wikipedia.org/wiki/Article_Title
    - Article titles directly
    - Multiple language editions
    """
    
    name = "Wikipedia"
    base_url = "https://en.wikipedia.org/w/api.php"
    
    def __init__(self, language: str = "en", **kwargs):
        """
        Initialize WikipediaEngine.
        
        Args:
            language: Wikipedia language code (default: "en")
        """
        super().__init__(**kwargs)
        self.language = language
        self.base_url = f"https://{language}.wikipedia.org/w/api.php"
    
    def search(self, query: str) -> Optional[CitationMetadata]:
        """
        Search Wikipedia by title.
        
        Args:
            query: Article title or search query
            
        Returns:
            CitationMetadata if found, None otherwise
        """
        # Check if query is a Wikipedia URL
        title = self._extract_title_from_url(query)
        if title:
            return self.get_by_id(title)
        
        # Otherwise search by title
        return self.get_by_id(query)
    
    def get_by_id(self, title: str) -> Optional[CitationMetadata]:
        """
        Fetch metadata by article title.
        
        Args:
            title: Wikipedia article title
            
        Returns:
            CitationMetadata if found, None otherwise
        """
        if not title:
            return None
        
        # Clean up title
        title = self._clean_title(title)
        print(f"[{self.name}] Fetching article: {title}")
        
        # Fetch page info and revision data
        params = {
            'action': 'query',
            'titles': title,
            'prop': 'info|revisions|pageprops',
            'rvprop': 'timestamp',
            'rvlimit': 1,
            'format': 'json',
            'redirects': 1,  # Follow redirects
        }
        
        response = self._make_request(self.base_url, params=params)
        if not response:
            return None
        
        try:
            data = response.json()
            pages = data.get('query', {}).get('pages', {})
            
            # Get the first (and only) page
            for page_id, page in pages.items():
                if page_id == '-1':
                    # Page not found
                    print(f"[{self.name}] Article not found: {title}")
                    return None
                
                return self._normalize(page, title)
            
            return None
            
        except Exception as e:
            print(f"[{self.name}] Parse error: {e}")
            return None
    
    def _extract_title_from_url(self, text: str) -> Optional[str]:
        """Extract Wikipedia article title from URL."""
        if not text:
            return None
        
        text = text.strip()
        
        # Check if it's a Wikipedia URL
        if 'wikipedia.org' not in text.lower():
            return None
        
        try:
            parsed = urlparse(text)
            
            # Extract language from subdomain
            domain = parsed.netloc.lower()
            lang_match = re.match(r'([a-z]{2,3})\.wikipedia\.org', domain)
            if lang_match:
                self.language = lang_match.group(1)
                self.base_url = f"https://{self.language}.wikipedia.org/w/api.php"
            
            # Extract title from path
            path = parsed.path
            if '/wiki/' in path:
                title = path.split('/wiki/')[-1]
                # URL decode and replace underscores
                title = unquote(title)
                title = title.replace('_', ' ')
                # Remove any fragment
                title = title.split('#')[0]
                return title
                
        except Exception:
            pass
        
        return None
    
    def _clean_title(self, title: str) -> str:
        """Clean and normalize article title."""
        if not title:
            return ""
        
        title = title.strip()
        
        # Replace underscores with spaces
        title = title.replace('_', ' ')
        
        # URL decode
        title = unquote(title)
        
        # Remove fragment
        title = title.split('#')[0]
        
        return title.strip()
    
    def _normalize(self, page: dict, raw_source: str) -> CitationMetadata:
        """Convert Wikipedia page data to CitationMetadata."""
        
        title = page.get('title', '')
        page_id = page.get('pageid', '')
        
        # Get last modified date from revisions
        last_modified = None
        year = None
        revisions = page.get('revisions', [])
        if revisions:
            timestamp = revisions[0].get('timestamp', '')
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    last_modified = dt.strftime('%B %d, %Y').replace(' 0', ' ')
                    year = str(dt.year)
                except:
                    pass
        
        # Build URL
        url_title = title.replace(' ', '_')
        url = f"https://{self.language}.wikipedia.org/wiki/{url_title}"
        
        # Access date
        access_date = datetime.now().strftime('%B %d, %Y').replace(' 0', ' ')
        
        # Wikipedia is a special citation type - usually cited as URL/website
        # But we'll use URL type with appropriate fields
        return self._create_metadata(
            citation_type=CitationType.URL,
            raw_source=raw_source,
            title=title,
            authors=[],  # Wikipedia has no single author
            year=year,
            url=url,
            date=last_modified,
            access_date=access_date,
            raw_data={
                'page': page,
                'language': self.language,
                'page_id': page_id,
                'source': 'Wikipedia',
            }
        )


class WikipediaSearchEngine(WikipediaEngine):
    """
    Extended Wikipedia engine with full-text search capability.
    
    Use this when you need to search Wikipedia by content,
    not just by exact title.
    """
    
    name = "Wikipedia Search"
    
    def search(self, query: str) -> Optional[CitationMetadata]:
        """
        Search Wikipedia by content.
        
        Args:
            query: Search query
            
        Returns:
            CitationMetadata for best matching article
        """
        # First check if it's a URL or exact title
        title = self._extract_title_from_url(query)
        if title:
            return self.get_by_id(title)
        
        # Try exact title match first
        result = self.get_by_id(query)
        if result and result.title:
            return result
        
        # Fall back to search
        print(f"[{self.name}] Searching for: {query}")
        
        params = {
            'action': 'query',
            'list': 'search',
            'srsearch': query,
            'srlimit': 5,
            'format': 'json',
        }
        
        response = self._make_request(self.base_url, params=params)
        if not response:
            return None
        
        try:
            data = response.json()
            results = data.get('query', {}).get('search', [])
            
            if not results:
                return None
            
            # Get the first (best) result
            best = results[0]
            return self.get_by_id(best['title'])
            
        except Exception as e:
            print(f"[{self.name}] Search error: {e}")
            return None
