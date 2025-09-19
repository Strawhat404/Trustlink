"""
API Views for the Groups App

This module provides the API endpoints for browsing and viewing group listings.
It uses Django REST Framework's generic views to provide a standard, browsable API.

Endpoints:
- /api/groups/listings/ - List all active group listings (supports search and filtering).
- /api/groups/listings/<id>/ - Retrieve details for a single group listing.
"""

from rest_framework import generics, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend

from .models import GroupListing
from .serializers import GroupListingListSerializer, GroupListingDetailSerializer

class GroupListingListView(generics.ListAPIView):
    """
    API endpoint to list all active group listings.
    Supports filtering by category and searching by title.
    """
    queryset = GroupListing.objects.filter(status='ACTIVE').order_by('-created_at')
    serializer_class = GroupListingListSerializer
    permission_classes = [permissions.AllowAny]  # Marketplace should be public
    
    # Add filtering and search capabilities
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category']
    search_fields = ['group_title', 'group_description']
    ordering_fields = ['created_at', 'price_usd', 'member_count']

class GroupListingDetailView(generics.RetrieveAPIView):
    """
    API endpoint to retrieve the details of a single group listing.
    """
    queryset = GroupListing.objects.filter(status='ACTIVE')
    serializer_class = GroupListingDetailSerializer
    permission_classes = [permissions.AllowAny] # Marketplace should be public
    lookup_field = 'id'
