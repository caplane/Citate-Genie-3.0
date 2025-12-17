"""
billing/ledger.py

Credit ledger operations for CitateGenie.

The ledger is the source of truth for credit balances:
    - Balance = SUM(delta) for a user
    - Every change is recorded (audit trail)
    - Supports disputes, refunds, compliance

Operations:
    - get_balance(user_id) -> int
    - grant_credits(user_id, amount, reason, ...) -> CreditLedger
    - spend_credit(user_id) -> bool
    - refund_credits(user_id, order_id) -> CreditLedger

Design principles:
    1. Never update credits directly - always use ledger entries
    2. Every entry records balance_after for fast reads
    3. All admin actions record who did it

Version History:
    2025-12-17: Initial implementation
"""

from typing import Optional
from datetime import datetime

from sqlalchemy import func

from billing.db import get_db
from billing.models import User, CreditLedger, CreditReason, Order, OrderStatus
from billing.config import CREDITS_PER_DOCUMENT, MAX_CREDITS_BALANCE


# =============================================================================
# BALANCE QUERIES
# =============================================================================

def get_balance(user_id: int) -> int:
    """
    Get current credit balance for a user.
    
    Args:
        user_id: User's ID
    
    Returns:
        Current balance (0 if no entries)
    """
    db = get_db()
    
    # Sum all deltas for this user
    result = db.query(func.sum(CreditLedger.delta)).filter(
        CreditLedger.user_id == user_id
    ).scalar()
    
    return result or 0


def get_balance_fast(user_id: int) -> int:
    """
    Get balance from most recent ledger entry (faster for display).
    
    Falls back to full calculation if no entries exist.
    
    Args:
        user_id: User's ID
    
    Returns:
        Current balance
    """
    db = get_db()
    
    # Get most recent entry
    entry = db.query(CreditLedger).filter(
        CreditLedger.user_id == user_id
    ).order_by(CreditLedger.created_at.desc()).first()
    
    if entry and entry.balance_after is not None:
        return entry.balance_after
    
    # Fallback to full calculation
    return get_balance(user_id)


def has_credits(user_id: int, required: int = CREDITS_PER_DOCUMENT) -> bool:
    """
    Check if user has enough credits.
    
    Args:
        user_id: User's ID
        required: Credits needed (default: 1 document)
    
    Returns:
        True if balance >= required
    """
    return get_balance_fast(user_id) >= required


# =============================================================================
# CREDIT OPERATIONS
# =============================================================================

def grant_credits(
    user_id: int,
    amount: int,
    reason: str,
    order_id: Optional[str] = None,
    notes: Optional[str] = None,
    created_by: Optional[int] = None
) -> Optional[CreditLedger]:
    """
    Grant credits to a user.
    
    Args:
        user_id: User to grant credits to
        amount: Number of credits (positive)
        reason: Reason code (CreditReason.*)
        order_id: Associated order ID (for purchases)
        notes: Optional notes
        created_by: Admin user ID (for admin grants)
    
    Returns:
        CreditLedger entry on success, None on failure
    """
    if amount <= 0:
        print(f"[Ledger] Invalid grant amount: {amount}")
        return None
    
    db = get_db()
    
    try:
        # Get current balance
        current_balance = get_balance(user_id)
        new_balance = current_balance + amount
        
        # Check max balance (prevent abuse)
        if new_balance > MAX_CREDITS_BALANCE:
            print(f"[Ledger] Max balance exceeded for user {user_id}: {new_balance}")
            return None
        
        # Create ledger entry
        entry = CreditLedger(
            user_id=user_id,
            delta=amount,
            reason=reason,
            order_id=order_id,
            balance_after=new_balance,
            notes=notes,
            created_by=created_by
        )
        
        db.add(entry)
        db.commit()
        
        print(f"[Ledger] Granted {amount} credits to user {user_id} ({reason}). Balance: {new_balance}")
        return entry
        
    except Exception as e:
        db.rollback()
        print(f"[Ledger] Failed to grant credits: {e}")
        return None


def spend_credit(
    user_id: int,
    amount: int = CREDITS_PER_DOCUMENT,
    notes: Optional[str] = None
) -> bool:
    """
    Spend credits for document processing.
    
    Args:
        user_id: User spending credits
        amount: Credits to spend (default: 1)
        notes: Optional notes (e.g., document name)
    
    Returns:
        True if successful, False if insufficient balance
    """
    if amount <= 0:
        return False
    
    db = get_db()
    
    try:
        # Check balance
        current_balance = get_balance(user_id)
        
        if current_balance < amount:
            print(f"[Ledger] Insufficient balance for user {user_id}: {current_balance} < {amount}")
            return False
        
        new_balance = current_balance - amount
        
        # Create ledger entry
        entry = CreditLedger(
            user_id=user_id,
            delta=-amount,
            reason=CreditReason.USAGE,
            balance_after=new_balance,
            notes=notes
        )
        
        db.add(entry)
        
        # Update user's document count
        user = db.query(User).get(user_id)
        if user:
            user.total_documents = (user.total_documents or 0) + 1
        
        db.commit()
        
        print(f"[Ledger] Spent {amount} credit for user {user_id}. Balance: {new_balance}")
        return True
        
    except Exception as e:
        db.rollback()
        print(f"[Ledger] Failed to spend credit: {e}")
        return False


