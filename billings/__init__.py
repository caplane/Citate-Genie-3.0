"""
billing/__init__.py

Billing module for CitateGenie.

Provider-agnostic payment system with:
    - Email/password authentication
    - Credit-based billing
    - Stripe integration (swappable)
    - Audit trail via ledger

Quick Start:
    from billing import init_billing, billing_bp, requires_credits
    
    # In Flask app:
    app = Flask(__name__)
    init_billing(app)
    app.register_blueprint(billing_bp)
    
    # Protect endpoints:
    @app.route('/api/process', methods=['POST'])
    @requires_credits()
    def process_document():
        # Process document
        spend_user_credit(notes='document.docx')
        return jsonify({'success': True})

Version History:
    2025-12-17: Initial implementation
"""

from billing.db import init_db, get_db, create_all_tables, check_connection
from billing.auth import init_auth
from billing.routes import billing_bp
from billing.service import billing_service
from billing.ledger import (
    get_balance, get_balance_fast, has_credits,
    grant_credits, spend_credit, refund_credits,
    admin_grant, admin_revoke
)
from billing.decorators import (
    requires_auth, requires_credits, requires_admin,
    spend_user_credit
)
from billing.config import (
    PRODUCTS, get_product, get_purchasable_products,
    CREDITS_PER_DOCUMENT, SIGNUP_BONUS_CREDITS
)


def init_billing(app):
    """
    Initialize the billing system for a Flask app.
    
    Call this during app startup:
        app = Flask(__name__)
        init_billing(app)
        app.register_blueprint(billing_bp)
    
    This initializes:
        - Database connection
        - Flask-Login authentication
        - Session cleanup on request teardown
    """
    init_db(app)
    init_auth(app)
    print("[Billing] Billing system initialized")


__all__ = [
    # Initialization
    'init_billing',
    'init_db',
    'init_auth',
    'create_all_tables',
    'check_connection',
    
    # Database
    'get_db',
    
    # Routes
    'billing_bp',
    
    # Service
    'billing_service',
    
    # Ledger operations
    'get_balance',
    'get_balance_fast',
    'has_credits',
    'grant_credits',
    'spend_credit',
    'refund_credits',
    'admin_grant',
    'admin_revoke',
    
    # Decorators
    'requires_auth',
    'requires_credits',
    'requires_admin',
    'spend_user_credit',
    
    # Config
    'PRODUCTS',
    'get_product',
    'get_purchasable_products',
    'CREDITS_PER_DOCUMENT',
    'SIGNUP_BONUS_CREDITS',
]
