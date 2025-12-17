"""
citeflex/exporters/ris.py

RIS format exporter for citation data.

RIS (Research Information Systems) is the universal interchange format
supported by virtually all reference managers:
- EndNote
- Zotero
- Mendeley
- RefWorks
- Papers
- Citavi

RIS format specification:
- Each record starts with TY (type) and ends with ER
- Fields are two uppercase letters followed by "  - " and the value
- Authors (AU) are one per line in "Last, First" format
- Multiple values for the same field use separate lines
"""

from typing import List
from exporters.base import BaseExporter, ExportFormat
from models import CitationMetadata, CitationType


class RISExporter(BaseExporter):
    """
    Export citations to RIS format.
    
    RIS is the recommended format for maximum compatibility with
    reference management software.
    """
    
    format = ExportFormat.RIS
    
    @property
    def file_extension(self) -> str:
        return "ris"
    
    @property
    def mime_type(self) -> str:
        return "application/x-research-info-systems"
    
    # Mapping from CitationType to RIS type codes
    TYPE_MAP = {
        CitationType.JOURNAL: "JOUR",
        CitationType.BOOK: "BOOK",
        CitationType.LEGAL: "CASE",
        CitationType.NEWSPAPER: "NEWS",
        CitationType.GOVERNMENT: "GOVDOC",
        CitationType.MEDICAL: "JOUR",  # Medical articles are journals
        CitationType.INTERVIEW: "PCOMM",  # Personal communication
        CitationType.LETTER: "PCOMM",
        CitationType.URL: "ELEC",  # Electronic source
        CitationType.UNKNOWN: "GEN",  # Generic
    }
    
    def export(self, citations: List[CitationMetadata]) -> str:
        """
        Export citations to RIS format string.
        
        Args:
            citations: List of CitationMetadata objects
            
        Returns:
            RIS formatted string (UTF-8)
        """
        records = []
        
        for citation in citations:
            record = self._format_record(citation)
            records.append(record)
        
        # RIS records are separated by blank lines
        return "\n\n".join(records)
    
    def _format_record(self, metadata: CitationMetadata) -> str:
        """
        Format a single citation as an RIS record.
        
        Args:
            metadata: Citation metadata
            
        Returns:
            RIS record string
        """
        lines = []
        
        # TY - Type (required, must be first)
        ris_type = self.TYPE_MAP.get(metadata.citation_type, "GEN")
        lines.append(f"TY  - {ris_type}")
        
        # Title fields
        if metadata.title:
            lines.append(f"TI  - {metadata.title}")
        
        # For legal cases, also include case_name if different
        if metadata.citation_type == CitationType.LEGAL and metadata.case_name:
            if metadata.case_name != metadata.title:
                lines.append(f"T1  - {metadata.case_name}")
        
        # Authors - one AU line per author
        authors = self._format_authors_list(metadata)
        for author in authors:
            lines.append(f"AU  - {author}")
        
        # Year
        if metadata.year:
            lines.append(f"PY  - {metadata.year}")
        
        # Date (full date if available)
        if metadata.date:
            lines.append(f"DA  - {metadata.date}")
        
        # Journal/publication fields
        if metadata.journal:
            lines.append(f"JO  - {metadata.journal}")
            lines.append(f"T2  - {metadata.journal}")  # Secondary title
        
        if metadata.newspaper:
            lines.append(f"T2  - {metadata.newspaper}")
        
        # Volume, issue, pages
        if metadata.volume:
            lines.append(f"VL  - {metadata.volume}")
        
        if metadata.issue:
            lines.append(f"IS  - {metadata.issue}")
        
        if metadata.pages:
            # Try to split into start/end pages
            pages = metadata.pages.replace("–", "-").replace("—", "-")
            if "-" in pages:
                parts = pages.split("-", 1)
                lines.append(f"SP  - {parts[0].strip()}")
                if len(parts) > 1 and parts[1].strip():
                    lines.append(f"EP  - {parts[1].strip()}")
            else:
                lines.append(f"SP  - {pages}")
        
        # Publisher and place
        if metadata.publisher:
            lines.append(f"PB  - {metadata.publisher}")
        
        if metadata.place:
            lines.append(f"CY  - {metadata.place}")
        
        # Edition
        if metadata.edition:
            lines.append(f"ET  - {metadata.edition}")
        
        # Identifiers
        if metadata.doi:
            lines.append(f"DO  - {metadata.doi}")
        
        if metadata.isbn:
            lines.append(f"SN  - {metadata.isbn}")
        
        if metadata.pmid:
            lines.append(f"AN  - PMID:{metadata.pmid}")
        
        # URL
        if metadata.url:
            lines.append(f"UR  - {metadata.url}")
        
        # Legal-specific fields
        if metadata.citation_type == CitationType.LEGAL:
            if metadata.citation:
                lines.append(f"SE  - {metadata.citation}")  # Section/citation
            if metadata.court:
                lines.append(f"A2  - {metadata.court}")  # Secondary author for court
            if metadata.jurisdiction:
                lines.append(f"CY  - {metadata.jurisdiction}")
        
        # Interview/letter specific
        if metadata.citation_type == CitationType.INTERVIEW:
            if metadata.interviewee:
                lines.append(f"A2  - {metadata.interviewee}")
            if metadata.interviewer:
                lines.append(f"A3  - {metadata.interviewer}")
        
        if metadata.citation_type == CitationType.LETTER:
            if metadata.sender:
                lines.append(f"AU  - {metadata.sender}")
            if metadata.recipient:
                lines.append(f"A2  - {metadata.recipient}")
        
        # Government document fields
        if metadata.agency:
            lines.append(f"A2  - {metadata.agency}")
        
        if metadata.document_number:
            lines.append(f"M1  - {metadata.document_number}")
        
        # Access date
        if metadata.access_date:
            lines.append(f"Y2  - {metadata.access_date}")
        
        # Source engine (as note for debugging/reference)
        if metadata.source_engine:
            lines.append(f"N1  - Source: {metadata.source_engine}")
        
        # Original source (as note)
        if metadata.raw_source and metadata.raw_source != metadata.url:
            lines.append(f"N1  - Original: {metadata.raw_source}")
        
        # ER - End of record (required, must be last)
        lines.append("ER  - ")
        
        return "\n".join(lines)
