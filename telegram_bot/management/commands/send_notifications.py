"""
Send Pending Notifications Management Command

This command sends all pending notifications that are due.
It should be run periodically via cron or a task scheduler.

Usage:
    python manage.py send_notifications
"""

from django.core.management.base import BaseCommand
from telegram_bot.notification_scheduler import NotificationScheduler
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send all pending notifications that are due'

    def handle(self, *args, **options):
        """
        Main command handler that sends pending notifications
        """
        self.stdout.write("Checking for pending notifications...")
        
        try:
            sent_count, failed_count = NotificationScheduler.send_pending_notifications()
            
            if sent_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Successfully sent {sent_count} notification(s)')
                )
            
            if failed_count > 0:
                self.stdout.write(
                    self.style.WARNING(f'⚠ Failed to send {failed_count} notification(s)')
                )
            
            if sent_count == 0 and failed_count == 0:
                self.stdout.write('No pending notifications to send.')
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error sending notifications: {str(e)}')
            )
            logger.error(f"Notification sending error: {str(e)}")
