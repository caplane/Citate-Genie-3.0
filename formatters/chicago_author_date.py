"""
citeflex/formatters/chicago_author_date.py

Chicago Manual of Style (17th ed.) Author-Date format.
Used in sciences and social sciences.

Key differences from Chicago Notes-Bibliography:
- In-text: (Author Year) parenthetical citations
- End: Reference list (not bibliography)
- Author names: Lastname, Firstname format

Created: 2025-12-10
"""

from models import CitationMetadata, CitationType, CitationStyle
from formatters.base import BaseFormatter


class ChicagoAuthorDateFormatter(BaseFormatter):
    """
    Chicago Manual of Style 17th Edition Author-Date formatter.
    
    Key features:
    - Author names: Lastname, Firstname. format (first author inverted)
    - Year after author
    - Titles in sentence case (articles) or title case (books)
    - Journal titles in italics
    """
    
    style = CitationStyle.CHICAGO
    style_name = "Chicago Author-Date"
    
    def format(self, metadata: CitationMetadata) -> str:
        """Format a full Chicago Author-Date reference."""
        
        if metadata.citation_type == CitationType.LEGAL:
            return self._format_legal(metadata)
        elif metadata.citation_type == CitationType.INTERVIEW:
            return self._format_interview(metadata)
        elif metadata.citation_type == CitationType.LETTER:
            return self._format_letter(metadata)
        elif metadata.citation_type == CitationType.NEWSPAPER:
            return self._format_newspaper(metadata)
        elif metadata.citation_type == CitationType.GOVERNMENT:
            return self._format_government(metadata)
        elif metadata.citation_type == CitationType.BOOK:
            return self._format_book(metadata)
        elif metadata.citation_type in [CitationType.JOURNAL, CitationType.MEDICAL]:
            return self._format_journal(metadata)
        elif metadata.citation_type == CitationType.URL:
            return self._format_url(metadata)
        else:
            return self._format_journal(metadata)
    
    def format_short(self, metadata: CitationMetadata) -> str:
        """Format short Chicago Author-Date citation (Author Year) - no comma."""
        parts = []
        
        if metadata.authors:
            last_name = self._get_last_name(metadata.authors[0])
            if len(metadata.authors) == 2:
                last_name2 = self._get_last_name(metadata.authors[1])
                parts.append(f"{last_name} and {last_name2}")
            elif len(metadata.authors) > 2:
                parts.append(f"{last_name} et al.")
            else:
                parts.append(last_name)
        
        if metadata.year:
            parts.append(metadata.year)  # No parentheses, no comma
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    def _format_authors_chicago_ad(self, authors: list) -> str:
        """
        Format authors in Chicago Author-Date style.
        
        First author: Last, First.
        Subsequent authors: First Last
        
        Examples:
        - Smith, John.
        - Smith, John, and Jane Doe.
        - Smith, John, Jane Doe, and Bob Wilson.
        """
        if not authors:
            return ""
        
        def format_first(name: str) -> str:
            """First author: Last, First"""
            parts = name.strip().split()
            if len(parts) == 0:
                return ""
            if len(parts) == 1:
                return parts[0]
            if ',' in name:
                return name
            last = parts[-1]
            first = " ".join(parts[:-1])
            return f"{last}, {first}"
        
        def format_subsequent(name: str) -> str:
            """Subsequent authors: First Last (not inverted)"""
            parts = name.strip().split()
            if ',' in name:
                # Already in Last, First format - convert
                comma_parts = name.split(',')
                if len(comma_parts) == 2:
                    return f"{comma_parts[1].strip()} {comma_parts[0].strip()}"
            return name
        
        if len(authors) == 1:
            return format_first(authors[0])
        elif len(authors) == 2:
            return f"{format_first(authors[0])}, and {format_subsequent(authors[1])}"
        else:
            formatted = [format_first(authors[0])]
            for a in authors[1:-1]:
                formatted.append(format_subsequent(a))
            formatted_str = ", ".join(formatted)
            return f"{formatted_str}, and {format_subsequent(authors[-1])}"
    
    # =========================================================================
    # JOURNAL
    # =========================================================================
    
    def _format_journal(self, m: CitationMetadata) -> str:
        """
        Chicago Author-Date journal article.
        
        Pattern: Last, First. Year. "Title." Journal Volume (Issue): Pages. DOI.
        """
        parts = []
        
        # Authors
        if m.authors:
            parts.append(self._format_authors_chicago_ad(m.authors) + ".")
        
        # Year
        if m.year:
            parts.append(f"{m.year}.")
        
        # Title in quotes
        if m.title:
            parts.append(f'"{m.title}."')
        
        # Journal in italics
        journal_parts = []
        if m.journal:
            journal_parts.append(f"<i>{m.journal}</i>")
        
        # Volume and issue
        if m.volume:
            vol_str = m.volume
            if m.issue:
                vol_str += f" ({m.issue})"
            journal_parts.append(vol_str)
        
        if journal_parts:
            journal_str = " ".join(journal_parts)
            if m.pages:
                journal_str += f": {m.pages}"
            parts.append(journal_str + ".")
        
        # DOI or URL
        if m.doi:
            parts.append(f"https://doi.org/{m.doi}.")
        elif m.url:
            parts.append(m.url + ".")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # BOOK
    # =========================================================================
    
    def _format_book(self, m: CitationMetadata) -> str:
        """
        Chicago Author-Date book.
        
        Pattern: Last, First. Year. Title. Place: Publisher.
        """
        parts = []
        
        # Authors
        if m.authors:
            parts.append(self._format_authors_chicago_ad(m.authors) + ".")
        
        # Year
        if m.year:
            parts.append(f"{m.year}.")
        
        # Title in italics
        if m.title:
            parts.append(f"<i>{m.title}</i>.")
        
        # Edition
        if m.edition:
            parts.append(f"{m.edition}.")
        
        # Place and Publisher
        pub_parts = []
        if m.place:
            pub_parts.append(m.place)
        if m.publisher:
            pub_parts.append(m.publisher)
        if pub_parts:
            parts.append(": ".join(pub_parts) + ".")
        
        # DOI or URL
        if m.doi:
            parts.append(f"https://doi.org/{m.doi}.")
        elif m.url:
            parts.append(m.url + ".")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # LEGAL
    # =========================================================================
    
    def _format_legal(self, m: CitationMetadata) -> str:
        """
        Chicago Author-Date legal case.
        
        Pattern: Case Name, Citation (Court Year).
        """
        parts = []
        
        # Case name in italics
        if m.case_name:
            parts.append(f"<i>{m.case_name}</i>,")
        
        # Citation
        if m.citation:
            parts.append(m.citation)
        elif m.neutral_citation:
            parts.append(m.neutral_citation)
        
        # Court and Year
        court_year = []
        if m.court:
            court_year.append(m.court)
        if m.year:
            court_year.append(m.year)
        if court_year:
            parts.append(f"({' '.join(court_year)})")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # INTERVIEW
    # =========================================================================
    
    def _format_interview(self, m: CitationMetadata) -> str:
        """Chicago Author-Date interview."""
        parts = []
        
        if m.interviewee:
            parts.append(self._format_authors_chicago_ad([m.interviewee]) + ".")
        
        if m.year:
            parts.append(f"{m.year}.")
        elif m.date:
            parts.append(f"{m.date}.")
        
        parts.append("Interview by")
        if m.interviewer:
            parts.append(f"{m.interviewer}.")
        else:
            parts.append("author.")
        
        if m.location:
            parts.append(f"{m.location}.")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # LETTER/CORRESPONDENCE
    # =========================================================================
    
    def _format_letter(self, m: CitationMetadata) -> str:
        """Chicago Author-Date letter."""
        parts = []
        
        if m.sender:
            parts.append(self._format_authors_chicago_ad([m.sender]) + ".")
        
        if m.date:
            parts.append(f"{m.date}.")
        elif m.year:
            parts.append(f"{m.year}.")
        
        if m.recipient:
            parts.append(f"Letter to {m.recipient}.")
        
        if m.title:
            parts.append(f'"{m.title}."')
        
        if m.location:
            parts.append(f"{m.location}.")
        
        if m.url:
            parts.append(m.url + ".")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # NEWSPAPER
    # =========================================================================
    
    def _format_newspaper(self, m: CitationMetadata) -> str:
        """
        Chicago Author-Date newspaper.
        
        Pattern: Last, First. Year. "Title." Newspaper, Date.
        """
        parts = []
        
        if m.authors:
            parts.append(self._format_authors_chicago_ad(m.authors) + ".")
        
        if m.year:
            parts.append(f"{m.year}.")
        
        if m.title:
            parts.append(f'"{m.title}."')
        
        pub_name = m.newspaper or getattr(m, 'publication', '')
        if pub_name:
            parts.append(f"<i>{pub_name}</i>,")
        
        if m.date:
            parts.append(f"{m.date}.")
        
        if m.url:
            parts.append(m.url + ".")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # GOVERNMENT
    # =========================================================================
    
    def _format_government(self, m: CitationMetadata) -> str:
        """Chicago Author-Date government document."""
        parts = []
        
        if m.agency:
            parts.append(m.agency + ".")
        
        if m.year:
            parts.append(f"{m.year}.")
        
        if m.title:
            parts.append(f"<i>{m.title}</i>.")
        
        if m.document_number:
            parts.append(f"{m.document_number}.")
        
        if m.url:
            parts.append(m.url + ".")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # URL
    # =========================================================================
    
    def _format_url(self, m: CitationMetadata) -> str:
        """
        Chicago Author-Date web page.
        
        Pattern: Author. Year. "Title." Site. Accessed date. URL.
        """
        parts = []
        
        if m.authors:
            parts.append(self._format_authors_chicago_ad(m.authors) + ".")
        
        if m.year:
            parts.append(f"{m.year}.")
        else:
            parts.append("n.d.")
        
        if m.title:
            parts.append(f'"{m.title}."')
        
        if m.access_date:
            parts.append(f"Accessed {m.access_date}.")
        
        if m.url:
            parts.append(m.url + ".")
        
        result = " ".join(parts)
        return self._ensure_period(result)
