"""
billing/providers/stripe_provider.py

Stripe implementation of PaymentProvider.

This is the ONLY file that imports the stripe library.
All Stripe-specific logic is contained here.

Supports:
    - Checkout Sessions (hosted payment page)
    - Webhook signature verification
    - checkout.session.completed parsing
    - charge.refunded parsing
    - payment_intent.payment_failed parsing

Stripe Dashboard Setup Required:
    1. Create Products with prices matching your product codes
    2. Enable webhooks pointing to /billing/webhook
    3. Subscribe to: checkout.session.completed, charge.refunded, payment_intent.payment_failed

Version History:
    2025-12-17: Initial implementation
"""

from typing import Optional, Tuple
import stripe

from billing.providers.base import PaymentProvider, CheckoutResult, WebhookEvent
from billing.models import Order
from billing.config import (
    STRIPE_SECRET_KEY,
    STRIPE_WEBHOOK_SECRET,
    get_product,
)


# Configure Stripe
stripe.api_key = STRIPE_SECRET_KEY


class StripeProvider(PaymentProvider):
    """Stripe payment provider implementation."""
    
    @property
    def name(self) -> str:
        return 'stripe'
    
    @property
    def checkout_completed_events(self) -> list:
        return ['checkout.session.completed']
    
    @property
    def payment_failed_events(self) -> list:
        return ['payment_intent.payment_failed']
    
    @property
    def refund_events(self) -> list:
        return ['charge.refunded']
    
    def create_checkout_session(
        self,
        order: Order,
        success_url: str,
        cancel_url: str,
        customer_email: Optional[str] = None,
        stripe_price_id: Optional[str] = None
    ) -> CheckoutResult:
        """
        Create a Stripe Checkout session.
        
        Args:
            order: Order to pay for
            success_url: Redirect URL after success (include {CHECKOUT_SESSION_ID} placeholder)
            cancel_url: Redirect URL if cancelled
            customer_email: Pre-fill email
            stripe_price_id: Stripe price ID (from config or DB)
        
        Returns:
            CheckoutResult with checkout URL
        """
        if not STRIPE_SECRET_KEY:
            return CheckoutResult(
                success=False,
                error="Stripe not configured"
            )
        
        try:
            # Get product info
            product = get_product(order.product_code)
            if not product:
                return CheckoutResult(
                    success=False,
                    error=f"Unknown product: {order.product_code}"
                )
            
            # Build line items
            # Option 1: Use Stripe price ID if configured
            # Option 2: Use price_data for dynamic pricing
            if stripe_price_id:
                line_items = [{
                    'price': stripe_price_id,
                    'quantity': 1,
                }]
            else:
                # Dynamic pricing (no need to create prices in Stripe dashboard)
                line_items = [{
                    'price_data': {
                        'currency': order.currency.lower(),
                        'unit_amount': order.amount_cents,
                        'product_data': {
                            'name': product.name,
                            'description': product.description or f'{product.credits} document credits',
                        },
                    },
                    'quantity': 1,
                }]
            
            # Create session
            session_params = {
                'mode': 'payment',
                'line_items': line_items,
                'success_url': success_url,
                'cancel_url': cancel_url,
                'client_reference_id': str(order.id),  # Our order UUID
                'metadata': {
                    'order_id': str(order.id),
                    'product_code': order.product_code,
                    'credits': str(order.credits_granted),
                },
                'payment_intent_data': {
                    'metadata': {
                        'order_id': str(order.id),
                        'product_code': order.product_code,
                    }
                },
            }
            
            if customer_email:
                session_params['customer_email'] = customer_email
            
            session = stripe.checkout.Session.create(**session_params)
            
            return CheckoutResult(
                success=True,
                checkout_url=session.url,
                provider_session_id=session.id
            )
            
        except stripe.error.StripeError as e:
            print(f"[Stripe] Checkout session error: {e}")
            return CheckoutResult(
                success=False,
                error=str(e)
            )
        except Exception as e:
            print(f"[Stripe] Unexpected error: {e}")
            return CheckoutResult(
                success=False,
                error="Payment system error"
            )
    
    def verify_webhook(
        self,
        payload: bytes,
        signature: str
    ) -> Tuple[bool, Optional[dict]]:
        """
        Verify Stripe webhook signature.
        
        Args:
            payload: Raw request body (bytes)
            signature: Stripe-Signature header
        
        Returns:
            (is_valid, event_dict)
        """
        if not STRIPE_WEBHOOK_SECRET:
            print("[Stripe] WARNING: Webhook secret not configured, skipping verification")
            # In development, try to parse without verification
            import json
            try:
                return True, json.loads(payload)
            except:
                return False, None
        
        try:
            event = stripe.Webhook.construct_event(
                payload, signature, STRIPE_WEBHOOK_SECRET
            )
            return True, event
        except stripe.error.SignatureVerificationError as e:
            print(f"[Stripe] Webhook signature verification failed: {e}")
            return False, None
        except Exception as e:
            print(f"[Stripe] Webhook parse error: {e}")
            return False, None
    
    def parse_checkout_completed(
        self,
        event_data: dict
    ) -> Optional[WebhookEvent]:
        """
        Parse checkout.session.completed event.
        
        The order_id comes from client_reference_id which we set during checkout.
        """
        try:
            event_id = event_data.get('id')
            event_type = event_data.get('type')
            
            session = event_data.get('data', {}).get('object', {})
            
            # Our order ID from client_reference_id
            order_id = session.get('client_reference_id')
            if not order_id:
                # Try metadata fallback
                order_id = session.get('metadata', {}).get('order_id')
            
            if not order_id:
                print(f"[Stripe] No order_id in checkout event: {event_id}")
                return None
            
            return WebhookEvent(
                event_id=event_id,
                event_type=event_type,
                raw_payload=event_data,
                order_id=order_id,
                payment_id=session.get('payment_intent'),
                amount_cents=session.get('amount_total'),
                currency=session.get('currency', 'usd').upper(),
                customer_email=session.get('customer_details', {}).get('email')
            )
            
        except Exception as e:
            print(f"[Stripe] Error parsing checkout event: {e}")
            return None
    
    def parse_payment_failed(
        self,
        event_data: dict
    ) -> Optional[WebhookEvent]:
        """
        Parse payment_intent.payment_failed event.
        """
        try:
            event_id = event_data.get('id')
            event_type = event_data.get('type')
            
            payment_intent = event_data.get('data', {}).get('object', {})
            
            # Order ID from metadata
            order_id = payment_intent.get('metadata', {}).get('order_id')
            
            return WebhookEvent(
                event_id=event_id,
                event_type=event_type,
                raw_payload=event_data,
                order_id=order_id,
                payment_id=payment_intent.get('id'),
                amount_cents=payment_intent.get('amount'),
                currency=payment_intent.get('currency', 'usd').upper()
            )
            
        except Exception as e:
            print(f"[Stripe] Error parsing payment failed event: {e}")
            return None
    
    def parse_refund(
        self,
        event_data: dict
    ) -> Optional[WebhookEvent]:
        """
        Parse charge.refunded event.
        
        Note: Refunds reference a charge, which references a payment_intent.
        We need to look up the order from payment_intent metadata.
        """
        try:
            event_id = event_data.get('id')
            event_type = event_data.get('type')
            
            charge = event_data.get('data', {}).get('object', {})
            
            # Order ID from payment_intent metadata
            payment_intent_id = charge.get('payment_intent')
            order_id = charge.get('metadata', {}).get('order_id')
            
            # If not in charge metadata, we may need to fetch payment_intent
            if not order_id and payment_intent_id:
                try:
                    pi = stripe.PaymentIntent.retrieve(payment_intent_id)
                    order_id = pi.get('metadata', {}).get('order_id')
                except:
                    pass
            
            return WebhookEvent(
                event_id=event_id,
                event_type=event_type,
                raw_payload=event_data,
                order_id=order_id,
                payment_id=payment_intent_id,
                amount_cents=charge.get('amount_refunded'),
                currency=charge.get('currency', 'usd').upper()
            )
            
        except Exception as e:
            print(f"[Stripe] Error parsing refund event: {e}")
            return None


# Singleton instance
_stripe_provider = None


def get_stripe_provider() -> StripeProvider:
    """Get or create Stripe provider instance."""
    global _stripe_provider
    if _stripe_provider is None:
        _stripe_provider = StripeProvider()
    return _stripe_provider
