"""
Group Monitoring Service

This service is responsible for actively monitoring Telegram groups that are part of a listing.
It fetches live data from Telegram, compares it against the last known state, and logs any
significant changes, such as admin promotions/demotions or changes in member count.

This is a critical component for ensuring the integrity of the listings and preventing scams.
"""

import asyncio
import hashlib
import logging
from typing import Dict, Any, Optional

from telegram import Bot
from telegram.error import TelegramError
from asgiref.sync import sync_to_async

from django.conf import settings
from .models import GroupListing, GroupStateLog, AdminChangeLog

logger = logging.getLogger(__name__)

class GroupMonitoringService:
    """
    A service to monitor and log changes in Telegram groups.
    """

    def __init__(self, bot_token: str = settings.TELEGRAM_BOT_TOKEN):
        self.bot = Bot(token=bot_token)

    async def get_group_details(self, group_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetches the latest details of a group from the Telegram API.
        """
        try:
            chat = await self.bot.get_chat(chat_id=group_id)
            admins = await self.bot.get_chat_administrators(chat_id=group_id)
            
            return {
                'title': chat.title,
                'member_count': await self.bot.get_chat_member_count(chat_id=group_id),
                'public_link': chat.invite_link,
                'description': chat.description,
                'admins': {admin.user.id: admin.user.username for admin in admins}
            }
        except TelegramError as e:
            logger.error(f"Failed to get details for group {group_id}: {e}")
            return None

    @sync_to_async
    def get_last_state(self, listing: GroupListing) -> Optional[GroupStateLog]:
        """
        Retrieves the most recent state log for a given listing.
        """
        return listing.state_logs.order_by('-timestamp').first()

    async def monitor_and_log_changes(self, listing: GroupListing):
        """
        Main method to monitor a group, compare its state, and log changes.
        """
        logger.info(f"Monitoring group: {listing.group_title} ({listing.group_id})")
        
        current_details = await self.get_group_details(listing.group_id)
        if not current_details:
            # Could not fetch details, maybe bot was kicked.
            # We should handle this case, e.g., by suspending the listing.
            listing.bot_is_admin = False
            await sync_to_async(listing.save)()
            logger.warning(f"Could not fetch details for {listing.group_title}. Bot might not be an admin.")
            return

        last_state = await self.get_last_state(listing)
        
        # Log the current state
        await self._log_current_state(listing, current_details)
        
        # Compare and log admin changes if there's a previous state
        if last_state:
            await self._compare_and_log_admin_changes(listing, last_state, current_details)

    @sync_to_async
    def _log_current_state(self, listing: GroupListing, details: Dict[str, Any]):
        """
        Saves a new GroupStateLog entry with the current group details.
        """
        description_hash = hashlib.sha256((details['description'] or "").encode()).hexdigest()
        
        GroupStateLog.objects.create(
            listing=listing,
            member_count=details['member_count'],
            public_link=details['public_link'],
            title=details['title'],
            description_hash=description_hash
        )

    @sync_to_async
    def _compare_and_log_admin_changes(self, listing: GroupListing, last_state: GroupStateLog, current_details: Dict[str, Any]):
        """
        Compares the current admin list with the last known admin list and logs changes.
        """
        # This is a simplified comparison. A more robust implementation would fetch the admin list
        # from the last snapshot, as GroupStateLog doesn't store it directly yet.
        # For now, we'll assume the listing's snapshot is the source of truth.
        last_admins = set(listing.admin_list_snapshot.keys()) 
        current_admins = set(current_details['admins'].keys())

        added_admins = current_admins - last_admins
        removed_admins = last_admins - current_admins

        for admin_id in added_admins:
            AdminChangeLog.objects.create(
                listing=listing,
                admin_user_id=admin_id,
                admin_username=current_details['admins'].get(admin_id),
                action='added'
            )
            logger.info(f"Logged new admin {admin_id} for group {listing.group_title}")

        for admin_id in removed_admins:
            AdminChangeLog.objects.create(
                listing=listing,
                admin_user_id=admin_id,
                admin_username=listing.admin_list_snapshot.get(str(admin_id)), # Get old username from snapshot
                action='removed'
            )
            logger.info(f"Logged removed admin {admin_id} for group {listing.group_title}")
        
        # Update the listing's main admin snapshot
        listing.admin_list_snapshot = {str(k): v for k, v in current_details['admins'].items()}
        listing.save()
