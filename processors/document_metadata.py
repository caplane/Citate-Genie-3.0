"""
processors/document_metadata.py

Embedded Citation Metadata Cache

This module manages the "invisible library" that travels with Word documents.
Citation metadata is stored as a Custom XML Part inside the .docx file,
allowing subsequent processing runs to skip API calls for known citations.

How it works:
1. When a document is opened, we check for customXml/citategenie.xml
2. If found, we load the cached metadata keyed by citation text hash
3. During processing, we check cache before making API calls
4. When document is saved, we embed updated cache back into the docx

Technical Details:
- .docx files are ZIP archives containing XML
- Word preserves Custom XML Parts through edits
- We use SHA-256 hash of exact citation text as cache key (exact matching)
- Metadata is serialized to/from XML format

Created: 2025-12-14
"""

import os
import re
import hashlib
import zipfile
import tempfile
import shutil
import json
import xml.etree.ElementTree as ET
from typing import Dict, Optional, Any, List
from io import BytesIO
from datetime import datetime

from models import CitationMetadata, CitationType


# =============================================================================
# CONSTANTS
# =============================================================================

# Custom XML namespace for CitateGenie metadata
CITATEGENIE_NS = "http://citategenie.com/metadata/v1"
CITATEGENIE_ITEM_ID = "citategenie-metadata-cache"

# Path within docx where custom XML is stored
CUSTOM_XML_DIR = "customXml"
CUSTOM_XML_ITEM_FILENAME = "citategenie.xml"
CUSTOM_XML_ITEM_PROPS_FILENAME = "citategenieProps.xml"


# =============================================================================
# HASHING
# =============================================================================

def hash_citation_text(text: str) -> str:
    """
    Generate a hash key for citation text.
    
    Uses SHA-256 of the exact text (after stripping whitespace).
    This implements exact matching - "Smith 2020" != "Smith, 2020"
    
    Args:
        text: The citation text to hash
        
    Returns:
        Hex string hash (first 16 chars for brevity)
    """
    if not text:
        return ""
    
    # Strip leading/trailing whitespace only - preserve internal formatting
    cleaned = text.strip()
    
    # SHA-256 hash, truncated for readability
    hash_obj = hashlib.sha256(cleaned.encode('utf-8'))
    return hash_obj.hexdigest()[:16]


# =============================================================================
# METADATA CACHE CLASS
# =============================================================================

