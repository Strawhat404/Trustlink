"""
Django Management Command: start_server

This command starts the Django development server with specific settings
optimized for webhook testing and development.

Usage:
    python manage.py start_server [--port PORT] [--host HOST]
"""

from django.core.management.base import BaseCommand
from django.core.management import execute_from_command_line
import sys

class Command(BaseCommand):
    help = 'Start Django development server for webhook testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--port',
            type=int,
            default=8000,
            help='Port to run the server on (default: 8000)'
        )
        parser.add_argument(
            '--host',
            type=str,
            default='0.0.0.0',
            help='Host to bind to (default: 0.0.0.0 for external access)'
        )

    def handle(self, *args, **options):
        port = options['port']
        host = options['host']
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Starting Django server on {host}:{port}...'
            )
        )
        
        self.stdout.write(
            f'Webhook endpoint will be available at: http://{host}:{port}/escrow/webhooks/coinbase/'
        )
        
        # Start the development server
        sys.argv = ['manage.py', 'runserver', f'{host}:{port}']
        execute_from_command_line(sys.argv)
