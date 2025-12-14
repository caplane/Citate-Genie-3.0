
"""
citeflex/app.py

Flask application for CiteFlex Unified.

Version History:
    2025-12-12: Added document topic extraction for AI context.
                Extracts keywords from document body to help AI disambiguate
                between authors with same name in different fields.
                Import: topic_extractor.get_document_context()
    2025-12-11: Fixed Author-Date UX to match Endnote UX:
                - Added 'recommendation' field (AI's best guess)
                - Original text now appears as first option (id=0)
                - Options 1-4 are AI lookup results
                - Each option has 'is_original' flag
    2025-12-10: Added /api/cite/parenthetical endpoint for Author-Date mode.
                Returns multiple options for user selection.
    2025-12-06 13:30: Added debug logging to diagnose session loss issue
    2025-12-06 13:00: CRITICAL FIX - Fixed /api/update and /api/download to properly
                      access session data. Override feature now works correctly.
    2025-12-06 12:45: Added file-based session persistence to survive deployments
                      Sessions saved to /data/sessions (Railway Volume mount point)
    2025-12-05 12:53: Thread-safe session management with threading.Lock()
    2025-12-05 13:35: Updated to use unified_router, added /api/update endpoint
                      Enhanced /api/cite to return type and source info
                      Enhanced /api/process to return notes list for workbench UI

FIXES APPLIED:
1. Thread-safe session management with threading.Lock()
2. Session expiration (4 hours) to prevent memory leaks
3. Periodic cleanup of expired sessions
4. File-based persistence for sessions (survives deployments with Railway Volume)
5. CRITICAL: /api/update now properly updates document (was silently failing)
6. CRITICAL: /api/download now returns updated document (was returning original)
7. DEBUG: Added logging to track session creation and lookup
8. Author-Date UX now matches Endnote UX with recommendation + options
"""

import os
import uuid
import time
import threading
import pickle
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, request, jsonify, render_template, send_file
from werkzeug.utils import secure_filename

from unified_router import get_citation, get_multiple_citations, get_parenthetical_options, get_parenthetical_metadata
from formatters.base import get_formatter
from document_processor import process_document
from audit_log import audit, AuditEvent
from encryption import get_encryptor
from processors.topic_extractor import get_document_context
from processors.document_metadata import export_cache_to_csv

# =============================================================================
# APP CONFIGURATION
# =============================================================================

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-prod')

ALLOWED_EXTENSIONS = {'docx'}

# =============================================================================
# FIX: PERSISTENT SESSION MANAGEMENT
# =============================================================================

# Session storage directory - use Railway Volume mount point for persistence
SESSIONS_DIR = Path(os.environ.get('SESSIONS_DIR', '/data/sessions'))

class SessionManager:
    """
    Thread-safe session manager with file-based persistence.
    
    Features:
    1. Thread-safe with threading.Lock()
    2. Sessions expire after 4 hours
    3. Persists to disk - survives server restarts/deployments
    4. Requires Railway Volume mounted at /data for full persistence
    
    Setup for Railway:
    1. Go to your service in Railway
    2. Add a Volume: Settings â†’ Volumes â†’ Add Volume
    3. Mount path: /data
    4. Sessions will now survive deployments
    """
    
    SESSION_EXPIRY_HOURS = 4
    CLEANUP_INTERVAL_MINUTES = 15
    
    def __init__(self, storage_dir: Path = SESSIONS_DIR):
        self._sessions = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.time()
        self._storage_dir = storage_dir
        self._persistence_available = False
        
        # Try to set up persistent storage
        self._init_storage()
        
        # Load existing sessions from disk
        self._load_sessions()
    
    def _init_storage(self):
        """Initialize storage directory if possible."""
        try:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            # Test write access
            test_file = self._storage_dir / '.test'
            test_file.write_text('test')
            test_file.unlink()
            self._persistence_available = True
            print(f"[SessionManager] Persistent storage enabled at {self._storage_dir}")
        except Exception as e:
            self._persistence_available = False
            print(f"[SessionManager] Persistent storage unavailable ({e}). Using in-memory only.")
            print("[SessionManager] To enable persistence, add a Railway Volume mounted at /data")
    
    def _get_session_file(self, session_id: str) -> Path:
        """Get the file path for a session."""
        return self._storage_dir / f"{session_id}.pkl"
    
    def _save_session(self, session_id: str):
        """Save a single session to disk with encryption and file locking."""
        if not self._persistence_available:
            return
        try:
            import fcntl
            session = self._sessions.get(session_id)
            if session:
                session_file = self._get_session_file(session_id)
                temp_file = session_file.with_suffix('.tmp')
                
                # Serialize then encrypt
                raw_bytes = pickle.dumps(session)
                encrypted_bytes = get_encryptor().encrypt(session_id, raw_bytes)
                
                with open(temp_file, 'wb') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    f.write(encrypted_bytes)
                    f.flush()
                    os.fsync(f.fileno())
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                temp_file.rename(session_file)
        except Exception as e:
            print(f"[SessionManager] Failed to save session {session_id[:8]}: {e}")
    
    def _delete_session_file(self, session_id: str):
        """Delete session file from disk."""
        if not self._persistence_available:
            return
        try:
            session_file = self._get_session_file(session_id)
            if session_file.exists():
                session_file.unlink()
        except Exception as e:
            print(f"[SessionManager] Failed to delete session file {session_id[:8]}: {e}")
    
    def _load_sessions(self):
        """Load all sessions from disk on startup (with decryption)."""
        if not self._persistence_available:
            return
        
        loaded = 0
        expired = 0
        failed = 0
        current_time = datetime.now()
        
        try:
            for session_file in self._storage_dir.glob("*.pkl"):
                try:
                    session_id = session_file.stem
                    
                    with open(session_file, 'rb') as f:
                        encrypted_bytes = f.read()
                    
                    # Decrypt then deserialize
                    decrypted_bytes = get_encryptor().decrypt(session_id, encrypted_bytes)
                    
                    if decrypted_bytes is None:
                        print(f"[SessionManager] Could not decrypt {session_file.name}, removing")
                        session_file.unlink()
                        failed += 1
                        continue
                    
                    session = pickle.loads(decrypted_bytes)
                    
                    # Check if expired
                    if current_time > session.get('expires_at', current_time):
                        session_file.unlink()
                        expired += 1
                        continue
                    
                    self._sessions[session_id] = session
                    loaded += 1
                except Exception as e:
                    print(f"[SessionManager] Failed to load {session_file.name}: {e}")
                    try:
                        session_file.unlink()
                    except:
                        pass
                    failed += 1
            
            if loaded > 0 or expired > 0 or failed > 0:
                print(f"[SessionManager] Loaded {loaded} sessions, {expired} expired, {failed} failed")
        except Exception as e:
            print(f"[SessionManager] Failed to load sessions: {e}")
    
    def create(self) -> str:
        """Create a new session with expiration."""
        session_id = str(uuid.uuid4())
        
        with self._lock:
            self._sessions[session_id] = {
                'created_at': datetime.now(),
                'expires_at': datetime.now() + timedelta(hours=self.SESSION_EXPIRY_HOURS),
                'data': {}
            }
            self._save_session(session_id)
            self._maybe_cleanup()
        
        # Audit log
        audit.log_request_event(
            event_type=AuditEvent.SESSION_CREATED,
            session_id=session_id
        )
        
        return session_id
    
    def get(self, session_id: str) -> dict:
        """Get session data (thread-safe). Falls back to disk if not in memory."""
        with self._lock:
            session = self._sessions.get(session_id)
            
            # Fallback: try loading from disk if not in memory
            if not session and self._persistence_available:
                session_file = self._get_session_file(session_id)
                if session_file.exists():
                    try:
                        with open(session_file, 'rb') as f:
                            encrypted_bytes = f.read()
                        decrypted_bytes = get_encryptor().decrypt(session_id, encrypted_bytes)
                        if decrypted_bytes:
                            session = pickle.loads(decrypted_bytes)
                            self._sessions[session_id] = session
                            print(f"[SessionManager] Recovered session {session_id[:8]} from disk")
                    except Exception as e:
                        print(f"[SessionManager] Failed to recover session {session_id[:8]}: {e}")
            
            if not session:
                return None
            
            # Check expiration
            if datetime.now() > session['expires_at']:
                del self._sessions[session_id]
                self._delete_session_file(session_id)
                return None
            
            return session['data']
    
    def set(self, session_id: str, key: str, value) -> bool:
        """Set session data (thread-safe). Falls back to disk if not in memory."""
        with self._lock:
            session = self._sessions.get(session_id)
            
            # Fallback: try loading from disk if not in memory
            if not session and self._persistence_available:
                session_file = self._get_session_file(session_id)
                if session_file.exists():
                    try:
                        with open(session_file, 'rb') as f:
                            encrypted_bytes = f.read()
                        decrypted_bytes = get_encryptor().decrypt(session_id, encrypted_bytes)
                        if decrypted_bytes:
                            session = pickle.loads(decrypted_bytes)
                            self._sessions[session_id] = session
                            print(f"[SessionManager] Recovered session {session_id[:8]} from disk for set()")
                    except Exception as e:
                        print(f"[SessionManager] Failed to recover session {session_id[:8]}: {e}")
            
            if not session:
                return False
            
            if datetime.now() > session['expires_at']:
                del self._sessions[session_id]
                self._delete_session_file(session_id)
                return False
            
            session['data'][key] = value
            self._save_session(session_id)
            return True
    
    def delete(self, session_id: str) -> bool:
        """Delete a session (thread-safe)."""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                self._delete_session_file(session_id)
                
                # Audit log
                audit.log_event(
                    event_type=AuditEvent.SESSION_DELETED,
                    session_id=session_id
                )
                
                return True
            return False
    
    def _maybe_cleanup(self) -> None:
        """
        Clean up expired sessions periodically.
        Called within lock, so no additional locking needed.
        """
        now = time.time()
        if now - self._last_cleanup < self.CLEANUP_INTERVAL_MINUTES * 60:
            return
        
        self._last_cleanup = now
        current_time = datetime.now()
        
        expired = [
            sid for sid, session in self._sessions.items()
            if current_time > session['expires_at']
        ]
        
        for sid in expired:
            del self._sessions[sid]
            self._delete_session_file(sid)
            
            # Audit log expired session
            audit.log_event(
                event_type=AuditEvent.SESSION_EXPIRED,
                session_id=sid
            )
        
        if expired:
            print(f"[SessionManager] Cleaned up {len(expired)} expired sessions")


