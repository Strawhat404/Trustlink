from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import (
    TelegramUser, 
    EscrowTransaction, 
    PaymentWebhook, 
    DisputeCase, 
    AuditLog
)

# =============================================================================
# TELEGRAM USER ADMIN
# =============================================================================

@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    """
    Admin interface for managing Telegram users
    Provides comprehensive view of user data and verification status
    """
    
    # Fields to display in the admin list view
    list_display = [
        'telegram_id', 
        'username', 
        'full_name', 
        'is_verified', 
        'total_purchases', 
        'total_sales',
        'created_at'
    ]
    
    # Fields that can be used for filtering in the admin
    list_filter = [
        'is_verified', 
        'created_at', 
        'updated_at'
    ]
    
    # Fields that can be searched
    search_fields = [
        'telegram_id', 
        'username', 
        'first_name', 
        'last_name'
    ]
    
    # Read-only fields that cannot be edited
    readonly_fields = [
        'telegram_id', 
        'created_at', 
        'updated_at',
        'total_purchases',
        'total_sales'
    ]
    
    # How to organize fields in the detail view
    fieldsets = (
        ('Basic Information', {
            'fields': ('telegram_id', 'username', 'first_name', 'last_name')
        }),
        ('Status', {
            'fields': ('is_verified',)
        }),
        ('Statistics', {
            'fields': ('total_purchases', 'total_sales'),
            'classes': ('collapse',)  # Make this section collapsible
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def full_name(self, obj):
        """
        Display user's full name combining first and last name
        Used in the list display
        """
        if obj.first_name and obj.last_name:
            return f"{obj.first_name} {obj.last_name}"
        elif obj.first_name:
            return obj.first_name
        else:
            return "No name provided"
    full_name.short_description = "Full Name"
    
    def total_purchases(self, obj):
        """
        Count total number of purchases made by this user
        """
        return obj.purchases.count()
    total_purchases.short_description = "Total Purchases"
    
    def total_sales(self, obj):
        """
        Count total number of sales made by this user
        """
        return obj.sales.count()
    total_sales.short_description = "Total Sales"

# =============================================================================
# ESCROW TRANSACTION ADMIN
# =============================================================================

@admin.register(EscrowTransaction)
class EscrowTransactionAdmin(admin.ModelAdmin):
    """
    Admin interface for managing escrow transactions
    This is the core of the system - handles all buy/sell transactions
    """
    
    # Fields to display in the admin list view
    list_display = [
        'id_short',
        'buyer_link',
        'seller_link', 
        'amount_display',
        'status_colored',
        'created_at',
        'days_since_created'
    ]
    
    # Fields for filtering transactions
    list_filter = [
        'status',
        'currency', 
        'created_at',
        'funded_at',
        'completed_at'
    ]
    
    # Fields that can be searched
    search_fields = [
        'id',
        'buyer__username',
        'seller__username',
        'group_listing__group_title',
        'payment_tx_hash'
    ]
    
    # Read-only fields
    readonly_fields = [
        'id',
        'created_at',
        'funded_at',
        'completed_at',
        'days_since_created',
        'is_expired_display',
        'audit_log_count'
    ]
    
    # Organize fields in detail view
    fieldsets = (
        ('Transaction Details', {
            'fields': ('id', 'buyer', 'seller', 'group_listing')
        }),
        ('Payment Information', {
            'fields': ('amount', 'currency', 'usd_equivalent', 'payment_address', 'payment_tx_hash')
        }),
        ('Status & Timeline', {
            'fields': ('status', 'transfer_deadline', 'is_expired_display')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'funded_at', 'completed_at', 'days_since_created'),
            'classes': ('collapse',)
        }),
        ('Additional Information', {
            'fields': ('notes', 'audit_log_count'),
            'classes': ('collapse',)
        }),
    )
    
    # Enable actions for bulk operations
    actions = ['mark_as_disputed', 'mark_as_cancelled']
    
    def id_short(self, obj):
        """
        Display shortened version of UUID for better readability
        """
        return str(obj.id)[:8] + "..."
    id_short.short_description = "Transaction ID"
    
    def buyer_link(self, obj):
        """
        Create clickable link to buyer's profile
        """
        url = reverse('admin:escrow_telegramuser_change', args=[obj.buyer.id])
        return format_html('<a href="{}">{}</a>', url, obj.buyer.username or obj.buyer.telegram_id)
    buyer_link.short_description = "Buyer"
    
    def seller_link(self, obj):
        """
        Create clickable link to seller's profile
        """
        url = reverse('admin:escrow_telegramuser_change', args=[obj.seller.id])
        return format_html('<a href="{}">{}</a>', url, obj.seller.username or obj.seller.telegram_id)
    seller_link.short_description = "Seller"
    
    def amount_display(self, obj):
        """
        Display amount with currency and USD equivalent
        """
        usd_text = f" (${obj.usd_equivalent})" if obj.usd_equivalent else ""
        return f"{obj.amount} {obj.currency}{usd_text}"
    amount_display.short_description = "Amount"
    
    def status_colored(self, obj):
        """
        Display status with color coding for better visibility
        """
        colors = {
            'PENDING': 'orange',
            'FUNDED': 'blue',
            'AWAITING_TRANSFER': 'purple',
            'VERIFYING': 'yellow',
            'COMPLETED': 'green',
            'REFUNDED': 'red',
            'DISPUTED': 'darkred',
            'CANCELLED': 'gray'
        }
        color = colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_colored.short_description = "Status"
    
    def days_since_created(self, obj):
        """
        Calculate and display days since transaction was created
        """
        delta = timezone.now() - obj.created_at
        return f"{delta.days} days"
    days_since_created.short_description = "Age"
    
    def is_expired_display(self, obj):
        """
        Display if transaction has expired with visual indicator
        """
        if obj.is_expired():
            return format_html('<span style="color: red; font-weight: bold;">EXPIRED</span>')
        else:
            return format_html('<span style="color: green;">Active</span>')
    is_expired_display.short_description = "Expiry Status"
    
    def audit_log_count(self, obj):
        """
        Count number of audit log entries for this transaction
        """
        return obj.audit_logs.count()
    audit_log_count.short_description = "Audit Entries"
    
    # Custom admin actions
    def mark_as_disputed(self, request, queryset):
        """
        Bulk action to mark selected transactions as disputed
        """
        updated = queryset.update(status='DISPUTED')
        self.message_user(request, f'{updated} transactions marked as disputed.')
    mark_as_disputed.short_description = "Mark selected transactions as disputed"
    
    def mark_as_cancelled(self, request, queryset):
        """
        Bulk action to cancel selected transactions
        """
        updated = queryset.update(status='CANCELLED')
        self.message_user(request, f'{updated} transactions cancelled.')
    mark_as_cancelled.short_description = "Cancel selected transactions"

# =============================================================================
# PAYMENT WEBHOOK ADMIN
# =============================================================================

@admin.register(PaymentWebhook)
class PaymentWebhookAdmin(admin.ModelAdmin):
    """
    Admin interface for payment webhooks
    Used for debugging payment processing and audit trail
    """
    
    list_display = [
        'transaction_link',
        'processed',
        'created_at',
        'webhook_summary'
    ]
    
    list_filter = [
        'processed',
        'created_at'
    ]
    
    search_fields = [
        'transaction__id',
        'webhook_data'
    ]
    
    readonly_fields = [
        'transaction',
        'webhook_data',
        'created_at',
        'webhook_summary'
    ]
    
    def transaction_link(self, obj):
        """
        Create link to related transaction
        """
        url = reverse('admin:escrow_escrowtransaction_change', args=[obj.transaction.id])
        return format_html('<a href="{}">{}</a>', url, str(obj.transaction.id)[:8] + "...")
    transaction_link.short_description = "Transaction"
    
    def webhook_summary(self, obj):
        """
        Display summary of webhook data
        """
        if isinstance(obj.webhook_data, dict):
            return f"Keys: {', '.join(obj.webhook_data.keys())}"
        return "Raw data"
    webhook_summary.short_description = "Webhook Summary"

# =============================================================================
# DISPUTE CASE ADMIN
# =============================================================================

@admin.register(DisputeCase)
class DisputeCaseAdmin(admin.ModelAdmin):
    """
    Admin interface for managing dispute cases
    Critical for handling conflicts between buyers and sellers
    """
    
    list_display = [
        'id',
        'transaction_link',
        'opened_by_link',
        'status_colored',
        'created_at',
        'days_open'
    ]
    
    list_filter = [
        'status',
        'created_at',
        'resolved_at'
    ]
    
    search_fields = [
        'transaction__id',
        'opened_by__username',
        'description'
    ]
    
    readonly_fields = [
        'transaction',
        'opened_by',
        'created_at',
        'resolved_at',
        'days_open'
    ]
    
    fieldsets = (
        ('Dispute Information', {
            'fields': ('transaction', 'opened_by', 'status')
        }),
        ('Details', {
            'fields': ('description', 'resolution_notes')
        }),
        ('Resolution', {
            'fields': ('resolved_by', 'resolved_at'),
            'classes': ('collapse',)
        }),
        ('Timeline', {
            'fields': ('created_at', 'days_open'),
            'classes': ('collapse',)
        }),
    )
    
    def transaction_link(self, obj):
        """
        Link to the disputed transaction
        """
        url = reverse('admin:escrow_escrowtransaction_change', args=[obj.transaction.id])
        return format_html('<a href="{}">{}</a>', url, str(obj.transaction.id)[:8] + "...")
    transaction_link.short_description = "Transaction"
    
    def opened_by_link(self, obj):
        """
        Link to user who opened the dispute
        """
        url = reverse('admin:escrow_telegramuser_change', args=[obj.opened_by.id])
        return format_html('<a href="{}">{}</a>', url, obj.opened_by.username or obj.opened_by.telegram_id)
    opened_by_link.short_description = "Opened By"
    
    def status_colored(self, obj):
        """
        Color-coded status display
        """
        colors = {
            'OPEN': 'red',
            'INVESTIGATING': 'orange',
            'RESOLVED_SELLER': 'green',
            'RESOLVED_BUYER': 'blue',
            'CLOSED': 'gray'
        }
        color = colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_colored.short_description = "Status"
    
    def days_open(self, obj):
        """
        Calculate how long dispute has been open
        """
        if obj.resolved_at:
            delta = obj.resolved_at - obj.created_at
            return f"Resolved in {delta.days} days"
        else:
            delta = timezone.now() - obj.created_at
            return f"Open for {delta.days} days"
    days_open.short_description = "Duration"

# =============================================================================
# AUDIT LOG ADMIN
# =============================================================================

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Admin interface for audit logs
    Essential for tracking all system activities and debugging
    """
    
    list_display = [
        'timestamp',
        'action_colored',
        'transaction_link',
        'user_link',
        'details_summary'
    ]
    
    list_filter = [
        'action',
        'timestamp'
    ]
    
    search_fields = [
        'transaction__id',
        'user__username',
        'action',
        'details'
    ]
    
    readonly_fields = [
        'transaction',
        'action',
        'user',
        'details',
        'timestamp'
    ]
    
    # Show most recent entries first
    ordering = ['-timestamp']
    
    def transaction_link(self, obj):
        """
        Link to related transaction
        """
        if obj.transaction:
            url = reverse('admin:escrow_escrowtransaction_change', args=[obj.transaction.id])
            return format_html('<a href="{}">{}</a>', url, str(obj.transaction.id)[:8] + "...")
        return "N/A"
    transaction_link.short_description = "Transaction"
    
    def user_link(self, obj):
        """
        Link to user who performed the action
        """
        if obj.user:
            url = reverse('admin:escrow_telegramuser_change', args=[obj.user.id])
            return format_html('<a href="{}">{}</a>', url, obj.user.username or obj.user.telegram_id)
        return "System"
    user_link.short_description = "User"
    
    def action_colored(self, obj):
        """
        Color-coded action display
        """
        colors = {
            'ESCROW_CREATED': 'blue',
            'PAYMENT_RECEIVED': 'green',
            'TRANSFER_STARTED': 'orange',
            'OWNERSHIP_CHANGED': 'purple',
            'VERIFICATION_PASSED': 'green',
            'VERIFICATION_FAILED': 'red',
            'FUNDS_RELEASED': 'darkgreen',
            'FUNDS_REFUNDED': 'darkred',
            'DISPUTE_OPENED': 'red',
            'DISPUTE_RESOLVED': 'blue'
        }
        color = colors.get(obj.action, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_action_display()
        )
    action_colored.short_description = "Action"
    
    def details_summary(self, obj):
        """
        Show summary of details JSON
        """
        if isinstance(obj.details, dict) and obj.details:
            keys = list(obj.details.keys())[:3]  # Show first 3 keys
            summary = ', '.join(keys)
            if len(obj.details) > 3:
                summary += f" (+{len(obj.details) - 3} more)"
            return summary
        return "No details"
    details_summary.short_description = "Details"
