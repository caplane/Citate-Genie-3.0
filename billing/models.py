"""
billing/models.py

SQLAlchemy models for the billing system.

Tables:
    - users: User accounts with email/password auth
    - orders: Purchase records (provider-agnostic)
    - payment_events: Webhook event log for idempotency
    - credit_ledger: Credit transactions (+purchase, -usage, etc.)
    - sessions: Database-backed sessions for Fargate compatibility
    - provider_price_map: Maps our products to provider-specific IDs

Design principles:
    1. Provider-agnostic: 'provider' + 'provider_ref' fields, not 'stripe_xxx'
    2. Idempotency: Unique constraints prevent double-processing
    3. Audit trail: Ledger records every credit change
    4. UUID order IDs: We control IDs, not Stripe

Version History:
    2025-12-17: Initial implementation
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Text, 
    ForeignKey, Numeric, Index, UniqueConstraint, event
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

import bcrypt


Base = declarative_base()


# =============================================================================
# USER MODEL
# =============================================================================

class User(Base):
    """
    User account with email/password authentication.
    
    Future: Add external_id for SSO providers (Clerk, Auth0)
    """
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    
    # Authentication
    email = Column(String(500), unique=True, nullable=False, index=True)
    password_hash = Column(String(200), nullable=False)
    
    # Profile
    name = Column(String(200))
    
    # Status
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    email_verified = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login_at = Column(DateTime(timezone=True))
    
    # Stats (denormalized for fast display)
    total_documents = Column(Integer, default=0)
    
    # Relationships
    orders = relationship('Order', back_populates='user')
    credit_entries = relationship('CreditLedger', back_populates='user', foreign_keys='[CreditLedger.user_id]')
    
    # Password hashing
    def set_password(self, password: str):
        """Hash and store password."""
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    def check_password(self, password: str) -> bool:
        """Verify password against hash."""
        return bcrypt.checkpw(
            password.encode('utf-8'), 
            self.password_hash.encode('utf-8')
        )
    
    # Flask-Login integration
    @property
    def is_authenticated(self):
        return True
    
    @property
    def is_anonymous(self):
        return False
    
    def get_id(self):
        return str(self.id)
    
    def __repr__(self):
        return f'<User {self.email}>'


# =============================================================================
# ORDER MODEL
# =============================================================================

class OrderStatus:
    """Order status constants."""
    CREATED = 'created'      # Order created, awaiting payment
    PENDING = 'pending'      # Payment initiated
    PAID = 'paid'            # Payment confirmed
    FAILED = 'failed'        # Payment failed
    REFUNDED = 'refunded'    # Full refund processed
    EXPIRED = 'expired'      # Checkout session expired


class Order(Base):
    """
    Purchase order record.
    
    Key design:
    - UUID id is OURS, passed to Stripe as client_reference_id
    - provider_ref stores Stripe's session/payment ID
    - Lookup flow: webhook → provider_ref → order → user → grant credits
    """
    __tablename__ = 'orders'
    
    # Our ID (UUID) - this is what we pass to Stripe
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # User who placed order
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    
    # Product purchased (our product code)
    product_code = Column(String(50), nullable=False)
    credits_granted = Column(Integer, nullable=False)
    
    # Payment provider info (provider-agnostic)
    provider = Column(String(50), nullable=False)  # 'stripe', 'paypal', 'manual'
    provider_ref = Column(String(200), index=True)  # Stripe checkout session ID
    provider_payment_id = Column(String(200))       # Stripe payment intent ID
    
    # Status
    status = Column(String(50), default=OrderStatus.CREATED, index=True)
    
    # Money
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(3), default='USD')
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    paid_at = Column(DateTime(timezone=True))
    
    # Relationships
    user = relationship('User', back_populates='orders')
    credit_entry = relationship('CreditLedger', back_populates='order', uselist=False)
    
    def __repr__(self):
        return f'<Order {self.id} {self.status}>'


# Index for webhook lookups: provider + provider_ref
Index('idx_orders_provider_ref', Order.provider, Order.provider_ref)


# =============================================================================
# PAYMENT EVENTS MODEL (Webhook Idempotency)
# =============================================================================

class PaymentEvent(Base):
    """
    Webhook event log for idempotency.
    
    Before processing any webhook:
    1. Try to insert into this table
    2. If duplicate (unique constraint), return 200 and do nothing
    3. If new, process the event
    
    This guarantees we never double-grant credits.
    """
    __tablename__ = 'payment_events'
    
    id = Column(Integer, primary_key=True)
    
    # Provider info
    provider = Column(String(50), nullable=False)
    provider_event_id = Column(String(200), nullable=False)  # Stripe event.id
    
    # Event details
    event_type = Column(String(100))  # 'checkout.session.completed'
    payload_json = Column(JSONB)
    
    # Processing status
    processed = Column(Boolean, default=False)
    error_message = Column(Text)
    
    # Timestamps
    received_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True))
    
    # Unique constraint for idempotency
    __table_args__ = (
        UniqueConstraint('provider', 'provider_event_id', name='uq_payment_events_provider_event'),
    )
    
    def __repr__(self):
        return f'<PaymentEvent {self.provider}:{self.provider_event_id}>'


# =============================================================================
# CREDIT LEDGER MODEL
# =============================================================================

class CreditReason:
    """Credit transaction reason constants."""
    SIGNUP_BONUS = 'signup_bonus'
    PURCHASE = 'purchase'
    USAGE = 'usage'
    REFUND = 'refund'
    ADMIN_GRANT = 'admin_grant'
    ADMIN_REVOKE = 'admin_revoke'
    PROMO = 'promo'
    EXPIRATION = 'expiration'


class CreditLedger(Base):
    """
    Credit transaction ledger.
    
    This is the source of truth for credit balances:
        SELECT SUM(delta) FROM credit_ledger WHERE user_id = ?
    
    Every credit change is recorded:
        +3  signup_bonus
        +10 purchase (order_id=xxx)
        -1  usage
        -10 refund (order_id=xxx)
    
    Audit trail for disputes, compliance.
    """
    __tablename__ = 'credit_ledger'
    
    id = Column(Integer, primary_key=True)
    
    # Who
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    
    # What
    delta = Column(Integer, nullable=False)  # Positive = grant, negative = spend
    reason = Column(String(100), nullable=False)
    
    # Related order (for purchases/refunds)
    order_id = Column(UUID(as_uuid=True), ForeignKey('orders.id'))
    
    # Balance after this transaction (denormalized for fast reads)
    balance_after = Column(Integer)
    
    # Notes (for admin grants, promos, etc.)
    notes = Column(Text)
    
    # Who made this entry (for admin actions)
    created_by = Column(Integer, ForeignKey('users.id'))
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship('User', back_populates='credit_entries', foreign_keys=[user_id])
    order = relationship('Order', back_populates='credit_entry')
    
    def __repr__(self):
        sign = '+' if self.delta > 0 else ''
        return f'<CreditLedger user={self.user_id} {sign}{self.delta} ({self.reason})>'


# Index for balance calculation
Index('idx_credit_ledger_user_created', CreditLedger.user_id, CreditLedger.created_at)


# =============================================================================
# SESSION MODEL (Database-backed sessions for Fargate)
# =============================================================================

class AppSession(Base):
    """
    Database-backed session storage.
    
    Replaces file-based SessionManager for Fargate compatibility:
    - Multiple containers can share sessions via database
    - No persistent filesystem required
    - Sessions survive container restarts
    
    Stores session data as JSONB (document data, citations, etc.)
    """
    __tablename__ = 'app_sessions'
    
    id = Column(String(100), primary_key=True)  # Session ID (UUID string)
    
    # Optional user association
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    
    # Session data (your document, citations, etc.)
    data = Column(JSONB, default={})
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    expires_at = Column(DateTime(timezone=True))
    
    @classmethod
    def default_expiry(cls) -> datetime:
        """Default session expiry: 4 hours from now."""
        return datetime.utcnow() + timedelta(hours=4)
    
    def is_expired(self) -> bool:
        """Check if session has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at
    
    def __repr__(self):
        return f'<AppSession {self.id[:8]}...>'


