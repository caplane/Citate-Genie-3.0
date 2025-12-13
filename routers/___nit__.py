"""
citeflex/routers/__init__.py

Router modules for specialized citation handling.

ARCHITECTURE NOTE (2025-12-12):
AI classification and lookup have been consolidated into engines/ai_lookup.py.
The following router files are DEPRECATED and should be deleted:
- routers/claude.py (functionality moved to engines/ai_lookup.py)
- routers/gemini.py (functionality moved to engines/ai_lookup.py)
- routers/chat_gpt_router.py (was duplicate of engines/ai_lookup.py)

Only URL routing remains in this package.
"""

# URL routing is the only remaining router
# from routers.url import route_url, classify_url, URLRouter

# For AI classification, import from the consolidated module:
# from engines.ai_lookup import classify_citation, lookup_fragment
