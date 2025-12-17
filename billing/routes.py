"""
billing/routes.py

Flask Blueprint for billing routes.

Endpoints:
    Auth:
        POST /billing/register - Create account
        POST /billing/login - Login
        POST /billing/logout - Logout
        GET  /billing/me - Get current user info
    
    Billing:
        GET  /billing/products - List available products
        GET  /billing/balance - Get credit balance
        POST /billing/checkout - Create checkout session
        GET  /billing/success - Payment success redirect
        GET  /billing/cancel - Payment cancel redirect
        POST /billing/webhook - Stripe webhook handler
        GET  /billing/orders - Order history

Version History:
    2025-12-17: Initial implementation
"""

from flask import Blueprint, request, jsonify, redirect, url_for
from flask_login import login_required, current_user

from billing.auth import (
    register_user, authenticate_user, login, logout, get_current_user
)
from billing.service import billing_service
from billing.ledger import get_balance_fast, get_user_history
from billing.config import get_purchasable_products, CREDITS_PER_DOCUMENT


billing_bp = Blueprint('billing_bp', __name__, url_prefix='/billing')


# =============================================================================
# AUTH ROUTES
# =============================================================================

@billing_bp.route('/register', methods=['POST'])
def register():
    """
    Register a new user.
    
    Request:
        {
            "email": "user@example.com",
            "password": "securepassword",
            "name": "Optional Name"
        }
    
    Response:
        {
            "success": true,
            "user": {
                "id": 1,
                "email": "user@example.com",
                "name": "Optional Name",
                "credits": 3
            }
        }
    """
    data = request.get_json() or {}
    
    email = data.get('email', '').strip()
    password = data.get('password', '')
    name = data.get('name', '').strip()
    
    user, error = register_user(email, password, name or None)
    
    if error:
        return jsonify({
            'success': False,
            'error': error
        }), 400
    
    # Auto-login after registration
    login(user, remember=True)
    
    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'email': user.email,
            'name': user.name,
            'credits': get_balance_fast(user.id)
        }
    })


@billing_bp.route('/login', methods=['POST'])
def login_route():
    """
    Login with email/password.
    
    Request:
        {
            "email": "user@example.com",
            "password": "securepassword",
            "remember": true
        }
    
    Response:
        {
            "success": true,
            "user": {...}
        }
    """
    data = request.get_json() or {}
    
    email = data.get('email', '').strip()
    password = data.get('password', '')
    remember = data.get('remember', False)
    
    user = authenticate_user(email, password)
    
    if not user:
        return jsonify({
            'success': False,
            'error': 'Invalid email or password'
        }), 401
    
    login(user, remember=remember)
    
    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'email': user.email,
            'name': user.name,
            'credits': get_balance_fast(user.id),
            'is_admin': user.is_admin
        }
    })


@billing_bp.route('/logout', methods=['POST'])
def logout_route():
    """Logout current user."""
    logout()
    return jsonify({'success': True})


@billing_bp.route('/me', methods=['GET'])
def me():
    """
    Get current user info.
    
    Response:
        {
            "authenticated": true,
            "user": {
                "id": 1,
                "email": "user@example.com",
                "name": "Name",
                "credits": 10,
                "is_admin": false
            }
        }
    """
    user = get_current_user()
    
    if not user:
        return jsonify({
            'authenticated': False,
            'user': None
        })
    
    return jsonify({
        'authenticated': True,
        'user': {
            'id': user.id,
            'email': user.email,
            'name': user.name,
            'credits': get_balance_fast(user.id),
            'is_admin': user.is_admin,
            'total_documents': user.total_documents
        }
    })


# =============================================================================
# BILLING ROUTES
# =============================================================================

@billing_bp.route('/products', methods=['GET'])
def products():
    """
    List available products.
    
    Response:
        {
            "products": [
                {
                    "code": "credit_10",
                    "name": "10-Pack",
                    "credits": 10,
                    "price": 5.99,
                    "price_per_credit": 0.60,
                    "savings_percent": 80,
                    "badge": "Most Popular"
                },
                ...
            ]
        }
    """
    products_list = get_purchasable_products()
    
    return jsonify({
        'products': [
            {
                'code': p.code,
                'name': p.name,
                'credits': p.credits,
                'price': p.price_dollars,
                'price_cents': p.price_cents,
                'price_per_credit': round(p.price_per_credit, 2),
                'savings_percent': p.savings_percent,
                'badge': p.badge,
                'description': p.description
            }
            for p in products_list
        ]
    })


@billing_bp.route('/balance', methods=['GET'])
@login_required
def balance():
    """
    Get current user's credit balance.
    
    Response:
        {
            "credits": 10,
            "credits_per_document": 1
        }
    """
    return jsonify({
        'credits': get_balance_fast(current_user.id),
        'credits_per_document': CREDITS_PER_DOCUMENT
    })


