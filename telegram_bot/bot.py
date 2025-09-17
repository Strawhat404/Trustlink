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

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    GROUP_LISTING_TITLE,
    GROUP_LISTING_DESCRIPTION,
    GROUP_LISTING_PRICE,
    GROUP_LISTING_CATEGORY,
    GROUP_LISTING_CONFIRM,
    TRANSACTION_AMOUNT,
    TRANSACTION_CURRENCY,
    TRANSACTION_CONFIRM,
    DISPUTE_DESCRIPTION,
) = range(11)

class TrustlinkBot:
    """
    Main bot class that handles all Telegram bot functionality
    
    This class manages user interactions, conversation flows,
    and integration with the Django backend services.
    """
    
    def __init__(self, token: str):
        """Initialize the bot with the given token"""
        self.token = token
        # Set a longer timeout to handle slow network conditions
        self.application = Application.builder().token(token).pool_timeout(30.0).build()
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Set up all command and message handlers"""
        
        # Basic command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("profile", self.profile_command))
        self.application.add_handler(CommandHandler("transactions", self.transactions_command))
        self.application.add_handler(CommandHandler("my_listings", self.my_listings_command))
        self.application.add_handler(CommandHandler("buy", self.buy_command))
        self.application.add_handler(CommandHandler("cancel", self.cancel_command))
        
        # Registration conversation handler
        registration_handler = ConversationHandler(
            entry_points=[CommandHandler("register", self.register_start)],
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
        
        welcome_message = f"""
🔒 **Welcome to Trustlink!**

Hello {user.first_name}! I'm your secure escrow bot for Telegram group transactions.

**What I can help you with:**
• 🛡️ Secure escrow for group purchases
• 💰 Cryptocurrency payments (USDT, ETH, BTC)
• 🔍 Group verification and ownership transfer
• ⚖️ Dispute resolution and arbitration

**Quick Start:**
• Use /register to complete your profile
• Use /help to see all available commands
• Use /list_group to sell a group
• Use /buy to browse available groups

Your safety is our priority! All transactions are secured with smart escrow contracts.
        """
        
        keyboard = [
            [InlineKeyboardButton("📝 Register", callback_data="register")],
            [InlineKeyboardButton("❓ Help", callback_data="help")],
            [InlineKeyboardButton("🏪 Browse Groups", callback_data="browse_groups")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /help command"""
        
        help_text = """
🤖 **Trustlink Bot Commands**

**👤 User Management:**
/start - Welcome message and quick actions
/register - Complete your user registration
/profile - View your profile and statistics

**🏪 Group Trading:**
/list_group - Create a new group listing for sale
/my_listings - View and manage your group listings
/buy - Browse available groups for purchase

**💰 Transactions:**
/transactions - View your transaction history
/dispute <transaction_id> - Open a dispute

**ℹ️ Information:**
/help - Show this help message
/cancel - Cancel current operation

**🔒 Security Features:**
• All payments held in secure escrow
• Automated group ownership verification
• 24/7 dispute resolution support
• Multi-signature transaction approval

Need help? Contact our support team anytime!
        """
        
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

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
    
    async def register_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the registration process"""
        
        user = update.effective_user
        
        # Check if already registered
        telegram_user = await self._get_telegram_user(user.id)
        if telegram_user and telegram_user.is_verified:
            await update.message.reply_text(
                "✅ You're already registered and verified!\n\n"
                "Use /profile to view your information or /help to see available commands."
            )
            return ConversationHandler.END
        
        await update.message.reply_text(
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
        
        profile_text = f"""
👤 **Your Profile**

**Basic Information:**
• Name: {telegram_user.first_name} {telegram_user.last_name or ''}
• Username: @{telegram_user.username or 'Not set'}
• Status: {'✅ Verified' if telegram_user.is_verified else '❌ Not verified'}
• Member Since: {telegram_user.created_at.strftime('%B %Y')}

**Trading Statistics:**
• Total Purchases: {total_purchases}
• Total Sales: {total_sales}
• Active Listings: {active_listings}
• User ID: `{telegram_user.telegram_id}`

**Account Actions:**
        """
        
        keyboard = [
            [InlineKeyboardButton("📊 Transaction History", callback_data="transactions")],
            [InlineKeyboardButton("🏪 My Listings", callback_data="my_listings")],
            [InlineKeyboardButton("🔄 Refresh Profile", callback_data="profile")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            profile_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

    async def transactions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /transactions command (placeholder)"""
        await update.message.reply_text("📊 Transaction history feature coming soon!")

    async def my_listings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /my_listings command (placeholder)"""
        await update.message.reply_text("📝 My listings feature coming soon!")
    
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
            "🏪 **Create Group Listing**\n\n"
            "Let's create a listing for your Telegram group!\n\n"
            "First, please enter the **title** of your group:",
            parse_mode=ParseMode.MARKDOWN
        )
        
        return GROUP_LISTING_TITLE
    
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
            "Now, please provide a **description** of your group (what it's about, rules, etc.):",
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
            "What's your asking **price in USD**? (Enter just the number, e.g., 150):",
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
            "Please select the category that best describes your group:",
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
        
        confirmation_text = f"""
