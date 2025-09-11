from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import (
    BotSession,
    BotMessage,
    BotNotification
)

# =============================================================================
# BOT SESSION ADMIN
# =============================================================================

@admin.register(BotSession)
class BotSessionAdmin(admin.ModelAdmin):
    """
    Admin interface for managing bot user sessions
    Tracks conversation state and temporary data for each user
    """
    
    # Fields to display in the admin list view
    list_display = [
        'telegram_user_link',
        'current_state_colored',
        'session_data_summary',
        'created_at',
        'updated_at',
        'session_duration'
    ]
    
    # Fields for filtering sessions
    list_filter = [
        'current_state',
        'created_at',
        'updated_at'
    ]
    
    # Fields that can be searched
    search_fields = [
        'telegram_user__username',
        'telegram_user__telegram_id',
        'current_state',
        'session_data'
    ]
    
    # Read-only fields that cannot be edited
    readonly_fields = [
        'telegram_user',
        'created_at',
        'updated_at',
        'session_duration',
        'session_data_summary'
    ]
    
    # Organize fields in detail view
    fieldsets = (
        ('Session Information', {
            'fields': ('telegram_user', 'current_state')
        }),
        ('Session Data', {
            'fields': ('session_data', 'session_data_summary'),
            'classes': ('collapse',)
        }),
        ('Timeline', {
            'fields': ('created_at', 'updated_at', 'session_duration'),
            'classes': ('collapse',)
        }),
    )
    
    # Enable bulk actions
    actions = ['reset_to_idle', 'clear_session_data']
    
    def telegram_user_link(self, obj):
        """
        Create clickable link to telegram user's profile
        """
        url = reverse('admin:escrow_telegramuser_change', args=[obj.telegram_user.id])
        return format_html('<a href="{}">{}</a>', url, obj.telegram_user.username or obj.telegram_user.telegram_id)
    telegram_user_link.short_description = "User"
    
    def current_state_colored(self, obj):
        """
        Display current state with color coding for better visibility
        """
        colors = {
            'IDLE': 'gray',
            'REGISTERING': 'blue',
            'BROWSING_LISTINGS': 'green',
            'CREATING_LISTING': 'orange',
            'PURCHASING': 'purple',
            'TRANSFER_GUIDE': 'red',
            'DISPUTE': 'darkred'
        }
        color = colors.get(obj.current_state, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_current_state_display()
        )
    current_state_colored.short_description = "State"
    
    def session_data_summary(self, obj):
        """
        Display summary of session data
        """
        if isinstance(obj.session_data, dict) and obj.session_data:
            keys = list(obj.session_data.keys())[:3]  # Show first 3 keys
            summary = ', '.join(keys)
            if len(obj.session_data) > 3:
                summary += f" (+{len(obj.session_data) - 3} more)"
            return summary
        return "No session data"
    session_data_summary.short_description = "Data Summary"
    
    def session_duration(self, obj):
        """
        Calculate how long the session has been active
        """
        delta = timezone.now() - obj.created_at
        if delta.days > 0:
            return f"{delta.days} days"
        elif delta.seconds > 3600:
            hours = delta.seconds // 3600
            return f"{hours} hours"
        else:
            minutes = delta.seconds // 60
            return f"{minutes} minutes"
    session_duration.short_description = "Duration"
    
    # Custom admin actions
    def reset_to_idle(self, request, queryset):
        """
        Bulk action to reset selected sessions to IDLE state
        """
        updated = queryset.update(current_state='IDLE')
        self.message_user(request, f'{updated} sessions reset to IDLE.')
    reset_to_idle.short_description = "Reset selected sessions to IDLE"
    
    def clear_session_data(self, request, queryset):
        """
        Bulk action to clear session data for selected sessions
        """
        updated = queryset.update(session_data={})
        self.message_user(request, f'Session data cleared for {updated} sessions.')
    clear_session_data.short_description = "Clear session data"

# =============================================================================
# BOT MESSAGE ADMIN
# =============================================================================

