"""
Trustlink Telegram Bot

This module contains the main Telegram bot implementation using python-telegram-bot.
The bot handles user registration, group listing creation, and escrow transaction management.

Key Features:
- User registration and authentication
- Group listing creation and management
- Escrow transaction initiation
- Payment processing integration
- Real-time status updates and notifications

Bot Commands:
- /start - Welcome message and registration
- /help - Show available commands
- /register - Complete user registration
- /profile - View user profile and statistics
- /list_group - Create a new group listing
- /my_listings - View user's group listings
- /buy - Browse and purchase groups
- /transactions - View transaction history
- /dispute - Open a dispute for a transaction
- /cancel - Cancel current operation
"""

import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from asgiref.sync import sync_to_async

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes
)
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown

import django
import os
import sys

# Add Django project to Python path dynamically
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'trustlink_backend.settings')

# Setup Django
try:
    django.setup()
except Exception as e:
    print(f"Django setup failed: {e}")
    sys.exit(1)

from django.conf import settings
from escrow.models import TelegramUser, EscrowTransaction
from groups.models import GroupListing
from escrow.services import EscrowService
from escrow.payment_service import PaymentService
from telegram_bot.models import BotSession, BotMessage
import httpx

API_BASE_URL = "http://127.0.0.1:8000/api"

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
(
    REGISTRATION_NAME,
    REGISTRATION_CONFIRM,
    GROUP_LISTING_USERNAME,
    GROUP_LISTING_TITLE,
    GROUP_LISTING_DESCRIPTION,
    GROUP_LISTING_PRICE,
    GROUP_LISTING_CATEGORY,
    GROUP_LISTING_CONFIRM,
    TRANSACTION_AMOUNT,
    TRANSACTION_CURRENCY,
    TRANSACTION_CONFIRM,
    DISPUTE_DESCRIPTION,
) = range(12)

