"""
Groups URL Configuration

This module defines URL patterns for the groups app.
Currently contains placeholder patterns - will be expanded
when group management features are implemented.
"""

from django.urls import path
from . import views

# Define the app namespace for URL reversing
app_name = 'groups'

urlpatterns = [
    # Placeholder patterns - to be implemented in future phases
    # path('api/listings/', views.group_listings, name='group_listings'),
    # path('api/listings/<uuid:listing_id>/', views.group_detail, name='group_detail'),
]
