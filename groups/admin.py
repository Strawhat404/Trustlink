"""
Django Admin Configuration for Groups App

This module registers all group-related models with the Django admin interface.
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import (
    GroupListing,
    GroupStateLog,
    AdminChangeLog,
    GroupMetadataSnapshot,
    GroupTransferLog,
    GroupVerificationResult,
)


@admin.register(GroupListing)
class GroupListingAdmin(admin.ModelAdmin):
    """Admin interface for GroupListing model"""
    
    list_display = (
        'group_title', 'seller_link', 'status_badge', 
        'price_usd', 'member_count', 'category', 'created_at'
    )
    list_filter = ('status', 'category', 'bot_is_admin', 'created_at')
    search_fields = ('group_title', 'group_username', 'seller__username', 'group_description')
    readonly_fields = ('id', 'created_at', 'updated_at', 'last_verified')
    
    fieldsets = (
        ('Group Information', {
            'fields': (
                'id', 'group_id', 'group_username', 'group_title', 
                'group_description', 'member_count'
            )
        }),
        ('Listing Details', {
            'fields': ('seller', 'price_usd', 'category', 'status')
        }),
        ('Verification', {
            'fields': (
                'bot_is_admin', 'last_verified', 'creation_date',
                'admin_list_snapshot'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'expires_at'),
            'classes': ('collapse',)
        }),
    )
    
    def status_badge(self, obj):
        """Display status with color coding"""
        colors = {
            'DRAFT': '#9E9E9E',
            'ACTIVE': '#4CAF50',
            'SOLD': '#2196F3',
            'SUSPENDED': '#FF9800',
            'EXPIRED': '#F44336',
        }
        color = colors.get(obj.status, '#000000')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def seller_link(self, obj):
        """Display seller with link"""
        return format_html(
            '<a href="/admin/escrow/telegramuser/{}/change/">@{}</a>',
            obj.seller.id, obj.seller.username or obj.seller.telegram_id
        )
    seller_link.short_description = 'Seller'
    
    actions = ['activate_listings', 'suspend_listings']
    
    def activate_listings(self, request, queryset):
        """Activate selected listings"""
        updated = queryset.update(status='ACTIVE')
        self.message_user(request, f'{updated} listing(s) activated.')
    activate_listings.short_description = 'Activate selected listings'
    
    def suspend_listings(self, request, queryset):
        """Suspend selected listings"""
        updated = queryset.update(status='SUSPENDED')
        self.message_user(request, f'{updated} listing(s) suspended.')
    suspend_listings.short_description = 'Suspend selected listings'


@admin.register(GroupStateLog)
class GroupStateLogAdmin(admin.ModelAdmin):
    """Admin interface for GroupStateLog model"""
    
    list_display = ('listing_link', 'title', 'member_count', 'timestamp')
    list_filter = ('timestamp',)
    search_fields = ('listing__group_title', 'title')
    readonly_fields = ('listing', 'timestamp', 'member_count', 'public_link', 'title', 'description_hash')
    
    def listing_link(self, obj):
        """Display listing with link"""
        return format_html(
            '<a href="/admin/groups/grouplisting/{}/change/">{}</a>',
            obj.listing.id, obj.listing.group_title
        )
    listing_link.short_description = 'Listing'
    
    def has_add_permission(self, request):
        """Prevent manual creation"""
        return False


@admin.register(AdminChangeLog)
class AdminChangeLogAdmin(admin.ModelAdmin):
    """Admin interface for AdminChangeLog model"""
    
    list_display = ('listing_link', 'action', 'admin_username', 'timestamp')
    list_filter = ('action', 'timestamp')
    search_fields = ('listing__group_title', 'admin_username')
    readonly_fields = (
        'listing', 'timestamp', 'admin_user_id', 
        'admin_username', 'action', 'performed_by_user_id'
    )
    
    def listing_link(self, obj):
        """Display listing with link"""
        return format_html(
            '<a href="/admin/groups/grouplisting/{}/change/">{}</a>',
            obj.listing.id, obj.listing.group_title
        )
    listing_link.short_description = 'Listing'
    
    def has_add_permission(self, request):
        """Prevent manual creation"""
        return False


@admin.register(GroupMetadataSnapshot)
class GroupMetadataSnapshotAdmin(admin.ModelAdmin):
    """Admin interface for GroupMetadataSnapshot model"""
    
    list_display = ('group_listing_link', 'snapshot_type', 'group_title', 'member_count', 'created_at')
    list_filter = ('snapshot_type', 'created_at')
    search_fields = ('group_listing__group_title', 'group_title')
    readonly_fields = (
        'group_listing', 'transaction', 'snapshot_type', 'group_title',
        'group_username', 'group_description', 'member_count', 'admin_list',
        'creator_id', 'pinned_message', 'created_at'
    )
    
    def group_listing_link(self, obj):
        """Display group listing with link"""
        return format_html(
            '<a href="/admin/groups/grouplisting/{}/change/">{}</a>',
            obj.group_listing.id, obj.group_listing.group_title
        )
    group_listing_link.short_description = 'Group Listing'
    
    def has_add_permission(self, request):
        """Prevent manual creation"""
        return False


@admin.register(GroupTransferLog)
class GroupTransferLogAdmin(admin.ModelAdmin):
    """Admin interface for GroupTransferLog model"""
    
    list_display = ('transaction_link', 'event_type', 'verified', 'detected_at')
    list_filter = ('event_type', 'verified', 'detected_at')
    search_fields = ('transaction__id', 'notes')
    readonly_fields = (
        'transaction', 'event_type', 'old_owner_id', 'new_owner_id',
        'admin_changes', 'detected_at', 'notes'
    )
    
    def transaction_link(self, obj):
        """Display transaction with link"""
        return format_html(
            '<a href="/admin/escrow/escrowtransaction/{}/change/">{}</a>',
            obj.transaction.id, str(obj.transaction.id)[:8]
        )
    transaction_link.short_description = 'Transaction'
    
    def has_add_permission(self, request):
        """Prevent manual creation"""
        return False


@admin.register(GroupVerificationResult)
class GroupVerificationResultAdmin(admin.ModelAdmin):
    """Admin interface for GroupVerificationResult model"""
    
    list_display = (
        'transaction_link', 'result_badge', 'ownership_verified',
        'metadata_matches', 'admin_permissions_correct', 'verified_at'
    )
    list_filter = ('result', 'ownership_verified', 'metadata_matches', 'verified_at')
    search_fields = ('transaction__id',)
    readonly_fields = (
        'transaction', 'result', 'ownership_verified', 'metadata_matches',
        'admin_permissions_correct', 'verification_details', 'failure_reasons',
        'verified_at'
    )
    
    def transaction_link(self, obj):
        """Display transaction with link"""
        return format_html(
            '<a href="/admin/escrow/escrowtransaction/{}/change/">{}</a>',
            obj.transaction.id, str(obj.transaction.id)[:8]
        )
    transaction_link.short_description = 'Transaction'
    
    def result_badge(self, obj):
        """Display result with color coding"""
        colors = {
            'PENDING': '#FFA500',
            'PASSED': '#4CAF50',
            'FAILED': '#F44336',
            'MANUAL_REVIEW': '#2196F3',
        }
        color = colors.get(obj.result, '#000000')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_result_display()
        )
    result_badge.short_description = 'Result'
    
    def has_add_permission(self, request):
        """Prevent manual creation"""
        return False
