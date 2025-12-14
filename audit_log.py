"""
citategenie/audit_log.py

Audit logging for SOC 2 compliance.

Logs security-relevant events with:
- Timestamp (ISO 8601 UTC)
- Event type
- Session ID (if applicable)
- IP address
- User agent
- Action details (never document content)

SOC 2 Compliance Notes:
- Append-only log (never modify/delete entries)
- Structured JSON format for analysis
- Retains: who, what, when, where
- NEVER logs document content, only metadata
- Logs should be retained for 1 year minimum

Usage:
    from audit_log import audit
    
    # Log a document upload
    audit.log_event(
        event_type=AuditEvent.DOCUMENT_UPLOAD,
        session_id=session_id,
        details={'filename': 'brief.docx', 'size_bytes': 52400}
    )
    
    # Log from Flask request context (auto-captures IP, user agent)
    audit.log_request_event(
        event_type=AuditEvent.DOCUMENT_DOWNLOAD,
        session_id=session_id
    )

Version History:
    2025-12-14: Initial implementation for SOC 2 compliance
"""

import os
import json
import fcntl
import threading
from enum import Enum
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any


class AuditEvent(Enum):
    """
    Enumeration of auditable events.
    
    Categories:
    - SESSION_*: Session lifecycle events
    - DOCUMENT_*: Document handling events
    - API_*: API access events
    - ADMIN_*: Administrative actions
    - SECURITY_*: Security-relevant events
    """
    
    # Session events
    SESSION_CREATED = "session.created"
    SESSION_ACCESSED = "session.accessed"
    SESSION_EXPIRED = "session.expired"
    SESSION_DELETED = "session.deleted"
    
    # Document events
    DOCUMENT_UPLOAD = "document.upload"
    DOCUMENT_PROCESSED = "document.processed"
    DOCUMENT_DOWNLOAD = "document.download"
    DOCUMENT_DELETED = "document.deleted"
    
    # API events
    API_CITE_REQUEST = "api.cite.request"
    API_CITE_SUCCESS = "api.cite.success"
    API_CITE_FAILURE = "api.cite.failure"
    API_PROCESS_REQUEST = "api.process.request"
    API_PROCESS_SUCCESS = "api.process.success"
    API_PROCESS_FAILURE = "api.process.failure"
    
    # Admin events
    ADMIN_COST_REPORT = "admin.cost_report"
    ADMIN_EXPORT_CACHE = "admin.export_cache"
    ADMIN_ACCESS_ATTEMPT = "admin.access_attempt"
    ADMIN_ACCESS_DENIED = "admin.access_denied"
    
    # Security events
    SECURITY_INVALID_FILE = "security.invalid_file"
    SECURITY_RATE_LIMITED = "security.rate_limited"
    SECURITY_DECRYPTION_FAILED = "security.decryption_failed"
    SECURITY_INVALID_SESSION = "security.invalid_session"


