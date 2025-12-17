"""
billing/auth.py

Authentication module for CitateGenie.

Features:
    - Email/password authentication
    - Flask-Login integration
    - Password hashing with bcrypt
    - Signup bonus credit grant

Future additions:
    - Email verification
    - Password reset
    - OAuth providers (Google, GitHub)
    - Rate limiting

Usage:
    from billing.auth import init_auth, register_user, authenticate_user
    
    # In Flask app:
    init_auth(app)
    
    # Registration:
    user, error = register_user('user@example.com', 'password123')
    
    # Login:
    user = authenticate_user('user@example.com', 'password123')
    if user:
        login_user(user)

Version History:
    2025-12-17: Initial implementation
"""

import re
from typing import Optional, Tuple
from datetime import datetime

from flask import current_app
from flask_login import LoginManager, login_user, logout_user, current_user

from billing.db import get_db
from billing.models import User, CreditLedger, CreditReason
from billing.config import SIGNUP_BONUS_CREDITS, SIGNUP_BONUS_REASON


# =============================================================================
# FLASK-LOGIN SETUP
# =============================================================================

login_manager = LoginManager()


@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    """Load user by ID for Flask-Login."""
    try:
        db = get_db()
        return db.query(User).get(int(user_id))
    except Exception:
        return None


def init_auth(app):
    """
    Initialize authentication for Flask app.
    
    Call during app startup:
        app = Flask(__name__)
        init_auth(app)
    """
    login_manager.init_app(app)
    login_manager.login_view = 'billing_bp.login'  # Redirect unauthorized users here
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    print("[Auth] Authentication initialized")


# =============================================================================
# VALIDATION
# =============================================================================

def validate_email(email: str) -> Tuple[bool, Optional[str]]:
    """
    Validate email format.
    
    Returns:
        (is_valid, error_message)
    """
    if not email:
        return False, "Email is required"
    
    email = email.strip().lower()
    
    # Basic format check
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, "Invalid email format"
    
    if len(email) > 500:
        return False, "Email too long"
    
    return True, None


def validate_password(password: str) -> Tuple[bool, Optional[str]]:
    """
    Validate password strength.
    
    Requirements:
        - At least 8 characters
        - (Future: complexity requirements)
    
    Returns:
        (is_valid, error_message)
    """
    if not password:
        return False, "Password is required"
    
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    
    if len(password) > 200:
        return False, "Password too long"
    
    # Future: Add complexity requirements
    # - At least one uppercase
    # - At least one number
    # - At least one special character
    
    return True, None


# =============================================================================
# USER REGISTRATION
# =============================================================================

def register_user(
    email: str, 
    password: str, 
    name: Optional[str] = None
) -> Tuple[Optional[User], Optional[str]]:
    """
    Register a new user.
    
    Flow:
        1. Validate email/password
        2. Check email not already taken
        3. Create user with hashed password
        4. Grant signup bonus credits
    
    Args:
        email: User's email address
        password: User's password (will be hashed)
        name: Optional display name
    
    Returns:
        (user, None) on success
        (None, error_message) on failure
    """
    # Validate email
    valid, error = validate_email(email)
    if not valid:
        return None, error
    
    email = email.strip().lower()
    
    # Validate password
    valid, error = validate_password(password)
    if not valid:
        return None, error
    
    db = get_db()
    
    try:
        # Check if email exists
        existing = db.query(User).filter_by(email=email).first()
        if existing:
            return None, "Email already registered"
        
        # Create user
        user = User(
            email=email,
            name=name.strip() if name else None,
        )
        user.set_password(password)
        
        db.add(user)
        db.flush()  # Get user.id before creating ledger entry
        
        # Grant signup bonus
        if SIGNUP_BONUS_CREDITS > 0:
            bonus = CreditLedger(
                user_id=user.id,
                delta=SIGNUP_BONUS_CREDITS,
                reason=SIGNUP_BONUS_REASON,
                balance_after=SIGNUP_BONUS_CREDITS,
                notes='Welcome to CitateGenie!'
            )
            db.add(bonus)
        
        db.commit()
        
        print(f"[Auth] New user registered: {email} (granted {SIGNUP_BONUS_CREDITS} bonus credits)")
        return user, None
        
    except Exception as e:
        db.rollback()
        print(f"[Auth] Registration failed for {email}: {e}")
        return None, "Registration failed. Please try again."


