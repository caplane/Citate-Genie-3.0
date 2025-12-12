"""
citeflex/engines/generic_url_engine.py

Generic URL metadata extraction via HTML scraping.

This engine fetches a URL and extracts metadata from:
1. Open Graph tags (og:title, og:author, article:published_time, etc.)
2. Twitter Card tags (twitter:title, twitter:creator, etc.)
3. Standard meta tags (name="author", name="date", etc.)
4. Schema.org JSON-LD structured data
5. Fallback: <title>, bylines, etc.

This is the fallback engine for URLs that don't match specialized handlers.

Version History:
    2025-12-08: Initial creation
"""

import re
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from urllib.parse import urlparse

from engines.base import SearchEngine
from models import CitationMetadata, CitationType
from config import DEFAULT_HEADERS, NEWSPAPER_DOMAINS, GOV_AGENCY_MAP

# Try to import BeautifulSoup - it's a common dependency
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    print("[GenericURLEngine] BeautifulSoup not available - install with: pip install beautifulsoup4")


class GenericURLEngine(SearchEngine):
    """
    Generic URL metadata extractor.
    
    Fetches any URL and extracts citation metadata from HTML meta tags,
    Open Graph tags, and page content.
    
    This serves as:
    1. The fallback for URLs without specialized handlers
    2. The base implementation for NewspaperEngine, GovernmentEngine, etc.
    """
    
    name = "Generic URL"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Use browser-like headers to avoid being blocked
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })
    
    def search(self, query: str) -> Optional[CitationMetadata]:
        """
        For GenericURLEngine, search is the same as fetch_by_url.
        The query is expected to be a URL.
        """
        return self.fetch_by_url(query)
    
    def fetch_by_url(self, url: str) -> Optional[CitationMetadata]:
        """
        Fetch a URL and extract citation metadata.
        
        Args:
            url: The URL to fetch
            
        Returns:
            CitationMetadata with extracted information
        """
        if not HAS_BS4:
            print(f"[{self.name}] BeautifulSoup not available")
            return self._minimal_metadata(url)
        
        if not url:
            return None
        
        # Ensure URL has scheme
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        print(f"[{self.name}] Fetching: {url}")
        
        try:
            response = self._make_request(url)
            if not response:
                print(f"[{self.name}] Failed to fetch URL")
                return self._minimal_metadata(url)
            
            # Check content type - only parse HTML
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' not in content_type and 'application/xhtml' not in content_type:
                print(f"[{self.name}] Not HTML content: {content_type}")
                return self._minimal_metadata(url)
            
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract metadata from various sources
            metadata = self._extract_all_metadata(soup, url)
            
            # Determine citation type based on domain
            citation_type = self._determine_citation_type(url)
            
            # Build CitationMetadata
            return self._build_citation_metadata(metadata, url, citation_type)
            
        except Exception as e:
            print(f"[{self.name}] Error: {e}")
            return self._minimal_metadata(url)
    
    def _extract_all_metadata(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """
        Extract metadata from all available sources in the HTML.
        
        Priority order:
        1. JSON-LD structured data (most reliable)
        2. Open Graph tags
        3. Twitter Card tags
        4. Standard meta tags
        5. HTML content fallbacks
        """
        metadata = {
            'title': '',
            'authors': [],
            'date': '',
            'description': '',
            'site_name': '',
            'image': '',
            'type': '',
        }
        
        # 1. JSON-LD (Schema.org structured data)
        json_ld = self._extract_json_ld(soup)
        if json_ld:
            self._merge_json_ld(metadata, json_ld)
        
        # 2. Open Graph tags
        og_data = self._extract_open_graph(soup)
        self._merge_metadata(metadata, og_data)
        
        # 3. Twitter Card tags
        twitter_data = self._extract_twitter_card(soup)
        self._merge_metadata(metadata, twitter_data)
        
        # 4. Standard meta tags
        meta_data = self._extract_meta_tags(soup)
        self._merge_metadata(metadata, meta_data)
        
        # 5. HTML content fallbacks
        html_data = self._extract_html_fallbacks(soup, url)
        self._merge_metadata(metadata, html_data)
        
        return metadata
    
    def _extract_json_ld(self, soup: BeautifulSoup) -> Optional[Dict]:
        """Extract JSON-LD structured data."""
        scripts = soup.find_all('script', type='application/ld+json')
        
        for script in scripts:
            try:
                data = json.loads(script.string)
                
                # Handle @graph arrays
                if isinstance(data, dict) and '@graph' in data:
                    for item in data['@graph']:
                        if item.get('@type') in ['Article', 'NewsArticle', 'WebPage', 'BlogPosting']:
                            return item
                
                # Handle direct article data
                if isinstance(data, dict):
                    if data.get('@type') in ['Article', 'NewsArticle', 'WebPage', 'BlogPosting', 'Report']:
                        return data
                
                # Handle arrays
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get('@type') in ['Article', 'NewsArticle', 'WebPage', 'BlogPosting']:
                            return item
                            
            except (json.JSONDecodeError, TypeError):
                continue
        
        return None
    
    def _merge_json_ld(self, metadata: Dict, json_ld: Dict):
        """Merge JSON-LD data into metadata dict."""
        # Title
        if not metadata['title']:
            metadata['title'] = json_ld.get('headline') or json_ld.get('name', '')
        
        # Authors
        if not metadata['authors']:
            author = json_ld.get('author')
            if author:
                if isinstance(author, dict):
                    name = author.get('name', '')
                    if name:
                        metadata['authors'] = [name]
                elif isinstance(author, list):
                    names = []
                    for a in author:
                        if isinstance(a, dict):
                            name = a.get('name', '')
                            if name:
                                names.append(name)
                        elif isinstance(a, str):
                            names.append(a)
                    metadata['authors'] = names
                elif isinstance(author, str):
                    metadata['authors'] = [author]
        
        # Date
        if not metadata['date']:
            date_str = json_ld.get('datePublished') or json_ld.get('dateCreated', '')
            if date_str:
                metadata['date'] = self._normalize_date(date_str)
        
        # Publisher/site name
        if not metadata['site_name']:
            publisher = json_ld.get('publisher')
            if isinstance(publisher, dict):
                metadata['site_name'] = publisher.get('name', '')
            elif isinstance(publisher, str):
                metadata['site_name'] = publisher
        
        # Description
        if not metadata['description']:
            metadata['description'] = json_ld.get('description', '')
    
    def _extract_open_graph(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract Open Graph meta tags."""
        data = {}
        
        og_mappings = {
            'og:title': 'title',
            'og:description': 'description',
            'og:site_name': 'site_name',
            'og:image': 'image',
            'og:type': 'type',
            'article:author': 'author',
            'article:published_time': 'date',
            'article:modified_time': 'modified_date',
        }
        
        for og_prop, key in og_mappings.items():
            tag = soup.find('meta', property=og_prop)
            if tag and tag.get('content'):
                value = tag['content'].strip()
                if key == 'date':
                    value = self._normalize_date(value)
                if key == 'author':
                    data['authors'] = [value]
                else:
                    data[key] = value
        
        return data
    
    def _extract_twitter_card(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract Twitter Card meta tags."""
        data = {}
        
        twitter_mappings = {
            'twitter:title': 'title',
            'twitter:description': 'description',
            'twitter:creator': 'author',
            'twitter:site': 'site_name',
        }
        
        for tw_name, key in twitter_mappings.items():
            tag = soup.find('meta', attrs={'name': tw_name})
            if tag and tag.get('content'):
                value = tag['content'].strip()
                # Twitter handles start with @
                if key == 'author' and value.startswith('@'):
                    value = value[1:]  # Remove @ prefix
                    data['authors'] = [value]
                elif key == 'site_name' and value.startswith('@'):
                    value = value[1:]
                    data[key] = value
                else:
                    if key == 'author':
                        data['authors'] = [value]
                    else:
                        data[key] = value
        
        return data
    
    def _extract_meta_tags(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract standard HTML meta tags."""
        data = {}
        
        # Author
        author_tag = soup.find('meta', attrs={'name': 'author'})
        if author_tag and author_tag.get('content'):
            data['authors'] = [author_tag['content'].strip()]
        
        # Date variations
        date_names = ['date', 'pubdate', 'publish_date', 'article:published_time', 'DC.date.issued']
        for name in date_names:
            tag = soup.find('meta', attrs={'name': name})
            if tag and tag.get('content'):
                data['date'] = self._normalize_date(tag['content'].strip())
                break
        
        # Description
        desc_tag = soup.find('meta', attrs={'name': 'description'})
        if desc_tag and desc_tag.get('content'):
            data['description'] = desc_tag['content'].strip()
        
        return data
    
    def _extract_html_fallbacks(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Extract metadata from HTML content when meta tags are missing."""
        data = {}
        
        # Title from <title> tag
        title_tag = soup.find('title')
        if title_tag and title_tag.string:
            title = title_tag.string.strip()
            # Clean up title - remove site name suffix
            # e.g., "Article Title | The Atlantic" -> "Article Title"
            separators = [' | ', ' - ', ' – ', ' — ', ' :: ']
            for sep in separators:
                if sep in title:
                    parts = title.split(sep)
                    # Usually the article title is the first/longest part
                    title = max(parts, key=len).strip()
                    break
            data['title'] = title
        
        # Author from common byline patterns
        byline_selectors = [
            {'class_': re.compile(r'byline|author|writer', re.I)},
            {'itemprop': 'author'},
            {'rel': 'author'},
            {'class_': 'contributor'},
        ]
        
        for selector in byline_selectors:
            byline = soup.find(['span', 'div', 'a', 'p', 'address'], **selector)
            if byline:
                author_text = byline.get_text(strip=True)
                # Clean up "By John Smith" -> "John Smith"
                author_text = re.sub(r'^by\s+', '', author_text, flags=re.IGNORECASE)
                if author_text and len(author_text) < 100:  # Sanity check
                    data['authors'] = [author_text]
                    break
        
        # Date from <time> element
        time_tag = soup.find('time', datetime=True)
        if time_tag:
            data['date'] = self._normalize_date(time_tag['datetime'])
        
        # Site name from domain if not found elsewhere
        if 'site_name' not in data:
            try:
                parsed = urlparse(url)
                domain = parsed.netloc.replace('www.', '')
                # Check our known mappings
                if domain in NEWSPAPER_DOMAINS:
                    data['site_name'] = NEWSPAPER_DOMAINS[domain]
                elif domain in GOV_AGENCY_MAP:
                    data['site_name'] = GOV_AGENCY_MAP[domain]
                else:
                    # Title case the domain
                    data['site_name'] = domain.split('.')[0].title()
            except:
                pass
        
        return data
    
    def _merge_metadata(self, target: Dict, source: Dict):
        """Merge source into target, only filling empty fields."""
        for key, value in source.items():
            if not target.get(key):
                target[key] = value
    
    def _normalize_date(self, date_str: str) -> str:
        """
        Normalize date string to a standard format.
        
        Input formats:
        - ISO 8601: 2025-12-07T10:30:00Z
        - US format: December 7, 2025
        - Short: 2025-12-07
        
        Output: "December 7, 2025"
        """
        if not date_str:
            return ''
        
        date_str = date_str.strip()
        
        # Try ISO format first
        iso_patterns = [
            '%Y-%m-%dT%H:%M:%S%z',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d',
        ]
        
        for pattern in iso_patterns:
            try:
                dt = datetime.strptime(date_str[:len(date_str.split('.')[0])].replace('Z', '+0000'), pattern)
                return dt.strftime('%B %d, %Y').replace(' 0', ' ')
            except ValueError:
                continue
        
        # Try common text formats
        text_patterns = [
            '%B %d, %Y',  # December 7, 2025
            '%b %d, %Y',  # Dec 7, 2025
            '%d %B %Y',   # 7 December 2025
            '%d %b %Y',   # 7 Dec 2025
            '%m/%d/%Y',   # 12/07/2025
            '%d/%m/%Y',   # 07/12/2025
        ]
        
        for pattern in text_patterns:
            try:
                dt = datetime.strptime(date_str, pattern)
                return dt.strftime('%B %d, %Y').replace(' 0', ' ')
            except ValueError:
                continue
        
        # If we can't parse it, return as-is but try to extract year
        year_match = re.search(r'\b(19|20)\d{2}\b', date_str)
        if year_match:
            return date_str
        
        return date_str
    
    def _determine_citation_type(self, url: str) -> CitationType:
        """Determine citation type based on URL domain."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace('www.', '')
            
            # Newspaper
            for news_domain in NEWSPAPER_DOMAINS:
                if news_domain in domain:
                    return CitationType.NEWSPAPER
            
            # Government
            if '.gov' in domain:
                return CitationType.GOVERNMENT
            
            # Default to URL type
            return CitationType.URL
            
        except:
            return CitationType.URL
    
    def _build_citation_metadata(
        self,
        metadata: Dict[str, Any],
        url: str,
        citation_type: CitationType
    ) -> CitationMetadata:
        """Build CitationMetadata from extracted data."""
        
        # Get current date for access_date
        access_date = datetime.now().strftime('%B %d, %Y').replace(' 0', ' ')
        
        # Build base metadata
        result = CitationMetadata(
            citation_type=citation_type,
            raw_source=url,
            source_engine=self.name,
            title=metadata.get('title', ''),
            authors=metadata.get('authors', []),
            url=url,
            access_date=access_date,
            raw_data=metadata,
        )
        
        # Set type-specific fields
        if citation_type == CitationType.NEWSPAPER:
            result.newspaper = metadata.get('site_name', '')
            result.date = metadata.get('date', '')
        
        elif citation_type == CitationType.GOVERNMENT:
            result.agency = metadata.get('site_name', '')
            result.date = metadata.get('date', '')
        
        else:
            result.date = metadata.get('date', '')
        
        # Extract year if we have a date
        if metadata.get('date'):
            year_match = re.search(r'\b(19|20)\d{2}\b', metadata['date'])
            if year_match:
                result.year = year_match.group(0)
        
        return result
    
    def _minimal_metadata(self, url: str) -> CitationMetadata:
        """Return minimal metadata when we can't fetch/parse the URL."""
        access_date = datetime.now().strftime('%B %d, %Y').replace(' 0', ' ')
        
        return CitationMetadata(
            citation_type=self._determine_citation_type(url),
            raw_source=url,
            source_engine=f"{self.name} (minimal)",
            url=url,
            access_date=access_date,
        )


# =============================================================================
# SPECIALIZED SUBCLASSES
# =============================================================================

class NewspaperEngine(GenericURLEngine):
    """
    Specialized engine for newspaper/magazine articles.
    
    Inherits all functionality from GenericURLEngine but:
    - Always sets citation_type to NEWSPAPER
    - Prioritizes author/date extraction patterns common in news
    """
    
    name = "Newspaper"
    
    def _determine_citation_type(self, url: str) -> CitationType:
        """Newspapers always return NEWSPAPER type."""
        return CitationType.NEWSPAPER
    
    def _build_citation_metadata(
        self,
        metadata: Dict[str, Any],
        url: str,
        citation_type: CitationType
    ) -> CitationMetadata:
        """Build newspaper-specific metadata."""
        result = super()._build_citation_metadata(metadata, url, CitationType.NEWSPAPER)
        
        # Ensure newspaper field is set
        if not result.newspaper:
            try:
                parsed = urlparse(url)
                domain = parsed.netloc.lower().replace('www.', '')
                for news_domain, name in NEWSPAPER_DOMAINS.items():
                    if news_domain in domain:
                        result.newspaper = name
                        break
            except:
                pass
        
        return result


class GovernmentEngine(GenericURLEngine):
    """
    Specialized engine for government documents.
    
    Inherits all functionality from GenericURLEngine but:
    - Always sets citation_type to GOVERNMENT
    - Sets agency from GOV_AGENCY_MAP
    """
    
    name = "Government"
    
    def _determine_citation_type(self, url: str) -> CitationType:
        """Government URLs always return GOVERNMENT type."""
        return CitationType.GOVERNMENT
    
    def _build_citation_metadata(
        self,
        metadata: Dict[str, Any],
        url: str,
        citation_type: CitationType
    ) -> CitationMetadata:
        """Build government-specific metadata."""
        result = super()._build_citation_metadata(metadata, url, CitationType.GOVERNMENT)
        
        # Ensure agency field is set
        if not result.agency:
            try:
                from config import get_gov_agency
                parsed = urlparse(url)
                result.agency = get_gov_agency(parsed.netloc)
            except:
                pass
        
        return result
