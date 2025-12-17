"""
billing/db.py

Database connection management for CitateGenie.

Design principles:
    1. Environment-driven: DATABASE_URL from Railway/AWS
    2. Connection pooling: Sized for container workloads
    3. Scoped sessions: Thread-safe, auto-cleanup
    4. Provider-agnostic: Works with any PostgreSQL host

Usage:
    from billing.db import get_db, init_db
    
    # In Flask app startup:
    init_db(app)
    
    # In request handlers:
    db = get_db()
    user = db.query(User).filter_by(email=email).first()

Version History:
    2025-12-17: Initial implementation
"""

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from sqlalchemy.pool import QueuePool


# =============================================================================
# CONFIGURATION
# =============================================================================

def get_database_url() -> str:
    """
    Get database URL from environment.
    
    Railway format: postgresql://user:pass@host:5432/dbname
    AWS RDS format: postgresql://user:pass@host.region.rds.amazonaws.com:5432/dbname
    
    Both work identically - just change the env var.
    """
    url = os.environ.get('DATABASE_URL', '')
    
    if not url:
        # Fallback for local development
        url = os.environ.get(
            'DEV_DATABASE_URL',
            'postgresql://localhost:5432/citategenie_dev'
        )
        print("[DB] WARNING: DATABASE_URL not set, using dev fallback")
    
    # Heroku/Railway sometimes use 'postgres://' which SQLAlchemy 2.0 doesn't like
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    
    return url


# =============================================================================
# ENGINE AND SESSION FACTORY
# =============================================================================

# Connection pool settings optimized for container workloads
POOL_CONFIG = {
    'poolclass': QueuePool,
    'pool_size': 5,           # Connections to keep open
    'max_overflow': 10,       # Extra connections under load
    'pool_timeout': 30,       # Seconds to wait for connection
    'pool_recycle': 1800,     # Recycle connections after 30 min (avoid stale)
    'pool_pre_ping': True,    # Test connections before using (handles disconnects)
}

_engine = None
_session_factory = None
_scoped_session = None


def get_engine():
    """Get or create the SQLAlchemy engine."""
    global _engine
    
    if _engine is None:
        database_url = get_database_url()
        _engine = create_engine(database_url, **POOL_CONFIG)
        
        # Log connection events in debug mode
        if os.environ.get('DEBUG_DB'):
            @event.listens_for(_engine, 'connect')
            def on_connect(dbapi_conn, connection_record):
                print(f"[DB] New connection established")
            
            @event.listens_for(_engine, 'checkout')
            def on_checkout(dbapi_conn, connection_record, connection_proxy):
                print(f"[DB] Connection checked out from pool")
    
    return _engine


def get_session_factory():
    """Get or create the session factory."""
    global _session_factory
    
    if _session_factory is None:
        engine = get_engine()
        _session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    
    return _session_factory


def get_scoped_session():
    """
    Get the scoped session for thread-safe access.
    
    Scoped sessions are essential for Flask:
    - Each request gets its own session
    - Sessions are automatically cleaned up
    - Thread-safe for gunicorn workers
    """
    global _scoped_session
    
    if _scoped_session is None:
        _scoped_session = scoped_session(get_session_factory())
    
    return _scoped_session


# =============================================================================
# PUBLIC API
# =============================================================================

def get_db() -> Session:
    """
    Get a database session for the current request/thread.
    
    Usage:
        db = get_db()
        user = db.query(User).filter_by(email=email).first()
    """
    return get_scoped_session()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions with automatic cleanup.
    
    Usage:
        with db_session() as db:
            user = db.query(User).filter_by(email=email).first()
            db.commit()
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(app=None):
    """
    Initialize database for Flask app.
    
    Call this during app startup:
        app = Flask(__name__)
        init_db(app)
    
    Registers teardown to clean up sessions after each request.
    Auto-creates tables if they don't exist (idempotent).
    """
    # Ensure engine is created
    engine = get_engine()
    
    # Auto-create tables (idempotent - only creates if missing)
    from billing.models import Base
    Base.metadata.create_all(engine)
    
    if app is not None:
        @app.teardown_appcontext
        def shutdown_session(exception=None):
            """Clean up scoped session after each request."""
            scoped = get_scoped_session()
            scoped.remove()
        
        print("[DB] Database initialized for Flask app")


def create_all_tables():
    """
    Create all tables defined in models.
    
    Call this once during initial setup or migrations:
        from billing.db import create_all_tables
        from billing.models import Base
        create_all_tables()
    """
    from billing.models import Base
    engine = get_engine()
    Base.metadata.create_all(engine)
    print("[DB] All tables created")


def drop_all_tables():
    """
    Drop all tables. USE WITH CAUTION - destroys data!
    
    Only for development/testing.
    """
    from billing.models import Base
    engine = get_engine()
    Base.metadata.drop_all(engine)
    print("[DB] All tables dropped")


# =============================================================================
# HEALTH CHECK
# =============================================================================

def check_connection() -> bool:
    """
    Check if database is reachable.
    
    Use for /health endpoint:
        @app.route('/health')
        def health():
            if check_connection():
                return {'status': 'healthy', 'db': 'connected'}
            return {'status': 'unhealthy', 'db': 'disconnected'}, 500
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception as e:
        print(f"[DB] Health check failed: {e}")
        return False
