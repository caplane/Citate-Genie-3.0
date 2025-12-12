"""
citeflex/engines/arxiv_engine.py

arXiv preprint metadata extraction via the arXiv API.

The arXiv API is free and requires no authentication.
Documentation: https://info.arxiv.org/help/api/basics.html

Version History:
    2025-12-08: Initial creation
"""

import re
import xml.etree.ElementTree as ET
from typing import Optional, List
from datetime import datetime

from engines.base import SearchEngine
from models import CitationMetadata, CitationType


class ArxivEngine(SearchEngine):
    """
    arXiv preprint metadata engine.
    
    Uses the arXiv API to fetch metadata for preprints.
    The API is free and requires no authentication.
    
    Handles:
    - arXiv IDs: 2301.12345, 2301.12345v2
    - Old format: hep-th/9901001
    - URLs: arxiv.org/abs/2301.12345
    """
    
    name = "arXiv"
    base_url = "http://export.arxiv.org/api/query"
    
    # XML namespaces used by arXiv API
    NAMESPACES = {
        'atom': 'http://www.w3.org/2005/Atom',
        'arxiv': 'http://arxiv.org/schemas/atom'
    }
    
    def search(self, query: str) -> Optional[CitationMetadata]:
        """
        Search arXiv by title/author query.
        
        Args:
            query: Search query (title, author, or keywords)
            
        Returns:
            CitationMetadata if found, None otherwise
        """
        # Check if query is an arXiv ID
        arxiv_id = self._extract_arxiv_id(query)
        if arxiv_id:
            return self.get_by_id(arxiv_id)
        
        # Otherwise search by title/author
        params = {
            'search_query': f'all:{query}',
            'start': 0,
            'max_results': 5,
            'sortBy': 'relevance',
            'sortOrder': 'descending'
        }
        
        response = self._make_request(self.base_url, params=params)
        if not response:
            return None
        
        try:
            entries = self._parse_response(response.text)
            if entries:
                best = self._find_best_match(entries, query)
                return self._normalize(best, query)
            return None
        except Exception as e:
            print(f"[{self.name}] Parse error: {e}")
            return None
    
    def get_by_id(self, arxiv_id: str) -> Optional[CitationMetadata]:
        """
        Fetch metadata by arXiv ID.
        
        Args:
            arxiv_id: arXiv identifier (e.g., "2301.12345" or "hep-th/9901001")
            
        Returns:
            CitationMetadata if found, None otherwise
        """
        # Clean up the ID
        arxiv_id = self._clean_arxiv_id(arxiv_id)
        if not arxiv_id:
            return None
        
        print(f"[{self.name}] Fetching ID: {arxiv_id}")
        
        params = {
            'id_list': arxiv_id,
            'max_results': 1
        }
        
        response = self._make_request(self.base_url, params=params)
        if not response:
            return None
        
        try:
            entries = self._parse_response(response.text)
            if entries:
                return self._normalize(entries[0], arxiv_id)
            return None
        except Exception as e:
            print(f"[{self.name}] Parse error: {e}")
            return None
    
    def _extract_arxiv_id(self, text: str) -> Optional[str]:
        """Extract arXiv ID from text or URL."""
        if not text:
            return None
        
        text = text.strip()
        
        # URL pattern: arxiv.org/abs/2301.12345
        match = re.search(r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)', text, re.IGNORECASE)
        if match:
            return match.group(1)
        
        # URL pattern old format: arxiv.org/abs/hep-th/9901001
        match = re.search(r'arxiv\.org/(?:abs|pdf)/([a-z-]+/\d{7})', text, re.IGNORECASE)
        if match:
            return match.group(1)
        
        # Direct ID: 2301.12345 or 2301.12345v2
        match = re.search(r'\b(\d{4}\.\d{4,5}(?:v\d+)?)\b', text)
        if match:
            return match.group(1)
        
        # Old format direct: hep-th/9901001
        match = re.search(r'\b([a-z-]+/\d{7})\b', text, re.IGNORECASE)
        if match:
            return match.group(1)
        
        # arXiv: prefix
        match = re.search(r'arxiv:\s*(\d{4}\.\d{4,5}(?:v\d+)?)', text, re.IGNORECASE)
        if match:
            return match.group(1)
        
        return None
    
    def _clean_arxiv_id(self, arxiv_id: str) -> Optional[str]:
        """Clean and validate arXiv ID."""
        if not arxiv_id:
            return None
        
        arxiv_id = arxiv_id.strip()
        
        # Remove common prefixes
        arxiv_id = re.sub(r'^arxiv:\s*', '', arxiv_id, flags=re.IGNORECASE)
        arxiv_id = re.sub(r'^https?://arxiv\.org/(?:abs|pdf)/', '', arxiv_id, flags=re.IGNORECASE)
        
        # Validate format
        if re.match(r'^\d{4}\.\d{4,5}(v\d+)?$', arxiv_id):
            return arxiv_id
        if re.match(r'^[a-z-]+/\d{7}$', arxiv_id, re.IGNORECASE):
            return arxiv_id
        
        return None
    
    def _parse_response(self, xml_text: str) -> List[dict]:
        """Parse arXiv API XML response."""
        entries = []
        
        try:
            root = ET.fromstring(xml_text)
            
            for entry in root.findall('atom:entry', self.NAMESPACES):
                data = {}
                
                # ID (extract just the arXiv ID from the URL)
                id_elem = entry.find('atom:id', self.NAMESPACES)
                if id_elem is not None and id_elem.text:
                    # Format: http://arxiv.org/abs/2301.12345v1
                    match = re.search(r'/abs/(.+)$', id_elem.text)
                    data['arxiv_id'] = match.group(1) if match else id_elem.text
                
                # Title
                title_elem = entry.find('atom:title', self.NAMESPACES)
                if title_elem is not None and title_elem.text:
                    # Clean up whitespace in title
                    data['title'] = ' '.join(title_elem.text.split())
                
                # Authors
                authors = []
                for author in entry.findall('atom:author', self.NAMESPACES):
                    name_elem = author.find('atom:name', self.NAMESPACES)
                    if name_elem is not None and name_elem.text:
                        authors.append(name_elem.text.strip())
                data['authors'] = authors
                
                # Abstract/Summary
                summary_elem = entry.find('atom:summary', self.NAMESPACES)
                if summary_elem is not None and summary_elem.text:
                    data['abstract'] = ' '.join(summary_elem.text.split())
                
                # Published date
                published_elem = entry.find('atom:published', self.NAMESPACES)
                if published_elem is not None and published_elem.text:
                    data['published'] = published_elem.text
                
                # Updated date
                updated_elem = entry.find('atom:updated', self.NAMESPACES)
                if updated_elem is not None and updated_elem.text:
                    data['updated'] = updated_elem.text
                
                # Primary category
                primary_cat = entry.find('arxiv:primary_category', self.NAMESPACES)
                if primary_cat is not None:
                    data['category'] = primary_cat.get('term', '')
                
                # DOI (if available)
                doi_elem = entry.find('arxiv:doi', self.NAMESPACES)
                if doi_elem is not None and doi_elem.text:
                    data['doi'] = doi_elem.text
                
                # Journal reference (if published)
                journal_ref = entry.find('arxiv:journal_ref', self.NAMESPACES)
                if journal_ref is not None and journal_ref.text:
                    data['journal_ref'] = journal_ref.text
                
                # Links
                for link in entry.findall('atom:link', self.NAMESPACES):
                    if link.get('type') == 'application/pdf':
                        data['pdf_url'] = link.get('href', '')
                    elif link.get('rel') == 'alternate':
                        data['url'] = link.get('href', '')
                
                entries.append(data)
                
        except ET.ParseError as e:
            print(f"[{self.name}] XML parse error: {e}")
        
        return entries
    
    def _find_best_match(self, entries: List[dict], query: str) -> dict:
        """Find best matching entry for query."""
        if len(entries) == 1:
            return entries[0]
        
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        best = entries[0]
        best_score = 0
        
        for entry in entries:
            score = 0
            title = entry.get('title', '').lower()
            
            # Title word overlap
            title_words = set(title.split())
            overlap = len(query_words & title_words)
            score += overlap * 3
            
            # Author match
            for author in entry.get('authors', []):
                author_lower = author.lower()
                for name_part in author_lower.split():
                    if len(name_part) >= 3 and name_part in query_lower:
                        score += 10
            
            if score > best_score:
                best_score = score
                best = entry
        
        return best
    
    def _normalize(self, entry: dict, raw_source: str) -> CitationMetadata:
        """Convert arXiv entry to CitationMetadata."""
        
        # Parse date
        year = None
        date_str = entry.get('published', '')
        if date_str:
            try:
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                year = str(dt.year)
            except:
                year_match = re.search(r'(\d{4})', date_str)
                if year_match:
                    year = year_match.group(1)
        
        # Build URL
        arxiv_id = entry.get('arxiv_id', '')
        url = entry.get('url', '')
        if not url and arxiv_id:
            url = f"https://arxiv.org/abs/{arxiv_id}"
        
        return self._create_metadata(
            citation_type=CitationType.JOURNAL,  # Preprints are treated as journal articles
            raw_source=raw_source,
            title=entry.get('title', ''),
            authors=entry.get('authors', []),
            year=year,
            doi=entry.get('doi', ''),
            url=url,
            journal=f"arXiv preprint arXiv:{arxiv_id}" if arxiv_id else "arXiv",
            raw_data=entry
        )