@billing_bp.route('/checkout', methods=['POST'])
@login_required
def checkout():
    """
    Create a checkout session.
    
    Request:
        {
            "product_code": "credit_10"
        }
    
    Response:
        {
            "success": true,
            "checkout_url": "https://checkout.stripe.com/...",
            "order_id": "uuid"
        }
    """
    data = request.get_json() or {}
    product_code = data.get('product_code')
    
    if not product_code:
        return jsonify({
            'success': False,
            'error': 'product_code is required'
        }), 400
    
    # Build success/cancel URLs
    base_url = request.host_url.rstrip('/')
    success_url = f"{base_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{base_url}/billing/cancel"
    
    result = billing_service.create_checkout(
        user_id=current_user.id,
        product_code=product_code,
        success_url=success_url,
        cancel_url=cancel_url
    )
    
    if not result['success']:
        return jsonify(result), 400
    
    return jsonify(result)


@billing_bp.route('/success', methods=['GET'])
def success():
    """
    Payment success redirect.
    
    User lands here after successful Stripe checkout.
    In production, redirect to your frontend with success message.
    """
    session_id = request.args.get('session_id')
    
    # For API-only: return JSON
    if request.headers.get('Accept') == 'application/json':
        return jsonify({
            'success': True,
            'message': 'Payment successful! Credits have been added.',
            'session_id': session_id
        })
    
    # For browser: redirect to main app
    # TODO: Update this to your frontend URL
    return redirect('/?payment=success')


@billing_bp.route('/cancel', methods=['GET'])
def cancel():
    """
    Payment cancel redirect.
    
    User lands here if they cancel Stripe checkout.
    """
    if request.headers.get('Accept') == 'application/json':
        return jsonify({
            'success': False,
            'message': 'Payment cancelled'
        })
    
    return redirect('/?payment=cancelled')


@billing_bp.route('/webhook', methods=['POST'])
def webhook():
    """
    Stripe webhook handler.
    
    Stripe sends events here:
        - checkout.session.completed → Grant credits
        - charge.refunded → Revoke credits
        - payment_intent.payment_failed → Mark order failed
    
    Always returns 200 to acknowledge receipt.
    """
    payload = request.data
    signature = request.headers.get('Stripe-Signature', '')
    
    result = billing_service.handle_webhook(payload, signature)
    
    # Always return 200 to prevent Stripe retries for handled events
    # Only return 400 for signature failures
    if not result['success'] and 'Invalid signature' in result.get('message', ''):
        return jsonify(result), 400
    
    return jsonify(result), 200


@billing_bp.route('/orders', methods=['GET'])
@login_required
def orders():
    """
    Get user's order history.
    
    Query params:
        - limit: Max orders to return (default 20)
        - offset: Pagination offset (default 0)
    
    Response:
        {
            "orders": [
                {
                    "id": "uuid",
                    "product_code": "credit_10",
                    "credits": 10,
                    "amount": 5.99,
                    "status": "paid",
                    "created_at": "2025-01-01T12:00:00Z"
                },
                ...
            ]
        }
    """
    limit = min(int(request.args.get('limit', 20)), 100)
    offset = int(request.args.get('offset', 0))
    
    orders_list = billing_service.get_user_orders(
        user_id=current_user.id,
        limit=limit,
        offset=offset
    )
    
    return jsonify({
        'orders': [
            {
                'id': str(o.id),
                'product_code': o.product_code,
                'credits': o.credits_granted,
                'amount': o.amount_cents / 100,
                'currency': o.currency,
                'status': o.status,
                'created_at': o.created_at.isoformat() if o.created_at else None,
                'paid_at': o.paid_at.isoformat() if o.paid_at else None
            }
            for o in orders_list
        ]
    })


@billing_bp.route('/history', methods=['GET'])
@login_required
def history():
    """
    Get user's credit history (ledger entries).
    
    Response:
        {
            "history": [
                {
                    "id": 1,
                    "delta": 10,
                    "reason": "purchase",
                    "balance_after": 13,
                    "created_at": "2025-01-01T12:00:00Z"
                },
                ...
            ]
        }
    """
    limit = min(int(request.args.get('limit', 50)), 100)
    offset = int(request.args.get('offset', 0))
    
    entries = get_user_history(
        user_id=current_user.id,
        limit=limit,
        offset=offset
    )
    
    return jsonify({
        'history': [
            {
                'id': e.id,
                'delta': e.delta,
                'reason': e.reason,
                'balance_after': e.balance_after,
                'notes': e.notes,
                'created_at': e.created_at.isoformat() if e.created_at else None
            }
            for e in entries
        ]
    })


# =============================================================================
# HEALTH CHECK
# =============================================================================

@billing_bp.route('/health', methods=['GET'])
def health():
    """
    Health check endpoint for load balancers.
    
    Response:
        {
            "status": "healthy",
            "db": "connected"
        }
    """
    from billing.db import check_connection
    
    db_ok = check_connection()
    
    if db_ok:
        return jsonify({
            'status': 'healthy',
            'db': 'connected'
        })
    else:
        return jsonify({
            'status': 'unhealthy',
            'db': 'disconnected'
        }), 500
