"""
Escrow Service Layer

This module contains the core business logic for handling escrow transactions.
It provides a clean interface between the Django models and the rest of the application,
implementing all the complex escrow workflows and state management.

Key Features:
- Transaction creation and management
- Payment processing integration
- Automatic state transitions
- Audit logging
- Error handling and validation
"""

from django.db import transaction
from django.utils import timezone
from django.contrib.auth.models import User
from decimal import Decimal
import logging
import uuid
from typing import Optional, Dict, Any, List

from .models import (
    TelegramUser,
    EscrowTransaction,
    PaymentWebhook,
    DisputeCase,
    AuditLog,
)
from groups.models import GroupListing
from groups.verification_service import GroupVerificationService
from asgiref.sync import async_to_sync

# Set up logging for this service
logger = logging.getLogger("trustlink.escrow")


class EscrowService:
    """
    Main service class for handling all escrow-related operations

    This class encapsulates all the business logic for:
    - Creating and managing escrow transactions
    - Processing payments and state changes
    - Handling disputes and refunds
    - Maintaining audit trails
    """

    @staticmethod
    def create_transaction(
        buyer: TelegramUser,
        seller: TelegramUser,
        group_listing: GroupListing,
        amount: Decimal,
        currency: str,
        usd_equivalent: Optional[Decimal] = None,
    ) -> EscrowTransaction:
        """
        Create a new escrow transaction

        This is the entry point for all new transactions. It validates the inputs,
        creates the transaction record, and sets up the initial state.

        Args:
            buyer: The TelegramUser who is purchasing the group
            seller: The TelegramUser who is selling the group
            group_listing: The GroupListing being purchased
            amount: The amount to be held in escrow
            currency: The cryptocurrency being used (USDT, ETH, BTC)
            usd_equivalent: Optional USD equivalent for reference

        Returns:
            EscrowTransaction: The newly created transaction

        Raises:
            ValueError: If validation fails
            Exception: If transaction creation fails
        """

        # Validate inputs
        if buyer == seller:
            raise ValueError("Buyer and seller cannot be the same user")

        if amount <= 0:
            raise ValueError("Transaction amount must be positive")

        if currency not in ["USDT", "ETH", "BTC"]:
            raise ValueError(f"Unsupported currency: {currency}")

        if group_listing.status != "ACTIVE":
            raise ValueError("Group listing is not active")

        # Use database transaction to ensure atomicity
        with transaction.atomic():
            try:
                # Create the escrow transaction
                escrow_transaction = EscrowTransaction.objects.create(
                    buyer=buyer,
                    seller=seller,
                    group_listing=group_listing,
                    amount=amount,
                    currency=currency,
                    usd_equivalent=usd_equivalent,
                    status="PENDING",
                    # Set transfer deadline to 7 days from now
                    transfer_deadline=timezone.now() + timezone.timedelta(days=7),
                )

                # Create audit log entry
                AuditLog.objects.create(
                    transaction=escrow_transaction,
                    action="ESCROW_CREATED",
                    user=buyer,
                    details={
                        "amount": str(amount),
                        "currency": currency,
                        "group_title": group_listing.group_title,
                        "seller_username": seller.username or str(seller.telegram_id),
                    },
                )

                logger.info(
                    f"Created escrow transaction {escrow_transaction.id} for {amount} {currency}"
                )
                return escrow_transaction

            except Exception as e:
                logger.error(f"Failed to create escrow transaction: {str(e)}")
                raise

    @staticmethod
    def process_payment_received(
        transaction_id: uuid.UUID,
        payment_tx_hash: str,
        payment_address: str,
        webhook_data: Dict[Any, Any],
    ) -> bool:
        """
        Process a payment received notification

        This method is called when we receive confirmation that payment has been
        received for an escrow transaction. It updates the transaction status
        and triggers the next steps in the workflow.

        Args:
            transaction_id: UUID of the escrow transaction
            payment_tx_hash: Blockchain transaction hash
            payment_address: Address where payment was received
            webhook_data: Raw webhook data for audit purposes

        Returns:
            bool: True if processing was successful, False otherwise
        """

        try:
            with transaction.atomic():
                # Get the transaction
                escrow_transaction = EscrowTransaction.objects.select_for_update().get(
                    id=transaction_id
                )

                # Validate current state
                if escrow_transaction.status != "PENDING":
                    logger.warning(
                        f"Payment received for transaction {transaction_id} in invalid state: {escrow_transaction.status}"
                    )
                    return False

                # Update transaction with payment details
                escrow_transaction.payment_tx_hash = payment_tx_hash
                escrow_transaction.payment_address = payment_address
                escrow_transaction.status = "FUNDED"
                escrow_transaction.funded_at = timezone.now()
                escrow_transaction.save()

                # Store webhook data for audit
                PaymentWebhook.objects.create(
                    transaction=escrow_transaction,
                    webhook_data=webhook_data,
                    processed=True,
                )

                # Create audit log
                AuditLog.objects.create(
                    transaction=escrow_transaction,
                    action="PAYMENT_RECEIVED",
                    details={
                        "payment_tx_hash": payment_tx_hash,
                        "payment_address": payment_address,
                        "funded_at": escrow_transaction.funded_at.isoformat(),
                    },
                )

                logger.info(f"Payment processed for transaction {transaction_id}")

                # --- Automated Verification Step ---
                verification_service = GroupVerificationService()
                verification_result = async_to_sync(
                    verification_service.perform_full_verification
                )(
                    listing=escrow_transaction.group_listing,
                    transaction=escrow_transaction,
                )

                if verification_result.result != "PASSED":
                    logger.error(
                        f"Post-payment verification failed for transaction {transaction_id}. Reasons: {verification_result.failure_reasons}"
                    )
                    escrow_transaction.status = (
                        "DISPUTED"  # Or a new 'VERIFICATION_FAILED' status
                    )
                    escrow_transaction.notes = f"Automated verification failed: {', '.join(verification_result.failure_reasons)}"
                    escrow_transaction.save()
                    # TODO: Notify admin and users
                    return False  # Stop the process here

                logger.info(
                    f"Post-payment verification PASSED for transaction {transaction_id}"
                )
                # --- End Verification Step ---

                # If verification passes, proceed to start the transfer process using the service class.
                EscrowService.start_transfer_process(
                    transaction_id=escrow_transaction.id
                )

                return True

        except EscrowTransaction.DoesNotExist:
            logger.error(f"Transaction {transaction_id} not found")
            return False
        except Exception as e:
            logger.error(
                f"Failed to process payment for transaction {transaction_id}: {str(e)}"
            )
            return False

    @staticmethod
    def start_transfer_process(transaction_id: uuid.UUID) -> bool:
        """
        Start the group transfer process

        This method transitions the transaction to the transfer phase,
        where the seller begins the process of transferring group ownership.

        Args:
            transaction_id: UUID of the escrow transaction

        Returns:
            bool: True if successful, False otherwise
        """

        try:
            with transaction.atomic():
                escrow_transaction = EscrowTransaction.objects.select_for_update().get(
                    id=transaction_id
                )

                # Validate current state
                if escrow_transaction.status != "FUNDED":
                    logger.warning(
                        f"Cannot start transfer for transaction {transaction_id} in state: {escrow_transaction.status}"
                    )
                    return False

                # Update status
                escrow_transaction.status = "AWAITING_TRANSFER"
                escrow_transaction.save()

                # Create audit log
                AuditLog.objects.create(
                    transaction=escrow_transaction,
                    action="TRANSFER_STARTED",
                    user=escrow_transaction.seller,
                    details={
                        "transfer_deadline": escrow_transaction.transfer_deadline.isoformat()
                        if escrow_transaction.transfer_deadline
                        else None
                    },
                )

                logger.info(
                    f"Transfer process started for transaction {transaction_id}"
                )

                # TODO: Send notification to seller with transfer instructions
                # TODO: Start monitoring the group for ownership changes

                return True

        except EscrowTransaction.DoesNotExist:
            logger.error(f"Transaction {transaction_id} not found")
            return False
        except Exception as e:
            logger.error(
                f"Failed to start transfer process for transaction {transaction_id}: {str(e)}"
            )
            return False

    @staticmethod
    def complete_transaction(
        transaction_id: uuid.UUID, verification_details: Dict[Any, Any]
    ) -> bool:
        """
        Complete an escrow transaction

        This method is called when verification confirms that the group
        ownership has been successfully transferred. It releases funds
        to the seller and marks the transaction as complete.

        Args:
            transaction_id: UUID of the escrow transaction
            verification_details: Details from the verification process

        Returns:
            bool: True if successful, False otherwise
        """

        try:
            with transaction.atomic():
                escrow_transaction = EscrowTransaction.objects.select_for_update().get(
                    id=transaction_id
                )

                # Validate current state
                if escrow_transaction.status not in ["VERIFYING", "AWAITING_TRANSFER"]:
                    logger.warning(
                        f"Cannot complete transaction {transaction_id} in state: {escrow_transaction.status}"
                    )
                    return False

                # Update transaction status
                escrow_transaction.status = "COMPLETED"
                escrow_transaction.completed_at = timezone.now()
                escrow_transaction.save()

                # Update group listing status
                group_listing = escrow_transaction.group_listing
                group_listing.status = "SOLD"
                group_listing.save()

                # Create audit log
                AuditLog.objects.create(
                    transaction=escrow_transaction,
                    action="FUNDS_RELEASED",
                    details={
                        "completed_at": escrow_transaction.completed_at.isoformat(),
                        "verification_details": verification_details,
                        "amount_released": str(escrow_transaction.amount),
                        "currency": escrow_transaction.currency,
                    },
                )

                logger.info(f"Transaction {transaction_id} completed successfully")

                # TODO: Trigger actual fund release to seller's wallet
                # TODO: Send completion notifications to both parties

                return True

        except EscrowTransaction.DoesNotExist:
            logger.error(f"Transaction {transaction_id} not found")
            return False
        except Exception as e:
            logger.error(f"Failed to complete transaction {transaction_id}: {str(e)}")
            return False

    @staticmethod
    def refund_transaction(
        transaction_id: uuid.UUID,
        reason: str,
        refund_details: Optional[Dict[Any, Any]] = None,
    ) -> bool:
        """
        Refund an escrow transaction

        This method handles refunding the buyer when a transaction fails
        or is disputed in favor of the buyer.

        Args:
            transaction_id: UUID of the escrow transaction
            reason: Reason for the refund
            refund_details: Optional additional details

        Returns:
            bool: True if successful, False otherwise
        """

        try:
            with transaction.atomic():
                escrow_transaction = EscrowTransaction.objects.select_for_update().get(
                    id=transaction_id
                )

                # Validate that transaction can be refunded
                if escrow_transaction.status in ["COMPLETED", "REFUNDED"]:
                    logger.warning(
                        f"Cannot refund transaction {transaction_id} in state: {escrow_transaction.status}"
                    )
                    return False

                # Update transaction status
                escrow_transaction.status = "REFUNDED"
                escrow_transaction.completed_at = timezone.now()
                escrow_transaction.notes = f"Refunded: {reason}"
                escrow_transaction.save()

                # Create audit log
                AuditLog.objects.create(
                    transaction=escrow_transaction,
                    action="FUNDS_REFUNDED",
                    details={
                        "refunded_at": escrow_transaction.completed_at.isoformat(),
                        "reason": reason,
                        "refund_details": refund_details or {},
                        "amount_refunded": str(escrow_transaction.amount),
                        "currency": escrow_transaction.currency,
                    },
                )

                logger.info(f"Transaction {transaction_id} refunded: {reason}")

                # TODO: Trigger actual refund to buyer's wallet
                # TODO: Send refund notifications to both parties

                return True

        except EscrowTransaction.DoesNotExist:
            logger.error(f"Transaction {transaction_id} not found")
            return False
        except Exception as e:
            logger.error(f"Failed to refund transaction {transaction_id}: {str(e)}")
            return False

    @staticmethod
    def create_dispute(
        transaction_id: uuid.UUID, opened_by: TelegramUser, description: str
    ) -> Optional[DisputeCase]:
        """
        Create a dispute case for a transaction

        This method allows buyers or sellers to open disputes when
        there are issues with the transaction.

        Args:
            transaction_id: UUID of the escrow transaction
            opened_by: User opening the dispute
            description: Description of the dispute

        Returns:
            DisputeCase: The created dispute case, or None if failed
        """

        try:
            with transaction.atomic():
                escrow_transaction = EscrowTransaction.objects.select_for_update().get(
                    id=transaction_id
                )

                # Validate that user is involved in the transaction
                if opened_by not in [
                    escrow_transaction.buyer,
                    escrow_transaction.seller,
                ]:
                    logger.warning(
                        f"User {opened_by.telegram_id} not authorized to dispute transaction {transaction_id}"
                    )
                    return None

                # Check if dispute already exists
                if hasattr(escrow_transaction, "disputecase"):
                    logger.warning(
                        f"Dispute already exists for transaction {transaction_id}"
                    )
                    return escrow_transaction.disputecase

                # Update transaction status
                escrow_transaction.status = "DISPUTED"
                escrow_transaction.save()

                # Create dispute case
                dispute = DisputeCase.objects.create(
                    transaction=escrow_transaction,
                    opened_by=opened_by,
                    description=description,
                    status="OPEN",
                )

                # Create audit log
                AuditLog.objects.create(
                    transaction=escrow_transaction,
                    action="DISPUTE_OPENED",
                    user=opened_by,
                    details={
                        "dispute_id": dispute.id,
                        "opened_by": opened_by.username or str(opened_by.telegram_id),
                        "description": description,
                    },
                )

                logger.info(
                    f"Dispute created for transaction {transaction_id} by user {opened_by.telegram_id}"
                )

                # TODO: Send notifications to admin team
                # TODO: Send notification to other party

                return dispute

        except EscrowTransaction.DoesNotExist:
            logger.error(f"Transaction {transaction_id} not found")
            return None
        except Exception as e:
            logger.error(
                f"Failed to create dispute for transaction {transaction_id}: {str(e)}"
            )
            return None

    @staticmethod
    def get_transaction_status(transaction_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive status information for a transaction

        This method returns detailed status information that can be used
        by the bot or API to inform users about their transaction.

        Args:
            transaction_id: UUID of the escrow transaction

        Returns:
            Dict containing transaction status information, or None if not found
        """

        try:
            escrow_transaction = EscrowTransaction.objects.select_related(
                "buyer", "seller", "group_listing"
            ).get(id=transaction_id)

            # Calculate time remaining if there's a deadline
            time_remaining = None
            if escrow_transaction.transfer_deadline:
                delta = escrow_transaction.transfer_deadline - timezone.now()
                if delta.total_seconds() > 0:
                    time_remaining = {
                        "days": delta.days,
                        "hours": delta.seconds // 3600,
                        "minutes": (delta.seconds % 3600) // 60,
                    }

            # Get recent audit logs
            recent_logs = list(
                escrow_transaction.audit_logs.all()[:5].values(
                    "action", "timestamp", "details"
                )
            )

            status_info = {
                "transaction_id": str(escrow_transaction.id),
                "status": escrow_transaction.status,
                "status_display": escrow_transaction.get_status_display(),
                "amount": str(escrow_transaction.amount),
                "currency": escrow_transaction.currency,
                "usd_equivalent": str(escrow_transaction.usd_equivalent)
                if escrow_transaction.usd_equivalent
                else None,
                "buyer": {
                    "username": escrow_transaction.buyer.username,
                    "telegram_id": escrow_transaction.buyer.telegram_id,
                },
                "seller": {
                    "username": escrow_transaction.seller.username,
                    "telegram_id": escrow_transaction.seller.telegram_id,
                },
                "group": {
                    "title": escrow_transaction.group_listing.group_title,
                    "username": escrow_transaction.group_listing.group_username,
                },
                "timeline": {
                    "created_at": escrow_transaction.created_at.isoformat(),
                    "funded_at": escrow_transaction.funded_at.isoformat()
                    if escrow_transaction.funded_at
                    else None,
                    "completed_at": escrow_transaction.completed_at.isoformat()
                    if escrow_transaction.completed_at
                    else None,
                    "transfer_deadline": escrow_transaction.transfer_deadline.isoformat()
                    if escrow_transaction.transfer_deadline
                    else None,
                    "time_remaining": time_remaining,
                },
                "payment": {
                    "tx_hash": escrow_transaction.payment_tx_hash,
                    "address": escrow_transaction.payment_address,
                },
                "is_expired": escrow_transaction.is_expired(),
                "recent_activity": recent_logs,
            }

            # Add dispute information if exists
            if hasattr(escrow_transaction, "disputecase"):
                dispute = escrow_transaction.disputecase
                status_info["dispute"] = {
                    "status": dispute.status,
                    "opened_by": dispute.opened_by.username
                    or str(dispute.opened_by.telegram_id),
                    "created_at": dispute.created_at.isoformat(),
                    "description": dispute.description,
                }

            return status_info

        except EscrowTransaction.DoesNotExist:
            logger.error(f"Transaction {transaction_id} not found")
            return None
        except Exception as e:
            logger.error(
                f"Failed to get status for transaction {transaction_id}: {str(e)}"
            )
            return None

    @staticmethod
    def get_user_transactions(
        user: TelegramUser, status_filter: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get transactions for a specific user

        This method returns a list of transactions where the user is either
        the buyer or seller, with optional filtering by status.

        Args:
            user: The TelegramUser to get transactions for
            status_filter: Optional status to filter by
            limit: Maximum number of transactions to return

        Returns:
            List of transaction dictionaries
        """

        try:
            # Build query for transactions where user is buyer or seller
            from django.db.models import Q

            query = Q(buyer=user) | Q(seller=user)

            if status_filter:
                query &= Q(status=status_filter)

            transactions = (
                EscrowTransaction.objects.filter(query)
                .select_related("buyer", "seller", "group_listing")
                .order_by("-created_at")[:limit]
            )

            result = []
            for txn in transactions:
                # Determine user's role in this transaction
                user_role = "buyer" if txn.buyer == user else "seller"
                other_party = txn.seller if user_role == "buyer" else txn.buyer

                result.append(
                    {
                        "transaction_id": str(txn.id),
                        "status": txn.status,
                        "status_display": txn.get_status_display(),
                        "user_role": user_role,
                        "amount": str(txn.amount),
                        "currency": txn.currency,
                        "group_title": txn.group_listing.group_title,
                        "other_party": other_party.username
                        or str(other_party.telegram_id),
                        "created_at": txn.created_at.isoformat(),
                        "is_expired": txn.is_expired(),
                    }
                )

            return result

        except Exception as e:
            logger.error(
                f"Failed to get transactions for user {user.telegram_id}: {str(e)}"
            )
            return []