class CitationMetadataCache:
    """
    In-memory cache for citation metadata.
    
    Manages the mapping between citation text hashes and resolved metadata.
    Can be serialized to/from XML for embedding in documents.
    """
    
    def __init__(self):
        """Initialize an empty cache."""
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._version = "1.0"
        self._created = datetime.utcnow().isoformat()
    
    def get(self, citation_text: str) -> Optional[CitationMetadata]:
        """
        Look up cached metadata for a citation.
        
        Args:
            citation_text: The original citation text
            
        Returns:
            CitationMetadata if found in cache, None otherwise
        """
        hash_key = hash_citation_text(citation_text)
        if not hash_key:
            return None
        
        if hash_key in self._cache:
            print(f"[MetadataCache] Cache HIT for hash {hash_key}: {citation_text[:40]}...")
            data = self._cache[hash_key]
            return CitationMetadata.from_dict(data.get('metadata', {}))
        
        print(f"[MetadataCache] Cache MISS for hash {hash_key}: {citation_text[:40]}...")
        return None
    
    def set(self, citation_text: str, metadata: CitationMetadata) -> None:
        """
        Store metadata in the cache.
        
        Args:
            citation_text: The original citation text
            metadata: The resolved CitationMetadata
        """
        hash_key = hash_citation_text(citation_text)
        if not hash_key or not metadata:
            return
        
        self._cache[hash_key] = {
            'original_text': citation_text.strip(),
            'hash': hash_key,
            'metadata': metadata.to_dict(),
            'cached_at': datetime.utcnow().isoformat(),
        }
        print(f"[MetadataCache] Stored metadata for hash {hash_key}")
    
    def has(self, citation_text: str) -> bool:
        """Check if citation is in cache without retrieving it."""
        hash_key = hash_citation_text(citation_text)
        return hash_key in self._cache
    
    def size(self) -> int:
        """Return number of cached citations."""
        return len(self._cache)
    
    def get_all_metadata(self) -> List[Dict[str, Any]]:
        """
        Get all cached metadata as a list of dicts.
        Useful for CSV export.
        
        Returns:
            List of metadata dictionaries with original text included
        """
        results = []
        for hash_key, entry in self._cache.items():
            item = entry.get('metadata', {}).copy()
            item['original_text'] = entry.get('original_text', '')
            item['hash'] = hash_key
            item['cached_at'] = entry.get('cached_at', '')
            results.append(item)
        return results
    
    def to_xml_string(self) -> str:
        """
        Serialize the cache to XML string.
        
        Returns:
            XML string representation of the cache
        """
        root = ET.Element('citategenie', {
            'version': self._version,
            'created': self._created,
            'xmlns': CITATEGENIE_NS,
        })
        
        for hash_key, entry in self._cache.items():
            citation_el = ET.SubElement(root, 'citation', {'hash': hash_key})
            
            # Original text
            original_el = ET.SubElement(citation_el, 'original')
            original_el.text = entry.get('original_text', '')
            
            # Cached timestamp
            cached_el = ET.SubElement(citation_el, 'cached_at')
            cached_el.text = entry.get('cached_at', '')
            
            # Metadata fields
            metadata = entry.get('metadata', {})
            meta_el = ET.SubElement(citation_el, 'metadata')
            
            for key, value in metadata.items():
                if value is None:
                    continue
                
                field_el = ET.SubElement(meta_el, key)
                
                if isinstance(value, list):
                    # Handle lists (e.g., authors)
                    field_el.text = json.dumps(value)
                elif isinstance(value, dict):
                    # Handle dicts (e.g., raw_data)
                    field_el.text = json.dumps(value)
                else:
                    field_el.text = str(value)
        
        return ET.tostring(root, encoding='unicode', xml_declaration=True)
    
    @classmethod
    def from_xml_string(cls, xml_string: str) -> 'CitationMetadataCache':
        """
        Deserialize cache from XML string.
        
        Args:
            xml_string: XML representation of the cache
            
        Returns:
            CitationMetadataCache instance
        """
        cache = cls()
        
        try:
            root = ET.fromstring(xml_string)
            
            cache._version = root.get('version', '1.0')
            cache._created = root.get('created', datetime.utcnow().isoformat())
            
            for citation_el in root.findall('.//citation'):
                hash_key = citation_el.get('hash')
                if not hash_key:
                    continue
                
                # Get original text
                original_el = citation_el.find('original')
                original_text = original_el.text if original_el is not None and original_el.text else ''
                
                # Get cached timestamp
                cached_el = citation_el.find('cached_at')
                cached_at = cached_el.text if cached_el is not None and cached_el.text else ''
                
                # Get metadata
                metadata = {}
                meta_el = citation_el.find('metadata')
                if meta_el is not None:
                    for field_el in meta_el:
                        key = field_el.tag
                        value = field_el.text
                        
                        if value is None:
                            metadata[key] = None
                        elif value.startswith('[') or value.startswith('{'):
                            # Parse JSON for lists/dicts
                            try:
                                metadata[key] = json.loads(value)
                            except json.JSONDecodeError:
                                metadata[key] = value
                        elif key == 'confidence':
                            try:
                                metadata[key] = float(value)
                            except ValueError:
                                metadata[key] = 1.0
                        else:
                            metadata[key] = value
                
                cache._cache[hash_key] = {
                    'original_text': original_text,
                    'hash': hash_key,
                    'metadata': metadata,
                    'cached_at': cached_at,
                }
            
            print(f"[MetadataCache] Loaded {cache.size()} cached citations from XML")
            
        except ET.ParseError as e:
            print(f"[MetadataCache] Failed to parse XML: {e}")
        
        return cache


# =============================================================================
# DOCUMENT OPERATIONS
# =============================================================================

def load_cache_from_docx(file_bytes: bytes) -> CitationMetadataCache:
    """
    Load the citation metadata cache from a Word document.
    
    Looks for customXml/citategenie.xml within the docx archive.
    Returns empty cache if not found.
    
    Args:
        file_bytes: The document as bytes
        
    Returns:
        CitationMetadataCache (may be empty if no cache found)
    """
    try:
        with zipfile.ZipFile(BytesIO(file_bytes), 'r') as zf:
            # List all files in archive
            names = zf.namelist()
            
            # Look for our custom XML part
            # Word may store custom XML in various locations
            possible_paths = [
                f'{CUSTOM_XML_DIR}/{CUSTOM_XML_ITEM_FILENAME}',
                f'{CUSTOM_XML_DIR}/item1.xml',  # Word sometimes uses generic names
                f'{CUSTOM_XML_DIR}/item2.xml',
                f'{CUSTOM_XML_DIR}/item3.xml',
            ]
            
            for path in possible_paths:
                if path in names:
                    content = zf.read(path).decode('utf-8')
                    # Check if this is our XML (has citategenie root or namespace)
                    if '<citategenie' in content or CITATEGENIE_NS in content:
                        print(f"[DocumentMetadata] Found cache at {path}")
                        return CitationMetadataCache.from_xml_string(content)
            
            print("[DocumentMetadata] No existing cache found in document")
            return CitationMetadataCache()
            
    except zipfile.BadZipFile:
        print("[DocumentMetadata] Invalid docx file")
        return CitationMetadataCache()
    except Exception as e:
        print(f"[DocumentMetadata] Error loading cache: {e}")
        return CitationMetadataCache()


