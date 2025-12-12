"""
citeflex/processors/author_date.py

Processing utilities for author-date citation style documents.
Handles generation of References sections for APA, Harvard, etc.

Created: 2025-12-10
"""

import zipfile
import tempfile
import shutil
import os
import re
from io import BytesIO
from typing import List


def append_references_section(doc_bytes: bytes, references: List[str]) -> bytes:
    """
    Append a References section to the end of a Word document.
    
    Args:
        doc_bytes: Original .docx file as bytes
        references: List of formatted reference strings (already formatted in target style)
        
    Returns:
        Modified document bytes with References section appended
    """
    if not references:
        return doc_bytes
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Extract docx
        with zipfile.ZipFile(BytesIO(doc_bytes), 'r') as zf:
            zf.extractall(temp_dir)
        
        # Read document.xml
        doc_path = os.path.join(temp_dir, 'word', 'document.xml')
        if not os.path.exists(doc_path):
            return doc_bytes
        
        with open(doc_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Build References section XML
        references_xml = _build_references_xml(references)
        
        # Find the closing </w:body> tag and insert before it
        body_close_pattern = r'(</w:body>)'
        
        if re.search(body_close_pattern, content):
            new_content = re.sub(
                body_close_pattern,
                references_xml + r'\1',
                content,
                count=1
            )
        else:
            # Fallback: couldn't find body close, return original
            return doc_bytes
        
        # Write modified document.xml
        with open(doc_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        # Repackage docx
        output_buffer = BytesIO()
        with zipfile.ZipFile(output_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, temp_dir)
                    zf.write(file_path, arcname)
        
        output_buffer.seek(0)
        return output_buffer.read()
        
    except Exception as e:
        print(f"[append_references_section] Error: {e}")
        return doc_bytes
        
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


def _build_references_xml(references: List[str]) -> str:
    """
    Build Word XML for References section.
    
    Creates:
    - A "References" heading paragraph
    - Each reference as a hanging-indent paragraph
    """
    import html
    
    paragraphs = []
    
    # References heading (Heading 1 style)
    paragraphs.append('''
<w:p>
  <w:pPr>
    <w:pStyle w:val="Heading1"/>
    <w:spacing w:before="480" w:after="240"/>
  </w:pPr>
  <w:r>
    <w:t>References</w:t>
  </w:r>
</w:p>''')
    
    # Each reference with hanging indent
    for ref in references:
        if not ref:
            continue
        
        # Escape HTML entities and handle italic tags
        escaped = _format_reference_xml(ref)
        
        paragraphs.append(f'''
<w:p>
  <w:pPr>
    <w:spacing w:after="120" w:line="480" w:lineRule="auto"/>
    <w:ind w:left="720" w:hanging="720"/>
  </w:pPr>
  {escaped}
</w:p>''')
    
    return ''.join(paragraphs)


def _format_reference_xml(text: str) -> str:
    """
    Convert formatted reference text to Word XML runs.
    
    Handles <i>italic</i> tags and escapes XML entities.
    """
    import html as html_module
    import re
    
    # Unescape any HTML entities first
    text = html_module.unescape(text)
    
    # Split by italic tags
    parts = re.split(r'(<i>.*?</i>)', text)
    runs = []
    
    for part in parts:
        if not part:
            continue
        
        if part.startswith('<i>') and part.endswith('</i>'):
            # Italic text
            inner = part[3:-4]
            inner_escaped = inner.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            runs.append(f'<w:r><w:rPr><w:i/></w:rPr><w:t xml:space="preserve">{inner_escaped}</w:t></w:r>')
        else:
            # Normal text
            escaped = part.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            runs.append(f'<w:r><w:t xml:space="preserve">{escaped}</w:t></w:r>')
    
    return ''.join(runs)


def deduplicate_references(references: List[str]) -> List[str]:
    """
    Remove duplicate references and sort alphabetically.
    
    Args:
        references: List of formatted references
        
    Returns:
        Sorted, deduplicated list
    """
    # Use set for deduplication, preserving first occurrence order
    seen = set()
    unique = []
    
    for ref in references:
        # Normalize for comparison (lowercase, strip whitespace)
        normalized = ref.lower().strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(ref)
    
    # Sort alphabetically (by author surname typically)
    return sorted(unique, key=lambda x: x.lower())


def process_author_date_document(doc_bytes: bytes, references: List[str]) -> bytes:
    """
    Process an author-date style document by appending a References section.
    
    This is a convenience function that combines deduplication and appending.
    
    Args:
        doc_bytes: Original .docx file as bytes
        references: List of formatted reference strings
        
    Returns:
        Modified document bytes with References section appended
    """
    # Deduplicate and sort
    unique_refs = deduplicate_references(references)
    
    # Append to document
    return append_references_section(doc_bytes, unique_refs)