def refund_credits(
    user_id: int,
    order_id: str,
    notes: Optional[str] = None,
    created_by: Optional[int] = None
) -> Optional[CreditLedger]:
    """
    Refund credits for an order.
    
    Args:
        user_id: User to refund
        order_id: Order being refunded
        notes: Optional notes
        created_by: Admin user ID
    
    Returns:
        CreditLedger entry on success, None on failure
    """
    db = get_db()
    
    try:
        # Find the original purchase entry
        original = db.query(CreditLedger).filter(
            CreditLedger.user_id == user_id,
            CreditLedger.order_id == order_id,
            CreditLedger.reason == CreditReason.PURCHASE
        ).first()
        
        if not original:
            print(f"[Ledger] No purchase found for order {order_id}")
            return None
        
        # Check if already refunded
        existing_refund = db.query(CreditLedger).filter(
            CreditLedger.user_id == user_id,
            CreditLedger.order_id == order_id,
            CreditLedger.reason == CreditReason.REFUND
        ).first()
        
        if existing_refund:
            print(f"[Ledger] Order {order_id} already refunded")
            return existing_refund
        
        # Calculate refund amount (negative of original grant)
        refund_amount = -original.delta  # This will be negative
        
        current_balance = get_balance(user_id)
        new_balance = current_balance + refund_amount  # Subtracting credits
        
        # Create refund entry
        entry = CreditLedger(
            user_id=user_id,
            delta=refund_amount,
            reason=CreditReason.REFUND,
            order_id=order_id,
            balance_after=new_balance,
            notes=notes or f"Refund for order {order_id}",
            created_by=created_by
        )
        
        db.add(entry)
        db.commit()
        
        print(f"[Ledger] Refunded {-refund_amount} credits for user {user_id}. Balance: {new_balance}")
        return entry
        
    except Exception as e:
        db.rollback()
        print(f"[Ledger] Failed to refund credits: {e}")
        return None


# =============================================================================
# ADMIN OPERATIONS
# =============================================================================

def admin_grant(
    user_id: int,
    amount: int,
    notes: str,
    admin_user_id: int
) -> Optional[CreditLedger]:
    """
    Admin grant of credits (for support, promos, etc.).
    
    Args:
        user_id: User to grant credits to
        amount: Number of credits
        notes: Required explanation
        admin_user_id: Admin making the grant
    
    Returns:
        CreditLedger entry on success
    """
    return grant_credits(
        user_id=user_id,
        amount=amount,
        reason=CreditReason.ADMIN_GRANT,
        notes=notes,
        created_by=admin_user_id
    )


def admin_revoke(
    user_id: int,
    amount: int,
    notes: str,
    admin_user_id: int
) -> Optional[CreditLedger]:
    """
    Admin revoke of credits (for abuse, etc.).
    
    Args:
        user_id: User to revoke credits from
        amount: Number of credits (positive number)
        notes: Required explanation
        admin_user_id: Admin making the revoke
    
    Returns:
        CreditLedger entry on success
    """
    db = get_db()
    
    try:
        current_balance = get_balance(user_id)
        new_balance = max(0, current_balance - amount)  # Don't go negative
        actual_revoke = current_balance - new_balance
        
        if actual_revoke <= 0:
            print(f"[Ledger] No credits to revoke for user {user_id}")
            return None
        
        entry = CreditLedger(
            user_id=user_id,
            delta=-actual_revoke,
            reason=CreditReason.ADMIN_REVOKE,
            balance_after=new_balance,
            notes=notes,
            created_by=admin_user_id
        )
        
        db.add(entry)
        db.commit()
        
        print(f"[Ledger] Admin revoked {actual_revoke} credits from user {user_id}. Balance: {new_balance}")
        return entry
        
    except Exception as e:
        db.rollback()
        print(f"[Ledger] Failed to revoke credits: {e}")
        return None


# =============================================================================
# LEDGER QUERIES (for admin dashboard)
# =============================================================================

def get_user_history(
    user_id: int,
    limit: int = 50,
    offset: int = 0
) -> list:
    """
    Get credit history for a user.
    
    Args:
        user_id: User's ID
        limit: Max entries to return
        offset: Pagination offset
    
    Returns:
        List of CreditLedger entries
    """
    db = get_db()
    
    return db.query(CreditLedger).filter(
        CreditLedger.user_id == user_id
    ).order_by(
        CreditLedger.created_at.desc()
    ).limit(limit).offset(offset).all()


def get_recent_activity(limit: int = 100) -> list:
    """
    Get recent credit activity across all users (for admin).
    
    Args:
        limit: Max entries to return
    
    Returns:
        List of CreditLedger entries with user info
    """
    db = get_db()
    
    return db.query(CreditLedger).order_by(
        CreditLedger.created_at.desc()
    ).limit(limit).all()


def get_stats() -> dict:
    """
    Get credit statistics (for admin dashboard).
    
    Returns:
        {
            'total_credits_granted': int,
            'total_credits_spent': int,
            'total_credits_refunded': int,
            'active_balance': int,
            'users_with_credits': int
        }
    """
    db = get_db()
    
    # Total granted (purchases + admin + signup)
    granted = db.query(func.sum(CreditLedger.delta)).filter(
        CreditLedger.delta > 0
    ).scalar() or 0
    
    # Total spent
    spent_result = db.query(func.sum(CreditLedger.delta)).filter(
        CreditLedger.reason == CreditReason.USAGE
    ).scalar() or 0
    spent = abs(spent_result)
    
    # Total refunded
    refunded_result = db.query(func.sum(CreditLedger.delta)).filter(
        CreditLedger.reason == CreditReason.REFUND
    ).scalar() or 0
    refunded = abs(refunded_result)
    
    # Active balance (sum of all user balances)
    active = db.query(func.sum(CreditLedger.delta)).scalar() or 0
    
    # Users with positive balance
    users_with_credits = db.query(CreditLedger.user_id).group_by(
        CreditLedger.user_id
    ).having(func.sum(CreditLedger.delta) > 0).count()
    
    return {
        'total_credits_granted': granted,
        'total_credits_spent': spent,
        'total_credits_refunded': refunded,
        'active_balance': active,
        'users_with_credits': users_with_credits
    }
