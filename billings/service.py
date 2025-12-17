"""
billing/service.py

BillingService - the main interface for payment operations.

Your app calls BillingService, never the payment provider directly.
This enables provider switching without application code changes.

Usage:
    from billing.service import billing_service
    
    # Create checkout
    result = billing_service.create_checkout(
        user_id=user.id,
        product_code='credit_10',
        success_url='https://yourapp.com/billing/success',
        cancel_url='https://yourapp.com/billing/cancel'
    )
    if result['success']:
        redirect(result['checkout_url'])
    
    # Handle webhook (in route)
    billing_service.handle_webhook(request.data, request.headers.get('Stripe-Signature'))

Version History:
    2025-12-17: Initial implementation
"""

import uuid
from typing import Optional, Dict, Any
from datetime import datetime

from billing.db import get_db
from billing.models import (
    User, Order, OrderStatus, PaymentEvent, CreditReason
)
from billing.config import get_product, get_purchasable_products
from billing.ledger import grant_credits, refund_credits, get_balance_fast
from billing.providers import get_stripe_provider, PaymentProvider


class BillingService:
    """
    Main billing service - coordinates payments, orders, and credits.
    
    Design:
        1. App calls BillingService methods
        2. BillingService creates internal records (Order)
        3. BillingService delegates to PaymentProvider
        4. Webhooks update Order status and trigger credit grants
    """
    
    def __init__(self, provider: Optional[PaymentProvider] = None):
        """
        Initialize with a payment provider.
        
        Args:
            provider: PaymentProvider instance (defaults to Stripe)
        """
        self._provider = provider
    
    @property
    def provider(self) -> PaymentProvider:
        """Get active payment provider."""
        if self._provider is None:
            self._provider = get_stripe_provider()
        return self._provider
    
    def set_provider(self, provider: PaymentProvider):
        """
        Switch payment provider.
        
        Future use: Switch from Stripe to PayPal, etc.
        """
        self._provider = provider
        print(f"[Billing] Provider switched to: {provider.name}")
    
    # =========================================================================
    # CHECKOUT
    # =========================================================================
    
    def create_checkout(
        self,
        user_id: int,
        product_code: str,
        success_url: str,
        cancel_url: str
    ) -> Dict[str, Any]:
        """
        Create a checkout session for purchasing credits.
        
        Flow:
            1. Validate product
            2. Create Order (status=created)
            3. Create provider checkout session
            4. Update Order with provider_ref
            5. Return checkout URL
        
        Args:
            user_id: User making purchase
            product_code: Product to purchase (e.g., 'credit_10')
            success_url: Redirect after successful payment
            cancel_url: Redirect if user cancels
        
        Returns:
            {
                'success': bool,
                'checkout_url': str,  # Redirect user here
                'order_id': str,      # Our order ID
                'error': str          # If failed
            }
        """
        # Validate product
        product = get_product(product_code)
        if not product:
            return {
                'success': False,
                'error': f'Invalid product: {product_code}'
            }
        
        if product.is_free:
            return {
                'success': False,
                'error': 'Cannot purchase free products'
            }
        
        db = get_db()
        
        try:
            # Get user
            user = db.query(User).get(user_id)
            if not user:
                return {
                    'success': False,
                    'error': 'User not found'
                }
            
            # Create order
            order = Order(
                user_id=user_id,
                product_code=product_code,
                credits_granted=product.credits,
                provider=self.provider.name,
                status=OrderStatus.CREATED,
                amount_cents=product.price_cents,
                currency=product.currency
            )
            db.add(order)
            db.commit()
            
            # Create provider checkout session
            result = self.provider.create_checkout_session(
                order=order,
                success_url=success_url,
                cancel_url=cancel_url,
                customer_email=user.email
            )
            
            if not result.success:
                # Mark order as failed
                order.status = OrderStatus.FAILED
                db.commit()
                return {
                    'success': False,
                    'error': result.error or 'Checkout creation failed'
                }
            
            # Update order with provider session ID
            order.provider_ref = result.provider_session_id
            order.status = OrderStatus.PENDING
            db.commit()
            
            print(f"[Billing] Checkout created for user {user_id}, order {order.id}, product {product_code}")
            
            return {
                'success': True,
                'checkout_url': result.checkout_url,
                'order_id': str(order.id)
            }
            
        except Exception as e:
            db.rollback()
            print(f"[Billing] Checkout error: {e}")
            return {
                'success': False,
                'error': 'Failed to create checkout'
            }
    
    # =========================================================================
    # WEBHOOKS
    # =========================================================================
    
    def handle_webhook(
        self,
        payload: bytes,
        signature: str
    ) -> Dict[str, Any]:
        """
        Handle incoming webhook from payment provider.
        
        Flow:
            1. Verify signature
            2. Check idempotency (have we seen this event?)
            3. Route to appropriate handler based on event type
            4. Return 200 (always, to prevent retries for handled events)
        
        Args:
            payload: Raw request body
            signature: Provider signature header
        
        Returns:
            {
                'success': bool,
                'message': str,
                'event_id': str
            }
        """
        # Verify signature
        is_valid, event_data = self.provider.verify_webhook(payload, signature)
        
        if not is_valid:
            print("[Billing] Webhook signature verification failed")
            return {
                'success': False,
                'message': 'Invalid signature'
            }
        
        event_id = event_data.get('id')
        event_type = event_data.get('type')
        
        print(f"[Billing] Webhook received: {event_type} ({event_id})")
        
        # Idempotency check
        db = get_db()
        
        try:
            # Try to insert event (unique constraint will catch duplicates)
            payment_event = PaymentEvent(
                provider=self.provider.name,
                provider_event_id=event_id,
                event_type=event_type,
                payload_json=event_data
            )
            db.add(payment_event)
            db.commit()
            
        except Exception as e:
            # Likely duplicate - check if it was already processed
            db.rollback()
            
            existing = db.query(PaymentEvent).filter_by(
                provider=self.provider.name,
                provider_event_id=event_id
            ).first()
            
            if existing:
                print(f"[Billing] Duplicate webhook ignored: {event_id}")
                return {
                    'success': True,
                    'message': 'Already processed',
                    'event_id': event_id
                }
            else:
                print(f"[Billing] Webhook error: {e}")
                return {
                    'success': False,
                    'message': 'Database error'
                }
        
        # Route to handler
        try:
            if self.provider.is_checkout_completed(event_type):
                self._handle_checkout_completed(event_data, payment_event)
            
            elif self.provider.is_payment_failed(event_type):
                self._handle_payment_failed(event_data, payment_event)
            
            elif self.provider.is_refund(event_type):
                self._handle_refund(event_data, payment_event)
            
            else:
                print(f"[Billing] Unhandled event type: {event_type}")
            
            # Mark event as processed
            payment_event.processed = True
            payment_event.processed_at = datetime.utcnow()
            db.commit()
            
            return {
                'success': True,
                'message': f'Processed {event_type}',
                'event_id': event_id
            }
            
        except Exception as e:
            payment_event.error_message = str(e)
            db.commit()
            print(f"[Billing] Webhook handler error: {e}")
            return {
                'success': False,
                'message': str(e),
                'event_id': event_id
            }
    
    def _handle_checkout_completed(self, event_data: dict, payment_event: PaymentEvent):
        """Handle successful checkout - grant credits."""
        db = get_db()
        
        # Parse event
        webhook_event = self.provider.parse_checkout_completed(event_data)
        if not webhook_event or not webhook_event.order_id:
            print("[Billing] Could not parse checkout event")
            return
        
        # Find order
        order = db.query(Order).filter_by(id=webhook_event.order_id).first()
        if not order:
            print(f"[Billing] Order not found: {webhook_event.order_id}")
            return
        
        # Check if already paid (idempotency)
        if order.status == OrderStatus.PAID:
            print(f"[Billing] Order already paid: {order.id}")
            return
        
        # Update order
        order.status = OrderStatus.PAID
        order.paid_at = datetime.utcnow()
        order.provider_payment_id = webhook_event.payment_id
        
        # Grant credits
        entry = grant_credits(
            user_id=order.user_id,
            amount=order.credits_granted,
            reason=CreditReason.PURCHASE,
            order_id=str(order.id),
            notes=f"Purchase: {order.product_code}"
        )
        
        if entry:
            print(f"[Billing] Credits granted: {order.credits_granted} to user {order.user_id}")
        else:
            print(f"[Billing] WARNING: Failed to grant credits for order {order.id}")
        
        db.commit()
    
    def _handle_payment_failed(self, event_data: dict, payment_event: PaymentEvent):
        """Handle failed payment."""
        db = get_db()
        
        webhook_event = self.provider.parse_payment_failed(event_data)
        if not webhook_event or not webhook_event.order_id:
            print("[Billing] Could not parse payment failed event")
            return
        
        order = db.query(Order).filter_by(id=webhook_event.order_id).first()
        if not order:
            print(f"[Billing] Order not found: {webhook_event.order_id}")
            return
        
        order.status = OrderStatus.FAILED
        db.commit()
        
        print(f"[Billing] Order marked failed: {order.id}")
    
    def _handle_refund(self, event_data: dict, payment_event: PaymentEvent):
        """Handle refund - revoke credits."""
        db = get_db()
        
        webhook_event = self.provider.parse_refund(event_data)
        if not webhook_event or not webhook_event.order_id:
            print("[Billing] Could not parse refund event")
            return
        
        order = db.query(Order).filter_by(id=webhook_event.order_id).first()
        if not order:
            print(f"[Billing] Order not found: {webhook_event.order_id}")
            return
        
        # Check if already refunded
        if order.status == OrderStatus.REFUNDED:
            print(f"[Billing] Order already refunded: {order.id}")
            return
        
        # Update order
        order.status = OrderStatus.REFUNDED
        
        # Revoke credits
        entry = refund_credits(
            user_id=order.user_id,
            order_id=str(order.id),
            notes=f"Refund processed"
        )
        
        if entry:
            print(f"[Billing] Credits refunded for user {order.user_id}")
        else:
            print(f"[Billing] WARNING: Failed to refund credits for order {order.id}")
        
        db.commit()
    
    # =========================================================================
    # QUERIES
    # =========================================================================
    
    def get_user_balance(self, user_id: int) -> int:
        """Get user's credit balance."""
        return get_balance_fast(user_id)
    
    def get_user_orders(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0
    ) -> list:
        """Get user's order history."""
        db = get_db()
        return db.query(Order).filter_by(
            user_id=user_id
        ).order_by(
            Order.created_at.desc()
        ).limit(limit).offset(offset).all()
    
    def get_products(self) -> list:
        """Get available products for purchase."""
        return get_purchasable_products()


# Singleton instance
billing_service = BillingService()
