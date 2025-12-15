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
from engines.gov_ngo_domains import get_org_author as get_org_author_from_cache

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
        6. Deep fallbacks (URL parsing, content analysis, etc.)
        """
        metadata = {
            'title': '',
            'authors': [],
            'date': '',
            'year': '',
            'description': '',
            'site_name': '',
            'image': '',
            'type': '',
            # Academic/journal fields
            'volume': '',
            'issue': '',
            'pages': '',
            'doi': '',
            'journal': '',
            # Document classification
            'document_type': '',
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
        
        # 6. Deep fallbacks for missing critical fields
        self._apply_deep_fallbacks(metadata, soup, url)
        
        return metadata
    
    def _apply_deep_fallbacks(self, metadata: Dict, soup: BeautifulSoup, url: str):
        """
        Apply intelligent fallback strategies for missing metadata.
        
        These are "deep" extractions that go beyond standard meta tags,
        analyzing URL structure, page content, and applying heuristics.
        """
        # Clean title (remove site name suffix)
        if metadata['title'] and metadata['site_name']:
            metadata['title'] = self._clean_title(metadata['title'], metadata['site_name'])
        
        # Date fallback: extract from URL, title, or page content
        if not metadata['date']:
            fallback_date = self._extract_date_fallback(url, metadata, soup)
            if fallback_date:
                metadata['date'] = fallback_date
        
        # Extract year from date if we have one
        if metadata['date'] and not metadata['year']:
            year_match = re.search(r'\b(19|20)\d{2}\b', metadata['date'])
            if year_match:
                metadata['year'] = year_match.group(0)
        
        # DOI discovery: check URL, meta tags, page content
        if not metadata['doi']:
            found_doi = self._discover_doi(url, soup)
            if found_doi:
                metadata['doi'] = found_doi
        
        # Volume/Issue extraction for academic content
        if not metadata['volume']:
            vol_issue = self._extract_volume_issue(url, soup)
            metadata.update({k: v for k, v in vol_issue.items() if v and not metadata.get(k)})
        
        # Document type inference
        if not metadata['document_type']:
            metadata['document_type'] = self._infer_document_type(url, metadata, soup)
    
    def _clean_title(self, title: str, site_name: str) -> str:
        """
        Remove site name suffixes from title.
        
        Examples:
            "Determining Rights - Harvard Law Review" → "Determining Rights"
            "CDC Report | Centers for Disease Control" → "CDC Report"
            "Policy Brief :: Brookings Institution" → "Policy Brief"
            "Cost-Benefit Analysis - A New Approach - Economics Journal" → "Cost-Benefit Analysis - A New Approach"
        
        Safety: Won't strip if result would be too short or if title IS the site name.
        """
        if not title:
            return title
        
        original_title = title
        separators = [' | ', ' - ', ' – ', ' — ', ' :: ', ' · ', ' // ']
        
        for sep in separators:
            if sep in title:
                parts = title.split(sep)
                # Remove parts that match or contain site name
                cleaned_parts = []
                site_lower = site_name.lower() if site_name else ''
                
                for part in parts:
                    part = part.strip()
                    # Skip if this part is the site name
                    if site_lower and site_lower in part.lower():
                        continue
                    # Skip common suffixes
                    if part.lower() in ['home', 'homepage', 'official site', 'official website']:
                        continue
                    cleaned_parts.append(part)
                
                if cleaned_parts:
                    # Join remaining parts back together (preserves multi-part titles)
                    cleaned = sep.join(cleaned_parts)
                    
                    # SAFETY GUARD: Don't return if result is too short
                    # This prevents over-stripping titles like "AB - Site Name"
                    if len(cleaned) < 10 and len(original_title) > 20:
                        return original_title
                    
                    # SAFETY GUARD: Don't return if we stripped too much
                    # If we removed more than 70% of the title, probably wrong
                    if len(cleaned) < len(original_title) * 0.3:
                        return original_title
                    
                    return cleaned
        
        return title
    
    def _is_valid_publication_year(self, year: str) -> bool:
        """
        Validate that a year is reasonable for a publication date.
        
        Guards against:
        - Future dates (conference announcements, etc.)
        - Ancient dates (historical references in titles)
        - Non-year numbers that happen to be 4 digits
        
        Valid range: 1990 to current year (academic web content unlikely before 1990)
        """
        try:
            y = int(year)
            current_year = datetime.now().year
            # Allow 1990 onwards (web content era) up to current year
            # No future dates - those are likely events, not publication dates
            return 1990 <= y <= current_year
        except (ValueError, TypeError):
            return False
    
    def _extract_date_fallback(self, url: str, metadata: Dict, soup: BeautifulSoup) -> Optional[str]:
        """
        Extract date from URL patterns, title, or page content when meta tags fail.
        
        Strategies:
        1. URL path patterns: /2025/02/11/ or /2025-02-11/
        2. URL year patterns: /2024/ or /reports/2024/
        3. Title contains year: "2024 Annual Report"
        4. Filename patterns: report-2024.pdf, annual-report-2023.html
        5. Page content: copyright notices, "Published: ..." text
        6. HTTP headers (if available in raw_data)
        
        All years are validated to be in reasonable range (1990-current).
        """
        url_lower = url.lower()
        
        # Strategy 1: Full date in URL path
        # Matches: /2025/02/11/ or /2025-02-11/ or /20250211/
        date_patterns = [
            r'/(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?:/|$|\?)',  # /2025/02/11/ or /2025-02-11/
            r'/(\d{4})(\d{2})(\d{2})(?:/|$|\?)',               # /20250211/
            r'[/\-](\d{4})-(\d{2})-(\d{2})[/.\-]',             # -2025-02-11- or .2025-02-11.
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, url)
            if match:
                year, month, day = match.groups()
                # VALIDATION: Check year is reasonable
                if not self._is_valid_publication_year(year):
                    continue
                try:
                    # Validate it's a real date
                    dt = datetime(int(year), int(month), int(day))
                    return self._normalize_date(f"{year}-{month}-{day}")
                except ValueError:
                    continue
        
        # Strategy 2: Year + month in URL
        # Matches: /2024/february/ or /2024-02/
        year_month_patterns = [
            r'/(\d{4})[/-](january|february|march|april|may|june|july|august|september|october|november|december)',
            r'/(\d{4})[/-](\d{1,2})(?:/|$|\?)',  # /2024/02/ (month only, no day)
        ]
        
        month_names = {
            'january': '01', 'february': '02', 'march': '03', 'april': '04',
            'may': '05', 'june': '06', 'july': '07', 'august': '08',
            'september': '09', 'october': '10', 'november': '11', 'december': '12'
        }
        
        for pattern in year_month_patterns:
            match = re.search(pattern, url_lower)
            if match:
                year = match.group(1)
                # VALIDATION: Check year is reasonable
                if not self._is_valid_publication_year(year):
                    continue
                month = match.group(2)
                if month.isdigit():
                    if 1 <= int(month) <= 12:
                        return f"{year}"  # Just return year if we only have month
                else:
                    return f"{month.capitalize()} {year}"
        
        # Strategy 3: Year only in URL path
        # Matches: /2024/ or /reports/2024/ or /annual-report-2024
        year_match = re.search(r'[/-](20[12]\d)(?:[/-]|$|\?|\.)', url)
        if year_match:
            year = year_match.group(1)
            # VALIDATION: Check year is reasonable
            if self._is_valid_publication_year(year):
                return year
        
        # Strategy 4: Year in title
        title = metadata.get('title', '')
        title_year = re.search(r'\b(20[012]\d)\b', title)
        if title_year:
            year = title_year.group(1)
            # VALIDATION: Check year is reasonable
            if self._is_valid_publication_year(year):
                # Check if it looks like a publication year (not a random number)
                year_indicators = ['report', 'annual', 'fiscal', 'fy', 'edition', 'update', 'review', 'survey']
                if any(ind in title.lower() for ind in year_indicators):
                    return year
        
        # Strategy 5: Look for date in page content
        # Common patterns: "Published: March 15, 2024" or "Date: 2024-03-15"
        date_labels = soup.find_all(['span', 'time', 'p', 'div'], 
                                     string=re.compile(r'(published|posted|date|updated|released)\s*:?\s*', re.I))
        for label in date_labels[:5]:  # Check first 5 matches
            text = label.get_text()
            # Try to find a date after the label
            date_match = re.search(
                r'(?:published|posted|date|updated|released)\s*:?\s*'
                r'(\w+\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2})',
                text, re.I
            )
            if date_match:
                date_str = date_match.group(1)
                # VALIDATION: Extract and check year
                year_in_date = re.search(r'(20[012]\d)', date_str)
                if year_in_date and self._is_valid_publication_year(year_in_date.group(1)):
                    return self._normalize_date(date_str)
        
        # Strategy 6: Look for structured date elements
        date_elem = soup.find(['span', 'div', 'p'], class_=re.compile(r'date|publish|posted|timestamp', re.I))
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            # Try to parse various formats
            date_match = re.search(r'(\w+\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2})', date_text)
            if date_match:
                date_str = date_match.group(1)
                # VALIDATION: Extract and check year
                year_in_date = re.search(r'(20[012]\d)', date_str)
                if year_in_date and self._is_valid_publication_year(year_in_date.group(1)):
                    return self._normalize_date(date_str)
        
        # Strategy 7: Copyright year as last resort (only gives year)
        copyright_match = re.search(r'©\s*(20[012]\d)|copyright\s*(20[012]\d)', 
                                    soup.get_text()[:5000].lower())  # Check first 5000 chars
        if copyright_match:
            year = copyright_match.group(1) or copyright_match.group(2)
            # VALIDATION: Must be valid AND recent (within last 2 years)
            current_year = datetime.now().year
            if self._is_valid_publication_year(year) and int(year) >= current_year - 1:
                return year
        
        return None
    
    def _discover_doi(self, url: str, soup: BeautifulSoup) -> Optional[str]:
        """
        Discover DOI from various sources.
        
        DOIs are critical because they enable authoritative database lookups.
        This method searches for DOIs in order of reliability.
        
        All DOIs are validated for proper format before returning.
        """
        doi_pattern = r'10\.\d{4,}/[^\s"\'<>]+'
        
        # Strategy 1: DOI in URL
        if 'doi.org/' in url:
            match = re.search(r'doi\.org/(10\.\d+/[^\s?#]+)', url)
            if match:
                cleaned = self._clean_doi(match.group(1))
                if self._is_valid_doi(cleaned):
                    return cleaned
        
        # Also check for DOI parameter in URL
        doi_param = re.search(r'[?&]doi=(10\.\d+/[^&\s]+)', url)
        if doi_param:
            cleaned = self._clean_doi(doi_param.group(1))
            if self._is_valid_doi(cleaned):
                return cleaned
        
        # Strategy 2: Meta tags (most reliable for academic content)
        doi_meta_names = [
            'citation_doi',
            'DC.identifier',
            'DC.Identifier',
            'dc.identifier',
            'prism.doi',
            'bepress_citation_doi',
        ]
        
        for name in doi_meta_names:
            tag = soup.find('meta', attrs={'name': name})
            if tag and tag.get('content'):
                content = tag['content'].strip()
                if '10.' in content:
                    # Extract DOI from content (might have prefix like "doi:")
                    match = re.search(doi_pattern, content)
                    if match:
                        cleaned = self._clean_doi(match.group(0))
                        if self._is_valid_doi(cleaned):
                            return cleaned
        
        # Strategy 3: Link with DOI
        doi_links = soup.find_all('a', href=re.compile(r'doi\.org/10\.'))
        for link in doi_links[:3]:
            href = link.get('href', '')
            match = re.search(r'doi\.org/(10\.\d+/[^\s?#]+)', href)
            if match:
                cleaned = self._clean_doi(match.group(1))
                if self._is_valid_doi(cleaned):
                    return cleaned
        
        # Strategy 4: DOI in page content (look for labeled DOIs)
        # Common patterns: "DOI: 10.1234/..." or "https://doi.org/10.1234/..."
        doi_labels = soup.find_all(string=re.compile(r'DOI\s*:', re.I))
        for label in doi_labels[:3]:
            parent = label.parent if label.parent else label
            text = parent.get_text() if hasattr(parent, 'get_text') else str(parent)
            match = re.search(doi_pattern, text)
            if match:
                cleaned = self._clean_doi(match.group(0))
                if self._is_valid_doi(cleaned):
                    return cleaned
        
        # Strategy 5: Look in citation/reference sections
        cite_sections = soup.find_all(['div', 'section', 'aside'], 
                                       class_=re.compile(r'citation|cite|reference|doi', re.I))
        for section in cite_sections[:3]:
            text = section.get_text()
            match = re.search(doi_pattern, text)
            if match:
                cleaned = self._clean_doi(match.group(0))
                if self._is_valid_doi(cleaned):
                    return cleaned
        
        return None
    
    def _clean_doi(self, doi: str) -> str:
        """Clean and normalize a DOI string."""
        # Remove common prefixes
        doi = re.sub(r'^(doi:|DOI:|https?://doi\.org/|https?://dx\.doi\.org/)', '', doi)
        # Remove trailing punctuation
        doi = doi.rstrip('.,;:)')
        return doi.strip()
    
    def _is_valid_doi(self, doi: str) -> bool:
        """
        Validate that a DOI has proper format.
        
        Valid DOI format: 10.PREFIX/SUFFIX
        - Must start with "10."
        - Prefix is 4+ digits (registrant code)
        - Suffix can contain alphanumerics, dots, dashes, underscores, etc.
        - Total length typically 10-100 characters
        
        Guards against:
        - Random numbers that match the pattern loosely
        - Truncated DOIs
        - Malformed DOIs with invalid characters
        """
        if not doi:
            return False
        
        # Must start with 10.
        if not doi.startswith('10.'):
            return False
        
        # Must have a slash separating prefix and suffix
        if '/' not in doi:
            return False
        
        # Split into prefix and suffix
        parts = doi.split('/', 1)
        if len(parts) != 2:
            return False
        
        prefix, suffix = parts
        
        # Prefix must be 10.XXXX where XXXX is 4+ digits
        prefix_match = re.match(r'^10\.(\d{4,})$', prefix)
        if not prefix_match:
            return False
        
        # Suffix must exist and be reasonable length
        if not suffix or len(suffix) < 2:
            return False
        
        # Suffix shouldn't contain obviously invalid characters
        # Note: <> are valid in SICI-format DOIs (e.g., 10.1002/(SICI)...85:1<1::AID-CNCR1>3.0.CO;2-1)
        # Only reject quotes, backslashes, pipes, and brackets which are never valid
        if re.search(r'["\'\\|{}\[\]]', suffix):
            return False
        
        # Total DOI shouldn't be excessively long (likely captured extra text)
        if len(doi) > 100:
            return False
        
        return True
    
    def _is_valid_volume(self, volume: str) -> bool:
        """
        Validate that a volume number is reasonable.
        
        Guards against:
        - Article IDs mistaken for volumes (e.g., 123456)
        - Random numbers from URLs
        - Zero or negative numbers
        
        Reasonable range: 1-500 (few journals exceed 200+ volumes)
        """
        try:
            v = int(volume)
            return 1 <= v <= 500
        except (ValueError, TypeError):
            return False
    
    def _is_valid_issue(self, issue: str) -> bool:
        """
        Validate that an issue number is reasonable.
        
        Reasonable range: 1-52 (weekly journals max, most are 1-12)
        """
        try:
            i = int(issue)
            return 1 <= i <= 52
        except (ValueError, TypeError):
            return False
    
    def _is_valid_page(self, page: str) -> bool:
        """
        Validate that a page number is reasonable.
        
        Reasonable range: 1-9999 (some law reviews go high, but not 5+ digits)
        """
        try:
            p = int(page)
            return 1 <= p <= 9999
        except (ValueError, TypeError):
            return False
    
    def _extract_volume_issue(self, url: str, soup: BeautifulSoup) -> Dict[str, str]:
        """
        Extract volume, issue, and page numbers for academic journals.
        
        These details are critical for proper academic citations but
        often missing from standard metadata.
        
        All values are validated to be in reasonable ranges.
        """
        result = {}
        url_lower = url.lower()
        
        # Strategy 1: Meta tags (most reliable)
        meta_mappings = {
            'citation_volume': 'volume',
            'citation_issue': 'issue',
            'citation_firstpage': 'first_page',
            'citation_lastpage': 'last_page',
            'prism.volume': 'volume',
            'prism.number': 'issue',
            'prism.startingPage': 'first_page',
            'prism.endingPage': 'last_page',
        }
        
        for meta_name, field in meta_mappings.items():
            tag = soup.find('meta', attrs={'name': meta_name})
            if tag and tag.get('content'):
                value = tag['content'].strip()
                # VALIDATION: Check if value is in reasonable range
                if field == 'volume' and not self._is_valid_volume(value):
                    continue
                if field == 'issue' and not self._is_valid_issue(value):
                    continue
                if field in ['first_page', 'last_page'] and not self._is_valid_page(value):
                    continue
                result[field] = value
        
        # Combine first_page and last_page into pages
        if result.get('first_page'):
            if result.get('last_page'):
                result['pages'] = f"{result['first_page']}-{result['last_page']}"
            else:
                result['pages'] = result['first_page']
        
        # Strategy 2: URL patterns
        # /vol-138/ or /volume/42/ or /v25/
        if not result.get('volume'):
            vol_patterns = [
                r'/vol(?:ume)?[/-]?(\d+)',
                r'/v(\d+)(?:/|n|$)',
                r'volume[=:](\d+)',
            ]
            for pattern in vol_patterns:
                match = re.search(pattern, url_lower)
                if match:
                    vol = match.group(1)
                    # VALIDATION: Check volume is reasonable
                    if self._is_valid_volume(vol):
                        result['volume'] = vol
                    break
        
        # /issue-4/ or /issue/3/ or /no-2/ or /n2/
        if not result.get('issue'):
            issue_patterns = [
                r'/issue[/-]?(\d+)',
                r'/no[/-]?(\d+)',
                r'/n(\d+)(?:/|$)',
                r'[?&]issue[=:](\d+)',
            ]
            for pattern in issue_patterns:
                match = re.search(pattern, url_lower)
                if match:
                    iss = match.group(1)
                    # VALIDATION: Check issue is reasonable
                    if self._is_valid_issue(iss):
                        result['issue'] = iss
                    break
        
        # Strategy 3: Citation strings in page content
        # "138 Harv. L. Rev. 921" or "42 Yale L.J. 1234"
        citation_patterns = [
            # Standard law review format: "138 Harv. L. Rev. 921"
            r'(\d+)\s+\w+\.?\s*L\.?\s*(?:Rev|J)\.?\s*(\d+)',
            # Journal format: "Vol. 42, No. 3, pp. 123-145"
            r'Vol\.?\s*(\d+),?\s*No\.?\s*(\d+)',
            # Page format: "pp. 123-145" or "pages 123-145"
            r'(?:pp?\.?|pages?)\s*(\d+)(?:\s*[-–]\s*(\d+))?',
        ]
        
        # Look in citation/header areas
        cite_areas = soup.find_all(['span', 'div', 'p'], 
                                   class_=re.compile(r'citation|cite|volume|issue|header', re.I))
        page_text = ' '.join(area.get_text() for area in cite_areas[:10])
        
        if not result.get('volume'):
            for pattern in citation_patterns[:2]:
                match = re.search(pattern, page_text)
                if match:
                    vol = match.group(1)
                    # VALIDATION: Check volume is reasonable
                    if self._is_valid_volume(vol):
                        result['volume'] = vol
                        if len(match.groups()) > 1 and match.group(2):
                            iss_or_page = match.group(2)
                            # For law review format, second group is page, not issue
                            # For journal format, second group is issue
                            if 'Vol' in pattern:
                                if not result.get('issue') and self._is_valid_issue(iss_or_page):
                                    result['issue'] = iss_or_page
                    break
        
        # Strategy 4: Look for explicit volume/issue labels
        vol_elem = soup.find(string=re.compile(r'volume\s*:?\s*\d+', re.I))
        if vol_elem and not result.get('volume'):
            match = re.search(r'volume\s*:?\s*(\d+)', str(vol_elem), re.I)
            if match:
                vol = match.group(1)
                # VALIDATION: Check volume is reasonable
                if self._is_valid_volume(vol):
                    result['volume'] = vol
        
        issue_elem = soup.find(string=re.compile(r'issue\s*:?\s*\d+', re.I))
        if issue_elem and not result.get('issue'):
            match = re.search(r'issue\s*:?\s*(\d+)', str(issue_elem), re.I)
            if match:
                iss = match.group(1)
                # VALIDATION: Check issue is reasonable
                if self._is_valid_issue(iss):
                    result['issue'] = iss
        
        return result
    
    def _infer_document_type(self, url: str, metadata: Dict, soup: BeautifulSoup) -> str:
        """
        Infer document type from URL patterns, title, and content.
        
        Document type affects citation format:
        - Reports require publisher/organization
        - Press releases need date prominently
        - Blog posts are cited differently than articles
        - Government documents have special formats
        """
        url_lower = url.lower()
        title_lower = metadata.get('title', '').lower()
        description = metadata.get('description', '').lower()
        combined = f"{url_lower} {title_lower} {description}"
        
        # Define document type patterns
        # Each type has URL patterns, title keywords, and priority
        type_patterns = {
            'report': {
                'url': ['/report/', '/reports/', '/publication/', '/publications/', 
                        '/research/', '/paper/', '/papers/', '/brief/', '/briefs/',
                        '/working-paper/', '/whitepaper/', '/white-paper/'],
                'title': ['report', 'annual report', 'technical report', 'research report',
                          'policy brief', 'issue brief', 'working paper', 'white paper',
                          'study', 'analysis', 'assessment', 'evaluation'],
                'priority': 2,
            },
            'press_release': {
                'url': ['/press-release/', '/press/', '/newsroom/', '/media-center/',
                        '/news-release/', '/media-release/', '/announcements/'],
                'title': ['press release', 'news release', 'media release', 'announces',
                          'statement by', 'statement from', 'statement on'],
                'priority': 1,
            },
            'blog_post': {
                'url': ['/blog/', '/blogs/', '/posts/', '/insights/', '/perspectives/',
                        '/commentary/', '/opinion/', '/op-ed/'],
                'title': ['blog', 'opinion', 'commentary', 'perspective', 'op-ed'],
                'priority': 3,
            },
            'news_article': {
                'url': ['/news/', '/article/', '/story/', '/stories/'],
                'title': [],  # News determined more by domain than title
                'priority': 4,
            },
            'academic_article': {
                'url': ['/article/', '/print/', '/journal/', '/full/', '/abs/',
                        '/doi/', '/abstract/', '/fulltext/'],
                'title': ['journal', 'abstract'],
                'priority': 2,
            },
            'fact_sheet': {
                'url': ['/fact-sheet/', '/factsheet/', '/facts/', '/faq/'],
                'title': ['fact sheet', 'factsheet', 'key facts', 'quick facts'],
                'priority': 1,
            },
            'testimony': {
                'url': ['/testimony/', '/hearing/', '/statement/'],
                'title': ['testimony', 'statement before', 'hearing on', 'testifies'],
                'priority': 1,
            },
            'speech': {
                'url': ['/speech/', '/speeches/', '/remarks/', '/address/'],
                'title': ['speech', 'remarks by', 'address by', 'remarks at'],
                'priority': 1,
            },
            'legislation': {
                'url': ['/bill/', '/bills/', '/law/', '/statute/', '/regulation/',
                        '/rule/', '/act/'],
                'title': ['bill', 'act of', 'public law', 'regulation', 'rule'],
                'priority': 1,
            },
            'interview': {
                'url': ['/interview/', '/interviews/', '/qa/', '/q-and-a/'],
                'title': ['interview', 'q&a', 'conversation with'],
                'priority': 2,
            },
            'dataset': {
                'url': ['/data/', '/dataset/', '/datasets/', '/statistics/'],
                'title': ['data', 'dataset', 'statistics', 'survey results'],
                'priority': 2,
            },
        }
        
        # Score each document type
        scores = {}
        for doc_type, patterns in type_patterns.items():
            score = 0
            
            # Check URL patterns
            for pattern in patterns['url']:
                if pattern in url_lower:
                    score += 3  # URL match is strong signal
                    break
            
            # Check title/description keywords
            for keyword in patterns['title']:
                if keyword in combined:
                    score += 2
                    break
            
            if score > 0:
                scores[doc_type] = score
        
        # Additional heuristics
        
        # Check if it's from a newspaper domain
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.lower().replace('www.', '')
            if domain in NEWSPAPER_DOMAINS:
                scores['news_article'] = scores.get('news_article', 0) + 5
        except:
            pass
        
        # Government documents
        if '.gov' in url_lower:
            if 'report' in combined:
                scores['report'] = scores.get('report', 0) + 2
            elif 'testimony' in combined or 'hearing' in combined:
                scores['testimony'] = scores.get('testimony', 0) + 2
        
        # Academic journals (check for volume/issue indicators)
        if metadata.get('volume') or metadata.get('doi'):
            scores['academic_article'] = scores.get('academic_article', 0) + 3
        
        # Return highest scoring type, or 'webpage' as default
        if scores:
            return max(scores, key=scores.get)
        
        return 'webpage'
    
    def _extract_json_ld(self, soup: BeautifulSoup) -> Optional[Dict]:
        """Extract JSON-LD structured data."""
        scripts = soup.find_all('script', type='application/ld+json')
        
        # Types we recognize as articles
        article_types = ['Article', 'NewsArticle', 'WebPage', 'BlogPosting', 
                         'ScholarlyArticle', 'Report', 'TechArticle', 'Review']
        
        for script in scripts:
            try:
                data = json.loads(script.string)
                
                # Handle @graph arrays
                if isinstance(data, dict) and '@graph' in data:
                    for item in data['@graph']:
                        if item.get('@type') in article_types:
                            return item
                
                # Handle direct article data
                if isinstance(data, dict):
                    if data.get('@type') in article_types:
                        return data
                
                # Handle arrays
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get('@type') in article_types:
                            return item
                            
            except (json.JSONDecodeError, TypeError):
                continue
        
        return None
    
    def _merge_json_ld(self, metadata: Dict, json_ld: Dict):
        """Merge JSON-LD data into metadata dict."""
        # Title
        if not metadata['title']:
            metadata['title'] = json_ld.get('headline') or json_ld.get('name', '')
        
        # Authors - validate names to filter out site handles like "hlr"
        if not metadata['authors']:
            author = json_ld.get('author')
            if author:
                if isinstance(author, dict):
                    name = author.get('name', '')
                    if name and self._is_valid_author_name(name):
                        metadata['authors'] = [name]
                elif isinstance(author, list):
                    names = []
                    for a in author:
                        if isinstance(a, dict):
                            name = a.get('name', '')
                            if name and self._is_valid_author_name(name):
                                names.append(name)
                        elif isinstance(a, str):
                            if self._is_valid_author_name(a):
                                names.append(a)
                    if names:
                        metadata['authors'] = names
                elif isinstance(author, str):
                    if self._is_valid_author_name(author):
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
                    # Reject URLs - they're not author names (e.g., https://thenation.com/authors)
                    if value and not value.startswith('http'):
                        # Validate it looks like a real author name
                        if self._is_valid_author_name(value):
                            data['authors'] = [value]
                elif key == 'title':
                    # Clean site name suffix from title (e.g., " | The Nation")
                    separators = [' | ', ' - ', ' – ', ' — ', ' :: ']
                    for sep in separators:
                        if sep in value:
                            parts = value.split(sep)
                            # Usually the article title is the first/longest part
                            value = max(parts, key=len).strip()
                            break
                    data[key] = value
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
                # Reject URLs - they're not author names
                if key == 'author' and value.startswith('http'):
                    continue
                # Twitter handles start with @
                if key == 'author' and value.startswith('@'):
                    value = value[1:]  # Remove @ prefix
                    # Filter out site handles that aren't real author names
                    # Real author names are usually:
                    # - At least 4 characters
                    # - Contain a space or capital letter (not all lowercase abbreviations)
                    # - Not common publication abbreviations
                    if not self._is_valid_author_name(value):
                        continue
                    data['authors'] = [value]
                elif key == 'site_name' and value.startswith('@'):
                    value = value[1:]
                    data[key] = value
                else:
                    if key == 'author':
                        if self._is_valid_author_name(value):
                            data['authors'] = [value]
                    else:
                        data[key] = value
        
        return data
    
    def _is_valid_author_name(self, name: str) -> bool:
        """
        Check if a string looks like a valid author name vs a site handle/abbreviation.
        
        Filters out:
        - Very short strings (likely abbreviations like 'hlr', 'nyt')
        - All-lowercase strings without spaces (likely handles)
        - Common publication abbreviations
        - Law review abbreviation patterns (XxxLRev, XxxLJ, etc.)
        """
        if not name:
            return False
        
        # Too short to be a real name
        if len(name) < 4:
            return False
        
        # All lowercase without spaces is likely a handle/abbreviation
        if name.islower() and ' ' not in name:
            return False
        
        # Common publication handles that aren't author names
        site_handles = {
            'hlr', 'ylj', 'nytimes', 'washpost', 'wsj', 'latimes',
            'theatlantic', 'newyorker', 'economist', 'guardian',
            'reuters', 'apnews', 'bbc', 'cnn', 'npr', 'pbs',
            'harvardlawreview', 'yalelawjournal', 'stanfordlawreview',
            # Common law review abbreviations
            'harvlrev', 'yaleljforum', 'stanfordlrev', 'columbialrev',
            'michlrev', 'texaslrev', 'virginialrev', 'pennlrev',
            'cornelllrev', 'dukelj', 'georgetownlj', 'naborelj',
        }
        if name.lower().replace('_', '').replace('-', '') in site_handles:
            return False
        
        # Pattern detection for law review / journal abbreviations
        # Matches: HarvLRev, YaleLJ, StanfordLRev, TexasLRev, etc.
        name_lower = name.lower()
        if re.search(r'l\.?rev$|l\.?j$|lawrev$|lawj$|ljournal$', name_lower):
            return False
        
        # Pattern for magazine/news abbreviations ending in common suffixes
        # Matches: TheAtlantic, NewYorker (no spaces, proper case)
        if ' ' not in name and len(name) > 6:
            # Single word with no spaces that looks like a publication name
            # (multiple capital letters = likely abbreviation/brand)
            capitals = sum(1 for c in name if c.isupper())
            if capitals >= 2 and not any(c == ' ' for c in name):
                # Could be "HarvLRev" or "NewYorker" - check for common patterns
                if re.search(r'(times|post|journal|review|tribune|news|weekly|monthly|daily)$', name_lower):
                    return False
        
        return True
    
    def _extract_meta_tags(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract standard HTML meta tags including academic/Dublin Core metadata."""
        data = {}
        
        # Author - check multiple common meta names
        # Priority: citation_author (academic) > DC.creator (Dublin Core) > author (standard)
        author_meta_names = [
            'citation_author',      # Google Scholar / academic
            'citation_authors',     # Alternate
            'DC.creator',           # Dublin Core
            'DC.Creator',           # Dublin Core (case variant)
            'dcterms.creator',      # Dublin Core Terms
            'author',               # Standard HTML
            'article:author',       # Some sites use this
        ]
        
        for name in author_meta_names:
            # Find all tags with this name (articles can have multiple authors)
            tags = soup.find_all('meta', attrs={'name': name})
            if tags:
                authors = []
                for tag in tags:
                    content = tag.get('content', '').strip()
                    if content and self._is_valid_author_name(content):
                        authors.append(content)
                if authors:
                    data['authors'] = authors
                    break
        
        # Date variations - check academic metadata first
        date_names = [
            'citation_publication_date',  # Google Scholar / academic
            'citation_date',              # Academic
            'DC.date',                    # Dublin Core
            'DC.Date',                    # Dublin Core (case variant)
            'dcterms.date',               # Dublin Core Terms
            'date',                       # Standard
            'pubdate',                    # Common
            'publish_date',               # Common
            'article:published_time',     # Open Graph style
            'DC.date.issued',             # Dublin Core specific
        ]
        for name in date_names:
            tag = soup.find('meta', attrs={'name': name})
            if tag and tag.get('content'):
                data['date'] = self._normalize_date(tag['content'].strip())
                break
        
        # Journal/publication name (for academic articles)
        journal_names = ['citation_journal_title', 'DC.publisher', 'citation_publisher']
        for name in journal_names:
            tag = soup.find('meta', attrs={'name': name})
            if tag and tag.get('content'):
                data['site_name'] = tag['content'].strip()
                break
        
        # Volume, issue, pages (academic)
        vol_tag = soup.find('meta', attrs={'name': 'citation_volume'})
        if vol_tag and vol_tag.get('content'):
            data['volume'] = vol_tag['content'].strip()
        
        issue_tag = soup.find('meta', attrs={'name': 'citation_issue'})
        if issue_tag and issue_tag.get('content'):
            data['issue'] = issue_tag['content'].strip()
        
        firstpage = soup.find('meta', attrs={'name': 'citation_firstpage'})
        lastpage = soup.find('meta', attrs={'name': 'citation_lastpage'})
        if firstpage and firstpage.get('content'):
            pages = firstpage['content'].strip()
            if lastpage and lastpage.get('content'):
                pages += '-' + lastpage['content'].strip()
            data['pages'] = pages
        
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
        
        # Author from common byline patterns - expanded for academic sites
        byline_selectors = [
            # Standard patterns
            {'class_': re.compile(r'byline|author|writer', re.I)},
            {'itemprop': 'author'},
            {'rel': 'author'},
            {'class_': 'contributor'},
            # Academic patterns
            {'class_': re.compile(r'article-author|post-author|entry-author', re.I)},
            {'class_': re.compile(r'author-name|authorname', re.I)},
            {'class_': re.compile(r'article__author|article-header__author', re.I)},
            # Law review specific patterns (Harvard, Yale, Stanford, etc.)
            {'class_': re.compile(r'post-card__author|piece-author', re.I)},
            {'class_': re.compile(r'single-article__authors-link', re.I)},  # Harvard Law Review
            {'class_': re.compile(r'author-block|authors-block', re.I)},
            {'class_': re.compile(r'essay-author|article-byline', re.I)},
        ]
        
        for selector in byline_selectors:
            # Find all matching elements (for multiple authors)
            bylines = soup.find_all(['span', 'div', 'a', 'p', 'address', 'li', 'h2', 'h3'], **selector)
            if bylines:
                authors = []
                for byline in bylines:
                    author_text = byline.get_text(strip=True)
                    # Clean up "By John Smith" -> "John Smith"
                    author_text = re.sub(r'^by\s+', '', author_text, flags=re.IGNORECASE)
                    # Remove footnote markers (e.g., "John Smith†" or "John Smith*")
                    author_text = re.sub(r'[†‡§*¶\d]+$', '', author_text).strip()
                    # Sanity checks
                    if author_text and len(author_text) < 100 and self._is_valid_author_name(author_text):
                        # Avoid duplicates
                        if author_text not in authors:
                            authors.append(author_text)
                if authors:
                    data['authors'] = authors
                    break
        
        # If still no author, try looking for author links near the title
        if 'authors' not in data:
            # Look for links with "author" in href
            author_links = soup.find_all('a', href=re.compile(r'/authors?/|/people/|/contributors?/', re.I))
            authors = []
            for link in author_links[:5]:  # Limit to first 5 to avoid nav links
                name = link.get_text(strip=True)
                if name and len(name) < 50 and self._is_valid_author_name(name):
                    if name not in authors:
                        authors.append(name)
            if authors:
                data['authors'] = authors
        
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
        
        # Get authors, with organizational fallback
        authors = metadata.get('authors', [])
        
        # Check if this is a known institutional domain where org should be the author
        # (regardless of what metadata says - departments/programs shouldn't be authors)
        org_author = self._get_organizational_author(metadata, url)
        
        if org_author:
            # For institutional domains, ALWAYS use org name, not department/program names
            # This prevents "Global HIV, Hepatitis and STI Programme" from being author
            # when it should be "World Health Organization"
            institutional_domains = self._get_institutional_domains()
            try:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.lower().replace('www.', '')
                
                # Check if this domain (or parent domain) is institutional
                is_institutional = any(
                    domain == inst_domain or domain.endswith('.' + inst_domain)
                    for inst_domain in institutional_domains
                )
                
                if is_institutional:
                    # Use org name, ignore metadata author
                    authors = [org_author]
                elif not authors:
                    # Fallback: use org if no individual author found
                    authors = [org_author]
            except:
                # On error, use fallback logic
                if not authors:
                    authors = [org_author]
        
        # Build base metadata
        result = CitationMetadata(
            citation_type=citation_type,
            raw_source=url,
            source_engine=self.name,
            title=metadata.get('title', ''),
            authors=authors,
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
    
    def _get_organizational_author(self, metadata: Dict, url: str) -> Optional[str]:
        """
        Get organizational author when no individual author is found.
        
        Used for government agencies, corporations, NGOs, think tanks, etc.
        Returns the organization name to use as author, or None.
        
        Examples:
            - who.int → "World Health Organization"
            - cdc.gov → "Centers for Disease Control and Prevention"
            - commonwealthfund.org → "Commonwealth Fund"
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace('www.', '')
        except:
            return None
        
        # Priority 0: Check gov_ngo_domains cache (204 orgs, most comprehensive)
        cached_org = get_org_author_from_cache(url)
        if cached_org:
            return cached_org
        
        # Priority 1: Check explicit domain mappings (most accurate)
        # Government agencies
        if domain in GOV_AGENCY_MAP:
            return GOV_AGENCY_MAP[domain]
        
        # Priority 2: Known organizational domains
        # These are organizations where site_name IS the author
        org_domains = {
            # International organizations
            'who.int': 'World Health Organization',
            'worldbank.org': 'World Bank',
            'imf.org': 'International Monetary Fund',
            'un.org': 'United Nations',
            'oecd.org': 'Organisation for Economic Co-operation and Development',
            
            # US Government
            'cdc.gov': 'Centers for Disease Control and Prevention',
            'nih.gov': 'National Institutes of Health',
            'fda.gov': 'U.S. Food and Drug Administration',
            'epa.gov': 'U.S. Environmental Protection Agency',
            'doi.gov': 'U.S. Department of the Interior',
            'state.gov': 'U.S. Department of State',
            'treasury.gov': 'U.S. Department of the Treasury',
            'justice.gov': 'U.S. Department of Justice',
            'ed.gov': 'U.S. Department of Education',
            'hhs.gov': 'U.S. Department of Health and Human Services',
            'dhs.gov': 'U.S. Department of Homeland Security',
            'energy.gov': 'U.S. Department of Energy',
            'usda.gov': 'U.S. Department of Agriculture',
            'commerce.gov': 'U.S. Department of Commerce',
            'labor.gov': 'U.S. Department of Labor',
            'transportation.gov': 'U.S. Department of Transportation',
            'va.gov': 'U.S. Department of Veterans Affairs',
            'gao.gov': 'U.S. Government Accountability Office',
            'cbo.gov': 'Congressional Budget Office',
            'federalreserve.gov': 'Federal Reserve',
            'sec.gov': 'U.S. Securities and Exchange Commission',
            'ftc.gov': 'Federal Trade Commission',
            'fcc.gov': 'Federal Communications Commission',
            'census.gov': 'U.S. Census Bureau',
            'bls.gov': 'Bureau of Labor Statistics',
            'supremecourt.gov': 'Supreme Court of the United States',
            'uscourts.gov': 'U.S. Courts',
            
            # Think tanks and research orgs
            'brookings.edu': 'Brookings Institution',
            'rand.org': 'RAND Corporation',
            'urban.org': 'Urban Institute',
            'commonwealthfund.org': 'Commonwealth Fund',
            'kff.org': 'Kaiser Family Foundation',
            'pewresearch.org': 'Pew Research Center',
            'cfr.org': 'Council on Foreign Relations',
            'heritage.org': 'Heritage Foundation',
            'cato.org': 'Cato Institute',
            'aei.org': 'American Enterprise Institute',
            'nber.org': 'National Bureau of Economic Research',
            
            # Major corporations (for corporate reports/press releases)
            'pfizer.com': 'Pfizer Inc.',
            'merck.com': 'Merck & Co.',
            'jnj.com': 'Johnson & Johnson',
            'apple.com': 'Apple Inc.',
            'google.com': 'Google LLC',
            'microsoft.com': 'Microsoft Corporation',
            'amazon.com': 'Amazon.com, Inc.',
            
            # International government
            'gov.uk': 'UK Government',
            'canada.ca': 'Government of Canada',
            'europa.eu': 'European Union',
        }
        
        # Check if domain or parent domain matches
        for org_domain, org_name in org_domains.items():
            if domain == org_domain or domain.endswith('.' + org_domain):
                return org_name
        
        # Priority 3: Use site_name if it looks like an organization
        # (not just a domain name or abbreviation)
        site_name = metadata.get('site_name', '')
        if site_name and self._looks_like_organization(site_name):
            return site_name
        
        # Priority 4: For .gov, .org, .edu domains without mapping,
        # try to use site_name even if it's short
        if any(domain.endswith(tld) for tld in ['.gov', '.org', '.edu', '.int']):
            if site_name and len(site_name) > 3:
                return site_name
        
        return None
    
    def _looks_like_organization(self, name: str) -> bool:
        """
        Check if a name looks like an organization vs a domain/abbreviation.
        
        Returns True for: "World Health Organization", "Centers for Disease Control"
        Returns False for: "WHO", "cdc", "harvardlawreview.org"
        """
        if not name:
            return False
        
        # Too short - likely an abbreviation
        if len(name) < 5:
            return False
        
        # All caps or all lowercase - likely abbreviation/domain
        if name.isupper() or name.islower():
            return False
        
        # Contains domain patterns
        if any(x in name.lower() for x in ['.com', '.org', '.gov', '.edu', '.net', '.io']):
            return False
        
        # Has multiple words or proper capitalization - likely an org name
        if ' ' in name:
            return True
        
        # Mixed case single word could be org (e.g., "Pfizer")
        if name[0].isupper() and not name.isupper():
            return True
        
        return False
    
    def _get_institutional_domains(self) -> set:
        """
        Return domains where the organization should ALWAYS be the author,
        regardless of what metadata says about individual departments/programs.
        
        For these domains, department names like "Global HIV, Hepatitis and STI Programme"
        should be ignored in favor of the main org name "World Health Organization".
        """
        return {
            # International organizations (have many programs/departments)
            'who.int',
            'worldbank.org',
            'imf.org',
            'un.org',
            'oecd.org',
            
            # US Government agencies (have many sub-agencies/offices)
            'cdc.gov',
            'nih.gov',
            'fda.gov',
            'epa.gov',
            'state.gov',
            'treasury.gov',
            'justice.gov',
            'hhs.gov',
            'dhs.gov',
            'energy.gov',
            'usda.gov',
            'commerce.gov',
            'labor.gov',
            'va.gov',
            'gao.gov',
            
            # Think tanks / research orgs (staff write under org name)
            'brookings.edu',
            'rand.org',
            'urban.org',
            'commonwealthfund.org',
            'kff.org',
            'pewresearch.org',
            'cfr.org',
            'nber.org',
            
            # International government
            'gov.uk',
            'canada.ca',
            'europa.eu',
        }
    
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
