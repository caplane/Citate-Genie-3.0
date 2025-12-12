# CitateGenie 3.0

**Transform messy citations into properly formatted references.**

CitateGenie processes Word documents containing URLs, DOIs, and rough citations, looks up metadata from authoritative sources (Crossref, PubMed, Google Books, CourtListener), and reformats them in your chosen style.

## What's New in 3.0

**Style-Driven Processing**: Select your citation style, and CitateGenie automatically determines the output format:
- Chicago Notes-Bibliography, Bluebook, OSCOLA → Footnotes/Endnotes
- APA 7, MLA 9, Chicago Author-Date → Parenthetical citations + References section

No more choosing between "modes" — just pick your style.

## Features

- **Unified Processing Pipeline**: One upload, style determines everything
- **Smart Extraction**: Finds URLs, DOIs, PMIDs, arXiv IDs, and (Author, Year) patterns
- **Multiple Styles**: Chicago, APA, MLA, Bluebook, OSCOLA
- **Smart Detection**: Automatically identifies citation types (legal, book, journal, newspaper)
- **Document Context**: Extracts topics from your document to improve AI accuracy
- **Tiered AI Fallback**: Free APIs → GPT-4o → Claude for difficult citations

## Real-World Workflow

CitateGenie is built for how academics actually work:
1. While writing, you paste URLs like `https://doi.org/10.1086/226147` as placeholders
2. Upload your draft to CitateGenie, select your style
3. Download with proper citations and a generated bibliography

## Project Structure

```
citeflex/
├── app.py                 # Flask application entry point
├── config.py              # API keys, timeouts, domain mappings
├── models.py              # CitationMetadata dataclass, CitationType enum
│
├── engines/               # Search engines for metadata retrieval
│   ├── academic.py        # Crossref, OpenAlex, Semantic Scholar, PubMed
│   ├── books.py           # Google Books, Open Library
│   ├── superlegal.py      # CourtListener, Famous Cases cache
│   ├── ai_lookup.py       # AI-powered search (GPT-4o, Claude, Gemini)
│   └── ...
│
├── processors/            # Document processing pipelines
│   ├── orchestrator.py    # Thin wiring layer - coordinates everything
│   ├── url_extractor.py   # Extract URLs from document body
│   ├── doi_extractor.py   # Extract DOIs, PMIDs, arXiv IDs, ISBNs
│   ├── parenthetical_extractor.py  # Extract (Author, Year) patterns
│   ├── citation_classifier.py      # Route to correct engines
│   ├── topic_extractor.py # Extract document context for AI
│   ├── footnote_builder.py         # Build footnote output
│   ├── author_date_builder.py      # Build parenthetical + References
│   └── word_document.py   # XML manipulation for Word docs
│
├── formatters/            # Output formatters for citation styles
│   ├── base.py            # BaseFormatter, get_formatter()
│   ├── chicago.py         # Chicago 17th ed. Notes-Bibliography
│   ├── chicago_author_date.py  # Chicago Author-Date
│   ├── apa.py             # APA 7th ed.
│   ├── mla.py             # MLA 9th ed.
│   └── legal.py           # Bluebook, OSCOLA
│
├── templates/
│   └── index.html         # Frontend UI
│
└── tests/
    └── stress_test.py     # Comprehensive test suite
```

## Installation

```bash
pip install -r requirements.txt
```

## Environment Variables

```bash
# Required for full functionality
ANTHROPIC_API_KEY=       # Claude API
OPENAI_API_KEY=          # GPT-4o API (cheaper fallback)
GEMINI_API_KEY=          # Gemini API

# Optional (for enhanced search)
CL_API_KEY=              # CourtListener for legal citations
SERPAPI_KEY=             # Google Scholar
PUBMED_API_KEY=          # Medical citations
```

## Running

```bash
# Development
python app.py

# Production (Railway)
gunicorn app:app --workers 2 --threads 4 --timeout 120
```

## Usage

1. Upload a Word document containing URLs, DOIs, or rough citations
2. Select citation style (this determines output format automatically)
3. Process and download the formatted document

## API Endpoints

**Unified (Recommended)**
- `POST /api/process-unified` - Process document (style determines format)
- `GET /api/style-info/<style>` - Get style metadata

**Legacy**
- `POST /api/cite` - Single citation lookup
- `POST /api/process` - Process footnotes/endnotes
- `POST /api/process-author-date` - Process author-date citations
- `GET /api/download/<session_id>` - Download processed document

## Style Output Mapping

| Style | Output Format | Bibliography |
|-------|---------------|--------------|
| Chicago Manual of Style | Footnotes | Bibliography |
| Bluebook | Footnotes | - |
| OSCOLA | Footnotes | - |
| APA 7 | (Author, Year) | References |
| MLA 9 | (Author Page) | Works Cited |
| Chicago Author-Date | (Author Year) | References |

## License

MIT
