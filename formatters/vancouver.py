"""
citeflex/formatters/vancouver.py

Vancouver (ICMJE) citation formatter.
Standard for biomedical and scientific publications.

The Vancouver system uses numbered references in order of first appearance.
Used by 5,000+ journals including NEJM, JAMA, Lancet, BMJ, Nature, Science.

Key features:
- Authors: Last FM (no periods between initials, max 6 then et al.)
- No quotation marks around article titles
- Journal names abbreviated (when known)
- Volume, pages follow with semicolon/colon pattern

Example:
  1. Smith J, Doe A, Johnson B. Effects of climate change on polar bears. 
     Nature. 2020;580(7803):123-45.
"""

from models import CitationMetadata, CitationType, CitationStyle
from formatters.base import BaseFormatter


# Common journal abbreviations (subset - real implementation would have thousands)
JOURNAL_ABBREVIATIONS = {
    'nature': 'Nature',
    'science': 'Science',
    'cell': 'Cell',
    'the lancet': 'Lancet',
    'lancet': 'Lancet',
    'new england journal of medicine': 'N Engl J Med',
    'jama': 'JAMA',
    'the journal of the american medical association': 'JAMA',
    'journal of the american medical association': 'JAMA',
    'british medical journal': 'BMJ',
    'bmj': 'BMJ',
    'annals of internal medicine': 'Ann Intern Med',
    'circulation': 'Circulation',
    'proceedings of the national academy of sciences': 'Proc Natl Acad Sci USA',
    'pnas': 'Proc Natl Acad Sci USA',
    'journal of biological chemistry': 'J Biol Chem',
    'journal of clinical investigation': 'J Clin Invest',
    'nature medicine': 'Nat Med',
    'nature genetics': 'Nat Genet',
    'nature neuroscience': 'Nat Neurosci',
    'neuron': 'Neuron',
    'the american journal of psychiatry': 'Am J Psychiatry',
    'archives of general psychiatry': 'Arch Gen Psychiatry',
    'psychological bulletin': 'Psychol Bull',
    'psychological review': 'Psychol Rev',
}


