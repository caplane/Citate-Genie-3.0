"""
billing/config.py

Billing configuration and product definitions.

Design principles:
    1. Products defined HERE, not in Stripe
    2. Prices in cents (avoid floating point)
    3. Margins increase with pack size (86% → 88.1%)
    4. Provider price mappings stored separately

Product Lineup (locked 2025-12-17):
    - signup_bonus: 3 free credits (no Stripe)
    - credit_1:     1 credit  @ $2.99  (86.0% margin)
    - credit_5:     5 credits @ $4.29  (86.7% margin)
    - credit_10:   10 credits @ $5.99  (87.1% margin)
    - credit_20:   20 credits @ $9.99  (88.1% margin)

Cost structure:
    - $0.03/credit usage cost
    - Stripe: 2.9% + $0.30 per transaction

Version History:
    2025-12-17: Initial implementation
"""

import os
from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum


# =============================================================================
# STRIPE CONFIGURATION
# =============================================================================

STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

# Stripe mode detection
STRIPE_TEST_MODE = STRIPE_SECRET_KEY.startswith('sk_test_')

if not STRIPE_SECRET_KEY:
    print("[Billing] WARNING: STRIPE_SECRET_KEY not set")
elif STRIPE_TEST_MODE:
    print("[Billing] Stripe running in TEST mode")
else:
    print("[Billing] Stripe running in LIVE mode")


# =============================================================================
# PRODUCT DEFINITIONS
# =============================================================================

class ProductCode(str, Enum):
    """Valid product codes."""
    SIGNUP_BONUS = 'signup_bonus'
    CREDIT_1 = 'credit_1'
    CREDIT_5 = 'credit_5'
    CREDIT_10 = 'credit_10'
    CREDIT_20 = 'credit_20'


@dataclass(frozen=True)
class Product:
    """Product definition."""
    code: str
    name: str
    credits: int
    price_cents: int
    currency: str = 'USD'
    active: bool = True
    is_free: bool = False
    description: Optional[str] = None
    badge: Optional[str] = None  # "Best Value", "Most Popular"
    
    @property
    def price_dollars(self) -> float:
        """Price in dollars for display."""
        return self.price_cents / 100
    
    @property
    def price_per_credit(self) -> float:
        """Price per credit in dollars."""
        if self.credits == 0:
            return 0.0
        return self.price_cents / 100 / self.credits
    
    @property
    def savings_percent(self) -> int:
        """Savings vs single credit purchase."""
        if self.code == ProductCode.CREDIT_1 or self.credits == 0:
            return 0
        single_price = 2.99  # Base single credit price
        would_cost = single_price * self.credits
        actual_cost = self.price_cents / 100
        savings = (would_cost - actual_cost) / would_cost * 100
        return int(savings)


# The product catalog - source of truth
PRODUCTS: Dict[str, Product] = {
    ProductCode.SIGNUP_BONUS: Product(
        code=ProductCode.SIGNUP_BONUS,
        name='Welcome Bonus',
        credits=3,
        price_cents=0,
        is_free=True,
        description='Free credits to try CitateGenie',
    ),
    ProductCode.CREDIT_1: Product(
        code=ProductCode.CREDIT_1,
        name='Try It',
        credits=1,
        price_cents=299,
        description='Process 1 document',
    ),
    ProductCode.CREDIT_5: Product(
        code=ProductCode.CREDIT_5,
        name='5-Pack',
        credits=5,
        price_cents=429,
        description='Process 5 documents',
        badge='Save 71%',
    ),
    ProductCode.CREDIT_10: Product(
        code=ProductCode.CREDIT_10,
        name='10-Pack',
        credits=10,
        price_cents=599,
        description='Process 10 documents',
        badge='Most Popular',
    ),
    ProductCode.CREDIT_20: Product(
        code=ProductCode.CREDIT_20,
        name='20-Pack',
        credits=20,
        price_cents=999,
        description='Process 20 documents',
        badge='Best Value — Save 83%',
    ),
}


def get_product(code: str) -> Optional[Product]:
    """Get product by code."""
    return PRODUCTS.get(code)


