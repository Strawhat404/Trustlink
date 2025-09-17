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
import asyncio

from telegram_bot.bot import TrustlinkBot

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
        
        bot = TrustlinkBot(bot_token)
        
        self.stdout.write(
            self.style.SUCCESS(
                'Bot started successfully! Press Ctrl+C to stop.'
            )
        )
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If a loop is already running, just run the bot's main coroutine
                task = loop.create_task(bot.run())
                # A simple way to keep the command alive
                while not task.done():
                    loop.run_until_complete(asyncio.sleep(1))
            else:
                # If no loop is running, we can run it until completion
                asyncio.run(bot.run())
        except KeyboardInterrupt:
            self.stdout.write(
                self.style.WARNING('\nBot stopped by user.')
            )
            # In a real async environment, you'd call bot.stop() here
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Bot error: {str(e)}')
            )
            logger.error(f"Bot startup error: {str(e)}")
