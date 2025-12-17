"""
billing/providers/base.py

Abstract base class for payment providers.

All payment providers (Stripe, PayPal, Adyen, etc.) must implement this interface.
Your app talks to BillingService, which delegates to the active provider.

This allows switching providers without changing application code.

Methods to implement:
    - create_checkout_session(order, success_url, cancel_url) -> url
    - verify_webhook(payload, signature) -> event
    - parse_checkout_completed(event) -> (order_id, payment_id)
    - parse_refund(event) -> (order_id, payment_id)

Version History:
    2025-12-17: Initial implementation
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Tuple, Any
from billing.models import Order


@dataclass
class CheckoutResult:
    """Result of creating a checkout session."""
    success: bool
    checkout_url: Optional[str] = None
    provider_session_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class WebhookEvent:
    """Parsed webhook event."""
    event_id: str
    event_type: str
    raw_payload: dict
    
    # Parsed data (depends on event type)
    order_id: Optional[str] = None       # Our order UUID
    payment_id: Optional[str] = None     # Provider's payment ID
    amount_cents: Optional[int] = None
    currency: Optional[str] = None
    customer_email: Optional[str] = None


class PaymentProvider(ABC):
    """
    Abstract base class for payment providers.
    
    Implement this for each payment provider:
        - StripeProvider
        - PayPalProvider (future)
        - AdyenProvider (future)
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'stripe', 'paypal')."""
        pass
    
    @abstractmethod
    def create_checkout_session(
        self,
        order: Order,
        success_url: str,
        cancel_url: str,
        customer_email: Optional[str] = None
    ) -> CheckoutResult:
        """
        Create a checkout session for the order.
        
        Args:
            order: Order to pay for
            success_url: Redirect URL after successful payment
            cancel_url: Redirect URL if user cancels
            customer_email: Pre-fill customer email
        
        Returns:
            CheckoutResult with checkout URL or error
        """
        pass
    
    @abstractmethod
    def verify_webhook(
        self,
        payload: bytes,
        signature: str
    ) -> Tuple[bool, Optional[dict]]:
        """
        Verify webhook signature and parse payload.
        
        Args:
            payload: Raw request body
            signature: Signature header value
        
        Returns:
            (is_valid, parsed_event_dict)
        """
        pass
    
    @abstractmethod
    def parse_checkout_completed(
        self,
        event_data: dict
    ) -> Optional[WebhookEvent]:
        """
        Parse a checkout.session.completed event.
        
        Args:
            event_data: Raw event data from webhook
        
        Returns:
            WebhookEvent with order_id and payment details, or None if invalid
        """
        pass
    
    @abstractmethod
    def parse_payment_failed(
        self,
        event_data: dict
    ) -> Optional[WebhookEvent]:
        """
        Parse a payment failure event.
        
        Args:
            event_data: Raw event data from webhook
        
        Returns:
            WebhookEvent with order_id, or None if invalid
        """
        pass
    
    @abstractmethod
    def parse_refund(
        self,
        event_data: dict
    ) -> Optional[WebhookEvent]:
        """
        Parse a refund event.
        
        Args:
            event_data: Raw event data from webhook
        
        Returns:
            WebhookEvent with order_id and refund details, or None if invalid
        """
        pass
    
    def get_event_type(self, event_data: dict) -> Optional[str]:
        """
        Get event type from webhook data.
        
        Override if provider uses different structure.
        """
        return event_data.get('type')
    
    def is_checkout_completed(self, event_type: str) -> bool:
        """Check if event type is checkout completed."""
        return event_type in self.checkout_completed_events
    
    def is_payment_failed(self, event_type: str) -> bool:
        """Check if event type is payment failed."""
        return event_type in self.payment_failed_events
    
    def is_refund(self, event_type: str) -> bool:
        """Check if event type is refund."""
        return event_type in self.refund_events
    
    # Event type mappings (override in subclasses)
    @property
    def checkout_completed_events(self) -> list:
        """Event types that indicate successful checkout."""
        return []
    
    @property
    def payment_failed_events(self) -> list:
        """Event types that indicate payment failure."""
        return []
    
    @property
    def refund_events(self) -> list:
        """Event types that indicate refund."""
        return []
