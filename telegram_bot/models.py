from django.db import models
from django.utils import timezone

class BotSession(models.Model):
    """Track user bot sessions and conversation state"""
    
    STATE_CHOICES = [
        ('IDLE', 'Idle'),
        ('REGISTERING', 'Registration Flow'),
        ('BROWSING_LISTINGS', 'Browsing Listings'),
        ('CREATING_LISTING', 'Creating Listing'),
        ('PURCHASING', 'Purchase Flow'),
        ('TRANSFER_GUIDE', 'Transfer Guide'),
        ('DISPUTE', 'Dispute Flow'),
    ]
    
    telegram_user = models.OneToOneField('escrow.TelegramUser', on_delete=models.CASCADE)
    current_state = models.CharField(max_length=20, choices=STATE_CHOICES, default='IDLE')
    session_data = models.JSONField(default=dict)  # Store temporary conversation data
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Session {self.telegram_user.username} - {self.current_state}"

class BotMessage(models.Model):
    """Log bot messages for debugging and analytics"""
    
    MESSAGE_TYPE_CHOICES = [
        ('INCOMING', 'User to Bot'),
        ('OUTGOING', 'Bot to User'),
        ('COMMAND', 'Bot Command'),
        ('CALLBACK', 'Callback Query'),
    ]
    
    telegram_user = models.ForeignKey('escrow.TelegramUser', on_delete=models.CASCADE, related_name='bot_messages')
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPE_CHOICES)
    
    # Message content
    text = models.TextField(blank=True)
    message_id = models.BigIntegerField(null=True, blank=True)
    chat_id = models.BigIntegerField()
    
    # Metadata
    command = models.CharField(max_length=50, blank=True, null=True)
    callback_data = models.CharField(max_length=200, blank=True, null=True)
    raw_data = models.JSONField(default=dict)
    
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.message_type} - {self.telegram_user.username} - {self.timestamp}"

class BotNotification(models.Model):
    """Queue notifications to be sent to users"""
    
    NOTIFICATION_TYPE_CHOICES = [
        ('PAYMENT_RECEIVED', 'Payment Received'),
        ('TRANSFER_REMINDER', 'Transfer Reminder'),
        ('VERIFICATION_COMPLETE', 'Verification Complete'),
        ('DISPUTE_UPDATE', 'Dispute Update'),
        ('SYSTEM_ALERT', 'System Alert'),
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('SENT', 'Sent'),
        ('FAILED', 'Failed'),
    ]
    
    telegram_user = models.ForeignKey('escrow.TelegramUser', on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPE_CHOICES)
    
    title = models.CharField(max_length=200)
    message = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    
    # Scheduling
    send_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    transaction = models.ForeignKey('escrow.EscrowTransaction', on_delete=models.CASCADE, null=True, blank=True)
    extra_data = models.JSONField(default=dict)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.notification_type} - {self.telegram_user.username}"
