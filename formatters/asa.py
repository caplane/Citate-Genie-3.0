"""
citeflex/formatters/asa.py

ASA (American Sociological Association) citation formatter.
Standard for sociology publications.

Key differences from APA:
- Full first names (not initials): "Smith, John" not "Smith, J."
- Year after author (not in parentheses): "Smith, John. 2020." not "Smith, J. (2020)."
- Article titles in quotes: "Title of Article"
- No comma before page numbers: 580:123-145 not 580, 123-145
- Journal names in italics

Example:
  Smith, John and Jane Doe. 2020. "The Effects of Climate Change." 
  Nature 580(7803):123-145. doi:10.1038/xyz.
"""

from models import CitationMetadata, CitationType, CitationStyle
from formatters.base import BaseFormatter


class ASAFormatter(BaseFormatter):
    """
    ASA (American Sociological Association) 6th Edition formatter.
    
    Key features:
    - Full author names: Last, First Middle
    - Year after author (no parentheses)
    - Article titles in quotation marks
    - Book titles in italics
    - No comma between volume and pages
    """
    
    style = CitationStyle.CHICAGO  # Closest enum match
    
    def format(self, metadata: CitationMetadata) -> str:
        """Format a full ASA-style citation."""
        
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
        """
        Format short ASA citation (Author Year).
        
        ASA uses Author (Year) for in-text citations.
        """
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
        elif metadata.case_name:
            # Legal short form
            parts.append(f"<i>{metadata.case_name}</i>")
        
        if metadata.year:
            parts.append(metadata.year)
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    def _format_authors_asa(self, authors: list) -> str:
        """
        Format authors in ASA style: Last, First Middle
        
        Rules:
        - Use full first names, not initials
        - First author: Last, First
        - Subsequent authors: First Last
        - Use "and" before final author
        """
        if not authors:
            return ""
        
        def format_first_author(name: str) -> str:
            """First author: Last, First"""
            parts = name.strip().split()
            if len(parts) == 0:
                return ""
            if len(parts) == 1:
                return parts[0]
            
            # Check for "Last, First" format already
            if ',' in name:
                return name
            
            # Convert "First Middle Last" to "Last, First Middle"
            last = parts[-1]
            first_middle = " ".join(parts[:-1])
            return f"{last}, {first_middle}"
        
        def format_subsequent_author(name: str) -> str:
            """Subsequent authors: First Last (as given)"""
            # If already in "Last, First" format, convert to "First Last"
            if ',' in name:
                parts = name.split(',')
                last = parts[0].strip()
                first = parts[1].strip() if len(parts) > 1 else ""
                return f"{first} {last}".strip()
            return name
        
        if len(authors) == 1:
            return format_first_author(authors[0])
        elif len(authors) == 2:
            return f"{format_first_author(authors[0])} and {format_subsequent_author(authors[1])}"
        elif len(authors) == 3:
            return (f"{format_first_author(authors[0])}, "
                    f"{format_subsequent_author(authors[1])}, and "
                    f"{format_subsequent_author(authors[2])}")
        else:
            # 4+ authors: list all (ASA lists all authors, no et al. in reference list)
            first = format_first_author(authors[0])
            middle = ", ".join(format_subsequent_author(a) for a in authors[1:-1])
            last = format_subsequent_author(authors[-1])
            return f"{first}, {middle}, and {last}"
    
    # =========================================================================
    # JOURNAL
    # =========================================================================
    
    def _format_journal(self, m: CitationMetadata) -> str:
        """
        ASA journal article.
        
        Pattern: Author, First. Year. "Title." Journal Volume(Issue):Pages. DOI.
        
        Example:
          Smith, John and Jane Doe. 2020. "The Effects of Climate Change." 
          Nature 580(7803):123-145. doi:10.1038/xyz.
        """
        parts = []
        
        # Authors
        if m.authors:
            parts.append(self._format_authors_asa(m.authors) + ".")
        
        # Year (no parentheses in ASA)
        if m.year:
            parts.append(m.year + ".")
        
        # Title in quotes
        if m.title:
            # Ensure title doesn't already have quotes
            title = m.title.strip('"').strip('"').strip('"')
            parts.append(f'"{title}."')
        
        # Journal (italics), Volume(Issue):Pages
        journal_part = ""
        if m.journal:
            journal_part = f"<i>{m.journal}</i>"
        
        if m.volume:
            journal_part += f" {m.volume}"
            if m.issue:
                journal_part += f"({m.issue})"
        
        if m.pages:
            # ASA uses colon, no comma before pages
            journal_part += f":{m.pages}"
        
        if journal_part:
            parts.append(journal_part + ".")
        
        # DOI (lowercase "doi:" in ASA)
        if m.doi:
            doi = m.doi.replace('https://doi.org/', '').replace('http://doi.org/', '')
            parts.append(f"doi:{doi}.")
        elif m.url:
            parts.append(f"Retrieved from {m.url}")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # BOOK
    # =========================================================================
    
    def _format_book(self, m: CitationMetadata) -> str:
        """
        ASA book.
        
        Pattern: Author, First. Year. Title. Place: Publisher.
        
        Example:
          Russell, Bertrand. 1945. A History of Western Philosophy. 
          New York: Simon & Schuster.
        """
        parts = []
        
        # Authors
        if m.authors:
            parts.append(self._format_authors_asa(m.authors) + ".")
        
        # Year
        if m.year:
            parts.append(m.year + ".")
        
        # Title in italics
        if m.title:
            title_part = f"<i>{m.title}</i>"
            if m.edition:
                title_part += f", {m.edition}"
            parts.append(title_part + ".")
        
        # Place: Publisher
        pub_parts = []
        if m.place:
            pub_parts.append(m.place)
        if m.publisher:
            pub_parts.append(m.publisher)
        if pub_parts:
            parts.append(": ".join(pub_parts) + ".")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # LEGAL
    # =========================================================================
    
    def _format_legal(self, m: CitationMetadata) -> str:
        """
        ASA legal case.
        
        Pattern: Case Name. Year. Citation.
        """
        parts = []
        
        # Case name (italics)
        if m.case_name:
            parts.append(f"<i>{m.case_name}</i>.")
        
        # Year
        if m.year:
            parts.append(m.year + ".")
        
        # Citation
        if m.citation:
            parts.append(m.citation + ".")
        elif m.neutral_citation:
            parts.append(m.neutral_citation + ".")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # INTERVIEW
    # =========================================================================
    
    def _format_interview(self, m: CitationMetadata) -> str:
        """
        ASA interview.
        
        Pattern: Interviewee, Name. Year. Interview by Interviewer. Location, Date.
        """
        parts = []
        
        # Interviewee
        if m.interviewee:
            parts.append(self._format_authors_asa([m.interviewee]) + ".")
        
        # Year
        if m.year:
            parts.append(m.year + ".")
        elif m.date:
            # Extract year from date if possible
            year = m.date.split(',')[-1].strip() if ',' in m.date else m.date.split()[-1]
            parts.append(year + ".")
        
        # Interview description
        if m.interviewer:
            parts.append(f"Interview by {m.interviewer}.")
        else:
            parts.append("Personal interview.")
        
        # Location and date
        loc_date = []
        if m.location:
            loc_date.append(m.location)
        if m.date:
            loc_date.append(m.date)
        if loc_date:
            parts.append(", ".join(loc_date) + ".")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # LETTER/CORRESPONDENCE
    # =========================================================================
    
    def _format_letter(self, m: CitationMetadata) -> str:
        """
        ASA letter.
        
        Pattern: Sender, Name. Year. "Subject/Description." Letter to Recipient. Date.
        """
        parts = []
        
        # Sender
        if m.sender:
            parts.append(self._format_authors_asa([m.sender]) + ".")
        
        # Year
        if m.year:
            parts.append(m.year + ".")
        
        # Subject/title in quotes if present
        if m.title:
            parts.append(f'"{m.title}."')
        
        # Letter to recipient
        if m.recipient:
            parts.append(f"Letter to {m.recipient}.")
        else:
            parts.append("Personal correspondence.")
        
        # Date and location
        if m.date:
            parts.append(m.date + ".")
        if m.location:
            parts.append(m.location + ".")
        
        # URL
        if m.url:
            parts.append(f"Retrieved from {m.url}")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # NEWSPAPER
    # =========================================================================
    
    def _format_newspaper(self, m: CitationMetadata) -> str:
        """
        ASA newspaper article.
        
        Pattern: Author, First. Year. "Title." Publication, Date, Pages.
        """
        parts = []
        
        # Authors
        if m.authors:
            parts.append(self._format_authors_asa(m.authors) + ".")
        
        # Year
        if m.year:
            parts.append(m.year + ".")
        
        # Title in quotes
        if m.title:
            parts.append(f'"{m.title}."')
        
        # Publication (italics)
        pub_name = m.newspaper or getattr(m, 'publication', '')
        if pub_name:
            pub_part = f"<i>{pub_name}</i>"
            if m.date:
                pub_part += f", {m.date}"
            if m.pages:
                pub_part += f", pp. {m.pages}"
            parts.append(pub_part + ".")
        
        # URL
        if m.url:
            parts.append(f"Retrieved from {m.url}")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # GOVERNMENT
    # =========================================================================
    
    def _format_government(self, m: CitationMetadata) -> str:
        """
        ASA government document.
        
        Pattern: Agency. Year. Title. Place: Publisher.
        """
        parts = []
        
        # Agency as author
        if m.agency:
            parts.append(m.agency + ".")
        
        # Year
        if m.year:
            parts.append(m.year + ".")
        
        # Title in italics
        if m.title:
            title_part = f"<i>{m.title}</i>"
            if m.document_number:
                title_part += f" ({m.document_number})"
            parts.append(title_part + ".")
        
        # Location and publisher
        if m.place and m.publisher:
            parts.append(f"{m.place}: {m.publisher}.")
        elif m.publisher:
            parts.append(m.publisher + ".")
        
        # URL
        if m.url:
            parts.append(f"Retrieved from {m.url}")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # URL
    # =========================================================================
    
    def _format_url(self, m: CitationMetadata) -> str:
        """
        ASA web page.
        
        Pattern: Author. Year. "Title." Retrieved Date (URL).
        """
        parts = []
        
        # Authors or organization
        if m.authors:
            parts.append(self._format_authors_asa(m.authors) + ".")
        
        # Year or N.d.
        if m.year:
            parts.append(m.year + ".")
        else:
            parts.append("N.d.")
        
        # Title in quotes
        if m.title:
            parts.append(f'"{m.title}."')
        
        # URL with access date
        if m.url:
            if m.access_date:
                parts.append(f"Retrieved {m.access_date} ({m.url}).")
            else:
                parts.append(f"Retrieved from {m.url}")
        
        result = " ".join(parts)
        return self._ensure_period(result)
