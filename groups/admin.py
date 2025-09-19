from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import (
    GroupListing, 
    GroupMetadataSnapshot, 
    GroupTransferLog, 
    GroupVerificationResult,
    GroupStateLog,
    AdminChangeLog
)

# =============================================================================
# GROUP LISTING ADMIN
# =============================================================================

@admin.register(GroupListing)
class GroupListingAdmin(admin.ModelAdmin):
    """
    Admin interface for managing Telegram group listings
    This handles all groups available for sale on the platform
    """
    
    # Fields to display in the admin list view
    list_display = [
        'group_title',
        'seller_link',
        'price_usd',
        'member_count',
        'category',
        'status_colored',
        'bot_is_admin',
        'created_at'
    ]
    
    # Fields for filtering listings
    list_filter = [
        'status',
        'category',
        'bot_is_admin',
        'created_at',
        'expires_at'
    ]
    
    # Fields that can be searched
    search_fields = [
        'group_title',
        'group_username',
        'group_description',
        'seller__username',
        'group_id'
    ]
    
    # Read-only fields that cannot be edited
    readonly_fields = [
        'group_id',
        'creation_date',
        'created_at',
        'updated_at',
        'last_verified',
        'days_since_created',
        'is_expired_display',
        'total_snapshots'
    ]
    
    # Organize fields in detail view
    fieldsets = (
        ('Group Information', {
            'fields': ('group_id', 'group_username', 'group_title', 'group_description', 'member_count')
        }),
        ('Listing Details', {
            'fields': ('seller', 'price_usd', 'category', 'status')
        }),
        ('Bot Validation', {
            'fields': ('bot_is_admin', 'last_verified'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('creation_date', 'pinned_message', 'admin_list_snapshot'),
            'classes': ('collapse',)
        }),
        ('Timeline', {
            'fields': ('created_at', 'updated_at', 'expires_at', 'days_since_created', 'is_expired_display'),
            'classes': ('collapse',)
        }),
        ('Statistics', {
            'fields': ('total_snapshots',),
            'classes': ('collapse',)
        }),
    )
    
    # Enable bulk actions
    actions = ['mark_as_active', 'mark_as_suspended', 'verify_bot_admin']
    
    def seller_link(self, obj):
        """
        Create clickable link to seller's profile
        """
        url = reverse('admin:escrow_telegramuser_change', args=[obj.seller.id])
        return format_html('<a href="{}">{}</a>', url, obj.seller.username or obj.seller.telegram_id)
    seller_link.short_description = "Seller"
    
    def status_colored(self, obj):
        """
        Display status with color coding for better visibility
        """
        colors = {
            'DRAFT': 'gray',
            'ACTIVE': 'green',
            'SOLD': 'blue',
            'SUSPENDED': 'red',
            'EXPIRED': 'orange'
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
        Calculate and display days since listing was created
        """
        delta = timezone.now() - obj.created_at
        return f"{delta.days} days"
    days_since_created.short_description = "Age"
    
    def is_expired_display(self, obj):
        """
        Display if listing has expired with visual indicator
        """
        if obj.is_expired():
            return format_html('<span style="color: red; font-weight: bold;">EXPIRED</span>')
        else:
            return format_html('<span style="color: green;">Active</span>')
    is_expired_display.short_description = "Expiry Status"
    
    def total_snapshots(self, obj):
        """
        Count total number of metadata snapshots for this listing
        """
        return obj.metadata_snapshots.count()
    total_snapshots.short_description = "Snapshots"
    
    # Custom admin actions
    def mark_as_active(self, request, queryset):
        """
        Bulk action to mark selected listings as active
        """
        updated = queryset.update(status='ACTIVE')
        self.message_user(request, f'{updated} listings marked as active.')
    mark_as_active.short_description = "Mark selected listings as active"
    
    def mark_as_suspended(self, request, queryset):
        """
        Bulk action to suspend selected listings
        """
        updated = queryset.update(status='SUSPENDED')
        self.message_user(request, f'{updated} listings suspended.')
    mark_as_suspended.short_description = "Suspend selected listings"
    
    def verify_bot_admin(self, request, queryset):
        """
        Bulk action to verify bot admin status (placeholder for future implementation)
        """
        # This would trigger actual verification in a real implementation
        updated = queryset.update(last_verified=timezone.now())
        self.message_user(request, f'Verification timestamp updated for {updated} listings.')
    verify_bot_admin.short_description = "Update verification timestamp"

# =============================================================================
# GROUP METADATA SNAPSHOT ADMIN
# =============================================================================

@admin.register(GroupMetadataSnapshot)
class GroupMetadataSnapshotAdmin(admin.ModelAdmin):
    """
    Admin interface for group metadata snapshots
    Critical for verification process - stores group state at different points in time
    """
    
    list_display = [
        'group_listing_link',
        'snapshot_type_colored',
        'group_title',
        'member_count',
        'creator_id',
        'created_at'
    ]
    
    list_filter = [
        'snapshot_type',
        'created_at'
    ]
    
    search_fields = [
        'group_listing__group_title',
        'group_title',
        'group_username',
        'transaction__id'
    ]
    
    readonly_fields = [
        'group_listing',
        'transaction',
        'snapshot_type',
        'group_title',
        'group_username',
        'group_description',
        'member_count',
        'admin_list',
        'creator_id',
        'pinned_message',
        'created_at',
        'admin_count'
    ]
    
    fieldsets = (
        ('Snapshot Information', {
            'fields': ('group_listing', 'transaction', 'snapshot_type', 'created_at')
        }),
        ('Group Data at Snapshot Time', {
            'fields': ('group_title', 'group_username', 'group_description', 'member_count', 'creator_id')
        }),
        ('Administrative Data', {
            'fields': ('admin_list', 'admin_count', 'pinned_message'),
            'classes': ('collapse',)
        }),
    )
    
    def group_listing_link(self, obj):
        """
        Create link to the related group listing
        """
        url = reverse('admin:groups_grouplisting_change', args=[obj.group_listing.id])
        return format_html('<a href="{}">{}</a>', url, obj.group_listing.group_title)
    group_listing_link.short_description = "Group Listing"
    
    def snapshot_type_colored(self, obj):
        """
        Color-coded snapshot type display
        """
        colors = {
            'LISTING_CREATED': 'blue',
            'PRE_TRANSFER': 'orange',
            'POST_TRANSFER': 'green',
            'VERIFICATION': 'purple'
        }
        color = colors.get(obj.snapshot_type, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_snapshot_type_display()
        )
    snapshot_type_colored.short_description = "Snapshot Type"
    
    def admin_count(self, obj):
        """
        Count number of admins in the admin list
        """
        if isinstance(obj.admin_list, list):
            return len(obj.admin_list)
        return 0
    admin_count.short_description = "Admin Count"

# =============================================================================
# GROUP TRANSFER LOG ADMIN
# =============================================================================

@admin.register(GroupTransferLog)
class GroupTransferLogAdmin(admin.ModelAdmin):
    """
    Admin interface for group transfer logs
    Tracks all events during the group ownership transfer process
    """
    
    list_display = [
        'transaction_link',
        'event_type_colored',
        'old_owner_id',
        'new_owner_id',
        'verified',
        'detected_at'
    ]
    
    list_filter = [
        'event_type',
        'verified',
        'detected_at'
    ]
    
    search_fields = [
        'transaction__id',
        'old_owner_id',
        'new_owner_id',
        'notes'
    ]
    
    readonly_fields = [
        'transaction',
        'event_type',
        'old_owner_id',
        'new_owner_id',
        'admin_changes',
        'detected_at',
        'admin_changes_summary'
    ]
    
    fieldsets = (
        ('Transfer Event', {
            'fields': ('transaction', 'event_type', 'detected_at')
        }),
        ('Ownership Changes', {
            'fields': ('old_owner_id', 'new_owner_id')
        }),
        ('Administrative Changes', {
            'fields': ('admin_changes', 'admin_changes_summary'),
            'classes': ('collapse',)
        }),
        ('Verification', {
            'fields': ('verified', 'notes'),
            'classes': ('collapse',)
        }),
    )
    
    def transaction_link(self, obj):
        """
        Create link to the related transaction
        """
        url = reverse('admin:escrow_escrowtransaction_change', args=[obj.transaction.id])
        return format_html('<a href="{}">{}</a>', url, str(obj.transaction.id)[:8] + "...")
    transaction_link.short_description = "Transaction"
    
    def event_type_colored(self, obj):
        """
        Color-coded event type display
        """
        colors = {
            'BUYER_ADDED': 'blue',
            'BUYER_PROMOTED': 'orange',
            'OWNERSHIP_TRANSFERRED': 'green',
            'SELLER_LEFT': 'red',
            'VERIFICATION_COMPLETED': 'purple'
        }
        color = colors.get(obj.event_type, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_event_type_display()
        )
    event_type_colored.short_description = "Event Type"
    
    def admin_changes_summary(self, obj):
        """
        Display summary of admin changes
        """
        if isinstance(obj.admin_changes, dict) and obj.admin_changes:
            changes = []
            for key, value in obj.admin_changes.items():
                changes.append(f"{key}: {value}")
            return "; ".join(changes[:3])  # Show first 3 changes
        return "No changes recorded"
    admin_changes_summary.short_description = "Changes Summary"

# =============================================================================
# GROUP VERIFICATION RESULT ADMIN
# =============================================================================

@admin.register(GroupVerificationResult)
class GroupVerificationResultAdmin(admin.ModelAdmin):
    """
    Admin interface for group verification results
    Shows the outcome of automated verification checks
    """
    
    list_display = [
        'transaction_link',
        'result_colored',
        'ownership_verified',
        'metadata_matches',
        'admin_permissions_correct',
        'verified_at'
    ]
    
    list_filter = [
        'result',
        'ownership_verified',
        'metadata_matches',
        'admin_permissions_correct',
        'verified_at'
    ]
    
    search_fields = [
        'transaction__id',
        'verification_details',
        'failure_reasons'
    ]
    
    readonly_fields = [
        'transaction',
        'result',
        'ownership_verified',
        'metadata_matches',
        'admin_permissions_correct',
        'verification_details',
        'failure_reasons',
        'verified_at',
        'verification_score',
        'failure_count'
    ]
    
    fieldsets = (
        ('Verification Overview', {
            'fields': ('transaction', 'result', 'verified_at', 'verification_score')
        }),
        ('Check Results', {
            'fields': ('ownership_verified', 'metadata_matches', 'admin_permissions_correct')
        }),
        ('Detailed Results', {
            'fields': ('verification_details',),
            'classes': ('collapse',)
        }),
        ('Failure Analysis', {
            'fields': ('failure_reasons', 'failure_count'),
            'classes': ('collapse',)
        }),
    )
    
    def transaction_link(self, obj):
        """
        Create link to the related transaction
        """
        url = reverse('admin:escrow_escrowtransaction_change', args=[obj.transaction.id])
        return format_html('<a href="{}">{}</a>', url, str(obj.transaction.id)[:8] + "...")
    transaction_link.short_description = "Transaction"
    
    def result_colored(self, obj):
        """
        Color-coded verification result display
        """
        colors = {
            'PENDING': 'orange',
            'PASSED': 'green',
            'FAILED': 'red',
            'MANUAL_REVIEW': 'purple'
        }
        color = colors.get(obj.result, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_result_display()
        )
    result_colored.short_description = "Result"
    
    def verification_score(self, obj):
        """
        Calculate verification score based on passed checks
        """
        checks = [obj.ownership_verified, obj.metadata_matches, obj.admin_permissions_correct]
        passed = sum(checks)
        total = len(checks)
        percentage = (passed / total) * 100 if total > 0 else 0
        
        color = 'green' if percentage >= 100 else 'orange' if percentage >= 66 else 'red'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.0f}% ({}/{})</span>',
            color, percentage, passed, total
        )
    verification_score.short_description = "Score"
    
    def failure_count(self, obj):
        """
        Count number of failure reasons
        """
        if isinstance(obj.failure_reasons, list):
            return len(obj.failure_reasons)
        return 0
    failure_count.short_description = "Failures"

# =============================================================================
# GROUP MONITORING LOGS ADMIN
# =============================================================================

@admin.register(GroupStateLog)
class GroupStateLogAdmin(admin.ModelAdmin):
    """
    Admin interface for group state logs.
    Provides a historical view of a group's state over time.
    """
    list_display = ('listing_link', 'timestamp', 'member_count', 'title')
    list_filter = ('listing__group_title', 'timestamp')
    search_fields = ('listing__group_title', 'title')
    ordering = ('-timestamp',)
    
    def listing_link(self, obj):
        url = reverse('admin:groups_grouplisting_change', args=[obj.listing.id])
        return format_html('<a href="{}">{}</a>', url, obj.listing.group_title)
    listing_link.short_description = "Group Listing"

@admin.register(AdminChangeLog)
class AdminChangeLogAdmin(admin.ModelAdmin):
    """
    Admin interface for group admin change logs.
    Tracks additions and removals of administrators for security auditing.
    """
    list_display = ('listing_link', 'timestamp', 'admin_username', 'action_colored', 'performed_by_user_id')
    list_filter = ('action', 'listing__group_title', 'timestamp')
    search_fields = ('listing__group_title', 'admin_username')
    ordering = ('-timestamp',)

    def listing_link(self, obj):
        url = reverse('admin:groups_grouplisting_change', args=[obj.listing.id])
        return format_html('<a href="{}">{}</a>', url, obj.listing.group_title)
    listing_link.short_description = "Group Listing"

    def action_colored(self, obj):
        color = 'green' if obj.action == 'added' else 'red'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_action_display()
        )
    action_colored.short_description = "Action"