# =============================================================================
# USER AUTHENTICATION
# =============================================================================

def authenticate_user(email: str, password: str) -> Optional[User]:
    """
    Authenticate user with email/password.
    
    Args:
        email: User's email
        password: User's password
    
    Returns:
        User if authenticated, None otherwise
    """
    if not email or not password:
        return None
    
    email = email.strip().lower()
    
    db = get_db()
    
    try:
        user = db.query(User).filter_by(email=email).first()
        
        if not user:
            return None
        
        if not user.is_active:
            return None
        
        if not user.check_password(password):
            return None
        
        # Update last login
        user.last_login_at = datetime.utcnow()
        db.commit()
        
        return user
        
    except Exception as e:
        print(f"[Auth] Authentication error for {email}: {e}")
        return None


def login(user: User, remember: bool = False) -> bool:
    """
    Log in a user (Flask-Login wrapper).
    
    Args:
        user: User to log in
        remember: Remember login across browser sessions
    
    Returns:
        True if successful
    """
    return login_user(user, remember=remember)


def logout() -> bool:
    """
    Log out current user (Flask-Login wrapper).
    
    Returns:
        True if successful
    """
    return logout_user()


def get_current_user() -> Optional[User]:
    """
    Get currently logged-in user.
    
    Returns:
        User if logged in, None otherwise
    """
    if current_user.is_authenticated:
        return current_user
    return None


# =============================================================================
# PASSWORD MANAGEMENT
# =============================================================================

def change_password(
    user: User, 
    current_password: str, 
    new_password: str
) -> Tuple[bool, Optional[str]]:
    """
    Change user's password.
    
    Args:
        user: User changing password
        current_password: Current password for verification
        new_password: New password
    
    Returns:
        (success, error_message)
    """
    # Verify current password
    if not user.check_password(current_password):
        return False, "Current password is incorrect"
    
    # Validate new password
    valid, error = validate_password(new_password)
    if not valid:
        return False, error
    
    db = get_db()
    
    try:
        user.set_password(new_password)
        db.commit()
        return True, None
    except Exception as e:
        db.rollback()
        print(f"[Auth] Password change failed for {user.email}: {e}")
        return False, "Password change failed"


# Future: Password reset via email
def request_password_reset(email: str) -> bool:
    """
    Request password reset email.
    
    TODO: Implement with email service
    """
    raise NotImplementedError("Password reset not yet implemented")


def reset_password(token: str, new_password: str) -> Tuple[bool, Optional[str]]:
    """
    Reset password using reset token.
    
    TODO: Implement with email service
    """
    raise NotImplementedError("Password reset not yet implemented")


# =============================================================================
# ADMIN UTILITIES
# =============================================================================

def make_admin(user: User) -> bool:
    """
    Grant admin privileges to user.
    
    Args:
        user: User to make admin
    
    Returns:
        True if successful
    """
    db = get_db()
    
    try:
        user.is_admin = True
        db.commit()
        print(f"[Auth] Admin granted to: {user.email}")
        return True
    except Exception as e:
        db.rollback()
        print(f"[Auth] Failed to grant admin to {user.email}: {e}")
        return False


def revoke_admin(user: User) -> bool:
    """
    Revoke admin privileges from user.
    
    Args:
        user: User to revoke admin from
    
    Returns:
        True if successful
    """
    db = get_db()
    
    try:
        user.is_admin = False
        db.commit()
        print(f"[Auth] Admin revoked from: {user.email}")
        return True
    except Exception as e:
        db.rollback()
        print(f"[Auth] Failed to revoke admin from {user.email}: {e}")
        return False


def deactivate_user(user: User, reason: Optional[str] = None) -> bool:
    """
    Deactivate a user account.
    
    Args:
        user: User to deactivate
        reason: Optional reason for audit
    
    Returns:
        True if successful
    """
    db = get_db()
    
    try:
        user.is_active = False
        db.commit()
        print(f"[Auth] User deactivated: {user.email} (reason: {reason})")
        return True
    except Exception as e:
        db.rollback()
        print(f"[Auth] Failed to deactivate {user.email}: {e}")
        return False
