"""
citeflex/exporters/bibtex.py

BibTeX format exporter for citation data.

BibTeX is the standard bibliography format for LaTeX documents,
widely used in academic publishing, especially in:
- Computer Science
- Mathematics
- Physics
- Engineering

Also supported by:
- Zotero
- JabRef
- Mendeley
- BibDesk
"""

import re
import unicodedata
from typing import List, Optional
from exporters.base import BaseExporter, ExportFormat
from models import CitationMetadata, CitationType


class BibTeXExporter(BaseExporter):
    """
    Export citations to BibTeX format.
    
    Produces .bib files compatible with LaTeX and reference managers.
    """
    
    format = ExportFormat.BIBTEX
    
    @property
    def file_extension(self) -> str:
        return "bib"
    
    @property
    def mime_type(self) -> str:
        return "application/x-bibtex"
    
    # Mapping from CitationType to BibTeX entry types
    TYPE_MAP = {
        CitationType.JOURNAL: "article",
        CitationType.BOOK: "book",
        CitationType.LEGAL: "misc",  # No standard legal type in BibTeX
        CitationType.NEWSPAPER: "article",
        CitationType.GOVERNMENT: "techreport",
        CitationType.MEDICAL: "article",
        CitationType.INTERVIEW: "misc",
        CitationType.LETTER: "misc",
        CitationType.URL: "misc",
        CitationType.UNKNOWN: "misc",
    }
    
    def __init__(self):
        self._key_counter = {}  # Track used keys to ensure uniqueness
    
    def export(self, citations: List[CitationMetadata]) -> str:
        """
        Export citations to BibTeX format string.
        
        Args:
            citations: List of CitationMetadata objects
            
        Returns:
            BibTeX formatted string
        """
        # Reset key counter for each export
        self._key_counter = {}
        
        entries = []
        
        for citation in citations:
            entry = self._format_entry(citation)
            entries.append(entry)
        
        return "\n\n".join(entries)
    
    def _format_entry(self, metadata: CitationMetadata) -> str:
        """
        Format a single citation as a BibTeX entry.
        
        Args:
            metadata: Citation metadata
            
        Returns:
            BibTeX entry string
        """
        # Determine entry type
        entry_type = self.TYPE_MAP.get(metadata.citation_type, "misc")
        
        # Generate citation key
        key = self._generate_key(metadata)
        
        # Build fields
        fields = []
        
        # Author(s)
        if metadata.authors or metadata.authors_parsed:
            authors = self._format_authors_bibtex(metadata)
            if authors:
                fields.append(f'  author = {{{authors}}}')
        
        # Title
        if metadata.title:
            # Preserve capitalization with braces
            title = self._escape_bibtex(metadata.title)
            fields.append(f'  title = {{{{{title}}}}}')
        
        # Year
        if metadata.year:
            fields.append(f'  year = {{{metadata.year}}}')
        
        # Journal/publication
        if metadata.journal:
            journal = self._escape_bibtex(metadata.journal)
            fields.append(f'  journal = {{{journal}}}')
        
        if metadata.newspaper and not metadata.journal:
            newspaper = self._escape_bibtex(metadata.newspaper)
            fields.append(f'  journal = {{{newspaper}}}')
        
        # Volume, number, pages
        if metadata.volume:
            fields.append(f'  volume = {{{metadata.volume}}}')
        
        if metadata.issue:
            fields.append(f'  number = {{{metadata.issue}}}')
        
        if metadata.pages:
            # BibTeX uses -- for page ranges
            pages = metadata.pages.replace("-", "--").replace("–", "--")
            fields.append(f'  pages = {{{pages}}}')
        
        # Publisher and address
        if metadata.publisher:
            publisher = self._escape_bibtex(metadata.publisher)
            fields.append(f'  publisher = {{{publisher}}}')
        
        if metadata.place:
            place = self._escape_bibtex(metadata.place)
            fields.append(f'  address = {{{place}}}')
        
        # Edition
        if metadata.edition:
            fields.append(f'  edition = {{{metadata.edition}}}')
        
        # DOI
        if metadata.doi:
            fields.append(f'  doi = {{{metadata.doi}}}')
        
        # URL
        if metadata.url:
            fields.append(f'  url = {{{metadata.url}}}')
        
        # ISBN
        if metadata.isbn:
            fields.append(f'  isbn = {{{metadata.isbn}}}')
        
        # Note for additional info
        notes = []
        if metadata.source_engine:
            notes.append(f"Source: {metadata.source_engine}")
        if metadata.citation_type == CitationType.LEGAL and metadata.citation:
            notes.append(f"Legal citation: {metadata.citation}")
        if metadata.court:
            notes.append(f"Court: {metadata.court}")
        
        if notes:
            note_text = self._escape_bibtex("; ".join(notes))
            fields.append(f'  note = {{{note_text}}}')
        
        # Build the entry
        fields_str = ",\n".join(fields)
        return f"@{entry_type}{{{key},\n{fields_str}\n}}"
    
    def _generate_key(self, metadata: CitationMetadata) -> str:
        """
        Generate a unique BibTeX citation key.
        
        Format: AuthorYear or AuthorYearLetter for duplicates
        Example: Smith2024, Smith2024a, Smith2024b
        
        Args:
            metadata: Citation metadata
            
        Returns:
            Unique citation key
        """
        # Get first author's last name
        author_part = "Unknown"
        
        if metadata.authors_parsed:
            first_author = metadata.authors_parsed[0]
            author_part = first_author.get('family', 'Unknown')
        elif metadata.authors:
            # Try to extract last name
            first_author = metadata.authors[0]
            if ',' in first_author:
                author_part = first_author.split(',')[0].strip()
            else:
                parts = first_author.split()
                author_part = parts[-1] if parts else "Unknown"
        
        # Clean author name for key
        author_part = self._clean_key_part(author_part)
        
        # Year
        year_part = metadata.year or "nodate"
        
        # Base key
        base_key = f"{author_part}{year_part}"
        
        # Ensure uniqueness
        if base_key not in self._key_counter:
            self._key_counter[base_key] = 0
            return base_key
        
        # Add letter suffix for duplicates
        self._key_counter[base_key] += 1
        suffix = chr(ord('a') + self._key_counter[base_key] - 1)
        return f"{base_key}{suffix}"
    
    def _clean_key_part(self, text: str) -> str:
        """
        Clean text for use in a BibTeX key.
        
        Removes special characters, converts to ASCII.
        
        Args:
            text: Raw text
            
        Returns:
            Cleaned text suitable for key
        """
        if not text:
            return "Unknown"
        
        # Normalize unicode (convert accented chars to ASCII equivalents)
        text = unicodedata.normalize('NFKD', text)
        text = text.encode('ascii', 'ignore').decode('ascii')
        
        # Remove non-alphanumeric characters
        text = re.sub(r'[^a-zA-Z0-9]', '', text)
        
        return text or "Unknown"
    
    def _format_authors_bibtex(self, metadata: CitationMetadata) -> str:
        """
        Format authors for BibTeX.
        
        BibTeX format: "Last1, First1 and Last2, First2 and Last3, First3"
        
        Args:
            metadata: Citation metadata
            
        Returns:
            BibTeX-formatted author string
        """
        authors = self._format_authors_list(metadata)
        
        if not authors:
            return ""
        
        # BibTeX uses " and " to separate authors
        return " and ".join(authors)
    
    def _escape_bibtex(self, text: str) -> str:
        """
        Escape special characters for BibTeX.
        
        Args:
            text: Raw text
            
        Returns:
            Escaped text safe for BibTeX
        """
        if not text:
            return ""
        
        # BibTeX special characters
        replacements = [
            ('&', r'\&'),
            ('%', r'\%'),
            ('$', r'\$'),
            ('#', r'\#'),
            ('_', r'\_'),
            ('{', r'\{'),
            ('}', r'\}'),
            ('~', r'\textasciitilde{}'),
            ('^', r'\textasciicircum{}'),
        ]
        
        for old, new in replacements:
            text = text.replace(old, new)
        
        return text
