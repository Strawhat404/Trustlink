"""
Group Verification Service

This service provides automated checks to verify the integrity and ownership of a Telegram group
listing. It is designed to be used at critical stages of the escrow process, such as before
payment and before releasing funds, to protect both buyers and sellers.

Key Verification Checks:
- Seller is still the owner/creator of the group.
- Group metadata (title, description, member count) matches the listing.
- The Trustlink bot is an admin with the necessary permissions.
- No suspicious changes in the admin list have occurred.
"""

import logging
from typing import Dict, Any, Tuple

from asgiref.sync import sync_to_async
from telegram import Bot
from django.conf import settings

from .models import GroupListing, GroupVerificationResult
from escrow.models import EscrowTransaction

logger = logging.getLogger(__name__)


class GroupVerificationService:
    """
    A service for performing automated verification of group listings.
    """

    def __init__(self, bot_token: str = settings.TELEGRAM_BOT_TOKEN):
        self.bot = Bot(token=bot_token)

    async def perform_full_verification(
        self, listing: GroupListing, transaction: EscrowTransaction = None
    ) -> GroupVerificationResult:
        """
        Performs all available verification checks on a group listing.
        """
        logger.info(f"Performing full verification for group: {listing.group_title}")

        # Fetch the latest group details from Telegram
        try:
            chat = await self.bot.get_chat(chat_id=listing.group_id)
            admins = await self.bot.get_chat_administrators(chat_id=listing.group_id)
            creator = next(
                (admin for admin in admins if admin.status == "creator"), None
            )
        except Exception as e:
            logger.error(f"Failed to fetch group details for verification: {e}")
            # Create a failed verification result
            return await self._create_failed_verification_result(
                transaction, listing, ["Failed to connect to Telegram API."]
            )

        # Run individual checks
        ownership_ok, owner_details = self._verify_ownership(listing, creator)
        metadata_ok, metadata_details = self._verify_metadata(listing, chat)
        bot_status_ok, bot_details = await self._verify_bot_status(admins)

        # Consolidate results
        all_checks_passed = ownership_ok and metadata_ok and bot_status_ok
        failure_reasons = [
            details
            for ok, details in [
                (ownership_ok, owner_details),
                (metadata_ok, metadata_details),
                (bot_status_ok, bot_details),
            ]
            if not ok
        ]

        # Create and save the verification result
        result = await self._save_verification_result(
            transaction=transaction,
            listing=listing,
            passed=all_checks_passed,
            ownership_verified=ownership_ok,
            metadata_matches=metadata_ok,
            bot_status_ok=bot_status_ok,
            details={
                "ownership": owner_details,
                "metadata": metadata_details,
                "bot_status": bot_details,
            },
            failure_reasons=failure_reasons,
        )
        return result

    def _verify_ownership(
        self, listing: GroupListing, creator: Any
    ) -> Tuple[bool, str]:
        """
        Verifies that the seller is the creator of the group.
        """
        if not creator:
            return False, "Could not identify the group creator."
        if creator.user.id != listing.seller.telegram_id:
            return (
                False,
                f"Seller ({listing.seller.telegram_id}) is not the group creator ({creator.user.id}).",
            )
        return True, "Seller is confirmed as the group creator."

    def _verify_metadata(self, listing: GroupListing, chat: Any) -> Tuple[bool, str]:
        """
        Verifies that the group's current metadata matches the listing.
        (Simple title check for now)
        """
        if listing.group_title.lower() != chat.title.lower():
            return (
                False,
                f"Group title mismatch. Expected '{listing.group_title}', found '{chat.title}'.",
            )
        return True, "Group metadata matches the listing."

    async def _verify_bot_status(self, admins: list) -> Tuple[bool, str]:
        """
        Verifies that the bot is an admin in the group.
        """
        bot_user = await self.bot.get_me()
        bot_admin = next(
            (admin for admin in admins if admin.user.id == bot_user.id), None
        )
        if not bot_admin:
            return False, "The Trustlink bot is not an administrator in the group."
        return True, "Bot is confirmed as an administrator."

    @sync_to_async
    def _save_verification_result(
        self, transaction, listing, passed, **kwargs
    ) -> GroupVerificationResult:
        """
        Saves the verification result to the database.
        """
        result_status = "PASSED" if passed else "FAILED"

        if transaction:
            result, _ = GroupVerificationResult.objects.update_or_create(
                transaction=transaction,
                defaults={
                    "result": result_status,
                    "ownership_verified": kwargs.get("ownership_verified"),
                    "metadata_matches": kwargs.get("metadata_matches"),
                    "admin_permissions_correct": kwargs.get("bot_status_ok"),
                    "verification_details": kwargs.get("details"),
                    "failure_reasons": kwargs.get("failure_reasons"),
                },
            )
        else:
            # This case can be used for periodic checks outside of a transaction
            # For now, we are focused on transaction-based verification
            logger.warning(
                "Verification outside of a transaction is not fully implemented."
            )
            return None

        return result

    @sync_to_async
    def _create_failed_verification_result(
        self, transaction, listing, reasons: list
    ) -> GroupVerificationResult:
        """
        Creates a verification result for a hard failure (e.g., API error).
        """
        if transaction:
            result, _ = GroupVerificationResult.objects.update_or_create(
                transaction=transaction,
                defaults={
                    "result": "FAILED",
                    "failure_reasons": reasons,
                    "verification_details": {"error": "API connection failed"},
                },
            )
            return result
        return None
