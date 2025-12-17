"""
billing/decorators.py

Decorators for billing-related route protection.

Usage:
    from billing.decorators import requires_credits, requires_admin
    
    @app.route('/api/process', methods=['POST'])
    @requires_credits
    def process_document():
        # User has credits, proceed with processing
        pass
    
    @app.route('/admin/users')
    @requires_admin
    def admin_users():
        # User is admin
        pass

Version History:
    2025-12-17: Initial implementation
"""

from functools import wraps
from flask import jsonify, request
from flask_login import current_user

from billing.ledger import has_credits, spend_credit
from billing.config import CREDITS_PER_DOCUMENT


def requires_auth(f):
    """
    Decorator that requires user to be authenticated.
    
    Returns 401 if not logged in.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({
                'success': False,
                'error': 'Authentication required',
                'code': 'AUTH_REQUIRED'
            }), 401
        return f(*args, **kwargs)
    return decorated_function


def requires_credits(amount: int = CREDITS_PER_DOCUMENT, auto_spend: bool = False):
    """
    Decorator that requires user to have sufficient credits.
    
    Args:
        amount: Credits required (default: 1)
        auto_spend: If True, automatically deduct credits on success
                    If False, caller must call spend_credit() manually
    
    Usage:
        @requires_credits()
        def process_document():
            # Requires 1 credit, doesn't auto-spend
            # Call spend_credit(current_user.id) after successful processing
            pass
        
        @requires_credits(amount=5, auto_spend=True)
        def bulk_process():
            # Requires 5 credits, auto-spends on function entry
            pass
    
    Returns:
        - 401 if not authenticated
        - 402 if insufficient credits
        - Proceeds to function if credits available
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check authentication
            if not current_user.is_authenticated:
                return jsonify({
                    'success': False,
                    'error': 'Authentication required',
                    'code': 'AUTH_REQUIRED'
                }), 401
            
            # Check credits
            if not has_credits(current_user.id, amount):
                return jsonify({
                    'success': False,
                    'error': f'Insufficient credits. You need {amount} credit(s) to perform this action.',
                    'code': 'INSUFFICIENT_CREDITS',
                    'required': amount,
                    'buy_url': '/billing/products'
                }), 402  # Payment Required
            
            # Auto-spend if configured
            if auto_spend:
                if not spend_credit(current_user.id, amount):
                    return jsonify({
                        'success': False,
                        'error': 'Failed to process payment',
                        'code': 'CREDIT_ERROR'
                    }), 500
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def requires_admin(f):
    """
    Decorator that requires user to be an admin.
    
    Returns 403 if not admin.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({
                'success': False,
                'error': 'Authentication required',
                'code': 'AUTH_REQUIRED'
            }), 401
        
        if not current_user.is_admin:
            return jsonify({
                'success': False,
                'error': 'Admin access required',
                'code': 'ADMIN_REQUIRED'
            }), 403
        
        return f(*args, **kwargs)
    return decorated_function


def optional_auth(f):
    """
    Decorator that loads user if authenticated, but doesn't require it.
    
    Useful for endpoints that work differently for logged-in vs anonymous users.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Flask-Login already handles loading current_user
        # This decorator is mainly for documentation purposes
        return f(*args, **kwargs)
    return decorated_function


# =============================================================================
# HELPER FOR MANUAL CREDIT SPENDING
# =============================================================================

def spend_user_credit(user_id: int = None, notes: str = None) -> bool:
    """
    Spend a credit for the current or specified user.
    
    Call this after successful document processing when not using auto_spend.
    
    Args:
        user_id: User ID (defaults to current_user)
        notes: Optional note (e.g., document filename)
    
    Returns:
        True if credit was spent successfully
    """
    if user_id is None:
        if not current_user.is_authenticated:
            return False
        user_id = current_user.id
    
    return spend_credit(user_id, CREDITS_PER_DOCUMENT, notes)
