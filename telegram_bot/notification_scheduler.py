"""
Notification Scheduler Service

This service handles scheduled notifications to users, such as:
- Payment reminders
- Transfer deadline warnings
- Dispute updates
- System announcements
"""

import logging
from django.utils import timezone
from datetime import timedelta
from .models import BotNotification
from .notification_service import NotificationService

logger = logging.getLogger(__name__)


class NotificationScheduler:
    """
    Service for scheduling and sending notifications to users
    """
    
    @classmethod
    def send_pending_notifications(cls):
        """
        Send all pending notifications that are due
        
        This method should be called periodically (e.g., every minute)
        by a cron job or task scheduler.
        """
        now = timezone.now()
        
        # Get all pending notifications that are due
        pending_notifications = BotNotification.objects.filter(
            status='PENDING',
            send_at__lte=now
        ).select_related('telegram_user')
        
        sent_count = 0
        failed_count = 0
        
        for notification in pending_notifications:
            try:
                # Send the notification
                success = NotificationService.send_message(
                    chat_id=notification.telegram_user.telegram_id,
                    text=f"**{notification.title}**\n\n{notification.message}",
                    parse_mode='Markdown'
                )
                
                if success:
                    notification.status = 'SENT'
                    notification.sent_at = timezone.now()
                    sent_count += 1
                else:
                    notification.status = 'FAILED'
                    failed_count += 1
                
                notification.save()
                
            except Exception as e:
                logger.error(f"Error sending notification {notification.id}: {str(e)}")
                notification.status = 'FAILED'
                notification.save()
                failed_count += 1
        
        if sent_count > 0 or failed_count > 0:
            logger.info(f"Sent {sent_count} notifications, {failed_count} failed")
        
        return sent_count, failed_count
    
    @classmethod
    def schedule_payment_reminder(cls, transaction, delay_hours=24):
        """
        Schedule a payment reminder for a pending transaction
        
        Args:
            transaction: EscrowTransaction instance
            delay_hours: Hours to wait before sending reminder
        """
        send_at = timezone.now() + timedelta(hours=delay_hours)
        
        notification = BotNotification.objects.create(
            telegram_user=transaction.buyer,
            notification_type='PAYMENT_RECEIVED',
            title='Payment Reminder',
            message=(
                f"⏰ Reminder: Your payment for transaction {transaction.id} is still pending.\n\n"
                f"Amount: {transaction.amount} {transaction.currency}\n"
                f"Group: {transaction.group_listing.group_title}\n\n"
                f"Please complete your payment to proceed with the escrow."
            ),
            status='PENDING',
            send_at=send_at,
            transaction=transaction
        )
        
        logger.info(f"Scheduled payment reminder for transaction {transaction.id}")
        return notification
    
    @classmethod
    def schedule_transfer_reminder(cls, transaction, delay_hours=48):
        """
        Schedule a transfer reminder for the seller
        
        Args:
            transaction: EscrowTransaction instance
            delay_hours: Hours to wait before sending reminder
        """
        send_at = timezone.now() + timedelta(hours=delay_hours)
        
        notification = BotNotification.objects.create(
            telegram_user=transaction.seller,
            notification_type='TRANSFER_REMINDER',
            title='Transfer Reminder',
            message=(
                f"⏰ Reminder: Please transfer ownership of the group for transaction {transaction.id}.\n\n"
                f"Group: {transaction.group_listing.group_title}\n"
                f"Buyer: @{transaction.buyer.username or transaction.buyer.telegram_id}\n\n"
                f"Transfer deadline: {transaction.transfer_deadline.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
                f"Please complete the transfer to receive your payment."
            ),
            status='PENDING',
            send_at=send_at,
            transaction=transaction
        )
        
        logger.info(f"Scheduled transfer reminder for transaction {transaction.id}")
        return notification
    
    @classmethod
    def send_immediate_notification(cls, telegram_user, title, message, notification_type='SYSTEM_ALERT', transaction=None):
        """
        Send an immediate notification to a user
        
        Args:
            telegram_user: TelegramUser instance
            title: Notification title
            message: Notification message
            notification_type: Type of notification
            transaction: Optional related transaction
        """
        # Create notification record
        notification = BotNotification.objects.create(
            telegram_user=telegram_user,
            notification_type=notification_type,
            title=title,
            message=message,
            status='PENDING',
            send_at=timezone.now(),
            transaction=transaction
        )
        
        # Send immediately
        try:
            success = NotificationService.send_message(
                chat_id=telegram_user.telegram_id,
                text=f"**{title}**\n\n{message}",
                parse_mode='Markdown'
            )
            
            if success:
                notification.status = 'SENT'
                notification.sent_at = timezone.now()
            else:
                notification.status = 'FAILED'
            
            notification.save()
            return success
            
        except Exception as e:
            logger.error(f"Error sending immediate notification: {str(e)}")
            notification.status = 'FAILED'
            notification.save()
            return False
    
    @classmethod
    def notify_payment_received(cls, transaction):
        """Send notification when payment is received"""
        # Notify buyer
        cls.send_immediate_notification(
            telegram_user=transaction.buyer,
            title='✅ Payment Confirmed',
            message=(
                f"Your payment for transaction {transaction.id} has been confirmed!\n\n"
                f"Amount: {transaction.amount} {transaction.currency}\n"
                f"Group: {transaction.group_listing.group_title}\n\n"
                f"The seller has been notified to transfer ownership."
            ),
            notification_type='PAYMENT_RECEIVED',
            transaction=transaction
        )
        
        # Notify seller
        cls.send_immediate_notification(
            telegram_user=transaction.seller,
            title='💰 Payment Received',
            message=(
                f"Payment received for transaction {transaction.id}!\n\n"
                f"Amount: {transaction.amount} {transaction.currency}\n"
                f"Group: {transaction.group_listing.group_title}\n"
                f"Buyer: @{transaction.buyer.username or transaction.buyer.telegram_id}\n\n"
                f"Please transfer ownership of the group to the buyer.\n"
                f"Deadline: {transaction.transfer_deadline.strftime('%Y-%m-%d %H:%M UTC')}"
            ),
            notification_type='PAYMENT_RECEIVED',
            transaction=transaction
        )
    
    @classmethod
    def notify_transfer_complete(cls, transaction):
        """Send notification when transfer is verified"""
        # Notify buyer
        cls.send_immediate_notification(
            telegram_user=transaction.buyer,
            title='🎉 Transfer Complete',
            message=(
                f"Congratulations! The group transfer for transaction {transaction.id} is complete.\n\n"
                f"Group: {transaction.group_listing.group_title}\n\n"
                f"You are now the owner of the group. Enjoy!"
            ),
            notification_type='VERIFICATION_COMPLETE',
            transaction=transaction
        )
        
        # Notify seller
        cls.send_immediate_notification(
            telegram_user=transaction.seller,
            title='✅ Funds Released',
            message=(
                f"The transfer for transaction {transaction.id} has been verified!\n\n"
                f"Amount: {transaction.amount} {transaction.currency}\n"
                f"Group: {transaction.group_listing.group_title}\n\n"
                f"Funds have been released to your account."
            ),
            notification_type='VERIFICATION_COMPLETE',
            transaction=transaction
        )
    
    @classmethod
    def notify_dispute_opened(cls, dispute):
        """Send notification when a dispute is opened"""
        transaction = dispute.transaction
        
        # Notify the other party
        other_party = transaction.seller if dispute.opened_by == transaction.buyer else transaction.buyer
        
        cls.send_immediate_notification(
            telegram_user=other_party,
            title='⚠️ Dispute Opened',
            message=(
                f"A dispute has been opened for transaction {transaction.id}.\n\n"
                f"Group: {transaction.group_listing.group_title}\n"
                f"Opened by: @{dispute.opened_by.username or dispute.opened_by.telegram_id}\n\n"
                f"An administrator will review the case and make a decision."
            ),
            notification_type='DISPUTE_UPDATE',
            transaction=transaction
        )
    
    @classmethod
    def notify_dispute_resolved(cls, dispute):
        """Send notification when a dispute is resolved"""
        transaction = dispute.transaction
        
        # Notify both parties
        for user in [transaction.buyer, transaction.seller]:
            cls.send_immediate_notification(
                telegram_user=user,
                title='✅ Dispute Resolved',
                message=(
                    f"The dispute for transaction {transaction.id} has been resolved.\n\n"
                    f"Group: {transaction.group_listing.group_title}\n"
                    f"Ruling: {dispute.get_ruling_display()}\n\n"
                    f"Resolution notes: {dispute.resolution_notes}"
                ),
                notification_type='DISPUTE_UPDATE',
                transaction=transaction
            )