# Index for cleanup queries
Index('idx_app_sessions_expires', AppSession.expires_at)


# =============================================================================
# PROVIDER PRICE MAP MODEL
# =============================================================================

class ProviderPriceMap(Base):
    """
    Maps our product codes to provider-specific price IDs.
    
    Example:
        provider='stripe', product_code='credit_10', provider_price_id='price_abc123'
    
    Allows different price IDs per provider without code changes.
    Admin dashboard can manage these.
    """
    __tablename__ = 'provider_price_map'
    
    id = Column(Integer, primary_key=True)
    
    provider = Column(String(50), nullable=False)
    product_code = Column(String(50), nullable=False)
    provider_price_id = Column(String(200), nullable=False)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint('provider', 'product_code', name='uq_provider_price_map'),
    )
    
    def __repr__(self):
        return f'<ProviderPriceMap {self.provider}:{self.product_code}>'


# =============================================================================
# USER DISCOUNTS MODEL (for admin dashboard)
# =============================================================================

class UserDiscount(Base):
    """
    Per-user discount codes and special pricing.
    
    Admin can grant specific users discounts:
    - Percentage off
    - Fixed amount off
    - Free credits
    - Specific product pricing
    """
    __tablename__ = 'user_discounts'
    
    id = Column(Integer, primary_key=True)
    
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    
    # Discount type
    discount_type = Column(String(50), nullable=False)  # 'percent', 'fixed', 'free_credits'
    discount_value = Column(Integer, nullable=False)    # Percent (10 = 10%) or cents or credits
    
    # Scope
    product_code = Column(String(50))  # Null = applies to all products
    
    # Usage limits
    max_uses = Column(Integer)  # Null = unlimited
    times_used = Column(Integer, default=0)
    
    # Validity
    valid_from = Column(DateTime(timezone=True), server_default=func.now())
    valid_until = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    
    # Notes
    notes = Column(Text)
    created_by = Column(Integer, ForeignKey('users.id'))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def is_valid(self) -> bool:
        """Check if discount is currently valid."""
        if not self.is_active:
            return False
        now = datetime.utcnow()
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        if self.max_uses and self.times_used >= self.max_uses:
            return False
        return True
    
    def __repr__(self):
        return f'<UserDiscount user={self.user_id} {self.discount_type}={self.discount_value}>'
