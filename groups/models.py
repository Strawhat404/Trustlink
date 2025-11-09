from django.db import models
from django.utils import timezone
import uuid
from escrow.models import TelegramUser

class GroupListing(models.Model):
    """Model for Telegram group listings"""
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ACTIVE', 'Active'),
        ('SOLD', 'Sold'),
        ('SUSPENDED', 'Suspended'),
        ('EXPIRED', 'Expired'),
    ]
    
    CATEGORY_CHOICES = [
        ('CRYPTO', 'Cryptocurrency'),
        ('TRADING', 'Trading'),
        ('TECH', 'Technology'),
        ('BUSINESS', 'Business'),
        ('EDUCATION', 'Education'),
        ('ENTERTAINMENT', 'Entertainment'),
        ('OTHER', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(TelegramUser, on_delete=models.CASCADE, related_name='group_listings')
    
    # Group Information
    group_id = models.BigIntegerField(unique=True)
    group_username = models.CharField(max_length=100, blank=True, null=True)
    group_title = models.CharField(max_length=200)
    group_description = models.TextField(blank=True)
    member_count = models.IntegerField()
    
    # Listing Details
    price_usd = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='OTHER')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    
    # Metadata Snapshots (for verification)
    creation_date = models.DateTimeField(null=True, blank=True)
    pinned_message = models.TextField(blank=True)
    admin_list_snapshot = models.JSONField(default=list)
    
    # Listing Management
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    # Bot validation
    bot_is_admin = models.BooleanField(default=False)
    last_verified = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['seller', 'status']),
            models.Index(fields=['category', 'status']),
            models.Index(fields=['group_id']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f"{self.group_title} - ${self.price_usd}"
    
    def is_expired(self):
        """Check if listing has expired"""
        if self.expires_at and timezone.now() > self.expires_at:
            return True
        return False

class GroupStateLog(models.Model):
    """
    Stores periodic snapshots of a group's state for monitoring.
    """
    listing = models.ForeignKey(GroupListing, on_delete=models.CASCADE, related_name='state_logs')
    timestamp = models.DateTimeField(auto_now_add=True)
    member_count = models.IntegerField(default=0)
    public_link = models.CharField(max_length=255, null=True, blank=True)
    title = models.CharField(max_length=255)
    description_hash = models.CharField(max_length=64)  # SHA256 hash of the description

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"Log for {self.listing.group_title} at {self.timestamp}"

class AdminChangeLog(models.Model):
    """
    Logs changes in group administrators for security auditing.
    """
    listing = models.ForeignKey(GroupListing, on_delete=models.CASCADE, related_name='admin_changes')
    timestamp = models.DateTimeField(auto_now_add=True)
    admin_user_id = models.BigIntegerField()
    admin_username = models.CharField(max_length=255, null=True, blank=True)
    action = models.CharField(max_length=50, choices=[('added', 'Admin Added'), ('removed', 'Admin Removed')])
    performed_by_user_id = models.BigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.action.capitalize()} admin {self.admin_username} for {self.listing.group_title}"

class GroupMetadataSnapshot(models.Model):
    """Store group metadata snapshots for verification"""
    
    SNAPSHOT_TYPE_CHOICES = [
        ('LISTING_CREATED', 'Listing Created'),
        ('PRE_TRANSFER', 'Pre Transfer'),
        ('POST_TRANSFER', 'Post Transfer'),
        ('VERIFICATION', 'Verification Check'),
    ]
    
    group_listing = models.ForeignKey(GroupListing, on_delete=models.CASCADE, related_name='metadata_snapshots')
    transaction = models.ForeignKey('escrow.EscrowTransaction', on_delete=models.CASCADE, null=True, blank=True)
    
    snapshot_type = models.CharField(max_length=20, choices=SNAPSHOT_TYPE_CHOICES)
    
    # Group data at time of snapshot
    group_title = models.CharField(max_length=200)
    group_username = models.CharField(max_length=100, blank=True, null=True)
    group_description = models.TextField(blank=True)
    member_count = models.IntegerField()
    admin_list = models.JSONField(default=list)
    creator_id = models.BigIntegerField(null=True, blank=True)
    pinned_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Snapshot {self.snapshot_type} - {self.group_listing.group_title}"

class GroupTransferLog(models.Model):
    """Log group ownership transfer events"""
    
    EVENT_TYPE_CHOICES = [
        ('BUYER_ADDED', 'Buyer Added to Group'),
        ('BUYER_PROMOTED', 'Buyer Promoted to Admin'),
        ('OWNERSHIP_TRANSFERRED', 'Ownership Transferred'),
        ('SELLER_LEFT', 'Seller Left Group'),
        ('VERIFICATION_COMPLETED', 'Verification Completed'),
    ]
    
    transaction = models.ForeignKey('escrow.EscrowTransaction', on_delete=models.CASCADE, related_name='transfer_logs')
    event_type = models.CharField(max_length=30, choices=EVENT_TYPE_CHOICES)
    
    # Event details
    old_owner_id = models.BigIntegerField(null=True, blank=True)
    new_owner_id = models.BigIntegerField(null=True, blank=True)
    admin_changes = models.JSONField(default=dict)
    
    # Metadata
    detected_at = models.DateTimeField(auto_now_add=True)
    verified = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.event_type} - {self.detected_at}"

class GroupVerificationResult(models.Model):
    """Store verification results for group transfers"""
    
    RESULT_CHOICES = [
        ('PENDING', 'Verification Pending'),
        ('PASSED', 'Verification Passed'),
        ('FAILED', 'Verification Failed'),
        ('MANUAL_REVIEW', 'Requires Manual Review'),
    ]
    
    transaction = models.OneToOneField('escrow.EscrowTransaction', on_delete=models.CASCADE, related_name='verification_result')
    
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, default='PENDING')
    
    # Verification checks
    ownership_verified = models.BooleanField(default=False)
    metadata_matches = models.BooleanField(default=False)
    admin_permissions_correct = models.BooleanField(default=False)
    
    # Detailed results
    verification_details = models.JSONField(default=dict)
    failure_reasons = models.JSONField(default=list)
    
    verified_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Verification {self.result} - {self.transaction.id}"