def save_cache_to_docx(file_bytes: bytes, cache: CitationMetadataCache) -> bytes:
    """
    Embed the citation metadata cache into a Word document.
    
    Adds or updates customXml/citategenie.xml within the docx archive.
    Also updates Content_Types and relationships as needed.
    
    Args:
        file_bytes: The document as bytes
        cache: The CitationMetadataCache to embed
        
    Returns:
        Updated document bytes with embedded cache
    """
    if cache.size() == 0:
        print("[DocumentMetadata] Empty cache, skipping embed")
        return file_bytes
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Extract docx
        with zipfile.ZipFile(BytesIO(file_bytes), 'r') as zf:
            zf.extractall(temp_dir)
        
        # Create customXml directory if it doesn't exist
        custom_xml_dir = os.path.join(temp_dir, CUSTOM_XML_DIR)
        os.makedirs(custom_xml_dir, exist_ok=True)
        
        # Write our XML cache
        cache_path = os.path.join(custom_xml_dir, CUSTOM_XML_ITEM_FILENAME)
        xml_content = cache.to_xml_string()
        with open(cache_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)
        
        print(f"[DocumentMetadata] Wrote cache with {cache.size()} citations to {CUSTOM_XML_ITEM_FILENAME}")
        
        # Update [Content_Types].xml to include our custom XML part
        content_types_path = os.path.join(temp_dir, '[Content_Types].xml')
        _update_content_types(content_types_path)
        
        # Repackage docx
        output_buffer = BytesIO()
        with zipfile.ZipFile(output_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root_dir, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root_dir, file)
                    arcname = os.path.relpath(file_path, temp_dir)
                    zf.write(file_path, arcname)
        
        output_buffer.seek(0)
        return output_buffer.read()
        
    except Exception as e:
        print(f"[DocumentMetadata] Error saving cache: {e}")
        return file_bytes
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _update_content_types(content_types_path: str) -> None:
    """
    Update [Content_Types].xml to include our custom XML content type.
    
    This ensures Word recognizes our custom XML part.
    """
    if not os.path.exists(content_types_path):
        return
    
    try:
        # Parse existing content types
        tree = ET.parse(content_types_path)
        root = tree.getroot()
        
        # Namespace for content types
        ns = {'ct': 'http://schemas.openxmlformats.org/package/2006/content-types'}
        ET.register_namespace('', ns['ct'])
        
        # Check if our override already exists
        our_path = f'/{CUSTOM_XML_DIR}/{CUSTOM_XML_ITEM_FILENAME}'
        existing = root.find(f".//ct:Override[@PartName='{our_path}']", ns)
        
        if existing is None:
            # Add override for our custom XML
            override = ET.SubElement(root, f"{{{ns['ct']}}}Override")
            override.set('PartName', our_path)
            override.set('ContentType', 'application/xml')
            
            tree.write(content_types_path, encoding='UTF-8', xml_declaration=True)
            print(f"[DocumentMetadata] Added content type for {our_path}")
            
    except Exception as e:
        print(f"[DocumentMetadata] Error updating content types: {e}")


# =============================================================================
# CSV EXPORT
# =============================================================================

def export_cache_to_csv(cache: CitationMetadataCache) -> str:
    """
    Export cache to CSV format.
    
    Args:
        cache: The CitationMetadataCache to export
        
    Returns:
        CSV string
    """
    import csv
    from io import StringIO
    
    output = StringIO()
    
    # Define columns for export
    columns = [
        'original_text',
        'title',
        'authors',
        'year',
        'doi',
        'url',
        'type',
        'journal',
        'publisher',
        'volume',
        'issue',
        'pages',
        'case_name',
        'citation',
        'court',
        'cached_at',
    ]
    
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction='ignore')
    writer.writeheader()
    
    for item in cache.get_all_metadata():
        # Flatten authors list to string, filtering out None values
        if 'authors' in item and isinstance(item['authors'], list):
            item['authors'] = '; '.join(str(a) for a in item['authors'] if a is not None)
        
        writer.writerow(item)
    
    return output.getvalue()