class AuditLogger:
    """
    Thread-safe audit logger with append-only file output.
    
    Log file format: JSON Lines (one JSON object per line)
    Location: /data/audit/audit.log (or AUDIT_LOG_PATH env var)
    
    Each log entry contains:
    {
        "timestamp": "2025-12-14T15:30:00.000Z",
        "event": "document.upload",
        "session_id": "abc123...",  # truncated for privacy
        "ip_address": "192.168.1.1",
        "user_agent": "Mozilla/5.0...",
        "details": {...},  # event-specific metadata
        "request_id": "uuid"  # for correlating related events
    }
    """
    
    def __init__(self, log_path: Optional[Path] = None):
        self._lock = threading.Lock()
        
        # Determine log path
        if log_path:
            self._log_path = log_path
        else:
            log_dir = Path(os.environ.get('AUDIT_LOG_DIR', '/data/audit'))
            self._log_path = log_dir / 'audit.log'
        
        self._enabled = self._init_log_file()
    
    def _init_log_file(self) -> bool:
        """Initialize log directory and file."""
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Test write access
            if not self._log_path.exists():
                self._log_path.touch()
            
            print(f"[AuditLog] Logging to {self._log_path}")
            return True
            
        except Exception as e:
            print(f"[AuditLog] WARNING: Could not initialize audit log: {e}")
            print("[AuditLog] Audit logging disabled - events will only print to stdout")
            return False
    
    def _get_request_context(self) -> Dict[str, str]:
        """
        Extract IP and user agent from Flask request context.
        
        Returns empty dict if not in request context.
        """
        try:
            from flask import request, has_request_context
            
            if has_request_context():
                # Get real IP (handle proxies)
                ip = request.headers.get('X-Forwarded-For', request.remote_addr)
                if ip and ',' in ip:
                    ip = ip.split(',')[0].strip()  # First IP in chain
                
                return {
                    'ip_address': ip or 'unknown',
                    'user_agent': request.headers.get('User-Agent', 'unknown')[:200],  # Truncate
                    'request_path': request.path,
                    'request_method': request.method,
                }
            
        except ImportError:
            pass
        except Exception as e:
            print(f"[AuditLog] Error getting request context: {e}")
        
        return {}
    
    def _truncate_session_id(self, session_id: Optional[str]) -> Optional[str]:
        """
        Truncate session ID for privacy while maintaining correlation ability.
        
        Full session IDs in logs could be a security risk if logs are compromised.
        First 8 + last 4 characters is enough for debugging.
        """
        if not session_id:
            return None
        if len(session_id) <= 12:
            return session_id
        return f"{session_id[:8]}...{session_id[-4:]}"
    
    def _sanitize_details(self, details: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Sanitize event details to ensure no sensitive data is logged.
        
        CRITICAL: Never log document content, only metadata.
        """
        if not details:
            return {}
        
        sanitized = {}
        
        # Allowed keys (whitelist approach)
        safe_keys = {
            'filename', 'size_bytes', 'citation_count', 'success_count',
            'failure_count', 'processing_time_ms', 'style', 'error_type',
            'error_message', 'citation_type', 'endpoint', 'status_code',
            'reason', 'attempt_count', 'cache_hit', 'api_provider',
        }
        
        for key, value in details.items():
            if key in safe_keys:
                # Truncate strings to prevent log bloat
                if isinstance(value, str) and len(value) > 500:
                    value = value[:500] + '...'
                sanitized[key] = value
            else:
                # Log that we skipped a key (for debugging)
                sanitized[f'_skipped_{key}'] = type(value).__name__
        
        return sanitized
    
    def log_event(
        self,
        event_type: AuditEvent,
        session_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """
        Log an audit event.
        
        Args:
            event_type: The type of event (from AuditEvent enum)
            session_id: Session identifier (will be truncated)
            details: Event-specific metadata (will be sanitized)
            request_id: UUID for correlating related events
            ip_address: Client IP (optional, auto-detected in request context)
            user_agent: Client user agent (optional, auto-detected)
        """
        import uuid
        
        # Build log entry
        entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'event': event_type.value,
            'session_id': self._truncate_session_id(session_id),
            'request_id': request_id or str(uuid.uuid4())[:8],
            'details': self._sanitize_details(details),
        }
        
        # Add request context if available
        if ip_address:
            entry['ip_address'] = ip_address
        if user_agent:
            entry['user_agent'] = user_agent[:200]
        
        # Write to log
        self._write_entry(entry)
    
    def log_request_event(
        self,
        event_type: AuditEvent,
        session_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log an event with automatic Flask request context extraction.
        
        Use this for events triggered by HTTP requests.
        """
        context = self._get_request_context()
        
        self.log_event(
            event_type=event_type,
            session_id=session_id,
            details={**(details or {}), **{k: v for k, v in context.items() if k.startswith('request_')}},
            ip_address=context.get('ip_address'),
            user_agent=context.get('user_agent'),
        )
    
    def _write_entry(self, entry: Dict[str, Any]) -> None:
        """
        Write log entry to file (thread-safe, append-only).
        """
        log_line = json.dumps(entry, default=str) + '\n'
        
        # Always print to stdout for Railway logs
        print(f"[AUDIT] {entry['event']} session={entry.get('session_id', 'none')}")
        
        if not self._enabled:
            return
        
        with self._lock:
            try:
                with open(self._log_path, 'a', encoding='utf-8') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    f.write(log_line)
                    f.flush()
                    os.fsync(f.fileno())
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception as e:
                print(f"[AuditLog] ERROR writing to log: {e}")
    
    def get_recent_events(
        self,
        count: int = 100,
        event_type: Optional[AuditEvent] = None,
        session_id: Optional[str] = None,
    ) -> list:
        """
        Retrieve recent audit events (for admin dashboard).
        
        Args:
            count: Maximum events to return
            event_type: Filter by event type
            session_id: Filter by session (prefix match on truncated ID)
        
        Returns:
            List of event dicts, newest first
        """
        if not self._enabled or not self._log_path.exists():
            return []
        
        events = []
        
        try:
            with open(self._log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Process in reverse (newest first)
            for line in reversed(lines):
                if len(events) >= count:
                    break
                
                try:
                    entry = json.loads(line.strip())
                    
                    # Apply filters
                    if event_type and entry.get('event') != event_type.value:
                        continue
                    if session_id and not (entry.get('session_id', '').startswith(session_id[:8])):
                        continue
                    
                    events.append(entry)
                    
                except json.JSONDecodeError:
                    continue
            
        except Exception as e:
            print(f"[AuditLog] Error reading log: {e}")
        
        return events


# Module-level singleton
_audit_logger: Optional[AuditLogger] = None

def get_audit_logger() -> AuditLogger:
    """Get or create the audit logger singleton."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


# Convenience alias
audit = get_audit_logger()