# Global session manager instance
sessions = SessionManager()


# =============================================================================
# HELPERS
# =============================================================================

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# =============================================================================
# ROUTES
# =============================================================================

@app.route('/')
def index():
    """Render the main page."""
    return render_template('index.html')


@app.route('/api/cite', methods=['POST'])
def cite():
    """
    Single citation lookup API.
    
    Request JSON:
    {
        "query": "citation text or URL",
        "style": "Chicago Manual of Style"  // optional
    }
    
    Response JSON:
    {
        "success": true,
        "citation": "formatted citation",
        "metadata": {...}
    }
    """
    try:
        data = request.get_json()
        
        if not data or not data.get('query'):
            return jsonify({
                'success': False,
                'error': 'Missing query parameter'
            }), 400
        
        query = data['query'].strip()
        style = data.get('style', 'Chicago Manual of Style')
        
        metadata, formatted = get_citation(query, style)
        
        if not formatted:
            return jsonify({
                'success': False,
                'error': 'Could not find citation information',
                'query': query
            }), 404
        
        # Determine type and source for UI badges
        citation_type = 'unknown'
        source = 'unified'
        confidence = 'medium'
        
        if metadata:
            citation_type = metadata.citation_type.name.lower() if metadata.citation_type else 'unknown'
            # Determine source based on type and metadata
            if citation_type == 'legal':
                source = 'cache' if metadata.citation else 'courtlistener'
                confidence = 'high' if metadata.citation else 'medium'
            elif citation_type in ['journal', 'medical']:
                source = 'crossref/openalex'
                confidence = 'high' if metadata.doi else 'medium'
            elif citation_type == 'book':
                source = 'openlibrary/googlebooks'
                confidence = 'high' if metadata.isbn else 'medium'
            else:
                source = 'unified'
        
        return jsonify({
            'success': True,
            'citation': formatted,
            'type': citation_type,
            'source': source,
            'confidence': confidence,
            'metadata': metadata.to_dict() if metadata else None
        })
        
    except Exception as e:
        print(f"[API] Error in /api/cite: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/cite/multiple', methods=['POST'])
def cite_multiple():
    """
    Multiple citation options API.
    
    Request JSON:
    {
        "query": "search text",
        "style": "Chicago Manual of Style",
        "limit": 5
    }
    
    Response JSON:
    {
        "success": true,
        "results": [
            {"citation": "...", "metadata": {...}},
            ...
        ]
    }
    """
    try:
        data = request.get_json()
        
        if not data or not data.get('query'):
            return jsonify({
                'success': False,
                'error': 'Missing query parameter'
            }), 400
        
        query = data['query'].strip()
        style = data.get('style', 'Chicago Manual of Style')
        limit = min(data.get('limit', 5), 10)  # Cap at 10
        
        results = get_multiple_citations(query, style, limit)
        
        return jsonify({
            'success': True,
            'results': [
                {
                    'citation': formatted,
                    'source': source,
                    'type': meta.citation_type.name.lower() if meta and meta.citation_type else 'unknown',
                    'confidence': 'high' if (meta and (meta.doi or meta.citation)) else 'medium',
                    'metadata': meta.to_dict() if meta else None
                }
                for meta, formatted, source in results
            ]
        })
        
    except Exception as e:
        print(f"[API] Error in /api/cite/multiple: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/cite/parenthetical', methods=['POST'])
def cite_parenthetical():
    """
    Parenthetical citation options API for Author-Date mode.
    
    Returns multiple possible works for a (Author, Year) citation,
    allowing user to select the correct one.
    
    Request JSON:
    {
        "query": "(Simonton, 1992)",
        "style": "APA 7",
        "limit": 5
    }
    
    Response JSON:
    {
        "success": true,
        "query": "(Simonton, 1992)",
        "recommendation": "Simonton, D. K. (1992). Leaders of American...",
        "options": [
            {
                "id": 0,
                "citation": "(Simonton, 1992)",
                "title": "[Keep Original]",
                "source": "original",
                "is_original": true
            },
            {
                "id": 1,
                "citation": "Simonton, D. K. (1992). Leaders of American...",
                "title": "Leaders of American psychology...",
                "source": "ai_lookup",
                "confidence": "high",
                "is_original": false
            },
            ...
        ]
    }
    """
    try:
        data = request.get_json()
        
        if not data or not data.get('query'):
            return jsonify({
                'success': False,
                'error': 'Missing query parameter'
            }), 400
        
        query = data['query'].strip()
        style = data.get('style', 'APA 7')
        limit = min(data.get('limit', 4), 10)  # Get 4 AI options (plus original = 5 total)
        
        # Get options from AI lookup
        results = get_parenthetical_options(query, style, limit)
        
        # Build options list with original first
        options = [{
            'id': 0,
            'citation': query,
            'title': '[Keep Original]',
            'authors': [],
            'year': '',
            'source': 'original',
            'confidence': 'original',
            'is_original': True,
            'metadata': None
        }]
        
        # Add AI results
        for idx, (meta, formatted) in enumerate(results):
            options.append({
                'id': idx + 1,
                'citation': formatted,
                'title': meta.title if meta else '',
                'authors': meta.authors if meta else [],
                'year': meta.year if meta else '',
                'source': meta.source_engine if meta else 'ai_lookup',
                'confidence': 'high' if meta and meta.confidence >= 0.9 else 'medium' if meta and meta.confidence >= 0.6 else 'low',
                'is_original': False,
                'metadata': meta.to_dict() if meta else None
            })
        
        # Recommendation = first AI result, or original if no AI results
        recommendation = options[1]['citation'] if len(options) > 1 else query
        
        return jsonify({
            'success': True,
            'query': query,
            'recommendation': recommendation,
            'options': options
        })
        
    except Exception as e:
        print(f"[API] Error in /api/cite/parenthetical: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/format-citation', methods=['POST'])
def format_citation():
    """
    Format a citation from raw metadata.
    
    Called when user clicks Accept & Save - this is when formatting happens.
    
    Request JSON:
    {
        "metadata": {
            "title": "The Social Context of Genius",
            "authors": ["Simonton, Dean Keith"],
            "year": "1992",
            "journal": "Psychological Bulletin",
            "volume": "104",
            "issue": "2",
            "pages": "251-267",
            "doi": "10.1037/0033-2909.104.2.251",
            "citation_type": "journal"
        },
        "style": "APA 7"
    }
    
    Response JSON:
    {
        "success": true,
        "formatted": "Simonton, D. K. (1992). The social context..."
    }
    """
    try:
        data = request.get_json()
        
        if not data or not data.get('metadata'):
            return jsonify({
                'success': False,
                'error': 'Missing metadata'
            }), 400
        
        meta_dict = data['metadata']
        style = data.get('style', 'APA 7')
        
        # Handle "keep original" case
        if meta_dict.get('is_original') or meta_dict.get('citation_type') == 'original':
            # Return the original text as-is (no formatting needed)
            return jsonify({
                'success': True,
                'formatted': meta_dict.get('title', '')  # title holds original text for this case
            })
        
        # Convert dict to CitationMetadata
        from models import CitationMetadata, CitationType
        
        # Map citation_type string to enum
        type_map = {
            'journal': CitationType.JOURNAL,
            'book': CitationType.BOOK,
            'legal': CitationType.LEGAL,
            'interview': CitationType.INTERVIEW,
            'letter': CitationType.LETTER,
            'newspaper': CitationType.NEWSPAPER,
            'government': CitationType.GOVERNMENT,
            'medical': CitationType.MEDICAL,
            'url': CitationType.URL,
            'unknown': CitationType.UNKNOWN,
        }
        
        citation_type = type_map.get(
            meta_dict.get('citation_type', 'unknown').lower(),
            CitationType.UNKNOWN
        )
        
        metadata = CitationMetadata(
            citation_type=citation_type,
            title=meta_dict.get('title', ''),
            authors=meta_dict.get('authors', []),
            year=meta_dict.get('year', ''),
            journal=meta_dict.get('journal', ''),
            volume=meta_dict.get('volume', ''),
            issue=meta_dict.get('issue', ''),
            pages=meta_dict.get('pages', ''),
            doi=meta_dict.get('doi', ''),
            url=meta_dict.get('url', ''),
            publisher=meta_dict.get('publisher', ''),
            place=meta_dict.get('place', ''),
            source_engine=meta_dict.get('source', 'manual')
        )
        
        # Get formatter and format
        formatter = get_formatter(style)
        formatted = formatter.format(metadata)
        
        return jsonify({
            'success': True,
            'formatted': formatted
        })
        
    except Exception as e:
        print(f"[API] Error in /api/format-citation: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/process', methods=['POST'])
def process_doc():
    """
    Document processing API.
    
    Expects multipart form with:
    - file: .docx document
    - style: citation style (optional)
    - add_links: whether to make URLs clickable (optional)
    
    Returns processed document as download.
    """
    try:
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No file provided'
            }), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No file selected'
            }), 400
        
        if not allowed_file(file.filename):
            # Audit log security event
            audit.log_request_event(
                event_type=AuditEvent.SECURITY_INVALID_FILE,
                details={'filename': secure_filename(file.filename)}
            )
            return jsonify({
                'success': False,
                'error': 'Only .docx files are supported'
            }), 400
        
        # Audit log document upload
        audit.log_request_event(
            event_type=AuditEvent.DOCUMENT_UPLOAD,
            details={'filename': secure_filename(file.filename)}
        )
        
        # Start tracking costs for this document
        from cost_tracker import start_document_tracking
        start_document_tracking(file.filename)
        
        style = request.form.get('style', 'Chicago Manual of Style')
        add_links = request.form.get('add_links', 'true').lower() == 'true'
        
        # Read file bytes
        file_bytes = file.read()
        
        # Process document (returns bytes, results, and metadata cache)
        processed_bytes, results, metadata_cache = process_document(
            file_bytes,
            style=style,
            add_links=add_links
        )
        
        # Create session to store results
        session_id = sessions.create()
        print(f"[API] Created session {session_id[:8]}... for document {file.filename}")
        
        sessions.set(session_id, 'processed_doc', processed_bytes)
        sessions.set(session_id, 'original_bytes', file_bytes)  # Store original for re-processing
        sessions.set(session_id, 'style', style)
        sessions.set(session_id, 'metadata_cache', metadata_cache)  # Store cache for CSV export
        sessions.set(session_id, 'results', [
            {
                'id': idx + 1,
                'original': r.original,
                'formatted': r.formatted,
                'success': r.success,
                'error': r.error,
                'form': r.citation_form,
                'type': r.citation_type.name.lower() if hasattr(r, 'citation_type') and r.citation_type else 'unknown'
            }
            for idx, r in enumerate(results)
        ])
        sessions.set(session_id, 'filename', secure_filename(file.filename))
        
        print(f"[API] Session {session_id[:8]} initialized with {len(results)} notes, doc size={len(processed_bytes)}")
        print(f"[API] Total active sessions: {len(sessions._sessions)}")
        
        # Build notes list for UI
        notes = []
        for idx, r in enumerate(results):
            note_type = 'unknown'
            if hasattr(r, 'citation_type') and r.citation_type:
                note_type = r.citation_type.name.lower()
            
            notes.append({
                'id': idx + 1,
                'text': r.original,
                'formatted': r.formatted if r.success else r.original,
                'type': note_type,
                'success': r.success,
                'form': r.citation_form
            })
        
        # Return summary with notes for workbench UI
        success_count = sum(1 for r in results if r.success)
        
        # Finish tracking costs and send email
        from cost_tracker import finish_document_tracking
        doc_cost_summary = finish_document_tracking()
        
        # Audit log document processed
        audit.log_request_event(
            event_type=AuditEvent.DOCUMENT_PROCESSED,
            session_id=session_id,
            details={
                'filename': secure_filename(file.filename),
                'citation_count': len(results),
                'success_count': success_count,
                'failure_count': len(results) - success_count
            }
        )
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'notes': notes,  # For workbench UI
            'stats': {
                'total': len(results),
                'success': success_count,
                'failed': len(results) - success_count,
                'ibid': sum(1 for r in results if r.citation_form == 'ibid'),
                'short': sum(1 for r in results if r.citation_form == 'short'),
                'full': sum(1 for r in results if r.citation_form == 'full'),
                'cached_citations': metadata_cache.size(),  # Total cached (old + new)
            },
            'cost': doc_cost_summary,  # Include cost info in response
        })
        
    except Exception as e:
        print(f"[API] Error in /api/process: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/download/<session_id>')
def download(session_id: str):
    """Download processed document."""
    try:
        # Get session data using proper method
        session_data = sessions.get(session_id)
        
        if not session_data:
            # Audit log invalid session
            audit.log_request_event(
                event_type=AuditEvent.SECURITY_INVALID_SESSION,
                session_id=session_id,
                details={'reason': 'not_found_or_expired'}
            )
            return jsonify({
                'success': False,
                'error': 'Session not found or expired'
            }), 404
        
        processed_doc = session_data.get('processed_doc')
        filename = session_data.get('filename', 'processed.docx')
        
        if not processed_doc:
            return jsonify({
                'success': False,
                'error': 'Processed document not found'
            }), 404
        
        # Audit log document download
        audit.log_request_event(
            event_type=AuditEvent.DOCUMENT_DOWNLOAD,
            session_id=session_id,
            details={'filename': filename, 'size_bytes': len(processed_doc)}
        )
        
        from io import BytesIO
        buffer = BytesIO(processed_doc)
        buffer.seek(0)
        
        return send_file(
            buffer,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            as_attachment=True,
            download_name=f"citeflex_{filename}" if filename else "citeflex_processed.docx"
        )
        
    except Exception as e:
        print(f"[API] Error in /api/download: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/export-metadata/<session_id>')
def export_metadata(session_id: str):
    """
    Export citation metadata as CSV file.
    
    This exports the embedded metadata cache from the processed document,
    allowing users to download a spreadsheet of all citation data.
    
    Added: 2025-12-14 (V4.1 - Embedded Metadata Cache)
    Updated: 2025-12-14 (V4.2 - Support author-date mode)
    """
    print(f"[API] export-metadata called for session {session_id[:8]}...")
    
    try:
        session_data = sessions.get(session_id)
        print(f"[API] Session data exists: {session_data is not None}")
        
        if not session_data:
            print(f"[API] Session not found: {session_id[:8]}")
            return jsonify({
                'success': False,
                'error': 'Session not found or expired'
            }), 404
        
        print(f"[API] Session keys: {list(session_data.keys())}")
        
        # Check mode - handle author-date differently
        mode = session_data.get('mode', 'footnote')
        print(f"[API] Session mode: {mode}")
        
        if mode == 'author-date':
            # Build CSV from citations and accepted_references
            citations = session_data.get('citations', [])
            accepted_refs = session_data.get('accepted_references', {})
            
            if not citations:
                return jsonify({
                    'success': False,
                    'error': 'No citations found for this session'
                }), 404
            
            # Build CSV content for author-date mode
            import csv
            from io import StringIO
            
            output = StringIO()
            writer = csv.writer(output)
            
            # Header row
            writer.writerow([
                'Original', 'Formatted', 'Title', 'Authors', 'Year', 
                'Journal', 'Publisher', 'Volume', 'Issue', 'Pages', 
                'DOI', 'URL', 'Type', 'Source'
            ])
            
            # Data rows
            for cite in citations:
                cite_id = str(cite.get('id') or cite.get('note_id', ''))
                original = cite.get('original', '')
                
                # Get formatted text from accepted_references or citation
                formatted = ''
                if cite_id in accepted_refs:
                    formatted = accepted_refs[cite_id].get('formatted', '')
                elif cite.get('formatted'):
                    formatted = cite.get('formatted', '')
                
                # Get metadata from the selected/first option
                options = cite.get('options', [])
                selected_idx = cite.get('selected_option', 1)
                
                # Get the non-original option if available
                meta_option = None
                if len(options) > 1 and selected_idx > 0 and selected_idx < len(options):
                    meta_option = options[selected_idx]
                elif len(options) > 1:
                    meta_option = options[1]  # First AI result
                
                if meta_option and not meta_option.get('is_original'):
                    writer.writerow([
                        original,
                        formatted,
                        meta_option.get('title', ''),
                        '; '.join(meta_option.get('authors', [])),
                        meta_option.get('year', ''),
                        meta_option.get('journal', ''),
                        meta_option.get('publisher', ''),
                        meta_option.get('volume', ''),
                        meta_option.get('issue', ''),
                        meta_option.get('pages', ''),
                        meta_option.get('doi', ''),
                        meta_option.get('url', ''),
                        meta_option.get('citation_type', ''),
                        meta_option.get('source', '')
                    ])
                else:
                    # No metadata available, just export original and formatted
                    writer.writerow([
                        original, formatted, '', '', '', '', '', '', '', '', '', '', '', ''
                    ])
            
            csv_content = output.getvalue()
            print(f"[API] Author-date CSV content length: {len(csv_content)} chars")
            
        else:
            # Footnote mode - use existing metadata_cache logic
            metadata_cache = session_data.get('metadata_cache')
            print(f"[API] metadata_cache exists: {metadata_cache is not None}")
            print(f"[API] metadata_cache type: {type(metadata_cache)}")
            
            if not metadata_cache:
                print(f"[API] No metadata_cache in session")
                return jsonify({
                    'success': False,
                    'error': 'No metadata cache found for this session'
                }), 404
            
            cache_size = metadata_cache.size()
            print(f"[API] metadata_cache size: {cache_size}")
            
            if cache_size == 0:
                print(f"[API] metadata_cache is empty")
                return jsonify({
                    'success': False,
                    'error': 'Metadata cache is empty'
                }), 404
            
            # Generate CSV
            print(f"[API] Generating CSV...")
            csv_content = export_cache_to_csv(metadata_cache)
            print(f"[API] CSV content length: {len(csv_content)} chars")
        
        # Get filename for export
        original_filename = session_data.get('filename', 'document')
        # Remove .docx extension if present
        base_name = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename
        
        from io import BytesIO
        buffer = BytesIO(csv_content.encode('utf-8'))
        buffer.seek(0)
        
        print(f"[API] Sending CSV file: {base_name}_citations.csv")
        return send_file(
            buffer,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f"{base_name}_citations.csv"
        )
        
    except Exception as e:
        import traceback
        print(f"[API] Error in /api/export-metadata: {e}")
        print(f"[API] Traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/results/<session_id>')
def get_results(session_id: str):
    """Get processing results for a session."""
    try:
        session_data = sessions.get(session_id)
        
        if not session_data:
            return jsonify({
                'success': False,
                'error': 'Session not found or expired'
            }), 404
        
        results = session_data.get('results')
        
        if results is None:
            return jsonify({
                'success': False,
                'error': 'Results not found'
            }), 404
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/update', methods=['POST'])
def update_note():
    """
    Update a specific note in the processed document.
    
    Request JSON:
    {
        "session_id": "uuid",
        "note_id": 1,
        "html": "formatted citation text"
    }
    
    This re-processes the document with the updated note.
    Updated: 2025-12-06 - Added retry logic and file locking
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Missing request data'
            }), 400
        
        session_id = data.get('session_id')
        note_id = data.get('note_id')
        new_html = data.get('html', '')
        
        if not session_id or not note_id:
            return jsonify({
                'success': False,
                'error': 'Missing session_id or note_id'
            }), 400
        
        # Retry logic - wait for any concurrent writes to complete
        session_data = None
        for attempt in range(3):
            session_data = sessions.get(session_id)
            if session_data:
                break
            print(f"[API] Session {session_id[:8]} not found, attempt {attempt+1}/3, waiting...")
            time.sleep(0.2)  # Wait 200ms between retries
        
        if not session_data:
            print(f"[API] Session {session_id[:8]} NOT FOUND after 3 attempts")
            return jsonify({
                'success': False,
                'error': 'Session not found or expired'
            }), 404
        
        results = session_data.get('results', [])
        processed_doc = session_data.get('processed_doc')
        
        if not results or not processed_doc:
            print(f"[API] Session {session_id[:8]} has incomplete data: results={bool(results)}, doc={bool(processed_doc)}")
            return jsonify({
                'success': False,
                'error': 'Session data incomplete'
            }), 404
        
        # Update the specific result
        note_idx = note_id - 1  # Convert 1-based to 0-based
        if note_idx < 0 or note_idx >= len(results):
            return jsonify({
                'success': False,
                'error': f'Note {note_id} not found'
            }), 404
        
        # Update the document - this is the critical part
        from document_processor import update_document_note
        try:
            updated_doc = update_document_note(processed_doc, note_id, new_html)
            
            # Verify the update actually changed something
            if updated_doc == processed_doc:
                print(f"[API] Warning: update_document_note returned unchanged document for note {note_id}")
            
            # Save updated document to session
            sessions.set(session_id, 'processed_doc', updated_doc)
            
        except Exception as update_err:
            print(f"[API] Document update failed for note {note_id}: {update_err}")
            return jsonify({
                'success': False,
                'error': f'Failed to update document: {str(update_err)}'
            }), 500
        
        # Update results array
        results[note_idx]['formatted'] = new_html
        results[note_idx]['success'] = True
        sessions.set(session_id, 'results', results)
        
        print(f"[API] Successfully updated note {note_id}")
        
        return jsonify({
            'success': True,
            'note_id': note_id,
            'formatted': new_html
        })
        
    except Exception as e:
        print(f"[API] Error in /api/update: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/process-author-date', methods=['POST'])
def process_author_date():
    """
    Process a document in author-date mode.
    
    Extracts parenthetical citations like (Author, Year) and returns
    multiple options for each citation for user selection.
    
    Request: multipart/form-data with 'file' field
    Optional form fields:
        - style: Citation style (default: 'apa')
    
    Response:
    {
        "success": true,
        "session_id": "uuid",
        "citations": [
            {
                "id": 1,
                "original": "(Simonton, 1992)",
                "options": [
                    {
                        "title": "Leaders, Machines, and Unification",
                        "formatted": "Simonton, D. K. (1992). Leaders...",
                        "authors": ["Simonton, Dean Keith"],
                        "year": "1992",
                        "source": "Crossref"
                    },
                    ...
                ]
            },
            ...
        ]
    }
    """
    try:
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No file provided'
            }), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No file selected'
            }), 400
        
        if not allowed_file(file.filename):
            return jsonify({
                'success': False,
                'error': 'Only .docx files are supported'
            }), 400
        
        style = request.form.get('style', 'apa')  # Default to APA for author-date
        
        # Read file bytes
        file_bytes = file.read()
        
        # Extract document topics for AI context (improves accuracy)
        document_context = get_document_context(file_bytes)
        print(f"[API] Document context: {document_context[:100]}..." if document_context else "[API] No document context extracted")
        
        # Extract author-date citations from document BODY TEXT
        from processors.author_year_extractor import AuthorDateExtractor
        
        extractor = AuthorDateExtractor()
        extracted_citations = extractor.extract_citations_from_docx(file_bytes)
        unique_citations = extractor.get_unique_citations(extracted_citations)
        
        print(f"[API] Extracted {len(extracted_citations)} author-year citations, {len(unique_citations)} unique")
        
        # =====================================================================
        # URL EXTRACTION (Added 2025-12-14)
        # Extract URLs from document body for AI-first metadata lookup
        # =====================================================================
        from processors.url_extractor import extract_urls_from_docx, get_unique_urls
        
        extracted_urls = extract_urls_from_docx(file_bytes)
        unique_urls = get_unique_urls(extracted_urls)
        
        print(f"[API] Extracted {len(extracted_urls)} URLs, {len(unique_urls)} unique")
        
        # Process citations in PARALLEL for speed
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        def process_single_citation(idx, cite):
            """Process one citation - called in parallel. Returns raw metadata."""
            # Preserve ALL author names for better AI lookup accuracy
            # Don't simplify to "et al." - send full author list
            if cite.third_author:
                # Three or more authors - include all three for better matching
                original_text = f"({cite.author}, {cite.second_author}, & {cite.third_author}, {cite.year})"
            elif cite.second_author:
                # Two authors
                original_text = f"({cite.author} & {cite.second_author}, {cite.year})"
            else:
                # Single author
                original_text = f"({cite.author}, {cite.year})"
            
            note_id = idx + 1
            
            try:
                # Get raw metadata (no formatting yet) - pass document context for better accuracy
                metadata_list = get_parenthetical_metadata(original_text, limit=4, context=document_context)
                
                # Build options with raw metadata
                options = [{
                    'id': 0,
                    'title': '[Keep Original]',
                    'authors': [],
                    'year': '',
                    'journal': '',
                    'publisher': '',
                    'volume': '',
                    'issue': '',
                    'pages': '',
                    'doi': '',
                    'url': '',
                    'citation_type': 'original',
                    'source': 'original',
                    'is_original': True
                }]
                
                for opt_idx, meta in enumerate(metadata_list):
                    options.append({
                        'id': opt_idx + 1,
                        'title': meta.title if meta else '',
                        'authors': meta.authors if meta else [],
                        'year': meta.year if meta else '',
                        'journal': getattr(meta, 'journal', '') or '',
                        'publisher': getattr(meta, 'publisher', '') or '',
                        'volume': getattr(meta, 'volume', '') or '',
                        'issue': getattr(meta, 'issue', '') or '',
                        'pages': getattr(meta, 'pages', '') or '',
                        'doi': getattr(meta, 'doi', '') or '',
                        'url': getattr(meta, 'url', '') or '',
                        'citation_type': meta.citation_type.name.lower() if meta and meta.citation_type else 'unknown',
                        'source': getattr(meta, 'source_engine', 'ai_lookup'),
                        'is_original': False
                    })
                
                # Pre-format the recommended option (first AI result) for immediate display
                formatted_recommendation = None
                if len(options) > 1 and len(metadata_list) > 0:
                    try:
                        from formatters.base import get_formatter
                        formatter = get_formatter(style)
                        formatted_recommendation = formatter.format(metadata_list[0])
                    except Exception as fmt_err:
                        print(f"[API] Error pre-formatting recommendation: {fmt_err}")
                
                return {
                    'id': idx + 1,
                    'note_id': note_id,
                    'original': original_text,
                    'options': options,
                    'selected_option': 1 if len(options) > 1 else 0,  # Default to first AI result
                    'formatted': formatted_recommendation,  # Pre-formatted for immediate display
                    'accepted': False
                }
                
            except Exception as e:
                print(f"[API] Error processing '{original_text[:40]}': {e}")
                return {
                    'id': idx + 1,
                    'note_id': note_id,
                    'original': original_text,
                    'options': [{
                        'id': 0,
                        'title': '[Keep Original]',
                        'authors': [],
                        'year': '',
                        'journal': '',
                        'publisher': '',
                        'volume': '',
                        'issue': '',
                        'pages': '',
                        'doi': '',
                        'url': '',
                        'citation_type': 'original',
                        'source': 'original',
                        'is_original': True
                    }],
                    'selected_option': 0,
                    'formatted': None,
                    'accepted': False,
                    'error': str(e)
                }
        
        # Run lookups in parallel (up to 5 concurrent)
        citations = [None] * len(unique_citations)
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(process_single_citation, idx, cite): idx 
                for idx, cite in enumerate(unique_citations)
            }
            for future in as_completed(futures):
                idx = futures[future]
                citations[idx] = future.result()
                print(f"[API] Completed citation {idx + 1}/{len(unique_citations)}")
        
        # =====================================================================
        # URL PROCESSING (Added 2025-12-14)
        # Process each URL through AI lookup to extract metadata
        # =====================================================================
        
        def extract_surname(author_name):
            """
            Extract surname from author name in various formats.
            Handles: "Smith, John" -> "Smith"
                     "John Smith" -> "Smith"
                     "Smith" -> "Smith"
                     "van Gogh, Vincent" -> "van Gogh"
            """
            if not author_name:
                return 'Unknown'
            
            author_name = author_name.strip()
            
            # If contains comma, surname is before the comma
            if ',' in author_name:
                return author_name.split(',')[0].strip()
            
            # Otherwise, surname is the last word (or last word with prefix)
            parts = author_name.split()
            if len(parts) == 0:
                return 'Unknown'
            elif len(parts) == 1:
                return parts[0]
            else:
                # Check for lowercase prefix (van, de, etc.) before last name
                prefixes = ['van', 'de', 'von', 'den', 'der', 'la', 'le', 'di', 'da', 'dos', 'das', 'del', 'della', 'du', 'el', 'al', 'bin', 'ibn']
                if len(parts) >= 2 and parts[-2].lower() in prefixes:
                    return f"{parts[-2]} {parts[-1]}"
                return parts[-1]
        
        def process_single_url(url_idx, url_info):
            """Process one URL - called in parallel. Returns citation-like structure."""
            url = url_info.get('url', '')
            original_text = url  # The URL itself is the "original"
            
            # Calculate global ID (after author-year citations)
            global_id = len(unique_citations) + url_idx + 1
            
            try:
                # Use the unified router to get metadata for the URL
                from unified_router import get_citation
                metadata, formatted = get_citation(url, style)
                
                if metadata:
                    # Build parenthetical text from metadata
                    authors = metadata.authors if metadata.authors else []
                    year = metadata.year or ''
                    
                    if len(authors) >= 3:
                        # 3+ authors: use et al.
                        surname = extract_surname(authors[0])
                        parenthetical = f"({surname} et al., {year})"
                    elif len(authors) == 2:
                        # 2 authors: Author1 & Author2
                        surname1 = extract_surname(authors[0])
                        surname2 = extract_surname(authors[1])
                        parenthetical = f"({surname1} & {surname2}, {year})"
                    elif len(authors) == 1:
                        # 1 author
                        surname = extract_surname(authors[0])
                        parenthetical = f"({surname}, {year})"
                    else:
                        # No author - use title (shortened if needed)
                        title_short = (metadata.title[:30] + '...') if metadata.title and len(metadata.title) > 30 else (metadata.title or 'Unknown')
                        parenthetical = f"({title_short}, {year})"
                        parenthetical = f"({title_short}, {year})"
                    
                    options = [{
                        'id': 0,
                        'title': '[Keep Original URL]',
                        'authors': [],
                        'year': '',
                        'journal': '',
                        'publisher': '',
                        'volume': '',
                        'issue': '',
                        'pages': '',
                        'doi': '',
                        'url': url,
                        'citation_type': 'original',
                        'source': 'original',
                        'is_original': True
                    }, {
                        'id': 1,
                        'title': metadata.title or '',
                        'authors': authors,
                        'year': year,
                        'journal': getattr(metadata, 'journal', '') or '',
                        'publisher': getattr(metadata, 'publisher', '') or '',
                        'volume': getattr(metadata, 'volume', '') or '',
                        'issue': getattr(metadata, 'issue', '') or '',
                        'pages': getattr(metadata, 'pages', '') or '',
                        'doi': getattr(metadata, 'doi', '') or '',
                        'url': getattr(metadata, 'url', url) or url,
                        'citation_type': metadata.citation_type.name.lower() if metadata.citation_type else 'url',
                        'source': getattr(metadata, 'source_engine', 'ai_lookup'),
                        'is_original': False,
                        'parenthetical': parenthetical  # The in-text citation to use
                    }]
                    
                    return {
                        'id': global_id,
                        'note_id': global_id,
                        'original': original_text,
                        'original_url': url,  # Store URL for replacement
                        'global_start': url_info.get('global_start', 0),
                        'global_end': url_info.get('global_end', 0),
                        'options': options,
                        'selected_option': 1,
                        'formatted': formatted,
                        'parenthetical': parenthetical,  # The in-text citation
                        'accepted': False,
                        'is_url': True  # Flag to identify URL citations
                    }
                else:
                    # No metadata found
                    return {
                        'id': global_id,
                        'note_id': global_id,
                        'original': original_text,
                        'original_url': url,
                        'global_start': url_info.get('global_start', 0),
                        'global_end': url_info.get('global_end', 0),
                        'options': [{
                            'id': 0,
                            'title': '[Keep Original URL]',
                            'authors': [],
                            'year': '',
                            'journal': '',
                            'publisher': '',
                            'volume': '',
                            'issue': '',
                            'pages': '',
                            'doi': '',
                            'url': url,
                            'citation_type': 'original',
                            'source': 'original',
                            'is_original': True
                        }],
                        'selected_option': 0,
                        'formatted': None,
                        'parenthetical': None,
                        'accepted': False,
                        'is_url': True,
                        'error': 'No metadata found'
                    }
                    
            except Exception as e:
                print(f"[API] Error processing URL '{url[:50]}': {e}")
                return {
                    'id': global_id,
                    'note_id': global_id,
                    'original': original_text,
                    'original_url': url,
                    'global_start': url_info.get('global_start', 0),
                    'global_end': url_info.get('global_end', 0),
                    'options': [{
                        'id': 0,
                        'title': '[Keep Original URL]',
                        'authors': [],
                        'year': '',
                        'journal': '',
                        'publisher': '',
                        'volume': '',
                        'issue': '',
                        'pages': '',
                        'doi': '',
                        'url': url,
                        'citation_type': 'original',
                        'source': 'original',
                        'is_original': True
                    }],
                    'selected_option': 0,
                    'formatted': None,
                    'parenthetical': None,
                    'accepted': False,
                    'is_url': True,
                    'error': str(e)
                }
        
        # Process URLs in parallel
        url_citations = [None] * len(unique_urls)
        if unique_urls:
            with ThreadPoolExecutor(max_workers=5) as executor:
                url_futures = {
                    executor.submit(process_single_url, idx, url_info): idx 
                    for idx, url_info in enumerate(unique_urls)
                }
                for future in as_completed(url_futures):
                    idx = url_futures[future]
                    url_citations[idx] = future.result()
                    print(f"[API] Completed URL {idx + 1}/{len(unique_urls)}")
        
        # Combine author-year and URL citations
        all_citations = citations + [c for c in url_citations if c is not None]
        
        # Create session to store results
        session_id = sessions.create()
        print(f"[API] Created author-date session {session_id[:8]}... for document {file.filename}")
        
        sessions.set(session_id, 'original_bytes', file_bytes)
        sessions.set(session_id, 'style', style)
        sessions.set(session_id, 'mode', 'author-date')
        sessions.set(session_id, 'citations', all_citations)  # Store combined citations
        sessions.set(session_id, 'filename', secure_filename(file.filename))
        
        # Count stats
        author_year_count = len(citations)
        url_count = len([c for c in url_citations if c is not None])
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'citations': all_citations,
            'stats': {
                'total': len(all_citations),
                'author_year': author_year_count,
                'urls': url_count,
                'with_options': sum(1 for c in all_citations if len(c.get('options', [])) > 1),
                'no_options': sum(1 for c in all_citations if len(c.get('options', [])) <= 1)
            }
        })
        
    except Exception as e:
        print(f"[API] Error in /api/process-author-date: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/accept-reference', methods=['POST'])
def accept_reference():
    """
    Accept/save a formatted reference for author-date mode.
    
    Called when user clicks Accept & Save OR auto-saves on navigation.
    Formats the selected option and persists to server session.
    
    Request JSON (NEW format - preferred):
    {
        "session_id": "uuid",
        "citation_id": 1,
        "selected_option": 1,
        "style": "APA 7"
    }
    
    Request JSON (LEGACY format - still supported):
    {
        "session_id": "uuid",
        "reference_id": 1,
        "formatted": "Simonton, D. K. (1992). The social context..."
    }
    
    Response:
    {
        "success": true,
        "reference_id": 1,
        "formatted": "Simonton, D. K. (1992). ..."
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Missing request data'
            }), 400
        
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({
                'success': False,
                'error': 'Missing session_id'
            }), 400
        
        session_data = sessions.get(session_id)
        
        if not session_data:
            return jsonify({
                'success': False,
                'error': 'Session not found or expired'
            }), 404
        
        # Check which format we received
        if 'selected_option' in data:
            # NEW FORMAT: Format on-demand from selection
            citation_id = data.get('citation_id')
            selected_option = data.get('selected_option', 0)
            style = data.get('style') or session_data.get('style', 'APA 7')
            
            if citation_id is None:
                return jsonify({
                    'success': False,
                    'error': 'Missing citation_id'
                }), 400
            
            # Find the citation in session
            citations = session_data.get('citations', [])
            citation = None
            for c in citations:
                if c.get('id') == citation_id or c.get('note_id') == citation_id:
                    citation = c
                    break
            
            if not citation:
                return jsonify({
                    'success': False,
                    'error': f'Citation {citation_id} not found in session'
                }), 404
            
            # Get the selected option
            options = citation.get('options', [])
            if selected_option < 0 or selected_option >= len(options):
                return jsonify({
                    'success': False,
                    'error': f'Invalid option index {selected_option}'
                }), 400
            
            option = options[selected_option]
            
            # Check if this is "Keep Original"
            if option.get('is_original'):
                formatted = citation.get('original', '')
                reference_id = citation_id
            else:
                # Reconstruct CitationMetadata from option data
                from models import CitationMetadata, CitationType
                
                # Map citation_type string to enum
                type_str = option.get('citation_type', 'unknown').lower()
                type_map = {
                    'journal': CitationType.JOURNAL,
                    'book': CitationType.BOOK,
                    'legal': CitationType.LEGAL,
                    'medical': CitationType.MEDICAL,
                    'newspaper': CitationType.NEWSPAPER,
                    'government': CitationType.GOVERNMENT,
                    'url': CitationType.URL,
                }
                citation_type = type_map.get(type_str, CitationType.JOURNAL)
                
                # Build metadata
                metadata = CitationMetadata(
                    citation_type=citation_type,
                    title=option.get('title', ''),
                    authors=option.get('authors', []),
                    year=option.get('year', ''),
                    journal=option.get('journal', ''),
                    publisher=option.get('publisher', ''),
                    volume=option.get('volume', ''),
                    issue=option.get('issue', ''),
                    pages=option.get('pages', ''),
                    doi=option.get('doi', ''),
                    url=option.get('url', ''),
                    source_engine=option.get('source', 'Unknown'),
                )
                
                # Format using specified style
                formatter = get_formatter(style)
                formatted = formatter.format(metadata)
                reference_id = citation_id
            
            print(f"[API] Formatted citation {citation_id} option {selected_option}: {formatted[:60]}...")
            
        else:
            # LEGACY FORMAT: Pre-formatted text provided
            reference_id = data.get('reference_id')
            formatted = data.get('formatted', '')
            
            if reference_id is None:
                return jsonify({
                    'success': False,
                    'error': 'Missing reference_id'
                }), 400
            
            # For legacy format, check if URL info was provided directly
            citation = None  # Initialize for URL check below
        
        # Get or create accepted_references dict
        accepted_refs = session_data.get('accepted_references', {})
        
        # Build the accepted reference data
        accepted_data = {
            'formatted': formatted,
            'accepted_at': time.time()
        }
        
        # For URL citations, also store the parenthetical and URL info
        # Check both new format (from citation object) and legacy format (from request data)
        if 'selected_option' in data and citation and citation.get('is_url'):
            accepted_data['is_url'] = True
            accepted_data['original_url'] = citation.get('original_url', '')
            # Get parenthetical from the selected option
            if not option.get('is_original') and option.get('parenthetical'):
                accepted_data['parenthetical'] = option.get('parenthetical')
            elif citation.get('parenthetical'):
                accepted_data['parenthetical'] = citation.get('parenthetical')
            else:
                # Build parenthetical from authors/year if available
                authors = option.get('authors', [])
                year = option.get('year', '')
                if authors and year:
                    if len(authors) >= 3:
                        surname = authors[0].split(',')[0].split()[-1] if authors[0] else 'Unknown'
                        accepted_data['parenthetical'] = f"({surname} et al., {year})"
                    elif len(authors) == 2:
                        s1 = authors[0].split(',')[0].split()[-1] if authors[0] else 'Unknown'
                        s2 = authors[1].split(',')[0].split()[-1] if authors[1] else 'Unknown'
                        accepted_data['parenthetical'] = f"({s1} & {s2}, {year})"
                    elif len(authors) == 1:
                        surname = authors[0].split(',')[0].split()[-1] if authors[0] else 'Unknown'
                        accepted_data['parenthetical'] = f"({surname}, {year})"
        elif data.get('is_url'):
            # Legacy format with URL info provided directly in request
            accepted_data['is_url'] = True
            accepted_data['original_url'] = data.get('original_url', '')
            if data.get('parenthetical'):
                accepted_data['parenthetical'] = data.get('parenthetical')
        
        # Store the formatted reference (keyed by reference_id)
        accepted_refs[str(reference_id)] = accepted_data
        
        # Save back to session
        sessions.set(session_id, 'accepted_references', accepted_refs)
        
        print(f"[API] Accepted reference {reference_id} for session {session_id[:8]}")
        
        # Build response
        response_data = {
            'success': True,
            'reference_id': reference_id,
            'formatted': formatted
        }
        
        # Include parenthetical for URL citations
        if accepted_data.get('parenthetical'):
            response_data['parenthetical'] = accepted_data['parenthetical']
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"[API] Error in /api/accept-reference: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/finalize-author-date', methods=['POST'])
def finalize_author_date():
    """
    Finalize author-date document by appending References section.
    
    Called before download. Builds the document with all accepted references.
    
    Request JSON:
    {
        "session_id": "uuid",
        "references": [
            {"id": 1, "original": "(Smith, 2020)", "formatted": "Smith, J. (2020). Title..."},
            ...
        ]
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Missing request data'
            }), 400
        
        session_id = data.get('session_id')
        references = data.get('references', [])
        
        if not session_id:
            return jsonify({
                'success': False,
                'error': 'Missing session_id'
            }), 400
        
        session_data = sessions.get(session_id)
        
        if not session_data:
            return jsonify({
                'success': False,
                'error': 'Session not found or expired'
            }), 404
        
        original_bytes = session_data.get('original_bytes')
        
        if not original_bytes:
            return jsonify({
                'success': False,
                'error': 'Original document not found'
            }), 404
        
        # If no references provided, try to get from accepted_references in session
        if not references:
            accepted_refs = session_data.get('accepted_references', {})
            citations = session_data.get('citations', [])
            
            for cite in citations:
                ref_id = str(cite.get('id', cite.get('note_id')))
                if ref_id in accepted_refs:
                    references.append({
                        'id': ref_id,
                        'original': cite.get('original', ''),
                        'formatted': accepted_refs[ref_id].get('formatted', ''),
                        'parenthetical': accepted_refs[ref_id].get('parenthetical', ''),
                        'is_url': cite.get('is_url', False),
                        'original_url': cite.get('original_url', ''),
                    })
        
        # =====================================================================
        # URL REPLACEMENT IN DOCUMENT BODY (Added 2025-12-14)
        # Replace URLs with parenthetical citations before adding References
        # =====================================================================
        
        # Collect URL replacements
        url_replacements = []
        for ref in references:
            if ref.get('is_url') and ref.get('original_url') and ref.get('parenthetical'):
                url_replacements.append({
                    'url': ref['original_url'],
                    'parenthetical': ref['parenthetical'],
                })
        
        print(f"[API] URL replacements to make: {len(url_replacements)}")
        
        # Generate document with References section
        from io import BytesIO
        import zipfile
        import tempfile
        import shutil
        import xml.etree.ElementTree as ET
        import re
        
        temp_dir = tempfile.mkdtemp()
        
        try:
            with zipfile.ZipFile(BytesIO(original_bytes), 'r') as zf:
                zf.extractall(temp_dir)
            
            doc_path = os.path.join(temp_dir, 'word', 'document.xml')
            
            # Register namespaces
            namespaces = {
                'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
                'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
            }
            for prefix, uri in namespaces.items():
                ET.register_namespace(prefix, uri)
            
            tree = ET.parse(doc_path)
            root = tree.getroot()
            body = root.find('.//w:body', namespaces)
            
            # =================================================================
            # STEP 1: Replace URLs in document body with parentheticals
            # =================================================================
            if url_replacements and body is not None:
                # Build a map of URL -> parenthetical
                url_to_paren = {r['url']: r['parenthetical'] for r in url_replacements}
                
                # Process each paragraph
                for para in body.findall('.//w:p', namespaces):
                    # Get all text elements in this paragraph
                    text_elements = para.findall('.//w:t', namespaces)
                    
                    # Join text to find URLs
                    full_text = ''.join(t.text or '' for t in text_elements)
                    
                    # Find all URLs in this paragraph that need replacement
                    urls_in_para = []
                    for url in url_to_paren.keys():
                        if url in full_text:
                            start_idx = full_text.find(url)
                            urls_in_para.append({
                                'url': url,
                                'start': start_idx,
                                'end': start_idx + len(url),
                                'parenthetical': url_to_paren[url]
                            })
                    
                    if not urls_in_para:
                        continue
                    
                    # Sort by position
                    urls_in_para.sort(key=lambda x: x['start'])
                    
                    # Check for adjacent URLs (within 5 characters of each other)
                    # and merge them with semicolons
                    merged_groups = []
                    current_group = [urls_in_para[0]]
                    
                    for i in range(1, len(urls_in_para)):
                        prev = urls_in_para[i-1]
                        curr = urls_in_para[i]
                        
                        # If current URL starts within 20 chars of previous URL end
                        # (allowing for ". " or ", " or " and " between)
                        if curr['start'] - prev['end'] <= 20:
                            current_group.append(curr)
                        else:
                            merged_groups.append(current_group)
                            current_group = [curr]
                    
                    merged_groups.append(current_group)
                    
                    # Build replacement text for the entire paragraph
                    new_text = full_text
                    
                    # Process groups in reverse order to maintain positions
                    for group in reversed(merged_groups):
                        if len(group) == 1:
                            # Single URL - simple replacement
                            url_info = group[0]
                            new_text = new_text[:url_info['start']] + url_info['parenthetical'] + new_text[url_info['end']:]
                        else:
                            # Multiple adjacent URLs - combine with semicolons
                            # Remove the inner parts of parentheticals and join
                            parentheticals = [g['parenthetical'] for g in group]
                            # Strip outer parens and join with semicolons
                            inner_parts = [p.strip('()') for p in parentheticals]
                            combined = '(' + '; '.join(inner_parts) + ')'
                            
                            # Replace from first URL start to last URL end
                            start = group[0]['start']
                            end = group[-1]['end']
                            
                            # Also remove any separators between URLs
                            new_text = new_text[:start] + combined + new_text[end:]
                    
                    # Now update the XML with new text
                    # Simple approach: clear all text elements and set first one
                    if text_elements and new_text != full_text:
                        # Clear all text elements
                        for t in text_elements[1:]:
                            t.text = ''
                        # Set first element to new text
                        text_elements[0].text = new_text
                        
                        print(f"[API] Replaced URLs in paragraph: {full_text[:50]}... -> {new_text[:50]}...")
            
            # =================================================================
            # STEP 2: Add References section
            # =================================================================
            
            if body is not None:
                sect_pr = body.find('w:sectPr', namespaces)
                
                # Create References heading
                heading_para = ET.Element(f"{{{namespaces['w']}}}p")
                heading_pPr = ET.SubElement(heading_para, f"{{{namespaces['w']}}}pPr")
                heading_style = ET.SubElement(heading_pPr, f"{{{namespaces['w']}}}pStyle")
                heading_style.set(f"{{{namespaces['w']}}}val", "Heading1")
                heading_run = ET.SubElement(heading_para, f"{{{namespaces['w']}}}r")
                heading_text = ET.SubElement(heading_run, f"{{{namespaces['w']}}}t")
                heading_text.text = "References"
                
                # Add blank line
                blank_para = ET.Element(f"{{{namespaces['w']}}}p")
                
                if sect_pr is not None:
                    idx = list(body).index(sect_pr)
                    body.insert(idx, heading_para)
                    body.insert(idx + 1, blank_para)
                else:
                    body.append(heading_para)
                    body.append(blank_para)
                
                # Sort references alphabetically by formatted text
                sorted_refs = sorted(references, key=lambda r: r.get('formatted', '').lower())
                
                # Add each reference
                for ref in sorted_refs:
                    formatted = ref.get('formatted', ref.get('original', ''))
                    if not formatted:
                        continue
                    
                    ref_para = ET.Element(f"{{{namespaces['w']}}}p")
                    
                    # Hanging indent style
                    ref_pPr = ET.SubElement(ref_para, f"{{{namespaces['w']}}}pPr")
                    ref_ind = ET.SubElement(ref_pPr, f"{{{namespaces['w']}}}ind")
                    ref_ind.set(f"{{{namespaces['w']}}}left", "720")
                    ref_ind.set(f"{{{namespaces['w']}}}hanging", "720")
                    
                    # Parse for italics
                    import re
                    import html
                    parts = re.split(r'(<i>.*?</i>)', html.unescape(formatted))
                    
                    for part in parts:
                        if not part:
                            continue
                        
                        run = ET.SubElement(ref_para, f"{{{namespaces['w']}}}r")
                        
                        italic_match = re.match(r'<i>(.*?)</i>', part)
                        if italic_match:
                            rPr = ET.SubElement(run, f"{{{namespaces['w']}}}rPr")
                            ET.SubElement(rPr, f"{{{namespaces['w']}}}i")
                            text_content = italic_match.group(1)
                        else:
                            text_content = part
                        
                        t = ET.SubElement(run, f"{{{namespaces['w']}}}t")
                        t.text = text_content
                        t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
                    
                    if sect_pr is not None:
                        idx = list(body).index(sect_pr)
                        body.insert(idx, ref_para)
                    else:
                        body.append(ref_para)
            
            # Write modified document
            tree.write(doc_path, encoding='UTF-8', xml_declaration=True)
            
            # Repackage docx
            output_buffer = BytesIO()
            with zipfile.ZipFile(output_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root_dir, dirs, files in os.walk(temp_dir):
                    for file in files:
                        file_path = os.path.join(root_dir, file)
                        arcname = os.path.relpath(file_path, temp_dir)
                        zf.write(file_path, arcname)
            
            output_buffer.seek(0)
            processed_bytes = output_buffer.read()
            
            # Save to session for download
            sessions.set(session_id, 'processed_doc', processed_bytes)
            
            print(f"[API] Finalized author-date document with {len(references)} references")
            
            return jsonify({
                'success': True,
                'reference_count': len(references)
            })
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
    except Exception as e:
        print(f"[API] Error in /api/finalize-author-date: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/select-citation', methods=['POST'])
def select_citation():
    """
    Select a specific citation option for an author-date citation.
    
    Request JSON:
    {
        "session_id": "uuid",
        "citation_id": 1,
        "option_index": 0  // Which option was selected (0-indexed)
    }
    
    This updates the document with the selected citation.
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Missing request data'
            }), 400
        
        session_id = data.get('session_id')
        citation_id = data.get('citation_id')
        option_index = data.get('option_index', 0)
        
        if not session_id or citation_id is None:
            return jsonify({
                'success': False,
                'error': 'Missing session_id or citation_id'
            }), 400
        
        session_data = sessions.get(session_id)
        if not session_data:
            return jsonify({
                'success': False,
                'error': 'Session not found or expired'
            }), 404
        
        citations = session_data.get('citations', [])
        
        # Find the citation
        citation = None
        for c in citations:
            if c['id'] == citation_id:
                citation = c
                break
        
        if not citation:
            return jsonify({
                'success': False,
                'error': f'Citation {citation_id} not found'
            }), 404
        
        options = citation.get('options', [])
        if option_index < 0 or option_index >= len(options):
            return jsonify({
                'success': False,
                'error': f'Invalid option index {option_index}'
            }), 400
        
        selected = options[option_index]
        
        # Update the citation with the selection
        citation['selected'] = selected
        citation['formatted'] = selected['formatted']
        
        sessions.set(session_id, 'citations', citations)
        
        return jsonify({
            'success': True,
            'citation_id': citation_id,
            'formatted': selected['formatted']
        })
        
    except Exception as e:
        print(f"[API] Error in /api/select-citation: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# ADMIN: COST REPORTING
# =============================================================================

@app.route('/admin/email-costs')
def admin_email_costs():
    """
    Send cost report to admin email.
    
    Requires secret key: /admin/email-costs?key=YOUR_ADMIN_SECRET
    
    Environment variables required:
        - ADMIN_SECRET: Secret key for authentication
        - ADMIN_EMAIL: Where to send the report
        - RESEND_API_KEY: Resend.com API key
    """
    from email_service import ADMIN_SECRET, send_cost_report
    
    # Audit log admin access attempt
    audit.log_request_event(
        event_type=AuditEvent.ADMIN_ACCESS_ATTEMPT,
        details={'endpoint': '/admin/email-costs'}
    )
    
    # Check for secret key
    provided_key = request.args.get('key', '')
    
    if not ADMIN_SECRET:
        return jsonify({
            'success': False,
            'error': 'ADMIN_SECRET not configured on server'
        }), 500
    
    if not provided_key or provided_key != ADMIN_SECRET:
        # Audit log denied access
        audit.log_request_event(
            event_type=AuditEvent.ADMIN_ACCESS_DENIED,
            details={'endpoint': '/admin/email-costs', 'reason': 'invalid_key'}
        )
        return jsonify({
            'success': False,
            'error': 'Invalid or missing key'
        }), 403
    
    # Audit log cost report request
    audit.log_request_event(
        event_type=AuditEvent.ADMIN_COST_REPORT,
        details={'endpoint': '/admin/email-costs'}
    )
    
    # Send the report
    success = send_cost_report()
    
    if success:
        return jsonify({
            'success': True,
            'message': 'Cost report sent to admin email'
        })
    else:
        return jsonify({
            'success': False,
            'error': 'Failed to send email. Check server logs and verify RESEND_API_KEY and ADMIN_EMAIL are configured.'
        }), 500


@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'version': '2.1.0',  # Updated version for author-date support
        'sessions_count': len(sessions._sessions),
        'persistence': sessions._persistence_available
    })


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
