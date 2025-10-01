from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid


class TelegramUser(models.Model):
    """Extended user model for Telegram users"""

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    telegram_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=100, blank=True, null=True)
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"@{self.username or self.telegram_id}"


class EscrowTransaction(models.Model):
    """Core escrow transaction model"""

    STATUS_CHOICES = [
        ("PENDING", "Pending Payment"),
        ("FUNDED", "Escrow Funded"),
        ("AWAITING_TRANSFER", "Awaiting Group Transfer"),
        ("VERIFYING", "Verifying Transfer"),
        ("COMPLETED", "Transfer Completed"),
        ("REFUNDED", "Refunded to Buyer"),
        ("DISPUTED", "Under Dispute"),
        ("CANCELLED", "Cancelled"),
    ]

    CURRENCY_CHOICES = [
        ("USDT", "USDT (Tether)"),
        ("ETH", "Ethereum"),
        ("BTC", "Bitcoin"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    buyer = models.ForeignKey(
        TelegramUser, on_delete=models.CASCADE, related_name="purchases"
    )
    seller = models.ForeignKey(
        TelegramUser, on_delete=models.CASCADE, related_name="sales"
    )
    group_listing = models.ForeignKey("groups.GroupListing", on_delete=models.CASCADE)

    # Payment details
    amount = models.DecimalField(max_digits=20, decimal_places=8)
    currency = models.CharField(max_length=10, choices=CURRENCY_CHOICES)
    usd_equivalent = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    # Transaction state
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    # Coinbase Commerce charge references
    payment_charge_id = models.CharField(max_length=100, blank=True, null=True)
    payment_charge_url = models.URLField(blank=True, null=True)
    payment_address = models.CharField(max_length=200, blank=True, null=True)
    payment_tx_hash = models.CharField(max_length=200, blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    funded_at = models.DateTimeField(null=True, blank=True)
    transfer_deadline = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Escrow {self.id} - {self.status}"

    def is_expired(self):
        """Check if transfer deadline has passed"""
        if self.transfer_deadline and timezone.now() > self.transfer_deadline:
            return True
        return False


class PaymentWebhook(models.Model):
    """Store payment webhook data for audit trail"""

    transaction = models.ForeignKey(
        EscrowTransaction, on_delete=models.CASCADE, related_name="webhooks"
    )
    webhook_data = models.JSONField()
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Webhook for {self.transaction.id}"


class DisputeCase(models.Model):
    """Handle dispute cases with a formal arbitration process"""

    STATUS_CHOICES = [
        ("OPEN", "Open"),
        ("INVESTIGATING", "Under Investigation"),
        ("AWAITING_RULING", "Awaiting Ruling"),
        ("RESOLVED", "Resolved"),
        ("CLOSED", "Closed"),
    ]

    RULING_CHOICES = [
        ("FAVOR_SELLER", "Favor Seller - Release Funds"),
        ("FAVOR_BUYER", "Favor Buyer - Refund"),
        ("PARTIAL_REFUND", "Partial Refund"),
        ("NO_ACTION", "No Action"),
    ]

    transaction = models.OneToOneField(
        EscrowTransaction, on_delete=models.CASCADE, related_name="dispute_case"
    )
    opened_by = models.ForeignKey(TelegramUser, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="OPEN")
    description = models.TextField()

    # Arbitration fields
    arbitrator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="arbitrated_cases",
    )
    evidence = models.JSONField(
        default=dict, blank=True, help_text="Links to screenshots, message IDs, etc."
    )

    # Resolution fields
    ruling = models.CharField(
        max_length=20, choices=RULING_CHOICES, null=True, blank=True
    )
    resolution_notes = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_disputes",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Dispute {self.id} for Txn {self.transaction_id} - {self.status}"


class AuditLog(models.Model):
    """Comprehensive audit logging"""

    ACTION_CHOICES = [
        ("ESCROW_CREATED", "Escrow Created"),
        ("PAYMENT_RECEIVED", "Payment Received"),
        ("TRANSFER_STARTED", "Transfer Started"),
        ("OWNERSHIP_CHANGED", "Ownership Changed"),
        ("VERIFICATION_PASSED", "Verification Passed"),
        ("VERIFICATION_FAILED", "Verification Failed"),
        ("FUNDS_RELEASED", "Funds Released"),
        ("FUNDS_REFUNDED", "Funds Refunded"),
        ("DISPUTE_OPENED", "Dispute Opened"),
        ("DISPUTE_RESOLVED", "Dispute Resolved"),
    ]

    transaction = models.ForeignKey(
        EscrowTransaction, on_delete=models.CASCADE, related_name="audit_logs"
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    user = models.ForeignKey(
        TelegramUser, on_delete=models.SET_NULL, null=True, blank=True
    )
    details = models.JSONField(default=dict)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.action} - {self.timestamp}"
