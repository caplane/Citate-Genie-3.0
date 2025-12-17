"""
citeflex/exporters/csv_export.py

CSV format exporter for citation data.

Note: Named csv_export.py to avoid conflict with Python's csv module.

CSV export provides a flat file format suitable for:
- Excel
- Google Sheets
- Database imports
- Data analysis
- Custom processing pipelines

The CSV includes all available metadata fields, making it useful
for bulk editing or migration to other systems.
"""

import csv
import io
from typing import List
from exporters.base import BaseExporter, ExportFormat
from models import CitationMetadata, CitationType


class CSVExporter(BaseExporter):
    """
    Export citations to CSV format.
    
    Produces a comprehensive CSV with all metadata fields.
    Uses proper CSV escaping for fields containing commas, quotes, etc.
    """
    
    format = ExportFormat.CSV
    
    @property
    def file_extension(self) -> str:
        return "csv"
    
    @property
    def mime_type(self) -> str:
        return "text/csv"
    
    # Column definitions: (header, metadata_field_or_callable)
    COLUMNS = [
        ("Type", "citation_type"),
        ("Title", "title"),
        ("Authors", "authors"),
        ("Year", "year"),
        ("Date", "date"),
        ("Journal", "journal"),
        ("Volume", "volume"),
        ("Issue", "issue"),
        ("Pages", "pages"),
        ("DOI", "doi"),
        ("URL", "url"),
        ("Publisher", "publisher"),
        ("Place", "place"),
        ("Edition", "edition"),
        ("ISBN", "isbn"),
        ("PMID", "pmid"),
        ("Newspaper", "newspaper"),
        ("Case Name", "case_name"),
        ("Legal Citation", "citation"),
        ("Court", "court"),
        ("Jurisdiction", "jurisdiction"),
        ("Agency", "agency"),
        ("Document Number", "document_number"),
        ("Interviewee", "interviewee"),
        ("Interviewer", "interviewer"),
        ("Sender", "sender"),
        ("Recipient", "recipient"),
        ("Location", "location"),
        ("Access Date", "access_date"),
        ("Source Engine", "source_engine"),
        ("Original Input", "raw_source"),
        ("Confidence", "confidence"),
    ]
    
    def export(self, citations: List[CitationMetadata]) -> str:
        """
        Export citations to CSV format string.
        
        Args:
            citations: List of CitationMetadata objects
            
        Returns:
            CSV formatted string (UTF-8 with BOM for Excel compatibility)
        """
        output = io.StringIO()
        
        # Use UTF-8 BOM for better Excel compatibility
        output.write('\ufeff')
        
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
        
        # Write header row
        headers = [col[0] for col in self.COLUMNS]
        writer.writerow(headers)
        
        # Write data rows
        for citation in citations:
            row = self._format_row(citation)
            writer.writerow(row)
        
        return output.getvalue()
    
    def _format_row(self, metadata: CitationMetadata) -> List[str]:
        """
        Format a single citation as a CSV row.
        
        Args:
            metadata: Citation metadata
            
        Returns:
            List of string values for each column
        """
        row = []
        
        for header, field in self.COLUMNS:
            value = self._get_field_value(metadata, field)
            row.append(value)
        
        return row
    
    def _get_field_value(self, metadata: CitationMetadata, field: str) -> str:
        """
        Get the value for a specific field from metadata.
        
        Args:
            metadata: Citation metadata
            field: Field name or special handler
            
        Returns:
            String value for the field
        """
        # Special handling for certain fields
        if field == "citation_type":
            return metadata.citation_type.name.lower()
        
        if field == "authors":
            return self._format_authors_for_csv(metadata)
        
        if field == "confidence":
            return f"{metadata.confidence:.2f}"
        
        # Standard field access
        value = getattr(metadata, field, "")
        
        if value is None:
            return ""
        
        if isinstance(value, list):
            return "; ".join(str(v) for v in value)
        
        return str(value)
    
    def _format_authors_for_csv(self, metadata: CitationMetadata) -> str:
        """
        Format authors list for CSV cell.
        
        Uses semicolon separator (standard for multi-value cells).
        
        Args:
            metadata: Citation metadata
            
        Returns:
            Semicolon-separated author string
        """
        authors = self._format_authors_list(metadata)
        return "; ".join(authors)


class TabDelimitedExporter(CSVExporter):
    """
    Export citations to tab-delimited format.
    
    Tab-delimited is sometimes preferred for EndNote import
    and avoids issues with commas in field values.
    """
    
    @property
    def file_extension(self) -> str:
        return "txt"
    
    @property
    def mime_type(self) -> str:
        return "text/tab-separated-values"
    
    def export(self, citations: List[CitationMetadata]) -> str:
        """
        Export citations to tab-delimited format string.
        
        Args:
            citations: List of CitationMetadata objects
            
        Returns:
            Tab-delimited string
        """
        output = io.StringIO()
        
        # UTF-8 BOM for Excel
        output.write('\ufeff')
        
        writer = csv.writer(output, delimiter='\t', quoting=csv.QUOTE_MINIMAL)
        
        # Write header row
        headers = [col[0] for col in self.COLUMNS]
        writer.writerow(headers)
        
        # Write data rows
        for citation in citations:
            row = self._format_row(citation)
            writer.writerow(row)
        
        return output.getvalue()