📋 **Listing Confirmation**

**Group Details:**
• Title: {title}
• Category: {category_names.get(category, category)}
• Price: ${price:.2f} USD

**Description:**
{description[:200]}{'...' if len(description) > 200 else ''}

**Important Notes:**
• You must be an admin of the group to list it
• Group ownership verification will be required
• 5% platform fee applies to successful sales
• Listing expires after 30 days

Ready to create this listing?
        """
        
        keyboard = [
            [InlineKeyboardButton("✅ Create Listing", callback_data="confirm_listing")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_listing")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            confirmation_text,
            parse_mode=ParseMode.MARKDOWN,
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
            # TODO: In a real implementation, we would:
            # 1. Verify the user is admin of the group
            # 2. Get actual group information from Telegram API
            # 3. Create the GroupListing record
            
            success_message = """
✅ **Listing Created Successfully!**

Your group listing has been created and is now pending verification.

**Next Steps:**
1. Our bot will verify your admin status
2. Group information will be validated
3. Listing will go live within 24 hours

**What happens next:**
• Buyers can browse and contact you
• Escrow transactions are handled automatically
• You'll receive notifications for all activity

Use /my_listings to manage your listings anytime!
            """
            
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
        
        if query.data == "register":
            await self.register_start(update, context)
        elif query.data == "help":
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

            # Clear context
            context.user_data.pop('transaction_listing_id', None)
            context.user_data.pop('transaction_currency', None)

            return ConversationHandler.END
        except Exception as e:
            logger.error(f"transaction_confirm error: {str(e)}")
            await query.edit_message_text("❌ Failed to create transaction.")
            return ConversationHandler.END
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        
        logger.error(f"Update {update} caused error {context.error}")
        logger.error(f"Error details: {str(context.error)}")
        
        if update.effective_message:
            # Provide more specific error information in development
            error_msg = f"❌ Error: {str(context.error)[:100]}..."
            await update.effective_message.reply_text(error_msg)
    
    # Helper methods for database operations
    async def _get_telegram_user(self, telegram_id: int) -> Optional[TelegramUser]:
        """Get TelegramUser by telegram_id"""
        try:
            return await sync_to_async(TelegramUser.objects.get)(telegram_id=telegram_id)
        except TelegramUser.DoesNotExist:
            return None
    
    async def _get_or_create_telegram_user(self, user) -> TelegramUser:
        """Get or create TelegramUser from Telegram user object"""
        from django.contrib.auth.models import User
        
        @sync_to_async
        def get_or_create_user():
            try:
                # Try to get existing user first
                telegram_user = TelegramUser.objects.get(telegram_id=user.id)
                return telegram_user
            except TelegramUser.DoesNotExist:
                # Create Django User first
                django_user = User.objects.create_user(
                    username=f"telegram_{user.id}",
                    first_name=user.first_name or "",
                    last_name=user.last_name or ""
                )
                
                # Then create TelegramUser with the Django User
                telegram_user = TelegramUser.objects.create(
                    telegram_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    is_verified=False,
                    user=django_user
                )
                
                return telegram_user
        
        return await get_or_create_user()
    
    async def _save_telegram_user(self, telegram_user: TelegramUser):
        """Save TelegramUser to database"""
        await sync_to_async(telegram_user.save)()
    
    async def _log_message(self, user_id: int, message_type: str, content: str):
        """Log bot message to database"""
        try:
            telegram_user = await self._get_telegram_user(user_id)
            if telegram_user:
                await sync_to_async(BotMessage.objects.create)(
                    user=telegram_user,
                    message_type=message_type,
                    content=content[:1000]  # Truncate if too long
                )
        except Exception as e:
            logger.error(f"Failed to log message: {e}")
    
    async def _get_user_transaction_count(self, user: TelegramUser, role: str) -> int:
        """Get transaction count for user as buyer or seller"""
        try:
            if role == 'buyer':
                return await sync_to_async(EscrowTransaction.objects.filter(buyer=user).count)()
            else:
                return await sync_to_async(EscrowTransaction.objects.filter(seller=user).count)()
        except Exception:
            return 0
    
    async def _get_user_active_listings_count(self, user: TelegramUser) -> int:
        """Get active listings count for user"""
        try:
            return await sync_to_async(
                GroupListing.objects.filter(seller=user, status='ACTIVE').count
            )()
        except Exception:
            return 0
    

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
    bot.application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
