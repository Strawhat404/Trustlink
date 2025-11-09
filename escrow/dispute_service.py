"""
Dispute Resolution Service

This service handles the logic for resolving a dispute case based on the ruling
of an administrator or arbitrator. It acts as a bridge between the admin interface
and the core EscrowService, ensuring that rulings are executed correctly and securely.

Key Responsibilities:
- Apply a final ruling to a dispute case.
- Trigger fund release or refund based on the ruling.
- Update the status of the dispute and the associated transaction.
- Log the resolution for auditing purposes.
"""

import logging
from django.utils import timezone
from django.contrib.auth.models import User

from .models import DisputeCase, EscrowTransaction
from .services import EscrowService

logger = logging.getLogger(__name__)

class DisputeResolutionService:
    """
    Service to manage the resolution of dispute cases.
    """

    @staticmethod
    def resolve_dispute(dispute: DisputeCase, ruling: str, resolved_by: User, notes: str) -> bool:
        """
        Resolves a dispute based on an arbitrator's ruling.

        Args:
            dispute: The DisputeCase to be resolved.
            ruling: The final ruling (e.g., 'FAVOR_SELLER', 'FAVOR_BUYER').
            resolved_by: The admin user who made the ruling.
            notes: The resolution notes explaining the decision.

        Returns:
            True if the resolution was processed successfully, False otherwise.
        """
        logger.info(f"Resolving dispute {dispute.id} with ruling '{ruling}' by {resolved_by.username}")
        
        transaction = dispute.transaction
        if transaction.status != 'DISPUTED':
            logger.warning(f"Cannot resolve dispute for transaction {transaction.id} in state {transaction.status}")
            return False

        # Update the dispute case
        dispute.status = 'RESOLVED'
        dispute.ruling = ruling
        dispute.resolved_by = resolved_by
        dispute.resolution_notes = notes
        dispute.resolved_at = timezone.now()
        dispute.save()

        # Execute the ruling
        if ruling == 'FAVOR_SELLER':
            success = EscrowService.complete_transaction(
                transaction_id=transaction.id,
                verification_details={'resolution': 'Dispute resolved in favor of seller.'}
            )
        elif ruling == 'FAVOR_BUYER':
            success = EscrowService.refund_transaction(
                transaction_id=transaction.id,
                reason=f"Dispute resolved in favor of buyer. Notes: {notes}"
            )
        elif ruling == 'PARTIAL_REFUND':
            # For partial refunds, we mark the transaction and log it
            # In a real implementation, you would calculate the partial amount
            # and process both a partial refund and partial payment to seller
            logger.info(f"Dispute {dispute.id} resolved with PARTIAL_REFUND ruling.")
            transaction.status = 'COMPLETED'
            transaction.notes = f"Dispute resolved with partial refund. Admin notes: {notes}"
            transaction.save()
            
            # Log the partial refund action
            from .models import AuditLog
            AuditLog.objects.create(
                transaction=transaction,
                action='DISPUTE_RESOLVED',
                details={
                    'ruling': 'PARTIAL_REFUND',
                    'notes': notes,
                    'resolved_by': resolved_by.username
                }
            )
            success = True
        elif ruling == 'NO_ACTION':
            # No action means the transaction continues as-is
            logger.info(f"Dispute {dispute.id} resolved with NO_ACTION ruling.")
            # Revert transaction status to previous state if it was disputed
            if transaction.status == 'DISPUTED':
                # Determine appropriate status based on transaction state
                if transaction.funded_at:
                    transaction.status = 'AWAITING_TRANSFER'
                else:
                    transaction.status = 'PENDING'
            transaction.notes = f"Dispute resolved - no action taken. Admin notes: {notes}"
            transaction.save()
            success = True
        else:
            logger.error(f"Unknown ruling type: {ruling}")
            success = False

        if success:
            logger.info(f"Successfully executed ruling for dispute {dispute.id}")
            # Send notifications to buyer and seller about the resolution
            from telegram_bot.notification_scheduler import NotificationScheduler
            NotificationScheduler.notify_dispute_resolved(dispute)
        else:
            logger.error(f"Failed to execute ruling for dispute {dispute.id}")
            # Revert dispute status if execution failed?
            dispute.status = 'AWAITING_RULING' # Revert to allow another attempt
            dispute.save()

        return success
