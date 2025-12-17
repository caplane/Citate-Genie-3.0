"""
citeflex/exporters/base.py

Base exporter class and factory function.
All export format implementations inherit from BaseExporter.

Supported formats:
- RIS: Universal interchange (EndNote, Zotero, Mendeley, RefWorks)
- CSV: Spreadsheet-compatible with all metadata fields
- BibTeX: LaTeX users, Zotero, JabRef
"""

from abc import ABC, abstractmethod
from typing import List, Optional, IO
from enum import Enum

from models import CitationMetadata


class ExportFormat(Enum):
    """Supported export formats."""
    RIS = "ris"
    CSV = "csv"
    BIBTEX = "bibtex"


class BaseExporter(ABC):
    """
    Abstract base class for citation exporters.
    
    Each exporter must implement:
    - export(citations) -> str: Convert citations to format string
    - file_extension: Property returning the file extension
    - mime_type: Property returning the MIME type for downloads
    
    The base class provides:
    - export_to_file(): Write to file handle
    - get_filename(): Generate appropriate filename
    """
    
    format: ExportFormat = ExportFormat.RIS
    
    @property
    @abstractmethod
    def file_extension(self) -> str:
        """Return file extension (without dot)."""
        pass
    
    @property
    @abstractmethod
    def mime_type(self) -> str:
        """Return MIME type for HTTP downloads."""
        pass
    
    @abstractmethod
    def export(self, citations: List[CitationMetadata]) -> str:
        """
        Export citations to format string.
        
        Args:
            citations: List of CitationMetadata objects
            
        Returns:
            Formatted string in the export format
        """
        pass
    
    def export_to_file(self, citations: List[CitationMetadata], file_handle: IO[str]) -> None:
        """
        Write exported citations to a file handle.
        
        Args:
            citations: List of CitationMetadata objects
            file_handle: Open file handle to write to
        """
        content = self.export(citations)
        file_handle.write(content)
    
    def get_filename(self, base_name: str = "citations") -> str:
        """
        Generate appropriate filename with extension.
        
        Args:
            base_name: Base filename without extension
            
        Returns:
            Filename with appropriate extension
        """
        return f"{base_name}.{self.file_extension}"
    
    def _safe_str(self, value: Optional[str]) -> str:
        """
        Safely convert value to string, handling None.
        
        Args:
            value: String or None
            
        Returns:
            String value or empty string
        """
        return value if value else ""
    
    def _format_authors_list(self, metadata: CitationMetadata) -> List[str]:
        """
        Get authors as a list of formatted strings.
        
        Prefers authors_parsed for structured data, falls back to authors list.
        
        Args:
            metadata: Citation metadata
            
        Returns:
            List of author name strings
        """
        if metadata.authors_parsed:
            result = []
            for author in metadata.authors_parsed:
                if author.get('is_org'):
                    result.append(author.get('family', ''))
                else:
                    given = author.get('given', '')
                    family = author.get('family', '')
                    if given and family:
                        result.append(f"{family}, {given}")
                    elif family:
                        result.append(family)
            return result
        
        return metadata.authors if metadata.authors else []


# =============================================================================
# EXPORTER FACTORY
# =============================================================================

def get_exporter(format_name: str) -> BaseExporter:
    """
    Get an exporter instance for the specified format.
    
    Args:
        format_name: Format name (e.g., "ris", "csv", "bibtex")
        
    Returns:
        Appropriate exporter instance
    
    Supported formats:
        - RIS: EndNote, Zotero, Mendeley, RefWorks
        - CSV: Excel, Google Sheets, databases
        - BibTeX: LaTeX, Zotero, JabRef
    """
    # Import here to avoid circular imports
    from exporters.ris import RISExporter
    from exporters.csv_export import CSVExporter
    from exporters.bibtex import BibTeXExporter
    
    format_lower = format_name.lower().strip()
    
    if format_lower == 'ris':
        return RISExporter()
    elif format_lower in ('csv', 'excel'):
        return CSVExporter()
    elif format_lower in ('bibtex', 'bib', 'latex'):
        return BibTeXExporter()
    else:
        # Default to RIS (most universal)
        return RISExporter()


def get_available_formats() -> List[dict]:
    """
    Get list of available export formats with metadata.
    
    Returns:
        List of format info dicts for UI display
    """
    return [
        {
            'id': 'ris',
            'name': 'RIS',
            'description': 'Universal format for EndNote, Zotero, Mendeley',
            'extension': 'ris',
        },
        {
            'id': 'csv',
            'name': 'CSV',
            'description': 'Spreadsheet format for Excel, Google Sheets',
            'extension': 'csv',
        },
        {
            'id': 'bibtex',
            'name': 'BibTeX',
            'description': 'LaTeX format for academic papers',
            'extension': 'bib',
        },
    ]
