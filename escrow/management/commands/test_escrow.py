"""
Test Escrow System Management Command

This command creates sample data to test the escrow system functionality.
It creates test users, group listings, and transactions to verify that
all the business logic works correctly.

Usage:
    python manage.py test_escrow
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
import uuid

from escrow.models import TelegramUser, EscrowTransaction
from groups.models import GroupListing
from escrow.services import EscrowService

class Command(BaseCommand):
    help = 'Create test data for the escrow system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clean',
            action='store_true',
            help='Clean existing test data before creating new data',
        )

    def handle(self, *args, **options):
        """
        Main command handler that creates comprehensive test data
        """
        
        if options['clean']:
            self.stdout.write("Cleaning existing test data...")
            self._clean_test_data()
        
        self.stdout.write("Creating test data for escrow system...")
        
        try:
            with transaction.atomic():
                # Create test users
                buyer, seller = self._create_test_users()
                
                # Create test group listing
                group_listing = self._create_test_group_listing(seller)
                
                # Create test escrow transaction
                escrow_transaction = self._create_test_transaction(buyer, seller, group_listing)
                
                # Test service methods
                self._test_service_methods(escrow_transaction)
                
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully created test data:\n"
                    f"- Buyer: {buyer.username} (ID: {buyer.telegram_id})\n"
                    f"- Seller: {seller.username} (ID: {seller.telegram_id})\n"
                    f"- Group: {group_listing.group_title}\n"
                    f"- Transaction: {escrow_transaction.id}\n"
                    f"\nYou can now test the system in Django admin at /admin/"
                )
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error creating test data: {str(e)}")
            )
    
    def _clean_test_data(self):
        """Remove existing test data"""
        
        # Delete test transactions (will cascade to related objects)
        EscrowTransaction.objects.filter(
            buyer__username__startswith='test_'
        ).delete()
        
        # Delete test group listings
        GroupListing.objects.filter(
            seller__username__startswith='test_'
        ).delete()
        
        # Delete test users
        TelegramUser.objects.filter(
            username__startswith='test_'
        ).delete()
        
        self.stdout.write("Cleaned existing test data")
    
    def _create_test_users(self):
        """Create test buyer and seller users"""
        
        from django.contrib.auth.models import User
        
        # Create Django User instances first
        buyer_user = User.objects.create_user(
            username='test_buyer_django',
            email='buyer@test.com'
        )
        
        seller_user = User.objects.create_user(
            username='test_seller_django',
            email='seller@test.com'
        )
        
        buyer = TelegramUser.objects.create(
            user=buyer_user,
            telegram_id=123456789,
            username='test_buyer',
            first_name='Test',
            last_name='Buyer',
            is_verified=True
        )
        
        seller = TelegramUser.objects.create(
            user=seller_user,
            telegram_id=987654321,
            username='test_seller',
            first_name='Test',
            last_name='Seller',
            is_verified=True
        )
        
        self.stdout.write(f"Created test users: {buyer.username}, {seller.username}")
        return buyer, seller
    
    def _create_test_group_listing(self, seller):
        """Create a test group listing"""
        
        group_listing = GroupListing.objects.create(
            seller=seller,
            group_id=-1001234567890,
            group_username='test_crypto_group',
            group_title='Test Crypto Trading Group',
            group_description='A test group for cryptocurrency trading discussions',
            price_usd=Decimal('150.00'),
            member_count=5420,
            category='CRYPTO',
            status='ACTIVE'
        )
        
        self.stdout.write(f"Created test group listing: {group_listing.group_title}")
        return group_listing
    
    def _create_test_transaction(self, buyer, seller, group_listing):
        """Create a test escrow transaction"""
        
        escrow_transaction = EscrowService.create_transaction(
            buyer=buyer,
            seller=seller,
            group_listing=group_listing,
            amount=Decimal('150.00'),
            currency='USDT',
            usd_equivalent=Decimal('150.00')
        )
        
        self.stdout.write(f"Created test transaction: {escrow_transaction.id}")
        return escrow_transaction
    
    def _test_service_methods(self, transaction):
        """Test various service methods with the created transaction"""
        
        self.stdout.write("Testing service methods...")
        
        # Test getting transaction status
        status_info = EscrowService.get_transaction_status(transaction.id)
        if status_info:
            self.stdout.write(f"✓ Transaction status retrieved: {status_info['status']}")
        
        # Test getting user transactions
        buyer_transactions = EscrowService.get_user_transactions(transaction.buyer)
        if buyer_transactions:
            self.stdout.write(f"✓ Buyer transactions retrieved: {len(buyer_transactions)} transactions")
        
        seller_transactions = EscrowService.get_user_transactions(transaction.seller)
        if seller_transactions:
            self.stdout.write(f"✓ Seller transactions retrieved: {len(seller_transactions)} transactions")
        
        # Test dispute creation
        dispute = EscrowService.create_dispute(
            transaction_id=transaction.id,
            opened_by=transaction.buyer,
            description="Test dispute - payment not received as expected"
        )
        if dispute:
            self.stdout.write(f"✓ Test dispute created: {dispute.id}")
        
        self.stdout.write("Service method testing completed")
