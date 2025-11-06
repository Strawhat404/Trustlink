#!/usr/bin/env python3
"""
Direct bot test without Django management command
"""
import os
import sys
import django

# Add Django project to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "trustlink_backend.settings")

# Setup Django
django.setup()

# Now import and run the bot
from telegram_bot.bot import main_async
import asyncio

if __name__ == "__main__":
    token = "8437815193:AAG0JzpXsOeGS6QmPUs9hy1ajedd5jd1Ngk"
    print("Starting bot directly...")
    asyncio.run(main_async(token))