"""
Telegram Notification Service

This service handles sending notifications to users via the Telegram Bot API.
It is designed to be called from the Django backend (e.g., from escrow services)
to decouple the notification logic from the main application flow.
"""

import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class NotificationService:
    """
    A service for sending Telegram notifications directly via the Bot API.
    """
    
    BASE_URL = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"

    @classmethod
    def send_message(cls, chat_id: int, text: str, parse_mode: str = 'Markdown') -> bool:
        """
        Sends a message to a specific Telegram chat ID.

        Args:
            chat_id: The user's Telegram chat ID.
            text: The message text to send.
            parse_mode: The parse mode for the message (Markdown or HTML).

        Returns:
            True if the message was sent successfully, False otherwise.
        """
        url = f"{cls.BASE_URL}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': parse_mode
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()  # Raise an exception for bad status codes
            
            if response.json().get('ok'):
                logger.info(f"Successfully sent notification to chat_id {chat_id}")
                return True
            else:
                logger.error(f"Failed to send notification to {chat_id}: {response.text}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending notification to {chat_id}: {e}")
            return False
