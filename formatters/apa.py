"""
citeflex/formatters/apa.py

APA (7th edition) citation formatter.
Standard for social sciences and psychology.
"""

from models import CitationMetadata, CitationType, CitationStyle
from formatters.base import BaseFormatter


class APAFormatter(BaseFormatter):
    """
    APA 7th Edition formatter.
    
    Key features:
    - Author names: Last, F. M. format
    - Year in parentheses after author
    - Titles in sentence case
    - Journal names in italics with volume
    """
    
    style = CitationStyle.APA
    
    # =========================================================================
    # HELPER METHODS (Added 2025-12-11)
    # =========================================================================
    
    def _to_sentence_case(self, title: str) -> str:
        """
        Convert title to APA sentence case.
        
        APA 7 rules:
        - Capitalize first word
        - Capitalize first word after colon or em-dash
        - Capitalize proper nouns (we preserve existing capitals for proper nouns)
        - Lowercase everything else
        
        Examples:
        - "A Study on Economic Trends in the Late 1960s" → "A study on economic trends in the late 1960s"
        - "The Role of Information: A Framework" → "The role of information: A framework"
        """
        if not title:
            return ""
        
        import re
        
        # Common words that should stay lowercase (unless at start)
        # Note: We don't force these lowercase if author capitalized them (could be proper nouns)
        
        # Split on sentence boundaries (colon, em-dash, period followed by space)
        # We'll process each segment separately
        segments = re.split(r'(:\s*|—\s*|\.\s+)', title)
        
        result_parts = []
        for i, segment in enumerate(segments):
            if not segment:
                continue
            
            # If this is a delimiter, keep it
            if re.match(r'^[:\.\—]\s*$', segment):
                result_parts.append(segment)
                continue
            
            # Process the segment
            words = segment.split()
            processed_words = []
            
            for j, word in enumerate(words):
                if j == 0:
                    # First word of segment: capitalize first letter, lowercase rest
                    # But preserve internal capitals for proper nouns like "McGraw"
                    if word:
                        processed_words.append(word[0].upper() + word[1:].lower() if len(word) > 1 else word.upper())
                else:
                    # Not first word: lowercase unless it looks like a proper noun
                    # Heuristic: if it has internal capitals (McDonald, iPhone), preserve
                    # If ALL CAPS, convert to lowercase
                    # If Title Case, convert to lowercase
                    if word.isupper() and len(word) > 1:
                        # ALL CAPS → lowercase
                        processed_words.append(word.lower())
                    elif re.match(r'^[A-Z][a-z]*[A-Z]', word):
                        # Has internal capital (McNeill, iPhone) - preserve
                        processed_words.append(word)
                    elif word[0].isupper() and len(word) > 1:
                        # Title case - convert to lowercase
                        processed_words.append(word.lower())
                    else:
                        processed_words.append(word)
            
            result_parts.append(' '.join(processed_words))
        
        return ''.join(result_parts)
    
    def _normalize_doi(self, doi: str) -> str:
        """
        Normalize DOI to just the identifier part.
        
        Examples:
        - "10.1234/abc" → "10.1234/abc"
        - "https://doi.org/10.1234/abc" → "10.1234/abc"
        - "http://dx.doi.org/10.1234/abc" → "10.1234/abc"
        - "doi:10.1234/abc" → "10.1234/abc"
        """
        if not doi:
            return ""
        
        doi = doi.strip()
        
        # Remove common prefixes
        prefixes = [
            'https://doi.org/',
            'http://doi.org/',
            'https://dx.doi.org/',
            'http://dx.doi.org/',
            'doi.org/',
            'dx.doi.org/',
            'doi:',
            'DOI:',
        ]
        
        for prefix in prefixes:
            if doi.lower().startswith(prefix.lower()):
                doi = doi[len(prefix):]
                break
        
        return doi.strip()
    
    def _format_doi_url(self, doi: str) -> str:
        """Format DOI as full URL for APA 7."""
        normalized = self._normalize_doi(doi)
        if normalized:
            return f"https://doi.org/{normalized}"
        return ""
    
    def format(self, metadata: CitationMetadata) -> str:
        """Format a full APA-style citation."""
        
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
        """Format short APA citation (Author, Year)."""
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
        
        if metadata.year:
            parts.append(f"({metadata.year})")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    def _format_authors_apa(self, authors: list) -> str:
        """
        Format authors in APA style: Last, F. M.
        
        Rules:
        - Up to 20 authors: list all
        - 21+: list first 19, ellipsis, last author
        - Always use initials, never full first names
        
        Updated 2025-12-11: Handle full first names in "Last, First Middle" format
        """
        if not authors:
            return ""
        
        def format_one(name: str) -> str:
            """
            Convert any name format to 'Last, F. M.'
            
            Handles:
            - "First Last" → "Last, F."
            - "First Middle Last" → "Last, F. M."
            - "Last, First" → "Last, F."
            - "Last, First Middle" → "Last, F. M."
            - "Last, F. M." → "Last, F. M." (already correct)
            """
            import re
            
            name = name.strip()
            if not name:
                return ""
            
            # Check if already in "Last, Initials" format (initials are single letters with periods)
            # Pattern: "LastName, X." or "LastName, X. Y." etc.
            already_initials = re.match(r'^([A-Za-z\-\']+),\s*([A-Z]\.\s*)+$', name)
            if already_initials:
                return name  # Already correctly formatted
            
            # Check for "Last, First..." format (comma present)
            if ',' in name:
                parts = name.split(',', 1)
                last_name = parts[0].strip()
                first_parts = parts[1].strip().split()
                
                # Convert each first/middle name to initial
                initials = []
                for part in first_parts:
                    part = part.strip().rstrip('.')
                    if part:
                        # If it's already a single letter, use it
                        if len(part) == 1:
                            initials.append(part.upper() + ".")
                        else:
                            # Take first letter of full name
                            initials.append(part[0].upper() + ".")
                
                if initials:
                    return f"{last_name}, {' '.join(initials)}"
                else:
                    return last_name
            
            # No comma: "First Middle Last" format
            parts = name.split()
            if len(parts) == 0:
                return ""
            if len(parts) == 1:
                return parts[0]
            
            # Last word is surname, rest are given names
            last = parts[-1]
            initials = " ".join(p[0].upper() + "." for p in parts[:-1] if p)
            return f"{last}, {initials}"
        
        formatted = [format_one(a) for a in authors]
        
        if len(formatted) == 1:
            return formatted[0]
        elif len(formatted) == 2:
            return f"{formatted[0]}, & {formatted[1]}"
        elif len(formatted) <= 20:
            return ", ".join(formatted[:-1]) + f", & {formatted[-1]}"
        else:
            # 21+ authors
            first_19 = ", ".join(formatted[:19])
            return f"{first_19}, ... {formatted[-1]}"
    
    # =========================================================================
    # JOURNAL
    # =========================================================================
    
    def _format_journal(self, m: CitationMetadata) -> str:
        """
        APA journal article.
        
        Pattern: Author, A. A. (Year). Title. Journal, Volume(Issue), Pages. DOI
        
        Updated 2025-12-11: Apply sentence case to titles, normalize DOIs
        """
        parts = []
        
        # Authors
        if m.authors:
            parts.append(self._format_authors_apa(m.authors))
        
        # Year
        if m.year:
            parts.append(f"({m.year}).")
        
        # Title (sentence case, no italics) - APA 7 requirement
        if m.title:
            title = self._to_sentence_case(m.title)
            parts.append(title + ".")
        
        # Journal (italics), Volume(Issue), Pages
        journal_parts = []
        if m.journal:
            journal_parts.append(f"<i>{m.journal}</i>")
        
        if m.volume:
            vol_str = f"<i>{m.volume}</i>"
            if m.issue:
                vol_str += f"({m.issue})"
            journal_parts.append(vol_str)
        
        if m.pages:
            journal_parts.append(m.pages)
        
        if journal_parts:
            parts.append(", ".join(journal_parts) + ".")
        
        # DOI or URL - normalize DOI to https://doi.org/ format
        if m.doi:
            parts.append(self._format_doi_url(m.doi))
        elif m.url:
            parts.append(m.url)
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # BOOK
    # =========================================================================
    
    def _format_book(self, m: CitationMetadata) -> str:
        """
        APA book.
        
        Pattern: Author, A. A. (Year). Title (Edition). Publisher. DOI
        
        Updated 2025-12-11: Apply sentence case to titles, normalize DOIs
        """
        parts = []
        
        # Authors
        if m.authors:
            parts.append(self._format_authors_apa(m.authors))
        
        # Year
        if m.year:
            parts.append(f"({m.year}).")
        
        # Title in italics (sentence case per APA 7)
        if m.title:
            title = self._to_sentence_case(m.title)
            title_part = f"<i>{title}</i>"
            if m.edition:
                title_part += f" ({m.edition})"
            parts.append(title_part + ".")
        
        # Publisher (APA 7: no location, just publisher name)
        if m.publisher:
            parts.append(m.publisher + ".")
        
        # DOI or URL
        if m.doi:
            parts.append(self._format_doi_url(m.doi))
        elif m.url:
            parts.append(m.url)
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # LEGAL (APA has different legal style from Bluebook)
    # =========================================================================
    
    def _format_legal(self, m: CitationMetadata) -> str:
        """
        APA legal case.
        
        Pattern: Name v. Name, Citation (Court Year).
        """
        parts = []
        
        # Case name (italics in APA)
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
        """
        APA interview (personal communication).
        
        Note: APA doesn't include interviews in reference lists;
        they're cited in-text only. This provides a reference-style format.
        """
        parts = []
        
        # Interviewee as author
        if m.interviewee:
            # Convert to APA author format
            parts.append(self._format_authors_apa([m.interviewee]))
        
        # Year
        if m.year:
            parts.append(f"({m.year}).")
        elif m.date:
            parts.append(f"({m.date}).")
        
        # Type of communication
        parts.append("[Personal interview].")
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # LETTER/CORRESPONDENCE
    # =========================================================================
    
    def _format_letter(self, m: CitationMetadata) -> str:
        """
        APA letter (personal communication).
        
        Note: APA treats letters as personal communications, typically
        cited in-text only. This provides a reference-style format.
        
        Pattern: Sender, S. (Date). [Letter to Recipient]. Collection.
        """
        parts = []
        
        # Sender as author
        if m.sender:
            parts.append(self._format_authors_apa([m.sender]))
        
        # Date
        if m.date:
            parts.append(f"({m.date}).")
        elif m.year:
            parts.append(f"({m.year}).")
        
        # Description with recipient
        if m.recipient:
            parts.append(f"[Letter to {m.recipient}].")
        else:
            parts.append("[Personal correspondence].")
        
        # Subject if present
        if m.title:
            parts.append(f'"{m.title}."')
        
        # Collection/location
        if m.location:
            parts.append(m.location + ".")
        
        # URL
        if m.url:
            parts.append(m.url)
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # NEWSPAPER
    # =========================================================================
    
    def _format_newspaper(self, m: CitationMetadata) -> str:
        """
        APA newspaper article.
        
        Pattern: Author, A. A. (Year, Month Day). Title. Publication. URL
        
        Updated 2025-12-11: Apply sentence case to titles
        """
        parts = []
        
        # Authors
        if m.authors:
            parts.append(self._format_authors_apa(m.authors))
        
        # Date
        if m.date:
            parts.append(f"({m.date}).")
        elif m.year:
            parts.append(f"({m.year}).")
        
        # Title (sentence case per APA 7)
        if m.title:
            title = self._to_sentence_case(m.title)
            parts.append(title + ".")
        
        # Publication (italics)
        pub_name = m.newspaper or getattr(m, 'publication', '')
        if pub_name:
            parts.append(f"<i>{pub_name}</i>.")
        
        # URL
        if m.url:
            parts.append(m.url)
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # GOVERNMENT
    # =========================================================================
    
    def _format_government(self, m: CitationMetadata) -> str:
        """
        APA government document.
        
        Pattern: Agency. (Year). Title (Publication No.). Publisher. URL
        """
        parts = []
        
        # Agency as author
        if m.agency:
            parts.append(m.agency + ".")
        
        # Year
        if m.year:
            parts.append(f"({m.year}).")
        
        # Title in italics
        if m.title:
            title_part = f"<i>{m.title}</i>"
            if m.document_number:
                title_part += f" ({m.document_number})"
            parts.append(title_part + ".")
        
        # URL
        if m.url:
            parts.append(m.url)
        
        result = " ".join(parts)
        return self._ensure_period(result)
    
    # =========================================================================
    # URL
    # =========================================================================
    
    def _format_url(self, m: CitationMetadata) -> str:
        """
        APA web page.
        
        Pattern: Author. (Year). Title. Site Name. URL
        
        Updated 2025-12-11: Apply sentence case to titles
        """
        parts = []
        
        # Authors or site as author
        if m.authors:
            parts.append(self._format_authors_apa(m.authors))
        
        # Year or n.d.
        if m.year:
            parts.append(f"({m.year}).")
        else:
            parts.append("(n.d.).")
        
        # Title in italics (sentence case per APA 7)
        if m.title:
            title = self._to_sentence_case(m.title)
            parts.append(f"<i>{title}</i>.")
        
        # URL
        if m.url:
            parts.append(m.url)
        
        result = " ".join(parts)
        return self._ensure_period(result)