class TrustlinkBot:
    """
    Main bot class that handles all Telegram bot functionality
    
    This class manages user interactions, conversation flows,
    and integration with the Django backend services.
    """
    
    def __init__(self, token: str):
        """Initialize the bot with the given token"""
        self.token = token
        # Set a longer timeout and a post_init hook to set the command menu
        self.application = Application.builder().token(token).pool_timeout(30.0).build()
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Set up all command and message handlers"""
        
        # Command Handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("profile", self.profile_command))
        self.application.add_handler(CommandHandler("browse", self.browse_command))
        self.application.add_handler(CommandHandler("view", self.view_command))
        self.application.add_handler(CommandHandler("cancel", self.cancel_command))

        # Message Handlers for Keyboard Buttons
        self.application.add_handler(MessageHandler(filters.Regex('^🏪 Browse Listings$'), self.browse_command))
        self.application.add_handler(MessageHandler(filters.Regex('^📝 List a Group$'), self.list_group_start))
        self.application.add_handler(MessageHandler(filters.Regex('^👤 My Profile$'), self.profile_command))
        self.application.add_handler(MessageHandler(filters.Regex('^❓ Help$'), self.help_command))

        # Callback Handlers for contextual menus
        self.application.add_handler(CallbackQueryHandler(self.my_listings_command, pattern='^my_listings$'))
        self.application.add_handler(CallbackQueryHandler(self.transactions_command, pattern='^transactions$'))
        self.application.add_handler(CallbackQueryHandler(self.profile_command, pattern='^profile$'))
        
        # Registration conversation handler
        registration_handler = ConversationHandler(
            entry_points=[
                CommandHandler("register", self.register_start),
                CallbackQueryHandler(self.register_start, pattern='^register$')
            ],
            states={
                REGISTRATION_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.register_name)],
                REGISTRATION_CONFIRM: [
                    CallbackQueryHandler(self.register_confirm, pattern="^(confirm|cancel)_registration$")
                ],
            },
            fallbacks=[CommandHandler("cancel", self.cancel_command)],
        )
        self.application.add_handler(registration_handler)
        
        # Group listing conversation handler
        listing_handler = ConversationHandler(
            entry_points=[CommandHandler("list_group", self.list_group_start)],
            states={
                GROUP_LISTING_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.list_group_username)],
                GROUP_LISTING_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.list_group_title)],
                GROUP_LISTING_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.list_group_description)],
                GROUP_LISTING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.list_group_price)],
                GROUP_LISTING_CATEGORY: [CallbackQueryHandler(self.list_group_category, pattern="^category_")],
                GROUP_LISTING_CONFIRM: [CallbackQueryHandler(self.list_group_confirm, pattern="^(confirm|cancel)_listing$")],
            },
            fallbacks=[CommandHandler("cancel", self.cancel_command)],
        )
        self.application.add_handler(listing_handler)
        
        # Transaction conversation handler
        transaction_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.transaction_start, pattern="^buy_group_")],
            states={
                TRANSACTION_CURRENCY: [CallbackQueryHandler(self.transaction_currency, pattern="^currency_")],
                TRANSACTION_CONFIRM: [CallbackQueryHandler(self.transaction_confirm, pattern="^(confirm|cancel)_transaction$")],
            },
            fallbacks=[CommandHandler("cancel", self.cancel_command)],
        )
        self.application.add_handler(transaction_handler)
        
        # Callback query handler for inline keyboards
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Error handler
        self.application.add_error_handler(self.error_handler)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command"""
        
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        # Log the interaction
        await self._log_message(user.id, "start", "/start command")
        
        # Check if user is already registered
        telegram_user = await self._get_or_create_telegram_user(user)
        
        first_name = escape_markdown(user.first_name or "User", version=2)
        welcome_message = f"""🎉 *Welcome to Trustlink!* 🎉

Hi {first_name}! I'm your secure escrow bot for safe Telegram group transactions.

Use the menu below to navigate the bot's features."""
        
        keyboard = [
            [KeyboardButton("🏪 Browse Listings"), KeyboardButton("📝 List a Group")],
            [KeyboardButton("👤 My Profile"), KeyboardButton("❓ Help")],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            welcome_message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /help command, works for both command and callback_query"""
        
        help_text = """📚 *Trustlink Help Guide*

*Available Commands:*
• `/start` \- Welcome message
• `/help` \- Show this help message
• `/register` \- Register as a new user
• `/profile` \- View your profile
• `/browse` \- Browse group listings
• `/view <id>` \- View a specific listing
• `/list_group` \- Create a new group listing
• `/cancel` \- Cancel current operation"""
        
        # Determine how to reply based on the update type
        if update.callback_query:
            # If it's a button press, edit the message
            await update.callback_query.edit_message_text(help_text, parse_mode=ParseMode.MARKDOWN_V2)
        elif update.message:
            # If it's a command, send a new message
            await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN_V2)

    async def buy_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /buy command - show active listings to purchase"""
        try:
            # Fetch latest active listings
            listings = await sync_to_async(list)(
                GroupListing.objects.filter(status='ACTIVE').select_related('seller').order_by('-created_at')[:10]
            )

            if not listings:
                await update.message.reply_text("🛍️ No active listings available right now. Please check back later.")
                return

            # Build keyboard with up to 10 listings
            keyboard = []
            for gl in listings:
                label = f"{gl.group_title[:28]} • ${gl.price_usd}"
                keyboard.append([InlineKeyboardButton(label, callback_data=f"buy_group_{gl.id}")])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "🛍️ **Available Group Listings**\n\nSelect a group to start a secure escrow purchase:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"/buy error: {str(e)}")
            await update.message.reply_text("❌ Failed to load listings. Please try again later.")

    async def browse_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /browse command to show marketplace listings."""
        chat_id = update.effective_chat.id
        
        try:
            # Send a typing action to show the bot is working
            await context.bot.send_chat_action(chat_id=chat_id, action='typing')
            
            # Try to get the message object to edit later
            try:
                status_message = await update.message.reply_text("🔎 Searching for the latest group listings...")
                message_id = status_message.message_id
            except:
                message_id = None
            
            try:
                # Add a timeout to the request
                timeout = httpx.Timeout(10.0, connect=30.0)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    # Try to connect to the API
                    try:
                        response = await client.get(f"{API_BASE_URL}/groups/listings/")
                        response.raise_for_status()
                        listings = response.json()
                    except httpx.ConnectError as e:
                        logger.error(f"Connection error while accessing API: {e}")
                        error_msg = "❌ Could not connect to the marketplace. Please make sure the server is running."
                        if message_id:
                            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=error_msg)
                        else:
                            await update.message.reply_text(error_msg)
                        return
                    except httpx.HTTPStatusError as e:
                        logger.error(f"API returned error status: {e.response.status_code} - {e.response.text}")
                        error_msg = "❌ There was an error retrieving listings. Please try again later."
                        if message_id:
                            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=error_msg)
                        else:
                            await update.message.reply_text(error_msg)
                        return
                    except Exception as e:
                        logger.error(f"Unexpected error while processing API response: {e}")
                        error_msg = "❌ An unexpected error occurred while processing the listings."
                        if message_id:
                            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=error_msg)
                        else:
                            await update.message.reply_text(error_msg)
                        return

                listings_data = listings.get('results', [])

                if not listings_data:
                    no_listings_msg = "🛍️ No active listings available right now. Please check back later."
                    if message_id:
                        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=no_listings_msg)
                    else:
                        await update.message.reply_text(no_listings_msg)
                    return

                # Format the listings into a message
                message = "*🔥 Top Group Listings*\n\n"
                for listing in listings_data[:10]:  # Show top 10
                    try:
                        # Clean and escape the title
                        title = escape_markdown(str(listing.get('group_title', 'Untitled')), version=2)
                        member_count = listing.get('member_count', 0)
                        price = listing.get('price_usd', '0.00')
                        listing_id = listing.get('id', '').strip()
                        
                        message += f"- *{title}*\n"
                        message += f"  👥 {member_count} members\n"
                        message += f"  💰 ${price}\n"
                        message += f"  📝 `/view {listing_id}`\n\n"
                    except Exception as e:
                        logger.error(f"Error formatting listing {listing.get('id')}: {e}")
                        continue
                
                # Add a footer
                message += "\nUse `/view <id>` to see more details about a listing."
                
                # Send or update the message
                if message_id:
                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=message,
                            parse_mode=ParseMode.MARKDOWN_V2,
                            disable_web_page_preview=True
                        )
                    except Exception as e:
                        logger.error(f"Error updating message: {e}")
                        # If we can't edit the message, send a new one
                        await update.message.reply_text(
                            message,
                            parse_mode=ParseMode.MARKDOWN_V2,
                            disable_web_page_preview=True
                        )
                else:
                    await update.message.reply_text(
                        message,
                        parse_mode=ParseMode.MARKDOWN_V2,
                        disable_web_page_preview=True
                    )
                
            except Exception as e:
                logger.error(f"Error in browse_command: {e}", exc_info=True)
                error_msg = "❌ An error occurred while fetching listings. Please try again."
                if message_id:
                    await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=error_msg)
                else:
                    await update.message.reply_text(error_msg)
        
        except Exception as e:
            logger.error(f"Unexpected error in browse_command: {e}", exc_info=True)
            await update.message.reply_text("❌ An unexpected error occurred. Please try again later.")

    async def view_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /view <id> command to show listing details."""
        if not context.args:
            await update.message.reply_text("Please provide a listing ID. Usage: `/view <listing_id>`")
            return

        listing_id = context.args[0]

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{API_BASE_URL}/groups/listings/{listing_id}/")
                response.raise_for_status()
                listing = response.json()

            seller_username = escape_markdown(listing['seller']['username'] or 'N/A', version=2)
            title = escape_markdown(listing['group_title'], version=2)
            description = escape_markdown(listing['group_description'], version=2)

            message = f"*📄 Listing Details: {title}*\n\n"
            message += f"*Description:*\n{description}\n\n"
            message += f"*Seller:* @{seller_username}\n"
            message += f"*Price:* ${listing['price_usd']}\n"
            message += f"*Members:* {listing['member_count']}\n"
            message += f"*Category:* {listing['category']}\n\n"
            message += f"To purchase this group, use the button below."

            keyboard = [[InlineKeyboardButton(f"🛒 Buy for ${listing['price_usd']}", callback_data=f"buy_group_{listing['id']}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                await update.message.reply_text("Sorry, I couldn't find a listing with that ID.")
            else:
                logger.error(f"API error while viewing listing {listing_id}: {e}")
                await update.message.reply_text("Sorry, there was an error retrieving the listing details.")
        except Exception as e:
            logger.error(f"Error in /view command for ID {listing_id}: {e}")
            await update.message.reply_text("An unexpected error occurred. Please try again.")
    
    async def register_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the registration process, handles both command and callback query"""
        
        query = update.callback_query
        if query:
            await query.answer()

        user = update.effective_user
        
        # Determine how to send the message
        reply_func = query.edit_message_text if query else update.message.reply_text

        # Check if already registered
        telegram_user = await self._get_telegram_user(user.id)
        if telegram_user and telegram_user.is_verified:
            await reply_func(
                "✅ You're already registered and verified!\n\n"
                "Use /profile to view your information or /help to see available commands."
            )
            return ConversationHandler.END
        
        await reply_func(
            "📝 **User Registration**\n\n"
            "To get started with Trustlink, I need to collect some basic information.\n\n"
            "Please enter your full name (this will be used for verification purposes):",
            parse_mode=ParseMode.MARKDOWN
        )
        
        return REGISTRATION_NAME
    
    async def register_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle name input during registration"""
        
        full_name = update.message.text.strip()
        
        if len(full_name) < 2:
            await update.message.reply_text(
                "❌ Please enter a valid full name (at least 2 characters)."
            )
            return REGISTRATION_NAME
        
        # Store the name in context
        context.user_data['registration_name'] = full_name
        
        user = update.effective_user
        
        confirmation_text = f"""
📋 **Registration Confirmation**

**Telegram Info:**
• Username: @{user.username or 'Not set'}
• First Name: {user.first_name}
• Last Name: {user.last_name or 'Not set'}

**Provided Info:**
• Full Name: {full_name}

**Terms & Conditions:**
By registering, you agree to:
• Use the service responsibly
• Provide accurate information
• Follow our dispute resolution process
• Pay applicable fees for transactions

Is this information correct?
        """
        
        keyboard = [
            [InlineKeyboardButton("✅ Confirm Registration", callback_data="confirm_registration")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_registration")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            confirmation_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        
        return REGISTRATION_CONFIRM
    
    async def register_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle registration confirmation"""
        
        query = update.callback_query
        await query.answer()
        
        if query.data == "cancel_registration":
            await query.edit_message_text("❌ Registration cancelled.")
            return ConversationHandler.END
        
        # Create or update the user
        user = update.effective_user
        full_name = context.user_data.get('registration_name', '')
        
        try:
            telegram_user = await self._get_or_create_telegram_user(user)
            
            # Update user information
            if full_name:
                name_parts = full_name.split(' ', 1)
                telegram_user.first_name = name_parts[0]
                if len(name_parts) > 1:
                    telegram_user.last_name = name_parts[1]
            
            telegram_user.is_verified = True
            await self._save_telegram_user(telegram_user)
            
            success_message = f"""
✅ **Registration Successful!**

Welcome to Trustlink, {telegram_user.first_name}!

**Your Account:**
• Status: Verified ✅
• Registration Date: {datetime.now().strftime('%Y-%m-%d')}
• User ID: {telegram_user.telegram_id}

**Next Steps:**
• Use /list_group to sell a group
• Use /buy to browse available groups
• Use /profile to view your account details

Happy trading! 🚀
            """
            
            keyboard = [
                [InlineKeyboardButton("🏪 Browse Groups", callback_data="browse_groups")],
                [InlineKeyboardButton("📝 List My Group", callback_data="list_group")],
                [InlineKeyboardButton("👤 View Profile", callback_data="profile")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                success_message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Registration error for user {user.id}: {str(e)}")
            await query.edit_message_text(
                "❌ Registration failed. Please try again later or contact support."
            )
        
        return ConversationHandler.END
    
    async def profile_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /profile command"""
        
        user = update.effective_user
        telegram_user = await self._get_telegram_user(user.id)
        
        if not telegram_user:
            await update.message.reply_text(
                "❌ You're not registered yet. Use /register to get started!"
            )
            return
        
        # Get user statistics
        total_purchases = await self._get_user_transaction_count(telegram_user, 'buyer')
        total_sales = await self._get_user_transaction_count(telegram_user, 'seller')
        active_listings = await self._get_user_active_listings_count(telegram_user)
        
        # Escape special characters for Markdown V2
        first_name = escape_markdown(telegram_user.first_name or "", version=2)
        last_name = escape_markdown(telegram_user.last_name or "", version=2)
        username = escape_markdown(telegram_user.username or "Not set", version=2)
        
        profile_text = f"""👤 *Your Profile*

*Basic Information:*
• Name: {first_name} {last_name}
• Username: @{username}
• Status: {'✅ Verified' if telegram_user.is_verified else '❌ Not verified'}
• Member Since: {telegram_user.created_at.strftime('%B %Y')}

*Trading Statistics:*
• Total Purchases: {total_purchases}
• Total Sales: {total_sales}
• Active Listings: {active_listings}
• User ID: `{telegram_user.telegram_id}`"""
        
        keyboard = [
            [InlineKeyboardButton("🏪 My Listings", callback_data="my_listings"), InlineKeyboardButton("📊 Transaction History", callback_data="transactions")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="profile")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Determine how to reply based on the update type
        if update.callback_query:
            await update.callback_query.edit_message_text(profile_text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup)
        elif update.message:
            await update.message.reply_text(profile_text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup)

    async def transactions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Displays the user's transaction history."""
        user = update.effective_user
        telegram_user = await self._get_telegram_user(user.id)
        if not telegram_user:
            await update.callback_query.answer("You need to be registered to see transactions.")
            return

        transactions = await sync_to_async(list)(EscrowTransaction.objects.filter(buyer=telegram_user).order_by('-created_at')[:10])

        message = "*📊 Your Recent Transactions*\n\n"
        if not transactions:
            message += "You have no recent transactions."
        else:
            for txn in transactions:
                message += f"▪️ *{escape_markdown(txn.listing.group_title, version=2)}* \- ${txn.amount} {txn.currency} \- *Status:* {txn.status}\n"

        keyboard = [[InlineKeyboardButton("⬅️ Back to Profile", callback_data="profile")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.callback_query:
            await update.callback_query.edit_message_text(message, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup)
        elif update.message:
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup)

    async def my_listings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Displays the user's group listings."""
        user = update.effective_user
        telegram_user = await self._get_telegram_user(user.id)
        if not telegram_user:
            await update.callback_query.answer("You need to be registered to see your listings.")
            return

        listings = await sync_to_async(list)(GroupListing.objects.filter(seller=telegram_user).order_by('-created_at')[:10])

        message = "*🏪 Your Group Listings*\n\n"
        if not listings:
            message += "You have no active listings. Use `/list_group` to create one."
        else:
            for listing in listings:
                message += f"▪️ *{escape_markdown(listing.group_title, version=2)}* \- ${listing.price_usd} \- *Status:* {listing.status}\n"

        keyboard = [[InlineKeyboardButton("⬅️ Back to Profile", callback_data="profile")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.callback_query:
            await update.callback_query.edit_message_text(message, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup)
        elif update.message:
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup)
    
    async def list_group_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the group listing process"""
        
        user = update.effective_user
        telegram_user = await self._get_telegram_user(user.id)
        
        if not telegram_user or not telegram_user.is_verified:
            await update.message.reply_text(
                "❌ You need to register first. Use /register to get started!"
            )
            return ConversationHandler.END
        
        await update.message.reply_text(
            "🏪 **Create Group Listing: Step 1 of 5**\n\n"
            "To begin, please provide your group's username (e.g., @mygroup).\n\n"
            "*Note: For verification, this bot must be an administrator in your group.*",
            parse_mode=ParseMode.MARKDOWN
        )
        
        return GROUP_LISTING_USERNAME
    
    async def list_group_username(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle group username input and verify ownership."""
        group_username = update.message.text.strip()
        if not group_username.startswith('@'):
            group_username = f"@{group_username}"

        try:
            # Check if bot is an admin
            bot_user = await context.bot.get_me()
            admins = await context.bot.get_chat_administrators(group_username)
            if not any(admin.user.id == bot_user.id for admin in admins):
                await update.message.reply_text(
                    "❌ **Verification Failed**\n\nI am not an administrator in that group. Please add me as an admin and try again.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return ConversationHandler.END

            # Check if the user is the creator
            creator = next((admin for admin in admins if admin.status == 'creator'), None)
            if not creator or creator.user.id != update.effective_user.id:
                await update.message.reply_text(
                    "❌ **Ownership Verification Failed**\n\nYou are not the creator of this group. Only the group owner can list it for sale.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return ConversationHandler.END

            context.user_data['listing_group_username'] = group_username
            await update.message.reply_text(
                f"✅ **Ownership Confirmed for {group_username}**\n\n"
                "Next, please enter the **title** for your listing:",
                parse_mode=ParseMode.MARKDOWN
            )
            return GROUP_LISTING_TITLE

        except Exception as e:
            logger.error(f"Error verifying group ownership for {group_username}: {e}")
            await update.message.reply_text(
                "❌ **Error**\n\nI couldn't find that group or an error occurred. Please ensure the username is correct and the group is public.",
                parse_mode=ParseMode.MARKDOWN
            )
            return ConversationHandler.END

    async def list_group_title(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle group title input"""
        
        title = update.message.text.strip()
        
        if len(title) < 3:
            await update.message.reply_text(
                "❌ Group title must be at least 3 characters long."
            )
            return GROUP_LISTING_TITLE
        
        context.user_data['listing_title'] = title
        
        await update.message.reply_text(
            f"✅ Title: **{title}**\n\n"
            "**Step 3 of 5:** Now, please provide a **description** of your group (what it's about, rules, etc.):",
            parse_mode=ParseMode.MARKDOWN
        )
        
        return GROUP_LISTING_DESCRIPTION
    
    async def list_group_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle group description input"""
        
        description = update.message.text.strip()
        
        if len(description) < 10:
            await update.message.reply_text(
                "❌ Description must be at least 10 characters long."
            )
            return GROUP_LISTING_DESCRIPTION
        
        context.user_data['listing_description'] = description
        
        await update.message.reply_text(
            "✅ Description saved!\n\n"
            "**Step 4 of 5:** What's your asking **price in USD**? (Enter just the number, e.g., 150):",
            parse_mode=ParseMode.MARKDOWN
        )
        
        return GROUP_LISTING_PRICE
    
    async def list_group_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle group price input"""
        
        try:
            price = float(update.message.text.strip())
            if price <= 0:
                raise ValueError("Price must be positive")
            if price > 10000:
                raise ValueError("Price too high")
        except ValueError:
            await update.message.reply_text(
                "❌ Please enter a valid price (1-10000 USD)."
            )
            return GROUP_LISTING_PRICE
        
        context.user_data['listing_price'] = price
        
        # Show category selection
        keyboard = [
            [InlineKeyboardButton("💰 Cryptocurrency", callback_data="category_CRYPTO")],
            [InlineKeyboardButton("📈 Trading", callback_data="category_TRADING")],
            [InlineKeyboardButton("💻 Technology", callback_data="category_TECH")],
            [InlineKeyboardButton("💼 Business", callback_data="category_BUSINESS")],
            [InlineKeyboardButton("📚 Education", callback_data="category_EDUCATION")],
            [InlineKeyboardButton("🎮 Entertainment", callback_data="category_ENTERTAINMENT")],
            [InlineKeyboardButton("📂 Other", callback_data="category_OTHER")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ Price: **${price:.2f} USD**\n\n"
            "**Step 5 of 5:** Please select the category that best describes your group:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        
        return GROUP_LISTING_CATEGORY
    
    async def list_group_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle category selection"""
        
        query = update.callback_query
        await query.answer()
        
        category = query.data.replace("category_", "")
        context.user_data['listing_category'] = category
        
        # Category display names
        category_names = {
            'CRYPTO': 'Cryptocurrency',
            'TRADING': 'Trading',
            'TECH': 'Technology',
            'BUSINESS': 'Business',
            'EDUCATION': 'Education',
            'ENTERTAINMENT': 'Entertainment',
            'OTHER': 'Other'
        }
        
        # Show confirmation
        title = context.user_data.get('listing_title', '')
        description = context.user_data.get('listing_description', '')
        price = context.user_data.get('listing_price', 0)
        group_username = context.user_data.get('listing_group_username', '')
        
        # Escape special characters for Markdown
        safe_title = escape_markdown(title, version=2)
        safe_description = escape_markdown(description[:200], version=2)
        safe_username = escape_markdown(group_username, version=2)
        safe_category = escape_markdown(category_names.get(category, category), version=2)
        
        try:
            confirmation_text = f"""📋 *Listing Confirmation*

*Group Details:*
• Group: {safe_username}
• Title: {safe_title}
• Category: {safe_category}
• Price: ${price:.2f} USD

*Description:*
{safe_description}{'\\.\\.\\.' if len(description) > 200 else ''}

*Important Notes:*
• Group ownership has been verified ✅
• 5% platform fee applies to successful sales
• Listing expires after 30 days

Ready to create this listing?"""
            
            keyboard = [
                [InlineKeyboardButton("✅ Create Listing", callback_data="confirm_listing")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_listing")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                confirmation_text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error in list_group_category: {e}")
            # Fallback to plain text
            simple_text = f"""📋 Listing Confirmation

Group: {group_username}
Title: {title}
Category: {category_names.get(category, category)}
Price: ${price:.2f} USD

Description: {description[:200]}{'...' if len(description) > 200 else ''}

Ready to create this listing?"""
            
            keyboard = [
                [InlineKeyboardButton("✅ Create Listing", callback_data="confirm_listing")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_listing")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                simple_text,
                reply_markup=reply_markup
            )
        
        return GROUP_LISTING_CONFIRM
    
    async def list_group_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle listing confirmation"""
        
        query = update.callback_query
        await query.answer()
        
        if query.data == "cancel_listing":
            await query.edit_message_text("❌ Listing cancelled.")
            return ConversationHandler.END
        
        # Create the listing
        user = update.effective_user
        telegram_user = await self._get_telegram_user(user.id)
        
        try:
            # Get listing data from context
            title = context.user_data.get('listing_title', '')
            description = context.user_data.get('listing_description', '')
            price = context.user_data.get('listing_price', 0)
            category = context.user_data.get('listing_category', 'OTHER')
            group_username = context.user_data.get('listing_group_username', '')
            
            # Get group information from Telegram API
            chat = await context.bot.get_chat(group_username)
            member_count = await context.bot.get_chat_member_count(group_username)
            
            # Create the GroupListing record
            @sync_to_async
            def create_listing():
                return GroupListing.objects.create(
                    seller=telegram_user,
                    group_title=title,
                    group_description=description,
                    group_username=group_username,
                    group_id=chat.id,
                    member_count=member_count,
                    price_usd=price,
                    category=category,
                    status='ACTIVE'
                )
            
            listing = await create_listing()
            
            success_message = f"""✅ **Listing Created Successfully!**

Your group listing has been created and is now live!

**Listing Details:**
• ID: {listing.id}
• Group: {group_username}
• Price: ${price:.2f} USD
• Status: Active

**What happens next:**
• Buyers can now browse and purchase your group
• All transactions are handled through secure escrow
• You'll receive notifications for purchase requests

Use `/my_listings` to manage your listings anytime!"""
            
            keyboard = [
                [InlineKeyboardButton("🏪 My Listings", callback_data="my_listings")],
                [InlineKeyboardButton("📊 View Profile", callback_data="profile")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                success_message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Listing creation error for user {user.id}: {str(e)}")
            await query.edit_message_text(
                "❌ Failed to create listing. Please try again later or contact support."
            )
        
        return ConversationHandler.END
    
    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /cancel command"""
        
        context.user_data.clear()
        await update.message.reply_text(
            "❌ Operation cancelled. Use /help to see available commands."
        )
        return ConversationHandler.END
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from inline keyboards"""
        
        query = update.callback_query
        await query.answer()
        
        if query.data == "help":
            await self.help_command(update, context)
        elif query.data == "profile":
            await self.profile_command(update, context)
        elif query.data == "browse_groups":
            await query.edit_message_text("🏪 Group browsing feature coming soon!")
        elif query.data == "list_group":
            await query.edit_message_text("Use /list_group command to create a new listing.")
        elif query.data == "my_listings":
            await query.edit_message_text("📝 My listings feature coming soon!")
        elif query.data == "transactions":
            await query.edit_message_text("📊 Transaction history feature coming soon!")

    # ===== Transaction conversation handlers =====
    async def transaction_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start transaction after selecting a group listing"""
        query = update.callback_query
        await query.answer()

        try:
            prefix = "buy_group_"
            listing_id = query.data[len(prefix):]
            context.user_data['transaction_listing_id'] = listing_id

            # Confirm listing exists
            gl = await sync_to_async(GroupListing.objects.get)(id=listing_id, status='ACTIVE')

            # Ask for currency selection
            keyboard = [
                [InlineKeyboardButton("USDT", callback_data="currency_USDT")],
                [InlineKeyboardButton("ETH", callback_data="currency_ETH")],
                [InlineKeyboardButton("BTC", callback_data="currency_BTC")],
            ]
            await query.edit_message_text(
                f"💳 Purchasing: {gl.group_title}\n\nSelect payment currency:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return TRANSACTION_CURRENCY
        except GroupListing.DoesNotExist:
            await query.edit_message_text("❌ Listing is no longer available.")
            return ConversationHandler.END
        except Exception as e:
            logger.error(f"transaction_start error: {str(e)}")
            await query.edit_message_text("❌ Failed to start transaction.")
            return ConversationHandler.END

    async def transaction_currency(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle currency selection"""
        query = update.callback_query
        await query.answer()
        try:
            currency = query.data.replace("currency_", "")
            context.user_data['transaction_currency'] = currency

            listing_id = context.user_data.get('transaction_listing_id')
            gl = await sync_to_async(GroupListing.objects.get)(id=listing_id)

            # For now, we use USD amount directly for USDT. For BTC/ETH, a real implementation would convert.
            amount_display = f"${gl.price_usd} USD" if currency == 'USDT' else f"≈ ${gl.price_usd} USD in {currency}"

            keyboard = [
                [InlineKeyboardButton("✅ Confirm", callback_data="confirm_transaction")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_transaction")],
            ]
            await query.edit_message_text(
                f"🧾 Transaction Summary\n\n"
                f"Group: {gl.group_title}\n"
                f"Seller: @{gl.seller.username or gl.seller.telegram_id}\n"
                f"Price: {amount_display}\n"
                f"Currency: {currency}\n\n"
                f"Proceed to create escrow and payment link?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return TRANSACTION_CONFIRM
        except Exception as e:
            logger.error(f"transaction_currency error: {str(e)}")
            await query.edit_message_text("❌ Failed to set currency.")
            return ConversationHandler.END

    async def transaction_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Create escrow and return payment link"""
        query = update.callback_query
        await query.answer()

        if query.data == "cancel_transaction":
            await query.edit_message_text("❌ Transaction cancelled.")
            return ConversationHandler.END

        try:
            user = update.effective_user
            buyer = await self._get_or_create_telegram_user(user)

            listing_id = context.user_data.get('transaction_listing_id')
            currency = context.user_data.get('transaction_currency', 'USDT')
            gl = await sync_to_async(GroupListing.objects.get)(id=listing_id)

            # Determine amount: use USD price as amount for USDT; for others, keep USD and mark usd_equivalent.
            from decimal import Decimal
            amount = Decimal(gl.price_usd)

            # Create escrow transaction via service layer
            txn = await sync_to_async(EscrowService.create_transaction)(
                buyer=buyer,
                seller=gl.seller,
                group_listing=gl,
                amount=amount,
                currency=currency,
                usd_equivalent=gl.price_usd
            )

            # Create charge
            ok, charge = await sync_to_async(PaymentService.create_payment_charge)(
                transaction=txn,
                redirect_url=f"https://t.me/{user.username}" if user.username else None,
                cancel_url=None
            )

            if not ok:
                await query.edit_message_text(
                    "❌ Failed to create payment link. Please try again later."
                )
                return ConversationHandler.END

            payment_url = charge.get('payment_url')
            await query.edit_message_text(
                f"✅ Escrow created!\n\n"
                f"Transaction ID: `{txn.id}`\n"
                f"Amount: {txn.amount} {txn.currency}\n\n"
                f"👉 Complete your payment here:\n{payment_url}",
                parse_mode=ParseMode.MARKDOWN
            )

            context.user_data.clear()
            return ConversationHandler.END
        except Exception as e:
            logger.error(f"transaction_confirm error: {str(e)}")
            await query.edit_message_text("❌ Failed to create transaction.")
            return ConversationHandler.END

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Log Errors caused by Updates."""
        logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)

        if update and hasattr(update, 'effective_message') and update.effective_message:
            await update.effective_message.reply_text("❌ An unexpected error occurred. Please try again.")

    # --- Database Helper Methods ---

    @staticmethod
    @sync_to_async
    def _get_telegram_user(telegram_id: int) -> Optional[TelegramUser]:
        """Get TelegramUser by telegram_id"""
        try:
            return TelegramUser.objects.get(telegram_id=telegram_id)
        except TelegramUser.DoesNotExist:
            return None

    @staticmethod
    @sync_to_async
    def _get_or_create_telegram_user(user: 'telegram.User') -> TelegramUser:
        """Get or create TelegramUser from Telegram user object"""
        try:
            return TelegramUser.objects.select_related('user').get(telegram_id=user.id)
        except TelegramUser.DoesNotExist:
            from django.contrib.auth.models import User
            django_user = User.objects.create_user(username=f"user_{user.id}", password=User.objects.make_random_password())
            return TelegramUser.objects.create(
                user=django_user,
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )

    @staticmethod
    @sync_to_async
    def _save_telegram_user(telegram_user: TelegramUser):
        """Save a TelegramUser instance"""
        telegram_user.save()

    @staticmethod
    @sync_to_async
    def _get_user_transaction_count(telegram_user: TelegramUser, role: str) -> int:
        """Get user's transaction count as buyer or seller"""
        if role == 'buyer':
            return EscrowTransaction.objects.filter(buyer=telegram_user).count()
        return EscrowTransaction.objects.filter(seller=telegram_user).count()

    @staticmethod
    @sync_to_async
    def _get_user_active_listings_count(telegram_user: TelegramUser) -> int:
        """Get user's active listings count"""
        return GroupListing.objects.filter(seller=telegram_user, status='ACTIVE').count()

    @staticmethod
    @sync_to_async
    def _log_message(user_id: int, command: str, text: str):
        """Log user message to database"""
        try:
            telegram_user = TelegramUser.objects.get(telegram_id=user_id)
            BotMessage.objects.create(
                telegram_user=telegram_user,
                message_type='COMMAND',
                text=text,
                command=command,
                chat_id=user_id
            )
        except TelegramUser.DoesNotExist:
            pass  # User not registered yet

    def run(self):
        """Run the bot"""
        logger.info("Starting bot...")
        # The actual polling is handled in main()
        pass


def main(token: Optional[str] = None):
    """Main function to run the bot"""
    
    # Get bot token from argument or environment
    bot_token = token or settings.TELEGRAM_BOT_TOKEN
    
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
        return
    
    # Create bot instance
    bot = TrustlinkBot(bot_token)
    
    # Run the bot until the user presses Ctrl-C
    logger.info("Starting bot polling...")
    
    # Create application and run it
    application = bot.application
    
    # Run the bot until the user presses Ctrl-C
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
        close_loop=False
    )

if __name__ == '__main__':
    main()