class VancouverFormatter(BaseFormatter):
    """
    Vancouver (ICMJE) formatter.
    
    Standard numbered citation system for biomedical literature.
    
    Key features:
    - Author names: Last FM (no periods, no commas between initials)
    - Up to 6 authors, then et al.
    - Article titles not in quotes
    - Journal names abbreviated
    - Volume;Pages format with colon
    """
    
    style = CitationStyle.CHICAGO  # Closest enum match
    
    def format(self, metadata: CitationMetadata) -> str:
        """Format a full Vancouver-style citation."""
        
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
        Format short Vancouver citation.
        
        In Vancouver, subsequent references just use the number.
        For display purposes, we show author(s) and year.
        """
        parts = []
        
        if metadata.authors:
            last_name = self._get_last_name(metadata.authors[0])
            if len(metadata.authors) == 2:
                last_name2 = self._get_last_name(metadata.authors[1])
                parts.append(f"{last_name} & {last_name2}")
            elif len(metadata.authors) > 2:
                parts.append(f"{last_name} et al.")
            else:
                parts.append(last_name)
        elif metadata.case_name:
            parts.append(f"<i>{metadata.case_name}</i>")
        
        if metadata.year:
            parts.append(f"({metadata.year})")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    def _format_authors_vancouver(self, authors: list) -> str:
        """
        Format authors in Vancouver style: Last FM
        
        Rules:
        - No periods between initials: Smith JA not Smith J.A.
        - No comma between last name and initials
        - List up to 6 authors, then add et al.
        - Separate authors with commas
        """
        if not authors:
            return ""
        
        def format_one(name: str) -> str:
            """Convert 'First Middle Last' to 'Last FM'"""
            name = name.strip()
            
            # Handle "Last, First Middle" format
            if ',' in name:
                parts = name.split(',')
                last = parts[0].strip()
                first_parts = parts[1].strip().split() if len(parts) > 1 else []
                initials = "".join(p[0].upper() for p in first_parts if p)
                return f"{last} {initials}" if initials else last
            
            # Handle "First Middle Last" format
            parts = name.split()
            if len(parts) == 0:
                return ""
            if len(parts) == 1:
                return parts[0]
            
            last = parts[-1]
            initials = "".join(p[0].upper() for p in parts[:-1] if p)
            return f"{last} {initials}"
        
        formatted = [format_one(a) for a in authors]
        
        if len(formatted) <= 6:
            return ", ".join(formatted)
        else:
            # More than 6: list first 6, then et al.
            return ", ".join(formatted[:6]) + ", et al."
    
    def _abbreviate_journal(self, journal: str) -> str:
        """
        Get abbreviated journal name if known.
        
        Vancouver style uses NLM journal abbreviations.
        """
        if not journal:
            return ""
        
        journal_lower = journal.lower().strip()
        return JOURNAL_ABBREVIATIONS.get(journal_lower, journal)
    
    # =========================================================================
    # JOURNAL
    # =========================================================================
    
    def _format_journal(self, m: CitationMetadata) -> str:
        """
        Vancouver journal article.
        
        Pattern: Authors. Title. Journal. Year;Volume(Issue):Pages.
        
        Example:
          Smith J, Doe A. Effects of climate change. Nature. 2020;580(7803):123-45.
        """
        parts = []
        
        # Authors
        if m.authors:
            parts.append(self._format_authors_vancouver(m.authors) + ".")
        
        # Title (no quotes, sentence case)
        if m.title:
            title = m.title.rstrip('.')
            parts.append(title + ".")
        
        # Journal (abbreviated if possible)
        if m.journal:
            journal = self._abbreviate_journal(m.journal)
            parts.append(journal + ".")
        
        # Year;Volume(Issue):Pages
        pub_info = ""
        if m.year:
            pub_info = m.year
        
        if m.volume:
            pub_info += f";{m.volume}"
            if m.issue:
                pub_info += f"({m.issue})"
        
        if m.pages:
            # Vancouver shortens page ranges: 123-145 becomes 123-45
            pages = self._shorten_pages(m.pages)
            pub_info += f":{pages}"
        
        if pub_info:
            parts.append(pub_info + ".")
        
        # DOI or PMID
        if m.doi:
            doi = m.doi.replace('https://doi.org/', '').replace('http://doi.org/', '')
            parts.append(f"doi:{doi}")
        elif m.pmid:
            parts.append(f"PMID: {m.pmid}")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    def _shorten_pages(self, pages: str) -> str:
        """
        Shorten page ranges per Vancouver style.
        
        123-145 becomes 123-45
        1234-1256 becomes 1234-56
        """
        if '-' not in pages and '–' not in pages:
            return pages
        
        # Handle both regular and en-dash
        sep = '-' if '-' in pages else '–'
        parts = pages.split(sep)
        
        if len(parts) != 2:
            return pages
        
        start, end = parts[0].strip(), parts[1].strip()
        
        # Only shorten if both are numeric
        if not start.isdigit() or not end.isdigit():
            return pages
        
        # Find common prefix length
        for i in range(min(len(start), len(end))):
            if i >= len(end) or start[i] != end[i]:
                break
        
        # Don't shorten to single digit
        if len(end) - i < 2 and len(end) > 2:
            i = len(end) - 2
        
        # Return shortened form
        if i > 0 and i < len(end):
            return f"{start}-{end[i:]}"
        return pages
    
    # =========================================================================
    # BOOK
    # =========================================================================
    
    def _format_book(self, m: CitationMetadata) -> str:
        """
        Vancouver book.
        
        Pattern: Authors. Title. Edition. Place: Publisher; Year.
        
        Example:
          Russell B. A history of western philosophy. New York: Simon & Schuster; 1945.
        """
        parts = []
        
        # Authors
        if m.authors:
            parts.append(self._format_authors_vancouver(m.authors) + ".")
        
        # Title (no italics in Vancouver)
        if m.title:
            parts.append(m.title + ".")
        
        # Edition
        if m.edition:
            parts.append(f"{m.edition}.")
        
        # Place: Publisher; Year
        pub_parts = []
        if m.place:
            pub_parts.append(m.place)
        if m.publisher:
            if pub_parts:
                pub_parts.append(f": {m.publisher}")
            else:
                pub_parts.append(m.publisher)
        if m.year:
            if pub_parts:
                pub_parts.append(f"; {m.year}")
            else:
                pub_parts.append(m.year)
        
        if pub_parts:
            parts.append("".join(pub_parts) + ".")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # LEGAL
    # =========================================================================
    
    def _format_legal(self, m: CitationMetadata) -> str:
        """
        Vancouver legal case (rare in medical literature).
        
        Pattern: Case Name. Citation (Court Year).
        """
        parts = []
        
        if m.case_name:
            parts.append(m.case_name + ".")
        
        if m.citation:
            cite_part = m.citation
            if m.year and m.year not in cite_part:
                cite_part += f" ({m.year})"
            parts.append(cite_part + ".")
        elif m.neutral_citation:
            parts.append(m.neutral_citation + ".")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # INTERVIEW
    # =========================================================================
    
    def _format_interview(self, m: CitationMetadata) -> str:
        """
        Vancouver interview (personal communication).
        
        Note: Vancouver typically cites personal communications in-text only.
        """
        parts = []
        
        if m.interviewee:
            parts.append(self._format_authors_vancouver([m.interviewee]) + ".")
        
        parts.append("Personal communication.")
        
        if m.date:
            parts.append(m.date + ".")
        elif m.year:
            parts.append(m.year + ".")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # LETTER
    # =========================================================================
    
    def _format_letter(self, m: CitationMetadata) -> str:
        """Vancouver letter/correspondence."""
        parts = []
        
        if m.sender:
            parts.append(self._format_authors_vancouver([m.sender]) + ".")
        
        if m.title:
            parts.append(m.title + ".")
        elif m.recipient:
            parts.append(f"Letter to {m.recipient}.")
        else:
            parts.append("Personal correspondence.")
        
        if m.date:
            parts.append(m.date + ".")
        elif m.year:
            parts.append(m.year + ".")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # NEWSPAPER
    # =========================================================================
    
    def _format_newspaper(self, m: CitationMetadata) -> str:
        """
        Vancouver newspaper.
        
        Pattern: Author. Title. Newspaper. Year Mon Day;Sect:Pages.
        """
        parts = []
        
        if m.authors:
            parts.append(self._format_authors_vancouver(m.authors) + ".")
        
        if m.title:
            parts.append(m.title + ".")
        
        pub_name = m.newspaper or getattr(m, 'publication', '')
        if pub_name:
            parts.append(pub_name + ".")
        
        if m.date:
            parts.append(m.date + ".")
        elif m.year:
            parts.append(m.year + ".")
        
        if m.url:
            parts.append(f"Available from: {m.url}")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # GOVERNMENT
    # =========================================================================
    
    def _format_government(self, m: CitationMetadata) -> str:
        """
        Vancouver government document.
        
        Pattern: Agency. Title. Place: Publisher; Year.
        """
        parts = []
        
        if m.agency:
            parts.append(m.agency + ".")
        
        if m.title:
            title = m.title
            if m.document_number:
                title += f" ({m.document_number})"
            parts.append(title + ".")
        
        # Place: Publisher; Year
        pub_parts = []
        if m.place:
            pub_parts.append(m.place)
        if m.publisher:
            if pub_parts:
                pub_parts.append(f": {m.publisher}")
            else:
                pub_parts.append(m.publisher)
        if m.year:
            if pub_parts:
                pub_parts.append(f"; {m.year}")
            else:
                pub_parts.append(m.year)
        
        if pub_parts:
            parts.append("".join(pub_parts) + ".")
        
        if m.url:
            parts.append(f"Available from: {m.url}")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # URL
    # =========================================================================
    
    def _format_url(self, m: CitationMetadata) -> str:
        """
        Vancouver web page.
        
        Pattern: Author/Organization. Title [Internet]. Place: Publisher; 
                 Year [cited Date]. Available from: URL
        """
        parts = []
        
        if m.authors:
            parts.append(self._format_authors_vancouver(m.authors) + ".")
        
        if m.title:
            parts.append(m.title + " [Internet].")
        
        if m.year:
            cite_part = m.year
            if m.access_date:
                cite_part += f" [cited {m.access_date}]"
            parts.append(cite_part + ".")
        
        if m.url:
            parts.append(f"Available from: {m.url}")
        
        result = " ".join(parts)
        return self._ensure_period(result)
