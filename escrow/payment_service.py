"""
Payment Service Layer

This module handles integration with cryptocurrency payment providers.
Currently supports Coinbase Commerce for accepting USDT, ETH, and BTC payments.

Key Features:
- Create payment charges for escrow transactions
- Handle payment webhooks and confirmations
- Validate payment amounts and currencies
- Automatic payment status updates
"""

import requests
import hashlib
import hmac
import json
import logging
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple
from django.conf import settings
from django.utils import timezone

from .models import EscrowTransaction, PaymentWebhook
from .services import EscrowService
from telegram_bot.notification_service import NotificationService

# Set up logging for payment service
logger = logging.getLogger('trustlink.payments')

class PaymentService:
    """
    Service class for handling cryptocurrency payments through Coinbase Commerce
    
    This class provides methods to:
    - Create payment charges for transactions
    - Verify webhook signatures
    - Process payment confirmations
    - Handle payment failures and timeouts
    """
    
    # Coinbase Commerce API endpoints
    BASE_URL = "https://api.commerce.coinbase.com"
    CHARGES_ENDPOINT = f"{BASE_URL}/charges"
    
    @classmethod
    def create_payment_charge(
        cls,
        transaction: EscrowTransaction,
        redirect_url: Optional[str] = None,
        cancel_url: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Create a payment charge for an escrow transaction
        
        This method creates a Coinbase Commerce charge that allows the buyer
        to pay for their escrow transaction using cryptocurrency.
        
        Args:
            transaction: The EscrowTransaction to create payment for
            redirect_url: Optional URL to redirect after successful payment
            cancel_url: Optional URL to redirect if payment is cancelled
            
        Returns:
            Tuple of (success: bool, response_data: dict)
        """
        
        try:
            # Prepare charge data
            charge_data = {
                "name": f"Escrow Payment - {transaction.group_listing.group_title}",
                "description": f"Escrow payment for Telegram group: {transaction.group_listing.group_title}",
                "pricing_type": "fixed_price",
                "local_price": {
                    "amount": str(transaction.amount),
                    "currency": transaction.currency
                },
                "metadata": {
                    "transaction_id": str(transaction.id),
                    "buyer_telegram_id": str(transaction.buyer.telegram_id),
                    "seller_telegram_id": str(transaction.seller.telegram_id),
                    "group_id": str(transaction.group_listing.group_id),
                    "group_title": transaction.group_listing.group_title
                }
            }
            
            # Add redirect URLs if provided
            if redirect_url:
                charge_data["redirect_url"] = redirect_url
            if cancel_url:
                charge_data["cancel_url"] = cancel_url
            
            # Set up headers with API key
            headers = {
                "Content-Type": "application/json",
                "X-CC-Api-Key": settings.COINBASE_COMMERCE_API_KEY,
                "X-CC-Version": "2018-03-22"
            }
            
            # Make API request to create charge
            response = requests.post(
                cls.CHARGES_ENDPOINT,
                headers=headers,
                json=charge_data,
                timeout=30
            )
            
            if response.status_code == 201:
                charge_info = response.json()["data"]
                
                # Store charge information in transaction
                transaction.payment_charge_id = charge_info["id"]
                transaction.payment_charge_url = charge_info["hosted_url"]
                transaction.save()
                
                logger.info(f"Created payment charge {charge_info['id']} for transaction {transaction.id}")
                
                return True, {
                    "charge_id": charge_info["id"],
                    "payment_url": charge_info["hosted_url"],
                    "expires_at": charge_info["expires_at"],
                    "addresses": charge_info.get("addresses", {}),
                    "pricing": charge_info.get("pricing", {})
                }
            else:
                error_msg = f"Failed to create charge: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return False, {"error": error_msg}
                
        except requests.RequestException as e:
            error_msg = f"Network error creating charge: {str(e)}"
            logger.error(error_msg)
            return False, {"error": error_msg}
        except Exception as e:
            error_msg = f"Unexpected error creating charge: {str(e)}"
            logger.error(error_msg)
            return False, {"error": error_msg}
    
    @classmethod
    def verify_webhook_signature(cls, payload: bytes, signature: str) -> bool:
        """
        Verify that a webhook request came from Coinbase Commerce
        
        This method validates the webhook signature to ensure the request
        is authentic and hasn't been tampered with.
        
        Args:
            payload: Raw webhook payload bytes
            signature: Signature from X-CC-Webhook-Signature header
            
        Returns:
            bool: True if signature is valid, False otherwise
        """
        
        try:
            # Get webhook secret from settings
            webhook_secret = settings.COINBASE_COMMERCE_WEBHOOK_SECRET
            if not webhook_secret:
                logger.error("Webhook secret not configured")
                return False
            
            # Calculate expected signature
            expected_signature = hmac.new(
                webhook_secret.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()
            
            # Compare signatures (use constant-time comparison to prevent timing attacks)
            return hmac.compare_digest(signature, expected_signature)
            
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {str(e)}")
            return False
    
    @classmethod
    def process_webhook(cls, webhook_data: Dict[str, Any]) -> bool:
        """
        Process a payment webhook from Coinbase Commerce
        
        This method handles various webhook events including payment confirmations,
        failures, and timeouts.
        
        Args:
            webhook_data: Parsed webhook payload
            
        Returns:
            bool: True if webhook was processed successfully
        """
        
        try:
            event_type = webhook_data.get("event", {}).get("type")
            event_data = webhook_data.get("event", {}).get("data", {})
            
            logger.info(f"Processing webhook event: {event_type}")
            
            # Extract transaction ID from metadata
            metadata = event_data.get("metadata", {})
            transaction_id = metadata.get("transaction_id")
            
            if not transaction_id:
                logger.error("No transaction_id in webhook metadata")
                return False
            
            # Get the transaction
            try:
                transaction = EscrowTransaction.objects.get(id=transaction_id)
            except EscrowTransaction.DoesNotExist:
                logger.error(f"Transaction {transaction_id} not found")
                return False
            
            # Store webhook data for audit
            PaymentWebhook.objects.create(
                transaction=transaction,
                webhook_data=webhook_data,
                processed=False  # Will be updated based on processing result
            )
            
            # Process different event types
            if event_type == "charge:confirmed":
                return cls._handle_payment_confirmed(transaction, event_data)
            elif event_type == "charge:failed":
                return cls._handle_payment_failed(transaction, event_data)
            elif event_type == "charge:delayed":
                return cls._handle_payment_delayed(transaction, event_data)
            elif event_type == "charge:pending":
                return cls._handle_payment_pending(transaction, event_data)
            elif event_type == "charge:resolved":
                return cls._handle_payment_resolved(transaction, event_data)
            else:
                logger.info(f"Unhandled webhook event type: {event_type}")
                return True  # Not an error, just not handled
                
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}")
            return False
    
    @classmethod
    def _handle_payment_confirmed(cls, transaction: EscrowTransaction, event_data: Dict[str, Any]) -> bool:
        """
        Handle confirmed payment webhook
        
        This is called when a payment has been confirmed on the blockchain
        and the escrow can proceed to the next stage.
        """
        
        try:
            # Extract payment details
            payments = event_data.get("payments", [])
            if not payments:
                logger.error(f"No payment data in confirmed webhook for transaction {transaction.id}")
                return False
            
            # Get the first (and usually only) payment
            payment = payments[0]
            payment_network = payment.get("network")
            payment_tx_hash = payment.get("transaction_id")
            
            # Determine payment address based on network
            addresses = event_data.get("addresses", {})
            payment_address = None
            
            if payment_network in addresses:
                payment_address = addresses[payment_network]
            
            logger.info(f"Payment confirmed for transaction {transaction.id}: {payment_tx_hash}")
            
            # Use escrow service to process the payment
            success = EscrowService.process_payment_received(
                transaction_id=transaction.id,
                payment_tx_hash=payment_tx_hash,
                payment_address=payment_address or "unknown",
                webhook_data=event_data
            )
            
            if success:
                # Update webhook as processed
                webhook = PaymentWebhook.objects.filter(
                    transaction=transaction,
                    processed=False
                ).first()
                if webhook:
                    webhook.processed = True
                    webhook.save()
                
                # Send notifications to buyer and seller
                buyer_message = f"✅ Payment confirmed for transaction `{transaction.id}`. The seller has been notified to transfer ownership."
                seller_message = f"💰 Payment received for transaction `{transaction.id}`. Please transfer ownership of the group to the buyer."
                
                NotificationService.send_message(transaction.buyer.telegram_id, buyer_message)
                NotificationService.send_message(transaction.seller.telegram_id, seller_message)
                
            return success
            
        except Exception as e:
            logger.error(f"Error handling payment confirmation: {str(e)}")
            return False
    
    @classmethod
    def _handle_payment_failed(cls, transaction: EscrowTransaction, event_data: Dict[str, Any]) -> bool:
        """
        Handle failed payment webhook
        
        This is called when a payment has failed or been cancelled.
        """
        
        try:
            logger.info(f"Payment failed for transaction {transaction.id}")
            
            # If transaction is still pending, we can leave it as is
            # The user can try to pay again or the transaction will expire
            if transaction.status == 'PENDING':
                # Send notification to buyer about payment failure
                buyer_message = f"❌ Payment failed for transaction `{transaction.id}`. Please try again or contact support if the problem persists."
                NotificationService.send_message(transaction.buyer.telegram_id, buyer_message)
            
            return True
            
        except Exception as e:
            logger.error(f"Error handling payment failure: {str(e)}")
            return False
    
    @classmethod
    def _handle_payment_delayed(cls, transaction: EscrowTransaction, event_data: Dict[str, Any]) -> bool:
        """
        Handle delayed payment webhook
        
        This is called when a payment is detected but needs more confirmations.
        """
        
        try:
            logger.info(f"Payment delayed for transaction {transaction.id}")
            
            # Send notification to buyer that payment is being processed
            buyer_message = f"⏳ Your payment for transaction `{transaction.id}` is delayed. This can happen with some cryptocurrencies. We will notify you once it's confirmed."
            NotificationService.send_message(transaction.buyer.telegram_id, buyer_message)
            
            return True
            
        except Exception as e:
            logger.error(f"Error handling payment delay: {str(e)}")
            return False
    
    @classmethod
    def _handle_payment_pending(cls, transaction: EscrowTransaction, event_data: Dict[str, Any]) -> bool:
        """
        Handle pending payment webhook
        
        This is called when a payment has been detected but is still pending confirmation.
        """
        
        try:
            logger.info(f"Payment pending for transaction {transaction.id}")
            
            # Send notification to buyer that payment is detected
            buyer_message = f"👀 Your payment for transaction `{transaction.id}` has been detected and is now pending confirmation."
            NotificationService.send_message(transaction.buyer.telegram_id, buyer_message)

            return True
            
        except Exception as e:
            logger.error(f"Error handling payment pending: {str(e)}")
            return False
    
    @classmethod
    def _handle_payment_resolved(cls, transaction: EscrowTransaction, event_data: Dict[str, Any]) -> bool:
        """
        Handle resolved payment webhook
        
        This is called when a previously delayed payment has been resolved.
        """
        
        try:
            logger.info(f"Payment resolved for transaction {transaction.id}")
            
            # Check if this is a successful resolution
            payments = event_data.get("payments", [])
            if payments:
                # Process as confirmed payment
                return cls._handle_payment_confirmed(transaction, event_data)
            else:
                # Payment was not successful
                return cls._handle_payment_failed(transaction, event_data)
            
        except Exception as e:
            logger.error(f"Error handling payment resolution: {str(e)}")
            return False
    
    @classmethod
    def get_charge_status(cls, charge_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Get the current status of a payment charge
        
        This method queries Coinbase Commerce for the current status
        of a payment charge.
        
        Args:
            charge_id: The Coinbase Commerce charge ID
            
        Returns:
            Tuple of (success: bool, charge_data: dict)
        """
        
        try:
            headers = {
                "X-CC-Api-Key": settings.COINBASE_COMMERCE_API_KEY,
                "X-CC-Version": "2018-03-22"
            }
            
            response = requests.get(
                f"{cls.CHARGES_ENDPOINT}/{charge_id}",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                charge_data = response.json()["data"]
                return True, charge_data
            else:
                error_msg = f"Failed to get charge status: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return False, {"error": error_msg}
                
        except requests.RequestException as e:
            error_msg = f"Network error getting charge status: {str(e)}"
            logger.error(error_msg)
            return False, {"error": error_msg}
        except Exception as e:
            error_msg = f"Unexpected error getting charge status: {str(e)}"
            logger.error(error_msg)
            return False, {"error": error_msg}
    
    @classmethod
    def cancel_charge(cls, charge_id: str) -> bool:
        """
        Cancel a payment charge
        
        This method cancels an active payment charge, preventing further payments.
        
        Args:
            charge_id: The Coinbase Commerce charge ID
            
        Returns:
            bool: True if cancellation was successful
        """
        
        try:
            headers = {
                "Content-Type": "application/json",
                "X-CC-Api-Key": settings.COINBASE_COMMERCE_API_KEY,
                "X-CC-Version": "2018-03-22"
            }
            
            response = requests.post(
                f"{cls.CHARGES_ENDPOINT}/{charge_id}/cancel",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"Successfully cancelled charge {charge_id}")
                return True
            else:
                logger.error(f"Failed to cancel charge {charge_id}: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error cancelling charge {charge_id}: {str(e)}")
            return False
