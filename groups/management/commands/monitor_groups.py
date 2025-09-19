"""
Django Management Command to Monitor Telegram Groups

This command periodically checks all active group listings for any changes in their state,
such as member count, title, or administrator list. It uses the GroupMonitoringService
to fetch live data from Telegram and logs any detected changes.

This command is designed to be run on a schedule (e.g., via a cron job) to ensure
that listings remain accurate and to detect potentially malicious activity.
"""

import asyncio
from django.core.management.base import BaseCommand
from django.utils import timezone
import logging

from groups.models import GroupListing
from groups.monitoring_service import GroupMonitoringService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Monitors all active Telegram group listings for changes.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting group monitoring process...'))
        
        try:
            asyncio.run(self.monitor_groups())
        except Exception as e:
            logger.error(f"An unexpected error occurred during group monitoring: {e}")
            self.stdout.write(self.style.ERROR('The monitoring process failed. See logs for details.'))
        
        self.stdout.write(self.style.SUCCESS('Group monitoring process finished.'))

    async def monitor_groups(self):
        """
        Asynchronously monitors all active group listings.
        """
        monitoring_service = GroupMonitoringService()
        
        # Get all active listings that have not been checked recently
        # This prevents checking too frequently if the cron job runs often
        time_threshold = timezone.now() - timezone.timedelta(minutes=30)
        active_listings = GroupListing.objects.filter(
            status='ACTIVE',
            bot_is_admin=True,
            last_verified__lte=time_threshold
        ).all()
        
        if not active_listings:
            self.stdout.write(self.style.NOTICE('No active groups to monitor at this time.'))
            return

        self.stdout.write(f"Found {len(active_listings)} groups to monitor.")

        # Create a list of monitoring tasks
        tasks = [monitoring_service.monitor_and_log_changes(listing) for listing in active_listings]
        
        # Run all monitoring tasks concurrently
        await asyncio.gather(*tasks)
        
        # Update the 'last_verified' timestamp for all monitored listings
        listing_ids = [listing.id for listing in active_listings]
        GroupListing.objects.filter(id__in=listing_ids).update(last_verified=timezone.now())
