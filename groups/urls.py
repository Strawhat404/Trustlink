"""
Groups URL Configuration

This module defines the API URL patterns for the groups app, specifically for the marketplace listings.
"""

from django.urls import path
from .views import GroupListingListView, GroupListingDetailView

app_name = 'groups'

urlpatterns = [
    path('listings/', GroupListingListView.as_view(), name='group-listing-list'),
    path('listings/<uuid:id>/', GroupListingDetailView.as_view(), name='group-listing-detail'),
]
