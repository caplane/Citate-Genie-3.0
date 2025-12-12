"""
utils/ - Shared helper functions used across the system.

Modules:
    type_detection.py       - Detect citation types (is_legal, is_medical, is_newspaper, etc.)
    metadata_extraction.py  - Extract metadata from API responses (Crossref, OpenAlex, etc.)
"""

from utils.type_detection import detect_type, is_url, is_legal, is_medical, DetectionResult

__all__ = [
    'detect_type',
    'is_url',
    'is_legal',
    'is_medical',
    'DetectionResult',
]
