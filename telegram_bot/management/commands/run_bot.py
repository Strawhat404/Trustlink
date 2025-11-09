"""
Run Telegram Bot Management Command

This Django management command starts the Trustlink Telegram bot.
It provides a clean way to run the bot as part of the Django project
with proper logging and error handling.

Usage:
    python manage.py run_bot
"""

from django.core.management.base import BaseCommand
from django.conf import settings
import logging

from telegram_bot.bot import main_async as run_bot_main_async

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Start the Trustlink Telegram bot'

    def add_arguments(self, parser):
        parser.add_argument(
            '--token',
            type=str,
            help='Telegram bot token (overrides settings)',
        )

    def handle(self, *args, **options):
        """
        Main command handler that starts the Telegram bot
        """
        import asyncio
        
        # Get bot token
        bot_token = options.get('token') or settings.TELEGRAM_BOT_TOKEN
        
        if not bot_token:
            self.stdout.write(
                self.style.ERROR(
                    'TELEGRAM_BOT_TOKEN not found in environment variables.\n'
                    'Please set TELEGRAM_BOT_TOKEN in your .env file or use --token argument.'
                )
            )
            return
        
        self.stdout.write("Starting Trustlink Telegram Bot...")
        self.stdout.write(f"Bot token: {bot_token[:10]}...")
        self.stdout.write(self.style.SUCCESS('Starting bot... Press Ctrl+C to stop.'))
        
        try:
            import asyncio
            import nest_asyncio
            nest_asyncio.apply()
            asyncio.run(run_bot_main_async(token=bot_token))
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\nBot stopped by user.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'An unexpected error occurred: {str(e)}'))
            logger.error(f"Bot startup error: {str(e)}")
