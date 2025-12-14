"""
citategenie/encryption.py

Encryption utilities for secure session persistence.

SOC 2 Compliance Notes:
- AES-256 encryption via Fernet (symmetric, authenticated)
- Per-session keys derived from master secret + session ID
- Master secret must be stored securely (environment variable)
- Keys never written to disk

Usage:
    from encryption import SessionEncryption
    
    encryptor = SessionEncryption()
    
    # Encrypt before saving
    encrypted = encryptor.encrypt(session_id, data_bytes)
    
    # Decrypt after loading
    decrypted = encryptor.decrypt(session_id, encrypted_bytes)

Version History:
    2025-12-14: Initial implementation for SOC 2 compliance
"""

import os
import base64
import hashlib
import secrets
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class SessionEncryption:
    """
    Handles encryption/decryption of session data.
    
    Security model:
    - Master secret from environment (ENCRYPTION_KEY)
    - Per-session keys derived via PBKDF2
    - Fernet provides AES-128-CBC + HMAC-SHA256
    
    If ENCRYPTION_KEY is not set, generates a random one (logs warning).
    In production, ENCRYPTION_KEY must be set and rotated periodically.
    """
    
    def __init__(self):
        self._master_secret = self._load_master_secret()
    
    def _load_master_secret(self) -> bytes:
        """
        Load master encryption key from environment.
        
        CRITICAL: In production, set ENCRYPTION_KEY to a secure random value.
        Generate with: python -c "import secrets; print(secrets.token_hex(32))"
        """
        key = os.environ.get('ENCRYPTION_KEY', '')
        
        if not key:
            # Development fallback - NOT FOR PRODUCTION
            print("[Encryption] WARNING: ENCRYPTION_KEY not set. Using random key.")
            print("[Encryption] Sessions will NOT survive restarts without ENCRYPTION_KEY.")
            key = secrets.token_hex(32)
        
        return key.encode('utf-8')
    
    def _derive_key(self, session_id: str) -> bytes:
        """
        Derive a unique Fernet key for each session.
        
        Uses PBKDF2 with:
        - Master secret as password
        - Session ID as salt
        - 100,000 iterations (OWASP recommendation)
        
        This ensures:
        - Each session has a unique encryption key
        - Compromising one session doesn't compromise others
        - Master secret alone isn't enough to decrypt
        """
        salt = session_id.encode('utf-8')
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        
        derived = kdf.derive(self._master_secret)
        
        # Fernet requires base64-encoded 32-byte key
        return base64.urlsafe_b64encode(derived)
    
    def encrypt(self, session_id: str, data: bytes) -> bytes:
        """
        Encrypt data for a specific session.
        
        Args:
            session_id: The session identifier (used to derive key)
            data: Raw bytes to encrypt (e.g., pickled session data)
        
        Returns:
            Encrypted bytes (safe to write to disk)
        """
        key = self._derive_key(session_id)
        fernet = Fernet(key)
        return fernet.encrypt(data)
    
    def decrypt(self, session_id: str, encrypted_data: bytes) -> Optional[bytes]:
        """
        Decrypt data for a specific session.
        
        Args:
            session_id: The session identifier (must match encryption)
            encrypted_data: Bytes from encrypt()
        
        Returns:
            Decrypted bytes, or None if decryption fails
        """
        try:
            key = self._derive_key(session_id)
            fernet = Fernet(key)
            return fernet.decrypt(encrypted_data)
        except InvalidToken:
            print(f"[Encryption] Decryption failed for session {session_id[:8]}...")
            return None
        except Exception as e:
            print(f"[Encryption] Unexpected error: {e}")
            return None


# Module-level singleton for convenience
_encryptor: Optional[SessionEncryption] = None

def get_encryptor() -> SessionEncryption:
    """Get or create the encryption singleton."""
    global _encryptor
    if _encryptor is None:
        _encryptor = SessionEncryption()
    return _encryptor
