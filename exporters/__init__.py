"""
citeflex/exporters/__init__.py

Citation export module for CitateGenie.

Provides export functionality to standard bibliography formats:
- RIS (Research Information Systems) - Universal format
- CSV - Spreadsheet compatible
- BibTeX - LaTeX compatible

Usage:
    from exporters import get_exporter, get_available_formats
    
    # Get exporter for format
    exporter = get_exporter('ris')
    
    # Export citations
    content = exporter.export(citations)
    
    # Get filename
    filename = exporter.get_filename('my_citations')  # 'my_citations.ris'
    
    # List available formats
    formats = get_available_formats()
"""

from exporters.base import (
    BaseExporter,
    ExportFormat,
    get_exporter,
    get_available_formats,
)
from exporters.ris import RISExporter
from exporters.csv_export import CSVExporter, TabDelimitedExporter
from exporters.bibtex import BibTeXExporter

__all__ = [
    # Base classes
    'BaseExporter',
    'ExportFormat',
    
    # Factory functions
    'get_exporter',
    'get_available_formats',
    
    # Concrete exporters
    'RISExporter',
    'CSVExporter',
    'TabDelimitedExporter',
    'BibTeXExporter',
]