def get_purchasable_products() -> list[Product]:
    """Get products that can be purchased (excludes free)."""
    return [p for p in PRODUCTS.values() if not p.is_free and p.active]


def get_all_products() -> list[Product]:
    """Get all products including free."""
    return list(PRODUCTS.values())


# =============================================================================
# PROVIDER PRICE MAPPINGS
# =============================================================================

# Map our product codes to Stripe price IDs
# You'll fill these in after creating products in Stripe dashboard
STRIPE_PRICE_IDS: Dict[str, str] = {
    # ProductCode.CREDIT_1: 'price_xxx',    # Create in Stripe, paste here
    # ProductCode.CREDIT_5: 'price_xxx',
    # ProductCode.CREDIT_10: 'price_xxx',
    # ProductCode.CREDIT_20: 'price_xxx',
}

# For future providers
PAYPAL_PRICE_IDS: Dict[str, str] = {}
ADYEN_PRICE_IDS: Dict[str, str] = {}


def get_stripe_price_id(product_code: str) -> Optional[str]:
    """Get Stripe price ID for a product."""
    return STRIPE_PRICE_IDS.get(product_code)


# =============================================================================
# BUSINESS RULES
# =============================================================================

# Credits required per document
CREDITS_PER_DOCUMENT = 1

# Signup bonus
SIGNUP_BONUS_CREDITS = 3
SIGNUP_BONUS_REASON = 'signup_bonus'

# Session/order expiration
CHECKOUT_SESSION_EXPIRY_MINUTES = 30
ORDER_PENDING_EXPIRY_HOURS = 24

# Rate limiting
MAX_PURCHASES_PER_DAY = 10
MAX_CREDITS_BALANCE = 1000  # Prevent abuse


# =============================================================================
# COST TRACKING (for your margin calculations)
# =============================================================================

COST_PER_CREDIT_CENTS = 3  # $0.03 per document processed

STRIPE_PERCENTAGE_FEE = 0.029  # 2.9%
STRIPE_FIXED_FEE_CENTS = 30    # $0.30


def calculate_margin(product: Product) -> dict:
    """
    Calculate margin for a product.
    
    Returns:
        {
            'revenue_cents': 999,
            'stripe_fee_cents': 59,
            'usage_cost_cents': 60,
            'net_profit_cents': 880,
            'margin_percent': 88.1
        }
    """
    if product.is_free:
        return {
            'revenue_cents': 0,
            'stripe_fee_cents': 0,
            'usage_cost_cents': product.credits * COST_PER_CREDIT_CENTS,
            'net_profit_cents': -(product.credits * COST_PER_CREDIT_CENTS),
            'margin_percent': 0.0
        }
    
    revenue = product.price_cents
    stripe_fee = int(revenue * STRIPE_PERCENTAGE_FEE) + STRIPE_FIXED_FEE_CENTS
    usage_cost = product.credits * COST_PER_CREDIT_CENTS
    net_profit = revenue - stripe_fee - usage_cost
    margin = (net_profit / revenue) * 100 if revenue > 0 else 0
    
    return {
        'revenue_cents': revenue,
        'stripe_fee_cents': stripe_fee,
        'usage_cost_cents': usage_cost,
        'net_profit_cents': net_profit,
        'margin_percent': round(margin, 1)
    }


def print_margin_report():
    """Print margin report for all products."""
    print("\n" + "=" * 70)
    print("CITATEGENIE PRODUCT MARGIN REPORT")
    print("=" * 70)
    print(f"{'Product':<15} {'Price':>8} {'Credits':>8} {'Stripe':>8} {'Usage':>8} {'Net':>8} {'Margin':>8}")
    print("-" * 70)
    
    for product in get_all_products():
        m = calculate_margin(product)
        print(
            f"{product.code:<15} "
            f"${product.price_cents/100:>7.2f} "
            f"{product.credits:>8} "
            f"${m['stripe_fee_cents']/100:>7.2f} "
            f"${m['usage_cost_cents']/100:>7.2f} "
            f"${m['net_profit_cents']/100:>7.2f} "
            f"{m['margin_percent']:>7.1f}%"
        )
    print("=" * 70 + "\n")


if __name__ == '__main__':
    # Run this file directly to see margin report
    print_margin_report()
