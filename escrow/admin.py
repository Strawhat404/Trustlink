"""
Django Admin Configuration for Escrow App

This module registers all escrow-related models with the Django admin interface,
providing a comprehensive management interface for administrators.
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import (
    TelegramUser,
    EscrowTransaction,
    PaymentWebhook,
    DisputeCase,
    AuditLog,
)


@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    """Admin interface for TelegramUser model"""
    
    list_display = ('telegram_id', 'username', 'full_name', 'is_verified', 'created_at')
    list_filter = ('is_verified', 'created_at')
    search_fields = ('telegram_id', 'username', 'first_name', 'last_name')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Telegram Information', {
            'fields': ('telegram_id', 'username', 'first_name', 'last_name')
        }),
        ('Account Status', {
            'fields': ('user', 'is_verified')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def full_name(self, obj):
        """Display full name"""
        return f"{obj.first_name or ''} {obj.last_name or ''}".strip() or "N/A"
    full_name.short_description = 'Full Name'


@admin.register(EscrowTransaction)
class EscrowTransactionAdmin(admin.ModelAdmin):
    """Admin interface for EscrowTransaction model"""
    
    list_display = (
        'id', 'status_badge', 'buyer_link', 'seller_link', 
        'amount_display', 'created_at', 'is_expired'
    )
    list_filter = ('status', 'currency', 'created_at', 'funded_at')
    search_fields = (
        'id', 'buyer__username', 'seller__username', 
        'group_listing__group_title', 'payment_tx_hash'
    )
    readonly_fields = (
        'id', 'created_at', 'funded_at', 'completed_at', 
        'payment_charge_url_link', 'payment_tx_hash'
    )
    
    fieldsets = (
        ('Transaction Details', {
            'fields': ('id', 'status', 'buyer', 'seller', 'group_listing')
        }),
        ('Payment Information', {
            'fields': (
                'amount', 'currency', 'usd_equivalent',
                'payment_charge_id', 'payment_charge_url_link',
                'payment_address', 'payment_tx_hash'
            )
        }),
        ('Timeline', {
            'fields': (
                'created_at', 'funded_at', 'transfer_deadline', 'completed_at'
            )
        }),
        ('Additional Information', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )
    
    def status_badge(self, obj):
        """Display status with color coding"""
        colors = {
            'PENDING': '#FFA500',
            'FUNDED': '#4CAF50',
            'AWAITING_TRANSFER': '#2196F3',
            'VERIFYING': '#9C27B0',
            'COMPLETED': '#4CAF50',
            'REFUNDED': '#FF9800',
            'DISPUTED': '#F44336',
            'CANCELLED': '#9E9E9E',
        }
        color = colors.get(obj.status, '#000000')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def buyer_link(self, obj):
        """Display buyer with link"""
        return format_html(
            '<a href="/admin/escrow/telegramuser/{}/change/">@{}</a>',
            obj.buyer.id, obj.buyer.username or obj.buyer.telegram_id
        )
    buyer_link.short_description = 'Buyer'
    
    def seller_link(self, obj):
        """Display seller with link"""
        return format_html(
            '<a href="/admin/escrow/telegramuser/{}/change/">@{}</a>',
            obj.seller.id, obj.seller.username or obj.seller.telegram_id
        )
    seller_link.short_description = 'Seller'
    
    def amount_display(self, obj):
        """Display amount with currency"""
        return f"{obj.amount} {obj.currency}"
    amount_display.short_description = 'Amount'
    
    def payment_charge_url_link(self, obj):
        """Display payment URL as clickable link"""
        if obj.payment_charge_url:
            return format_html(
                '<a href="{}" target="_blank">View Payment Page</a>',
                obj.payment_charge_url
            )
        return "N/A"
    payment_charge_url_link.short_description = 'Payment URL'


@admin.register(DisputeCase)
class DisputeCaseAdmin(admin.ModelAdmin):
    """Admin interface for DisputeCase model"""
    
    list_display = (
        'id', 'transaction_link', 'status', 'opened_by_link', 
        'arbitrator', 'ruling', 'created_at'
    )
    list_filter = ('status', 'ruling', 'created_at', 'resolved_at')
    search_fields = (
        'transaction__id', 'opened_by__username', 
        'description', 'resolution_notes'
    )
    readonly_fields = ('created_at', 'resolved_at')
    
    fieldsets = (
        ('Dispute Information', {
            'fields': ('transaction', 'opened_by', 'status', 'description')
        }),
        ('Arbitration', {
            'fields': ('arbitrator', 'evidence')
        }),
        ('Resolution', {
            'fields': ('ruling', 'resolution_notes', 'resolved_by', 'resolved_at')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def transaction_link(self, obj):
        """Display transaction with link"""
        return format_html(
            '<a href="/admin/escrow/escrowtransaction/{}/change/">{}</a>',
            obj.transaction.id, str(obj.transaction.id)[:8]
        )
    transaction_link.short_description = 'Transaction'
    
    def opened_by_link(self, obj):
        """Display user who opened dispute"""
        return format_html(
            '<a href="/admin/escrow/telegramuser/{}/change/">@{}</a>',
            obj.opened_by.id, obj.opened_by.username or obj.opened_by.telegram_id
        )
    opened_by_link.short_description = 'Opened By'
    
    actions = ['resolve_in_favor_of_seller', 'resolve_in_favor_of_buyer']
    
    def resolve_in_favor_of_seller(self, request, queryset):
        """Quick action to resolve disputes in favor of seller"""
        from .dispute_service import DisputeResolutionService
        
        count = 0
        for dispute in queryset.filter(status__in=['OPEN', 'INVESTIGATING']):
            success = DisputeResolutionService.resolve_dispute(
                dispute=dispute,
                ruling='FAVOR_SELLER',
                resolved_by=request.user,
                notes='Resolved via admin quick action'
            )
            if success:
                count += 1
        
        self.message_user(request, f'{count} dispute(s) resolved in favor of seller.')
    resolve_in_favor_of_seller.short_description = 'Resolve in favor of seller'
    
    def resolve_in_favor_of_buyer(self, request, queryset):
        """Quick action to resolve disputes in favor of buyer"""
        from .dispute_service import DisputeResolutionService
        
        count = 0
        for dispute in queryset.filter(status__in=['OPEN', 'INVESTIGATING']):
            success = DisputeResolutionService.resolve_dispute(
                dispute=dispute,
                ruling='FAVOR_BUYER',
                resolved_by=request.user,
                notes='Resolved via admin quick action'
            )
            if success:
                count += 1
        
        self.message_user(request, f'{count} dispute(s) resolved in favor of buyer.')
    resolve_in_favor_of_buyer.short_description = 'Resolve in favor of buyer'


@admin.register(PaymentWebhook)
class PaymentWebhookAdmin(admin.ModelAdmin):
    """Admin interface for PaymentWebhook model"""
    
    list_display = ('id', 'transaction_link', 'processed', 'created_at')
    list_filter = ('processed', 'created_at')
    search_fields = ('transaction__id',)
    readonly_fields = ('transaction', 'webhook_data', 'created_at')
    
    def transaction_link(self, obj):
        """Display transaction with link"""
        return format_html(
            '<a href="/admin/escrow/escrowtransaction/{}/change/">{}</a>',
            obj.transaction.id, str(obj.transaction.id)[:8]
        )
    transaction_link.short_description = 'Transaction'


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin interface for AuditLog model"""
    
    list_display = ('id', 'action', 'transaction_link', 'user_link', 'timestamp')
    list_filter = ('action', 'timestamp')
    search_fields = ('transaction__id', 'user__username')
    readonly_fields = ('transaction', 'action', 'user', 'details', 'timestamp')
    
    def transaction_link(self, obj):
        """Display transaction with link"""
        return format_html(
            '<a href="/admin/escrow/escrowtransaction/{}/change/">{}</a>',
            obj.transaction.id, str(obj.transaction.id)[:8]
        )
    transaction_link.short_description = 'Transaction'
    
    def user_link(self, obj):
        """Display user with link"""
        if obj.user:
            return format_html(
                '<a href="/admin/escrow/telegramuser/{}/change/">@{}</a>',
                obj.user.id, obj.user.username or obj.user.telegram_id
            )
        return "System"
    user_link.short_description = 'User'
    
    def has_add_permission(self, request):
        """Prevent manual creation of audit logs"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of audit logs"""
        return False