@admin.register(BotMessage)
class BotMessageAdmin(admin.ModelAdmin):
    """
    Admin interface for bot message logs
    Essential for debugging bot conversations and user interactions
    """
    
    # Fields to display in the admin list view
    list_display = [
        'timestamp',
        'telegram_user_link',
        'message_type_colored',
        'text_preview',
        'command',
        'message_id'
    ]
    
    # Fields for filtering messages
    list_filter = [
        'message_type',
        'timestamp',
        'command'
    ]
    
    # Fields that can be searched
    search_fields = [
        'telegram_user__username',
        'telegram_user__telegram_id',
        'text',
        'command',
        'callback_data'
    ]
    
    # Read-only fields (all fields are read-only for audit purposes)
    readonly_fields = [
        'telegram_user',
        'message_type',
        'text',
        'message_id',
        'chat_id',
        'command',
        'callback_data',
        'raw_data',
        'timestamp',
        'text_preview',
        'raw_data_summary'
    ]
    
    # Organize fields in detail view
    fieldsets = (
        ('Message Information', {
            'fields': ('telegram_user', 'message_type', 'timestamp')
        }),
        ('Content', {
            'fields': ('text', 'text_preview', 'command', 'callback_data')
        }),
        ('Technical Details', {
            'fields': ('message_id', 'chat_id'),
            'classes': ('collapse',)
        }),
        ('Raw Data', {
            'fields': ('raw_data', 'raw_data_summary'),
            'classes': ('collapse',)
        }),
    )
    
    # Show most recent messages first
    ordering = ['-timestamp']
    
    # Limit the number of messages shown per page for performance
    list_per_page = 50
    
    def telegram_user_link(self, obj):
        """
        Create clickable link to telegram user's profile
        """
        url = reverse('admin:escrow_telegramuser_change', args=[obj.telegram_user.id])
        return format_html('<a href="{}">{}</a>', url, obj.telegram_user.username or obj.telegram_user.telegram_id)
    telegram_user_link.short_description = "User"
    
    def message_type_colored(self, obj):
        """
        Display message type with color coding
        """
        colors = {
            'INCOMING': 'blue',
            'OUTGOING': 'green',
            'COMMAND': 'orange',
            'CALLBACK': 'purple'
        }
        color = colors.get(obj.message_type, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_message_type_display()
        )
    message_type_colored.short_description = "Type"
    
    def text_preview(self, obj):
        """
        Show preview of message text (first 100 characters)
        """
        if obj.text:
            preview = obj.text[:100]
            if len(obj.text) > 100:
                preview += "..."
            return preview
        return "No text content"
    text_preview.short_description = "Text Preview"
    
    def raw_data_summary(self, obj):
        """
        Display summary of raw data
        """
        if isinstance(obj.raw_data, dict) and obj.raw_data:
            keys = list(obj.raw_data.keys())[:5]  # Show first 5 keys
            return ', '.join(keys)
        return "No raw data"
    raw_data_summary.short_description = "Raw Data Keys"

# =============================================================================
# BOT NOTIFICATION ADMIN
# =============================================================================

