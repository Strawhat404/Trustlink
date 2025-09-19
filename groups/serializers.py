"""
Serializers for the Groups App

This module defines how the GroupListing model and related data are converted to
JSON format for the API endpoints. It provides different levels of detail for
list views and detail views to optimize performance and data exposure.
"""

from rest_framework import serializers
from .models import GroupListing
from escrow.models import TelegramUser

class SellerSerializer(serializers.ModelSerializer):
    """Serializer for displaying seller information."""
    class Meta:
        model = TelegramUser
        fields = ('username', 'telegram_id', 'is_verified')

class GroupListingListSerializer(serializers.ModelSerializer):
    """
    A lightweight serializer for displaying a list of group listings.
    Used for the main marketplace browsing view.
    """
    category = serializers.CharField(source='get_category_display')
    
    class Meta:
        model = GroupListing
        fields = (
            'id',
            'group_title',
            'member_count',
            'price_usd',
            'category'
        )

class GroupListingDetailSerializer(serializers.ModelSerializer):
    """
    A detailed serializer for a single group listing.
    Provides all public information about a listing.
    """
    seller = SellerSerializer(read_only=True)
    category = serializers.CharField(source='get_category_display')
    status = serializers.CharField(source='get_status_display')

    class Meta:
        model = GroupListing
        fields = (
            'id',
            'group_title',
            'group_description',
            'member_count',
            'price_usd',
            'category',
            'status',
            'seller',
            'created_at'
        )
