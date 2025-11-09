"""
Django Admin Configuration for Telegram Bot App

This module registers bot-related models with the Django admin interface.
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import BotSession, BotMessage, BotNotification


@admin.register(BotSession)
class BotSessionAdmin(admin.ModelAdmin):
    """Admin interface for BotSession model"""
    
    list_display = ('telegram_user_link', 'current_state', 'updated_at')
    list_filter = ('current_state', 'created_at', 'updated_at')
    search_fields = ('telegram_user__username', 'telegram_user__telegram_id')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Session Information', {
            'fields': ('telegram_user', 'current_state')
        }),
        ('Session Data', {
            'fields': ('session_data',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def telegram_user_link(self, obj):
        """Display user with link"""
        return format_html(
            '<a href="/admin/escrow/telegramuser/{}/change/">@{}</a>',
            obj.telegram_user.id, obj.telegram_user.username or obj.telegram_user.telegram_id
        )
    telegram_user_link.short_description = 'User'


@admin.register(BotMessage)
class BotMessageAdmin(admin.ModelAdmin):
    """Admin interface for BotMessage model"""
    
    list_display = ('telegram_user_link', 'message_type', 'command', 'text_preview', 'timestamp')
    list_filter = ('message_type', 'timestamp')
    search_fields = ('telegram_user__username', 'text', 'command')
    readonly_fields = (
        'telegram_user', 'message_type', 'text', 'message_id',
        'chat_id', 'command', 'callback_data', 'raw_data', 'timestamp'
    )
    
    def telegram_user_link(self, obj):
        """Display user with link"""
        return format_html(
            '<a href="/admin/escrow/telegramuser/{}/change/">@{}</a>',
            obj.telegram_user.id, obj.telegram_user.username or obj.telegram_user.telegram_id
        )
    telegram_user_link.short_description = 'User'
    
    def text_preview(self, obj):
        """Display text preview"""
        if obj.text:
            return obj.text[:50] + ('...' if len(obj.text) > 50 else '')
        return '-'
    text_preview.short_description = 'Text'
    
    def has_add_permission(self, request):
        """Prevent manual creation"""
        return False


@admin.register(BotNotification)
class BotNotificationAdmin(admin.ModelAdmin):
    """Admin interface for BotNotification model"""
    
    list_display = (
        'telegram_user_link', 'notification_type', 'status_badge',
        'title', 'send_at', 'sent_at'
    )
    list_filter = ('notification_type', 'status', 'send_at', 'sent_at')
    search_fields = ('telegram_user__username', 'title', 'message')
    readonly_fields = ('created_at', 'sent_at')
    
    fieldsets = (
        ('Notification Details', {
            'fields': ('telegram_user', 'notification_type', 'title', 'message', 'status')
        }),
        ('Scheduling', {
            'fields': ('send_at', 'sent_at')
        }),
        ('Related Data', {
            'fields': ('transaction', 'extra_data'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def telegram_user_link(self, obj):
        """Display user with link"""
        return format_html(
            '<a href="/admin/escrow/telegramuser/{}/change/">@{}</a>',
            obj.telegram_user.id, obj.telegram_user.username or obj.telegram_user.telegram_id
        )
    telegram_user_link.short_description = 'User'
    
    def status_badge(self, obj):
        """Display status with color coding"""
        colors = {
            'PENDING': '#FFA500',
            'SENT': '#4CAF50',
            'FAILED': '#F44336',
        }
        color = colors.get(obj.status, '#000000')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    actions = ['mark_as_sent', 'retry_failed']
    
    def mark_as_sent(self, request, queryset):
        """Mark notifications as sent"""
        from django.utils import timezone
        updated = queryset.update(status='SENT', sent_at=timezone.now())
        self.message_user(request, f'{updated} notification(s) marked as sent.')
    mark_as_sent.short_description = 'Mark as sent'
    
    def retry_failed(self, request, queryset):
        """Retry failed notifications"""
        updated = queryset.filter(status='FAILED').update(status='PENDING')
        self.message_user(request, f'{updated} notification(s) queued for retry.')
    retry_failed.short_description = 'Retry failed notifications'