@admin.register(BotNotification)
class BotNotificationAdmin(admin.ModelAdmin):
    """
    Admin interface for bot notifications
    Manages queued notifications to be sent to users
    """
    
    # Fields to display in the admin list view
    list_display = [
        'telegram_user_link',
        'notification_type_colored',
        'title',
        'status_colored',
        'send_at',
        'sent_at',
        'created_at'
    ]
    
    # Fields for filtering notifications
    list_filter = [
        'notification_type',
        'status',
        'send_at',
        'sent_at',
        'created_at'
    ]
    
    # Fields that can be searched
    search_fields = [
        'telegram_user__username',
        'telegram_user__telegram_id',
        'title',
        'message',
        'transaction__id'
    ]
    
    # Read-only fields
    readonly_fields = [
        'telegram_user',
        'transaction',
        'created_at',
        'sent_at',
        'message_preview',
        'extra_data_summary',
        'delivery_delay'
    ]
    
    # Organize fields in detail view
    fieldsets = (
        ('Notification Details', {
            'fields': ('telegram_user', 'notification_type', 'title')
        }),
        ('Content', {
            'fields': ('message', 'message_preview')
        }),
        ('Scheduling', {
            'fields': ('status', 'send_at', 'sent_at', 'delivery_delay')
        }),
        ('Related Data', {
            'fields': ('transaction', 'extra_data', 'extra_data_summary'),
            'classes': ('collapse',)
        }),
        ('Timeline', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    # Enable bulk actions
    actions = ['mark_as_sent', 'mark_as_failed', 'reschedule_now']
    
    # Show most recent notifications first
    ordering = ['-created_at']
    
    def telegram_user_link(self, obj):
        """
        Create clickable link to telegram user's profile
        """
        url = reverse('admin:escrow_telegramuser_change', args=[obj.telegram_user.id])
        return format_html('<a href="{}">{}</a>', url, obj.telegram_user.username or obj.telegram_user.telegram_id)
    telegram_user_link.short_description = "User"
    
    def notification_type_colored(self, obj):
        """
        Display notification type with color coding
        """
        colors = {
            'PAYMENT_RECEIVED': 'green',
            'TRANSFER_REMINDER': 'orange',
            'VERIFICATION_COMPLETE': 'blue',
            'DISPUTE_UPDATE': 'red',
            'SYSTEM_ALERT': 'purple'
        }
        color = colors.get(obj.notification_type, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_notification_type_display()
        )
    notification_type_colored.short_description = "Type"
    
    def status_colored(self, obj):
        """
        Display status with color coding
        """
        colors = {
            'PENDING': 'orange',
            'SENT': 'green',
            'FAILED': 'red'
        }
        color = colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_colored.short_description = "Status"
    
    def message_preview(self, obj):
        """
        Show preview of notification message (first 150 characters)
        """
        if obj.message:
            preview = obj.message[:150]
            if len(obj.message) > 150:
                preview += "..."
            return preview
        return "No message content"
    message_preview.short_description = "Message Preview"
    
    def extra_data_summary(self, obj):
        """
        Display summary of extra data
        """
        if isinstance(obj.extra_data, dict) and obj.extra_data:
            keys = list(obj.extra_data.keys())[:3]  # Show first 3 keys
            return ', '.join(keys)
        return "No extra data"
    extra_data_summary.short_description = "Extra Data"
    
    def delivery_delay(self, obj):
        """
        Calculate delay between scheduled send time and actual send time
        """
        if obj.sent_at and obj.send_at:
            delta = obj.sent_at - obj.send_at
            if delta.total_seconds() > 0:
                if delta.days > 0:
                    return f"+{delta.days} days"
                elif delta.seconds > 3600:
                    hours = delta.seconds // 3600
                    return f"+{hours} hours"
                else:
                    minutes = delta.seconds // 60
                    return f"+{minutes} minutes"
            else:
                return "On time"
        elif obj.status == 'PENDING':
            if timezone.now() > obj.send_at:
                delta = timezone.now() - obj.send_at
                if delta.days > 0:
                    return format_html('<span style="color: red;">Overdue by {} days</span>', delta.days)
                elif delta.seconds > 3600:
                    hours = delta.seconds // 3600
                    return format_html('<span style="color: red;">Overdue by {} hours</span>', hours)
                else:
                    minutes = delta.seconds // 60
                    return format_html('<span style="color: red;">Overdue by {} minutes</span>', minutes)
            else:
                return "Scheduled"
        return "N/A"
    delivery_delay.short_description = "Delivery Status"
    
    # Custom admin actions
    def mark_as_sent(self, request, queryset):
        """
        Bulk action to mark selected notifications as sent
        """
        updated = queryset.update(status='SENT', sent_at=timezone.now())
        self.message_user(request, f'{updated} notifications marked as sent.')
    mark_as_sent.short_description = "Mark selected notifications as sent"
    
    def mark_as_failed(self, request, queryset):
        """
        Bulk action to mark selected notifications as failed
        """
        updated = queryset.update(status='FAILED')
        self.message_user(request, f'{updated} notifications marked as failed.')
    mark_as_failed.short_description = "Mark selected notifications as failed"
    
    def reschedule_now(self, request, queryset):
        """
        Bulk action to reschedule selected notifications to send immediately
        """
        updated = queryset.update(send_at=timezone.now(), status='PENDING')
        self.message_user(request, f'{updated} notifications rescheduled to send now.')
    reschedule_now.short_description = "Reschedule selected notifications to send now"
