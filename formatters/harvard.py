"""
citeflex/formatters/harvard.py

Harvard citation style formatter.
Common in UK, Australia, and business/management fields.

Key differences from APA:
- Title capitalization varies (often title case vs sentence case)
- Publisher location often included for books
- "Available at:" prefix for URLs
- Some institutions have specific variations

This implements a common Harvard variant.

Created: 2025-12-10
"""

from models import CitationMetadata, CitationType, CitationStyle
from formatters.base import BaseFormatter


class HarvardFormatter(BaseFormatter):
    """
    Harvard referencing style formatter.
    
    Key features:
    - Author names: Surname, F.M. format
    - Year in parentheses after author
    - Book/journal titles in italics
    - URLs prefixed with "Available at:"
    """
    
    style = CitationStyle.APA  # Use APA enum as base (structurally similar)
    style_name = "Harvard"
    
    def format(self, metadata: CitationMetadata) -> str:
        """Format a full Harvard-style reference."""
        
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
        """Format short Harvard citation (Author Year) - no comma."""
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
            parts.append(f"({metadata.year})")  # No comma before year in Harvard
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    def _format_authors_harvard(self, authors: list) -> str:
        """
        Format authors in Harvard style: Surname, F.M.
        
        Rules:
        - Single author: Surname, F.M.
        - Two authors: Surname, F.M. and Surname, F.M.
        - Three+ authors: Surname, F.M., Surname, F.M. and Surname, F.M.
        """
        if not authors:
            return ""
        
        def format_one(name: str) -> str:
            """Convert 'First Middle Last' to 'Last, F.M.'"""
            parts = name.strip().split()
            if len(parts) == 0:
                return ""
            if len(parts) == 1:
                return parts[0]
            
            # Check for "Last, First" format already
            if ',' in name:
                return name
            
            last = parts[-1]
            initials = ".".join(p[0].upper() for p in parts[:-1] if p) + "."
            return f"{last}, {initials}"
        
        formatted = [format_one(a) for a in authors]
        
        if len(formatted) == 1:
            return formatted[0]
        elif len(formatted) == 2:
            return f"{formatted[0]} and {formatted[1]}"
        else:
            return ", ".join(formatted[:-1]) + f" and {formatted[-1]}"
    
    # =========================================================================
    # JOURNAL
    # =========================================================================
    
    def _format_journal(self, m: CitationMetadata) -> str:
        """
        Harvard journal article.
        
        Pattern: Surname, F.M. (Year) 'Article title', Journal Name, Volume(Issue), pp. Pages.
        """
        parts = []
        
        # Authors
        if m.authors:
            parts.append(self._format_authors_harvard(m.authors))
        
        # Year
        if m.year:
            parts.append(f"({m.year})")
        
        # Title in single quotes (Harvard convention)
        if m.title:
            parts.append(f"'{m.title}',")
        
        # Journal in italics
        journal_parts = []
        if m.journal:
            journal_parts.append(f"<i>{m.journal}</i>")
        
        # Volume and issue
        if m.volume:
            vol_str = m.volume
            if m.issue:
                vol_str += f"({m.issue})"
            journal_parts.append(vol_str)
        
        # Pages with pp. prefix
        if m.pages:
            journal_parts.append(f"pp. {m.pages}")
        
        if journal_parts:
            parts.append(", ".join(journal_parts) + ".")
        
        # DOI or URL
        if m.doi:
            parts.append(f"Available at: https://doi.org/{m.doi}")
        elif m.url:
            parts.append(f"Available at: {m.url}")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # BOOK
    # =========================================================================
    
    def _format_book(self, m: CitationMetadata) -> str:
        """
        Harvard book.
        
        Pattern: Surname, F.M. (Year) Title. Edition. Place: Publisher.
        """
        parts = []
        
        # Authors
        if m.authors:
            parts.append(self._format_authors_harvard(m.authors))
        
        # Year
        if m.year:
            parts.append(f"({m.year})")
        
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
            parts.append(f"Available at: https://doi.org/{m.doi}")
        elif m.url:
            parts.append(f"Available at: {m.url}")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # LEGAL
    # =========================================================================
    
    def _format_legal(self, m: CitationMetadata) -> str:
        """
        Harvard legal case (basic format).
        
        Pattern: Case Name [Year] Citation.
        """
        parts = []
        
        # Case name in italics
        if m.case_name:
            parts.append(f"<i>{m.case_name}</i>")
        
        # Year in brackets (UK style)
        if m.year:
            parts.append(f"[{m.year}]")
        
        # Citation
        if m.citation:
            parts.append(m.citation)
        elif m.neutral_citation:
            parts.append(m.neutral_citation)
        
        # Court
        if m.court:
            parts.append(f"({m.court})")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # INTERVIEW
    # =========================================================================
    
    def _format_interview(self, m: CitationMetadata) -> str:
        """
        Harvard interview (personal communication).
        
        Pattern: Surname, F.M. (Year) Interview with Author. Date.
        """
        parts = []
        
        # Interviewee
        if m.interviewee:
            parts.append(self._format_authors_harvard([m.interviewee]))
        
        # Year
        if m.year:
            parts.append(f"({m.year})")
        elif m.date:
            parts.append(f"({m.date})")
        
        # Description
        if m.interviewer:
            parts.append(f"Interview with {m.interviewer}.")
        else:
            parts.append("Personal interview.")
        
        # Date
        if m.date and m.year and m.date != m.year:
            parts.append(m.date + ".")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # LETTER/CORRESPONDENCE
    # =========================================================================
    
    def _format_letter(self, m: CitationMetadata) -> str:
        """
        Harvard letter (personal communication).
        
        Pattern: Surname, F.M. (Year) Letter to Recipient. Date.
        """
        parts = []
        
        # Sender
        if m.sender:
            parts.append(self._format_authors_harvard([m.sender]))
        
        # Date/Year
        if m.date:
            parts.append(f"({m.date})")
        elif m.year:
            parts.append(f"({m.year})")
        
        # Description
        if m.recipient:
            parts.append(f"Letter to {m.recipient}.")
        else:
            parts.append("Personal correspondence.")
        
        # Subject if present
        if m.title:
            parts.append(f"Re: {m.title}.")
        
        # Location/archive
        if m.location:
            parts.append(m.location + ".")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # NEWSPAPER
    # =========================================================================
    
    def _format_newspaper(self, m: CitationMetadata) -> str:
        """
        Harvard newspaper article.
        
        Pattern: Surname, F.M. (Year) 'Article title', Newspaper, Date, p. Page.
        """
        parts = []
        
        # Authors
        if m.authors:
            parts.append(self._format_authors_harvard(m.authors))
        
        # Year
        if m.year:
            parts.append(f"({m.year})")
        elif m.date:
            parts.append(f"({m.date})")
        
        # Title in single quotes
        if m.title:
            parts.append(f"'{m.title}',")
        
        # Newspaper in italics
        pub_name = m.newspaper or getattr(m, 'publication', '')
        if pub_name:
            parts.append(f"<i>{pub_name}</i>,")
        
        # Date
        if m.date:
            parts.append(f"{m.date},")
        
        # Page
        if m.pages:
            parts.append(f"p. {m.pages}.")
        
        # URL
        if m.url:
            parts.append(f"Available at: {m.url}")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # GOVERNMENT
    # =========================================================================
    
    def _format_government(self, m: CitationMetadata) -> str:
        """
        Harvard government document.
        
        Pattern: Agency (Year) Title. Place: Publisher.
        """
        parts = []
        
        # Agency
        if m.agency:
            parts.append(m.agency)
        
        # Year
        if m.year:
            parts.append(f"({m.year})")
        
        # Title in italics
        if m.title:
            parts.append(f"<i>{m.title}</i>.")
        
        # Document number
        if m.document_number:
            parts.append(f"({m.document_number})")
        
        # URL
        if m.url:
            parts.append(f"Available at: {m.url}")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # URL
    # =========================================================================
    
    def _format_url(self, m: CitationMetadata) -> str:
        """
        Harvard web page.
        
        Pattern: Author/Organisation (Year) Title. Available at: URL (Accessed: date).
        """
        parts = []
        
        # Authors or site as author
        if m.authors:
            parts.append(self._format_authors_harvard(m.authors))
        
        # Year or n.d.
        if m.year:
            parts.append(f"({m.year})")
        else:
            parts.append("(n.d.)")
        
        # Title in italics
        if m.title:
            parts.append(f"<i>{m.title}</i>.")
        
        # URL with Available at prefix
        if m.url:
            parts.append(f"Available at: {m.url}")
        
        # Access date
        if m.access_date:
            parts.append(f"(Accessed: {m.access_date}).")
        
        result = " ".join(parts)
        return self._ensure_period(result)
