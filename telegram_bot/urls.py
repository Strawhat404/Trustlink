"""
Telegram Bot URL Configuration

This module defines URL patterns for the telegram_bot app.
Currently contains placeholder patterns - will be expanded
when bot features are implemented.
"""

from django.urls import path
from . import views

# Define the app namespace for URL reversing
app_name = 'telegram_bot'

urlpatterns = [
    # Placeholder patterns - to be implemented in future phases
    # path('api/bot/webhook/', views.telegram_webhook, name='telegram_webhook'),
    # path('api/bot/status/', views.bot_status, name='bot_status'),
]
